# Day2 RAG 검색 품질 검토 결과

이 문서는 제조 기술 문서 참조형 RAG Agent v1이 질의별로 찾아온 근거 후보의
검색 품질을 검토하기 위한 자료입니다. 단순 검색 성공/실패 확인이 아니라,
"이 결과가 답변 근거로 쓸 만한가"를 사람이 판단하는 것이 목적입니다.

## 1. 검색 방식 요약

- 의미 기반 검색(Vector 검색)으로 질의와 가까운 문서 chunk를 찾습니다.
- 검색 대상 경로는 `C:\work\manufacturing_agent_project\vector_db\chroma_db`입니다.
- 검색 대상 collection 이름은 `manufacturing_rag_docs`입니다.
- Embedding provider: Ollama
- Embedding model: `nomic-embed-text:latest`
- Embedding API URL: `http://localhost:11434/api/embeddings`
- 저장할 때와 검색할 때 같은 embedding 모델을 사용해야 검색 결과가 일관됩니다.
- 각 질의마다 Top-3 결과를 찾고, LangGraph State의 `retrieved_docs`에 담겨
  답변 생성과 grounding 검증의 핵심 입력으로 사용됩니다.
- 이 검색 결과 구조(doc_name·chunk_id·section_title·text)는 3일차 search_manual
  MCP Tool의 출력 구조 기반이 됩니다.

## 2. 질의별 검색 결과

### Q001

- user_query: ALM-TEMP-402 알람은 디스플레이 패널 제조 라인의 증착 공정에서 어떤 의미로 해석해야 하나요?
- intent: 알람 의미 확인
- difficulty: basic
- expected_keywords: ALM-TEMP-402, 온도 상승, 반복 알람, 증착 공정
- expected_docs: alarm_manual.md, troubleshooting_guide.md

| rank | score | distance | doc_name | section_title | chunk_id | keywords | preview |
|---:|---:|---:|---|---|---|---|---|
| 1 | 0.0269 | 36.2127 | troubleshooting_guide.md | 10. 조치 방향 작성 기준 | CHUNK-0178 | ALM-TEMP-402, 반복 알람, 조치 방향 | ALM-TEMP-402 반복 알람에 대한 조치 방향은 실제 장비 제어 지시가 아니라 확인과 검토 중심으로 작성해야 합니다. 이 문서는 교육용 샘플 문서이므로 실제 현장 작업을 안내하지 않습니다. |
| 2 | 0.0268 | 36.3614 | troubleshooting_guide.md | 7. 공정 상태 확인 관점 | CHUNK-0166 | ALM-TEMP-402, 설비, 증착 공정, 공정 상태, 제조 라인, 디스플레이 패널 제조 라인, 반복 알람 | 공정 상태 확인은 ALM-TEMP-402 반복 알람을 해석할 때 중요한 기준입니다. 디스플레이 패널 제조 라인의 증착 공정에서는 설비 상태와 공정 흐름이 함께 영향을 주고받을 수 있기 때문입니다. |
| 3 | 0.0253 | 38.534 | troubleshooting_guide.md | 8. 품질 영향 확인 관점 | CHUNK-0172 | ALM-TEMP-402, 불량률, 품질 영향 | 품질 영향 확인에서 중요한 점은 직접 원인으로 단정하지 않는 것입니다. 불량률 변화가 보이더라도 “ALM-TEMP-402 때문에 불량이 발생했습니다”라고 표현하지 않아야 합니다. |

### Q002

- user_query: EQP-EV-03에서 ALM-TEMP-402 반복 알람이 발생했을 때 가능한 원인 후보를 정리해 주세요.
- intent: 원인 후보 확인
- difficulty: basic
- expected_keywords: EQP-EV-03, ALM-TEMP-402, 반복 알람, 원인 후보, 온도 상승
- expected_docs: alarm_manual.md, troubleshooting_guide.md

| rank | score | distance | doc_name | section_title | chunk_id | keywords | preview |
|---:|---:|---:|---|---|---|---|---|
| 1 | 0.0846 | 10.824 | troubleshooting_guide.md | 4. EQP-EV-03 설비 상황 예시 | CHUNK-0153 | ALM-TEMP-402, 온도 상승, 냉각 상태 | EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생하는 상황을 가정합니다. 이때 주요 증상은 온도 상승 흐름이 반복적으로 관찰되고, 일부 구간에서 냉각 상태가 안정적으로 유지되지 않는 것처럼 보이는 상황입니다. |
| 2 | 0.0693 | 13.4311 | troubleshooting_guide.md | 8. 품질 영향 확인 관점 | CHUNK-0172 | ALM-TEMP-402, 불량률, 품질 영향 | 품질 영향 확인에서 중요한 점은 직접 원인으로 단정하지 않는 것입니다. 불량률 변화가 보이더라도 “ALM-TEMP-402 때문에 불량이 발생했습니다”라고 표현하지 않아야 합니다. |
| 3 | 0.0687 | 13.5472 | troubleshooting_guide.md | 7. 공정 상태 확인 관점 | CHUNK-0166 | ALM-TEMP-402, 설비, 증착 공정, 공정 상태, 제조 라인, 디스플레이 패널 제조 라인, 반복 알람 | 공정 상태 확인은 ALM-TEMP-402 반복 알람을 해석할 때 중요한 기준입니다. 디스플레이 패널 제조 라인의 증착 공정에서는 설비 상태와 공정 흐름이 함께 영향을 주고받을 수 있기 때문입니다. |

