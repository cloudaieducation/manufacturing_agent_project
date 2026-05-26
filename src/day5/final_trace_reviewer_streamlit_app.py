"""
Day5 Final Trace Reviewer Dashboard

Streamlit UI for running and reviewing src/day5/final_trace_reviewer.py.

주의:
- 기존 final_trace_reviewer.py는 수정하지 않습니다.
- 기준 파일 내부 함수를 import하지 않습니다.
- subprocess로 CLI 실행 흐름을 그대로 실행합니다.
- 외부 API, DB, MCP Server, LLM API를 호출하지 않습니다.
- pandas, langchain, langgraph, chromadb를 사용하지 않습니다.
"""

from pathlib import Path
import json
import subprocess
import sys

import streamlit as st


# 1
def find_project_root():
    """현재 파일 위치를 기준으로 프로젝트 루트를 계산합니다."""
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if (parent / "src").exists():
            return parent
    return current_path.parents[2]


# 2
def read_json_file(path):
    """JSON 파일을 읽습니다. 파일이 없으면 None을 반환합니다."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


# 3
def read_text_file(path):
    """텍스트 파일을 읽습니다. 파일이 없으면 None을 반환합니다."""
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8-sig")


# 4
def run_trace_reviewer(project_root):
    """기준 Trace Reviewer를 subprocess로 실행합니다."""
    command = [sys.executable, "src/day5/final_trace_reviewer.py"]
    result = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


# 5
def main():
    """Streamlit 화면을 구성합니다."""
    st.set_page_config(page_title="Day5 Final Trace Reviewer Dashboard", layout="wide")

    project_root = find_project_root()
    template_path = project_root / "templates" / "day5" / "final_trace_summary.mustache"
    markdown_path = project_root / "outputs" / "day5" / "final_trace_summary.md"
    json_path = project_root / "outputs" / "day5" / "final_trace_summary.json"

    st.title("Day5 Final Trace Reviewer Dashboard")
    st.markdown(
        """
