"""
Day3 FastMCP Client + Fallback Tool Registry - simplified version

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.

이 파일은 초보자 교육용으로 단순화한 MCP Client 예제입니다.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path


SUPPORTED_TOOLS = [
    "get_equipment_status",
    "get_recent_alarm_events",
    "get_process_status",
    "get_quality_metrics",
    "get_maintenance_history",
    "get_equipment_overview",
    "search_manual",
]

TOOL_DESCRIPTIONS = {
    "get_equipment_status": "교육용 제조 DB에서 설비 기본 정보를 조회합니다.",
    "get_recent_alarm_events": "교육용 알람 이력에서 최근 반복 알람을 조회합니다.",
    "get_process_status": "교육용 공정 상태에서 온도, 압력, 진공 상태를 조회합니다.",
    "get_quality_metrics": "교육용 품질 지표에서 수율, 불량률 등 품질 영향을 조회합니다.",
    "get_maintenance_history": "교육용 정비 이력에서 최근 점검 및 부품 교체 정보를 조회합니다.",
    "get_equipment_overview": "설비, 알람, 공정, 품질, 정비 정보를 통합 조회합니다.",
    "search_manual": "교육용 기술 문서/RAG에서 알람 조치 절차를 검색합니다.",
}


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 폴더를 반환합니다.
    """
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = get_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def get_mcp_mode() -> str:
    """
    MCP 호출 방식을 환경변수 MCP_MODE에서 읽습니다.
    """
    mode = os.getenv("MCP_MODE", "auto").strip().lower()
    if mode not in {"auto", "fastmcp", "fallback"}:
        return "auto"
    return mode


def get_fastmcp_target() -> str:
    """
    FastMCP Client 접속 대상을 반환합니다.
    """
    fastmcp_url = os.getenv("MCP_FASTMCP_URL", "").strip()
    if fastmcp_url:
        return fastmcp_url

    server_script = get_project_root() / "src" / "day3" / "manufacturing_mcp_server.py"
    return str(server_script)


def list_tools() -> dict:
    """
    현재 Client가 지원하는 Tool 목록을 반환합니다.
    """
    tools = []
    for tool_name in SUPPORTED_TOOLS:
        tools.append({
            "name": tool_name,
            "description": TOOL_DESCRIPTIONS.get(tool_name, "교육용 제조 Agent Tool입니다."),
        })

    return {
        "tool_count": len(tools),
        "tools": tools,
    }


async def _call_tool_via_fastmcp_async(tool_name: str, tool_input: dict) -> object:
    """
    FastMCP Client를 사용해 Tool을 비동기로 호출합니다.
    """
    from fastmcp import Client

    target = get_fastmcp_target()
    async with Client(target) as client:
        return await client.call_tool(tool_name, tool_input)


def call_tool_via_fastmcp(tool_name: str, tool_input: dict) -> object:
    """
    FastMCP Tool Server를 통해 Tool을 호출합니다.
    """
    raw_result = asyncio.run(_call_tool_via_fastmcp_async(tool_name, tool_input))

    if hasattr(raw_result, "structured_content"):
        structured_content = getattr(raw_result, "structured_content")
        if structured_content is not None:
            return structured_content

    if hasattr(raw_result, "data"):
        data = getattr(raw_result, "data")
        if data is not None:
            return data

    if hasattr(raw_result, "content"):
        content = getattr(raw_result, "content")
        if content is not None:
            return content

    return raw_result


def call_tool_via_fallback(tool_name: str, tool_input: dict) -> dict:
    """
    fallback Tool Registry를 통해 Tool을 호출합니다.
    """
    fallback_module = importlib.import_module("src.day3.tool_registry_fallback")
    return fallback_module.call_tool(tool_name, tool_input)


def call_tool(tool_name: str, tool_input: dict | None = None) -> object:
    """
    Tool 이름과 입력값을 받아 FastMCP 또는 fallback으로 Tool을 호출합니다.
    """
    if tool_input is None:
        tool_input = {}

    if tool_name not in SUPPORTED_TOOLS:
        raise ValueError(f"지원하지 않는 Tool입니다: {tool_name}")

    mode = get_mcp_mode()

    if mode == "fallback":
        return call_tool_via_fallback(tool_name, tool_input)

    if mode == "fastmcp":
        return call_tool_via_fastmcp(tool_name, tool_input)

    try:
        return call_tool_via_fastmcp(tool_name, tool_input)
    except Exception:
        return call_tool_via_fallback(tool_name, tool_input)


def print_header() -> None:
    """
    Client 실행 시 수강생에게 보여줄 최소 안내 문구를 출력합니다.
    """
    print("Day3 FastMCP Client 시작")
    print(f"MCP_MODE: {get_mcp_mode()}")
    print(f"FastMCP target: {get_fastmcp_target()}")
    print()
    print("지원 Tool 7개:")
    for tool_name in SUPPORTED_TOOLS:
        print(f"- {tool_name}")


# standalone 서버 접속 테스트 예:
# 터미널 1:
# python src/day3/manufacturing_mcp_server_20260524_060658.py
#
# 터미널 2:
# $env:MCP_MODE="fastmcp"
# $env:MCP_FASTMCP_URL="http://127.0.0.1:8765/mcp"
# python src/day3/manufacturing_mcp_client_20260524_092615.py


if __name__ == "__main__":
    print_header()

    sample_tool_calls = [
        {
            "title": "1. 설비 기본 정보 조회",
            "tool_name": "get_equipment_status",
            "tool_input": {
                "equipment_id": "EQP-EV-03",
            },
        },
        {
            "title": "2. 최근 알람 이력 조회",
            "tool_name": "get_recent_alarm_events",
            "tool_input": {
                "equipment_id": "EQP-EV-03",
                "alarm_code": "ALM-TEMP-402",
                "limit": 5,
            },
        },
        {
            "title": "3. 최근 공정 상태 조회",
            "tool_name": "get_process_status",
            "tool_input": {
                "equipment_id": "EQP-EV-03",
                "limit": 3,
            },
        },
        {
            "title": "4. 최근 품질 지표 조회",
            "tool_name": "get_quality_metrics",
            "tool_input": {
                "line_id": "LINE-07",
                "limit": 3,
            },
        },
        {
            "title": "5. 최근 정비 이력 조회",
            "tool_name": "get_maintenance_history",
            "tool_input": {
                "equipment_id": "EQP-EV-03",
                "limit": 3,
            },
        },
        {
            "title": "6. 설비 통합 Overview 조회",
            "tool_name": "get_equipment_overview",
            "tool_input": {
                "equipment_id": "EQP-EV-03",
                "alarm_code": "ALM-TEMP-402",
            },
        },
        {
            "title": "7. 기술 매뉴얼 검색",
            "tool_name": "search_manual",
            "tool_input": {
                "alarm_code": "ALM-TEMP-402",
                "symptom": "temperature abnormal",
                "top_k": 3,
            },
        },
    ]

    for tool_call in sample_tool_calls:
        print()
        print("=" * 80)
        print(tool_call["title"])
        print(f"Tool: {tool_call['tool_name']}")
        print(f"Input: {tool_call['tool_input']}")

        result = call_tool(
            tool_call["tool_name"],
            tool_call["tool_input"],
        )

        print("Result:")
        print(result)