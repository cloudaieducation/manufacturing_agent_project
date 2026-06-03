# -*- coding: utf-8 -*-
"""
Day5 mcp_client03 - 실제 MCP streamable-http transport 연결 계층

[이 파일의 역할]
이미 떠 있는 mcp_server03 의 long-lived HTTP 서버(streamable-http)에 fastmcp.Client 로 접속해
Tool 을 호출합니다. transport_stdio.py 와 형제 모듈이며, 호출 인터페이스(함수 이름/반환)는 같습니다.
차이는 '연결 방식'뿐입니다 — stdio 는 호출마다 서버 프로세스를 새로 띄우지만, http 는 미리 떠 있는
서버에 네트워크로 붙습니다.

[왜 HTTP 인가 — search_manual timeout 해결]
- stdio: client 가 Tool 호출마다 서버를 새 프로세스로 spawn → RAG(chroma+onnx+Ollama) 가 그
  서브프로세스 실행 컨텍스트에서 무응답/timeout(150s+) 됨. DB Tool 은 정상.
- http : 서버가 long-lived 프로세스로 한 번만 떠서 RAG 초기화를 1회만 치르고 살아 있는 상태로
  재사용 → search_manual 이 in-process 와 같은 수초(약 2~4s) 내에 정상 응답함(실측 확인).

[확인된 사실(현재 환경, fastmcp 3.3.1)]
- 서버 실행: `python -m day5.mcp_server03.mcp_server --transport streamable-http --host 127.0.0.1 --port 8003`
  → run_fastmcp_http_server() → server.run(transport="streamable-http", ...). 기본 endpoint: http://127.0.0.1:8003/mcp
- 클라이언트: `from fastmcp import Client`, `StreamableHttpTransport(url=...)` (async).
- 서버가 MCP 로 노출하는 Tool/업무 Tool 호출 규약은 stdio 와 동일하다(call_mcp_tool / list_mcp_tools 경유).

[보안/안정성]
- 모든 호출에 timeout 을 두어 무한 대기를 막고, 시간 초과/오류는 안전 status dict 로 표시한다.
- 서버가 떠 있지 않으면(연결 거부) {"status": "error"} 로 안전 표시한다(stack trace 원문 미출력).
- DB password/connection string/stack trace 원문을 출력하지 않는다.
"""
from __future__ import annotations

import asyncio
import json

# fastmcp Client: MCP 서버에 '클라이언트'로 붙는 객체. StreamableHttpTransport: 이미 떠 있는 HTTP
# MCP 서버에 URL 로 접속하는 연결 방식(서버를 spawn 하지 않음 — stdio 와의 핵심 차이).
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


# 업무 Tool 호출에 사용하는 MCP Tool 이름(서버가 노출하는 진입 Tool). stdio 와 동일 규약.
_CALL_TOOL = "call_mcp_tool"
_LIST_TOOL = "list_mcp_tools"

# HTTP endpoint 기본값(서버 기본 host/port/path 와 일치). README 에도 동일하게 표기한다.
DEFAULT_URL = "http://127.0.0.1:8003/mcp"

# 호출 기본 timeout(초). HTTP long-lived 서버에서는 search_manual 도 수초 내 응답하지만,
# 서버 미기동/지연 대비로 timeout 을 둔다(무한 대기 방지).
DEFAULT_TIMEOUT = 30


def _build_transport(url: str) -> StreamableHttpTransport:
    """이미 떠 있는 mcp_server03 HTTP 서버에 붙는 StreamableHttpTransport 를 만든다.

    - url: MCP endpoint(기본 http://127.0.0.1:8003/mcp). 서버를 spawn 하지 않고 접속만 한다.
    """
    return StreamableHttpTransport(url=url or DEFAULT_URL)


def _extract(call_result) -> dict:
    """fastmcp CallToolResult 에서 서버 Tool 의 반환 dict 를 꺼낸다(transport_stdio 와 동일 규칙).

    - 구조화 출력이면 .data / .structured_content 를 우선 사용.
    - 아니면 content[0].text 를 JSON 파싱. 어느 것도 안 되면 빈 dict.
    """
    for attr in ("data", "structured_content"):
        value = getattr(call_result, attr, None)
        if isinstance(value, (dict, list)):
            return value
    content = getattr(call_result, "content", None) or []
    if content and getattr(content[0], "text", None):
        try:
            return json.loads(content[0].text)
        except Exception:
            return {}
    return {}


