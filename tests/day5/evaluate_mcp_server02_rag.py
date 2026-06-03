# -*- coding: utf-8 -*-
"""
Day5 mcp_server02 - search_manual RAG 검색 성능 평가 스크립트 (보완판 v2)

[위치]
이 파일은 tests/day5/ 에 있습니다(이전에는 scripts/day5/ 에 있었음 — tests/day5 로 이동).
실행: uv run python tests/day5/evaluate_mcp_server02_rag.py [--limit N] [--case-id RAG-EVAL-001]

[목적]
Day4 평가 케이스(data/day4_rag_evaluation_cases.json)를 '그대로 재사용'하되,
검색 실행 경로는 Day5 mcp_server02 의 실제 MCP Tool 흐름
(call_mcp_tool('search_manual', ...) → tool_executor → manual_search → rag_quality_adapter → rag_search)
을 사용해 검색 성능을 재측정한다.

[이 보완판(v2)에서 개선한 평가 정확도]
1. alarm_code 정규식 보정: ALM-TEMP-402 가 ALM-TEMP 로 잘리던 문제 제거(숫자형 ALM-9999 포함).
2. equipment_id 추출(검색 인자로는 넘기지 않음 — contract 에 없음).
3. out_of_scope 지표 분리: positive(긍정) 검색 지표(hit@k/MRR)에서 out_of_scope/none 제외.
4. evidence_type 세분화: doc_name 기준(doc_hit) / signal 기준(signal_hit) 분리.
   - answer_caution_policy 는 전용 doc_name 이 없으므로 doc_hit 을 N/A(평가 제외)로 처리.
5. metadata gap 표시(metadata_partial_hit / metadata_gap / missing_metadata_keys).
6. auxiliary_equipment_id_hit: metadata.equipment_id 가 비어 있어도 title/snippet/keywords 에
   query 의 equipment_id 가 있으면 '보조 hit'로 분리 기록(정식 metadata_hit 과 구분).
7. direct_evidence_found: query 에서 추출한 식별자(alarm_code/equipment_id/process)가 문서에
   직접 존재하는지 표시(out_of_scope 직접 근거 부족 진단용).
8. quality gate: 현재 성능을 기준선으로 기록(리포트용, exit code 는 실패로 만들지 않음).

[오버피팅 방지 — 매우 중요]
- expected_keywords / expected_metadata / expected_evidence_type 등 '정답 라벨'은
  채점/분석에만 쓰고, 검색 입력·rerank·direct_evidence 판정 로직에는 사용하지 않는다.
- 특정 case_id / 특정 알람 코드 전용 분기를 두지 않는다. 모든 추출은 일반 정규식/키워드.

[이 스크립트가 하지 않는 것]
- Day4 원본/데이터 수정, vector_db/metadata DB 수정, mcp_server01/02 코드 수정.
- search_manual contract 에 top_k 노출(이 스크립트는 top_k 를 Tool argument 로 넘기지 않는다).

[출력]
- outputs/day5/mcp_server02/rag_eval/{results.json, summary.json, report.md}

[보안]
- 문서 전문/metadata 원문 전체를 콘솔에 출력하지 않는다. snippet_preview 는 길이 제한 저장.

[이 파일의 성격 — 교육용으로 꼭 이해할 점]
- 이 스크립트는 '합격/불합격을 가르는 단위 테스트'가 아니라 RAG 검색 품질을 '측정·기록'하는 평가
  하베스트(harness)입니다. 케이스마다 PASS/WARNING/FAIL/INFO 를 매기지만, 프로그램 전체 종료 코드는
  항상 0 입니다(quality gate 가 미달이어도 실패로 끝내지 않음 — CI 연동은 --fail-on-gate TODO).
- 검색 실행은 '같은 프로세스 안에서' call_mcp_tool('search_manual', ...) 를 직접 호출합니다(in-process).
  즉 별도 서버 프로세스(subprocess)나 stdio/http transport, async/await, 호출 timeout 은 이 파일에
  존재하지 않습니다. 서버 내부에서 임베딩·벡터 검색이 일어나지만, 이 스크립트 입장에서는 함수 한 번
  호출로 결과 dict 를 받는 동기 흐름입니다.

[전체 실행 흐름 한눈에]
main() → run() → load_cases() 로 케이스 로드 → 케이스마다 evaluate_case() 호출
  → evaluate_case() 안에서 call_mcp_tool('search_manual') 로 문서 검색
  → 반환 문서를 각종 evaluate_*() 지표 함수로 채점 → judge_status() 로 케이스 상태 판정
  → build_summary()/build_report() 로 집계·보고서 작성 → outputs/day5/.../{results,summary,report} 저장.
"""
from __future__ import annotations

# 표준 라이브러리만 사용한다(외부 패키지 의존 없음).
# argparse: CLI 옵션(--limit/--case-id) 파싱 / json: 케이스·결과 입출력 / re: 식별자 정규식 추출 /
# sys: import 경로(sys.path) 보강 / pathlib.Path: OS 무관 경로 처리.
import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 경로 설정 (항상 프로젝트 루트 기준, 어디서 실행해도 동일)
# ---------------------------------------------------------------------------
# 이 파일: <root>/tests/day5/evaluate_mcp_server02_rag.py
#   parents[0]=day5, [1]=tests, [2]=<root>  → parents[2] 가 프로젝트 루트.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# CASES_PATH: Day4 에서 만든 평가 케이스 묶음(읽기 전용으로 재사용). OUTPUT_DIR: 결과 3종 저장 위치.
CASES_PATH = _PROJECT_ROOT / "data" / "day4_rag_evaluation_cases.json"
OUTPUT_DIR = _PROJECT_ROOT / "outputs" / "day5" / "mcp_server02" / "rag_eval"

CONFIGURED_TOP_K = 10  # mcp_server02 adapter 기본값과 동일(이 스크립트는 검증/기록만)

# 채점에 실제로 '사용하는' 정답 라벨 필드. 검색 입력에는 쓰지 않고 평가에만 쓴다(오버피팅 방지).
USED_EXPECTED_FIELDS = [
    "expected_keywords",
    "expected_metadata",
    "expected_evidence_type",
    "case_design_type",
]
# 케이스에 '있을 수도 있는' 보조 필드. 없으면 expected_fields_missing 에 기록해 데이터 공백을 드러낸다.
CANDIDATE_MISSING_FIELDS = ["expected_doc_name", "expected_answer", "teaching_point"]

# 검색 결과에 절대 섞여 나오면 안 되는 민감/내부 key. 하나라도 보이면 그 케이스는 FAIL 처리한다.
# (문서 전문/원본 경로/내부 URL/벡터 거리값 등 — 클라이언트로 새어 나가면 안 되는 값들.)
FORBIDDEN_KEYS = (
    "full_text", "chroma:document", "source_path", "file_path",
    "internal_url", "raw_metadata", "raw_text", "distance",
)
# 결과 문자열 어딘가에 http(s):// 링크가 들어 있으면 내부 경로 노출 의심 → 금지 신호로 본다.
_URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)

