"""
Day3 MCP Tool-Using Multi-Agent v2 - simplified launcher

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.

역할:
- 사용자 질문 준비
- Multi-Agent 실행 호출
- 결과 JSON 저장
- Markdown 결과 저장 호출
- 생성 파일 경로 출력

실제 Multi-Agent 역할 분담은 src/day3/multi_agent_roles_20260524_115828.py가 담당합니다.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


DEFAULT_MODE = "fastmcp"
EDUCATION_NOTICE = "본 실습은 실제 사내 데이터가 아닌 교육용 가상 제조 시나리오입니다."
DEFAULT_USER_QUERY = (
    "EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생했습니다. "
    "최근 알람 이력, 공정 상태, 품질 영향, 정비 이력, 기술 문서 근거를 확인해서 "
    "원인 후보와 조치 방향을 정리해 주세요."
)


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 폴더를 반환합니다.
    """
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = get_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def get_output_dir() -> Path:
    """
    Day3 산출물을 저장할 outputs/day3 폴더를 반환합니다.
    """
    output_dir = get_project_root() / "outputs" / "day3"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def to_json_safe(value: Any) -> Any:
    """
    datetime, date, Decimal처럼 JSON 저장이 어려운 값을 안전한 값으로 바꿉니다.
    """
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, dict):
        return {str(key): to_json_safe(item_value) for key, item_value in value.items()}

    if isinstance(value, list):
        return [to_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [to_json_safe(item) for item in value]

    return value


def print_opening_message(mode: str, user_query: str) -> None:
    """
    실행 시작 안내를 출력합니다.
    """
    print("[Day3 MCP Tool-Using Multi-Agent v2]")
    print("최종 launcher를 실행합니다.")
    print("본 실습은 실제 사내 데이터가 아닌 교육용 가상 제조 시나리오를 사용합니다.")
    print()
    print(f"요청 실행 모드: {mode}")
    print("FastMCP standalone 서버에 연결하여 Tool을 호출합니다.")
    print("fallback은 MCP_MODE=fallback으로 실행할 때 사용하는 예비 방식입니다.")
    print()
    print("사용자 요청:")
    print(user_query)
    print()


def import_multi_agent_runner():
    """
    최신 Multi-Agent runner에서 실행 함수와 Markdown 저장 함수를 불러옵니다.
    """
    from src.day3.multi_agent_roles import (
        run_multi_agent_flow,
        save_result_markdown,
    )

    return run_multi_agent_flow, save_result_markdown


def run_day3_agent_v2(user_query: str, mode: str = DEFAULT_MODE) -> dict:
    """
    Multi-Agent 실행을 multi_agent_roles 모듈에 위임합니다.
    """
    run_multi_agent_flow, _ = import_multi_agent_runner()
    state = run_multi_agent_flow(user_query=user_query, mode=mode)

    if not isinstance(state, dict):
        raise TypeError("run_multi_agent_flow() 반환값이 dict가 아닙니다.")

    return state


def save_result_json(state: dict) -> Path:
    """
    최종 State를 outputs/day3/day3_mcp_tool_agent_v2_result.json에 저장합니다.
    """
    result_path = get_output_dir() / "day3_mcp_tool_agent_v2_result.json"
    safe_state = to_json_safe(state)

    result_path.write_text(
        json.dumps(safe_state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return result_path


def print_final_summary(state: dict, saved_paths: dict[str, Path]) -> None:
    """
    최종 실행 요약과 생성 파일 경로를 출력합니다.
    """
    print("[Day3 v2 실행 완료]")
    print(f"- mode: {state.get('mode')}")
    print(f"- equipment_id: {state.get('equipment_id')}")
    print(f"- alarm_code: {state.get('alarm_code')}")
    print(f"- line_id: {state.get('line_id')}")
    print(f"- Agent step 수: {len(state.get('agent_steps', [])) if isinstance(state.get('agent_steps'), list) else 0}")
    print()

    print("[생성된 파일]")
    for path in saved_paths.values():
        try:
            print(f"- {path.relative_to(get_project_root())}")
        except ValueError:
            print(f"- {path}")

    print()
    print("FastMCP standalone 실행 안내:")
    print()
    print("터미널 1:")
    print("cd C:\\work\\manufacturing_agent_project")
    print("conda activate manufacturing_agent_env")
    print("python src/day3/manufacturing_mcp_server.py")
    print()
    print("터미널 2:")
    print("cd C:\\work\\manufacturing_agent_project")
    print("conda activate manufacturing_agent_env")
    print("set MCP_MODE=fastmcp")
    print("set MCP_FASTMCP_URL=http://127.0.0.1:8765/mcp")
    print("python src/day3/day3_mcp_tool_agent_v2_20260524_121917.py")


def main() -> None:
    """
    전체 실행 진입점입니다.

    이 launcher의 책임은 "오케스트레이션"입니다. 실제 Tool 선택/호출/결과 통합은
    multi_agent_roles 모듈이 담당하고, 여기서는 그 흐름을 호출하고 산출물만 남깁니다.
        질문 준비 → Multi-Agent 실행(Tool 호출 흐름 위임) → 결과 State를 산출물로 저장 → 경로 출력
    저장한 JSON/Markdown 산출물은 4일차 Trace/품질 평가의 입력 자료로 이어집니다.
    """
    # 1) 실행 입력 준비: 교육용 기본 질문과 Tool 호출 모드(fastmcp)를 정합니다.
    user_query = DEFAULT_USER_QUERY
    mode = DEFAULT_MODE

    print_opening_message(mode=mode, user_query=user_query)

    # 2) Multi-Agent 흐름 실행을 위임합니다. 반환된 state에는 추출 정보, db_results,
    #    rag_results, agent_steps(trace), final_summary가 모두 담겨 옵니다.
    state = run_day3_agent_v2(user_query=user_query, mode=mode)

    # 3) Markdown 저장 함수만 가져와 사용합니다(run_multi_agent_flow는 위에서 이미 실행했으므로 제거).
    run_multi_agent_flow, save_result_markdown = import_multi_agent_runner()
    del run_multi_agent_flow

    # 4) 최종 State를 두 가지 산출물로 남깁니다: 기계 판독용 JSON과 사람 검토용 Markdown.
    result_json_path = save_result_json(state)
    markdown_path = save_result_markdown(state)

    saved_paths = {
        "result_json": result_json_path,
        "multi_agent_markdown": markdown_path,
    }

    # 5) 실행 요약과 생성된 산출물 경로를 출력해 다음 단계(검토/평가)로 연결합니다.
    print_final_summary(state, saved_paths)


if __name__ == "__main__":
    main()
