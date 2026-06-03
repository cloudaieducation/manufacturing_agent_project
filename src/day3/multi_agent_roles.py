"""
Day3 Multi-Agent Roles - FastMCP standalone 연동 단순화 버전

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.

[이 파일이 Day3 아키텍처에서 맡는 역할 — Day3의 핵심 파일]
- 여러 Agent가 "역할을 나눠" 하나의 장애 대응 흐름을 처리하는 구조를 보여 줍니다.
- 핵심은 이름을 나누는 것이 아니라 "책임(responsibility)을 분리"하는 것입니다.
    · CoordinatorAgent     : 사용자 요청 분석(설비 ID/알람 코드 추출)
    · DBInvestigationAgent : DB/Log Tool 호출 책임
    · ManualRAGAgent       : search_manual(RAG) Tool 호출 책임
    · IncidentSummaryAgent : DB 결과 + RAG 결과 종합 책임

[State 전달 구조 — 반드시 이해해야 할 개념]
- 모든 Agent는 하나의 dict인 "State"를 차례로 받고, 자기 책임만큼 채운 뒤 넘깁니다.
- State 안의 주요 칸:
    · equipment_id / alarm_code / line_id : 추출한 핵심 정보
    · db_results   : DB Tool 호출 결과 모음
    · rag_results  : RAG Tool 호출 결과
    · agent_steps  : 어떤 Agent가 무엇을 했는지 적는 실행 기록
    · final_summary: 최종 종합 요약
- db_results와 rag_results를 분리해 두는 이유: "사실 데이터(DB)"와 "절차 근거(RAG)"는
  성격이 다르므로, 나중에 결과를 해석/평가할 때 출처별로 구분하기 위함입니다.

[LangGraph 관점]
- 각 Agent의 run(state)은 LangGraph의 한 Node로 해석할 수 있습니다.
  (State를 입력받아 갱신된 State를 반환하는 노드 → 노드들을 순서대로 연결한 그래프)

[현업 적용 시 확장 방향]
- Agent 간 Handoff 평가, Guardrail(안전 점검), 사람 승인(approval) 흐름 등을 더할 수 있습니다.
  (※ 본 파일에는 안전 검토 Agent가 구현되어 있지 않으며, 그런 확장은 4일차 Guardrail 주제입니다.)

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


# DEFAULT_MODE: Tool 호출 경로 기본값. "fastmcp"면 MCP 서버를 통해 호출합니다.
#   (서버가 없으면 Client의 auto 동작이나 fallback 모드로 바꿔야 합니다.)
DEFAULT_MODE = "fastmcp"
# SAMPLE_USER_QUERY: 직접 실행 시 사용하는 교육용 예시 질문(가상 설비/알람 코드 포함).
SAMPLE_USER_QUERY = "EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생했습니다. 원인과 조치 방향을 알려주세요."
# EDUCATION_NOTICE: 결과물에 항상 붙이는 "교육용 가상 데이터" 고지 문구.
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
    사용자 요청을 받아 Agent들이 함께 사용할 초기 State(dict)를 만듭니다.

    설계 의미:
        - 이 dict가 Agent들 사이를 흐르는 "공유 작업판"입니다.
        - 모든 칸을 미리 만들어 두어, 각 Agent가 자기 칸만 채우면 되도록 합니다.
          (어떤 정보가 오갈지 한눈에 보이는 것이 State 설계의 장점입니다.)
    출력: 빈 값으로 초기화된 State dict
    """
    return {
        "user_query": user_query,   # 원본 사용자 질문
        "equipment_id": None,       # Coordinator가 추출
        "alarm_code": None,         # Coordinator가 추출
        "line_id": None,            # DB 조회 중 설비 정보에서 얻음
        "db_results": {},           # DBInvestigationAgent가 채움 (사실 데이터)
        "rag_results": {},          # ManualRAGAgent가 채움 (절차 근거)
        "agent_steps": [],          # 각 Agent의 실행 기록(흐름 추적용)
        "final_summary": "",        # IncidentSummaryAgent가 채움
        "mode": DEFAULT_MODE,       # 실제 사용된 Tool 호출 모드(실행 시 갱신)
    }