### Q003

- user_query: 온도 상승 반복 알람이 발생했을 때 1차로 확인해야 할 항목은 무엇인지 알려 주세요.
- intent: 1차 확인 항목 정리
- difficulty: basic
- expected_keywords: 온도 상승, 반복 알람, 1차 확인 항목, 공정 상태, 냉각 상태
- expected_docs: troubleshooting_guide.md

| rank | score | distance | doc_name | section_title | chunk_id | keywords | preview |
|---:|---:|---:|---|---|---|---|---|
| 1 | 0.6904 | 0.4485 | alarm_manual.md | 5.2 문서 기준 확인 항목 | CHUNK-0027 |  | 이 키워드는 1일차 단순 문서 검색 실습과 2일차 RAG 검색 실습에서 사용할 수 있습니다. |
| 2 | 0.6111 | 0.6363 | alarm_manual.md | 3.2 알람 의미 | CHUNK-0011 |  | AI Agent는 이 알람을 해석할 때 다음 정보를 함께 확인할 수 있습니다. |
| 3 | 0.6111 | 0.6363 | alarm_manual.md | 11. Agent 답변 예시 | CHUNK-0070 |  | 아래 예시는 교육용 문서 검색과 RAG 실습에서 사용할 수 있는 답변 형식입니다. |

### Q004

- user_query: ALM-TEMP-402 반복 알람이 품질 지표와 관련될 가능성이 있는지 검토해 주세요.
- intent: 품질 영향 가능성 확인
- difficulty: intermediate
- expected_keywords: ALM-TEMP-402, 품질 지표, 품질 영향, 반복 알람, 검사 결과
- expected_docs: troubleshooting_guide.md, quality_standard.md

| rank | score | distance | doc_name | section_title | chunk_id | keywords | preview |
|---:|---:|---:|---|---|---|---|---|
| 1 | 0.0817 | 11.2451 | troubleshooting_guide.md | 10. 조치 방향 작성 기준 | CHUNK-0178 | ALM-TEMP-402, 반복 알람, 조치 방향 | ALM-TEMP-402 반복 알람에 대한 조치 방향은 실제 장비 제어 지시가 아니라 확인과 검토 중심으로 작성해야 합니다. 이 문서는 교육용 샘플 문서이므로 실제 현장 작업을 안내하지 않습니다. |
| 2 | 0.074 | 12.5213 | troubleshooting_guide.md | 7. 공정 상태 확인 관점 | CHUNK-0166 | ALM-TEMP-402, 설비, 증착 공정, 공정 상태, 제조 라인, 디스플레이 패널 제조 라인, 반복 알람 | 공정 상태 확인은 ALM-TEMP-402 반복 알람을 해석할 때 중요한 기준입니다. 디스플레이 패널 제조 라인의 증착 공정에서는 설비 상태와 공정 흐름이 함께 영향을 주고받을 수 있기 때문입니다. |
| 3 | 0.0629 | 14.8924 | troubleshooting_guide.md | 8. 품질 영향 확인 관점 | CHUNK-0172 | ALM-TEMP-402, 불량률, 품질 영향 | 품질 영향 확인에서 중요한 점은 직접 원인으로 단정하지 않는 것입니다. 불량률 변화가 보이더라도 “ALM-TEMP-402 때문에 불량이 발생했습니다”라고 표현하지 않아야 합니다. |

### Q005

- user_query: EQP-EV-03에서 온도 상승 알람이 반복될 때 불량률, 수율, 검사 결과를 함께 확인해야 하는 이유는 무엇인가요?
- intent: 품질 지표 확인 이유 설명
- difficulty: intermediate
- expected_keywords: EQP-EV-03, 불량률, 수율, 검사 결과, 품질 지표, 온도 상승
- expected_docs: quality_standard.md, troubleshooting_guide.md

