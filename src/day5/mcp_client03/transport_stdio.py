# -*- coding: utf-8 -*-
"""
Day5 mcp_client03 - 실제 MCP stdio transport 연결 계층

[이 파일의 역할]
mcp_server03 을 '별도 프로세스 stdio MCP 서버'로 실행하고, fastmcp.Client 로 그 서버에 붙어
Tool 을 호출합니다. mcp_client01/02 의 direct mode(서버 함수 직접 호출)와 달리, 여기서는
**실제 MCP transport(stdio)** 를 거칩니다.

[확인된 사실(현재 환경, fastmcp 3.3.1)]
- 서버: `python -m day5.mcp_server03.mcp_server` → run_fastmcp_server() → server.run()(기본 stdio).
- 클라이언트: `from fastmcp import Client`, `StdioTransport(command, args, env, cwd, ...)` (async).
- 서버가 MCP 로 노출하는 Tool: execute_query / select_tools_for_manufacturing_query /
  validate_tool_plan / execute_selected_tools / call_mcp_tool / list_mcp_tools.
- 업무 Tool(search_manual/get_equipment_overview 등)은 MCP Tool 'call_mcp_tool' 을 통해 호출한다
  (인자: {"tool_name": ..., "arguments": {...}}). 업무 Tool 목록은 MCP Tool 'list_mcp_tools' 로 받는다.

[알려진 한계 — 매우 중요]
- 이 환경에서 'search_manual'(RAG, chroma+Ollama) 을 stdio 서버 서브프로세스로 호출하면
  응답이 매우 지연/행(hang)된다(서버 내부 실행 컨텍스트 문제로 추정). in-process 직접 호출은 빠르다.
- 따라서 모든 호출에 timeout 을 두고, 시간 초과 시 {"status": "timeout"} 으로 안전 처리한다.
  (서버 코드는 수정하지 않으므로, RAG-over-stdio 성능 문제는 이번 단계에서 timeout 처리 + TODO 로 둔다.)

[보안/안정성]
- 서버 프로세스는 async with 블록 종료 시 정리된다(정상/오류 모두).
- DB password/connection string/stack trace 원문을 출력하지 않는다.
- 서버 배너/로그(stderr)는 log_file 로 빼서 콘솔 출력을 깔끔히 유지한다.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# fastmcp Client: MCP 서버에 '클라이언트'로 붙는 객체. StdioTransport: 서버를 별도 프로세스로 띄우고
# 표준입출력(stdin/stdout)으로 MCP 메시지를 주고받는 연결 방식. (서버=Tool 제공자, 클라이언트=호출자)
from fastmcp import Client
from fastmcp.client.transports import StdioTransport


# 경로: 이 파일 <root>/src/day5/mcp_client03/transport_stdio.py → parents[3] = <root>
_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"

# 서버 stderr(배너/로그)를 빼둘 파일(콘솔 출력 정돈용). outputs 아래(gitignore 영향 없음).
_SERVER_LOG = _ROOT / "outputs" / "day5" / "mcp_client03_server.log"

# 업무 Tool 호출에 사용하는 MCP Tool 이름(서버가 노출하는 진입 Tool).
_CALL_TOOL = "call_mcp_tool"
_LIST_TOOL = "list_mcp_tools"

# 호출 기본 timeout(초). RAG(search_manual)는 이 환경에서 지연될 수 있어 timeout 으로 보호한다.
DEFAULT_TIMEOUT = 30


def _build_transport() -> StdioTransport:
    """mcp_server03 을 stdio MCP 서버로 띄우는 StdioTransport 를 만든다.

    - command/args: `python -m day5.mcp_server03.mcp_server` (서버의 __main__ → run_fastmcp_server).
    - env: 서브프로세스가 day5.* 패키지를 찾도록 PYTHONPATH=src 를 넣는다(비밀값은 그대로 상속만).
    - cwd: 프로젝트 루트(상대 경로 자원 탐색 일관성).
    - log_file: 서버 배너/로그(stderr)를 파일로 빼서 콘솔을 깔끔히 한다.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    try:
        _SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return StdioTransport(
        command=sys.executable,
        args=["-m", "day5.mcp_server03.mcp_server"],
        env=env,
        cwd=str(_ROOT),
        log_file=_SERVER_LOG,
    )


