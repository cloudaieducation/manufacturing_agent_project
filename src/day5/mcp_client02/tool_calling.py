# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 - Tool Calling (서버 Tool entrypoint 호출 wrapper)

[이 파일의 역할]
mcp_client02 의 모든 Agent Node 가 PostgreSQL/ChromaDB 같은 데이터에 접근할 때, 반드시
'mcp_server03 의 Tool entrypoint' 만 통하도록 강제하는 얇은 wrapper 계층입니다.

[MCP 서버 vs MCP 클라이언트 — 역할 구분]
- 서버(mcp_server03): 실제 데이터(DB/Chroma)에 접근하는 Tool 을 정의·노출하고, 입력 검증/sanitize 를
  책임진다. '무엇을 어떻게 조회하는가'의 구현이 서버에 있다.
- 클라이언트(mcp_client02): 서버가 노출한 Tool 의 '이름과 인자'만 알고 호출한다. 데이터 구현은 모른다.
- 이 파일의 call_server_tool 은 그 호출을 대신해 주는 클라이언트 쪽 창구다. 즉 '이 단계에서는 LLM 이
  Tool 을 고르는 게 아니라, 클라이언트(Agent Node) 코드가 규칙으로 정한 Tool 을 직접 호출'한다.

[경계 — 매우 중요]
- 허용: from day5.mcp_server03.mcp_server import call_mcp_tool, list_mcp_tools
- 금지: repositories / db_access / rag_quality_adapter / rag_search / equipment_data /
        manual_search 등 '서버 내부 구현' 직접 import.
  → client 는 DB/Chroma 에 직접 접속하지 않고, 서버가 노출한 Tool 만 호출한다(MCP 의 핵심 경계).

[안정성]
- Tool 호출 중 예외가 나도 그래프 전체를 중단시키지 않는다.
  call_server_tool 은 예외를 잡아 안전한 error dict 로 바꾼다(stack trace 원문 미노출).
"""
from __future__ import annotations


def call_server_tool(tool_name: str, arguments: dict) -> dict:
    """mcp_server03 의 단일 Tool 을 호출하고 envelope(dict)를 돌려준다.

    [입력]
        tool_name: 호출할 Tool 이름(예: "search_manual").
        arguments: 호출 인자 dict.
    [반환]
        성공 시: call_mcp_tool 의 반환 envelope
            {status, validation_status, executed_count, results:[{tool_name, status, result, ...}], ...}
        예외 시: {"status": "error", "_client_error": "<예외 타입명>"} (원문 trace 미노출)

    [지연 import]
        서버 entrypoint 를 함수 안에서 import 한다. import 실패가 모듈 로딩 전체를 깨뜨리지 않게 하고,
        '서버 Tool 만 사용한다'는 경계를 호출 지점에서 명확히 드러내기 위함이다.
    """
    try:
        from day5.mcp_server03.mcp_server import call_mcp_tool
        return call_mcp_tool(tool_name, dict(arguments or {}))
    except Exception as error:
        # 전체 그래프를 중단시키지 않도록, 예외를 안전한 error dict 로 변환한다.
        return {"status": "error", "_client_error": type(error).__name__}


def list_server_tools() -> list:
    """mcp_server03 이 노출하는 Tool schema 목록을 돌려준다(실패 시 빈 list)."""
    try:
        from day5.mcp_server03.mcp_server import list_mcp_tools
        return list_mcp_tools()
    except Exception:
        return []
