"""
Day3 MCP Tool Client 테스트 Streamlit App

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.

FastMCP 서버 실행:
cd C:\work\manufacturing_agent_project
conda activate manufacturing_agent_env
python src/day3/manufacturing_mcp_server.py

Streamlit 실행:
cd C:\work\manufacturing_agent_project
conda activate manufacturing_agent_env
set MCP_MODE=fastmcp
set MCP_FASTMCP_URL=http://127.0.0.1:8765/mcp
streamlit run src/day3/mcp_tool_client_streamlit_app.py

fallback 모드:
set MCP_MODE=fallback
streamlit run src/day3/mcp_tool_client_streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 폴더를 반환합니다.
    """
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = get_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.day3.manufacturing_mcp_client import (
    SUPPORTED_TOOLS,
    TOOL_DESCRIPTIONS,
    call_tool,
    get_mcp_mode,
    get_fastmcp_target,
)


def build_tool_input(tool_name: str) -> dict:
    """
    선택한 Tool 이름에 맞는 입력 폼을 만들고 dict를 반환합니다.
    """
    if tool_name == "get_equipment_status":
        equipment_id = st.text_input("equipment_id", value="EQP-EV-03")
        return {"equipment_id": equipment_id}

    if tool_name == "get_recent_alarm_events":
        equipment_id = st.text_input("equipment_id", value="EQP-EV-03")
        alarm_code = st.text_input("alarm_code", value="ALM-TEMP-402")
        limit = st.number_input("limit", min_value=1, max_value=50, value=5, step=1)
        return {
            "equipment_id": equipment_id,
            "alarm_code": alarm_code,
            "limit": int(limit),
        }

    if tool_name == "get_process_status":
        equipment_id = st.text_input("equipment_id", value="EQP-EV-03")
        limit = st.number_input("limit", min_value=1, max_value=50, value=3, step=1)
        return {
            "equipment_id": equipment_id,
            "limit": int(limit),
        }

    if tool_name == "get_quality_metrics":
        line_id = st.text_input("line_id", value="LINE-07")
        limit = st.number_input("limit", min_value=1, max_value=50, value=3, step=1)
        return {
            "line_id": line_id,
            "limit": int(limit),
        }

    if tool_name == "get_maintenance_history":
        equipment_id = st.text_input("equipment_id", value="EQP-EV-03")
        limit = st.number_input("limit", min_value=1, max_value=50, value=3, step=1)
        return {
            "equipment_id": equipment_id,
            "limit": int(limit),
        }

    if tool_name == "get_equipment_overview":
        equipment_id = st.text_input("equipment_id", value="EQP-EV-03")
        alarm_code = st.text_input("alarm_code", value="ALM-TEMP-402")
        return {
            "equipment_id": equipment_id,
            "alarm_code": alarm_code,
        }

    if tool_name == "search_manual":
        alarm_code = st.text_input("alarm_code", value="ALM-TEMP-402")
        symptom = st.text_input("symptom", value="temperature abnormal")
        top_k = st.number_input("top_k", min_value=1, max_value=10, value=3, step=1)
        return {
            "alarm_code": alarm_code,
            "symptom": symptom,
            "top_k": int(top_k),
        }

    return {}


