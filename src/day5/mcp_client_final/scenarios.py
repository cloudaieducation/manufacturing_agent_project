# -*- coding: utf-8 -*-
"""
Day5 mcp_client_final - Agent 실행 예시 질문 정의 (scenarios)

[이 파일의 역할]
mcp_client_final 의 Streamlit 화면 'Agent 실행' 탭에서 selectbox 로 선택할 수 있는 예시 질문을
관리하는 '데이터 정의 파일'입니다. 실행 로직이 아니라, 화면에 보여 줄 예시 질문 목록(SCENARIOS)을 둡니다.

[예시 질문 구성]
SCENARIOS 의 예시 질문은 다음 흐름을 단계적으로 확인할 수 있도록 구성되어 있습니다.
- DB 조회        → Agent 가 RAG 없이 DB Tool 만 선택하는 흐름
- RAG 검색       → Agent 가 매뉴얼/근거 문서 검색만 선택하는 흐름
- DB+RAG 비교    → DB 사실과 RAG 근거를 함께 조합해 비교·검증하는 흐름
- 다중 Tool 조회 → 여러 DB Tool 을 순차로 호출해 결과를 Tool 별로 분리해 보는 흐름
- 결과 없음 확인 → 조회 결과가 없을 때 EMPTY 가 ERROR 와 구분되는지 확인하는 흐름
- Agent 판단     → 설비 사실 확인과 조치 근거 검색이 함께 필요하다고 판단하는 흐름

[관리 기준 — 매우 중요]
- 이 파일은 'Agent 실행' 탭의 예시 질문을 위한 데이터 정의 파일이다(실행 로직은 agent_flow.py 에 있다).
- '다중 DB Tool 병렬 호출 데모'(Client 측 병렬 호출 데모) 질문은 이 파일에 넣지 않고, 별도 병렬 탭에서 관리한다.
- 각 항목의 expected_intent 는 agent_flow.py 의 실제 의도 분류 결과와 일치해야 한다.
- agent_flow.py 로직은 바꾸지 않고, 필요하면 질문 문장을 조정해 분류 결과를 맞춘다.
- 예시 질문은 mcp_client_final 이 실제로 선택 가능한 Tool 흐름에 맞게 구성한다
  (get_equipment_overview / get_recent_alarm_events / get_quality_metrics /
   get_maintenance_history / search_manual).
- 서버에는 존재하지만 agent_flow.py 가 선택하지 않는 Tool 을 전제로 한 질문은 넣지 않는다.

[주의]
모든 식별자(EQP-*/ALM-*/LINE-*)는 교육용 가상 값입니다(실제 설비 아님).
"""
from __future__ import annotations