async def _call_mcp(client, tool_name: str, arguments: dict, timeout: int):
    """세션(client)에서 단일 MCP Tool 을 timeout 과 함께 호출하고 결과를 돌려준다.

    [반환] 추출된 결과 dict/list. 시간 초과 시 {"status": "timeout", ...}, 오류 시 {"status": "error", ...}.
    """
    try:
        result = await asyncio.wait_for(client.call_tool(tool_name, arguments), timeout=timeout)
        return _extract(result)
    except asyncio.TimeoutError:
        return {"status": "timeout", "_note": f"{timeout}s 내 응답 없음(HTTP 서버 지연/미기동 가능)"}
    except Exception as error:
        # 연결 거부(서버 미기동) 등도 안전한 error dict 로 변환(예외 타입명만 남김).
        return {"status": "error", "_client_error": type(error).__name__}


async def _session_call(url: str, tool_name: str, arguments: dict, timeout: int):
    """HTTP 세션을 열어 단일 MCP Tool 을 호출한다(연결 실패까지 안전 처리).

    [왜 여기서 try/except 인가]
        서버가 떠 있지 않으면 `async with Client(...)` 진입(연결) 단계에서 예외가 난다.
        이는 _call_mcp(호출 단계) 보다 먼저이므로, 세션 진입까지 감싸야 안전 status 로 변환된다.
    [반환] 결과 dict/list. 연결 실패/오류 시 {"status": "error", "_client_error": ...}.
    """
    try:
        async with Client(_build_transport(url)) as client:
            return await _call_mcp(client, tool_name, arguments, timeout)
    except asyncio.TimeoutError:
        return {"status": "timeout", "_note": f"{timeout}s 내 응답 없음(HTTP 서버 지연/미기동 가능)"}
    except Exception as error:
        # 연결 거부(서버 미기동) 등: 예외 타입명만 남기고 stack trace 원문은 숨긴다.
        return {"status": "error", "_client_error": type(error).__name__,
                "_note": "HTTP 서버에 연결하지 못했습니다(서버 기동 여부/URL 확인)."}


async def list_tools_http(url: str = DEFAULT_URL, timeout: int = DEFAULT_TIMEOUT) -> list:
    """실제 HTTP 연결로 '업무 Tool 목록'(이름)을 조회한다(MCP Tool list_mcp_tools 경유).

    [반환] Tool 이름 list. 서버 미기동/오류로 list 를 못 받으면 빈 list.
    """
    result = await _session_call(url, _LIST_TOOL, {}, timeout)
    if isinstance(result, list):
        return [t.get("name") for t in result if isinstance(t, dict)]
    return []


async def call_tool_http(tool_name: str, arguments: dict, url: str = DEFAULT_URL,
                         timeout: int = DEFAULT_TIMEOUT) -> dict:
    """실제 HTTP 연결로 '업무 Tool' 하나를 호출한다(MCP Tool call_mcp_tool 경유).

    [입력] tool_name(예: search_manual / get_equipment_overview / execute_sql), arguments, url.
    [반환] 서버 execute_tool_plan envelope(dict). 연결 실패/timeout/error 시 status 로 표시.
    """
    return await _session_call(
        url, _CALL_TOOL,
        {"tool_name": tool_name, "arguments": dict(arguments or {})}, timeout)


async def run_default_demo_http(query: str, equipment_id: str, alarm_code: str,
                                metric_name: str, url: str = DEFAULT_URL,
                                timeout: int = DEFAULT_TIMEOUT) -> dict:
    """기본 데모 시나리오를 실제 HTTP 연결로 순차 실행하고 결과를 모아 돌려준다.

    [시나리오] 1) 업무 Tool 목록 2) search_manual 3) get_equipment_overview
               4) get_recent_alarm_events 5) get_quality_metrics 6) execute_sql 거부

    [세션 분리] transport_stdio 와 동일하게 각 단계를 독립 세션으로 호출한다(한 단계 timeout 격리).
                단, HTTP 서버는 long-lived 라 세션을 새로 열어도 서버 프로세스/ RAG 초기화는 재사용된다.
    [반환] {"tools": [...], "calls": [{"label","tool","result"}...]}
    """
    out = {"tools": [], "calls": []}
    out["tools"] = await list_tools_http(url, timeout)

    steps = [
        ("RAG 검색", "search_manual", {"query": query, **({"alarm_code": alarm_code} if alarm_code else {})}),
        ("DB 조회: 설비 개요", "get_equipment_overview",
         {"equipment_id": equipment_id} if equipment_id else {}),
        ("DB 조회: 최근 알람", "get_recent_alarm_events",
         {k: v for k, v in (("equipment_id", equipment_id), ("alarm_code", alarm_code)) if v}),
        ("DB 조회: 품질 지표", "get_quality_metrics",
         {k: v for k, v in (("equipment_id", equipment_id), ("metric_name", metric_name)) if v}),
        ("SQL Tool 거부", "execute_sql", {"query": "select * from users"}),
    ]
    for label, tool, args in steps:
        result = await call_tool_http(tool, args, url=url, timeout=timeout)
        out["calls"].append({"label": label, "tool": tool, "result": result})
    return out
