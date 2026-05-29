"""
Day3 Multi-Agent 제조 장애 대응 Streamlit App

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.

실행 방법:

터미널 1:
cd C:\work\manufacturing_agent_project
conda activate manufacturing_agent_env
python src/day3/manufacturing_mcp_server.py

터미널 2:
cd C:\work\manufacturing_agent_project
conda activate manufacturing_agent_env
set MCP_MODE=fastmcp
set MCP_FASTMCP_URL=http://127.0.0.1:8765/mcp
streamlit run src/day3/day3_multi_agent_streamlit_app.py

fallback 모드 실행:
set MCP_MODE=fallback
streamlit run src/day3/day3_multi_agent_streamlit_app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st


DEFAULT_USER_QUERY = (
    "EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생했습니다. "
    "원인과 조치 방향을 알려주세요."
)

FASTMCP_URL = "http://127.0.0.1:8765/mcp"


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 폴더를 반환합니다.
    """
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = get_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.day3.multi_agent_roles import run_multi_agent_flow, save_result_markdown


def show_sidebar() -> str:
    """
    Sidebar에서 실행 모드를 선택합니다.
    """
    st.sidebar.header("실행 설정")

    mode = st.sidebar.radio(
        "실행 모드 선택",
        options=["fastmcp", "fallback"],
        index=0,
        help="fastmcp는 standalone FastMCP 서버가 먼저 실행되어야 합니다.",
    )

    st.sidebar.divider()

    st.sidebar.subheader("FastMCP URL")
    st.sidebar.code(FASTMCP_URL)

    st.sidebar.subheader("서버 실행 명령")
    st.sidebar.code(
        "cd C:\\work\\manufacturing_agent_project\n"
        "conda activate manufacturing_agent_env\n"
        "python src/day3/manufacturing_mcp_server.py",
        language="powershell",
    )

    st.sidebar.subheader("Streamlit 실행 명령")
    st.sidebar.code(
        "$env:MCP_MODE=\"fastmcp\"\n"
        "$env:MCP_FASTMCP_URL=\"http://127.0.0.1:8765/mcp\"\n"
        "streamlit run src/day3/day3_multi_agent_streamlit_app.py",
        language="powershell",
    )

    return mode


def show_state_result(state: dict, saved_path: Path | None = None) -> None:
    """
    Multi-Agent 실행 결과를 화면에 표시합니다.
    """
    st.subheader("1. 추출 정보")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("equipment_id", state.get("equipment_id") or "미확인")
    col2.metric("alarm_code", state.get("alarm_code") or "미확인")
    col3.metric("line_id", state.get("line_id") or "미확인")
    col4.metric("mode", state.get("mode") or "미확인")

    st.subheader("2. Agent 실행 단계")
    agent_steps = state.get("agent_steps", [])

    if agent_steps:
        for index, step in enumerate(agent_steps, start=1):
            st.write(f"{index}. {step}")
    else:
        st.info("Agent 실행 단계 기록이 없습니다.")

    st.subheader("3. 최종 요약")
    final_summary = state.get("final_summary", "")

    if final_summary:
        st.markdown(final_summary)
    else:
        st.warning("최종 요약이 아직 생성되지 않았습니다.")

    st.subheader("4. Tool 결과")

    with st.expander("DB Tool 결과 보기", expanded=False):
        st.json(state.get("db_results", {}))

    with st.expander("RAG Tool 결과 보기", expanded=False):
        st.json(state.get("rag_results", {}))

    if saved_path is not None:
        st.success("Markdown 결과 파일을 저장했습니다.")
        st.code(str(saved_path), language="text")


def main() -> None:
    """
    Streamlit 실행 진입점입니다.
    """
    st.set_page_config(
        page_title="Day3 Multi-Agent 제조 장애 대응 실습",
        layout="wide",
    )

    st.title("Day3 Multi-Agent 제조 장애 대응 실습")

    st.info(
        "본 실습은 실제 사내 데이터가 아닌 교육용 가상 제조 시나리오입니다. "
        "fastmcp 모드는 standalone FastMCP 서버가 먼저 실행되어야 합니다."
    )

    mode = show_sidebar()

    if mode == "fastmcp":
        os.environ["MCP_MODE"] = "fastmcp"
        os.environ["MCP_FASTMCP_URL"] = FASTMCP_URL
    else:
        os.environ["MCP_MODE"] = "fallback"

    st.subheader("사용자 질문 입력")

    user_query = st.text_area(
        "질문",
        value=DEFAULT_USER_QUERY,
        height=120,
    )

    run_button = st.button("Multi-Agent 실행", type="primary")

    if run_button:
        with st.spinner("Multi-Agent 실행 중입니다..."):
            state = run_multi_agent_flow(user_query=user_query, mode=mode)
            saved_path = save_result_markdown(state)

        st.session_state["last_state"] = state
        st.session_state["last_saved_path"] = str(saved_path)

        show_state_result(state, saved_path)

    elif "last_state" in st.session_state:
        st.divider()
        st.subheader("마지막 실행 결과")
        last_state = st.session_state["last_state"]
        last_saved_path = st.session_state.get("last_saved_path")
        saved_path = Path(last_saved_path) if last_saved_path else None
        show_state_result(last_state, saved_path)

    else:
        st.caption("왼쪽 실행 모드를 확인한 뒤, 질문을 입력하고 [Multi-Agent 실행] 버튼을 클릭하세요.")


if __name__ == "__main__":
    main()
