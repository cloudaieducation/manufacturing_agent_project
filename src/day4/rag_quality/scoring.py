# -*- coding: utf-8 -*-
"""
Day4 RAG 검색 품질 평가기 - 채점/판정 계층 모듈 (scoring)

이 파일은 "검색된 근거(chunk)가 질문에 맞는지 채점하고 PASS/WARN/FAIL을 판정하는" 단계만 모아 둡니다.
- 키워드 채점(score_keywords)
- 메타데이터 채점(score_metadata)
- 종합 판정(judge_evidence_quality) : PASS / WARN / FAIL
- 실패/주의 원인 메모 생성(build_missing_reason)

교육용 리팩토링 4단계에서 runner.py로부터 분리했습니다.
- 함수 내부 로직은 분리 전과 한 글자도 다르지 않습니다(안전한 위치 이동).
- 검색(retrieval) / 재정렬(rerank) / 보고서(report) 로직은 이 파일에 들어오지 않습니다.

import 계층 규칙(중요):
- scoring.py는 config.py만 import 합니다(runner.py / retrieval.py를 import 하지 않습니다).
  → config 아래 계층을 바라보는 단방향 구조라 순환 import가 생기지 않습니다.
"""

from __future__ import annotations

# 채점/판정에 필요한 공용 유틸과 상수는 config.py에서 명시적으로 가져옵니다(별표 import 금지).
from src.day4.rag_quality.config import (
    normalize_value,
    NONE_EVIDENCE_TYPES,
    is_out_of_scope_case,
)

# ──────────────────────────────────────────────────────────────────────
# 9. 키워드 점수 함수
# ──────────────────────────────────────────────────────────────────────
def score_keywords(expected_keywords: list[str], retrieved_chunks: list[dict]) -> dict:
    """
    기대 키워드(expected_keywords)가 검색된 문서들에 얼마나 들어 있는지 셉니다.

    방식:
        - 모든 chunk의 text를 하나로 합치고 소문자로 만든 뒤, 키워드 포함 여부만 봅니다.
        - 한글/영문이 섞여 있어도 "단순 포함(in)" 여부로 판단합니다(단순 규칙).

    [왜 단순 포함 기반인가 — 강의 맥락에서 확인할 포인트]
        - 의미 유사도/형태소 분석 없이 "문자열 포함"만으로 채점하는, 의도적으로 단순한 평가입니다.
        - 수업에서는 "이 단순 규칙의 한계는 무엇인가(동의어·어미 변화를 못 잡음)"를 함께
          이야기하기 좋은 출발점입니다. 운영 평가에서는 더 정교한 매칭이 필요합니다.

    반환: matched_keywords / missing_keywords / score / total / ratio
    """
    # expected_keywords가 비어 있거나 잘못된 형태면 안전하게 빈 평가를 돌려줍니다.
    if not isinstance(expected_keywords, list) or not expected_keywords:
        return {"matched_keywords": [], "missing_keywords": [], "score": 0, "total": 0, "ratio": 0.0}

    # 모든 chunk의 text를 이어 붙여 소문자로 만든 "검색 대상 텍스트"를 만듭니다.
    combined_text = " ".join(str(chunk.get("text", "") or "") for chunk in retrieved_chunks).lower()

    matched: list[str] = []
    missing: list[str] = []
    for keyword in expected_keywords:
        # 키워드도 소문자로 맞춰 비교합니다(대소문자 무시).
        if str(keyword).lower() in combined_text:
            matched.append(keyword)
        else:
            missing.append(keyword)

    total = len(expected_keywords)
    score = len(matched)
    # ratio: 몇 퍼센트나 맞았는지(0.0~1.0). total이 0이면 0.0 (위에서 이미 걸렀지만 안전 차원).
    ratio = round(score / total, 4) if total > 0 else 0.0

    return {
        "matched_keywords": matched,
        "missing_keywords": missing,
        "score": score,
        "total": total,
        "ratio": ratio,
    }