def build_sample_tool_calls() -> list[dict]:
    """
    7개 Tool을 순서대로 호출하기 위한 샘플 입력을 반환합니다.
    """
    return [
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


def show_result(result) -> None:
    """
    Tool 호출 결과를 화면에 표시합니다.
    """
    if isinstance(result, dict):
        st.json(result)
    else:
        st.write(result)


def show_sidebar() -> None:
    """
    Sidebar에 현재 설정과 실행 명령을 표시합니다.
    """
    st.sidebar.header("실행 정보")

    st.sidebar.subheader("현재 MCP_MODE")
    st.sidebar.code(get_mcp_mode())

    st.sidebar.subheader("FastMCP target")
    st.sidebar.code(get_fastmcp_target())

    st.sidebar.subheader("FastMCP 서버 실행")
    st.sidebar.code(
        "cd C:\\work\\manufacturing_agent_project\n"
        "conda activate manufacturing_agent_env\n"
        "python src/day3/manufacturing_mcp_server.py",
        language="powershell",
    )

    st.sidebar.subheader("Streamlit 실행")
    st.sidebar.code(
        "cd C:\\work\\manufacturing_agent_project\n"
        "conda activate manufacturing_agent_env\n"
        "$env:MCP_MODE=\"fastmcp\"\n"
        "$env:MCP_FASTMCP_URL=\"http://127.0.0.1:8765/mcp\"\n"
        "streamlit run src/day3/mcp_tool_client_streamlit_app.py",
        language="powershell",
    )

    st.sidebar.subheader("fallback 모드")
    st.sidebar.code(
        "$env:MCP_MODE=\"fallback\"\n"
        "streamlit run src/day3/mcp_tool_client_streamlit_app.py",
        language="powershell",
    )


def main() -> None:
    """
    Streamlit 실행 진입점입니다.
    """
    st.set_page_config(
        page_title="Day3 MCP Tool Client 테스트",
        layout="wide",
    )

    st.title("Day3 MCP Tool Client 테스트")

    st.info(
        "본 실습은 실제 사내 데이터가 아닌 교육용 가상 제조 시나리오입니다. "
        "fastmcp 모드는 standalone FastMCP 서버가 먼저 실행되어야 합니다. "
        "fallback 모드는 서버 없이 Python 함수로 직접 Tool을 호출합니다."
    )

    show_sidebar()

    st.subheader("1. Tool 선택")

    tool_name = st.selectbox(
        "호출할 Tool",
        options=SUPPORTED_TOOLS,
    )

    st.caption(TOOL_DESCRIPTIONS.get(tool_name, "교육용 제조 Agent Tool입니다."))

    st.subheader("2. Tool 입력")
    tool_input = build_tool_input(tool_name)

    st.subheader("3. Tool 단일 호출")

    if st.button("Tool 호출", type="primary"):
        with st.spinner(f"{tool_name} 호출 중입니다..."):
            result = call_tool(tool_name, tool_input)

        st.session_state["last_result"] = result
        st.session_state["last_tool_input"] = tool_input
        st.session_state["last_tool_name"] = tool_name

        st.write(f"Tool 이름: `{tool_name}`")
        st.write("입력값:")
        st.json(tool_input)
        st.write("결과:")
        show_result(result)

    if "last_result" in st.session_state:
        with st.expander("마지막 단일 Tool 호출 결과", expanded=False):
            st.write(f"Tool 이름: `{st.session_state.get('last_tool_name')}`")
            st.write("입력값:")
            st.json(st.session_state.get("last_tool_input", {}))
            st.write("결과:")
            show_result(st.session_state["last_result"])

    st.divider()

    st.subheader("4. 7개 Tool 순차 호출")

    if st.button("7개 Tool 순차 호출"):
        sequence_results = []

        with st.spinner("7개 Tool을 순서대로 호출 중입니다..."):
            for sample in build_sample_tool_calls():
                result = call_tool(sample["tool_name"], sample["tool_input"])
                sequence_results.append(
                    {
                        "title": sample["title"],
                        "tool_name": sample["tool_name"],
                        "tool_input": sample["tool_input"],
                        "result": result,
                    }
                )

        st.session_state["last_sequence_results"] = sequence_results

    if "last_sequence_results" in st.session_state:
        for item in st.session_state["last_sequence_results"]:
            with st.expander(item["title"], expanded=False):
                st.write(f"Tool 이름: `{item['tool_name']}`")
                st.write("입력값:")
                st.json(item["tool_input"])
                st.write("결과:")
                show_result(item["result"])


if __name__ == "__main__":
    main()
