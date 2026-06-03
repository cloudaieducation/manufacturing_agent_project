# -*- coding: utf-8 -*-
"""
Day5 mcp_server_final - rag_search 운영형 재정렬(rerank) 모듈 (reranking)

[출처/유래 — 매우 중요]
이 파일은 Day4 `rag_quality/reranking.py`를 Day5 `rag_search`로 가져오되,
**평가용 reranker는 그대로 쓰지 않고 운영형으로 다시 정리한 복사본**입니다.
Day4 원본은 수정하지 않습니다.

[왜 평가용 rerank_chunks(case, chunks)를 쓰지 않는가]
- Day4 `rerank_chunks(case, chunks)`는 평가 케이스의 정답 라벨
  (expected_keywords / expected_metadata / expected_evidence_type)에 의존합니다.
- 운영용 `search_manual`에는 정답 라벨이 존재하지 않습니다(실사용 질의만 있음).
- 따라서 평가용 함수를 그대로 쓰면 안 되며, 이 파일에는 평가 라벨에 의존하지 않는
  '운영형(query/metadata 기반) 정렬 함수'만 둡니다.
  → 평가용 rerank_chunks(case, chunks) / get_final_evidence_limit(case) 는 의도적으로
    가져오지 않았습니다(미사용/제외).

[운영형 정렬이 쓰는 신호 — 정답 라벨이 아님]
- 사용자 query 키워드
- 요청 인자(alarm_code / equipment_type)와 chunk metadata의 일치
- chunk metadata(section_title / doc_name / keywords / symptom / action)

import 계층 규칙:
- reranking.py는 config.py만 import 합니다(retrieval / adapter 등을 import 하지 않습니다).
  → 단방향 구조라 순환 import가 생기지 않습니다.
"""

from __future__ import annotations

# 값 비교(대소문자/공백/타입 정규화)에는 config의 normalize_value를 재사용합니다.
from day5.mcp_server_final.rag_search.config import normalize_value


# 현재 지식베이스(3개 문서) 기준 doc_type routing 키워드.
# (정답 라벨이 아니라, 사용자 query 의도만으로 우선 문서를 추론하기 위한 운영 신호입니다.)
_QUALITY_KEYWORDS = ["품질", "불량률", "수율", "검사 결과", "품질 지표", "관련 가능성"]
_TROUBLE_KEYWORDS = ["원인", "조치", "정비", "설정 변경", "확인 항목", "공정 상태", "점검"]
_ALARM_KEYWORDS = ["알람 의미", "어떤 의미", "어떤 알람", "반복 발생", "보조 알람", "챔버", "매뉴얼", "알람"]


def infer_preferred_doc_types_for_query(query: str) -> list[str]:
    """사용자 query '만'으로 우선 검색할 문서 이름을 추론한다(운영형 doc_type routing).

    [Day4 infer_preferred_doc_types 와의 차이]
        - Day4 버전은 expected_evidence_type(평가 라벨)도 함께 사용했지만,
          운영형인 이 함수는 정답 라벨을 쓰지 않고 query 키워드만 사용한다.

    [반환]
        우선 문서 이름 리스트(중복 제거, 등장 순서 유지). 매칭이 없으면 빈 리스트.
        문서 역할(현재 지식베이스):
          - quality_standard.md      : 품질/불량률/수율/검사 결과
          - troubleshooting_guide.md : 원인/조치/정비/공정 상태/확인 항목
          - alarm_manual.md          : 알람 의미/반복 발생/챔버/매뉴얼
    """
    text = str(query or "").lower()
    preferred: list[str] = []

    if any(keyword in text for keyword in _QUALITY_KEYWORDS):
        preferred.append("quality_standard.md")
    if any(keyword in text for keyword in _TROUBLE_KEYWORDS):
        preferred.append("troubleshooting_guide.md")
    if any(keyword in text for keyword in _ALARM_KEYWORDS):
        preferred.append("alarm_manual.md")

    # 중복 제거(등장 순서 유지)
    result: list[str] = []
    for item in preferred:
        if item not in result:
            result.append(item)
    return result


