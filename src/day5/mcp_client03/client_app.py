# -*- coding: utf-8 -*-
"""
Day5 mcp_client03 - 실제 MCP transport(stdio) Client (CLI 진입점)

[이 패키지가 무엇인가]
mcp_client01(direct), mcp_client02(direct+LangGraph)의 다음 단계로, **실제 MCP transport(stdio)**
로 mcp_server03 에 연결해 Tool 을 호출하는 실습 client 입니다.
- direct mode 가 아니라, 별도 프로세스로 stdio MCP 서버를 띄우고 fastmcp.Client 로 붙습니다.
- LangGraph/멀티 에이전트 병렬은 사용하지 않습니다(그건 mcp_client04 단계).
- direct fallback 도 만들지 않습니다(direct 는 mcp_client01 에서 이미 다룸).

[확인된 동작(현재 환경)]
- 실제 stdio 연결로 Tool 목록 조회, get_equipment_overview(DB) 호출, execute_sql 거부가 동작.
- search_manual(RAG)은 이 환경에서 stdio 서버 서브프로세스 실행 시 지연/timeout 됨(아래 한계 참조).

[transport 모드 — stdio / http]
- --mode stdio (기본): 호출마다 서버를 별도 프로세스로 spawn 해 붙는다. DB Tool/목록/거부는 정상이나
  search_manual(RAG)은 이 환경에서 stdio 서브프로세스 실행 시 지연/timeout 된다(아래 한계 참조).
- --mode http        : 미리 떠 있는 long-lived HTTP 서버(streamable-http)에 --url 로 접속한다.
  RAG 초기화를 1회만 치르고 재사용하므로 search_manual 도 수초 내 정상 응답한다(실측 확인).
  HTTP 서버를 먼저 띄워야 한다:
    uv run python -m day5.mcp_server03.mcp_server --transport streamable-http --host 127.0.0.1 --port 8003

[한계/주의]
- (stdio) search_manual(chroma+Ollama)을 stdio 서버 프로세스로 호출하면 timeout 될 수 있다(서버측 RAG
  실행 컨텍스트 문제). 모든 호출에 timeout 을 두어 무한 대기를 막고, timeout 은 안전하게 표시한다.
- (http) 서버가 떠 있지 않으면 연결 오류를 안전 status 로 표시한다(stack trace 원문 미출력).
- 결과 전체 dict/민감정보는 출력하지 않고 요약만 출력한다.

[실행]
    uv run python -m day5.mcp_client03                      # stdio 기본 데모
    uv run python -m day5.mcp_client03 --tool get_equipment_overview --equipment-id EQP-EV-03
    uv run python -m day5.mcp_client03 --mode http --url http://127.0.0.1:8003/mcp
    uv run python -m day5.mcp_client03 --mode http --tool search_manual --query "ALM-TEMP-402 조치 방향"
    (import 경로상 <root>/src 가 sys.path 에 있어야 한다 — PYTHONPATH=src 또는 src 를 cwd)
"""
from __future__ import annotations

import argparse  # CLI 인자(--tool/--query/--timeout 등) 파싱
import asyncio   # stdio transport 호출이 async 이므로, 동기 main 에서 asyncio.run 으로 실행한다
import sys
from pathlib import Path

# [import 경로 보강] 이 파일 <root>/src/day5/mcp_client03/client_app.py → parents[3] = <root>
# <root>/src 를 sys.path 에 넣어 'day5.mcp_client03.*' 패키지 import 가 어디서 실행하든 동작하게 한다.
_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# transport_stdio: stdio MCP 연결/호출 계층(호출마다 서버 spawn).
# transport_http : streamable-http MCP 연결/호출 계층(이미 떠 있는 long-lived 서버에 접속).
# summarize_tool_result: 결과 요약 출력(민감정보 미출력).
from day5.mcp_client03 import transport_stdio
from day5.mcp_client03 import transport_http
from day5.mcp_client03.result_formatting import summarize_tool_result


_DEFAULT_QUERY = "ALM-TEMP-402 조치 방향"
_DEFAULT_EQUIPMENT_ID = "EQP-EV-03"
_DEFAULT_ALARM_CODE = "ALM-TEMP-402"
_DEFAULT_METRIC_NAME = "yield_rate"


def _build_arguments(tool: str, args) -> dict:
    """--tool 에 맞는 호출 arguments(dict)를 CLI 옵션으로 구성한다(서버가 검증/거부 담당)."""
    if tool == "search_manual":
        params = {"query": args.query or _DEFAULT_QUERY}
        if args.alarm_code:
            params["alarm_code"] = args.alarm_code
        return params
    if tool == "get_equipment_overview":
        return {"equipment_id": args.equipment_id or _DEFAULT_EQUIPMENT_ID}
    if tool == "get_recent_alarm_events":
        params = {"equipment_id": args.equipment_id or _DEFAULT_EQUIPMENT_ID}
        if args.alarm_code:
            params["alarm_code"] = args.alarm_code
        return params
    if tool == "get_quality_metrics":
        params = {"metric_name": args.metric_name or _DEFAULT_METRIC_NAME}
        if args.equipment_id:
            params["equipment_id"] = args.equipment_id
        return params
    if tool == "execute_sql":
        return {"query": args.query or "select * from users"}
    return {}


