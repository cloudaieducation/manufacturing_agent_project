"""
Day3 Multi-Agent Roles - FastMCP standalone 연동 단순화 버전

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.

실행 구조 예:

터미널 1:
cd C:\\work\\manufacturing_agent_project
conda activate manufacturing_agent_env
python src/day3/manufacturing_mcp_server.py

터미널 2:
cd C:\\work\\manufacturing_agent_project
conda activate manufacturing_agent_env
set MCP_MODE=fastmcp
set MCP_FASTMCP_URL=http://127.0.0.1:8765/mcp
python src/day3/multi_agent_roles_20260524_115828.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pystache


DEFAULT_MODE = "fastmcp"
SAMPLE_USER_QUERY = "EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생했습니다. 원인과 조치 방향을 알려주세요."
EDUCATION_NOTICE = "본 실습은 실제 사내 데이터가 아닌 교육용 가상 제조 시나리오입니다."


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 폴더를 반환합니다.
    """
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = get_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def create_initial_state(user_query: str) -> dict:
    """
    사용자 요청을 받아 Agent들이 함께 사용할 초기 State를 만듭니다.
    """
    return {
        "user_query": user_query,
        "equipment_id": None,
        "alarm_code": None,
        "line_id": None,
        "db_results": {},
        "rag_results": {},
        "agent_steps": [],
        "final_summary": "",
        "mode": DEFAULT_MODE,
    }


def extract_equipment_id(text: str) -> str | None:
    """
    사용자 요청에서 EQP-EV-03 같은 교육용 설비 ID 패턴을 찾습니다.
    """
    if not text:
        return None

    match = re.search(r"(?<![A-Z0-9])EQP-[A-Z]{2}-\d{2}(?![A-Z0-9])", text.upper())
    return match.group(0) if match else None


def extract_alarm_code(text: str) -> str | None:
    """
    사용자 요청에서 ALM-TEMP-402 같은 교육용 알람 코드 패턴을 찾습니다.
    """
    if not text:
        return None

    match = re.search(r"(?<![A-Z0-9])ALM-[A-Z]{2,10}-\d{2,4}(?![A-Z0-9])", text.upper())
    return match.group(0) if match else None


def add_step(state: dict, agent_name: str, message: str) -> None:
    """
    State에 Agent 실행 단계를 추가합니다.
    """
    state["agent_steps"].append(f"{agent_name}: {message}")


def load_tool_caller(mode: str = DEFAULT_MODE):
    """
    Tool 호출 함수를 불러옵니다.

    - fastmcp 모드: manufacturing_mcp_client.call_tool 사용
    - fallback 모드: tool_registry_fallback.call_tool 사용
    - server 입력은 fastmcp로 해석
    """
    requested_mode = str(mode or DEFAULT_MODE).strip().lower()

    if requested_mode == "server":
        requested_mode = "fastmcp"

    if requested_mode == "fallback":
        from src.day3.tool_registry_fallback import call_tool

        return call_tool, "fallback"

    from src.day3.manufacturing_mcp_client import call_tool

    return call_tool, "fastmcp"


def get_tool_data(result):
    """
    FastMCP raw dict, fallback 표준 응답, list-wrapper dict를 모두 처리합니다.
    """
    if isinstance(result, dict) and result.get("status") == "success":
        return result.get("data")

    if isinstance(result, dict) and "data" in result:
        return result["data"]

    return result


def count_items(data) -> int:
    """
    list 또는 list-wrapper dict에서 항목 개수를 계산합니다.
    """
    if isinstance(data, list):
        return len(data)

    if isinstance(data, dict):
        for count_key in ["event_count", "status_count", "metric_count", "maintenance_count", "result_count"]:
            value = data.get(count_key)
            if isinstance(value, int):
                return value

        for list_key in ["events", "statuses", "metrics", "maintenance_history", "results"]:
            value = data.get(list_key)
            if isinstance(value, list):
                return len(value)

    return 0


class CoordinatorAgent:
    """
    사용자 요청을 정리하는 Agent입니다.
    """

    agent_name = "CoordinatorAgent"

    def run(self, state: dict) -> dict:
        user_query = state.get("user_query", "")

        equipment_id = extract_equipment_id(user_query)
        alarm_code = extract_alarm_code(user_query)

        state["equipment_id"] = equipment_id
        state["alarm_code"] = alarm_code

        if equipment_id is None:
            add_step(state, self.agent_name, "[ERROR] equipment_id를 찾을 수 없습니다.")

        if alarm_code is None:
            add_step(state, self.agent_name, "[WARN] alarm_code를 찾을 수 없습니다.")

        add_step(
            state,
            self.agent_name,
            f"사용자 요청에서 equipment_id={equipment_id}, alarm_code={alarm_code}를 확인했습니다.",
        )

        return state