# ---------------------------------------------------------------------------
# 식별자 추출 정규식
# ---------------------------------------------------------------------------
# [alarm_code] 문자형(ALM-TEMP-402)과 숫자형(ALM-9999) 모두, 한글 조사 인접에도 전체 추출.
#   lookaround 로 경계 처리(단순 \b 는 'ALM-...402은' 에서 ALM-TEMP 로 잘림).
ALARM_CODE_PATTERN = re.compile(r"(?<![A-Za-z0-9])ALM-(?:[A-Z]+-)?\d+(?![A-Za-z0-9-])", re.IGNORECASE)
# [equipment_id] 예: EQP-EV-03 / EQP-CVD-02
EQUIPMENT_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])EQP-[A-Z]+-\d+(?![A-Za-z0-9])", re.IGNORECASE)

# [process 후보] query 에서 추출하는 일반 공정 키워드(정답 라벨 아님).
#   direct_evidence_found 판정의 보조 신호. 범위밖 공정(ETCH 등)이면 문서에 없어 missing 으로 잡힌다.
_PROCESS_CANDIDATES = ["etch", "증착", "evaporation", "검사", "inspection", "cleaning", "세정", "cvd"]


# ---------------------------------------------------------------------------
# expected_evidence_type → 문서/키워드 mapping 기준
# ---------------------------------------------------------------------------
# document 가 ① metadata.doc_name 이 preferred_docs 에 속하면 'doc 기준 부합',
#            ② title/section_title/doc_name/keywords/snippet 합본에 signal 키워드가 있으면 'signal 기준 부합'.
# 현재 지식베이스 doc_name: alarm_manual.md / quality_standard.md / troubleshooting_guide.md
# [중요] answer_caution_policy 는 전용 doc_name 이 없다(preferred_docs 비어 있음) → doc_hit 평가 N/A.
EVIDENCE_TYPE_MAP = {
    "alarm_manual": {
        "preferred_docs": {"alarm_manual.md"},
        "signals": ["alarm", "manual", "알람", "매뉴얼"],
    },
    "troubleshooting_manual": {
        "preferred_docs": {"troubleshooting_guide.md"},
        "signals": ["troubleshooting", "트러블슈팅", "조치", "원인", "반복", "정비"],
    },
    "quality_standard_document": {
        "preferred_docs": {"quality_standard.md"},
        "signals": ["quality", "품질", "수율", "불량률", "검사"],
    },
    "maintenance_and_troubleshooting_guide": {
        "preferred_docs": {"troubleshooting_guide.md"},
        "signals": ["maintenance", "정비", "troubleshooting", "조치", "반복"],
    },
    "answer_caution_policy": {
        "preferred_docs": set(),  # 전용 문서 없음 → doc_hit N/A. signal 로만 판정.
        "signals": ["caution", "policy", "단정", "확정", "근거", "주의", "제어", "교육", "답변"],
    },
    "none": {"preferred_docs": set(), "signals": []},
    "out_of_scope": {"preferred_docs": set(), "signals": []},
}

# 직접 근거가 '없어야' 정상인 evidence_type(긍정 타깃에서 제외).
_NON_POSITIVE_EVIDENCE = {"none", "out_of_scope"}

# ---------------------------------------------------------------------------
# quality gate 임계값 (리포트용 기준선; exit code 는 실패로 만들지 않음)
# ---------------------------------------------------------------------------
# min_* 는 '이상이어야 통과', max_* 는 '이하여야 통과'. 측정값을 이 기준과 비교해 gate 통과 여부만 기록한다.
QUALITY_GATE_THRESHOLDS = {
    "min_positive_hit_at_3": 0.90,        # 긍정 케이스 상위 3건 안에 정답 문서가 들어온 비율
    "min_mean_mrr_positive": 0.90,        # 긍정 케이스 평균 MRR(정답이 앞 순위일수록 1.0 에 가까움)
    "min_keyword_any_hit_rate": 0.80,     # 기대 키워드가 결과에 하나라도 잡힌 비율
    "min_evidence_type_doc_hit_rate": 0.70,  # 전용 문서가 있는 유형에서 그 문서가 검색된 비율
    "max_forbidden_field_case_count": 0,  # 금지 필드가 노출된 케이스 수(보안 — 0 이어야 함)
    "max_fallback_count": 0,              # mock_fallback 으로 떨어진 케이스 수(실제 검색 실패 신호)
    "max_fail_count": 0,                  # FAIL 케이스 수
}


def _norm(value) -> str:
    """비교용 정규화: 문자열화 + 앞뒤 공백 제거 + 소문자(형태소 분석은 하지 않음)."""
    return str(value if value is not None else "").strip().lower()


def is_out_of_scope_case(case: dict) -> bool:
    """out_of_scope/none 케이스 여부(positive 지표에서 제외 대상)."""
    cdt = _norm(case.get("case_design_type"))
    evt = _norm(case.get("expected_evidence_type"))
    return cdt == "out_of_scope" or evt in _NON_POSITIVE_EVIDENCE


def load_cases() -> list[dict]:
    """평가 케이스 JSON 을 읽어 list[dict] 로 돌려준다(읽기 전용, 수정하지 않음).

    [실패하면 의심할 것] CASES_PATH 경로 오류(파일 없음) 또는 JSON 형식 오류.
    encoding='utf-8-sig' 는 Windows 에서 저장된 BOM 을 함께 처리하기 위함이다(이 저장소 공통 규칙).
    """
    raw = CASES_PATH.read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    return [c for c in data if isinstance(c, dict)]


def extract_identifiers(case: dict) -> dict:
    """query 본문에서 alarm_code / equipment_id / process 후보를 추출한다.

    - query_alarm_code / query_equipment_id / query_processes: query 본문에서만 추출(정답 미사용).
    - search 인자용 alarm_code: query 우선 → 없으면 expected_metadata.alarm_code(보조).
    - direct_evidence_found 판정에는 'query 추출분(query_*)' 만 사용한다.
    - equipment_id 는 search_manual 인자로 넘기지 않는다(contract 에 없음).
    """
    query = str(case.get("user_query", "") or "")
    expected_metadata = case.get("expected_metadata") or {}

    am = ALARM_CODE_PATTERN.search(query)
    query_alarm_code = am.group(0) if am else None
    if query_alarm_code:
        alarm_code, alarm_source = query_alarm_code, "query"
    elif expected_metadata.get("alarm_code"):
        alarm_code, alarm_source = expected_metadata.get("alarm_code"), "expected_metadata"
    else:
        alarm_code, alarm_source = None, "none"

    eq = EQUIPMENT_ID_PATTERN.search(query)
    query_equipment_id = eq.group(0) if eq else None
    if query_equipment_id:
        equipment_id, equip_source = query_equipment_id, "query"
    elif expected_metadata.get("equipment_id"):
        equipment_id, equip_source = expected_metadata.get("equipment_id"), "expected_metadata"
    else:
        equipment_id, equip_source = None, "none"

    q_lower = query.lower()
    query_processes = [p for p in _PROCESS_CANDIDATES if p in q_lower]

    args = {"query": query}
    if alarm_code:
        args["alarm_code"] = alarm_code

    return {
        "args": args,
        "alarm_code_source": alarm_source,
        "extracted_equipment_id": equipment_id,
        "equipment_id_source": equip_source,
        "query_alarm_code": query_alarm_code,
        "query_equipment_id": query_equipment_id,
        "query_processes": query_processes,
    }


