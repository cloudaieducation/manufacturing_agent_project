# -*- coding: utf-8 -*-
"""
Day5 mcp_client_final - Agent 판단 흐름 (agent_flow)

[이 파일의 역할 — mcp_client_final 의 심장]
'규칙 기반'으로 Agent 의 판단 흐름을 한눈에 읽을 수 있게 구현합니다. LLM 필수 의존 없이,
아래 9단계를 순서대로 수행해 하나의 결과 dict 를 만듭니다.

    1) 질문 분석        analyze_question
    2) 의도 분류        classify_intent          (DB_ONLY / RAG_ONLY / DB_AND_RAG / AMBIGUOUS)
    3) MCP Tool 선택    select_tools             (server03 기존 업무 Tool 만, execute_sql 미사용)
    4) MCP Tool 호출    _run_tools               (ToolCaller 경유 — 실패는 ERROR 로 정직 기록)
    5) DB 결과 요약     summarize_db
    6) RAG 결과 요약    summarize_rag
    7) 비교+Evidence    compare_and_check        (규칙 기반 근거 확인)
    8) 교육용 점검 등급 educational_check_level  ('위험도' 아님 — 교육용 점검 우선순위)
    9) 다음 확인 항목   build_next_checks        ('조치 명령' 아님 — 추가 확인 방향)
    → run_agent_flow 가 위를 엮어 단계별 dict 를 반환한다.

[경계 — 매우 중요]
- MCP 서버(mcp_server03)는 수정하지 않는다. 기존 업무 Tool 만 호출한다(execute_sql 미사용).
- 서버 내부 모듈(repositories/db_access/rag_*)을 직접 import 하지 않는다.
- mcp_client04 에서는 '실행 호출 방식'만 얇게 재사용한다(config + ToolCaller + extract_payload).
- 서버 미기동/Tool 실패는 성공처럼 포장하지 않고 status="ERROR" 로 tool_trace 에 정직하게 남긴다.
- DB/RAG 메타데이터(data_source/retrieval_source/fallback_used/mock_fallback)는 숨기지 않는다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# [import 경로 보강] 이 파일 <root>/src/day5/mcp_client_final/agent_flow.py → parents[3] = <root>.
# streamlit 직접 실행/별도 -c 실행 어디서든 'day5.*' 를 찾도록 <root>/src 를 sys.path 에 넣는다.
_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# [재사용 — '실행 호출 방식'만 얇게] mcp_client04 의 client 측 계층만 가져온다.
#   - config         : 타임아웃 등 설정 상수(MCP_HTTP_URL=8000 은 사용하지 않고 로컬 8003 상수 사용).
#   - HttpToolCaller : standalone HTTP(streamable-http) 서버 접속용 ToolCaller(이 client 는 http 전용).
#   - extract_payload: call_mcp_tool envelope 에서 단일 Tool result payload 를 꺼내는 헬퍼.
# 서버 내부 모듈은 직접 import 하지 않는다(MCP Tool 호출 경로 유지).
from day5.mcp_client04 import config
from day5.mcp_client04.mcp_tools import HttpToolCaller, extract_payload


# ===========================================================================
# server03 가 제공하는 '업무 Tool'(이 client 가 사용할 수 있는 후보). execute_sql 은 제외.
# ===========================================================================
DB_TOOLS = (
    "get_equipment_overview",
    "get_equipment_status",
    "get_recent_alarm_events",
    "get_process_status",
    "get_quality_metrics",
    "get_maintenance_history",
)
RAG_TOOL = config.MCP_SEARCH_TOOL  # "search_manual"

# 출력/요약에서 제외할 민감 key 마커(부분 일치, 소문자 비교). 서버가 이미 sanitize 하지만 2차 방어.
_SENSITIVE_MARKERS = (
    "password", "token", "secret", "connection", "dsn",
    "source_path", "file_path", "internal_url",
    "full_text", "chroma:document", "raw_metadata",
    "message", "operator_note", "technician_note", "lot_id", "owner_team", "location",
)

# 교육용 가상 식별자 패턴(설비/알람/라인). 일반화 가능한 규칙만 사용(정답 라벨/케이스 ID 미사용).
_EQUIP_PATTERN = re.compile(r"(?<![A-Za-z0-9])EQP-[A-Z]+-\d+(?![A-Za-z0-9])", re.IGNORECASE)
_ALARM_PATTERN = re.compile(r"(?<![A-Za-z0-9])ALM-(?:[A-Z]+-)?\d+(?![A-Za-z0-9-])", re.IGNORECASE)
_LINE_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:EDU-)?LINE-[A-Z0-9]+", re.IGNORECASE)

# metric_name 키워드 → 서버 allowlist 컬럼.
_METRIC_KEYWORDS = [
    (("수율", "yield"), "yield_rate"),
    (("불량률", "defect"), "defect_rate"),
    (("검사 결과", "검사", "inspection"), "inspection_result"),
    (("이상", "abnormal"), "abnormal_flag"),
]

# 의도 판단용 키워드(규칙 기반).
_RAG_KEYWORDS = ("매뉴얼", "조치", "절차", "근거", "문서", "방향", "원인", "트러블슈팅", "설명", "어떻게")
_DB_STATUS_KEYWORDS = ("상태", "개요", "현재", "가동")
_DB_ALARM_KEYWORDS = ("알람", "이력", "최근", "반복", "발생")
_DB_QUALITY_KEYWORDS = ("품질", "수율", "불량률", "검사", "지표")
_DB_MAINT_KEYWORDS = ("정비", "교체", "부품", "보전", "점검 이력")
_DB_PROCESS_KEYWORDS = ("공정", "라인")


def _is_sensitive_key(key) -> bool:
    """key 이름에 민감 마커가 포함되면 True(출력/요약 제외 대상)."""
    name = str(key).lower()
    return any(marker in name for marker in _SENSITIVE_MARKERS)


def _sanitize_payload(payload: dict) -> dict:
    """payload 에서 '민감 key 제외 + 리스트는 개수만' 으로 작은 요약 dict 를 만든다."""
    safe = {}
    if not isinstance(payload, dict):
        return safe
    for key, value in payload.items():
        if _is_sensitive_key(key):
            continue
        if isinstance(value, list):
            safe[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            continue
        else:
            safe[key] = value
    return safe


def _detect_metric(text: str):
    """질문에서 metric_name(allowlist 컬럼)을 추론한다(없으면 None)."""
    low = text.lower()
    for keywords, column in _METRIC_KEYWORDS:
        if any(kw.lower() in low for kw in keywords):
            return column
    return None


# ===========================================================================
# 1) 질문 분석
# ===========================================================================
def analyze_question(question: str) -> dict:
    """질문에서 식별자/키워드를 추출한다(규칙 기반, 1단계).

    [반환] {equipment_id, alarm_code, line_id, metric_name, keywords, raw}
    """
    text = str(question or "")
    eq = _EQUIP_PATTERN.search(text)
    al = _ALARM_PATTERN.search(text)
    ln = _LINE_PATTERN.search(text)

    # 어떤 의도 키워드가 등장했는지 그대로 모아 둔다(화면에서 '왜 그렇게 판단했는지' 설명용).
    found = []
    for label, words in (
        ("RAG/매뉴얼", _RAG_KEYWORDS), ("상태", _DB_STATUS_KEYWORDS), ("알람", _DB_ALARM_KEYWORDS),
        ("품질", _DB_QUALITY_KEYWORDS), ("정비", _DB_MAINT_KEYWORDS), ("공정", _DB_PROCESS_KEYWORDS),
    ):
        hits = [w for w in words if w in text]
        if hits:
            found.append({"category": label, "matched": hits})

    return {
        "equipment_id": eq.group(0) if eq else None,
        "alarm_code": al.group(0) if al else None,
        "line_id": ln.group(0) if ln else None,
        "metric_name": _detect_metric(text),
        "keywords": found,
        "raw": text,
    }


# ===========================================================================
# 2) 의도 분류
# ===========================================================================
def classify_intent(analysis: dict) -> dict:
    """질문 분석 결과로 의도를 분류한다(2단계, 규칙 기반).

    [반환] {intent, reason, extracted_entities, needs_db, needs_rag}
        intent ∈ DB_ONLY / RAG_ONLY / DB_AND_RAG / AMBIGUOUS
    """
    text = analysis.get("raw", "")
    eq, al, ln = analysis.get("equipment_id"), analysis.get("alarm_code"), analysis.get("line_id")

    # RAG 단서: 매뉴얼/조치/절차/근거 류 키워드.
    wants_rag = any(k in text for k in _RAG_KEYWORDS)
    # DB 단서: 설비/라인 식별자, 또는 상태/알람/품질/정비/공정 키워드.
    wants_db = bool(eq or ln) or any(
        k in text for k in (_DB_STATUS_KEYWORDS + _DB_ALARM_KEYWORDS
                            + _DB_QUALITY_KEYWORDS + _DB_MAINT_KEYWORDS + _DB_PROCESS_KEYWORDS)
    )

    if wants_db and wants_rag:
        intent, reason = "DB_AND_RAG", "설비 사실(DB)과 매뉴얼 근거(RAG)가 모두 필요한 질문입니다."
    elif wants_rag:
        intent, reason = "RAG_ONLY", "매뉴얼/조치/절차 등 문서 근거만 필요한 질문입니다."
    elif wants_db:
        intent, reason = "DB_ONLY", "설비 상태/알람/품질 등 DB 사실만 필요한 질문입니다."
    else:
        intent, reason = "AMBIGUOUS", "DB/RAG 단서가 뚜렷하지 않아 기본적으로 매뉴얼 검색만 시도합니다."

    return {
        "intent": intent,
        "reason": reason,
        "extracted_entities": {"equipment_id": eq, "alarm_code": al,
                               "line_id": ln, "metric_name": analysis.get("metric_name")},
        "needs_db": intent in ("DB_ONLY", "DB_AND_RAG"),
        "needs_rag": intent in ("RAG_ONLY", "DB_AND_RAG", "AMBIGUOUS"),
    }


# ===========================================================================
# 3) MCP Tool 선택 (server03 기존 업무 Tool 만)
# ===========================================================================
def select_tools(analysis: dict, intent: dict) -> list:
    """의도/식별자에 맞는 업무 Tool 과 호출 인자를 고른다(3단계). execute_sql 은 절대 고르지 않는다.

    [반환] list[ {tool_name, purpose, reason, call_order, input_hint} ]
    """
    eq = analysis.get("equipment_id")
    al = analysis.get("alarm_code")
    ln = analysis.get("line_id")
    metric = analysis.get("metric_name")
    text = analysis.get("raw", "")
    selected = []

    def add(tool_name, purpose, reason, input_hint):
        selected.append({
            "tool_name": tool_name, "purpose": purpose, "reason": reason,
            "call_order": len(selected) + 1, "input_hint": input_hint,
        })

    if intent.get("needs_db"):
        # 알람 의도 + 설비 → 최근 알람 이력.
        if any(k in text for k in _DB_ALARM_KEYWORDS) and eq:
            args = {"equipment_id": eq}
            if al:
                args["alarm_code"] = al
            add("get_recent_alarm_events", "최근 알람 이력 확인",
                "알람/반복/이력 키워드와 설비 ID가 있어 알람 이력을 확인합니다.", args)
        # 품질 의도 → 품질 지표(식별자/지표명 중 하나 이상 필요).
        if any(k in text for k in _DB_QUALITY_KEYWORDS) and (metric or eq or ln):
            args = {}
            if metric:
                args["metric_name"] = metric
            if eq:
                args["equipment_id"] = eq
            if ln:
                args["line_id"] = ln
            add("get_quality_metrics", "품질 지표 확인",
                "품질/수율/불량률 키워드가 있어 품질 지표를 확인합니다.", args)
        # 정비 의도 + 설비 → 정비 이력.
        if any(k in text for k in _DB_MAINT_KEYWORDS) and eq:
            add("get_maintenance_history", "정비 이력 확인",
                "정비/교체/점검 키워드와 설비 ID가 있어 정비 이력을 확인합니다.", {"equipment_id": eq})
        # 기본 설비 사실: 개요(설비/라인 식별자가 있으면).
        if eq or ln:
            args = {"equipment_id": eq} if eq else {"line_id": ln}
            add("get_equipment_overview", "설비 개요 확인",
                "설비/라인 식별자가 있어 기본 개요(사실 데이터)를 확인합니다.", args)
        # DB 의도인데 아무 DB Tool 도 못 고른 경우(식별자 부족) — 개요라도 시도(빈 인자 → 서버가 검증).
        if not any(s["tool_name"] in DB_TOOLS for s in selected):
            add("get_equipment_overview", "설비 개요 확인(식별자 부족)",
                "DB 의도지만 식별자가 부족해 개요 조회만 시도합니다(결과 부족 시 추가 확인 필요).", {})

    if intent.get("needs_rag"):
        args = {"query": text or "조치 절차"}
        if al:
            args["alarm_code"] = al
        add(RAG_TOOL, "매뉴얼/조치 근거 검색",
            "조치/절차/근거 키워드가 있어 매뉴얼(RAG)에서 근거를 검색합니다.", args)

    return selected


# ===========================================================================
# 4) MCP Tool 호출 (실패는 ERROR 로 정직 기록)
# ===========================================================================
# [standalone HTTP 전용] 교육용 최종 실습 MCP endpoint 를 8003 으로 통일한다.
#   mcp_client04.config.MCP_HTTP_URL 은 8000 을 가리키므로 사용하지 않고, 이 로컬 상수만 사용한다
#   (mcp_client04 는 참조 대상이라 수정하지 않는다).
DEFAULT_MCP_HTTP_URL = "http://127.0.0.1:8003/mcp"


def _build_caller(transport: str = "http", http_url=None, timeout: int = config.DEFAULT_TIMEOUT):
    """standalone HTTP 서버에 연결하는 ToolCaller 를 만든다(http 전용).

    - http  : 외부에서 미리 띄운 streamable-http 서버(http://127.0.0.1:8003/mcp)에 접속(서버 선기동 필요).
    [정책] mcp_client_final 은 stdio/subprocess 로 서버를 실행하지 않는다. transport 가 http 가 아니면
           조용히 http 로 바꾸지 않고, standalone HTTP 만 지원한다는 명확한 오류를 발생시킨다.
    """
    if transport != "http":
        raise ValueError(
            "mcp_client_final은 standalone HTTP 서버 연결만 지원합니다. "
            "mcp_server_final을 8003 포트로 먼저 실행해 주세요."
        )
    return HttpToolCaller(url=http_url or DEFAULT_MCP_HTTP_URL,
                          timeout=max(timeout, config.RAG_TIMEOUT))


def _call_one(caller, tool_name: str, arguments: dict) -> dict:
    """단일 Tool 을 호출하고 'tool_trace 1건'을 만든다. 실패는 ERROR 로 정직하게 남긴다.

    [반환 trace] {tool_name, status, data_source, retrieval_source, fallback_used,
                  mock_fallback, error, payload}
        status ∈ "OK" | "ERROR"  (EMPTY/SKIPPED 는 5/6단계 요약에서 판정)
    """
    entry = {"tool_name": tool_name, "status": None, "data_source": None,
             "retrieval_source": None, "fallback_used": None, "mock_fallback": None,
             "error": None, "payload": {}}
    try:
        envelope = caller.call_tool(tool_name, dict(arguments or {}))
    except Exception as error:  # noqa: BLE001 - 서버 미기동/연결 실패 등 → 성공으로 포장하지 않고 ERROR
        entry["status"] = "ERROR"
        entry["error"] = f"call_failed:{type(error).__name__}"
        return entry

    if not isinstance(envelope, dict):
        entry["status"] = "ERROR"
        entry["error"] = "invalid_envelope"
        return entry

    # transport 가 만든 안전 표시(timeout/연결 오류) 또는 서버 status 를 ERROR 로 정직 변환.
    server_status = envelope.get("status")
    if envelope.get("_client_error"):
        entry["status"] = "ERROR"
        entry["error"] = f"client_error:{envelope.get('_client_error')}"
        return entry
    if server_status in ("timeout", "error"):
        entry["status"] = "ERROR"
        entry["error"] = str(server_status)
        return entry
    if server_status == "rejected":
        entry["status"] = "ERROR"
        entry["error"] = "rejected(금지 Tool)"
        return entry

    # 정상 envelope → 단일 Tool payload 추출(mcp_client04.extract_payload 재사용).
    payload = extract_payload(envelope) or {}
    ds = payload.get("data_source")
    rs = payload.get("retrieval_source")
    entry["status"] = "OK"
    entry["data_source"] = ds
    entry["retrieval_source"] = rs
    entry["fallback_used"] = payload.get("fallback_used")
    entry["mock_fallback"] = (ds == "mock_fallback") or (rs == "mock_fallback")
    entry["payload"] = _sanitize_payload(payload)
    # 내부 판정용 원본 일부(문서/이벤트 개수 등)는 payload(요약)에 _count 로 보존됨.
    # [근거 비교용] search_manual documents 의 '비민감' title/snippet 만 미리보기로 보존한다.
    #   (full_text/chroma:document/source_path 등 민감 필드는 _SENSITIVE 정책상 애초에 제외된다.)
    #   이 미리보기가 있어야 7단계에서 '질문 알람코드가 매뉴얼 근거에 등장하는가'를 비교할 수 있다.
    docs = payload.get("documents")
    if isinstance(docs, list) and docs:
        preview = []
        for doc in docs[:5]:
            if isinstance(doc, dict):
                title = str(doc.get("title") or "")
                snippet = str(doc.get("snippet") or "")
                text = (title + " " + snippet).strip()
                if text:
                    preview.append(text)
        if preview:
            entry["payload"]["documents_preview"] = preview
    return entry


def _run_tools(selected: list, caller) -> list:
    """선택된 Tool 들을 호출 순서대로 호출해 tool_trace 리스트를 만든다(4단계)."""
    # call_order 기준 정렬 후 순차 호출(교육용으로 '호출 순서'가 보이도록).
    trace = []
    for spec in sorted(selected, key=lambda s: s.get("call_order", 0)):
        trace.append(_call_one(caller, spec["tool_name"], _args_from_hint(spec)))
    return trace


def _args_from_hint(spec: dict) -> dict:
    """select_tools 가 넣은 input_hint(=실제 호출 인자)를 그대로 사용한다."""
    hint = spec.get("input_hint")
    return dict(hint) if isinstance(hint, dict) else {}


# ===========================================================================
# 5) DB 결과 요약 / 6) RAG 결과 요약
# ===========================================================================
def summarize_db(trace: list, selected: list) -> dict:
    """DB Tool 결과를 정직하게 요약한다(5단계). 상태: OK/EMPTY/SKIPPED/ERROR."""
    db_entries = [t for t in trace if t.get("tool_name") in DB_TOOLS]
    db_selected = [s for s in selected if s.get("tool_name") in DB_TOOLS]

    if not db_selected:
        return {"status": "SKIPPED", "reason": "DB 의도가 아니어서 DB Tool 을 호출하지 않았습니다.",
                "data_source": None, "has_mock_fallback": False, "tools": []}

    ok = [t for t in db_entries if t.get("status") == "OK"]
    err = [t for t in db_entries if t.get("status") == "ERROR"]
    has_mock = any(t.get("mock_fallback") for t in db_entries)
    data_sources = sorted({t.get("data_source") for t in ok if t.get("data_source")})

    if ok:
        # 적어도 하나가 OK. (개별 Tool 의 '0건'은 payload 의 *_count 로 화면에서 확인)
        status = "OK"
        reason = "DB Tool 이 정상 응답했습니다." + (
            " 일부는 mock_fallback(실제 DB 미연결 가능)입니다." if has_mock else "")
    elif err:
        status = "ERROR"
        reason = "DB Tool 호출이 모두 실패했습니다(서버 미기동/연결 실패 가능)."
    else:
        status = "EMPTY"
        reason = "DB Tool 을 호출했으나 표시할 결과가 없습니다."

    return {
        "status": status, "reason": reason,
        "data_source": data_sources, "has_mock_fallback": bool(has_mock),
        "tools": [{"tool_name": t["tool_name"], "status": t["status"],
                   "data_source": t.get("data_source"), "mock_fallback": t.get("mock_fallback"),
                   "error": t.get("error"), "payload": t.get("payload")} for t in db_entries],
    }


def summarize_rag(trace: list, selected: list) -> dict:
    """search_manual 결과를 정직하게 요약한다(6단계). 상태: OK/EMPTY/SKIPPED/ERROR."""
    rag_selected = any(s.get("tool_name") == RAG_TOOL for s in selected)
    rag_entry = next((t for t in trace if t.get("tool_name") == RAG_TOOL), None)

    if not rag_selected:
        return {"status": "SKIPPED", "reason": "RAG 의도가 아니어서 search_manual 을 호출하지 않았습니다.",
                "retrieval_source": None, "fallback_used": None, "has_mock_fallback": False,
                "documents_count": 0}

    if rag_entry is None or rag_entry.get("status") == "ERROR":
        err = (rag_entry or {}).get("error", "unknown")
        return {"status": "ERROR",
                "reason": f"search_manual 호출이 실패/timeout 했습니다({err}). "
                          "stdio 환경은 RAG timeout 가능 — HTTP 서버 사용을 권장합니다.",
                "retrieval_source": (rag_entry or {}).get("retrieval_source"),
                "fallback_used": (rag_entry or {}).get("fallback_used"),
                "has_mock_fallback": bool((rag_entry or {}).get("mock_fallback")),
                "documents_count": 0}

    docs = int(rag_entry.get("payload", {}).get("documents_count") or 0)
    status = "OK" if docs > 0 else "EMPTY"
    reason = (f"매뉴얼 문서 {docs}건을 검색했습니다." if docs > 0
              else "search_manual 을 호출했으나 관련 문서가 0건입니다.")
    return {
        "status": status, "reason": reason,
        "retrieval_source": rag_entry.get("retrieval_source"),
        "fallback_used": rag_entry.get("fallback_used"),
        "has_mock_fallback": bool(rag_entry.get("mock_fallback")),
        "documents_count": docs,
    }


# ===========================================================================
# 7) DB↔RAG 비교 + Evidence Check (규칙 기반)
# ===========================================================================
def compare_and_check(analysis: dict, trace: list, db_summary: dict, rag_summary: dict) -> dict:
    """DB 사실과 RAG 근거를 규칙 기반으로 비교/검증한다(7단계).

    [반환] {evidence_level, evidence_reason, db_supported, rag_supported,
            has_mock_fallback, mismatch_notes}
        evidence_level ∈ DIRECT / PARTIAL / INSUFFICIENT / ERROR
    """
    eq = (analysis.get("equipment_id") or "").lower()
    al = (analysis.get("alarm_code") or "").lower()

    # DB 근거: DB 가 OK 이고(mock_fallback 이 아니면 더 강함), 질문 설비 ID 가 DB payload 에 등장.
    db_ok = db_summary.get("status") == "OK"
    db_text = json.dumps([t.get("payload") for t in trace if t.get("tool_name") in DB_TOOLS],
                         ensure_ascii=False).lower()
    db_has_id = (eq in db_text) if eq else db_ok
    db_supported = bool(db_ok and db_has_id)

    # RAG 근거: RAG 가 OK 이고 문서 > 0, 알람코드가 있으면 문서 요약에 등장하는지까지 확인.
    rag_ok = rag_summary.get("status") == "OK"
    rag_text = json.dumps([t.get("payload") for t in trace if t.get("tool_name") == RAG_TOOL],
                          ensure_ascii=False).lower()
    rag_has_alarm = (al in rag_text) if al else rag_ok
    rag_supported = bool(rag_ok and rag_has_alarm)

    has_mock = bool(db_summary.get("has_mock_fallback") or rag_summary.get("has_mock_fallback"))

    # 불일치/주의 메모(규칙 기반): 성공처럼 위장하지 않도록 정직하게 적는다.
    notes = []
    if db_summary.get("status") == "ERROR" or rag_summary.get("status") == "ERROR":
        notes.append("일부 Tool 호출이 ERROR 입니다 — 근거를 확정할 수 없습니다.")
    if db_summary.get("has_mock_fallback"):
        notes.append("DB 결과가 mock_fallback 입니다 — 실제 DB 사실로 확정할 수 없습니다(서버 미기동 가능).")
    if rag_summary.get("status") in ("EMPTY", "ERROR"):
        notes.append("매뉴얼 근거가 0건/실패입니다 — 문서 근거가 있는 것처럼 말하지 않습니다.")
    if eq and db_ok and eq not in db_text:
        notes.append("질문의 설비 ID 가 DB 결과에 직접 나타나지 않았습니다 — 직접 근거 부족.")
    if al and rag_ok and al not in rag_text:
        notes.append("질문의 알람 코드가 매뉴얼 검색 결과에 직접 나타나지 않았습니다 — 직접 근거 부족.")

    # evidence_level 판정.
    if db_summary.get("status") == "ERROR" and rag_summary.get("status") == "ERROR":
        level, reason = "ERROR", "DB/RAG 호출이 모두 실패해 근거를 확인할 수 없습니다."
    elif db_supported and rag_supported:
        level, reason = "DIRECT", "DB 사실과 매뉴얼 근거가 모두 질문 식별자를 직접 뒷받침합니다."
    elif db_supported or rag_supported:
        level, reason = "PARTIAL", "DB 또는 RAG 중 한쪽만 근거가 있어 근거가 부분적입니다."
    else:
        level, reason = "INSUFFICIENT", "직접 근거가 부족합니다(결과 없음/식별자 불일치/mock_fallback)."

    return {
        "evidence_level": level,
        "evidence_reason": reason,
        "db_supported": db_supported,
        "rag_supported": rag_supported,
        "has_mock_fallback": has_mock,
        "mismatch_notes": notes,
    }


# ===========================================================================
# 8) 교육용 점검 등급 ('위험도' 아님)
# ===========================================================================
def educational_check_level(analysis: dict, trace: list, db_summary: dict,
                            rag_summary: dict, evidence: dict) -> dict:
    """교육용 '점검 우선순위'를 규칙 기반으로 산정한다(8단계). 실제 운영 판단이 아니다.

    [반환] {check_level, reason, supporting_tools, uncertainty}
        check_level ∈ "높음" | "보통" | "낮음" | "판단 보류"
    """
    # 알람 이벤트 개수(있으면).
    alarm_entry = next((t for t in trace if t.get("tool_name") == "get_recent_alarm_events"
                        and t.get("status") == "OK"), None)
    alarm_count = int((alarm_entry or {}).get("payload", {}).get("recent_events_count") or 0) if alarm_entry else 0
    has_quality_kw = any(k in analysis.get("raw", "") for k in _DB_QUALITY_KEYWORDS)
    quality_ok = any(t.get("tool_name") == "get_quality_metrics" and t.get("status") == "OK" for t in trace)

    supporting = [t["tool_name"] for t in trace if t.get("status") == "OK"]
    uncertainty = []
    if evidence.get("has_mock_fallback"):
        uncertainty.append("일부 결과가 mock_fallback(실제 DB 미연결 가능).")
    if db_summary.get("status") == "ERROR" or rag_summary.get("status") == "ERROR":
        uncertainty.append("일부 Tool 호출이 ERROR.")
    if evidence.get("evidence_level") in ("INSUFFICIENT",):
        uncertainty.append("직접 근거 부족.")

    # 판단 보류: 받쳐 주는 OK Tool 이 하나도 없거나 evidence 가 ERROR.
    if not supporting or evidence.get("evidence_level") == "ERROR":
        level = "판단 보류"
        reason = "Tool 결과가 부족하거나 호출이 실패해 점검 등급을 산정하지 않습니다(추가 확인 필요)."
    elif alarm_count > 0 and (has_quality_kw or quality_ok):
        level = "높음"
        reason = f"최근 알람 {alarm_count}건이 있고 품질 관련 확인이 함께 필요합니다(교육용 기준)."
    elif alarm_count > 0:
        level = "보통"
        reason = "최근 알람은 있으나 품질 근거가 충분하지 않습니다(교육용 기준)."
    else:
        level = "낮음"
        reason = "상태 조회 위주이고 뚜렷한 이상 근거가 확인되지 않았습니다(교육용 기준)."

    return {
        "check_level": level,
        "reason": reason + " ※ 교육용 예제 기준이며 실제 운영 판단이 아닙니다.",
        "supporting_tools": supporting,
        "uncertainty": uncertainty,
    }


# ===========================================================================
# 9) 다음 확인 항목 제안 ('조치 명령' 아님)
# ===========================================================================
def build_next_checks(analysis: dict, intent: dict, db_summary: dict,
                      rag_summary: dict, evidence: dict) -> dict:
    """다음 '확인 항목'과 후속 질문 후보를 제안한다(9단계). 운영 지시가 아니라 추가 확인 방향."""
    eq = analysis.get("equipment_id")
    al = analysis.get("alarm_code")
    next_checks = []
    follow_ups = []

    # 서버/Tool 실패가 있으면 가장 먼저 서버 상태 확인을 안내.
    if db_summary.get("status") == "ERROR" or rag_summary.get("status") == "ERROR":
        next_checks.append("mcp_server03 HTTP 서버 실행 상태 확인(서버 미기동/연결 실패 가능)")
    if evidence.get("has_mock_fallback"):
        next_checks.append("DB 가 mock_fallback 이므로 실제 PostgreSQL 연결 후 재확인")

    if eq:
        next_checks.append(f"{eq} 최근 알람 이력 추가 확인")
        next_checks.append(f"{eq} 정비 이력 확인")
        follow_ups.append(f"{eq}의 최근 정비 이력도 확인할까요?")
    if any(k in analysis.get("raw", "") for k in _DB_QUALITY_KEYWORDS) or eq:
        next_checks.append("해당 설비/라인의 품질 지표 변화 확인")
        follow_ups.append("품질 지표 추세도 함께 볼까요?")
    if al:
        next_checks.append(f"{al} 매뉴얼 절차 근거 확인")
        follow_ups.append(f"{al} 조치 절차 문서를 더 볼까요?")

    next_checks.append("담당자가 실제 현장 상태를 직접 확인(교육용 예제는 판단을 대신하지 않음)")
    if not follow_ups:
        follow_ups.append("다른 설비/알람도 확인할까요?")

    # 중복 제거(순서 유지).
    seen = set()
    next_checks = [c for c in next_checks if not (c in seen or seen.add(c))]
    return {"next_checks": next_checks, "follow_up_questions": follow_ups}


# ===========================================================================
# 10) 전체 흐름 — run_agent_flow
# ===========================================================================
def run_agent_flow(question: str, transport: str = "http", http_url=None,
                   timeout: int = config.DEFAULT_TIMEOUT, tool_caller=None) -> dict:
    """질문 1건을 9단계 판단 흐름으로 처리해 단계별 결과 dict 를 돌려준다.

    [강건성]
        - 규칙 기반 단계(1~3, 5~9)는 서버 없이도 항상 동작한다.
        - Tool 호출(4단계)만 서버가 필요하며, 서버 미기동/실패는 tool_trace 에 status="ERROR" 로
          정직하게 기록하고 전체 흐름은 죽지 않는다(예외를 흡수).
    [입력]
        transport : "http"(기본, standalone HTTP 서버 접속만 지원). http 가 아니면 _build_caller 가 오류.
        http_url  : 접속 URL(미지정 시 DEFAULT_MCP_HTTP_URL = http://127.0.0.1:8003/mcp).
        tool_caller: 테스트/오프라인용 주입 hook(있으면 그대로 사용, 없으면 transport 로 생성).
    [반환] 보고서 형식 dict(아래 키 참조).
    """
    analysis = analyze_question(question)
    intent = classify_intent(analysis)
    selected = select_tools(analysis, intent)

    # 4단계: Tool 호출. caller 생성/호출 단계의 어떤 예외도 흐름을 죽이지 않는다.
    tool_trace = []
    if selected:
        try:
            caller = tool_caller if tool_caller is not None else _build_caller(transport, http_url, timeout)
            tool_trace = _run_tools(selected, caller)
        except Exception as error:  # noqa: BLE001 - caller 생성 실패 등 → 선택한 Tool 전부 ERROR 로 기록
            tool_trace = [{"tool_name": s["tool_name"], "status": "ERROR",
                           "data_source": None, "retrieval_source": None,
                           "fallback_used": None, "mock_fallback": None,
                           "error": f"caller_failed:{type(error).__name__}", "payload": {}}
                          for s in sorted(selected, key=lambda s: s.get("call_order", 0))]

    db_summary = summarize_db(tool_trace, selected)
    rag_summary = summarize_rag(tool_trace, selected)
    evidence = compare_and_check(analysis, tool_trace, db_summary, rag_summary)
    check = educational_check_level(analysis, tool_trace, db_summary, rag_summary, evidence)
    nexts = build_next_checks(analysis, intent, db_summary, rag_summary, evidence)

    final_message = _build_final_message(intent, evidence, check)

    return {
        "question": str(question or ""),
        "analysis": analysis,
        "intent": intent,
        "selected_tools": selected,
        "tool_trace": tool_trace,
        "db_summary": db_summary,
        "rag_summary": rag_summary,
        "comparison": evidence,          # 비교 결과(= evidence_check 와 동일 객체)
        "evidence_check": evidence,
        "educational_check_level": check,
        "next_checks": nexts["next_checks"],
        "follow_up_questions": nexts["follow_up_questions"],
        "final_message": final_message,
    }


def _build_final_message(intent: dict, evidence: dict, check: dict) -> str:
    """단계 결과를 한 줄로 정직하게 요약한다(원인 단정/운영 지시 금지)."""
    return (
        f"의도={intent.get('intent')} · 근거수준={evidence.get('evidence_level')} · "
        f"교육용 점검 등급={check.get('check_level')}. "
        "결과는 확정이 아니라 '확인·검토용'이며, 장비 제어 지시는 제공하지 않습니다(교육용)."
    )


if __name__ == "__main__":
    # 단독 실행: 규칙 기반 단계가 서버 없이도 동작하는지 빠르게 확인(Tool 호출은 환경에 따라 ERROR 가능).
    demo = run_agent_flow("EQP-EV-03 지금 상태 알려줘")
    print("keys:", list(demo.keys()))
    print("intent:", demo["intent"])
