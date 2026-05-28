# Day2 RAG Agent v1 실행 결과 (노트북 통합 실행)

## 1. 실행 개요

- 검색 → State → Node/조건부 분기 → Trace → 최종 답변 흐름을 하나로 묶은 결과입니다.
- 검색 방식: Chroma Vector DB (의미 기반)

## 2. 사용자 질문

- EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘

## 3. 설비 ID / 알람 코드

- equipment_id: EQP-EV-03
- alarm_code: ALM-TEMP-402

## 4. 검색 근거 (retrieved_docs)

| rank | score | doc_name | chunk_id | section_title |
|---:|---:|---|---|---|
| 1 | 0.0732 | alarm_manual.md | CHUNK-0016 | 4.2 같은 챔버에서 반복 발생 |
| 2 | 0.0668 | alarm_manual.md | CHUNK-0009 | 3.2 알람 의미 |
| 3 | 0.057 | alarm_manual.md | CHUNK-0075 | 11.2 리포트형 답변 예시 |

## 5. grounding_status

- grounded

## 6. 최종 답변 (초안)

## 근거 기반 답변 초안
- 설비 ID: EQP-EV-03
- 알람 코드: ALM-TEMP-402

### 사용한 검색 근거
- alarm_manual.md / 4.2 같은 챔버에서 반복 발생 (score=0.0732)
- alarm_manual.md / 3.2 알람 의미 (score=0.0668)
- alarm_manual.md / 11.2 리포트형 답변 예시 (score=0.057)

### 정리
검색된 문서 근거를 기준으로 원인 후보와 품질 영향 확인 항목을 정리합니다. 원인은 단정하지 않고 담당자 검토가 필요한 후보로만 제시합니다.

## 7. Trace 요약

| 순서 | node_name | status |
|---:|---|---|
| 1 | parse_query_node | success |
| 2 | retrieve_docs_node | success |
| 3 | generate_answer_node | success |
| 4 | verify_grounding_node | success |

> 핵심은 답변 문장이 매끄러운지가 아니라, 어떤 문서 근거를 썼고 State·Trace에 남았는지입니다.
