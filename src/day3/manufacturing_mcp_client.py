"""
Day3 FastMCP Client + Fallback Tool Registry - simplified version

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.

이 파일은 초보자 교육용으로 단순화한 MCP Client 예제입니다.

[이 파일이 Day3 아키텍처에서 맡는 역할]
- Agent(또는 실습 코드)는 "어떤 Tool을 어떤 입력으로 부를지"만 정하고,
  실제로 그 Tool을 FastMCP 서버로 호출할지 / fallback 함수로 호출할지는
  이 Client가 결정하고 처리합니다.
- 즉 상위 흐름(Agent)과 실제 실행 경로(MCP/fallback)를 분리해 주는 "중간 계층"입니다.

[핵심 개념]
- call_tool(tool_name, tool_input)이 이 파일의 대표 진입점입니다.
- 상위 Agent는 tool_name 문자열과 입력 dict만 알면 되고,
  네트워크/서버 연결 같은 세부는 몰라도 됩니다. (관심사 분리)

[현업 적용 시 검토 포인트]
- Tool Catalog 관리, 호출 권한, audit log, timeout, retry, 에러 처리 정책을
  Client 계층에서 표준화해야 합니다.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path


# SUPPORTED_TOOLS: 이 Client가 호출을 허용하는 Tool 이름 목록입니다.
# - Agent가 호출 가능한 Tool의 "화이트리스트" 역할을 합니다.
# - 여기 없는 이름으로 call_tool을 부르면 거부됩니다. (아래 call_tool 참고)
# - 이 7개 이름은 MCP Server(@mcp.tool 등록 이름)와 정확히 일치해야 호출이 연결됩니다.
SUPPORTED_TOOLS = [
    "get_equipment_status",
    "get_recent_alarm_events",
    "get_process_status",
    "get_quality_metrics",
    "get_maintenance_history",
    "get_equipment_overview",
    "search_manual",
]

# TOOL_DESCRIPTIONS: 각 Tool이 무엇을 하는지 설명하는 사전입니다.
# - 단순 주석이 아니라, LLM이 "어떤 Tool을 골라야 하는가"를 판단할 때 참고하는 근거입니다.
#   (4일차의 Tool 선택/Tool Call Plan에서 이 설명 품질이 선택 정확도에 직접 영향을 줍니다.)
# - 그래서 설명은 사람을 위한 메모가 아니라 "Tool 선택 기준"으로 작성해야 합니다.
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
    Tool 호출 방식을 환경변수 MCP_MODE에서 읽어 결정합니다.

    의미:
        - "fastmcp": 항상 FastMCP 서버로 호출
        - "fallback": 항상 fallback 함수로 호출 (서버 불필요)
        - "auto": FastMCP를 먼저 시도하고 실패하면 fallback (기본값)
    알 수 없는 값이 들어오면 안전하게 "auto"로 처리합니다.
    """
    mode = os.getenv("MCP_MODE", "auto").strip().lower()
    if mode not in {"auto", "fastmcp", "fallback"}:
        return "auto"
    return mode


def get_fastmcp_target() -> str:
    """
    FastMCP Client가 접속할 대상을 결정합니다.

    우선순위:
        1) 환경변수 MCP_FASTMCP_URL이 있으면 그 URL(원격/standalone 서버)을 사용
        2) 없으면 로컬 서버 스크립트 경로를 대상으로 사용
    이렇게 두면 "이미 떠 있는 HTTP 서버"든 "스크립트 직접 기동"이든 같은 코드로 다룰 수 있습니다.
    """
    fastmcp_url = os.getenv("MCP_FASTMCP_URL", "").strip()
    if fastmcp_url:
        return fastmcp_url

    server_script = get_project_root() / "src" / "day3" / "manufacturing_mcp_server.py"
    return str(server_script)


def list_tools() -> dict:
    """
    현재 Client가 지원하는 Tool 이름과 설명을 묶어 반환합니다.

    용도:
        - "이 Agent/Client가 무엇을 할 수 있는가"를 한눈에 보여 주는 Tool Catalog입니다.
        - 화면(Streamlit)이나 LLM에게 사용 가능한 Tool 목록을 제시할 때 활용합니다.
    출력: {"tool_count": N, "tools": [{"name":..., "description":...}, ...]}
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
    FastMCP Client로 실제 MCP 서버에 Tool 호출을 보내는 비동기 내부 함수입니다.

    설계 의미:
        - FastMCP의 Client API가 async 기반이라 비동기로 작성했습니다.
        - target은 get_fastmcp_target()이 결정한 "URL 또는 서버 스크립트"입니다.
        - async with로 Client를 열고 닫아 연결 자원을 안전하게 정리합니다.
    """
    from fastmcp import Client

    target = get_fastmcp_target()
    async with Client(target) as client:
        return await client.call_tool(tool_name, tool_input)


