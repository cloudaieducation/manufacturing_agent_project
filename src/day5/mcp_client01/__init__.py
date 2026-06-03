# -*- coding: utf-8 -*-
"""
Day5 mcp_client01 패키지

[이 패키지가 무엇인가]
mcp_server03(FastMCP 기반 MCP Server)의 Tool 을 'MCP Client 관점'에서 호출해 보는
교육용 실습 패키지입니다. 이번 1단계는 실제 stdio/HTTP 연결이 아니라, 서버의 Tool entrypoint
(call_mcp_tool / list_mcp_tools)를 직접 import 해서 호출하는 'direct mode' 입니다.

[구성]
- client_app.py        : CLI 진입점. 기본 데모 시나리오 + 단일 Tool 호출.
- result_formatting.py : Tool 결과를 민감정보 없이 요약 출력하는 보조 함수.
- __main__.py          : `python -m day5.mcp_client01` 실행 지원.

[경계]
- 이 패키지는 '서버 Tool entrypoint' 만 사용한다. repositories/db_access/rag adapter 등
  서버 내부 구현은 import 하지 않는다(DB/ChromaDB 직접 접속 금지).
- 'client' 라는 이름은 이 mcp_client01 패키지에서만 사용한다(서버 내부 파일명에는 쓰지 않음).
"""
