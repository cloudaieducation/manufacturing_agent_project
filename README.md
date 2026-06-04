# 제조 AI Agent Architecture 과정

## 1. 과정 개요

본 프로젝트는 **제조 AI Agent Architecture 과정**의 실습 코드와 교육 자료를 정리한 저장소입니다.

교육의 핵심 목표는 제조 도메인에서 AI Agent를 설계하고 구현할 때 필요한 주요 구성 요소를 단계적으로 이해하는 것입니다.

주요 학습 내용은 다음과 같습니다.

- LLM 호출 구조
- Prompt Chain
- LangGraph 기반 Agent 흐름
- RAG 검색 구조
- PostgreSQL 기반 제조 데이터 조회
- MCP Server / MCP Client 구조
- Tool Selection
- RAG 품질 평가
- Text-to-SQL Safety
- Multi-Agent 구조
- 제조 업무 Tool 연동 및 검증

본 저장소는 단순히 코드를 실행하는 것을 목표로 하지 않고, **제조 도메인 AI Agent Architecture를 설계 관점에서 이해하는 것**을 목표로 합니다.

---

## 2. 교육 구성

| Day | 주요 주제 | 핵심 내용 |
|---|---|---|
| Day1 | LLM 기초와 Agent v0 | LLM 단일 호출, Prompt Chain, mini LangGraph, Agent v0, Streamlit UI |
| Day2 | RAG 구조 | 문서 로딩, Chunk 생성, Chroma Index, RAG 검색, LangGraph RAG, RAG Agent |
| Day3 | DB Tool과 MCP 기초 | PostgreSQL, DB Tool, RAG Tool, MCP Server/Client, Multi-Agent |
| Day4 | Agent 품질 검증 | Tool Selection, RAG Quality, Text-to-SQL Safety, Quality Gate |
| Day5 | MCP Server/Client 심화 | MCP Server 단계 확장, MCP Client 단계 확장, 최종 통합 UI |

---

## 3. 프로젝트 폴더 구조

```text
manufacturing_agent_project/
├─ src/                 # Day1~Day5 실습 코드
├─ docs/                # RAG 입력 문서 및 참고 문서
├─ data/                # 실습 입력 데이터 및 평가 케이스
├─ db/                  # PostgreSQL Docker Compose 및 초기화 SQL
├─ templates/           # Day별 프롬프트/리포트 Mustache 템플릿
├─ prompt/              # Claude Code/TDD 실습 보조 프롬프트
├─ lecture_materials/   # Day별 강의자료(PPTX/PDF/drawio/png)
├─ notebook_instructor/ # 강사용 노트북 자료
├─ outputs/             # 실행 결과 산출물
└─ vector_db/           # Chroma Vector DB 저장 위치
```

### 주요 폴더 설명

| 폴더 | 설명 |
|---|---|
| `src/` | Day1~Day5의 핵심 실습 코드가 들어 있습니다. |
| `docs/` | RAG 검색에 사용되는 매뉴얼, 장애 대응 가이드, 품질 기준 문서가 포함됩니다. |
| `data/` | 실습 입력 데이터, RAG 평가 케이스, Tool Selection 평가 케이스 등이 포함됩니다. |
| `db/` | 제조 도메인 PostgreSQL 실습을 위한 Docker Compose와 SQL 파일이 포함됩니다. |
| `templates/` | 코드 실행 시 사용되는 Day별 템플릿이 포함됩니다. |
| `prompt/` | Claude Code 또는 TDD 실습에 참고할 수 있는 보조 프롬프트가 포함됩니다. |
| `lecture_materials/` | Day별 강의자료가 포함됩니다. |
| `notebook_instructor/` | 강사용 노트북 자료가 포함됩니다. |
| `outputs/` | 실습 실행 결과가 저장되는 폴더입니다. |
| `vector_db/` | Chroma 기반 Vector DB가 저장되는 폴더입니다. |

---

## 4. Day1: LLM 기초와 Agent v0

Day1은 LLM 호출 구조를 가장 작은 단위부터 시작하여 Agent 형태로 확장하는 과정입니다.

교육 흐름은 다음과 같습니다.