def _extract(call_result) -> dict:
    """fastmcp CallToolResult 에서 서버 Tool 의 반환 dict 를 꺼낸다.

    - 구조화 출력이면 .data / .structured_content 를 우선 사용.
    - 아니면 content[0].text 를 JSON 파싱.
    - 어느 것도 안 되면 빈 dict.
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


async def _call_mcp(client, tool_name: str, arguments: dict, timeout: int) -> dict:
    """세션(client)에서 단일 MCP Tool 을 timeout 과 함께 호출하고 결과 dict 를 돌려준다.

    [반환] 추출된 결과 dict. 시간 초과 시 {"status": "timeout", ...}, 오류 시 {"status": "error", ...}.
    [주의] timeout 으로 무한 대기를 막는다(서버 RAG 지연 대비).
    """
    try:
        # client.call_tool: MCP 프로토콜로 서버에 '이 Tool 을 이 인자로 실행해 달라'고 요청한다.
        # asyncio.wait_for 로 timeout 을 걸어, 응답이 없을 때 무한 대기하지 않게 한다.
        result = await asyncio.wait_for(client.call_tool(tool_name, arguments), timeout=timeout)
        return _extract(result)
    except asyncio.TimeoutError:
        # 시간 초과: 예외로 그래프를 멈추는 대신 'timeout' 상태 dict 로 안전 표시(원문 trace 미노출).
        return {"status": "timeout", "_note": f"{timeout}s 내 응답 없음(이 환경의 RAG-over-stdio 지연 가능)"}
    except Exception as error:
        # 그 밖의 호출 오류도 안전한 error dict 로 변환(예외 타입명만 남기고 상세는 숨김).
        return {"status": "error", "_client_error": type(error).__name__}


async def list_tools_stdio(timeout: int = DEFAULT_TIMEOUT) -> list:
    """실제 stdio 연결로 '업무 Tool 목록'(이름)을 조회한다.

    MCP Tool 'list_mcp_tools' 를 호출해 contracts 기준 업무 Tool schema 를 받고 이름만 추린다.
    """
    # async with Client(...): 진입 시 서버 프로세스를 띄워 연결하고, 블록을 벗어나면 자동으로 정리(종료)한다.
    async with Client(_build_transport()) as client:
        result = await _call_mcp(client, _LIST_TOOL, {}, timeout)
        if isinstance(result, list):
            return [t.get("name") for t in result if isinstance(t, dict)]
        return []


async def call_tool_stdio(tool_name: str, arguments: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """실제 stdio 연결로 '업무 Tool' 하나를 호출한다(MCP Tool call_mcp_tool 경유).

    [입력] tool_name(예: search_manual / get_equipment_overview / execute_sql), arguments.
    [반환] 서버 execute_tool_plan envelope(dict). timeout/error 시 status 로 표시.
    [경계] 서버 내부 함수가 아니라 MCP Tool 'call_mcp_tool' 을 통해 호출한다(실제 transport).
    """
    # 업무 Tool 은 서버의 진입 Tool 'call_mcp_tool' 에 {tool_name, arguments} 를 넘겨 간접 호출한다.
    # (LLM 이 Tool 을 고르는 게 아니라, 호출자가 tool_name 을 직접 지정하는 구조다.)
    async with Client(_build_transport()) as client:
        return await _call_mcp(client, _CALL_TOOL,
                               {"tool_name": tool_name, "arguments": dict(arguments or {})}, timeout)


async def run_default_demo_stdio(query: str, equipment_id: str, alarm_code: str,
                                 metric_name: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """기본 데모 시나리오를 실제 stdio 연결로 순차 실행하고 결과를 모아 돌려준다.

    [시나리오] 1) 업무 Tool 목록 2) search_manual 3) get_equipment_overview
               4) get_recent_alarm_events 5) get_quality_metrics 6) execute_sql 거부

    [세션 분리] 각 단계는 독립 세션(서버 프로세스)으로 호출한다. 한 단계가 timeout 되어도
                다음 단계 세션에 영향을 주지 않게 하기 위함이다(세션 상태 오염 방지).
    [반환] {"tools": [...], "calls": [{"label","tool","result"}...]}
    """
    out = {"tools": [], "calls": []}
    # 먼저 업무 Tool 목록을 받아 둔다(데모 1단계).
    out["tools"] = await list_tools_stdio(timeout)

    # 2~6단계: (라벨, Tool 이름, 인자) 목록. 아래 for 문이 이 순서대로 '순차' 호출한다(병렬 아님).
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
        # 각 단계는 call_tool_stdio 안에서 독립 세션(새 서버 프로세스)으로 호출된다 → timeout 격리.
        result = await call_tool_stdio(tool, args, timeout)
        out["calls"].append({"label": label, "tool": tool, "result": result})
    return out