def _doc_combined_text(doc: dict) -> str:
    """document 의 title/snippet/metadata(허용 값)를 합쳐 소문자 한 덩어리로(키워드/식별자 검사용)."""
    metadata = doc.get("metadata") or {}
    parts = [str(doc.get("title", "") or ""), str(doc.get("snippet", "") or "")]
    if isinstance(metadata, dict):
        for value in metadata.values():
            parts.append(str(value if value is not None else ""))
    return _norm(" ".join(parts))


def _doc_aux_text(doc: dict) -> str:
    """metadata.equipment_id 를 '제외'한 보조 필드 합본(title/snippet/keywords/section_title)."""
    metadata = doc.get("metadata") or {}
    parts = [str(doc.get("title", "") or ""), str(doc.get("snippet", "") or "")]
    if isinstance(metadata, dict):
        for key in ("keywords", "section_title", "doc_name", "symptom", "action"):
            parts.append(str(metadata.get(key, "") or ""))
    return _norm(" ".join(parts))


def evaluate_keywords(expected_keywords: list, documents: list) -> dict:
    """expected_keywords 가 반환 문서(어느 하나)에 포함되는지 본다(any/all, 단순 포함 기준).

    [의미] keyword_any_hit=하나라도 포함, keyword_all_hit=모두 포함. 형태소 분석 없이 부분 문자열 포함만 본다.
    [실패하면 의심할 것] 검색이 엉뚱한 문서를 가져왔거나, 정답 키워드 라벨이 실제 문서 표현과 어긋남.
    """
    keywords = [k for k in (expected_keywords or []) if str(k).strip()]
    if not keywords:
        return {"keyword_any_hit": None, "keyword_all_hit": None,
                "matched_keywords": [], "missing_keywords": []}
    combined_all = " ".join(_doc_combined_text(d) for d in documents)
    matched, missing = [], []
    for kw in keywords:
        (matched if (_norm(kw) and _norm(kw) in combined_all) else missing).append(kw)
    return {
        "keyword_any_hit": len(matched) >= 1,
        "keyword_all_hit": len(missing) == 0,
        "matched_keywords": matched,
        "missing_keywords": missing,
    }


def doc_matches_metadata(doc: dict, expected_metadata: dict) -> bool:
    """document 의 metadata 가 expected_metadata 의 모든 (key,val) 과 일치하는가(단일 문서 기준)."""
    if not expected_metadata:
        return False
    metadata = doc.get("metadata") or {}
    if not isinstance(metadata, dict):
        return False
    return all(_norm(metadata.get(k)) == _norm(v) for k, v in expected_metadata.items())


def evaluate_metadata(expected_metadata: dict, documents: list) -> dict:
    """expected_metadata 의 key 단위 충족도를 본다(full / partial / gap).

    - per-key: 어느 문서든 해당 key=value 가 일치하면 그 key 는 matched.
    - metadata_hit: 모든 key matched / metadata_partial_hit: 일부만 / metadata_gap = partial.
    - expected_metadata 가 비어 있으면 모두 None(not_applicable).
    """
    if not expected_metadata:
        return {"metadata_hit": None, "metadata_partial_hit": None, "metadata_gap": None,
                "matched_metadata": {}, "missing_metadata_keys": []}
    matched, missing = {}, []
    for key, val in expected_metadata.items():
        hit = any(
            isinstance(d.get("metadata"), dict) and _norm(d["metadata"].get(key)) == _norm(val)
            for d in documents
        )
        if hit:
            matched[key] = val
        else:
            missing.append(key)
    full = len(missing) == 0
    partial = (len(matched) >= 1) and (len(missing) >= 1)
    return {
        "metadata_hit": bool(full),
        "metadata_partial_hit": bool(partial),
        "metadata_gap": bool(partial),
        "matched_metadata": matched,
        "missing_metadata_keys": missing,
    }


def evaluate_auxiliary_equipment_id(query_equipment_id, documents: list) -> dict:
    """metadata.equipment_id 가 비어 있어도 보조 필드에 equipment_id 가 있으면 보조 hit 기록.

    - query 에서 추출한 equipment_id 가 없으면 모두 None(not_applicable).
    - metadata.equipment_id 가 직접 일치하는 문서는 '정식 metadata' 영역이므로 보조에서 제외한다.
    - title/snippet/keywords/section_title 등 보조 필드에서 equipment_id 가 등장하면 auxiliary hit.
    [주의] 이 값은 검색/rerank 에 사용하지 않는다. metadata_hit 을 억지로 true 로 바꾸지 않는다.
    """
    if not query_equipment_id:
        return {"auxiliary_equipment_id_hit": None, "auxiliary_equipment_id_rank": None}
    target = _norm(query_equipment_id)
    rank = None
    for index, doc in enumerate(documents):
        metadata = doc.get("metadata") or {}
        meta_eq = _norm(metadata.get("equipment_id")) if isinstance(metadata, dict) else ""
        if meta_eq == target:
            continue  # 정식 metadata 일치는 보조 hit 가 아님
        if target and target in _doc_aux_text(doc):
            rank = index + 1
            break
    return {"auxiliary_equipment_id_hit": rank is not None, "auxiliary_equipment_id_rank": rank}


def evaluate_direct_evidence(ids: dict, documents: list) -> dict:
    """query 에서 추출한 식별자(alarm_code/equipment_id/process)가 문서에 직접 존재하는지 본다.

    - expected_* 정답 라벨은 사용하지 않는다(query 추출분만).
    - 추출된 식별자가 하나도 없으면 None(not_applicable).
    - direct_evidence_found: 추출된 식별자가 '모두' 어느 문서엔가 직접 등장하면 True.
    - matched_fields: 직접 등장한 식별자 종류. missing_identifiers: 등장하지 않은 식별자 값.
    """
    identifiers = []
    if ids.get("query_alarm_code"):
        identifiers.append(("alarm_code", ids["query_alarm_code"]))
    if ids.get("query_equipment_id"):
        identifiers.append(("equipment_id", ids["query_equipment_id"]))
    for proc in ids.get("query_processes", []):
        identifiers.append(("process", proc))

    if not identifiers:
        return {"direct_evidence_found": None,
                "direct_evidence_matched_fields": [], "direct_evidence_missing_identifiers": []}

    combined_all = " ".join(_doc_combined_text(d) for d in documents)
    matched_fields, missing = [], []
    for field, value in identifiers:
        if _norm(value) and _norm(value) in combined_all:
            if field not in matched_fields:
                matched_fields.append(field)
        else:
            missing.append(value)
    return {
        "direct_evidence_found": len(missing) == 0,
        "direct_evidence_matched_fields": matched_fields,
        "direct_evidence_missing_identifiers": missing,
    }


