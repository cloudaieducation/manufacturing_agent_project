"""
Day3 Simple Fallback Tool Registry

이 파일은 교육용 가상 제조 AI Agent 프로젝트에서 사용합니다.
MCP Server/Client 실행이 어려울 때, Tool 이름과 Python 함수를 직접 연결해 호출하는
fallback registry 개념만 보여 주기 위한 초보자용 예제입니다.

주의:
- 실제 사내 데이터나 실제 내부 시스템명을 사용하지 않습니다.
- 교육용 가상 제조 시나리오만 사용합니다.
- trace 파일이나 로그 파일을 생성하지 않습니다.
"""

from __future__ import annotations

import sys
from pathlib import Path


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 폴더를 찾습니다.

    예:
    - 프로젝트루트/src/day3/tool_registry_fallback_YYYYMMDD_HHMMSS.py

    parents[0] = src/day3
    parents[1] = src
    parents[2] = 프로젝트 루트
    """
    return Path(__file__).resolve().parents[2]


def build_tool_registry() -> dict:
    """
    Tool 이름과 실제 Python 함수를 연결한 dict를 반환합니다.

    Registry는 "Tool 이름표와 실제 함수 연결표"라고 생각하면 됩니다.
    Agent는 Tool 이름만 알고 있고, Registry가 실제 함수를 찾아서 실행합니다.
    """
    project_root = get_project_root()

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.day3.postgres_db_tool import get_equipment_overview
    from src.day3.search_manual_tool import search_manual

    return {
        "get_equipment_overview": get_equipment_overview,
        "search_manual": search_manual,
    }


def call_tool(tool_name: str, tool_input: dict | None = None) -> dict:
    """
    Tool 이름과 입력값을 받아 실제 Python 함수를 실행합니다.

    예:
    call_tool(
        "search_manual",
        {
            "alarm_code": "ALM-TEMP-402",
            "symptom": "temperature abnormal",
            "top_k": 3,
        },
    )
    """
    registry = build_tool_registry()

    if tool_name not in registry:
        available_tools = ", ".join(registry.keys())
        raise ValueError(
            f"등록되지 않은 Tool입니다: {tool_name}. "
            f"사용 가능한 Tool: {available_tools}"
        )

    tool_function = registry[tool_name]
    return tool_function(**(tool_input or {}))


def run_sample() -> dict:
    """
    파일을 직접 실행했을 때 search_manual Tool을 한 번 호출합니다.
    """
    return call_tool(
        "search_manual",
        {
            "alarm_code": "ALM-TEMP-402",
            "symptom": "temperature abnormal",
            "top_k": 3,
        },
    )


if __name__ == "__main__":
    result = run_sample()
    print(result)
