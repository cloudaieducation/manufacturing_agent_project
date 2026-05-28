# Day2 RAG 검색 결과 (Top-3 근거 후보)

- 검색 방식: Chroma Vector DB (의미 기반)

> Top-3는 정답 3개가 아니라 답변 전 검토할 근거 후보 집합입니다. score, doc_name, chunk_id, section_title, text를 함께 확인하세요.

## Q001

- user_query: ALM-TEMP-402 알람은 디스플레이 패널 제조 라인의 증착 공정에서 어떤 의미로 해석해야 하나요?

| rank | score | doc_name | chunk_id | section_title | preview |
|---:|---:|---|---|---|---|
| 1 | 0.0269 | troubleshooting_guide.md | CHUNK-0118 | 10. 조치 방향 작성 기준 | ALM-TEMP-402 반복 알람에 대한 조치 방향은 실제 장비 제어 지시가 아니라 확인과 검토 중심으로 작성해야 합니다. 이 문서는 교육용 샘... |
| 2 | 0.0268 | troubleshooting_guide.md | CHUNK-0106 | 7. 공정 상태 확인 관점 | 공정 상태 확인은 ALM-TEMP-402 반복 알람을 해석할 때 중요한 기준입니다. 디스플레이 패널 제조 라인의 증착 공정에서는 설비 상태와 공... |
| 3 | 0.0253 | troubleshooting_guide.md | CHUNK-0112 | 8. 품질 영향 확인 관점 | 품질 영향 확인에서 중요한 점은 직접 원인으로 단정하지 않는 것입니다. 불량률 변화가 보이더라도 “ALM-TEMP-402 때문에 불량이 발생했습... |

## Q002

- user_query: EQP-EV-03에서 ALM-TEMP-402 반복 알람이 발생했을 때 가능한 원인 후보를 정리해 주세요.

| rank | score | doc_name | chunk_id | section_title | preview |
|---:|---:|---|---|---|---|
| 1 | 0.0846 | troubleshooting_guide.md | CHUNK-0093 | 4. EQP-EV-03 설비 상황 예시 | EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생하는 상황을 가정합니다. 이때 주요 증상은 온도 상승 흐름이 반복적으로 관찰되고, ... |
| 2 | 0.0693 | troubleshooting_guide.md | CHUNK-0112 | 8. 품질 영향 확인 관점 | 품질 영향 확인에서 중요한 점은 직접 원인으로 단정하지 않는 것입니다. 불량률 변화가 보이더라도 “ALM-TEMP-402 때문에 불량이 발생했습... |
| 3 | 0.0687 | troubleshooting_guide.md | CHUNK-0106 | 7. 공정 상태 확인 관점 | 공정 상태 확인은 ALM-TEMP-402 반복 알람을 해석할 때 중요한 기준입니다. 디스플레이 패널 제조 라인의 증착 공정에서는 설비 상태와 공... |

## Q003

- user_query: 온도 상승 반복 알람이 발생했을 때 1차로 확인해야 할 항목은 무엇인지 알려 주세요.

| rank | score | doc_name | chunk_id | section_title | preview |
|---:|---:|---|---|---|---|
| 1 | 0.6904 | alarm_manual.md | CHUNK-0027 | 5.2 문서 기준 확인 항목 | 이 키워드는 1일차 단순 문서 검색 실습과 2일차 RAG 검색 실습에서 사용할 수 있습니다. |
| 2 | 0.6111 | alarm_manual.md | CHUNK-0011 | 3.2 알람 의미 | AI Agent는 이 알람을 해석할 때 다음 정보를 함께 확인할 수 있습니다. |
| 3 | 0.6111 | alarm_manual.md | CHUNK-0070 | 11. Agent 답변 예시 | 아래 예시는 교육용 문서 검색과 RAG 실습에서 사용할 수 있는 답변 형식입니다. |