async def _run_single(tool: str, args) -> None:
    """--tool 로 지정된 단일 업무 Tool 을 실제 transport(stdio/http)로 호출하고 요약 출력한다.

    [분기] tool 이 'list_mcp_tools' 면 목록 조회 경로, 그 외에는 업무 Tool 호출 경로로 나뉜다.
           --mode 에 따라 stdio/http transport 계층을 선택한다(호출 인터페이스는 동일).
    """
    is_http = args.mode == "http"
    label = "http transport" if is_http else "stdio transport"
    # 'list_mcp_tools' 는 인자가 필요 없는 목록 조회 → 이름만 받아 출력하고 끝낸다.
    if tool == "list_mcp_tools":
        if is_http:
            names = await transport_http.list_tools_http(url=args.url, timeout=args.timeout)
        else:
            names = await transport_stdio.list_tools_stdio(timeout=args.timeout)
        print(f"[Tool 목록 확인] ({label})")
        for name in names:
            print(f"- {name}")
        return
    # 그 외 업무 Tool: CLI 옵션으로 호출 인자를 만들고, 선택한 transport 로 호출한 뒤 요약 출력한다.
    arguments = _build_arguments(tool, args)
    if is_http:
        envelope = await transport_http.call_tool_http(tool, arguments, url=args.url, timeout=args.timeout)
    else:
        envelope = await transport_stdio.call_tool_stdio(tool, arguments, timeout=args.timeout)
    print(f"[{tool}] ({label})")
    print(summarize_tool_result(tool, envelope))


async def _run_demo(args) -> None:
    """기본 데모 시나리오를 실제 transport(stdio/http)로 순차 실행하고 요약 출력한다.

    [흐름] 선택한 transport 의 run_default_demo_* 가 ①목록 ②~⑤ 업무 Tool ⑥execute_sql 거부를
           순차 호출해 결과 묶음(dict)을 돌려주면, 여기서는 그 결과를 단계별로 요약 출력만 한다.
    """
    is_http = args.mode == "http"
    label = "http transport" if is_http else "stdio transport"
    if is_http:
        result = await transport_http.run_default_demo_http(
            query=args.query or _DEFAULT_QUERY,
            equipment_id=args.equipment_id or _DEFAULT_EQUIPMENT_ID,
            alarm_code=args.alarm_code or _DEFAULT_ALARM_CODE,
            metric_name=args.metric_name or _DEFAULT_METRIC_NAME,
            url=args.url,
            timeout=args.timeout,
        )
    else:
        result = await transport_stdio.run_default_demo_stdio(
            query=args.query or _DEFAULT_QUERY,
            equipment_id=args.equipment_id or _DEFAULT_EQUIPMENT_ID,
            alarm_code=args.alarm_code or _DEFAULT_ALARM_CODE,
            metric_name=args.metric_name or _DEFAULT_METRIC_NAME,
            timeout=args.timeout,
        )
    print(f"[1] Tool 목록 확인 ({label})")
    for name in result.get("tools", []):
        print(f"- {name}")
    for index, call in enumerate(result.get("calls", []), start=2):
        print(f"\n[{index}] {call['label']}: {call['tool']}")
        print(summarize_tool_result(call["tool"], call["result"]))
    if is_http:
        print("\n[참고] mcp_client03 --mode http 는 미리 떠 있는 long-lived HTTP 서버(streamable-http)에 "
              "접속합니다. 이 모드에서는 search_manual(RAG)도 수초 내 정상 응답합니다.")
    else:
        print("\n[참고] mcp_client03 은 실제 MCP stdio transport 로 서버에 연결합니다(direct mode 아님). "
              "이 환경에서 search_manual(RAG)은 서버 서브프로세스 실행 시 timeout 될 수 있습니다 "
              "(해결책: --mode http).")


def main() -> None:
    """CLI 진입점: stdio transport 로 Tool 을 호출한다. --tool 없으면 기본 데모."""
    parser = argparse.ArgumentParser(
        description="mcp_client03 - 실제 MCP stdio transport client(mcp_server03 연결)"
    )
    parser.add_argument("--mode", default="stdio", choices=["stdio", "http"],
                        help="transport 모드. stdio(기본, 호출마다 서버 spawn) 또는 http(long-lived HTTP 서버 접속). direct fallback 없음")
    parser.add_argument("--url", default=transport_http.DEFAULT_URL,
                        help=f"--mode http 의 MCP endpoint URL(기본 {transport_http.DEFAULT_URL})")
    parser.add_argument("--tool", default=None, help="호출할 단일 Tool(미지정 시 기본 데모)")
    parser.add_argument("--query", default=None, help="search_manual / execute_sql 질의문")
    parser.add_argument("--equipment-id", dest="equipment_id", default=None, help="설비 식별자")
    parser.add_argument("--alarm-code", dest="alarm_code", default=None, help="알람 코드")
    parser.add_argument("--metric-name", dest="metric_name", default=None, help="품질 지표 이름")
    parser.add_argument("--timeout", type=int, default=transport_stdio.DEFAULT_TIMEOUT,
                        help="Tool 호출 timeout(초). 무한 대기 방지(특히 RAG over stdio)")
    args = parser.parse_args()

    if args.mode == "http":
        # http 모드: 미리 서버를 띄워야 한다는 안내(연결 실패 시에도 안전 status 로 표시됨).
        print(f"[안내] --mode http: {args.url} 에 접속합니다. 서버를 먼저 띄워야 합니다 → "
              "python -m day5.mcp_server03.mcp_server --transport streamable-http --port 8003\n")

    # 실행 분기: --tool 이 있으면 단일 Tool 호출, 없으면 기본 데모 시나리오.
    # async 함수이므로 asyncio.run 으로 이벤트 루프를 열어 실행한다.
    if args.tool:
        asyncio.run(_run_single(args.tool, args))
    else:
        asyncio.run(_run_demo(args))


if __name__ == "__main__":
    main()
