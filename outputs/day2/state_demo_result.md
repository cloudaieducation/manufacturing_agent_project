# Day2 LangGraph State 구조 데모

## 1. State 역할 요약

- State는 Node 사이에서 공유되는 업무 처리 문맥입니다.
- retrieved_docs는 답변 생성과 grounding 검증의 핵심 입력입니다.

## 2. 현재 State 요약

- user_query: EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘
- equipment_id: EQP-EV-03
- alarm_code: ALM-TEMP-402
- grounding_status: grounded
- retrieved_docs 수: 3

## 3. retrieved_docs 요약

1. troubleshooting_guide.md / 1. 문서 개요 / score=0.5455 / 문서의 주요 목적은 제조 기술 문서를 검색하고, 검색된 근거를 바탕으로 설비 알람의 원인 후보와 확인 항목을 정리하는 과정을 이해하는 것입니다....
2. troubleshooting_guide.md / 2. 반복 알람 대응 기본 원칙 / score=0.5455 / EQP-EV-03에서 ALM-TEMP-402가 반복 발생한 경우, 알람 발생 시점만 확인하는 것은 충분하지 않습니다. 공정 상태, 품질 지표, ...
3. troubleshooting_guide.md / 8. 품질 영향 확인 관점 / score=0.5455 / EQP-EV-03에서 ALM-TEMP-402가 반복 발생한 구간 전후로 불량률, 수율, 검사 결과를 확인할 필요가 있습니다. 품질 지표가 평소와...
