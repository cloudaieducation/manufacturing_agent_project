# Day2 RAG Agent v1 실행 결과


## 1. 실행 개요

- Day2 RAG Agent v1은 제조 기술 문서 참조형 RAG Agent입니다.
- 이 파일은 검색 모듈(`rag_search`)과 Graph 실행 모듈(`langgraph_rag_graph_runner`)을
  호출해, RAG Agent v1의 최종 State와 근거 기반 답변 결과를 정리하는 통합 실행 파일입니다.
- Agent 처리 흐름은 실제 LangGraph StateGraph를 사용합니다.
- 실제 사내 데이터가 아닌 교육용 샘플 문서를 사용합니다.
- 결과를 볼 때는 답변 문장이 매끄러운지보다, 어떤 문서 근거(retrieved_docs)를 사용했고
  그 흐름이 State와 Trace에 제대로 남았는지를 확인하는 것이 중요합니다.
- 이 파일은 검색 로직이나 LangGraph Node를 직접 구현하지 않고, `run_langgraph_rag()` 실행 결과를 리포트로 정리합니다.

## 2. 사용자 질문

- user_query: EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘

## 3. Agent 처리 흐름 요약

1. 사용자 질문 분석
2. 설비 ID와 알람 코드 추출 (검색·Tool 호출 조건)
3. 관련 문서 Top-3 근거 후보 검색
4. 검색 결과를 LangGraph State의 `retrieved_docs`에 저장 (답변·grounding 검증의 핵심 입력)
5. 근거 기반 답변 초안 생성
6. grounding 검증 (근거 부족 시 조건부 분기로 질의 재작성)
7. 최종 답변 생성

## 4. 추출된 핵심 정보

- equipment_id: EQP-EV-03
- alarm_code: ALM-TEMP-402
- rewritten_query: 
- grounding_status: PASS
- retry_count: 0
- errors: 없음

## 5. 검색된 근거 문서 Top-3

Top-3는 정답 3개가 아니라 답변 전 검토할 근거 후보 집합입니다.
`score`는 참고값이며 단독 판단 기준이 아니므로, `doc_name`, `chunk_id`, `section_title`,
`preview`를 함께 확인해 근거 적합성을 판단합니다.

| rank | score | distance | doc_name | section_title | chunk_id | keywords | preview |
|---:|---:|---:|---|---|---|---|---|
| 1 | 0.0732 | 12.6588 | alarm_manual.md | 4.2 같은 챔버에서 반복 발생 | CHUNK-0016 | ALM-TEMP-402 | 같은 챔버에서 `ALM-TEMP-402`가 여러 번 발생했다면 단순 일회성 알람이 아니라 반복 발생 패턴으로 볼 수 있습니다. |
| 2 | 0.0668 | 13.9614 | alarm_manual.md | 3.2 알람 의미 | CHUNK-0009 | ALM-TEMP-402, 증착 공정 | `ALM-TEMP-402`는 교육용 가상 시나리오에서 박막 증착 공정 중 특정 챔버의 온도 값이 교육용 기준 범위에서 벗어난 상황을 나타내는 알람입니다. |
| 3 | 0.057 | 16.5526 | alarm_manual.md | 11.2 리포트형 답변 예시 | CHUNK-0075 | 설비, 품질 영향 | - 동일 설비 반복 여부 - 동일 챔버 집중 여부 - 심각도 변화 - 현장 메모 - 주변 시간대의 관련 교육용 알람 - 품질 영향 가능성 |

## 6. 최종 답변 초안

## 1. 질의 요약
사용자는 교육용 가상 시나리오에서 EQP-EV-03 설비의 ALM-TEMP-402 알람이 반복 발생한 경우, 원인 후보와 품질에 미칠 수 있는 영향 확인 항목을 요청하였습니다.

## 2. 확인된 설비 ID와 알람 코드
- 설비 ID: EQP-EV-03
- 알람 코드: ALM-TEMP-402

## 3. 검색 근거 요약
검색된 근거 문서(`alarm_manual.md`)는 다음과 같은 정보를 제공합니다.
- **ALM-TEMP-402**는 교육용 가상 시나리오에서 박막 증착 공정 중 특정 챔버의 온도 값이 교육용 기준 범위에서 벗어난 상황을 나타내는 알람입니다.
- 같은 챔버에서 **ALM-TEMP-402**가 여러 번 발생하면 단순 일회성 알람이 아니라 **반복 발생 패턴**으로 볼 수 있습니다.
- 리포트 작성 시 확인해야 할 항목으로는 동일 설비/챔버 반복 여부, 심각도 변화, 현장 메모, 주변 관련 알람, **품질 영향 가능성** 등이 포함됩니다.

## 4. 원인 후보
근거 문서에 기반하여, ALM-TEMP-402가 반복 발생할 수 있는 원인 후보는 다음과 같습니다.
- **반복 발생 패턴 관련 원인 후보**: 동일 챔버에서 알람이 반복된다는 것은 일시적인 변동이 아닌, 지속적인 상태 이상 가능성을 시사할 수 있습니다. 이는 센서의 안정성 문제, 제어 루프의 지속적 편차, 또는 특정 공정 조건에서의 고유한 문제일 수 있습니다.
- **교육용 가상 시나리오 맥락**: 해당 알람은 교육 목적으로 설정된 기준 범위를 초과한 상황을 나타내므로, 원인은 교육 시나리오에서 정의한 특정 조건(예: 설정된 시뮬레이션 파라미터)과 연관될 수 있습니다.

