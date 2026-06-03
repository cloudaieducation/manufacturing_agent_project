# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 패키지 — MCP Client(LangGraph 멀티 에이전트)

[이 패키지가 무엇인가]
mcp_client03(실제 stdio transport, 단일 호출)의 다음 단계로, **standalone MCP transport 위에
LangGraph 기반 최소 멀티 에이전트 흐름**을 올린 실습 패키지입니다.
여기서 client 는 Tool 을 직접 구현하지 않습니다. 서버(mcp_server03)가 노출한 Tool 을 transport 로
'요청'할 뿐입니다(= MCP 의 핵심: client 는 요청자, server 는 구현자).

[지원하는 transport — 코드에서 확인된 방식만]
- stdio (기본) : client 가 mcp_server03 을 '서브프로세스'로 직접 띄우고(stdin/stdout 으로 MCP 통신),
                 Tool 호출마다 새 세션(프로세스)을 연다. server 를 따로 띄울 필요 없음.
                 (transport.py 의 StdioTransport)
- streamable-http : 외부에서 '미리 long-lived 로 띄운' HTTP MCP 서버 URL 에 접속한다.
                 client 가 서버를 spawn 하지 않는다 → 서버를 별도 터미널에서 계속 띄워 두어야 한다.
                 (mcp_tools.py 의 HttpToolCaller, URL 문자열 → fastmcp.Client 가 자동 추론)
  ※ sse 등 다른 transport 는 이 패키지에서 사용하지 않는다.

[구성]
- config.py      : 서버 실행 명령/transport 선택/HTTP URL/timeout/위험 SQL 키워드 등 설정.
- transport.py   : fastmcp.Client 저수준 호출(target=None→stdio 서브프로세스, URL→streamable-http).
- mcp_tools.py   : ToolCaller 추상화 — StdioToolCaller / HttpToolCaller. Agent 가 Tool 을 호출하는 창구.
- state.py       : LangGraph State(ClientState) + reducer(messages/errors 누적). allow_rag 포함.
- agents.py      : supervisor / tool_discovery / db / safety / rag / answer Node.
- graph.py       : supervisor →(조건부)→ agent → answer 그래프 조립/compile.
- runner.py      : run_query / run_list_tools / run_demo 실행 흐름(transport/allow_rag 선택).
- __main__.py    : CLI(--demo / --list-tools / --query / --allow-rag / --transport / --http-url).

이 패키지는 CLI/runner/graph/agents/ToolCaller/ThreadPool 병렬 실행 '엔진' 중심이다.
Streamlit 웹 UI 는 mcp_client05 로 분리되어 있으며, 핵심 실행 로직(runner/config)을 import 해서
재사용한다(화면 계층은 graph/agents/mcp_tools/transport 를 복사하지 않는다).

[search_manual(RAG) 처리 — 기본 활성]
- 기본(config.ALLOW_RAG_DEFAULT=True) : 사용자 질문은 별도 플래그 없이도 http 로 전환되어 실제 호출
  (rag_status: OK/EMPTY/ERROR). 따라서 외부 long-lived streamable-http 서버를 먼저 띄워야 한다.
- 오프라인(서버 없이) : --no-rag(또는 --transport stdio) / Streamlit toggle OFF → rag_status="SKIPPED".
- demo 시나리오는 항상 오프라인 stdio 로 고정(4단계가 SKIPPED 를 보여 주는 교육용).

[경계]
- mcp_server03 내부 함수/모듈 직접 import 금지. 데이터 접근은 ToolCaller(transport)만 사용한다.
- 민감정보(키/비밀번호/원문 문서)는 출력/저장하지 않는다(요약은 비민감 스칼라/개수만).
"""