| rank | score | distance | doc_name | section_title | chunk_id | keywords | preview |
|---:|---:|---:|---|---|---|---|---|
| 1 | 0.0234 | 41.6903 | troubleshooting_guide.md | 3. ALM-TEMP-402 온도 상승 반복 알람 개요 | CHUNK-0151 | 검사 결과 변화, 품질 지표, 불량률, 수율, 검사 결과, 추가 검토 | ALM-TEMP-402는 품질 지표와 연관될 가능성이 있습니다. 그러나 불량률, 수율, 검사 결과 변화가 함께 확인되더라도 알람이 직접 원인이라고 단정하지 말고, 관련 가능성과 추가 검토 필요로 표현해야 합니다. |
| 2 | 0.0211 | 46.3515 | quality_standard.md | 11. AI Agent 답변 시 품질 관련 주의사항 | CHUNK-0121 | 불량률, 수율, 검사 결과, 품질 영향 | ALM-TEMP-402와 불량률, 수율, 검사 결과가 함께 언급되더라도 직접 인과관계를 단정하면 안 됩니다. AI Agent는 “품질 영향 가능성이 있으므로 추가 확인이 필요합니다”와 같이 신중하게 표현해야 합니다. |
| 3 | 0.021 | 46.521 | quality_standard.md | 3. 설비 알람과 품질 지표의 관계 | CHUNK-0090 | 온도 상승, 반복 알람, 검사 결과 변화, 불량률, 수율, 검사 결과, 품질 영향, 품질 영향 여부 확인 | ALM-TEMP-402와 같은 온도 상승 반복 알람은 불량률, 수율, 검사 결과 변화와 관련 가능성이 있을 수 있습니다. 그러나 관련 가능성은 원인 확정이 아니며, 품질 영향 여부 확인을 위한 출발점으로 이해해야 합니다. |

### Q006

- user_query: ALM-TEMP-402 발생 전후로 최근 정비 이력과 설정 변경 여부를 확인해야 하는 이유를 설명해 주세요.
- intent: 정비 이력 확인 필요성 설명
- difficulty: intermediate
- expected_keywords: ALM-TEMP-402, 정비 이력, 설정 변경, 반복 알람, 확인 필요
- expected_docs: alarm_manual.md, troubleshooting_guide.md, quality_standard.md

| rank | score | distance | doc_name | section_title | chunk_id | keywords | preview |
|---:|---:|---:|---|---|---|---|---|
| 1 | 0.1718 | 4.8212 | troubleshooting_guide.md | 10. 조치 방향 작성 기준 | CHUNK-0178 | ALM-TEMP-402, 반복 알람, 조치 방향 | ALM-TEMP-402 반복 알람에 대한 조치 방향은 실제 장비 제어 지시가 아니라 확인과 검토 중심으로 작성해야 합니다. 이 문서는 교육용 샘플 문서이므로 실제 현장 작업을 안내하지 않습니다. |
| 2 | 0.1314 | 6.6079 | troubleshooting_guide.md | 7. 공정 상태 확인 관점 | CHUNK-0166 | ALM-TEMP-402, 설비, 증착 공정, 공정 상태, 제조 라인, 디스플레이 패널 제조 라인, 반복 알람 | 공정 상태 확인은 ALM-TEMP-402 반복 알람을 해석할 때 중요한 기준입니다. 디스플레이 패널 제조 라인의 증착 공정에서는 설비 상태와 공정 흐름이 함께 영향을 주고받을 수 있기 때문입니다. |
| 3 | 0.0918 | 9.8925 | troubleshooting_guide.md | 8. 품질 영향 확인 관점 | CHUNK-0172 | ALM-TEMP-402, 불량률, 품질 영향 | 품질 영향 확인에서 중요한 점은 직접 원인으로 단정하지 않는 것입니다. 불량률 변화가 보이더라도 “ALM-TEMP-402 때문에 불량이 발생했습니다”라고 표현하지 않아야 합니다. |

### Q007

- user_query: 검색된 문서 근거가 부족할 때 AI Agent는 EQP-EV-03의 ALM-TEMP-402 원인에 대해 어떻게 답변해야 하나요?
- intent: 근거 부족 시 답변 방식 확인
- difficulty: advanced
- expected_keywords: AI Agent, 근거 부족, EQP-EV-03, ALM-TEMP-402, 원인 후보, 추가 확인
- expected_docs: troubleshooting_guide.md, quality_standard.md

