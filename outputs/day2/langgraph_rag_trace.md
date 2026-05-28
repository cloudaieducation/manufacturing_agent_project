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
| 2 | retrieve_docs_node | success | 1. troubleshooting_guide.md / 1. 문서 개요 / score=0.5455 / 문서의 주요 목적은 제조 기술 문서를 검색하고, 검색된 근거를 바탕으로 설비 알람의 원인 후보와 확인 항목을 정리하는 과정을 이해하는 것입니다.... 2. troubleshooting_guide.md / 2. 반복 알람 대응 기본 원칙 / score=0.5455 / EQP-EV-03에서 ALM-TEMP-402가 반복 발생한 경우, 알람 발생 시점만 확인하는 것은 충분하지 않습니다. 공정 상태, 품질 지표, ... 3. troubleshooting_guide.md / 8. 품질 영향 확인 관점 / score=0.5455 / EQP-EV-03에서 ALM-TEMP-402가 반복 발생한 구간 전후로 불량률, 수율, 검사 결과를 확인할 필요가 있습니다. 품질 지표가 평소와... |
| 3 | generate_answer_node | success | answer_source=notebook_draft |
| 4 | verify_grounding_node | success | grounding_status=grounded, needs_rewrite=False |