def extract_equipment_id(text: str) -> str | None:
    """
    사용자 요청 문자열에서 EQP-EV-03 같은 교육용 설비 ID 패턴을 정규식으로 찾습니다.

    설계 의미:
        - LLM 없이 규칙(정규식)만으로 핵심 식별자를 뽑는 가장 단순한 추출 방식입니다.
        - 앞뒤로 (?<![A-Z0-9]) / (?![A-Z0-9])를 둬, 더 긴 코드의 일부를 잘못 잡는 것을 막습니다.
    출력: 찾으면 "EQP-..." 문자열, 없으면 None
    """
    if not text:
        return None

    # text.upper()로 대문자 통일 후 매칭해, 소문자로 적힌 경우도 잡습니다.
    match = re.search(r"(?<![A-Z0-9])EQP-[A-Z]{2}-\d{2}(?![A-Z0-9])", text.upper())
    return match.group(0) if match else None


def extract_alarm_code(text: str) -> str | None:
    """
    사용자 요청 문자열에서 ALM-TEMP-402 같은 교육용 알람 코드 패턴을 찾습니다.

    (설비 ID 추출과 같은 규칙 기반 방식이며, 알람 코드 형태에 맞춰 패턴만 다릅니다.)
    출력: 찾으면 "ALM-..." 문자열, 없으면 None
    """
    if not text:
        return None

    match = re.search(r"(?<![A-Z0-9])ALM-[A-Z]{2,10}-\d{2,4}(?![A-Z0-9])", text.upper())
    return match.group(0) if match else None


def add_step(state: dict, agent_name: str, message: str) -> None:
    """
    State의 agent_steps에 "어떤 Agent가 무엇을 했는지" 한 줄을 추가합니다.

    설계 의미:
        - agent_steps는 실행 흐름을 사람이 따라 읽을 수 있게 남기는 기록(trace)입니다.
        - 결과만 보는 것이 아니라 "누가 무엇을 했고 어디서 막혔는지"를 해석하는 근거가 됩니다.
          ([ERROR]/[WARN] 같은 표식을 메시지에 넣어 문제 지점을 구분합니다.)
    """
    state["agent_steps"].append(f"{agent_name}: {message}")


def load_tool_caller(mode: str = DEFAULT_MODE):
    """
    실행 모드에 맞는 "Tool 호출 함수"를 골라 돌려줍니다.

    설계 의미:
        - Agent들은 자기가 어떤 경로(MCP/fallback)로 Tool을 부르는지 몰라도 되도록,
          여기서 call_tool 함수 자체를 주입(inject)해 줍니다. (의존성 주입)
        - 그래서 DBInvestigationAgent/ManualRAGAgent는 받은 call_tool만 호출하면 됩니다.

    입력: mode("fastmcp"/"fallback"/"server")
    출력: (call_tool 함수, 실제로 정해진 모드 문자열) 튜플

    분기 설명:
        - "server"라고 들어오면 fastmcp로 해석합니다(같은 의미의 별칭 처리).
        - "fallback"이면 fallback registry의 call_tool을, 그 외에는 MCP Client의 call_tool을 씁니다.
    """
    requested_mode = str(mode or DEFAULT_MODE).strip().lower()

    # "server"는 fastmcp의 별칭으로 취급합니다.
    if requested_mode == "server":
        requested_mode = "fastmcp"

    # fallback 모드: 서버 없이 Python 함수로 직접 호출하는 경로
    if requested_mode == "fallback":
        from src.day3.tool_registry_fallback import call_tool

        return call_tool, "fallback"

    # 기본: MCP Client를 통한 호출 경로
    from src.day3.manufacturing_mcp_client import call_tool

    return call_tool, "fastmcp"


