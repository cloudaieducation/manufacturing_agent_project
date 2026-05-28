# Day2 Chunk 생성 결과 (검색 가능한 지식 단위 설계)

이 문서는 RAG Agent v1이 참조할 제조 기술 문서를 "검색 가능한 지식 단위(chunk)"로
나눈 결과를 검토하기 위한 요약 자료입니다. chunk는 단순한 작은 조각이 아니라,
RAG 검색이 답변 근거를 문단 단위로 찾고 추적할 수 있게 만드는 설계 단위입니다.

## 1. 생성 요약

- 읽은 문서 수: 3
- 생성된 chunk 수: 201
- chunk preview JSON 경로: `C:\work\manufacturing_agent_project\outputs\day2\chunk_preview.json`
- 위 `chunk_preview.json`은 이후 RAG 검색 로직이 그대로 재사용하는 구조화된 chunk 데이터입니다.

## 2. 문서별 chunk 수

| 문서명 | chunk 수 |
|---|---:|
| alarm_manual.md | 78 |
| quality_standard.md | 60 |
| troubleshooting_guide.md | 63 |

## 3. metadata 추출 예시

각 chunk의 `chunk_id`와 `doc_name`은 검색 결과와 Trace에서 "이 답변이 어느 문서
어느 조각에 근거했는지"를 되짚기 위한 근거 위치 추적 기준입니다.
`alarm_code`, `equipment_id`, `keywords` 등의 metadata는 검색·필터링에 쓰이며,
3일차 search_manual MCP Tool의 입력값 설계로 그대로 이어집니다.

### CHUNK-0001

- chunk_id: CHUNK-0001
- doc_name: alarm_manual.md
- section_title: DisplayEdu Fab 교육용 가상 알람 매뉴얼
- alarm_code: 
- equipment_id: 
- keywords: 설비
- text 미리보기: &gt; 본 문서는 AI Agent 교육을 위한 가상 알람 매뉴얼입니다. 실제 기업의 설비, 공정, 알람 기준, 조치 절차와 무관합니다.

### CHUNK-0002

- chunk_id: CHUNK-0002
- doc_name: alarm_manual.md
- section_title: 1. 문서 목적
- alarm_code: 
- equipment_id: 
- keywords: 
- text 미리보기: 이 문서는 삼성디스플레이 재직자 대상 AI Agent Architecture 강의에서 사용할 **교육용 가상 알람 매뉴얼**입니다.

### CHUNK-0003

- chunk_id: CHUNK-0003
- doc_name: alarm_manual.md
- section_title: 1. 문서 목적
- alarm_code: 
- equipment_id: 
- keywords: 
- text 미리보기: 수강생은 이 문서를 통해 AI Agent가 알람 로그만 보고 임의로 답변하지 않고, 문서 근거를 참고하여 다음 내용을 정리하는 흐름을 실습할 수 있습니다.

### CHUNK-0004

- chunk_id: CHUNK-0004
- doc_name: alarm_manual.md
- section_title: 1. 문서 목적
- alarm_code: 
- equipment_id: 
- keywords: 설비, 품질 영향, 확인 필요, 조치 방향, 원인 후보
- text 미리보기: - 알람 코드의 의미 확인 - 반복 발생 여부 판단 - 관련 설비와 챔버 확인 - 원인 후보 정리 - 1차 확인 항목 도출 - 권장 조치 방향 정리 - 품질 영향 가능성 설명 - 추가 확인 필요 사항 제시

### CHUNK-0005

- chunk_id: CHUNK-0005
- doc_name: alarm_manual.md
- section_title: 1. 문서 목적
- alarm_code: 
- equipment_id: 
- keywords: 설비
- text 미리보기: 이 문서의 모든 설비, 라인, 알람 코드, 수치, 판단 기준은 교육용 가상 예시입니다.


## 4. 다음 단계 안내

다음 단계에서는 이 chunk 결과를 기반으로 RAG 검색을 수행합니다.
기본 강의에서는 검색 결과가 답변 근거(retrieved_docs)로 어떻게 사용되는지 확인하는 것이 목표입니다.

Chroma Vector DB 저장(`chroma_index_builder_날짜_시간.py`)은 선택/확장 실습입니다.
Chroma/Ollama 환경이 준비되지 않아도, 미리 저장해 둔 검색 결과로 진행하는
Saved Result Review가 가능합니다.

입력 파일:

`outputs/day2/chunk_preview.json`

선택/확장 실행 명령어:

```bash
python src/day2/chroma_index_builder_날짜_시간.py
```