- 이 화면은 Day5 실습에서 생성된 Trace와 결과 파일을 확인하는 교육용 대시보드입니다.
- `final_mcp_call_trace.jsonl`은 리포트 생성형 Agent의 Tool 실행 흐름을 보여줍니다.
- `action_lab_trace.jsonl`은 원인 후보 랭킹, 체크리스트 생성, 라우팅 같은 업무 Action 실행 흔적을 보여줍니다.
- 실제 사내 데이터가 아닌 교육용 가상 제조 시나리오만 사용합니다.
        """.strip()
    )

    with st.sidebar:
        st.header("실행")
        if st.button("Trace Review 실행", use_container_width=True):
            st.session_state["last_run_result"] = run_trace_reviewer(project_root)
            st.rerun()

        st.divider()
        st.subheader("기준 파일")
        st.code("src/day5/final_trace_reviewer.py")

        st.subheader("결과 파일")
        st.code("outputs/day5/final_trace_summary.md")
        st.code("outputs/day5/final_trace_summary.json")

        st.subheader("템플릿 파일")
        st.code("templates/day5/final_trace_summary.mustache")
        if template_path.exists():
            st.success("템플릿 파일이 있습니다.")
        else:
            st.warning(
                "templates/day5/final_trace_summary.mustache 파일이 없습니다.\n"
                "먼저 템플릿 생성 과정을 확인하세요."
            )

    summary_json = None
    json_error = None
    try:
        summary_json = read_json_file(json_path)
    except Exception as error:
        json_error = error

    markdown_text = read_text_file(markdown_path)

    output_targets = [
        {"name": "final_incident_report", "path": "outputs/day5/final_incident_report.md"},
        {"name": "final_mcp_call_trace", "path": "outputs/day5/final_mcp_call_trace.jsonl"},
        {"name": "action_lab_result_md", "path": "outputs/day5/action_lab_result.md"},
        {"name": "action_lab_result_json", "path": "outputs/day5/action_lab_result.json"},
        {"name": "action_lab_trace", "path": "outputs/day5/action_lab_trace.jsonl"},
        {"name": "edge_case_test_results_md", "path": "outputs/day5/edge_case_test_results.md"},
        {"name": "edge_case_test_results_json", "path": "outputs/day5/edge_case_test_results.json"},
        {"name": "final_trace_summary_md", "path": "outputs/day5/final_trace_summary.md"},
        {"name": "final_trace_summary_json", "path": "outputs/day5/final_trace_summary.json"},
    ]
    direct_outputs = []
    for item in output_targets:
        target_path = project_root / item["path"]
        direct_outputs.append(
            {
                "name": item["name"],
                "status": "생성됨" if target_path.exists() else "없음",
                "path": item["path"],
            }
        )

    tab_summary, tab_tools, tab_outputs, tab_markdown, tab_json, tab_log = st.tabs(
        ["Trace 요약", "Tool 사용 요약", "결과 파일 상태", "Markdown 보고서", "JSON 원본", "실행 로그"]
    )

    with tab_summary:
        st.subheader("Trace 요약")
        if json_error:
            st.error("final_trace_summary.json 파일을 읽는 중 오류가 발생했습니다.")
            with st.expander("오류 상세"):
                st.exception(json_error)
        elif not summary_json:
            st.info("아직 final_trace_summary.json이 생성되지 않았습니다. 사이드바의 [Trace Review 실행] 버튼을 먼저 눌러 주세요.")
        else:
            summary = summary_json.get("summary", {})
            col1, col2, col3 = st.columns(3)
            col1.metric("Final MCP Trace row 수", summary.get("final_trace_count", 0))
            col2.metric("Action Lab Trace row 수", summary.get("action_trace_count", 0))
            col3.metric("전체 Trace row 수", summary.get("total_trace_count", 0))
            col4, col5, col6 = st.columns(3)
            col4.metric("Tool 사용 종류 수", summary.get("tool_kind_count", 0))
            col5.metric("Guardrail 이벤트 수", summary.get("guardrail_event_count", 0))
            col6.metric("깨진 JSONL row 수", summary.get("broken_row_count", 0))

    with tab_tools:
        st.subheader("Tool 사용 요약")
        if json_error:
            st.error("final_trace_summary.json 파일을 읽는 중 오류가 발생했습니다.")
            with st.expander("오류 상세"):
                st.exception(json_error)
        elif not summary_json:
            st.info("아직 결과 파일이 없습니다. 사이드바의 [Trace Review 실행] 버튼을 먼저 눌러 주세요.")
        else:
            tool_counts = summary_json.get("tool_counts", [])
            if tool_counts:
                st.table(tool_counts)
            else:
                st.info("아직 Tool 사용 기록이 없습니다. final_mcp_call_trace.jsonl 또는 action_lab_trace.jsonl이 생성되었는지 확인하세요.")

    with tab_outputs:
        st.subheader("결과 파일 상태")
        if summary_json and isinstance(summary_json.get("outputs"), list):
            st.table(summary_json.get("outputs"))
        else:
            st.table(direct_outputs)
            st.caption("final_trace_summary.json이 없거나 읽을 수 없어 Streamlit 화면에서 직접 파일 존재 여부를 계산했습니다.")

    with tab_markdown:
        st.subheader("Markdown 보고서")
        if markdown_text:
            st.markdown(markdown_text)
        else:
            st.info("아직 final_trace_summary.md가 생성되지 않았습니다. 사이드바의 [Trace Review 실행] 버튼을 먼저 눌러 주세요.")

    with tab_json:
        st.subheader("JSON 원본")
        if json_error:
            st.error("final_trace_summary.json 파일을 읽는 중 오류가 발생했습니다.")
            with st.expander("오류 상세"):
                st.exception(json_error)
        elif summary_json:
            st.json(summary_json)
        else:
            st.info("아직 final_trace_summary.json이 생성되지 않았습니다. 사이드바의 [Trace Review 실행] 버튼을 먼저 눌러 주세요.")

    with tab_log:
        st.subheader("실행 로그")
        last_run_result = st.session_state.get("last_run_result")
        if not last_run_result:
            st.info("아직 Trace Review 실행 로그가 없습니다. 사이드바의 [Trace Review 실행] 버튼을 눌러 주세요.")
        else:
            st.write("실행 명령")
            st.code(last_run_result.get("command", ""))
            st.write(f"returncode: {last_run_result.get('returncode')}")
            with st.expander("stdout"):
                st.code(last_run_result.get("stdout", ""))
            with st.expander("stderr"):
                st.code(last_run_result.get("stderr", ""))


if __name__ == "__main__":
    main()