## 5. 품질 영향 확인 항목
근거 문서의 리포트 예시를 참고하여, 반복 알람 발생 시 품질 영향 가능성을 확인하기 위한 항목은 다음과 같습니다.
- 동일 설비(EQP-EV-03) 및 동일 챔버에서의 반복 발생 빈도 및 패턴 확인
- 알람 발생 시점의 **심각도 변화** 추이 확인 (예: 경고 → 중대)
- 현장 작업자 또는 시스템에 기록된 **현장 메모** 확인
- 알람 발생 주변 시간대의 다른 **관련 교육용 알람** 발생 여부 확인
- 해당 챔버에서 생산된 최근 **교육용 가상 제품의 품질 데이터**와의 연관성 검토 가능성

## 6. 추가 확인 필요 사항
근거 문서의 권고사항을 바탕으로, 추가적으로 확인이 필요한 사항은 다음과 같습니다.
- ALM-TEMP-402 발생 시점의 정확한 **챔버 위치** 및 해당 챔버의 **교육용 가상 공정 조건** 확인
- 알람 발생 간격 및 **반복 횟수**에 대한 구체적인 데이터 확인
- 동일 교육용 시나리오 내에서 **다른 설비 또는 챔버**에서는 유사 알람이 발생하지 않는지 확인
- 알람 발생 전/후의 **교육용 가상 공정 파라미터 로그** (온도 설정값, 실제 측정값 등) 검토 필요

## 7. 주의 문구
본 답변은 제공된 교육용 샘플 문서(`alarm_manual.md`)의 정보만을 기반으로 하였습니다. 실제 제조 설비의 상태, 품질 기준, 또는 보안 절차를 대변하지 않습니다. 제시된 &quot;원인 후보&quot;와 &quot;확인 항목&quot;은 교육 목적의 가상 시나리오 해석을 위한 참고 자료이며, **실제 장애 판단 및 조치 결정은 반드시 담당자가 관련 데이터를 종합적으로 검토한 후 내려야 합니다.**

## 7. LangGraph State 요약

- State는 Node 사이에서 공유되는 업무 처리 문맥입니다.
- `retrieved_docs`는 답변 생성과 grounding 검증의 핵심 입력입니다.
- `grounding_status`는 답변이 검색 근거를 반영했는지 확인하는 상태입니다.
- `trace`는 Node 실행 순서와 State 변화를 확인하는 실행 검토 자료이며, 4일차 실행 품질 평가의 기반이 됩니다.
- Day2 RAG Agent v1은 이 State를 최종 리포트로 변환합니다.

## 8. Node 실행 Trace

| node_name | status | message | input_summary | output_summary |
|---|---|---|---|---|
| parse_query_node | success | 질문에서 설비 ID와 알람 코드를 추출했습니다. | EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘 | equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402 |
| retrieve_docs_node | success | RAG 검색을 수행했습니다. | EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘 | 1. alarm_manual.md / 4.2 같은 챔버에서 반복 발생 / score=0.0732 / 같은 챔버에서 `ALM-TEMP-402`가 여러 번 발생했다면 단순 일회성 알람이 아니라 반복 발생 패턴으로 볼 수 있습니다. 2. alarm_manual.md / 3.2 알람 의미 / score=0.0668 / `ALM-TEMP-402`는 교육용 가상 시나리오에서 박막 증착 공정 중 특정 챔버의 온도 값이 교육용 기준 범위에서 벗어난 상황을 나타내는 알람입니다. 3. alarm_manual.md / 11.2 리포트형 답변 예시 / score=0.057 / - 동일 설비 반복 여부 - 동일 챔버 집중 여부 - 심각도 변화 - 현장 메모 - 주변 시간대의 관련 교육용 알람 - 품질 영향 가능성 |
| generate_answer_node | success | llm_client.py를 통해 답변을 생성했습니다. | retrieved_docs=3건 | answer_source=llm_client |
| verify_grounding_node | success | 검색 근거가 있어 grounding_status를 PASS로 설정했습니다. | retrieved_docs=3건, retry_count=0 | grounding_status=PASS, needs_rewrite=False, retry_count=0 |

## 9. 2일차 공식 실습 항목 대응

- [x] Markdown 문서 로드
- [x] 검색 가능한 지식 단위(chunk) 생성
- [x] metadata 생성
- [x] RAG 검색 결과 확인
- [x] Top-3 근거 후보 검토
- [x] LangGraph State 관리 (Node 간 공유 업무 처리 문맥)
- [x] Node 기반 처리 흐름
- [x] 조건부 분기 (근거 없는 답변 방지)
- [x] 근거 문서 기반 답변 생성
- [ ] 선택/확장: Chroma Vector DB 저장 및 검색

## 10. 3일차 연결 안내

- 이 `day2_rag_agent_v1_result.md`는 RAG 검색이 한 파일 안에 묶여 있던 시점의 기준 결과,
  즉 3일차 `search_manual` Tool 분리 전 기준 결과입니다.
- 3일차에는 오늘 만든 RAG 검색 기능이 `search_manual` MCP Tool로 분리되어 외부에서 호출됩니다.
- 이후 PostgreSQL 제조 DB/Log Tool과 함께 MCP 방식으로 호출됩니다.
- Day2 RAG Agent v1은 Day3 MCP Tool-Using Agent v2의 문서 검색 기반이 됩니다.