```text
LLM 단일 호출
→ Prompt Chain
→ mini LangGraph
→ Agent v0
→ Streamlit UI
```

| 순서 | 파일 | 설명 | 실행 명령 |
|---:|---|---|---|
| 1 | `src/day1/first_sample_run.py` | 샘플 질의, 알람 로그, 매뉴얼을 읽어 LLM 호출 결과를 생성합니다. | `uv run python src/day1/first_sample_run.py` |
| 2 | `src/day1/simple_chain_starter.py` | Prompt와 Result 템플릿을 분리한 Chain 구조를 실습합니다. | `uv run python src/day1/simple_chain_starter.py` |
| 3 | `src/day1/mini_graph_runner.py` | State, Node, Edge, 조건부 분기를 갖춘 mini LangGraph 흐름을 실습합니다. | `uv run python src/day1/mini_graph_runner.py` |
| 4 | `src/day1/day1_agent_v0_template.py` | Prompt, Chain, Graph, LLM 호출을 통합한 Agent v0 구조를 실습합니다. | `uv run python src/day1/day1_agent_v0_template.py` |
| 5 | `src/day1/*_streamlit_app.py` | 각 CLI 실습 흐름을 브라우저에서 확인합니다. | `uv run streamlit run src/day1/day1_agent_v0_streamlit_app.py` |

Day1에서 사용하는 주요 입력 자료는 `data/sample_query.json`, `data/sample_alarm_logs.csv`, `docs/alarm_manual.md`, `templates/day1/`입니다.

---

## 5. Day2: RAG 검색 구조

Day2는 제조 매뉴얼 문서를 기반으로 RAG 검색 구조를 구현하는 과정입니다.

교육 흐름은 다음과 같습니다.

```text
문서 로딩
→ Chunk 생성
→ Chroma Index 생성
→ RAG 검색
→ LangGraph RAG
→ RAG Agent
→ Streamlit UI
```

| 순서 | 파일 | 설명 | 실행 명령 |
|---:|---|---|---|
| 1 | `src/day2/rag_document_loader.py` | RAG 대상 문서를 로딩합니다. | `uv run python src/day2/rag_document_loader.py` |
| 2 | `src/day2/chunk_builder.py` | 문서를 검색 단위 Chunk로 분할합니다. | `uv run python src/day2/chunk_builder.py` |
| 3 | `src/day2/chroma_index_builder.py` | Chunk를 임베딩하여 Chroma Vector DB에 저장합니다. | `uv run python src/day2/chroma_index_builder.py` |
| 4 | `src/day2/rag_search.py` | 질문과 가까운 Top-K 문서 Chunk를 검색합니다. | `uv run python src/day2/rag_search.py` |
| 5 | `src/day2/langgraph_rag_graph_runner.py` | LangGraph 기반 RAG 흐름을 실행합니다. | `uv run python src/day2/langgraph_rag_graph_runner.py` |
| 6 | `src/day2/day2_rag_agent_v1.py` | RAG 검색과 Agent 답변 생성을 통합합니다. | `uv run python src/day2/day2_rag_agent_v1.py` |
| 7 | `src/day2/day2_rag_agent_streamlit_app.py` | RAG Agent 결과를 UI로 확인합니다. | `uv run streamlit run src/day2/day2_rag_agent_streamlit_app.py` |

Day2에서 사용하는 RAG 입력 문서는 다음 3개입니다.

| 문서 | 설명 |
|---|---|
| `docs/alarm_manual.md` | 제조 알람 매뉴얼 |
| `docs/troubleshooting_guide.md` | 장애 대응 가이드 |
| `docs/quality_standard.md` | 품질 기준 문서 |

---

## 6. Day3: DB Tool과 MCP 기초

Day3은 제조 데이터를 PostgreSQL에 저장하고, 이를 Agent Tool 및 MCP 구조로 연결하는 과정입니다.

교육 흐름은 다음과 같습니다.

```text
PostgreSQL 기동
→ DB Tool
→ RAG Tool
→ MCP Server
→ MCP Client
→ Tool Agent
→ Multi-Agent
→ Streamlit UI
```

