# -*- coding: utf-8 -*-
"""
Day5 mcp_client01 - MCP Client 실습 앱 (direct mode)

[이 패키지가 무엇인가 — 교육용 설명]
mcp_client01 은 'MCP Client 관점'에서 mcp_server03 의 Tool 을 호출해 보는 실습용 패키지입니다.
MCP 의 핵심 아이디어는 'LLM 이 DB/파일/검색을 직접 다루지 않고, 서버가 노출한 Tool 을 통해서만
접근한다'는 것입니다. 이 client 는 그 'Tool 호출 측' 역할을 보여줍니다.

[direct mode 란]
이번 1단계는 실제 stdio/HTTP MCP 연결이 아니라, mcp_server03 의 'Tool entrypoint'
(call_mcp_tool / list_mcp_tools)를 직접 import 해서 호출하는 'direct mode' 입니다.
- 장점: 네트워크/프로세스 구성 없이 MCP Client 호출 흐름을 그대로 따라갈 수 있다.
- 한계: 실제 전송 계층(stdio/HTTP)을 거치지 않는다 → 그 부분은 다음 단계(mcp_client02) TODO.

[client 가 지켜야 하는 경계 — 매우 중요]
- client 는 '서버 Tool entrypoint' 만 사용한다(call_mcp_tool / list_mcp_tools).
- repositories / db_access / rag_quality_adapter 같은 서버 내부 구현은 import 하지 않는다.
  (DB/ChromaDB 직접 접속 금지 — 반드시 서버 Tool 을 통해서만 데이터에 접근)
- mcp_server03 의 기능 로직은 수정하지 않는다.

[보안]
- 결과 전체 dict 를 그대로 출력하지 않고 요약한다(result_formatting).
- 민감 필드/문서 전문/접속 비밀값은 출력하지 않는다.
- DB 미기동 시 DB Tool 은 data_source="mock_fallback" 로 응답할 수 있으며, 이는 실패가 아니다.

[실행]
    uv run python -m day5.mcp_client01.client_app          # 기본 데모 시나리오 전체
    uv run python -m day5.mcp_client01                     # __main__.py 경유(동일)
    uv run python -m day5.mcp_client01.client_app --tool search_manual --query "..."
    (import 경로상 <root>/src 가 sys.path 에 있어야 한다 — PYTHONPATH=src 또는 src 를 cwd)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# [import 경로 보강] 이 파일이 직접 실행되거나 일부 환경에서 import 될 때를 대비해,
# 프로젝트 루트의 src 디렉터리를 sys.path 에 넣어 day5.* 패키지를 찾을 수 있게 한다.
#   이 파일 위치: <root>/src/day5/mcp_client01/client_app.py → parents[3] = <root>
_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# 결과 요약은 같은 패키지의 보조 모듈에 둔다.
from day5.mcp_client01.result_formatting import summarize_tool_result


# 기본 데모 시나리오에서 사용할 예시 식별자(가상 시나리오 값).
_DEFAULT_QUERY = "ALM-TEMP-402 조치 방향"
_DEFAULT_EQUIPMENT_ID = "EQP-EV-03"
_DEFAULT_ALARM_CODE = "ALM-TEMP-402"
_DEFAULT_METRIC_NAME = "yield_rate"


def _load_server_entrypoints():
    """대상 서버(mcp_server03)의 Tool entrypoint 를 '지연 import' 한다.

    [왜 지연 import 인가]
        import 시점 오류(예: 경로 문제)가 모듈 로딩 전체를 깨뜨리지 않도록, 실제 호출 직전에 가져온다.
    [경계]
        여기서 가져오는 것은 '서버가 노출한 Tool entrypoint' 뿐이다.
        repositories/db_access/rag_quality_adapter 같은 내부 구현은 가져오지 않는다.
    [반환] (call_mcp_tool, list_mcp_tools)
    """
    # direct mode: 서버의 공개 Tool entrypoint 만 사용한다.
    from day5.mcp_server03.mcp_server import call_mcp_tool, list_mcp_tools
    return call_mcp_tool, list_mcp_tools


def build_arguments(tool: str, args) -> dict:
    """--tool 에 맞는 호출 arguments(dict)를 CLI 옵션으로부터 구성한다.

    [주의]
        client 는 query 를 직접 실행하지 않는다. 서버 Tool 에 '전달'만 하고,
        실제 검증/실행/거부는 서버가 담당한다(예: execute_sql 은 서버가 거부).
    """
    if tool == "search_manual":
        return {"query": args.query or _DEFAULT_QUERY}
    if tool == "get_equipment_overview":
        return {"equipment_id": args.equipment_id or _DEFAULT_EQUIPMENT_ID}
    if tool == "get_recent_alarm_events":
        params = {"equipment_id": args.equipment_id or _DEFAULT_EQUIPMENT_ID}
        if args.alarm_code:
            params["alarm_code"] = args.alarm_code
        return params
    if tool == "get_quality_metrics":
        params = {"metric_name": args.metric_name or _DEFAULT_METRIC_NAME}
        # equipment_id 가 주어지면 함께 전달(서버가 line_id 로 매핑).
        if args.equipment_id:
            params["equipment_id"] = args.equipment_id
        return params
    if tool == "execute_sql":
        # 금지 Tool. query 를 넘기지만 서버가 거부하는지 확인하는 용도일 뿐, client 가 실행하지 않는다.
        return {"query": args.query or "select * from users"}
    # 그 외 Tool 은 빈 arguments 로 전달(서버가 필요한 인자 검증).
    return {}


def run_single_tool(tool: str, args) -> None:
    """--tool 로 지정된 단일 Tool 을 direct mode 로 호출하고 결과를 요약 출력한다."""
    call_mcp_tool, list_mcp_tools = _load_server_entrypoints()

    if tool == "list_mcp_tools":
        print("[Tool 목록 확인] (direct mode)")
        for schema in list_mcp_tools():
            print(f"- {schema.get('name')}")
        return

    arguments = build_arguments(tool, args)
    try:
        result = call_mcp_tool(tool, arguments)
    except Exception as error:
        # 원문 stack trace 를 길게 쏟지 않고 타입명만 보여준다(민감정보 노출 방지).
        print(f"[{tool}] 호출 중 오류: {type(error).__name__}")
        return
    print(f"[{tool}] (direct mode)")
    print(summarize_tool_result(tool, result))


def run_demo(args) -> None:
    """--tool 없이 실행했을 때의 기본 데모 시나리오(6단계).

    1) Tool 목록 → 2) RAG 검색 → 3~5) DB 조회 3종 → 6) 금지 Tool 거부 확인.
    각 단계는 서버 Tool entrypoint 만 사용하며, 결과는 요약해서 보여준다.
    """
    call_mcp_tool, list_mcp_tools = _load_server_entrypoints()

    # [1] 사용 가능한 Tool 목록 — client 는 이 목록을 보고 호출할 Tool 을 고른다.
    print("[1] Tool 목록 확인 (direct mode)")
    for schema in list_mcp_tools():
        print(f"- {schema.get('name')}")
    print()

    # [2] RAG 검색: search_manual (벡터 검색 → 매뉴얼 근거)
    print("[2] RAG 검색: search_manual")
    print(summarize_tool_result("search_manual", call_mcp_tool(
        "search_manual", {"query": args.query or _DEFAULT_QUERY})))
    print()

    # [3] DB 조회: 설비 개요
    print("[3] DB 조회: get_equipment_overview")
    print(summarize_tool_result("get_equipment_overview", call_mcp_tool(
        "get_equipment_overview", {"equipment_id": args.equipment_id or _DEFAULT_EQUIPMENT_ID})))
    print()

    # [4] DB 조회: 최근 알람 이력 (민감 컬럼은 서버가 제외, client 도 요약만)
    print("[4] DB 조회: get_recent_alarm_events")
    print(summarize_tool_result("get_recent_alarm_events", call_mcp_tool(
        "get_recent_alarm_events", {
            "equipment_id": args.equipment_id or _DEFAULT_EQUIPMENT_ID,
            "alarm_code": args.alarm_code or _DEFAULT_ALARM_CODE,
        })))
    print()

    # [5] DB 조회: 품질 지표 (metric_name 은 서버 allowlist 로 통제)
    #     equipment_id 를 함께 전달하면 서버가 equipment_master 를 통해 line_id 로 매핑해 값을 찾는다.
    print("[5] DB 조회: get_quality_metrics")
    print(summarize_tool_result("get_quality_metrics", call_mcp_tool(
        "get_quality_metrics", {
            "metric_name": args.metric_name or _DEFAULT_METRIC_NAME,
            "equipment_id": args.equipment_id or _DEFAULT_EQUIPMENT_ID,
        })))
    print()

    # [6] 금지 Tool 거부 확인: execute_sql 은 서버가 rejected 처리해야 한다.
    print("[6] SQL Tool 거부 확인: execute_sql")
    print(summarize_tool_result("execute_sql", call_mcp_tool(
        "execute_sql", {"query": args.query or "select * from users"})))


def main() -> None:
    """CLI 진입점. --tool 이 없으면 전체 데모, 있으면 단일 Tool 호출.

    client01 은 교육용 direct mode 예제(서버 entrypoint 직접 호출)이며,
    stdio/http transport 는 이후 client03 단계에서 다룬다.
    """
    parser = argparse.ArgumentParser(
        description="mcp_client01 - mcp_server03 Tool 을 호출하는 MCP Client 실습(direct mode)"
    )
    parser.add_argument("--tool", default=None,
                        help="호출할 단일 Tool 이름(미지정 시 전체 데모 시나리오 실행)")
    parser.add_argument("--query", default=None, help="search_manual / execute_sql 질의문")
    parser.add_argument("--equipment-id", dest="equipment_id", default=None, help="설비 식별자")
    parser.add_argument("--alarm-code", dest="alarm_code", default=None, help="알람 코드")
    parser.add_argument("--metric-name", dest="metric_name", default=None, help="품질 지표 이름")
    args = parser.parse_args()

    if args.tool:
        run_single_tool(args.tool, args)
    else:
        run_demo(args)


if __name__ == "__main__":
    main()