# ──────────────────────────────────────────────────────────────────────
# 10. Metadata 점수 함수
# ──────────────────────────────────────────────────────────────────────
def score_metadata(expected_metadata: dict, retrieved_chunks: list[dict]) -> dict:
    """
    기대 metadata(expected_metadata)의 key/value가 검색 결과 metadata에 있는지 셉니다.

    방식:
        - 기대 key/value 한 쌍이, 검색된 chunk 중 "하나라도" 같은 값을 가지면 매칭으로 봅니다.
        - 값 비교는 normalize_value()로 정규화해 True / "true" / "True" 를 같게 봅니다.

    [왜 "하나라도 일치하면 매칭"인가 — 코드 해석을 돕기 위한 설명]
        - 근거는 여러 chunk에 흩어져 있을 수 있습니다. 기대 metadata(예: alarm_code)가
          top-N 중 어느 한 chunk에라도 정확히 들어 있으면 "그 근거를 찾아온 것"으로 봅니다.
        - 그래서 모든 chunk가 다 가질 필요는 없고, 하나만 일치해도 그 key는 매칭 처리합니다.

    반환: matched_metadata / missing_metadata / score / total / ratio
        - expected_metadata가 비어 있으면 total=0, ratio=1.0 으로 처리합니다.
          ("비교할 기준이 없으니 metadata 측면에서는 통과로 본다"는 의미. 이 1.0은 아래
           judge_evidence_quality에서 metadata 조건을 자동 통과시키는 역할을 합니다.)
    """
    # 기대 metadata가 없거나 빈 dict면 비교할 게 없으므로 ratio=1.0(통과 취급).
    if not isinstance(expected_metadata, dict) or not expected_metadata:
        return {"matched_metadata": {}, "missing_metadata": {}, "score": 0, "total": 0, "ratio": 1.0}

    # 검색된 chunk들의 metadata만 미리 모아 둡니다(없거나 dict 아니면 빈 dict).
    chunk_metadatas = [
        chunk.get("metadata", {}) if isinstance(chunk.get("metadata", {}), dict) else {}
        for chunk in retrieved_chunks
    ]

    matched: dict = {}
    missing: dict = {}
    for key, expected_raw in expected_metadata.items():
        expected_norm = normalize_value(expected_raw)  # 기대값 정규화

        # 어느 한 chunk라도 같은 key를 가지고 값이 같으면 매칭으로 인정합니다.
        is_matched = False
        for metadata in chunk_metadatas:
            if key in metadata and normalize_value(metadata.get(key)) == expected_norm:
                is_matched = True
                break

        if is_matched:
            matched[key] = expected_raw
        else:
            missing[key] = expected_raw

    total = len(expected_metadata)
    score = len(matched)
    ratio = round(score / total, 4) if total > 0 else 1.0

    return {
        "matched_metadata": matched,
        "missing_metadata": missing,
        "score": score,
        "total": total,
        "ratio": ratio,
    }


# ──────────────────────────────────────────────────────────────────────
# 11. Evidence Quality 판정 함수
# ──────────────────────────────────────────────────────────────────────
def judge_evidence_quality(
    case: dict,
    keyword_score: dict,
    metadata_score: dict,
    retrieved_chunks: list[dict],
) -> str:
    """
    채점 결과를 종합해 이 케이스의 검색 근거 품질을 PASS / WARN / FAIL 로 판정합니다.

    [판정 순서가 왜 중요한가 — 학습 흐름을 따라가기 위한 설명]
        - 아래 규칙은 "위에서부터 먼저 맞는 것"이 적용됩니다(early return).
        - 그래서 특수 케이스(out_of_scope, 근거 없음이 정상)를 일반 점수 규칙보다 "먼저"
          처리해야 합니다. 순서를 바꾸면 같은 데이터라도 판정이 달라질 수 있습니다.

    판정 순서(위에서부터 우선 적용):
        0) out_of_scope 케이스(현재 3개 문서 범위 밖) → 가장 먼저 처리
            - 키워드/메타데이터가 모두 0 매칭 → PASS
              (범위 밖 직접 근거가 없음을 올바르게 판단한 것이므로 통과)
            - 일부라도 매칭 → WARN
              (범위 밖 케이스인데 유사 근거와 혼동할 가능성이 있음)
            - 주의: 유사 문서(retrieved_chunks)가 검색되었다는 이유만으로 FAIL 하지 않습니다.
        1) "근거 없음이 정상"인 케이스(none / none_or_low_confidence)
            - 검색 결과 없음 → PASS (없는 게 맞으니 통과)
            - 검색 결과 있음 → WARN (유사 문서를 확정 근거로 쓰면 안 됨)
        2) 검색 결과가 아예 없음 → FAIL
        3) 키워드를 하나도 못 맞춤(score==0) → FAIL
        4) 키워드 70% 이상 AND metadata 50% 이상 → PASS
        5) 키워드 40% 이상 → WARN
        6) 그 외 → FAIL
    """
    evidence_type = str(case.get("expected_evidence_type", "") or "").strip().lower()

    # 0) out_of_scope 케이스를 가장 먼저 처리합니다.
    #    - Chroma는 범위 밖 질문에도 유사 문서를 가져올 수 있습니다.
    #    - 따라서 "유사 문서가 검색되었는가"가 아니라
    #      "직접 근거(expected_keywords/expected_metadata)가 매칭되지 않는가"로 판단합니다.
    #    - 직접 근거가 전혀 매칭되지 않으면 "범위 밖 직접 근거 없음"을 올바르게 판단한 것이므로 PASS.
    #    - 일부라도 매칭되면 유사 근거 혼동 가능성이 있으므로 WARN.
    if is_out_of_scope_case(case):
        keyword_matches = keyword_score.get("score", 0)
        metadata_matches = metadata_score.get("score", 0)
        if keyword_matches == 0 and metadata_matches == 0:
            return "PASS"
        return "WARN"

    # 1) "근거 없음이 정상"인 케이스 처리
    if evidence_type in NONE_EVIDENCE_TYPES:
        if not retrieved_chunks:
            return "PASS"   # 없는 게 정상인데 정말 없음 → 통과
        return "WARN"       # 없어야 하는데 유사 문서가 검색됨 → 경고

    # 2) 일반 케이스인데 검색 결과 자체가 없음 → 근거 없음이므로 실패
    if not retrieved_chunks:
        return "FAIL"

    # 3) 키워드를 하나도 못 맞춤 → 검색이 질문과 동떨어진 것이므로 실패
    if keyword_score.get("score", 0) == 0:
        return "FAIL"

    keyword_ratio = keyword_score.get("ratio", 0.0)
    # metadata total이 0이면 ratio는 1.0(위 score_metadata에서 그렇게 처리) → 나눗셈 오류 없음
    metadata_ratio = metadata_score.get("ratio", 1.0)

    # 4) 키워드도 충분히 맞고 metadata도 절반 이상 맞으면 통과
    if keyword_ratio >= 0.7 and metadata_ratio >= 0.5:
        return "PASS"

    # 5) 키워드가 40% 이상은 맞으면 일단 경고(완전 실패는 아님)
    if keyword_ratio >= 0.4:
        return "WARN"

    # 6) 그 외는 실패
    return "FAIL"