### Day3 DB 실습용 PostgreSQL 실행

```powershell
docker compose -f db/docker-compose.yml up -d
```

Docker 실행 환경에 따라 사전 확인이 필요할 수 있습니다.

### Day3 주요 실행 파일

| 순서 | 파일 | 설명 | 실행 명령 |
|---:|---|---|---|
| 1 | `src/day3/postgres_db_tool.py` | 제조 DB 조회 기능을 Tool로 제공합니다. | `uv run python src/day3/postgres_db_tool.py` |
| 2 | `src/day3/search_manual_tool.py` | RAG 검색을 `search_manual` Tool로 제공합니다. | `uv run python src/day3/search_manual_tool.py` |
| 3 | `src/day3/manufacturing_mcp_server.py` | DB/RAG Tool을 FastMCP 서버로 등록합니다. | `uv run python src/day3/manufacturing_mcp_server.py` |
| 4 | `src/day3/manufacturing_mcp_client.py` | MCP 서버 또는 fallback 경로로 Tool을 호출합니다. | `uv run python src/day3/manufacturing_mcp_client.py` |
| 5 | `src/day3/day3_mcp_tool_agent_v2.py` | MCP Tool 기반 Agent 실행 런처입니다. | `uv run python src/day3/day3_mcp_tool_agent_v2.py` |
| 6 | `src/day3/multi_agent_roles.py` | 역할 기반 Multi-Agent 흐름을 순차 실행합니다. | `uv run python src/day3/multi_agent_roles.py` |
| 7 | `src/day3/multi_agent_roles_graph.py` | LangGraph 기반 Multi-Agent 흐름을 실행합니다. | `uv run python src/day3/multi_agent_roles_graph.py` |
| 8 | `src/day3/day3_multi_agent_streamlit_app.py` | Multi-Agent 흐름을 UI로 확인합니다. | `uv run streamlit run src/day3/day3_multi_agent_streamlit_app.py` |
| 9 | `src/day3/mcp_tool_client_streamlit_app.py` | MCP/fallback Tool 호출 경로를 UI로 비교합니다. | `uv run streamlit run src/day3/mcp_tool_client_streamlit_app.py` |

---

## 7. Day4: Agent 품질 검증

Day4는 Agent가 Tool을 적절히 선택하고, RAG 결과가 충분한지 평가하며, SQL이 안전한지 검사하는 품질 검증 과정입니다.

Day4는 내부 모듈을 직접 실행하기보다 외부 runner/checker/evaluator 진입점을 기준으로 실행합니다.

| 영역 | 설명 | 실행 파일 | 실행 명령 |
|---|---|---|---|
| Tool Selection | LLM이 생성한 Tool Plan을 검증하고, 필요 시 Repair 후 재검증합니다. | `src/day4/langgraph_tool_selector_v2_runner.py` | `uv run python src/day4/langgraph_tool_selector_v2_runner.py` |
| RAG Quality | RAG 검색 결과를 재정렬, 채점, 판정합니다. | `src/day4/rag_quality_evaluator.py` | `uv run python src/day4/rag_quality_evaluator.py` |
| Text-to-SQL Safety | 생성된 SQL을 실행 전에 PASS/WARNING/BLOCK으로 검사합니다. | `src/day4/text_to_sql_safety_checker.py` | `uv run python src/day4/text_to_sql_safety_checker.py` |

Day4에서 사용하는 주요 입력 데이터는 다음과 같습니다.

| 파일 | 설명 |
|---|---|
| `data/tool_selection_test_cases.json` | Tool Selection 평가 케이스 |
| `data/day4_rag_evaluation_cases.json` | RAG 품질 평가 케이스 |
| `data/day4_text_to_sql_cases.json` | Text-to-SQL Safety 평가 케이스 |

---

## 8. Day5: MCP Server / Client 심화

Day5는 MCP Server와 MCP Client를 단계별로 확장하고, 최종적으로 DB와 RAG를 통합한 제조 AI Agent 구조를 구성하는 과정입니다.

### 8-1. MCP Server 단계