| rank | score | distance | doc_name | section_title | chunk_id | keywords | preview |
|---:|---:|---:|---|---|---|---|---|
| 1 | 0.0255 | 38.2675 | troubleshooting_guide.md | 8. 품질 영향 확인 관점 | CHUNK-0172 | ALM-TEMP-402, 불량률, 품질 영향 | 품질 영향 확인에서 중요한 점은 직접 원인으로 단정하지 않는 것입니다. 불량률 변화가 보이더라도 “ALM-TEMP-402 때문에 불량이 발생했습니다”라고 표현하지 않아야 합니다. |
| 2 | 0.025 | 38.9688 | quality_standard.md | 2. 품질 지표 확인 기본 원칙 | CHUNK-0085 | ALM-TEMP-402, 반복 알람, 품질 지표, 불량률 | 품질 지표를 확인할 때는 단일 지표만으로 원인을 판단하지 않아야 합니다. 예를 들어 불량률 변화가 관찰되더라도 그 원인이 ALM-TEMP-402 반복 알람 때문이라고 바로 단정할 수 없습니다. |
| 3 | 0.023 | 42.5142 | quality_standard.md | 6. 불량률 확인 관점 | CHUNK-0100 | ALM-TEMP-402, 반복 알람, 품질 지표, 불량률, 품질 영향 | 불량률은 제조 품질 상태를 이해하는 대표적인 품질 지표 중 하나입니다. ALM-TEMP-402 반복 알람이 발생한 전후 구간에서 불량률 변화가 있었는지 확인하면 품질 영향 가능성을 검토하는 데 도움이 됩니다. |

### Q008

- user_query: EQP-EV-03의 ALM-TEMP-402 반복 알람에 대해 공정 상태, 품질 지표, 정비 이력을 종합해서 추가 확인 항목을 정리해 주세요.
- intent: 종합 추가 확인 항목 정리
- difficulty: advanced
- expected_keywords: EQP-EV-03, ALM-TEMP-402, 공정 상태, 품질 지표, 정비 이력, 추가 확인 항목
- expected_docs: alarm_manual.md, troubleshooting_guide.md, quality_standard.md

| rank | score | distance | doc_name | section_title | chunk_id | keywords | preview |
|---:|---:|---:|---|---|---|---|---|
| 1 | 0.2141 | 3.6697 | troubleshooting_guide.md | 4. EQP-EV-03 설비 상황 예시 | CHUNK-0153 | ALM-TEMP-402, 온도 상승, 냉각 상태 | EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생하는 상황을 가정합니다. 이때 주요 증상은 온도 상승 흐름이 반복적으로 관찰되고, 일부 구간에서 냉각 상태가 안정적으로 유지되지 않는 것처럼 보이는 상황입니다. |
| 2 | 0.1747 | 4.7251 | troubleshooting_guide.md | 4. EQP-EV-03 설비 상황 예시 | CHUNK-0155 | ALM-TEMP-402, 반복 알람, 품질 지표, 불량률, 수율, 검사 결과, 확인 필요 | EQP-EV-03의 ALM-TEMP-402 반복 알람은 품질 지표와 함께 확인해야 합니다. 불량률, 수율, 검사 결과가 평소와 다른 흐름을 보였는지 확인 필요하지만, 품질 변화의 직접 원인을 알람 하나로 단정해서는 안 됩니다. |
| 3 | 0.1444 | 5.9259 | troubleshooting_guide.md | 10. 조치 방향 작성 기준 | CHUNK-0180 | ALM-TEMP-402, 온도 상승, 냉각 상태, 공정 부하, 센서 값 변동, 품질 지표, 점검 필요, 조치 방향, 정비 이력 | EQP-EV-03의 ALM-TEMP-402 상황에서 제시할 수 있는 조치 방향은 온도 상승 추세 확인, 냉각 상태 점검 필요, 공정 부하 증가 여부 확인, 센서 값 변동 가능성 검토, 품질 지표 변화 확인, 정비 이력 확인입니다. |


## 3. 검색 결과 해석

- Top-3는 정답 3개가 아니라 "답변 전 검토할 근거 후보 집합"입니다.
- `score`는 후보를 가늠하는 참고값일 뿐 단독 판단 기준이 아닙니다.
  실제 근거 적합성은 `doc_name`, `chunk_id`, `section_title`, `preview`(또는 `text`)를
  함께 확인해 사람이 판단해야 합니다.
- 검색 결과가 좋은 경우에는 질문의 핵심 키워드와 관련 문서 chunk의 `keywords`, `section_title`, `preview`가 자연스럽게 연결됩니다.
- 검색 결과가 부족한 경우에는 문서 chunk가 충분히 만들어졌는지, 질문에 핵심 키워드가 포함되어 있는지 확인 필요합니다.

## 4. 환경 확인 명령 (선택/확장 실습용)

Chroma Vector DB와 Ollama는 선택/확장 실습 구성입니다. 아직 준비되지 않았다면
먼저 `chroma_index_builder.py`를 실행해 Chroma DB를 생성하고, 아래 명령으로
Ollama와 `nomic-embed-text:latest` 모델 상태를 확인합니다.

Chroma/Ollama 실행이 지연되거나 어려우면, 이미 저장된 본 검색 품질 검토 자료
(`outputs/day2/rag_test_results.md`)로 진행하는 Saved Result Review로 대체할 수 있습니다.

```powershell
ollama list
ollama pull nomic-embed-text
ollama serve
```