class DBInvestigationAgent:
    """
    교육용 제조 DB Tool을 호출하는 Agent입니다.
    """

    agent_name = "DBInvestigationAgent"

    def __init__(self, call_tool_func) -> None:
        self.call_tool = call_tool_func

    def run(self, state: dict) -> dict:
        equipment_id = state.get("equipment_id")
        alarm_code = state.get("alarm_code")

        if not equipment_id:
            add_step(state, self.agent_name, "[ERROR] equipment_id가 없어 DB Tool 호출을 건너뜁니다.")
            return state

        equipment_status = self.call_tool("get_equipment_status", {"equipment_id": equipment_id})
        state["db_results"]["equipment_status"] = equipment_status

        equipment_data = get_tool_data(equipment_status)
        if isinstance(equipment_data, dict):
            state["line_id"] = equipment_data.get("line_id")

        recent_alarm_events = self.call_tool(
            "get_recent_alarm_events",
            {"equipment_id": equipment_id, "alarm_code": alarm_code, "limit": 5},
        )
        state["db_results"]["recent_alarm_events"] = recent_alarm_events

        process_status = self.call_tool(
            "get_process_status",
            {"equipment_id": equipment_id, "limit": 3},
        )
        state["db_results"]["process_status"] = process_status

        maintenance_history = self.call_tool(
            "get_maintenance_history",
            {"equipment_id": equipment_id, "limit": 3},
        )
        state["db_results"]["maintenance_history"] = maintenance_history

        if state.get("line_id"):
            quality_metrics = self.call_tool(
                "get_quality_metrics",
                {"line_id": state["line_id"], "limit": 3},
            )
            state["db_results"]["quality_metrics"] = quality_metrics
        else:
            add_step(state, self.agent_name, "[WARN] line_id를 찾지 못해 품질 지표 조회를 건너뜁니다.")

        add_step(
            state,
            self.agent_name,
            "교육용 제조 DB Tool을 호출하여 설비 정보, 알람 이력, 공정 상태, 정비 이력, 품질 지표를 확인했습니다.",
        )

        return state


class ManualRAGAgent:
    """
    교육용 기술 문서 검색 Tool을 호출하는 Agent입니다.
    """

    agent_name = "ManualRAGAgent"

    def __init__(self, call_tool_func) -> None:
        self.call_tool = call_tool_func

    def run(self, state: dict) -> dict:
        alarm_code = state.get("alarm_code")
        user_query = state.get("user_query", "")

        tool_input = {
            "alarm_code": alarm_code,
            "symptom": "temperature abnormal" if alarm_code else None,
            "query": user_query,
            "top_k": 3,
        }

        rag_result = self.call_tool("search_manual", tool_input)
        state["rag_results"] = rag_result

        add_step(
            state,
            self.agent_name,
            "교육용 기술 문서 검색 Tool을 호출하여 알람 코드와 사용자 요청 관련 근거를 검색했습니다.",
        )

        return state