def call_tool_via_fastmcp(tool_name: str, tool_input: dict) -> object:
    """
    FastMCP Tool Server를 통해 Tool을 호출하는 동기 래퍼입니다.

    설계 의미:
        - 상위 Agent 코드는 동기 호출만 다루면 되도록 asyncio.run으로 감쌌습니다.
        - FastMCP 응답 객체는 버전/Tool에 따라 결과가 담기는 속성이 다를 수 있어,
          structured_content → data → content 순으로 "있으면 그걸" 꺼내 줍니다.
          이렇게 정규화해 두면 상위 코드가 결과를 일관된 형태로 받습니다.
    """
    raw_result = asyncio.run(_call_tool_via_fastmcp_async(tool_name, tool_input))

    # 1순위: 구조화된 결과(structured_content)가 있으면 그것을 사용합니다.
    if hasattr(raw_result, "structured_content"):
        structured_content = getattr(raw_result, "structured_content")
        if structured_content is not None:
            return structured_content

    # 2순위: data 속성
    if hasattr(raw_result, "data"):
        data = getattr(raw_result, "data")
        if data is not None:
            return data

    # 3순위: content 속성
    if hasattr(raw_result, "content"):
        content = getattr(raw_result, "content")
        if content is not None:
            return content

    # 어느 속성도 없으면 원본 응답을 그대로 반환합니다.
    return raw_result


def call_tool_via_fallback(tool_name: str, tool_input: dict) -> dict:
    """
    fallback Tool Registry(tool_registry_fallback)를 통해 Tool을 호출합니다.

    설계 의미:
        - MCP 서버 없이도 Python 함수로 직접 Tool을 실행하는 "예비 실행 경로"입니다.
        - 교육 환경에서 서버 기동이 어렵거나 서버 호출이 실패해도 흐름이 이어지게 합니다.
        - 단, fallback registry는 모든 Tool을 대체하지는 않습니다(아래 모듈 주석 참고).
    """
    # import를 함수 안에서 하는 이유: fallback이 실제로 필요할 때만 모듈을 로딩하기 위함입니다.
    fallback_module = importlib.import_module("src.day3.tool_registry_fallback")
    return fallback_module.call_tool(tool_name, tool_input)


def call_tool(tool_name: str, tool_input: dict | None = None) -> object:
    """
    이 Client의 대표 진입점입니다. Tool 이름과 입력값을 받아,
    MCP_MODE에 따라 FastMCP 또는 fallback으로 실제 호출을 분배합니다.

    Agent 관점:
        - DBInvestigationAgent/ManualRAGAgent는 이 함수 하나만 호출하면 되고,
          서버 연결 여부나 fallback 전환은 신경 쓰지 않습니다. (호출 경로의 추상화)

    입력: tool_name(SUPPORTED_TOOLS 중 하나), tool_input(dict, 없으면 빈 dict)
    출력: Tool 실행 결과(객체/딕셔너리)

    현업 적용 시:
        - 여기서 권한 확인, 호출 로깅(audit), timeout, retry 정책을 표준화합니다.
    """
    # 입력이 없으면 빈 dict로 다뤄, None으로 인한 오류를 막습니다.
    if tool_input is None:
        tool_input = {}

    # 화이트리스트 검증: 지원 목록에 없는 Tool은 호출 자체를 거부합니다.
    # (Agent가 임의의 함수를 부르지 못하게 막는 1차 안전장치)
    if tool_name not in SUPPORTED_TOOLS:
        raise ValueError(f"지원하지 않는 Tool입니다: {tool_name}")

    mode = get_mcp_mode()

    # 모드 선택 분기 ----------------------------------------------------------
    # 1) fallback 고정: 서버 없이 Python 함수로만 호출
    if mode == "fallback":
        return call_tool_via_fallback(tool_name, tool_input)

    # 2) fastmcp 고정: 반드시 MCP 서버로 호출 (서버가 없으면 여기서 오류가 납니다)
    if mode == "fastmcp":
        return call_tool_via_fastmcp(tool_name, tool_input)

    # 3) auto(기본): FastMCP를 먼저 시도하고, 실패하면 fallback으로 자동 전환합니다.
    #    수업 중 서버가 안 떠 있어도 흐름이 끊기지 않게 하는 안전 설계입니다.
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
    # 직접 실행 시: 7개 Tool을 순서대로 한 번씩 호출하며 입력/결과 형태를 출력합니다.
    # 이는 "Agent가 Tool Call Plan대로 Tool을 차례로 부르는 모습"을 콘솔에서 미리 보는 예제입니다.
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