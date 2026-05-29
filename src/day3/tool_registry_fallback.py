"""
Day3 Simple Fallback Tool Registry

이 파일은 교육용 가상 제조 AI Agent 프로젝트에서 사용합니다.
MCP Server/Client 실행이 어려울 때, Tool 이름과 Python 함수를 직접 연결해 호출하는
fallback registry 개념만 보여 주기 위한 초보자용 예제입니다.

[fallback registry란 무엇인가 — 그리고 무엇이 아닌가]
- fallback은 "Tool 이름표 ↔ 실제 Python 함수"를 dict로 연결해, MCP 서버 없이도
  Tool을 직접 실행해 보는 예비 호출 경로입니다.
- 중요한 한계: 이 fallback은 7개 Tool 전체를 대체하는 운영 구조가 "아닙니다".
  현재는 get_equipment_overview, search_manual 두 개를 중심으로 한 단순 예비 호출만
  제공합니다. (대표 DB Tool 하나 + RAG Tool 하나로 흐름을 잇는 정도)
- 성격: 교육용 안정화 / mock / sandbox / 장애 대비 개념으로 이해하면 됩니다.

[설계 일관성]
- fallback에서도 Tool 이름과 입력 구조(dict)는 MCP와 동일하게 유지합니다.
  그래야 상위 Agent 코드가 "MCP든 fallback이든" 같은 방식으로 Tool을 부를 수 있습니다.

주의:
- 실제 사내 데이터나 실제 내부 시스템명을 사용하지 않습니다.
- 교육용 가상 제조 시나리오만 사용합니다.
- trace 파일이나 로그 파일을 생성하지 않습니다.

[현업 적용 시 검토 포인트]
- 운영에서 fallback을 둔다면, 그 fallback에도 호출 권한, 로그, 감사(audit),
  조회 가능한 데이터 범위 통제가 똑같이 필요합니다. (예비 경로라고 통제를 빼면 안 됩니다.)
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
    Tool 이름과 실제 Python 함수를 연결한 dict(=registry)를 반환합니다.

    Registry는 "Tool 이름표와 실제 함수 연결표"라고 생각하면 됩니다.
    Agent는 Tool 이름만 알고 있고, Registry가 실제 함수를 찾아서 실행합니다.

    설계 메모:
        - 여기 등록된 Tool은 2개뿐입니다(get_equipment_overview, search_manual).
          즉 통합 DB Tool 1개 + RAG Tool 1개로, 전체 흐름을 잇기 위한 최소 구성입니다.
          (개별 DB Tool 6종을 모두 fallback으로 제공하지는 않습니다.)
        - import를 함수 안에서 하는 이유는, fallback이 실제로 필요할 때만 모듈을 로딩하기 위함입니다.

    출력: {"Tool 이름": 함수 객체} 형태의 dict
    """
    project_root = get_project_root()

    # 패키지 경로(src.day3.*)로 import하려면 프로젝트 루트가 sys.path에 있어야 합니다.
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # 대표 DB Tool(통합 조회)과 RAG Tool(매뉴얼 검색)만 가져와 연결합니다.
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

    # registry에 없는 이름이면 명확한 오류로 알려 줍니다.
    # (fallback이 두 개 Tool만 다룬다는 한계가 여기서 그대로 드러납니다.)
    if tool_name not in registry:
        available_tools = ", ".join(registry.keys())
        raise ValueError(
            f"등록되지 않은 Tool입니다: {tool_name}. "
            f"사용 가능한 Tool: {available_tools}"
        )

    # 이름표로 실제 함수를 찾은 뒤, 입력 dict를 키워드 인자(**)로 풀어 호출합니다.
    # 입력 dict 키가 함수 파라미터 이름과 일치해야 한다는 점이 중요합니다.
    tool_function = registry[tool_name]
    return tool_function(**(tool_input or {}))


def run_sample() -> dict:
    """
    파일을 직접 실행했을 때 search_manual Tool을 한 번 호출하는 자체 점검 함수입니다.
    (fallback 경로로 RAG Tool이 정상 동작하는지 확인하는 용도입니다.)
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
    # 직접 실행 시: fallback 경로로 search_manual을 한 번 호출해 결과를 출력합니다.
    result = run_sample()
    print(result)
