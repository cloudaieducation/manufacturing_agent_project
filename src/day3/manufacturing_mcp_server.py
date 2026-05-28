"""
Day3 Manufacturing FastMCP Tool Server - simplified version

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.

이 파일은 초보자 교육용으로 단순화한 FastMCP 기반 MCP Tool Server입니다.
핵심 목적은 "Python 함수를 MCP Tool로 등록하는 구조"를 보여 주는 것입니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastmcp import FastMCP

SERVER_NAME = "manufacturing_agent_tools"

REGISTERED_TOOL_NAMES = [
    "get_equipment_status",
    "get_recent_alarm_events",
    "get_process_status",
    "get_quality_metrics",
    "get_maintenance_history",
    "get_equipment_overview",
    "search_manual",
]


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 폴더를 반환합니다.

    예:
    - 프로젝트루트/src/day3/manufacturing_mcp_server_xxx.py

    parents[0] = src/day3
    parents[1] = src
    parents[2] = 프로젝트 루트
    """
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = get_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.day3.postgres_db_tool import (
    get_equipment_status,
    get_recent_alarm_events,
    get_process_status,
    get_quality_metrics,
    get_maintenance_history,
    get_equipment_overview,
)

from src.day3.search_manual_tool import search_manual


def normalize_blank_text(value: str | None) -> str | None:
    """
    빈 문자열을 None으로 바꿉니다.

    MCP Client에서 빈 문자열("")이 들어올 수 있으므로,
    기존 Python Tool 함수가 이해하기 쉬운 None 값으로 정리합니다.
    """
    if value is None:
        return None

    stripped = str(value).strip()
    if stripped == "":
        return None

    return stripped


def print_startup_message() -> None:
    """
    서버 시작 시 최소 안내만 출력합니다.

    이 파일은 standalone FastMCP HTTP 서버 방식으로 실행합니다.
    Client에서는 MCP_FASTMCP_URL에 아래 URL을 설정해서 접속합니다.
    """
    print("Day3 FastMCP Tool Server 시작", file=sys.stderr)
    print("standalone HTTP 서버로 실행됨", file=sys.stderr)
    print("URL: http://127.0.0.1:8765/mcp", file=sys.stderr)
    print("Client에서는 MCP_FASTMCP_URL에 위 URL을 설정", file=sys.stderr)
    print("등록 Tool 7개 목록", file=sys.stderr)

    for tool_name in REGISTERED_TOOL_NAMES:
        print(f"- {tool_name}", file=sys.stderr)

    print("종료하려면 Ctrl+C", file=sys.stderr)


mcp = FastMCP(SERVER_NAME)


@mcp.tool(name="get_equipment_status")
def get_equipment_status_tool(equipment_id: str) -> dict:
    """
    교육용 제조 DB에서 설비 기본 정보를 조회합니다.
    """
    return get_equipment_status(equipment_id=equipment_id)


@mcp.tool(name="get_recent_alarm_events")
def get_recent_alarm_events_tool(
    equipment_id: str,
    alarm_code: str = "",
    limit: int = 5,
) -> dict:
    """
    교육용 제조 DB에서 특정 설비의 최근 알람 이력을 조회합니다.
    """
    normalized_alarm_code = normalize_blank_text(alarm_code)

    events = get_recent_alarm_events(
        equipment_id=equipment_id,
        alarm_code=normalized_alarm_code,
        limit=limit,
    )

    return {
        "equipment_id": equipment_id,
        "alarm_code": normalized_alarm_code,
        "event_count": len(events),
        "events": events,
    }


@mcp.tool(name="get_process_status")
def get_process_status_tool(equipment_id: str, limit: int = 5) -> dict:
    """
    교육용 제조 DB에서 특정 설비의 최근 공정 상태를 조회합니다.
    """
    process_rows = get_process_status(
        equipment_id=equipment_id,
        limit=limit,
    )

    return {
        "equipment_id": equipment_id,
        "status_count": len(process_rows),
        "statuses": process_rows,
    }


@mcp.tool(name="get_quality_metrics")
def get_quality_metrics_tool(line_id: str, limit: int = 5) -> dict:
    """
    교육용 제조 DB에서 생산 라인의 최근 품질 지표를 조회합니다.
    """
    metrics = get_quality_metrics(
        line_id=line_id,
        limit=limit,
    )

    return {
        "line_id": line_id,
        "metric_count": len(metrics),
        "metrics": metrics,
    }


@mcp.tool(name="get_maintenance_history")
def get_maintenance_history_tool(equipment_id: str, limit: int = 5) -> dict:
    """
    교육용 제조 DB에서 특정 설비의 최근 정비 이력을 조회합니다.
    """
    maintenance_rows = get_maintenance_history(
        equipment_id=equipment_id,
        limit=limit,
    )

    return {
        "equipment_id": equipment_id,
        "maintenance_count": len(maintenance_rows),
        "maintenance_history": maintenance_rows,
    }


@mcp.tool(name="get_equipment_overview")
def get_equipment_overview_tool(equipment_id: str, alarm_code: str = "") -> dict:
    """
    교육용 제조 DB에서 설비 관련 정보를 한 번에 묶어 조회합니다.
    """
    return get_equipment_overview(
        equipment_id=equipment_id,
        alarm_code=normalize_blank_text(alarm_code),
    )


@mcp.tool(name="search_manual")
def search_manual_tool(
    query: str = "",
    alarm_code: str = "",
    symptom: str = "",
    top_k: int = 3,
) -> dict:
    """
    교육용 기술 문서와 매뉴얼에서 알람 또는 증상 관련 내용을 검색합니다.
    """
    return search_manual(
        alarm_code=normalize_blank_text(alarm_code),
        symptom=normalize_blank_text(symptom),
        user_query=normalize_blank_text(query),
        top_k=top_k,
    )


if __name__ == "__main__":
    print_startup_message()
    mcp.run(
        transport="http",
        host="127.0.0.1",
        port=8765,
        path="/mcp",
    )