# 각 시나리오: name(이름) / question(예시 질문) / explanation(수업 설명 문구) /
#              expected_intent(예상 의도) / key_concept(학생이 이해해야 할 핵심 개념)
SCENARIOS = [
    {
        "name": "01. DB 조회 - 설비 상태",
        "question": "EQP-EV-03 지금 상태 알려줘",
        "explanation": "설비 관련 질문이 RAG 검색 없이 DB 조회 흐름으로 처리되는지 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "DB_ONLY 판단, 설비 개요 Tool 호출, data_source 확인",
    },
    {
        "name": "02. DB 조회 - 설비 개요",
        "question": "EQP-EV-03 설비 개요 알려줘",
        "explanation": "설비 ID를 기준으로 설비 유형, 라인 정보, 데이터 출처가 어떻게 표시되는지 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "get_equipment_overview, equipment_type, line_id, data_source",
    },
    {
        "name": "03. DB 조회 - 최근 알람 이력",
        "question": "EQP-EV-03 최근 알람 이력 보여줘",
        "explanation": "설비 기준으로 최근 알람 이력이 조회되고 event_count가 표시되는지 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "get_recent_alarm_events, recent_events, event_count",
    },
    {
        "name": "04. DB 조회 - 알람 코드 필터",
        "question": "EQP-EV-03에서 ALM-TEMP-402 알람이 몇 번 발생했는지 알려줘",
        "explanation": "설비 ID와 알람 코드를 함께 사용해 알람 이력이 필터링되는지 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "alarm_code 필터, event_count, Tool 인자 구성",
    },
    {
        "name": "05. DB 조회 - 불량률 지표",
        "question": "EQP-EV-03 불량률 지표 알려줘",
        "explanation": "품질 지표 조회 흐름과 metric_name allowlist가 적용되는 방식을 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "get_quality_metrics, defect_rate, data_source",
    },
    {
        "name": "06. DB 조회 - 라인 수율 지표",
        "question": "LINE-07 수율 지표 보여줘",
        "explanation": "라인 ID를 기준으로 품질 지표를 조회하는 흐름을 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "line_id 기반 품질 조회, yield_rate",
    },
    {
        "name": "07. DB 조회 - 검사 결과 지표",
        "question": "EQP-EV-03 검사 결과 지표 알려줘",
        "explanation": "inspection_result 지표가 품질 Tool을 통해 조회되는지 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "metric_name allowlist, inspection_result",
    },
    {
        "name": "08. DB 조회 - 정비 이력",
        "question": "EQP-EV-03 정비 이력 알려줘",
        "explanation": "설비 ID를 기준으로 정비 이력과 건수가 조회되는지 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "get_maintenance_history, history, count, fallback_used",
    },
    {
        "name": "09. RAG 검색 - 조치 절차",
        "question": "ALM-TEMP-402 조치 절차가 뭐야?",
        "explanation": "알람 코드 중심 질문이 DB 조회가 아닌 매뉴얼 검색 흐름으로 처리되는지 확인합니다.",
        "expected_intent": "RAG_ONLY",
        "key_concept": "search_manual, alarm_code, documents, retrieval_source",
    },
    {
        "name": "10. RAG 검색 - 원인 확인",
        "question": "ALM-TEMP-402 원인이 뭘까?",
        "explanation": "설비 ID 없이 알람 코드만 주어졌을 때 RAG 검색이 선택되는지 확인합니다.",
        "expected_intent": "RAG_ONLY",
        "key_concept": "RAG_ONLY 판단, search_manual, 검색 근거",
    },
    {
        "name": "11. RAG 검색 - 공정 매뉴얼",
        "question": "증착 트러블슈팅 매뉴얼을 찾아줘",
        "explanation": "증착 관련 키워드를 기준으로 매뉴얼 검색이 수행되는지 확인합니다.",
        "expected_intent": "RAG_ONLY",
        "key_concept": "query 기반 RAG 검색, documents 개수",
    },
    {
        "name": "12. RAG 검색 - 온도 상승 근거",
        "question": "온도 상승 시 대처 방법 매뉴얼 근거를 알려줘",
        "explanation": "증상 중심 질문이 문서 근거 검색으로 연결되는지 확인합니다.",
        "expected_intent": "RAG_ONLY",
        "key_concept": "retrieval_source, documents, 근거 확인",
    },
    {
        "name": "13. DB+RAG 비교 - 알람과 조치 절차",
        "question": "EQP-EV-03 최근 알람 이력과 조치 절차를 함께 확인해줘",
        "explanation": "DB의 알람 이력과 RAG의 조치 절차를 함께 확인하는 흐름을 보여 줍니다.",
        "expected_intent": "DB_AND_RAG",
        "key_concept": "DB 결과와 RAG 근거 비교, evidence_level",
    },
    {
        "name": "14. DB+RAG 비교 - 불량률과 매뉴얼 근거",
        "question": "EQP-EV-03 불량률을 확인하고 관련 매뉴얼 근거도 알려줘",
        "explanation": "품질 지표 조회 결과와 매뉴얼 근거가 함께 사용되는지 확인합니다.",
        "expected_intent": "DB_AND_RAG",
        "key_concept": "품질 지표, search_manual, 근거 비교",
    },
    {
        "name": "15. DB+RAG 비교 - 반복 알람과 품질 영향",
        "question": "EQP-EV-03에서 ALM-TEMP-402가 반복되는데 품질 영향과 추가 확인 방향 알려줘",
        "explanation": "알람 이력, 품질 지표, 설비 개요, 매뉴얼 검색이 함께 사용되는 종합 흐름을 확인합니다.",
        "expected_intent": "DB_AND_RAG",
        "key_concept": "다중 Tool 호출, DB+RAG 비교, evidence_level",
    },
    {
        "name": "16. DB+RAG 비교 - 품질 지표와 매뉴얼 비교",
        "question": "EQP-EV-03 품질 지표가 정상 범위인지 매뉴얼과 비교해줘",
        "explanation": "DB 조회 결과와 문서 근거를 비교해 판단 흐름이 구성되는지 확인합니다.",
        "expected_intent": "DB_AND_RAG",
        "key_concept": "db_supported, rag_supported, evidence_level",
    },
    {
        "name": "17. 다중 Tool 조회 - 설비와 알람",
        "question": "EQP-EV-03 설비 개요와 최근 알람 이력을 함께 보여줘",
        "explanation": "두 개의 DB Tool이 선택되고 결과가 Tool별로 분리되어 표시되는지 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "다중 Tool 순차 호출, Tool별 trace 분리",
    },
    {
        "name": "18. 다중 Tool 조회 - 알람, 품질, 정비",
        "question": "EQP-EV-03 알람 이력, 품질 지표, 정비 이력을 모두 확인해줘",
        "explanation": "여러 DB Tool이 순차적으로 호출되고 결과가 각각 구분되는지 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "다중 Tool 호출, alarm, quality, maintenance",
    },
    {
        "name": "19. 결과 없음 확인 - 알람 이력",
        "question": "EQP-IN-02 최근 알람 이력 알려줘",
        "explanation": "조회 결과가 없을 때 EMPTY가 ERROR와 구분되어 표시되는지 확인합니다.",
        "expected_intent": "DB_ONLY",
        "key_concept": "EMPTY, ERROR 구분, 결과 없음 처리",
    },
    {
        "name": "20. Agent 판단 - 이상 조치",
        "question": "EQP-EV-03 상태가 이상한데 어떻게 조치해야 해?",
        "explanation": "설비 상태 확인과 조치 근거 검색이 함께 필요한 질문으로 판단되는지 확인합니다.",
        "expected_intent": "DB_AND_RAG",
        "key_concept": "Agent 판단 흐름, DB+RAG 동시 판단, 추가 확인 방향",
    },
]


def get_scenarios() -> list:
    """수업 시연용 시나리오 목록을 돌려준다(streamlit selectbox 등에서 사용)."""
    return list(SCENARIOS)


def get_example_questions() -> list:
    """예시 질문 문자열만 돌려준다(selectbox option 용)."""
    return [s["question"] for s in SCENARIOS]
