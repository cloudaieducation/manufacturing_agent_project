# -*- coding: utf-8 -*-
"""
Day4 RAG 검색 품질 평가기 - 재정렬(rerank) 계층 모듈 (reranking)

이 파일은 "검색된 top_k 결과를 질문 의도/메타데이터 기준으로 다시 정렬하고,
케이스 유형에 맞는 최종 근거 개수(top 3 또는 top 5)를 정하는" 진단용 reranker 단계만 모아 둡니다.
- 질문 의도 기반 우선 문서 추론(infer_preferred_doc_types)
- 케이스 유형별 최종 evidence 개수 결정(get_final_evidence_limit)
- 규칙 기반 재정렬(rerank_chunks)

교육용 리팩토링 7단계에서 runner.py로부터 분리했습니다.
- 함수 내부 로직은 분리 전과 한 글자도 다르지 않습니다(안전한 위치 이동).
- 검색(retrieval) / 채점(scoring) / 보고서(reporting) 로직은 이 파일에 들어오지 않습니다.
- 이 reranker는 평가용 진단 도구이며, 운영 search_manual Tool 설계와는 입력 신호가 다릅니다
  (자세한 설명은 rerank_chunks의 docstring 참고).

import 계층 규칙(중요):
- reranking.py는 config.py만 import 합니다(runner / retrieval / scoring / reporting 을 import 하지 않습니다).
  → config 아래 계층을 바라보는 단방향 구조라 순환 import가 생기지 않습니다.
"""

from __future__ import annotations

# 재정렬 점수 계산에서 metadata 값 비교를 정규화하기 위해 config의 normalize_value를 사용합니다.
from src.day4.rag_quality.config import normalize_value

def infer_preferred_doc_types(user_query: str, expected_evidence_type: str) -> list[str]:
    """
    질문 의도를 보고 우선 검색해야 할 문서 이름을 추론합니다. (doc_type routing)

    이 함수는 검색 결과를 조작하는 것이 아니라,
    현재 3개 문서(alarm_manual.md / quality_standard.md / troubleshooting_guide.md)의
    역할에 맞춰 검색 결과를 재정렬(rerank)하기 위한 routing 기준을 제공합니다.

    문서별 역할(현재 지식베이스 기준):
        - alarm_manual.md          : 알람 의미, 어떤 알람인지, 반복 발생, 챔버, 보조 알람, 알람 매뉴얼
        - quality_standard.md      : 품질 지표, 불량률, 수율, 검사 결과, 품질 영향, 관련 가능성
        - troubleshooting_guide.md : 원인 후보, 조치 방향, 정비 이력, 설정 변경, 공정 상태, 확인 항목
        - 단정 금지/추가 확인/근거 부족 질문 : 세 문서 모두 후보

    반환:
        - 우선 검색할 문서 이름 리스트(중복 제거, 등장 순서 유지)
        - out_of_scope 케이스는 우선 문서를 두지 않고 빈 리스트를 돌려줍니다.
    """
    text = str(user_query or "").lower()
    evidence_type = str(expected_evidence_type or "").lower()

    # out_of_scope 케이스는 "어느 문서를 우선할지" 자체가 의미 없으므로 빈 리스트.
    if evidence_type == "out_of_scope":
        return []

    preferred: list[str] = []

    # (1) 질문 텍스트의 의도 키워드로 문서 추론
    if any(keyword in text for keyword in ["품질", "불량률", "수율", "검사 결과", "품질 지표", "관련 가능성"]):
        preferred.append("quality_standard.md")

    if any(keyword in text for keyword in ["원인", "조치", "정비", "설정 변경", "확인 항목", "공정 상태", "점검"]):
        preferred.append("troubleshooting_guide.md")

    if any(keyword in text for keyword in ["알람 의미", "어떤 의미", "어떤 알람", "반복 발생", "보조 알람", "챔버", "매뉴얼"]):
        preferred.append("alarm_manual.md")

    # 단정 금지/추가 확인/근거 부족류 질문은 세 문서 모두 후보로 둡니다.
    if any(keyword in text for keyword in ["단정", "확정", "근거", "추가 확인", "부족", "실제 장비", "제어 지시"]):
        preferred.extend(["alarm_manual.md", "troubleshooting_guide.md", "quality_standard.md"])

    # (2) expected_evidence_type 으로 보강 (케이스가 기대하는 문서 유형 반영)
    if "quality_standard_document" in evidence_type:
        preferred.append("quality_standard.md")
    if "troubleshooting" in evidence_type or "maintenance" in evidence_type:
        preferred.append("troubleshooting_guide.md")
    if "alarm_manual" in evidence_type:
        preferred.append("alarm_manual.md")
    if "answer_caution_policy" in evidence_type:
        preferred.extend(["alarm_manual.md", "troubleshooting_guide.md", "quality_standard.md"])

    # 중복 제거(등장 순서 유지)
    result: list[str] = []
    for item in preferred:
        if item not in result:
            result.append(item)

    return result