def get_tool_data(result):
    """
    Tool 응답에서 "실제 알맹이 데이터"를 꺼내는 정규화 헬퍼입니다.

    왜 필요한가:
        - 호출 경로(FastMCP vs fallback)나 Tool에 따라 결과 형태가 조금씩 다릅니다.
          (어떤 건 {"status":"success","data":...}, 어떤 건 {"data":...}, 어떤 건 그냥 값)
        - 요약 Agent가 형태마다 다르게 처리하지 않도록, 여기서 data 부분을 통일해 꺼냅니다.
    출력: 감싸진 data 또는 원본 그대로
    """
    # 표준 성공 응답: {"status": "success", "data": ...}
    if isinstance(result, dict) and result.get("status") == "success":
        return result.get("data")

    # data 키만 있는 경우
    if isinstance(result, dict) and "data" in result:
        return result["data"]

    # 그 외에는 받은 값을 그대로 데이터로 간주합니다.
    return result


def count_items(data) -> int:
    """
    Tool 결과에서 "몇 건인지"를 세는 헬퍼입니다.

    설계 의미:
        - 요약문에 "알람 N건, 공정 상태 M건..."처럼 건수를 적기 위한 공통 계산기입니다.
        - 데이터가 list면 길이를, dict면 미리 약속된 count 키나 list 키를 보고 셉니다.
          (서버 래퍼가 event_count 등으로 건수를 함께 주므로 이를 우선 활용)
    출력: 항목 개수(정수). 셀 수 없으면 0.
    """
    if isinstance(data, list):
        return len(data)

    if isinstance(data, dict):
        # 1순위: 서버가 넣어 준 *_count 정수 값을 그대로 사용
        for count_key in ["event_count", "status_count", "metric_count", "maintenance_count", "result_count"]:
            value = data.get(count_key)
            if isinstance(value, int):
                return value

        # 2순위: 목록 키를 찾아 그 길이로 셈
        for list_key in ["events", "statuses", "metrics", "maintenance_history", "results"]:
            value = data.get(list_key)
            if isinstance(value, list):
                return len(value)

    return 0


