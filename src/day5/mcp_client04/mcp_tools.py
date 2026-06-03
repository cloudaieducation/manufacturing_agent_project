# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 - MCP Tool 호출 래퍼 (mcp_tools)

[이 파일의 역할]
LangGraph Agent 들이 사용할 'Tool 호출자(ToolCaller)' 추상화를 둡니다. Agent 는 이 추상화만 호출하고,
실제 stdio transport 세부는 모릅니다. 덕분에 단위 테스트에서는 가짜 ToolCaller(Fake)를 주입해
외부 MCP 서버/DB/Ollama 없이 그래프 흐름만 검증할 수 있습니다.

[Tool 이름 기준 — 추측 금지]
- 서버가 노출하는 wrapper Tool: config.MCP_LIST_TOOL("list_mcp_tools") / config.MCP_CALL_TOOL("call_mcp_tool").
  (mcp_client03 에서 검증된 이름)
- 업무 Tool 목록은 list_mcp_tools 를 '실행 시점에' 조회해서 얻는다(이름을 코드에 박지 않는다).
- 업무 Tool 호출은 call_mcp_tool({tool_name, arguments}) 경유로 한다(서버 내부 함수 직접 호출 아님).

[경계]
- repositories/db_access/rag_quality_adapter/rag_search/equipment_data/manual_search 를 import 하지 않는다.
"""
from __future__ import annotations

import asyncio

from day5.mcp_client04 import config, transport


def extract_payload(envelope: dict) -> dict:
    """call_mcp_tool envelope 에서 단일 Tool result payload 를 꺼낸다(없으면 빈 dict)."""
    if not isinstance(envelope, dict):
        return {}
    results = envelope.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        inner = results[0].get("result")
        return inner if isinstance(inner, dict) else {}
    return {}


class ToolCaller:
    """Agent 가 사용할 Tool 호출자 인터페이스.

    [메서드]
        list_tools() -> list[str]              : 업무 Tool 이름 목록.
        call_tool(tool_name, arguments) -> dict : 업무 Tool 호출 결과 envelope.
    [용도]
        실제 구현은 StdioToolCaller. 단위 테스트는 이 인터페이스를 흉내내는 Fake 를 주입한다.
    """

    def list_tools(self) -> list:  # pragma: no cover - 인터페이스 기본형
        raise NotImplementedError

    def list_tool_schemas(self) -> list:  # pragma: no cover - 인터페이스 기본형
        raise NotImplementedError

    def call_tool(self, tool_name: str, arguments: dict) -> dict:  # pragma: no cover
        raise NotImplementedError


class _TransportToolCaller(ToolCaller):
    """transport(stdio/http) 위에서 동작하는 ToolCaller 공통 구현.

    [동기 wrapper]
        LangGraph 그래프는 동기로 invoke 되므로, 내부의 async transport 호출을 asyncio.run 으로 감싼다.
        각 호출은 transport.acall_mcp_tool 안에서 '독립 세션'으로 실행된다(요청 단위 연결/정리).
    [timeout]
        호출 단위 timeout(생성 시 지정)으로 무한 대기를 막는다.
    [target]
        접속 대상을 정하는 hook. 하위 클래스가 override 한다.
            - StdioToolCaller : None → 서버 서브프로세스 spawn(기존 방식).
            - HttpToolCaller  : URL 문자열 → 외부 long-lived streamable-http 서버 접속.
    """

    def __init__(self, timeout: int = config.DEFAULT_TIMEOUT):
        self.timeout = timeout

    def _target(self):  # pragma: no cover - 하위 클래스가 결정
        """transport.acall_mcp_tool 에 넘길 접속 대상(None=stdio, URL str=http)."""
        return None

    def list_tool_schemas(self) -> list:
        """서버가 제공하는 업무 Tool 의 '전체 schema dict 목록'을 조회한다(이름만이 아니라 inputSchema 포함).

        [왜 schema 까지 받는가 — DB Tool 병렬 데모용]
            병렬 데모는 Tool 마다 필요한 입력이 다르다(equipment_id/line_id/limit ...).
            이름만으로는 인자를 구성할 수 없으므로, 각 Tool 의 inputSchema(properties/required)를 보고
            '그 Tool 이 실제로 받는 인자만' 골라 전달하려고 schema 전체를 받는다(인자 추측 금지).
        [async 처리] transport.acall_mcp_tool 은 코루틴이지만 호출부는 동기이므로 asyncio.run 으로 감싼다.
        [반환] list[dict] (각 {"name","description","inputSchema"}). 조회 실패/형식 불일치면 빈 list.
        """
        result = asyncio.run(transport.acall_mcp_tool(
            config.MCP_LIST_TOOL, {}, self.timeout, target=self._target()))
        # 서버는 schema dict 의 list 를 준다. 형식이 맞는 dict 만 추려 그대로 반환한다(없으면 빈 list).
        if isinstance(result, list):
            return [t for t in result if isinstance(t, dict)]
        return []

    def list_tools(self) -> list:
        """서버가 제공하는 업무 Tool '이름 목록'을 조회한다(MCP 의 list_tools 단계).

        [MCP 개념] list_tools 는 '서버가 어떤 기능을 제공하는지' 묻는 단계다(실행이 아니라 목록 조회).
                   client 는 이 목록을 보고 어떤 Tool 을 부를지 정한다.
        [구현] list_tool_schemas() 가 받은 schema dict 목록에서 name 만 추린다(조회는 1회). 기존 동작과 동일.
        [반환] 업무 Tool 이름 list[str]. 조회 실패/형식 불일치면 빈 list.
        """
        return [schema.get("name") for schema in self.list_tool_schemas() if schema.get("name")]

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """업무 Tool 하나를 '실행 요청'한다(MCP 의 call_tool 단계, call_mcp_tool wrapper 경유).

        [MCP 개념] call_tool 은 실제 도구 실행 요청이다. client 는 Tool 을 직접 구현하지 않고,
                   tool_name + arguments 를 서버로 보내 서버가 실행한 결과(envelope)를 받는다.
        [입력] tool_name: 호출할 업무 Tool 이름(서버 contract 와 일치). arguments: Tool 인자 dict.
        [async 처리] list_tools 와 동일하게 asyncio.run 으로 코루틴을 동기처럼 실행한다.
        [반환] 서버 execute_tool_plan envelope(dict). timeout/연결오류는 status 로 표시된다(예외 아님).
        """
        return asyncio.run(transport.acall_mcp_tool(
            config.MCP_CALL_TOOL,
            {"tool_name": tool_name, "arguments": dict(arguments or {})},
            self.timeout,
            target=self._target(),
        ))


class StdioToolCaller(_TransportToolCaller):
    """standalone stdio transport 로 mcp_server03 에 접속해 Tool 을 호출하는 ToolCaller(기본/기존).

    [동작] target=None → transport.build_transport() 로 서버 서브프로세스를 호출마다 spawn.
           기존 동작과 완전히 동일하다(DB Tool 중심, search_manual 은 stdio 에서 timeout 가능성).
    """
    # _target() 기본 구현(None=stdio)을 그대로 사용한다.


class HttpToolCaller(_TransportToolCaller):
    """외부에서 이미 실행 중인 streamable-http MCP 서버에 접속해 Tool 을 호출하는 ToolCaller.

    [왜 http 인가]
        stdio 는 호출마다 서버를 새로 spawn 하므로 RAG(search_manual) 초기화 비용 때문에 timeout 된다.
        long-lived HTTP 서버는 초기화를 1회만 치르고 프로세스가 살아 있어 search_manual 이 수초 내 응답한다.
    [경계] client 가 서버를 spawn 하지 않는다. 사용자가 별도 터미널에서 미리 띄운 서버 URL 에 접속만 한다.
    """

    def __init__(self, url: str = config.MCP_HTTP_URL, timeout: int = config.RAG_TIMEOUT):
        super().__init__(timeout=timeout)
        self.url = url

    def _target(self):
        """URL 문자열 → fastmcp.Client 가 streamable-http transport 로 자동 추론."""
        return self.url
