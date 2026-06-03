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
교육용 시나리오에서 EQP-EV-03 설비의 ALM-TEMP-402 알람이 반복 발생한 경우의 원인 후보와 품질 영향 확인 항목에 대해 질의하였습니다.

## 2. 확인된 설비 ID와 알람 코드
- 설비 ID: EQP-EV-03
- 알람 코드: ALM-TEMP-402

## 3. 검색 근거 요약
검색된 근거 문서(`alarm_manual.md`)에서 다음 내용을 확인하였습니다.
- **섹션 4.2**: 동일 챔버에서 `ALM-TEMP-402`가 여러 번 발생하면 단순 일회성이 아닌 반복 발생 패턴으로 볼 수 있습니다.
- **섹션 3.2**: `ALM-TEMP-402`는 교육용 가상 시나리오에서 박막 증착 공정 중 특정 챔버의 온도 값이 교육용 기준 범위를 벗어난 상황을 나타냅니다.
- **섹션 11.2**: 리포트 작성 시 확인할 항목으로 동일 설비/챔버 반복 여부, 심각도 변화, 현장 메모, 주변 알람, 품질 영향 가능성 등이 포함됩니다.

## 4. 원인 후보
근거 문서에 기반하여, `ALM-TEMP-402` 반복 발생의 원인 후보는 다음과 같이 추정됩니다.
- **동일 챔버의 온도 제어 불안정**: 교육용 기준 범위 내 온도 유지가 어려운 상태가 지속되고 있을 가능성이 있습니다.
- **센서 또는 측정 시스템 오차**: 온도 측정 값에 대한 반복적인 오차가 발생하고 있을 가능성이 있습니다.
- **주변 공정 조건 변화**: 증착 공정 중 다른 변수(예: 가스 유량, 압력) 변화가 온도에 반복적으로 영향을 미칠 가능성이 있습니다.

## 5. 품질 영향 확인 항목
근거 문서의 리포트 항목을 참고하여, 품질 영향 가능성을 확인하기 위한 항목은 다음과 같습니다.
- 동일 챔버에서의 알람 반복 빈도 및 패턴 확인
- 알람 발생 시점의 심각도(Severity) 변화 여부 확인
- 해당 챔버에서 생산된 최근 교육용 시료의 품질 데이터(두께 균일성, 결함률 등) 비교
- 알람 발생 시간대 주변의 다른 교육용 알람(예: 압력, 가스 관련) 동시 발생 여부
- 현장 작업자의 메모나 관찰 기록 확인

## 6. 추가 확인 필요 사항
- 알람 발생 시점의 구체적인 온도 값과 교육용 기준 범위 대비 편차 정도
- 동일 설비(EQP-EV-03) 내 다른 챔버에서는 유사 알람이 발생하지 않는지 확인
- 최근 해당 챔버의 유지보수 또는 설정 변경 이력 확인
- 알람 발생 간격이 규칙적인지 불규칙한지 패턴 분석

## 7. 주의 문구
본 답변은 제공된 교육용 샘플 문서(`alarm_manual.md`)의 근거만을 기반으로 작성되었습니다. 실제 제조 라인에서의 원인 분석과 품질 영향 평가는 담당자가 현장 데이터와 전체 공정 맥락을 종합적으로 검토하여 판단해야 합니다.

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