def _evidence_doc_match(doc: dict, mapping: dict) -> bool:
    """doc_name 기준 evidence 부합 여부."""
    metadata = doc.get("metadata") or {}
    doc_name = _norm(metadata.get("doc_name")) if isinstance(metadata, dict) else ""
    return bool(doc_name) and doc_name in {d.lower() for d in mapping["preferred_docs"]}


def _evidence_signal_match(doc: dict, mapping: dict) -> bool:
    """signal 키워드 기준 evidence 부합 여부."""
    if not mapping["signals"]:
        return False
    combined = _doc_combined_text(doc)
    return any(sig in combined for sig in mapping["signals"])


def evaluate_evidence_type(evidence_type: str, documents: list) -> dict:
    """evidence_type 을 doc 기준 / signal 기준으로 분리 평가한다.

    - evidence_type_doc_applicable: 전용 doc_name(preferred_docs)이 있는 유형만 True.
      answer_caution_policy 처럼 전용 문서가 없으면 False → doc_hit=None(평가 제외).
    - evidence_type_doc_hit: applicable 일 때만 True/False, 아니면 None.
    - evidence_type_signal_hit: signal 키워드 기준.
    - evidence_type_hit: doc_hit(있으면) 또는 signal_hit 중 하나라도 True.
    - none/out_of_scope 는 긍정 타깃 아님 → 모두 None.
    """
    evt = _norm(evidence_type)
    mapping = EVIDENCE_TYPE_MAP.get(evt)
    if not mapping or evt in _NON_POSITIVE_EVIDENCE:
        return {"evidence_type_doc_applicable": False,
                "evidence_type_doc_hit": None, "evidence_type_signal_hit": None,
                "evidence_type_hit": None, "matched_evidence_type_rank": None,
                "matched_evidence_type_doc_rank": None, "matched_evidence_type_signal_rank": None}

    doc_applicable = len(mapping["preferred_docs"]) > 0
    doc_rank = signal_rank = None
    for index, doc in enumerate(documents):
        if doc_applicable and doc_rank is None and _evidence_doc_match(doc, mapping):
            doc_rank = index + 1
        if signal_rank is None and _evidence_signal_match(doc, mapping):
            signal_rank = index + 1
        if (not doc_applicable or doc_rank is not None) and signal_rank is not None:
            break

    doc_hit = (doc_rank is not None) if doc_applicable else None
    signal_hit = signal_rank is not None
    # evidence_type_hit: doc 적용 가능하면 doc 또는 signal, 아니면 signal 만으로 판정.
    if doc_applicable:
        hit = (doc_hit is True) or signal_hit
    else:
        hit = signal_hit
    ranks = [r for r in (doc_rank, signal_rank) if r is not None]
    return {
        "evidence_type_doc_applicable": doc_applicable,
        "evidence_type_doc_hit": doc_hit,
        "evidence_type_signal_hit": signal_hit,
        "evidence_type_hit": bool(hit),
        "matched_evidence_type_rank": min(ranks) if ranks else None,
        "matched_evidence_type_doc_rank": doc_rank,
        "matched_evidence_type_signal_rank": signal_rank,
    }


def evaluate_rank(case: dict, documents: list) -> dict:
    """positive(긍정) 케이스에 대해서만 hit@k / MRR 을 계산한다.

    - out_of_scope/none 케이스는 positive 지표에서 제외 → 모두 None(positive_rank_evaluable=False).
    - relevant 문서: expected_metadata 전체 일치(단일 문서) OR evidence(doc/signal) 부합.

    [지표 의미] hit@k = 정답 문서가 상위 k건 안에 있는가, MRR = 1/(정답의 첫 등장 순위).
      정답이 1순위면 MRR=1.0, 2순위면 0.5 … 즉 '정답을 얼마나 앞쪽에 올렸는가'를 본다.
    [실패하면 의심할 것] 임베딩/색인 품질 저하, 정답 문서 누락, expected_metadata 와 실제 metadata 불일치.
    """
    out_of_scope = is_out_of_scope_case(case)
    expected_metadata = case.get("expected_metadata") or {}
    evt = _norm(case.get("expected_evidence_type"))
    mapping = EVIDENCE_TYPE_MAP.get(evt)
    has_md_basis = bool(expected_metadata)
    has_ev_basis = (evt not in _NON_POSITIVE_EVIDENCE) and (mapping is not None)

    none_result = {
        "rank_evaluable": False, "positive_rank_evaluable": False,
        "hit_at_1": None, "hit_at_3": None, "hit_at_5": None, "hit_at_10": None,
        "mrr": None, "first_relevant_rank": None,
    }
    if out_of_scope or not (has_md_basis or has_ev_basis):
        return none_result

    # 상위부터 훑으며 '처음으로 관련 있는 문서'의 순위(1-base)를 찾는다. 찾는 즉시 멈춘다(첫 등장만 필요).
    first_rank = None
    for index, doc in enumerate(documents):
        relevant = False
        if has_md_basis and doc_matches_metadata(doc, expected_metadata):
            relevant = True
        if not relevant and has_ev_basis and (
            _evidence_doc_match(doc, mapping) or _evidence_signal_match(doc, mapping)
        ):
            relevant = True
        if relevant:
            first_rank = index + 1
            break

    def hit_at(k):
        return (first_rank is not None) and (first_rank <= k)

    return {
        "rank_evaluable": True, "positive_rank_evaluable": True,
        "hit_at_1": hit_at(1), "hit_at_3": hit_at(3), "hit_at_5": hit_at(5), "hit_at_10": hit_at(10),
        "mrr": (1.0 / first_rank) if first_rank else 0.0,
        "first_relevant_rank": first_rank,
    }


def scan_forbidden(result_payload: dict) -> dict:
    """반환 result 에서 금지 key/문자열(URL)이 있는지 검사한다(보안 검증).

    [왜 필요한가] RAG 결과에 문서 전문/원본 경로/내부 URL/벡터 거리 같은 내부 값이 섞이면 안 된다.
    하나라도 발견되면 judge_status 에서 그 케이스를 FAIL 로 만든다.
    [실패하면 의심할 것] 서버의 결과 sanitize 로직이 빠졌거나, 문서 metadata 에 내부 필드가 새로 추가됨.
    """
    found_keys = set()
    found_url = False

    # 중첩 dict/list 를 재귀로 훑어, 어떤 깊이에 숨어 있어도 금지 key·URL 을 놓치지 않는다.
    def walk(node):
        nonlocal found_url
        if isinstance(node, dict):
            for key, val in node.items():
                if str(key) in FORBIDDEN_KEYS:
                    found_keys.add(str(key))
                walk(val)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            if _URL_PATTERN.search(node):
                found_url = True

    walk(result_payload)
    forbidden = sorted(found_keys)
    if found_url:
        forbidden.append("url_pattern")
    return {"forbidden_field_found": len(forbidden) > 0, "forbidden_fields": forbidden}