# ──────────────────────────────────────────────────────────────────────
# 12. 실패/주의 원인 생성 함수
# ──────────────────────────────────────────────────────────────────────
def build_missing_reason(
    case: dict,
    keyword_score: dict,
    metadata_score: dict,
    retrieved_chunks: list[dict],
    retrieval_info: dict,
) -> list[str]:
    """
    왜 이런 판정이 나왔는지 사람이 읽을 수 있는 "원인 메모"를 리스트로 만듭니다.

    [이 함수의 역할 — 강의 맥락에서 확인할 포인트]
        - PASS/WARN/FAIL 판정은 결론만 알려 주고 "왜"는 알려 주지 않습니다.
        - 이 함수는 그 "왜"를 사람이 읽기 쉬운 문장 목록으로 만들어,
          수업 보고서(Markdown)에서 실패/주의 원인을 바로 확인할 수 있게 합니다.

    포함 가능한 항목:
        - 검색 결과가 없을 때
        - mock fallback이 일어났을 때(사유 포함)
        - 누락된 키워드 / 누락된 metadata
        - 검색 결과에 metadata가 전혀 없을 때
        - "근거 없음이 정상"인데 유사 문서가 검색되었을 때(확정 근거 금지 안내)
    """
    reasons: list[str] = []

    # 검색 결과가 없는 경우
    if not retrieved_chunks:
        reasons.append("검색 결과가 없습니다.")

    # mock fallback이 발생한 경우(사유를 그대로 붙여 추적 가능하게 함)
    if retrieval_info.get("fallback_used"):
        reasons.append(f"Chroma 검색 실패로 mock fallback 사용: {retrieval_info.get('fallback_reason')}")

    # 누락된 키워드가 있으면 나열
    missing_keywords = keyword_score.get("missing_keywords", [])
    if missing_keywords:
        reasons.append("누락 키워드: " + ", ".join(str(keyword) for keyword in missing_keywords))

    # 누락된 metadata가 있으면 나열
    missing_metadata = metadata_score.get("missing_metadata", {})
    if missing_metadata:
        pairs = ", ".join(f"{key}={value}" for key, value in missing_metadata.items())
        reasons.append("누락 metadata: " + pairs)

    # 검색 결과는 있는데 그 안에 metadata가 전혀 없는 경우
    if retrieved_chunks:
        has_any_metadata = any(
            isinstance(chunk.get("metadata"), dict) and chunk.get("metadata")
            for chunk in retrieved_chunks
        )
        if not has_any_metadata:
            reasons.append("검색 결과에 metadata가 없습니다.")

    # out_of_scope 케이스를 사람이 이해하기 쉽게 별도 안내합니다.
    #   - 범위 밖 케이스는 retrieved_chunks가 있어도 직접 근거가 없으면 실패로 보지 않습니다.
    evidence_type = str(case.get("expected_evidence_type", "") or "").strip().lower()
    if is_out_of_scope_case(case):
        keyword_matches = keyword_score.get("score", 0)
        metadata_matches = metadata_score.get("score", 0)
        if keyword_matches == 0 and metadata_matches == 0:
            reasons.append(
                "현재 3개 문서 범위 밖 케이스이며, 기대 설비/알람에 대한 직접 근거가 검색되지 않았습니다."
            )
        if retrieved_chunks:
            reasons.append("유사 문서가 검색되었더라도 직접 근거로 사용하면 안 됩니다.")
        reasons.append(
            "범위 밖(out_of_scope) 케이스는 유사 문서가 검색되어도 직접 근거가 없으면 실패로 보지 않습니다."
        )
        return reasons

    # "근거 없음이 정상"인데 유사 문서가 검색된 경우의 강한 주의 문구
    if evidence_type in NONE_EVIDENCE_TYPES and retrieved_chunks:
        reasons.append(
            "없는 항목 또는 근거 부족 케이스에서 유사 문서가 검색되었습니다. "
            "이 문서를 확정 근거로 사용하면 안 됩니다."
        )

    return reasons