def _query_tokens(query: str) -> list[str]:
    """query를 소문자 토큰으로 분리한다(길이 2 이상만 사용, 중복 제거).

    너무 짧은 토큰(조사/한 글자)은 잡음이 많아 제외한다. 의미 검색을 대체하려는 것이
    아니라, metadata 텍스트에 query 핵심어가 들어 있는지 보는 가벼운 보조 신호다.
    """
    raw = str(query or "").lower().split()
    tokens: list[str] = []
    for token in raw:
        token = token.strip()
        if len(token) >= 2 and token not in tokens:
            tokens.append(token)
    return tokens


def rerank_chunks_for_manual_search(query, chunks, alarm_code=None, equipment_type=None):
    """검색 결과 chunk를 운영형 신호로 재정렬한다(정답 라벨 미사용).

    [입력]
        query         : 사용자 질의문.
        chunks         : retrieval 결과 list[dict]. chunk={chunk_id,text,metadata,distance,source}.
        alarm_code    : 요청 알람 코드(선택). metadata.alarm_code 와 일치하면 가점.
        equipment_type: 요청 설비 유형(선택). metadata.equipment_type 와 일치하면 가점.
    [반환]
        재정렬된 list[dict]. 각 chunk에 진단 필드(original_rank / operational_rerank_score /
        operational_rerank_reasons)를 덧붙인다. 원본 chunk는 훼손하지 않는다(복사 후 추가).

    [정렬 규칙(운영형, 정답 라벨 없음)]
        1) retrieve 순서를 기본으로 유지한다(original_rank, 안정 정렬).
        2) alarm_code 가 요청과 일치하면 우선(+4).
        3) equipment_type 이 요청과 일치하면 우선(+3).
        4) section_title / doc_name / keywords / symptom / action 등에 query 키워드가 있으면 우선(+2).
        5) 질문 의도(doc_type routing)에 맞는 문서면 우선(+2).
        6) 동일 점수면 원래 retrieval 순서를 유지(안정 정렬).

    [안정성]
        chunks 가 비어 있거나 형식이 어긋나면 원본을 그대로(또는 빈 리스트) 돌려준다.
    """
    if not isinstance(chunks, list) or not chunks:
        return chunks if isinstance(chunks, list) else []

    preferred_docs = infer_preferred_doc_types_for_query(query)
    tokens = _query_tokens(query)
    req_alarm = normalize_value(alarm_code) if alarm_code else ""
    req_equip = normalize_value(equipment_type) if equipment_type else ""

    reranked: list[dict] = []
    for original_rank, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        metadata = chunk.get("metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}

        doc_name = str(metadata.get("doc_name", "") or "")
        # query 키워드 매칭에 쓸 metadata 텍스트 합본(소문자). 본문(text)은 길어서 제외하고
        # 구조적 metadata 필드만 사용한다(운영형 가벼운 신호).
        combined = " ".join(
            str(metadata.get(key, "") or "")
            for key in ("section_title", "doc_name", "keywords", "symptom", "action")
        ).lower()

        score = 0
        reasons: list[str] = []

        # (2) alarm_code 일치 가점
        if req_alarm and normalize_value(metadata.get("alarm_code")) == req_alarm:
            score += 4
            reasons.append("alarm_code_match")

        # (3) equipment_type 일치 가점
        if req_equip and normalize_value(metadata.get("equipment_type")) == req_equip:
            score += 3
            reasons.append("equipment_type_match")

        # (4) query 키워드가 metadata 텍스트에 있으면 가점(한 번만)
        if tokens and any(token in combined for token in tokens):
            score += 2
            reasons.append("query_keyword_match")

        # (5) 질문 의도에 맞는 문서면 가점
        if doc_name and doc_name in preferred_docs:
            score += 2
            reasons.append(f"preferred_doc:{doc_name}")

        new_chunk = dict(chunk)
        new_chunk["original_rank"] = original_rank
        new_chunk["operational_rerank_score"] = score
        new_chunk["operational_rerank_reasons"] = reasons
        reranked.append(new_chunk)

    # 점수 내림차순 정렬. Python sort는 안정 정렬이라 동점은 original_rank 순서가 유지된다.
    reranked.sort(key=lambda item: item.get("operational_rerank_score", 0), reverse=True)
    return reranked