def build_top_documents(documents: list, max_docs: int = 5, snippet_chars: int = 150) -> list:
    """결과 저장용 상위 문서 미리보기(문서 전문/metadata 원문 전체 저장 금지)."""
    preview = []
    for index, doc in enumerate(documents[:max_docs]):
        snippet = str(doc.get("snippet", "") or "")
        preview.append({
            "rank": index + 1,
            "doc_id": str(doc.get("doc_id", "") or ""),
            "title": str(doc.get("title", "") or ""),
            "metadata": doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {},
            "snippet_preview": snippet[:snippet_chars] + ("..." if len(snippet) > snippet_chars else ""),
        })
    return preview


def judge_status(case: dict, m: dict) -> tuple[str, str]:
    """케이스 유형/지표로 PASS/WARNING/FAIL/INFO 판정. (status, note) 반환.

    [판정 우선순위] 케이스 '설계 의도(case_design_type)'에 따라 기대가 다르므로 분기 순서가 중요하다.
      ① 보안(금지 필드) → ② out_of_scope(직접 근거가 없어야 정상) → ③ low_confidence(주의/단정 금지)
      → ④ 긍정 케이스(직접 근거/다중 문서: 키워드+metadata/evidence 가 함께 맞아야 PASS).
    아래 if 순서를 바꾸면 같은 검색 결과라도 다른 status 가 나오므로 순서 자체가 판정 규칙의 일부다.
    """
    cdt = _norm(case.get("case_design_type"))
    is_lowconf = cdt == "low_confidence"
    out_of_scope = is_out_of_scope_case(case)
    success = m["returned_doc_count"] >= 1

    # ① 보안 최우선: 금지 필드가 새어 나왔다면 검색 적중과 무관하게 FAIL.
    if m["forbidden_field_found"]:
        return "FAIL", "금지 필드(full_text/source_path 등)가 반환됨"

    # ② 범위 밖 질문: 직접 근거가 '없어야' 정상. 오히려 정답 metadata 가 전부 맞으면 오판 위험 → FAIL.
    if out_of_scope:
        if m.get("metadata_hit") is True:
            return "FAIL", "out_of_scope/none 인데 expected_metadata 전부 직접 매칭(확정 근거 오판 가능)"
        return "WARNING", "out_of_scope/none: 단순 search Tool 은 확정 근거 사용 여부 미판정(한계)"

    # ③ 저신뢰(주의/단정 금지) 케이스: 주의성 근거(evidence_type)나 최소한 키워드가 잡혀야 한다.
    if is_lowconf:
        if not success:
            return "FAIL", "low_confidence 인데 검색 결과 없음"
        if m.get("evidence_type_hit") is True:
            return "PASS", "low_confidence: 주의/단정 금지 성격 근거(evidence_type) 검색됨"
        if m.get("keyword_any_hit"):
            return "WARNING", "low_confidence: 일부 keyword 만 검색됨"
        return "FAIL", "low_confidence: 주의 근거/keyword 모두 검색되지 않음"

    # ④ 긍정 케이스(direct_evidence / multi_document_evidence): 결과가 있어야 하고, 키워드와
    #    (metadata 또는 evidence_type) 근거가 함께 맞을 때만 PASS. 일부만 맞으면 WARNING.
    if not success:
        return "FAIL", "검색 결과 없음"
    md = m.get("metadata_hit")
    ev = m.get("evidence_type_hit")
    kany = m.get("keyword_any_hit")
    strong = (md is True) or (ev is True)
    if kany and strong:
        return "PASS", "검색 성공 + keyword + (metadata 또는 evidence_type) 부합"
    if (md is not True) and (ev is not True):
        if cdt == "direct_evidence":
            return "FAIL", "직접 근거 케이스인데 metadata/evidence_type 모두 미부합"
        return "WARNING", "metadata/evidence_type 모두 미부합(부분 결과)"
    return "WARNING", "검색은 되었으나 일부 expected 기준만 부합"


