# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 패키지

[이 파일(__init__.py)의 의미]
이 파일이 폴더 안에 존재하기 때문에 Python 은 mcp_client02 폴더를 '패키지(import 가능한 모듈 묶음)'로
인식합니다. 덕분에 `from day5.mcp_client02.graph_builder import build_graph` 처럼 점(.) 경로로
하위 모듈을 가져올 수 있습니다. 이 docstring 은 패키지를 import 했을 때 가장 먼저 읽히는 설명으로,
패키지가 무엇을 하고 어떤 파일로 구성되는지를 한눈에 보여 주는 '입구 안내문' 역할을 합니다.

[이 패키지가 무엇인가]
mcp_client01(단일 Tool 호출 direct client)의 다음 단계로, LangGraph 기반 멀티 에이전트
direct client 입니다. Planner → 5개 Agent(병렬 fan-out) → Evidence Check → Synthesis 구조로
mcp_server03 의 Tool 을 호출하고 결과를 종합합니다.

[구성]
- graph_state.py      : LangGraph State(ClientState) + errors reducer.
- graph_nodes.py      : 규칙 Planner / 5개 Agent(skip 지원) / Evidence Check Node.
- result_synthesis.py : 템플릿 기반 Synthesis Node(LLM 미사용).
- graph_builder.py    : fan-out/fan-in 그래프 조립/compile.
- tool_calling.py     : 서버 Tool entrypoint 호출 wrapper(call_mcp_tool/list_mcp_tools 만).
- result_formatting.py: 결과 요약 + 민감정보 차단.
- client_app.py       : CLI 진입점.

[경계]
- 서버 Tool entrypoint 만 사용한다. repositories/db_access/rag adapter 등 내부 구현은 import 하지 않는다.
- 이번 단계 병렬은 LangGraph 구조상 '논리적 병렬'이며 실제 동시성은 후속 TODO.
- 실제 stdio/HTTP MCP transport 는 mcp_client03 TODO.
"""