def get_final_evidence_limit(case: dict) -> int:
    """
    케이스 유형에 따라 최종 평가에 사용할 evidence chunk 개수를 정합니다.

    기준:
        - 기본값 3 (direct_evidence / out_of_scope / low_confidence)
        - multi_document_evidence 이면 5

    이유:
        - direct_evidence는 한 문서 안에서 근거를 찾으므로 top 3로 충분합니다.
        - multi_document_evidence는 quality_standard.md, troubleshooting_guide.md,
          alarm_manual.md 의 근거가 함께 필요할 수 있어 top 3만으로 평가하면 불리합니다.
          그래서 top 5까지 최종 근거로 사용합니다.
    """
    case_design_type = str(case.get("case_design_type", "") or "").strip().lower()
    if case_design_type == "multi_document_evidence":
        return 5
    return 3


def rerank_chunks(case: dict, retrieved_chunks: list[dict]) -> list[dict]:
    """
    Chroma 검색 결과(top_k)를 질문 의도, expected_keywords, expected_metadata,
    doc_name, section_title 기준으로 재정렬합니다. (rule-based reranker)

    ============================================================
    [매우 중요] 이 함수는 "평가용 진단(diagnostic) reranker" 입니다.
    ============================================================
    - 목적은 평가기 내부에서 "현재 검색 결과가 질문 의도에 맞게 정렬될 수 있는가"를
      진단하기 위한 것입니다. 정답을 미리 알고 끼워 맞추는 장치가 아닙니다.
    - 그래서 여기서는 평가 케이스가 가진 expected_keywords / expected_metadata 를
      재정렬 신호로 사용합니다. (평가 데이터는 정답 라벨을 알고 있으므로 가능)
    - 반면 운영용 search_manual Tool 에서는 expected_keywords 같은 정답 라벨을
      절대 쓸 수 없습니다. 운영 reranker는 query analysis, entity extraction,
      metadata filter 결과를 신호로 사용해야 합니다.
    - 즉, 이 reranker는 "검색 품질을 진단/시연"하는 교육용 도구이며,
      운영 reranker 설계와는 입력 신호가 다르다는 점을 반드시 구분해야 합니다.

    동작:
        - 각 chunk에 rerank_score(점수)와 rerank_reasons(가점/감점 사유)를 추가합니다.
        - 외부 모델/외부 패키지를 전혀 사용하지 않는 단순 규칙 기반 점수입니다.

    점수 기준(교육용 기본값)과 각 점수의 의미:
        - keyword match           : +3  (기대 키워드가 본문/section/metadata에 들어 있음 = 내용 적합)
        - metadata match          : +3  (기대 metadata 값과 일치 = 구조적 적합)
        - preferred doc match     : +4  (질문 의도에 맞는 문서에서 나온 근거 = 문서 라우팅 적합)
        - exact alarm_code match  : +4  (질문의 핵심 식별자 알람 코드가 정확히 포함 = 강한 신호)
        - exact equipment_id match: +4  (질문의 핵심 식별자 설비 ID가 정확히 포함 = 강한 신호)
        - section_title match     : +2  (질문 의도와 section 제목이 맞음 = 위치 적합)
        - generic section penalty : -2  (문서 개요/검색 키워드/최종 정리 같은 일반 section은 감점)
          (단, 답변 주의/단정 금지/추가 확인을 묻는 질문에서는 주의사항 section이 오히려
           정답 근거일 수 있으므로 감점하지 않음)

    [점수 가중치에 대한 강의 맥락 설명]
        - "정확 식별자(+4) > 문서 라우팅(+4) > 내용/구조 일치(+3) > 위치(+2)" 순으로 가중치를 둡니다.
          핵심 식별자가 정확히 박혀 있을수록 "그 근거가 이 질문의 것"이라는 확신이 크기 때문입니다.
        - 점수 상수 값과 순서는 평가 결과(정렬 → 최종 근거 선택)에 직접 영향을 주므로,
          교육 중 값을 바꿔 볼 때는 결과가 달라질 수 있음을 함께 설명하면 좋습니다.
    """
    expected_keywords = case.get("expected_keywords", []) or []
    expected_metadata = case.get("expected_metadata", {}) or {}
    expected_evidence_type = case.get("expected_evidence_type", "")
    user_query = case.get("user_query", "")

    # 질문 의도 기반 우선 문서 목록(routing)
    preferred_docs = infer_preferred_doc_types(user_query, expected_evidence_type)
    query_text = str(user_query or "")

    reranked: list[dict] = []

    for original_rank, chunk in enumerate(retrieved_chunks):
        text = str(chunk.get("text", "") or "")
        metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata", {}), dict) else {}
        doc_name = str(metadata.get("doc_name", "") or "")
        section_title = str(metadata.get("section_title", "") or "")
        metadata_keywords = str(metadata.get("keywords", "") or "")

        # 점수 계산에 쓸 "본문 + section 제목 + metadata 키워드" 합본(소문자)
        combined = f"{text} {section_title} {metadata_keywords}".lower()

        score = 0
        reasons: list[str] = []

        # (1) expected_keywords 가점
        for keyword in expected_keywords:
            keyword_norm = str(keyword).lower()
            if keyword_norm and keyword_norm in combined:
                score += 3
                reasons.append(f"keyword:{keyword}")

        # (2) expected_metadata 가점 (key/value 정규화 일치)
        for key, expected_value in expected_metadata.items():
            if normalize_value(metadata.get(key)) == normalize_value(expected_value):
                score += 3
                reasons.append(f"metadata:{key}")

        # (3) preferred doc_type 가점 (질문 의도에 맞는 문서)
        if doc_name and doc_name in preferred_docs:
            score += 4
            reasons.append(f"preferred_doc:{doc_name}")

        # (4) 핵심 식별자(alarm_code / equipment_id) 정확 포함 가점
        alarm_code = expected_metadata.get("alarm_code")
        if alarm_code and str(alarm_code).lower() in combined:
            score += 4
            reasons.append("exact_alarm_code")

        equipment_id = expected_metadata.get("equipment_id")
        if equipment_id and str(equipment_id).lower() in combined:
            score += 4
            reasons.append("exact_equipment_id")

        # (5) section_title 이 질문 의도와 맞으면 가점
        if any(keyword in query_text for keyword in ["품질", "불량률", "수율", "검사 결과", "품질 지표"]):
            if any(keyword in section_title for keyword in ["품질", "불량률", "수율", "검사 결과"]):
                score += 2
                reasons.append("section_quality")

        if any(keyword in query_text for keyword in ["조치", "원인", "정비", "설정", "공정 상태", "확인 항목"]):
            if any(keyword in section_title for keyword in ["조치", "원인", "정비", "확인", "공정 상태"]):
                score += 2
                reasons.append("section_troubleshooting")

        if any(keyword in query_text for keyword in ["의미", "어떤 알람", "어떤 의미"]):
            if any(keyword in section_title for keyword in ["알람", "의미", "개요"]):
                score += 2
                reasons.append("section_alarm_definition")

        # (6) 너무 일반적인 section 감점
        #     단, 답변 주의사항/단정 금지/추가 확인을 묻는 질문에서는 주의사항 성격 section이
        #     오히려 정답 근거일 수 있으므로 감점하지 않습니다.
        asks_caution = any(keyword in query_text for keyword in ["단정", "확정", "추가 확인", "근거", "부족"])
        generic_sections = ["문서 개요", "검색 키워드", "최종 정리"]
        if not asks_caution and any(generic in section_title for generic in generic_sections):
            score -= 2
            reasons.append("generic_section_penalty")

        # 원본 chunk를 훼손하지 않도록 복사 후 "진단 필드"만 덧붙입니다.
        #   - original_rank  : 재정렬 전 원래 검색 순위(0부터). 정렬이 바뀐 정도를 보여 줌.
        #   - rerank_score   : 위에서 계산한 합산 점수.
        #   - rerank_reasons : 어떤 가점/감점이 적용됐는지 사유 목록(보고서에서 진단 근거로 사용).
        # 이 세 필드는 보고서의 "검색 결과 미리보기" 표에 그대로 노출되어,
        # 수강생이 "왜 이 근거가 위로 올라왔는가"를 눈으로 따라갈 수 있게 합니다.
        new_chunk = dict(chunk)
        new_chunk["original_rank"] = original_rank
        new_chunk["rerank_score"] = score
        new_chunk["rerank_reasons"] = reasons
        reranked.append(new_chunk)

    # 점수가 높은 순으로 정렬합니다. Python의 sort는 안정 정렬이라,
    # 동점인 chunk들끼리는 원래(original_rank) 순서가 그대로 유지됩니다.
    reranked.sort(key=lambda item: item.get("rerank_score", 0), reverse=True)
    return reranked
