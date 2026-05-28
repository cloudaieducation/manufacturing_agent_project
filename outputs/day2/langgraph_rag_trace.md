# Day2 LangGraph RAG 실행 Trace

- LangGraph 사용: True

## 1. 사용자 질문

- EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘

## 2. 최종 State 요약

- equipment_id: EQP-EV-03
- alarm_code: ALM-TEMP-402
- grounding_status: grounded
- needs_rewrite: False
- retry_count: 0
- retrieved_docs 수: 3

## 3. Node 실행 Trace

| 순서 | node_name | status | output_summary |
|---:|---|---|---|
| 1 | parse_query_node | success | equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402 |
| 2 | retrieve_docs_node | success | 1. alarm_manual.md / 4.2 같은 챔버에서 반복 발생 / score=0.0732 / 같은 챔버에서 `ALM-TEMP-402`가 여러 번 발생했다면 단순 일회성 알람이 아니라 반복 발생 패턴으로 볼 수 있습니다. 2. alarm_manual.md / 3.2 알람 의미 / score=0.0668 / `ALM-TEMP-402`는 교육용 가상 시나리오에서 박막 증착 공정 중 특정 챔버의 온도 값이 교육용 기준 범위에서 벗어난 상황을 나타내는 알... 3. alarm_manual.md / 11.2 리포트형 답변 예시 / score=0.057 / - 동일 설비 반복 여부 - 동일 챔버 집중 여부 - 심각도 변화 - 현장 메모 - 주변 시간대의 관련 교육용 알람 - 품질 영향 가능성 |
| 3 | generate_answer_node | success | answer_source=notebook_draft |
| 4 | verify_grounding_node | success | grounding_status=grounded, needs_rewrite=False |