def evaluate_case(case: dict) -> dict:
    """한 케이스를 mcp_server02 search_manual 로 검색·평가한다.

    [이 함수가 사실상 '한 건의 테스트']
    - Given: 평가 케이스 1건(user_query 와 expected_* 정답 라벨)과 실행 가능한 mcp_server02 RAG.
    - When : query 로 search_manual Tool 을 호출해 문서 목록을 받는다(아래 call_mcp_tool).
    - Then : 받은 문서를 여러 evaluate_*() 로 채점하고 judge_status() 로 PASS/WARNING/FAIL 을 매긴다.
    [반환] 케이스 1건의 입력·검색출처·모든 지표·상태를 담은 record dict(results.json 한 줄이 된다).
    """
    # 지연 import: 서버 모듈을 함수 안에서 불러온다. 파일이 로드되는 시점이 아니라 '실제 검색 직전'에
    # 의존성을 잡아, import 단계의 부작용/실패가 스크립트 전체를 막지 않게 한다.
    # 또한 이 호출은 같은 프로세스 안의 직접 함수 호출이다(별도 서버 프로세스/transport 가 아님).
    from day5.mcp_server02.mcp_server import call_mcp_tool  # 지연 import

    expected_keywords = case.get("expected_keywords") or []
    expected_metadata = case.get("expected_metadata") or {}
    out_of_scope = is_out_of_scope_case(case)
    # query 본문에서 alarm_code/equipment_id/process 를 정규식으로 뽑는다(정답 라벨은 검색 입력에 안 씀).
    ids = extract_identifiers(case)
    args = ids["args"]

    record = {
        "case_id": case.get("case_id"),
        "query": args.get("query"),
        "category": case.get("category"),
        "case_design_type": case.get("case_design_type"),
        "difficulty": case.get("difficulty"),
        "configured_top_k": CONFIGURED_TOP_K,
        "out_of_scope_case": out_of_scope,
        "search_arguments_used": {k: v for k, v in args.items() if k != "query"},
        "alarm_code_source": ids["alarm_code_source"],
        "extracted_equipment_id": ids["extracted_equipment_id"],
        "equipment_id_source": ids["equipment_id_source"],
        "expected_evidence_type": case.get("expected_evidence_type"),
        "expected_metadata": expected_metadata,
        "expected_fields_used": list(USED_EXPECTED_FIELDS),
        "expected_fields_missing": [f for f in CANDIDATE_MISSING_FIELDS if f not in case],
        "failure_reason_to_check": case.get("failure_reason_to_check"),
        "expected_improvement_hint": case.get("expected_improvement_hint"),
        "error_message": None,
    }

    # [When] 자연어 query 를 search_manual Tool 로 보낸다. 서버 내부에서 임베딩→벡터 검색→문서 조립이
    # 일어난 뒤 결과 dict 가 돌아온다. 검색은 외부 인덱스/임베딩 상태에 따라 느려질 수 있으나, 이 평가
    # 스크립트는 호출 timeout 을 두지 않고 동기적으로 끝까지 기다린다.
    try:
        tool_result = call_mcp_tool("search_manual", args)
    except Exception as error:
        # 검색 호출 자체가 예외로 죽어도 평가 전체를 멈추지 않는다. 이 케이스만 ERROR 로 기록하고
        # (예외 타입+메시지 앞부분만 저장) 다음 케이스로 넘어간다 → 한 건 실패가 전체 리포트를 막지 않음.
        record.update({
            "status": "ERROR", "status_note": "call_mcp_tool 실행 실패",
            "returned_doc_count": 0, "retrieval_source": "unknown", "fallback_used": None,
            "error_message": f"{type(error).__name__}: {str(error)[:200]}",
        })
        return record

    # 서버 응답 구조: {results: [{tool_name, result: {documents:[...], retrieval_source, ...}}]}.
    # 형(type) 검사를 단계마다 넣어, 예상과 다른 구조가 와도 빈 값으로 안전하게 흘러가게 한다.
    results = tool_result.get("results") if isinstance(tool_result, dict) else None
    payload = {}
    if isinstance(results, list) and results and isinstance(results[0], dict):
        payload = results[0].get("result") or {}
    documents = payload.get("documents") if isinstance(payload, dict) else None
    documents = documents if isinstance(documents, list) else []

    # [Then] 받은 문서를 여러 채점 함수로 평가해 한 dict 로 합친다(**로 펼쳐 병합).
    # retrieval_source='chroma' 면 실제 벡터 검색, 'mock_fallback' 이면 인덱스 미준비 등으로 대체 응답.
    metrics = {
        "returned_doc_count": len(documents),
        "retrieval_source": payload.get("retrieval_source", "unknown"),
        "fallback_used": bool(payload.get("fallback_used")),
        **scan_forbidden(payload),
        **evaluate_keywords(expected_keywords, documents),
        **evaluate_metadata(expected_metadata, documents),
        **evaluate_auxiliary_equipment_id(ids.get("query_equipment_id"), documents),
        **evaluate_evidence_type(case.get("expected_evidence_type"), documents),
        **evaluate_direct_evidence(ids, documents),
        **evaluate_rank(case, documents),
    }
    metrics["out_of_scope_false_positive"] = bool(out_of_scope and metrics.get("metadata_hit") is True)

    status, note = judge_status(case, metrics)
    record.update(metrics)
    record["status"] = status
    record["status_note"] = note
    record["top_documents"] = build_top_documents(documents)
    return record


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def build_quality_gate(summary: dict) -> dict:
    """현재 summary 값으로 quality gate 통과 여부를 계산한다(리포트용)."""
    actual_map = {
        "min_positive_hit_at_3": summary["hit_at_3_positive"],
        "min_mean_mrr_positive": summary["mean_mrr_positive"],
        "min_keyword_any_hit_rate": summary["keyword_any_hit_rate"],
        "min_evidence_type_doc_hit_rate": summary["evidence_type_doc_hit_rate"],
        "max_forbidden_field_case_count": summary["forbidden_field_case_count"],
        "max_fallback_count": summary["fallback_count"],
        "max_fail_count": summary["fail_count"],
    }
    checks = {}
    all_passed = True
    for name, threshold in QUALITY_GATE_THRESHOLDS.items():
        actual = actual_map[name]
        passed = (actual >= threshold) if name.startswith("min_") else (actual <= threshold)
        checks[name] = {"threshold": threshold, "actual": actual, "passed": bool(passed)}
        all_passed = all_passed and passed
    return {"passed": bool(all_passed), "checks": checks}


def build_summary(results: list[dict]) -> dict:
    """케이스 결과 집계(positive 지표와 out_of_scope 지표를 분리)."""
    total = len(results)
    status_counts = {"PASS": 0, "WARNING": 0, "FAIL": 0, "INFO": 0, "ERROR": 0}
    for r in results:
        status_counts[r.get("status", "INFO")] = status_counts.get(r.get("status", "INFO"), 0) + 1

    positive = [r for r in results if not r.get("out_of_scope_case")]
    oos = [r for r in results if r.get("out_of_scope_case")]
    pos_rank = [r for r in positive if r.get("positive_rank_evaluable")]

    kw_any_den = [r for r in results if r.get("keyword_any_hit") is not None]
    kw_all_den = [r for r in results if r.get("keyword_all_hit") is not None]
    md_den = [r for r in results if r.get("metadata_hit") is not None]
    # evidence doc: applicable 한 케이스만 분모(answer_caution_policy/none/oos 제외)
    ev_doc_den = [r for r in results if r.get("evidence_type_doc_applicable") and r.get("evidence_type_doc_hit") is not None]
    ev_sig_den = [r for r in results if r.get("evidence_type_signal_hit") is not None]
    ev_den = [r for r in results if r.get("evidence_type_hit") is not None]
    aux_den = [r for r in results if r.get("auxiliary_equipment_id_hit") is not None]
    de_den = [r for r in results if r.get("direct_evidence_found") is not None]
    mrr_den = [r for r in pos_rank if r.get("mrr") is not None]

    summary = {
        "total_cases": total,
        "configured_top_k": CONFIGURED_TOP_K,
        "pass_count": status_counts["PASS"],
        "warning_count": status_counts["WARNING"],
        "fail_count": status_counts["FAIL"],
        "info_count": status_counts["INFO"],
        "error_count": status_counts["ERROR"],

        "positive_case_count": len(positive),
        "positive_rank_evaluable_count": len(pos_rank),

        "keyword_any_hit_rate": _rate(sum(1 for r in kw_any_den if r["keyword_any_hit"]), len(kw_any_den)),
        "keyword_all_hit_rate": _rate(sum(1 for r in kw_all_den if r["keyword_all_hit"]), len(kw_all_den)),

        "metadata_hit_rate": _rate(sum(1 for r in md_den if r["metadata_hit"]), len(md_den)),
        "metadata_partial_hit_rate": _rate(sum(1 for r in md_den if r.get("metadata_partial_hit")), len(md_den)),
        "metadata_gap_case_count": sum(1 for r in results if r.get("metadata_gap") is True),

        "auxiliary_equipment_id_hit_count": sum(1 for r in aux_den if r["auxiliary_equipment_id_hit"]),
        "auxiliary_equipment_id_hit_rate": _rate(sum(1 for r in aux_den if r["auxiliary_equipment_id_hit"]), len(aux_den)),

        "evidence_type_doc_evaluable_count": len(ev_doc_den),
        "evidence_type_doc_hit_rate": _rate(sum(1 for r in ev_doc_den if r["evidence_type_doc_hit"]), len(ev_doc_den)),
        "evidence_type_signal_hit_rate": _rate(sum(1 for r in ev_sig_den if r["evidence_type_signal_hit"]), len(ev_sig_den)),
        "evidence_type_hit_rate": _rate(sum(1 for r in ev_den if r["evidence_type_hit"]), len(ev_den)),

        "hit_at_1_positive": _rate(sum(1 for r in pos_rank if r["hit_at_1"]), len(pos_rank)),
        "hit_at_3_positive": _rate(sum(1 for r in pos_rank if r["hit_at_3"]), len(pos_rank)),
        "hit_at_5_positive": _rate(sum(1 for r in pos_rank if r["hit_at_5"]), len(pos_rank)),
        "hit_at_10_positive": _rate(sum(1 for r in pos_rank if r["hit_at_10"]), len(pos_rank)),
        "mean_mrr_positive": _rate(sum(r["mrr"] for r in mrr_den), len(mrr_den)),

        "out_of_scope_case_count": len(oos),
        "out_of_scope_warning_count": sum(1 for r in oos if r.get("status") == "WARNING"),
        "out_of_scope_fail_count": sum(1 for r in oos if r.get("status") == "FAIL"),
        "out_of_scope_false_positive_count": sum(1 for r in oos if r.get("out_of_scope_false_positive")),

        "direct_evidence_found_count": sum(1 for r in de_den if r["direct_evidence_found"]),
        "direct_evidence_missing_count": sum(1 for r in de_den if not r["direct_evidence_found"]),

        "fallback_count": sum(1 for r in results if r.get("fallback_used")),
        "chroma_count": sum(1 for r in results if r.get("retrieval_source") == "chroma"),
        "avg_returned_doc_count": _rate(sum(r.get("returned_doc_count", 0) for r in results), total),
        "forbidden_field_case_count": sum(1 for r in results if r.get("forbidden_field_found")),

        "low_confidence_case_count": sum(1 for r in results if _norm(r.get("case_design_type")) == "low_confidence"),
        "low_confidence_pass_count": sum(
            1 for r in results
            if _norm(r.get("case_design_type")) == "low_confidence" and r.get("status") == "PASS"
        ),
    }
    summary["quality_gate"] = build_quality_gate(summary)
    return summary


