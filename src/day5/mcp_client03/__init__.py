# -*- coding: utf-8 -*-
"""
Day5 mcp_client03 패키지

[이 파일(__init__.py)의 의미]
이 파일이 폴더 안에 있기 때문에 Python 은 mcp_client03 폴더를 'import 가능한 패키지'로 인식합니다.
덕분에 `from day5.mcp_client03 import transport_stdio` 처럼 점(.) 경로로 하위 모듈을 가져올 수 있습니다.
이 docstring 은 패키지를 import 할 때 가장 먼저 읽히는 '입구 안내문' 역할을 합니다.

[이 패키지가 무엇인가]
mcp_client01(direct), mcp_client02(direct+LangGraph)의 다음 단계로, **실제 MCP transport(stdio)**
로 mcp_server03 에 연결해 Tool 을 호출하는 실습 패키지입니다.

[구성]
- transport_stdio.py   : fastmcp.Client + StdioTransport 로 mcp_server03 stdio 서버에 연결/호출.
- result_formatting.py : 결과 요약 + 민감정보 차단.
- client_app.py        : CLI 진입점(기본 데모 / 단일 Tool).

[경계 / 한계]
- direct mode 가 아니라 실제 stdio transport 를 사용한다(direct fallback 없음).
- LangGraph/멀티 에이전트 병렬은 사용하지 않는다(mcp_client04 단계).
- 서버 내부 구현(repositories/db_access/rag adapter)은 import 하지 않는다.
- 이 환경에서 search_manual(RAG)은 stdio 서버 서브프로세스 실행 시 timeout 될 수 있다(한계/TODO).
- HTTP transport 는 미구현(TODO).
"""
