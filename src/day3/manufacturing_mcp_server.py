"""
Day3 Manufacturing FastMCP Tool Server - simplified version

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.

이 파일은 초보자 교육용으로 단순화한 FastMCP 기반 MCP Tool Server입니다.
핵심 목적은 "Python 함수를 MCP Tool로 등록하는 구조"를 보여 주는 것입니다.

[FastMCP Server에 대한 오해 방지]
- FastMCP는 사람이 보는 웹 페이지를 띄우는 웹 서버가 아닙니다.
- "Tool을 등록하고, Client가 그 Tool을 호출할 수 있게 해 주는 MCP Tool Server"입니다.
- 즉 이 파일은 DB Tool/RAG Tool 같은 Python 함수들을 "Agent가 표준 방식으로
  호출할 수 있는 Tool"로 외부에 공개하는 역할을 합니다.

[핵심 구조]
- @mcp.tool(name="...")로 등록한 함수의 name이, Client가 부르는 Tool 이름과 연결됩니다.
- DB Tool(postgres_db_tool)과 RAG Tool(search_manual)이 모두 "동일한 @mcp.tool 등록
  방식"으로 올라간다는 점이 중요합니다. 호출하는 쪽 입장에서는 둘이 같은 모양의 Tool입니다.

[현업 적용 시 검토 포인트]
- 인증/권한, 네트워크 정책(접근 허용 범위), timeout, logging, audit, 보안 정책을
  서버 계층에서 갖춰야 실제 운영에 쓸 수 있습니다. (이 교육용 서버에는 없습니다.)
"""

from __future__ import annotations

import sys
from pathlib import Path

# FastMCP: Python 함수를 MCP Tool로 등록/공개하기 위한 라이브러리입니다.
from fastmcp import FastMCP

# 서버 식별용 이름입니다. Client/로그에서 "어떤 Tool 서버인지" 구분할 때 쓰입니다.
SERVER_NAME = "manufacturing_agent_tools"

# 이 서버가 등록하는 Tool 이름 목록입니다(안내 출력용 참고 목록).
# 실제 등록은 아래 @mcp.tool(name=...) 데코레이터가 수행하며,
# 이 목록과 Client의 SUPPORTED_TOOLS가 같은 이름으로 맞아야 호출이 연결됩니다.
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
# 패키지 경로(src.day3.*)로 import하려면 프로젝트 루트가 sys.path에 있어야 합니다.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# 실제 Tool 구현(비즈니스 로직)은 이 서버 파일이 아니라 별도 모듈에 있습니다.
# 이 서버는 그 함수들을 가져와 "MCP Tool로 등록만" 합니다. (구현과 공개의 분리)
# - DB Tool 6종: postgres_db_tool
from src.day3.postgres_db_tool import (
    get_equipment_status,
    get_recent_alarm_events,
    get_process_status,
    get_quality_metrics,
    get_maintenance_history,
    get_equipment_overview,
)

# - RAG Tool 1종: search_manual
from src.day3.search_manual_tool import search_manual


def normalize_blank_text(value: str | None) -> str | None:
    """
    빈 문자열("")을 None으로 바꾸는 입력 표준화(normalization) 헬퍼입니다.

    왜 필요한가:
        - MCP Client/화면에서는 "선택 입력"이 비어 있어도 빈 문자열("")로 넘어오기 쉽습니다.
        - 반면 내부 Python Tool은 "값이 없음"을 None으로 다룹니다.
        - 이 함수가 그 간극을 메워, 선택 입력이 비면 None으로 정리해 줍니다.
          (예: alarm_code가 ""이면 "특정 알람 코드 지정 없음"으로 해석되게 함)

    입력: 문자열 또는 None
    출력: 의미 있는 문자열, 또는 비었으면 None
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

    설계 메모:
        - 안내 문구를 stdout이 아니라 stderr(file=sys.stderr)로 출력합니다.
          MCP는 stdout 채널을 프로토콜 통신에 쓸 수 있어, 사람용 안내는 stderr로 분리합니다.
        - 이 파일은 standalone FastMCP HTTP 서버 방식으로 실행합니다.
        - Client에서는 MCP_FASTMCP_URL에 아래 URL을 설정해서 접속합니다.
    """
    print("Day3 FastMCP Tool Server 시작", file=sys.stderr)
    print("standalone HTTP 서버로 실행됨", file=sys.stderr)
    print("URL: http://127.0.0.1:8765/mcp", file=sys.stderr)
    print("Client에서는 MCP_FASTMCP_URL에 위 URL을 설정", file=sys.stderr)
    print("등록 Tool 7개 목록", file=sys.stderr)

    for tool_name in REGISTERED_TOOL_NAMES:
        print(f"- {tool_name}", file=sys.stderr)

    print("종료하려면 Ctrl+C", file=sys.stderr)


# FastMCP 인스턴스를 만듭니다. 이 mcp 객체에 @mcp.tool로 함수를 붙이면 Tool이 등록됩니다.
mcp = FastMCP(SERVER_NAME)


# ── Tool 등록부 ───────────────────────────────────────────────────────────────
# 아래 함수들은 "MCP Tool 등록용 얇은 래퍼"입니다.
# - @mcp.tool(name="...")의 name이 Client가 호출하는 Tool 이름이 됩니다.
# - 실제 로직은 위에서 import한 DB/RAG 함수가 수행하고, 래퍼는 입력 정리와
#   결과 형태 맞추기 정도만 담당합니다. (등록과 구현의 분리)
# - 함수의 docstring은 Tool 설명으로도 활용되므로, Tool 선택의 근거가 됩니다.

@mcp.tool(name="get_equipment_status")
def get_equipment_status_tool(equipment_id: str) -> dict:
    """
    교육용 제조 DB에서 설비 기본 정보를 조회합니다.
    """
    # 입력을 그대로 DB Tool로 전달하는 가장 단순한 래퍼입니다.
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
    # alarm_code는 선택 입력이므로 빈 문자열이면 None으로 표준화합니다.
    normalized_alarm_code = normalize_blank_text(alarm_code)

    events = get_recent_alarm_events(
        equipment_id=equipment_id,
        alarm_code=normalized_alarm_code,
        limit=limit,
    )

    # 결과를 "건수 + 목록" 형태로 감싸 돌려줍니다.
    # event_count를 함께 주면 호출 측(Agent/요약)이 개수를 다시 세지 않아도 됩니다.
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
    # 선택 입력 alarm_code를 표준화한 뒤, 통합 조회 DB Tool에 위임합니다.
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

    설계 메모:
        - DB Tool과 똑같은 @mcp.tool 방식으로 RAG Tool도 등록된다는 점이 핵심입니다.
        - MCP 쪽 파라미터 이름은 query/alarm_code/symptom이지만,
          실제 search_manual 함수는 user_query 인자를 받으므로 여기서 이름을 맞춰 전달합니다.
    """
    # 세 개의 선택 입력을 모두 표준화(빈 문자열→None)한 뒤 RAG Tool로 넘깁니다.
    return search_manual(
        alarm_code=normalize_blank_text(alarm_code),
        symptom=normalize_blank_text(symptom),
        user_query=normalize_blank_text(query),
        top_k=top_k,
    )


if __name__ == "__main__":
    # 이 파일을 직접 실행하면 standalone HTTP 방식의 MCP Tool 서버가 기동됩니다.
    # Client는 http://127.0.0.1:8765/mcp 로 접속해 위에서 등록한 Tool들을 호출합니다.
    # (종료: Ctrl+C)
    print_startup_message()
    mcp.run(
        transport="http",
        host="127.0.0.1",
        port=8765,
        path="/mcp",
    )