class IncidentSummaryAgent:
    """
    DB 결과와 RAG 결과를 합쳐 교육용 장애 대응 요약을 만드는 Agent입니다.
    """

    agent_name = "IncidentSummaryAgent"

    def run(self, state: dict) -> dict:
        equipment_id = state.get("equipment_id") or "미확인"
        alarm_code = state.get("alarm_code") or "미확인"
        line_id = state.get("line_id") or "미확인"

        db_results = state.get("db_results", {})
        rag_result = state.get("rag_results", {})

        equipment_data = get_tool_data(db_results.get("equipment_status", {}))
        alarm_data = get_tool_data(db_results.get("recent_alarm_events", {}))
        process_data = get_tool_data(db_results.get("process_status", {}))
        maintenance_data = get_tool_data(db_results.get("maintenance_history", {}))
        quality_data = get_tool_data(db_results.get("quality_metrics", {}))
        rag_data = get_tool_data(rag_result)

        alarm_count = count_items(alarm_data)
        process_count = count_items(process_data)
        maintenance_count = count_items(maintenance_data)
        quality_count = count_items(quality_data)
        rag_count = count_items(rag_data)

        process_name = "미확인"
        equipment_type = "미확인"

        if isinstance(equipment_data, dict):
            process_name = str(equipment_data.get("process_name", "미확인"))
            equipment_type = str(equipment_data.get("equipment_type", "미확인"))

        state["final_summary"] = f"""# 교육용 장애 대응 요약

## 요청 요약
- 설비 ID: {equipment_id}
- 알람 코드: {alarm_code}
- 라인 ID: {line_id}
- 공정/설비 유형: {process_name} / {equipment_type}
- 실행 모드: {state.get("mode")}

## DB 조회 요약
- 최근 교육용 알람 이력 조회 건수: {alarm_count}건
- 최근 공정 상태 조회 건수: {process_count}건
- 최근 정비 이력 조회 건수: {maintenance_count}건
- 최근 품질 지표 조회 건수: {quality_count}건

## 기술 문서 검색 요약
- 교육용 기술 문서 검색 결과: {rag_count}건

## 원인 후보
- 반복 온도 알람이므로 교육용 시나리오 기준으로 온도 제어 상태, 압력/진공 상태 변화, 최근 정비 이력, 공정 상태 변화를 함께 확인해야 합니다.
- 하나의 지표만으로 원인을 확정하지 않고, 알람 이력과 공정 상태, 품질 지표를 함께 비교해야 합니다.

## 1차 조치 방향
- 동일 알람의 반복 발생 시간대와 공정 상태 변화를 먼저 비교합니다.
- 최근 정비 이력 또는 조건 변경 여부를 확인합니다.
- 교육용 기술 문서 검색 결과의 조치 기준을 참고해 점검 항목을 순서대로 확인합니다.

## 추가 확인 항목
- 알람 발생 직전의 온도, 압력, 진공 상태 변화
- 같은 라인의 품질 지표 변화 여부
- 최근 부품 교체, 점검, 조건 변경 여부
- 동일 알람의 반복 주기와 발생 패턴

## 주의
- {EDUCATION_NOTICE}
- 이 요약은 외부 LLM 호출 없이 규칙 기반으로 생성한 교육용 결과입니다.
"""

        add_step(state, self.agent_name, "DB 결과와 RAG 결과를 기반으로 교육용 장애 대응 요약을 생성했습니다.")

        return state


def run_multi_agent_flow(user_query: str, mode: str = DEFAULT_MODE) -> dict:
    """
    전체 Multi-Agent 역할 분담 흐름을 실행합니다.
    """
    state = create_initial_state(user_query)
    call_tool_func, actual_mode = load_tool_caller(mode)
    state["mode"] = actual_mode

    print("[Day3 Multi-Agent Roles]")
    print("교육용 제조 Multi-Agent 역할 분담 실습을 시작합니다.")
    print(f"실행 모드: {actual_mode}")
    print()

    state = CoordinatorAgent().run(state)
    state = DBInvestigationAgent(call_tool_func).run(state)
    state = ManualRAGAgent(call_tool_func).run(state)
    state = IncidentSummaryAgent().run(state)

    return state


def save_result_markdown(state: dict) -> Path:
    """
    Mustache 템플릿을 사용해 최종 결과 Markdown을 저장합니다.
    """
    output_path = get_project_root() / "outputs" / "day3" / "day3_multi_agent_roles_result.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    template_path = get_project_root() / "templates" / "day3" / "multi_agent_roles_result.mustache"
    template_text = template_path.read_text(encoding="utf-8")

    template_data = {
        "user_query": state.get("user_query", ""),
        "equipment_id": state.get("equipment_id") or "미확인",
        "alarm_code": state.get("alarm_code") or "미확인",
        "line_id": state.get("line_id") or "미확인",
        "mode": state.get("mode", ""),
        "agent_steps": state.get("agent_steps", []),
        "final_summary": state.get("final_summary", "최종 요약이 생성되지 않았습니다."),
    }

    rendered = pystache.render(template_text, template_data)
    output_path.write_text(rendered, encoding="utf-8")

    return output_path


def main() -> None:
    """
    샘플 Multi-Agent 흐름을 실행하고 Markdown 결과를 저장합니다.
    """
    state = run_multi_agent_flow(SAMPLE_USER_QUERY, mode=DEFAULT_MODE)
    output_path = save_result_markdown(state)

    print("[저장 완료]")
    print(str(output_path.relative_to(get_project_root())).replace("\\", "/"))


if __name__ == "__main__":
    main()
