# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 - MCP transport 저수준 계층 (transport)

[이 파일의 역할]
fastmcp.Client 로 mcp_server03 의 Tool 을 호출하는 가장 낮은 계층입니다. 두 transport 를 지원합니다.
- stdio(기본)        : mcp_server03 을 '별도 프로세스'로 띄우고(StdioTransport) stdin/stdout 으로 MCP 통신.
                       mcp_client03 에서 검증된 연결 방식(StdioTransport + log_file 분리 + 호출 단위 timeout).
- streamable-http    : 외부에서 미리 띄운 long-lived HTTP 서버 URL 에 접속(acall_mcp_tool 의 target 인자).
                       URL 문자열을 fastmcp.Client 에 넘기면 streamable-http 로 자동 추론된다.

[경계 — 매우 중요]
- 서버 내부 함수/모듈(call_mcp_tool/repositories/db_access/rag_*)을 직접 import 하지 않습니다.
- 서버는 transport(stdio 서브프로세스 또는 HTTP 세션)로만 호출합니다.
- 즉 '일반 함수 호출'이 아니라 'MCP 프로토콜 메시지'로 Tool 을 실행합니다(client=요청자, server=구현자).

[안정성]
- 모든 Tool 호출에 timeout 을 둔다(특히 RAG-over-stdio 지연, HTTP 서버 미기동 대비). 무한 대기를 막는다.
- 세션/서버 프로세스는 async with 종료 시 정리된다(정상/오류 모두) — 요청 단위로 열고 닫는다.
- (stdio) 서버 배너/로그(stderr)는 config.SERVER_LOG_PATH 로 분리한다(콘솔/프로토콜 혼선 방지).
"""
from __future__ import annotations

import asyncio
import json

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from day5.mcp_client04 import config


def build_transport() -> StdioTransport:
    """config 기준으로 mcp_server03 stdio 서버를 띄우는 StdioTransport 를 만든다.

    [반환] StdioTransport(command/args/env/cwd/log_file).
    [주의] env 에는 PYTHONPATH=src 만 주입(비밀값은 상속만, 출력하지 않음).
    """
    try:
        config.SERVER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return StdioTransport(
        command=config.SERVER_COMMAND,
        args=list(config.SERVER_ARGS),
        env=config.get_server_env(),
        cwd=str(config.PROJECT_ROOT),
        log_file=config.SERVER_LOG_PATH,
    )


def extract_result(call_result) -> dict:
    """fastmcp CallToolResult 에서 서버 Tool 의 반환 dict/list 를 꺼낸다.

    [왜 필요한가]
        MCP 의 Tool 호출 응답(CallToolResult)은 한 가지 모양이 아니다. 서버/SDK 버전에 따라
        '구조화 출력'(.data / .structured_content, 이미 dict/list)으로 올 수도 있고, 사람이 읽는
        'content 블록'(content[0].text, JSON 문자열)으로 올 수도 있다. 호출자(agents)는 항상
        dict/list 만 다루고 싶으므로, 이 함수가 두 경우를 모두 흡수해 dict/list 로 정규화한다.
    [입력] call_result: fastmcp client.call_tool() 의 반환 객체(CallToolResult).
    [반환] 서버 Tool 의 결과(dict 또는 list). 어느 경로로도 못 꺼내면 빈 dict.
    [교육 포인트] client 는 서버 응답 '형식'에 의존하지 않도록 한 곳에서 정규화한다(경계 단순화).
    """
    # 1순위: 구조화 출력(.data / .structured_content). 이미 dict/list 면 그대로 사용한다.
    for attr in ("data", "structured_content"):
        value = getattr(call_result, attr, None)
        if isinstance(value, (dict, list)):
            return value
    # 2순위: content 블록의 text(JSON 문자열)를 파싱한다.
    content = getattr(call_result, "content", None) or []
    if content and getattr(content[0], "text", None):
        try:
            return json.loads(content[0].text)
        except Exception:
            # text 가 JSON 이 아니면(예상과 다른 응답 형식) 흐름을 깨지 않고 빈 dict 로 둔다.
            return {}
    return {}


def _resolve_client_target(target):
    """fastmcp.Client 에 넘길 '접속 대상'을 결정한다(transport 선택의 single source).

    [입력] target
        - None      : stdio. build_transport() 로 StdioTransport 생성(서버 서브프로세스 spawn).
        - str(URL)  : http. fastmcp.Client 가 URL 문자열을 받으면 streamable-http 로 자동 추론
                      (외부에서 이미 실행 중인 long-lived 서버에 접속, client 가 spawn 안 함).
    [반환] Client 생성자에 그대로 넘길 값(StdioTransport 또는 URL 문자열).
    """
    if target is None:
        return build_transport()   # stdio(기존 동작)
    return target                  # http URL 문자열 → streamable-http 자동 추론


async def acall_mcp_tool(mcp_tool_name: str, arguments: dict, timeout: int, target=None) -> dict:
    """단일 MCP Tool(wrapper)을 timeout 과 함께 호출하고 결과 dict 를 돌려준다(async).

    [입력]
        mcp_tool_name: 서버가 노출한 wrapper Tool 이름(list_mcp_tools/call_mcp_tool).
        target       : 접속 대상. None=stdio(기존), URL 문자열=streamable-http(외부 long-lived 서버).
    [반환] 추출된 결과(dict/list). timeout 시 {"status":"timeout"}, 오류 시 {"status":"error"}.
    [경계] 새 세션을 열어 호출하고 종료한다 → 단계 간 timeout 격리. stdio 는 서버 프로세스를,
           http 는 HTTP 세션을 호출 단위로 열고 닫는다(요청 단위 연결/정리 원칙 동일).
    """
    try:
        # async with Client(...) : MCP 세션을 연다(여기서 실제 연결이 시작된다).
        #   - stdio target(None) → 서버를 서브프로세스로 spawn 하고 stdin/stdout 으로 핸드셰이크.
        #   - http target(URL)   → 외부 long-lived 서버에 HTTP 세션을 연다.
        #   블록을 벗어나면(정상/예외 모두) 세션이 닫히고 stdio 면 서브프로세스도 정리된다.
        async with Client(_resolve_client_target(target)) as client:
            # client.call_tool : 'Tool 실행 요청' 을 서버로 보낸다(MCP 의 call_tool).
            #   네트워크/프로세스 간 I/O 라서 코루틴이며, await 로 응답을 기다린다.
            #   asyncio.wait_for(timeout) : 서버가 멈춰도 무한 대기하지 않도록 시간 상한을 건다.
            result = await asyncio.wait_for(client.call_tool(mcp_tool_name, arguments), timeout=timeout)
            return extract_result(result)
    except asyncio.TimeoutError:
        # transport 별 지연 원인을 힌트로 남긴다(stdio=서브프로세스 RAG 초기화, http=서버 미기동/지연).
        hint = "RAG-over-stdio 지연 가능" if target is None else "HTTP 서버 미기동/지연 가능"
        return {"status": "timeout", "_note": f"{timeout}s 내 응답 없음({hint})"}
    except Exception as error:
        # 예외를 전체 흐름 중단으로 키우지 않고 안전 dict 로 변환(원문 trace 미노출).
        return {"status": "error", "_client_error": type(error).__name__}