def _md(text) -> str:
    """Markdown 표 셀용 간단 escape."""
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def build_report(results: list[dict], summary: dict) -> str:
    """사람이 읽기 좋은 Markdown 보고서를 만든다."""
    L = []
    L.append("# mcp_server02 search_manual RAG 검색 성능 평가 보고서 (보완판 v2)\n")

    L.append("## 1. 평가 기준 변경 요약")
    L.append("- 평가 스크립트 위치 이동: `scripts/day5/` → **`tests/day5/`**.")
    L.append("- `answer_caution_policy` 는 전용 doc_name 이 없어 **doc_hit 을 N/A 처리**(doc_hit_rate 분모 제외).")
    L.append("- `auxiliary_equipment_id_hit` 추가: metadata.equipment_id 공백을 보조 필드로 보완 표시(정식 metadata_hit 과 분리).")
    L.append("- `direct_evidence_found` 추가: query 추출 식별자(alarm_code/equipment_id/process)의 문서 직접 존재 여부.")
    L.append("- quality gate 추가(리포트용, exit code 는 실패로 만들지 않음).")
    L.append("- out_of_scope 분리 / evidence doc·signal 분리 / metadata_gap 유지.\n")

    L.append("## 2. evidence_type_doc_hit 해석")
    L.append("- doc 기준(`evidence_type_doc_hit`): `metadata.doc_name` 이 전용 문서와 일치.")
    L.append("- signal 기준(`evidence_type_signal_hit`): title/section_title/keywords/snippet signal 부합.")
    L.append("- `answer_caution_policy` 는 전용 doc_name 이 없으므로 **doc_hit=N/A**, signal 로만 판정.")
    L.append(f"- evidence_type_doc_evaluable_count={summary['evidence_type_doc_evaluable_count']} "
             f"(answer_caution_policy/none/out_of_scope 제외).\n")
    L.append("| evidence_type | preferred doc_name | doc_hit 평가 | signal 키워드(일부) |")
    L.append("|---|---|---|---|")
    for et, mp in EVIDENCE_TYPE_MAP.items():
        docs = ", ".join(sorted(mp["preferred_docs"])) or "-"
        applicable = "평가" if mp["preferred_docs"] else "N/A"
        L.append(f"| {et} | {docs} | {applicable} | {', '.join(mp['signals'][:5]) or '-'} |")
    L.append("")

    L.append("## 3. 주요 지표 요약")
    L.append("| 지표 | 값 |")
    L.append("|---|---|")
    for key in ("total_cases", "pass_count", "warning_count", "fail_count", "info_count", "error_count",
                "positive_case_count", "positive_rank_evaluable_count",
                "keyword_any_hit_rate", "keyword_all_hit_rate",
                "metadata_hit_rate", "metadata_partial_hit_rate", "metadata_gap_case_count",
                "auxiliary_equipment_id_hit_count", "auxiliary_equipment_id_hit_rate",
                "evidence_type_doc_evaluable_count", "evidence_type_doc_hit_rate",
                "evidence_type_signal_hit_rate", "evidence_type_hit_rate",
                "hit_at_1_positive", "hit_at_3_positive", "hit_at_5_positive", "hit_at_10_positive",
                "mean_mrr_positive",
                "out_of_scope_case_count", "out_of_scope_warning_count", "out_of_scope_fail_count",
                "out_of_scope_false_positive_count",
                "direct_evidence_found_count", "direct_evidence_missing_count",
                "chroma_count", "fallback_count", "avg_returned_doc_count", "forbidden_field_case_count"):
        L.append(f"| {key} | {summary.get(key)} |")
    L.append("")

    L.append("## 4. quality gate 결과 (리포트용)")
    L.append(f"- 전체 통과: **{summary['quality_gate']['passed']}** (gate 실패해도 exit code 는 0)")
    L.append("| gate | threshold | actual | passed |")
    L.append("|---|---|---|---|")
    for name, chk in summary["quality_gate"]["checks"].items():
        L.append(f"| {name} | {chk['threshold']} | {chk['actual']} | {chk['passed']} |")
    L.append("")

    L.append("## 5. 케이스별 결과")
    L.append("| case_id | type | status | oos | docs | kw_all | md_hit | md_part | aux_eq | ev_doc | ev_sig | direct | hit@1 | mrr |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        L.append("| {cid} | {ct} | {st} | {oos} | {dc} | {kl} | {md} | {mp} | {ax} | {ed} | {es} | {de} | {h1} | {mrr} |".format(
            cid=_md(r.get("case_id")), ct=_md(r.get("case_design_type")), st=r.get("status"),
            oos=r.get("out_of_scope_case"), dc=r.get("returned_doc_count"),
            kl=r.get("keyword_all_hit"), md=r.get("metadata_hit"), mp=r.get("metadata_partial_hit"),
            ax=r.get("auxiliary_equipment_id_hit"), ed=r.get("evidence_type_doc_hit"),
            es=r.get("evidence_type_signal_hit"), de=r.get("direct_evidence_found"),
            h1=r.get("hit_at_1"), mrr=r.get("mrr"),
        ))
    L.append("")

    L.append("## 6. metadata gap / auxiliary 분석")
    for r in results:
        if r.get("metadata_gap") is True or r.get("auxiliary_equipment_id_hit") is True:
            L.append(f"- **{r['case_id']}**: matched={_md(r.get('matched_metadata'))} "
                     f"missing={_md(r.get('missing_metadata_keys'))} "
                     f"aux_eq_hit={r.get('auxiliary_equipment_id_hit')}(rank={r.get('auxiliary_equipment_id_rank')})")
    L.append("")

    L.append("## 7. direct evidence 분석 (out_of_scope 포함)")
    for r in results:
        if r.get("out_of_scope_case") or r.get("direct_evidence_found") is False:
            L.append(f"- **{r['case_id']}** [{r['status']}] direct_found={r.get('direct_evidence_found')} "
                     f"matched={_md(r.get('direct_evidence_matched_fields'))} "
                     f"missing={_md(r.get('direct_evidence_missing_identifiers'))}")
    L.append("- 해석: out_of_scope 에서 direct_evidence_found=false 는 '유사 문서만 검색됨'을 시사. "
             "강한 거절/확정 근거 억제는 Guardrail 단계로 이관(이번 단계 미구현).\n")

    L.append("## 8. positive 검색 지표 (out_of_scope 제외)")
    L.append(f"- positive_rank_evaluable_count={summary['positive_rank_evaluable_count']}")
    L.append(f"- hit@1={summary['hit_at_1_positive']}, hit@3={summary['hit_at_3_positive']}, "
             f"hit@5={summary['hit_at_5_positive']}, hit@10={summary['hit_at_10_positive']}, "
             f"mean_mrr={summary['mean_mrr_positive']}\n")

    L.append("## 9. 파일 위치 변경")
    L.append("- 평가 스크립트는 `scripts/day5/evaluate_mcp_server02_rag.py` 에서 "
             "`tests/day5/evaluate_mcp_server02_rag.py` 로 이동했다. 실행 경로/루트 탐색은 동일하게 동작한다.\n")

    L.append("## 10. 개선 제안")
    L.append("- 검색 코드 수정 없이도, doc_hit N/A·auxiliary·direct_evidence 도입으로 지표 '해석'이 정확해졌다.")
    L.append("- 추후 rerank 보강 시 오버피팅 금지: expected_* 라벨/case_id 전용 분기 금지, 일반 정규식·키워드만.")
    L.append("- Guardrail 단계로 이관: out_of_scope 확정 근거 억제/거절, 범위밖 공정 판정, 부분 근거 종합 판단.")
    L.append("- TODO: CI/회귀 단계에서 `--fail-on-gate` 옵션으로 quality gate 실패 시 exit code 1 처리.\n")
    return "\n".join(L)