| 단계 | 패키지 | 설명 |
|---:|---|---|
| 1 | `src/day5/mcp_server01` | FastMCP 서버 기본 골격입니다. Tool 등록, 검증, 실행, 로깅 흐름을 다룹니다. |
| 2 | `src/day5/mcp_server02` | server01에 RAG 검색 기능을 확장한 서버입니다. |
| 3 | `src/day5/mcp_server03` | 제조 DB 접근 기능을 추가한 서버입니다. |
| 4 | `src/day5/mcp_server_final` | DB와 RAG를 통합한 최종 MCP 서버입니다. |

### 최종 MCP Server 실행

```powershell
$env:PYTHONPATH="src"
uv run python -m day5.mcp_server_final.mcp_server --transport streamable-http --host 127.0.0.1 --port 8003
```

최종 서버는 장기 실행되는 HTTP 서버로 먼저 기동하는 것을 권장합니다.  
RAG 초기화 비용을 줄이고, Client에서 안정적으로 Tool을 호출하기 위함입니다.

### 8-2. MCP Client 단계

| 단계 | 패키지 | 설명 |
|---:|---|---|
| 1 | `src/day5/mcp_client01` | direct mode 기반 기본 Client입니다. |
| 2 | `src/day5/mcp_client02` | LangGraph fan-out 구조를 추가한 Client입니다. |
| 3 | `src/day5/mcp_client03` | stdio/http transport로 실제 MCP 서버에 연결하는 Client입니다. |
| 4 | `src/day5/mcp_client04` | transport, LangGraph Agent, 병렬 DB 호출 데모를 통합한 Client입니다. |
| 5 | `src/day5/mcp_client05` | client04 실행 로직을 Streamlit UI로 제공하는 Client입니다. |
| 6 | `src/day5/mcp_client_final` | Agent 판단 흐름을 시각화하는 최종 통합 UI입니다. |

### 최종 MCP Client 실행

```powershell
$env:PYTHONPATH="src"
uv run streamlit run src/day5/mcp_client_final/streamlit_app.py
```

최종 Client는 다음 흐름을 UI에서 확인하는 것을 목표로 합니다.

```text
사용자 질문
→ 의도 분석
→ Tool 후보 선택
→ MCP Tool 호출
→ DB 결과와 RAG 결과 비교
→ 근거 검증
→ 점검 등급 판단
→ 다음 확인 사항 제안
```

---

## 9. 주요 입력 문서와 데이터

### RAG 입력 문서

| 파일 | 설명 |
|---|---|
| `docs/alarm_manual.md` | 제조 알람 매뉴얼 |
| `docs/troubleshooting_guide.md` | 장애 대응 가이드 |
| `docs/quality_standard.md` | 품질 기준 문서 |

### 실습 입력 데이터

| 파일 | 설명 |
|---|---|
| `data/sample_query.json` | Day1 샘플 질의 |
| `data/sample_alarm_logs.csv` | Day1 샘플 알람 로그 |
| `data/sample_rag_queries.json` | Day2 RAG 샘플 질의 |
| `data/tool_selection_test_cases.json` | Day4 Tool Selection 평가 케이스 |
| `data/day4_rag_evaluation_cases.json` | Day4 RAG 평가 케이스 |
| `data/day4_text_to_sql_cases.json` | Day4 Text-to-SQL Safety 평가 케이스 |
| `data/action_lab_scenarios.json` | Day5 Action Lab 시나리오 |

### DB 관련 파일

| 파일 | 설명 |
|---|---|
| `db/docker-compose.yml` | PostgreSQL 컨테이너 실행 설정 |
| `db/init_manufacturing_db.sql` | 제조 DB 스키마 초기화 SQL |
| `db/sample_manufacturing_data.sql` | 제조 샘플 데이터 입력 SQL |

---

## 10. 강의자료와 노트북

| 경로 | 설명 |
|---|---|
| `lecture_materials/` | Day별 강의자료가 포함됩니다.  |
| `notebook_instructor/` | 강사용 노트북 자료가 포함됩니다. |

강의자료와 강사용 노트북은 폴더 단위로 제공되며, 세부 파일은 각 폴더에서 확인할 수 있습니다.
