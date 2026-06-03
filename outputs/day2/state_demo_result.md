# Day2 LangGraph State 구조 데모

## 1. State 역할 요약

- State는 개인 작업 노트가 아니라, Node 사이에서 공유되는 업무 처리 문맥입니다.
  각 Node는 같은 State를 읽고 자신의 결과를 채워 다음 Node로 넘깁니다.
- retrieved_docs는 RAG 검색 근거 후보가 담기는 자리이며, 답변 생성과
  grounding 검증의 핵심 입력입니다.
- trace는 Node 실행 순서와 State 변화를 확인하는 실행 검토 자료이자 품질 평가·디버깅 근거입니다.
- graph_state.py는 State 구조를 정의할 뿐, 검색이나 LangGraph 실행은 직접 수행하지 않습니다.
- 이 State 구조는 3일차 Multi-Agent Handoff State(에이전트 간 작업 인계 상태)로 확장될 수 있습니다.

## 2. 현재 State 요약

- user_query: EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘
- rewritten_query: 
- equipment_id: EQP-EV-03
- alarm_code: ALM-TEMP-402
- grounding_status: grounded
- needs_rewrite: False
- retry_count: 0
- errors: 없음

## 3. Retrieved Docs 예시

### Retrieved Doc 1

- rank: 1
- score: 0.8123
- doc_name: troubleshooting_guide.md
- section_title: ALM-TEMP-402 온도 상승 반복 알람 개요
- chunk_id: CHUNK-0007
- keywords: ALM-TEMP-402, EQP-EV-03, 온도 상승, 반복 알람, 원인 후보
- preview: ALM-TEMP-402 반복 알람은 온도 상승, 냉각 상태, 공정 부하, 센서 값 변동 가능성을 함께 확인해야 합니다.

### Retrieved Doc 2

- rank: 2
- score: 0.7642
- doc_name: quality_standard.md
- section_title: 품질 영향 확인 관점
- chunk_id: CHUNK-0015
- keywords: 품질 지표, 불량률, 수율, 검사 결과, 품질 영향
- preview: 반복 알람 발생 전후의 품질 지표, 불량률, 수율, 검사 결과 변화를 함께 확인해야 합니다.


## 4. Trace 예시

### create_initial_state

- node_name: create_initial_state
- status: success
- message: 사용자 질문으로 초기 State를 생성했습니다.
- input_summary: EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘
- output_summary: user_query가 State에 저장되었습니다.

### parse_query_node

- node_name: parse_query_node
- status: success
- message: 질문에서 설비 ID와 알람 코드를 추출한 예시입니다.
- input_summary: EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘
- output_summary: equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402

### retrieve_docs_node

- node_name: retrieve_docs_node
- status: success
- message: Chroma Vector DB 검색 결과가 retrieved_docs에 저장된 예시입니다.
- input_summary: search_top_k(user_query, top_k=3)
- output_summary: 1. troubleshooting_guide.md / ALM-TEMP-402 온도 상승 반복 알람 개요 / score=0.8123 / ALM-TEMP-402 반복 알람은 온도 상승, 냉각 상태, 공정 부하, 센서 값 변동 가능성을 함께 확인해야 합니다.
2. quality_standard.md / 품질 영향 확인 관점 / score=0.7642 / 반복 알람 발생 전후의 품질 지표, 불량률, 수율, 검사 결과 변화를 함께 확인해야 합니다.

### generate_answer_node

- node_name: generate_answer_node
- status: success
- message: 검색 근거를 바탕으로 답변 초안을 생성한 예시입니다.
- input_summary: retrieved_docs 2건
- output_summary: 원인 후보와 품질 영향 확인 항목을 포함한 답변 초안 생성

### verify_grounding_node

- node_name: verify_grounding_node
- status: success
- message: 답변에 사용할 검색 근거가 존재한다고 판단한 예시입니다.
- input_summary: draft_answer와 retrieved_docs
- output_summary: grounding_status=grounded, needs_rewrite=False


## 5. 다음 단계 안내

다음 단계에서는 `langgraph_rag_graph_runner.py`에서 실제 LangGraph StateGraph를 구성합니다.

`retrieve_docs_node`가 `rag_search.py`의 `search_top_k()`를 호출해 검색 결과를
State의 `retrieved_docs` 필드에 저장하면, 이 값이 답변 생성과 grounding 검증으로 이어집니다.

이 State 데모 실행 명령어:

```powershell
python src/day2/graph_state.py
```