def run(limit=None, case_id=None) -> dict:
    """평가를 실행하고 결과/요약/보고서를 파일로 저장한다(반환: summary).

    [흐름] 케이스 로드 → (옵션) case_id/limit 로 추림 → 케이스마다 evaluate_case() → 집계/보고서 → 저장.
    [입력] case_id: 한 케이스만 실행(디버깅용). limit: 앞에서 N건만 실행(빠른 점검용).
    """
    cases = load_cases()
    # --case-id: 특정 케이스 한 건만 골라 실행(문제 케이스 재현/디버깅 시 유용).
    if case_id:
        cases = [c for c in cases if c.get("case_id") == case_id]
    # --limit: 앞에서 N건만 실행(전체는 검색 호출이 많아 시간이 걸리므로 빠른 확인용).
    if limit is not None:
        cases = cases[:limit]

    # 케이스를 하나씩 '순차' 평가한다(병렬 아님). 각 결과는 그 자리에서 진행 상황으로 한 줄 출력한다.
    results = []
    for case in cases:
        record = evaluate_case(case)
        results.append(record)
        print(f"[{record.get('case_id')}] {record.get('status')} "
              f"(oos={record.get('out_of_scope_case')}, src={record.get('retrieval_source')}, "
              f"docs={record.get('returned_doc_count')}, ev_doc={record.get('evidence_type_doc_hit')}, "
              f"aux_eq={record.get('auxiliary_equipment_id_hit')}, direct={record.get('direct_evidence_found')})")

    # 모든 케이스 결과를 모아 집계 지표(summary)와 사람이 읽을 보고서(report.md 본문)를 만든다.
    summary = build_summary(results)
    report = build_report(results, summary)

    # 출력 폴더를 만들고(이미 있으면 통과) 결과 3종을 저장한다. BOM 포함 utf-8-sig 로 통일(이 저장소 규칙).
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    (OUTPUT_DIR / "report.md").write_text(report, encoding="utf-8-sig")

    gate = summary["quality_gate"]
    print("\n=== SUMMARY ===")
    print(f"total={summary['total_cases']} PASS={summary['pass_count']} WARNING={summary['warning_count']} "
          f"FAIL={summary['fail_count']} ERROR={summary['error_count']}")
    print(f"positive: hit@3={summary['hit_at_3_positive']} hit@10={summary['hit_at_10_positive']} "
          f"mean_mrr={summary['mean_mrr_positive']} (rank_evaluable={summary['positive_rank_evaluable_count']})")
    print(f"evidence: doc_hit={summary['evidence_type_doc_hit_rate']} "
          f"(evaluable={summary['evidence_type_doc_evaluable_count']}) signal={summary['evidence_type_signal_hit_rate']} hit={summary['evidence_type_hit_rate']}")
    print(f"metadata: hit={summary['metadata_hit_rate']} gap_cases={summary['metadata_gap_case_count']} "
          f"aux_eq_hit={summary['auxiliary_equipment_id_hit_count']}")
    print(f"direct_evidence: found={summary['direct_evidence_found_count']} missing={summary['direct_evidence_missing_count']}")
    print(f"out_of_scope: cases={summary['out_of_scope_case_count']} warning={summary['out_of_scope_warning_count']} "
          f"fail={summary['out_of_scope_fail_count']} false_positive={summary['out_of_scope_false_positive_count']}")
    print(f"chroma={summary['chroma_count']} fallback={summary['fallback_count']} forbidden_cases={summary['forbidden_field_case_count']}")
    print(f"quality_gate.passed={gate['passed']} (gate 실패해도 exit code=0; CI 용 --fail-on-gate 는 TODO)")
    print(f"outputs -> {OUTPUT_DIR}")
    return summary


def main():
    # CLI 진입점: 인자를 파싱해 run() 에 넘긴다. `python tests/day5/evaluate_mcp_server02_rag.py` 로 실행.
    parser = argparse.ArgumentParser(description="mcp_server02 search_manual RAG 검색 성능 평가(보완판 v2)")
    parser.add_argument("--limit", type=int, default=None, help="평가할 케이스 수 제한")
    parser.add_argument("--case-id", type=str, default=None, help="특정 case_id 만 평가")
    # TODO(CI/회귀): --fail-on-gate 옵션으로 quality_gate 실패 시 exit code 1 처리(이번 단계 미구현).
    args = parser.parse_args()
    run(limit=args.limit, case_id=args.case_id)


if __name__ == "__main__":
    main()