class CoordinatorAgent:
    """
    [요청 분석 Agent] 사용자 요청에서 후속 처리에 필요한 핵심 정보를 추출합니다.

    책임:
        - user_query에서 equipment_id, alarm_code를 뽑아 State에 적습니다.
        - 이후 DB/RAG Agent가 무엇을 조회해야 할지의 출발점을 만듭니다.
    State 변화: equipment_id, alarm_code, agent_steps를 기록합니다.
    LangGraph 관점: 그래프의 첫 입력 처리 Node에 해당합니다.
    """

    agent_name = "CoordinatorAgent"

    def run(self, state: dict) -> dict:
        # State에서 원본 질문을 읽어 옵니다. (State 읽기)
        user_query = state.get("user_query", "")

        # 규칙 기반 추출로 핵심 식별자를 뽑습니다.
        equipment_id = extract_equipment_id(user_query)
        alarm_code = extract_alarm_code(user_query)

        # 추출 결과를 State에 기록합니다. (State 쓰기)
        state["equipment_id"] = equipment_id
        state["alarm_code"] = alarm_code

        # equipment_id가 없으면 이후 DB 조회 자체가 불가하므로 ERROR로 남깁니다.
        if equipment_id is None:
            add_step(state, self.agent_name, "[ERROR] equipment_id를 찾을 수 없습니다.")

        # alarm_code는 없어도 전체 알람을 볼 수 있으므로 WARN 수준으로 남깁니다.
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
    [DB 조사 Agent] 설비/알람/공정/정비/품질 같은 "사실 데이터"를 DB Tool로 수집합니다.

    책임:
        - Coordinator가 추출한 equipment_id/alarm_code로 여러 DB Tool을 순서대로 호출합니다.
        - 결과는 모두 state["db_results"]의 칸에 나눠 담습니다.
    설계:
        - 생성자에서 call_tool 함수를 주입받습니다. 그래서 이 Agent는 MCP/fallback 어느
          경로로 호출되는지 몰라도 됩니다. (load_tool_caller가 정해 줌)
    """

    agent_name = "DBInvestigationAgent"

    def __init__(self, call_tool_func) -> None:
        # 어떤 경로로 Tool을 호출할지는 외부에서 주입받습니다(의존성 주입).
        self.call_tool = call_tool_func

    def run(self, state: dict) -> dict:
        equipment_id = state.get("equipment_id")
        alarm_code = state.get("alarm_code")

        # equipment_id가 없으면 DB 조회의 기준이 없으므로 전체 DB 단계를 건너뜁니다.
        # (이 가드가 없으면 빈 ID로 무의미한 조회를 하게 됩니다.)
        if not equipment_id:
            add_step(state, self.agent_name, "[ERROR] equipment_id가 없어 DB Tool 호출을 건너뜁니다.")
            return state

        # 1) 설비 기본 정보 조회 → db_results에 저장
        equipment_status = self.call_tool("get_equipment_status", {"equipment_id": equipment_id})
        state["db_results"]["equipment_status"] = equipment_status

        # 설비 정보에서 line_id를 뽑아 State에 올려 둡니다.
        # 이 line_id는 아래 품질 지표 조회의 입력으로 쓰입니다. (Tool 간 데이터 연결고리)
        equipment_data = get_tool_data(equipment_status)
        if isinstance(equipment_data, dict):
            state["line_id"] = equipment_data.get("line_id")

        # 2) 최근 알람 이력 조회 (alarm_code가 있으면 해당 알람으로 좁혀짐)
        recent_alarm_events = self.call_tool(
            "get_recent_alarm_events",
            {"equipment_id": equipment_id, "alarm_code": alarm_code, "limit": 5},
        )
        state["db_results"]["recent_alarm_events"] = recent_alarm_events

        # 3) 최근 공정 상태 조회
        process_status = self.call_tool(
            "get_process_status",
            {"equipment_id": equipment_id, "limit": 3},
        )
        state["db_results"]["process_status"] = process_status

        # 4) 최근 정비 이력 조회
        maintenance_history = self.call_tool(
            "get_maintenance_history",
            {"equipment_id": equipment_id, "limit": 3},
        )
        state["db_results"]["maintenance_history"] = maintenance_history

        # 5) 품질 지표는 line_id가 있어야만 조회 가능합니다(품질은 라인 단위).
        #    line_id를 못 구했으면 이 단계만 건너뛰고 WARN으로 남깁니다.
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
    [RAG 조사 Agent] search_manual Tool로 "조치 절차/기술 문서 근거"를 검색합니다.

    책임:
        - alarm_code와 사용자 질문을 입력으로 RAG Tool을 호출하고,
          결과를 state["rag_results"]에 저장합니다.
    DB Agent와의 차이:
        - DB Agent는 "현장의 사실"을, 이 Agent는 "대응 지식/절차"를 모읍니다.
          그래서 결과 칸도 db_results와 분리합니다.
    """

    agent_name = "ManualRAGAgent"

    def __init__(self, call_tool_func) -> None:
        # DB Agent와 동일하게 call_tool 함수를 주입받습니다.
        self.call_tool = call_tool_func

    def run(self, state: dict) -> dict:
        alarm_code = state.get("alarm_code")
        user_query = state.get("user_query", "")

        # search_manual에 넘길 입력을 구성합니다.
        # symptom은 알람 코드가 있을 때만 교육용 예시 증상을 넣어 검색 신호를 보강합니다.
        # (현업에서는 실제 증상 텍스트나 분류된 증상 코드를 넣게 됩니다.)
        tool_input = {
            "alarm_code": alarm_code,
            "symptom": "temperature abnormal" if alarm_code else None,
            "query": user_query,
            "top_k": 3,
        }

        # RAG Tool 호출 결과를 통째로 rag_results에 저장합니다.
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
