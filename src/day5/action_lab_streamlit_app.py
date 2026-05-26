"""
Day5 Agent Action Lab Streamlit App

5일차 Agent Action Lab을 로컬 Streamlit UI로 실행하고 결과를 확인하는 선택 실습 파일입니다.

사전 설치:
    pip install streamlit

실행 명령:
    streamlit run src/day5/action_lab_streamlit_app.py

주의:
- 실제 사내 데이터나 민감정보를 사용하지 않습니다.
- 외부 LLM API, PostgreSQL, MCP Server, Chroma, Ollama, Notion API, 외부 SaaS API를 호출하지 않습니다.
- 로컬 Python 함수와 outputs/day5 폴더의 교육용 결과 파일만 사용합니다.
"""

from pathlib import Path
import json
import sys
from datetime import datetime

try:
    import streamlit as st
except ImportError:
    print("[Day5 Agent Action Lab UI]")
    print("Streamlit이 설치되어 있지 않습니다.")
    print("아래 명령으로 설치한 뒤 다시 실행해 주세요.")
    print("pip install streamlit")
    raise SystemExit(1)


ACTION_MAP = {
    "원인 후보 랭킹": "root_cause_ranking",
    "조치 체크리스트": "checklist_generation",
    "담당 부서 라우팅": "team_routing",
    "재발 감시 조건": "monitoring_rule_generation",
    "Agent 자기 점검": "self_review",
}

SOURCE_FILES = [
    "src/day5/final_mcp_multi_agent.py",
    "src/day5/final_agent_action_lab.py",
    "src/day5/final_edge_case_runner.py",
    "src/day5/final_trace_reviewer.py",
    "src/day5/action_lab_streamlit_app.py",
]

OUTPUT_FILES = [
    "outputs/day5/final_incident_report.md",
    "outputs/day5/action_lab_result.md",
    "outputs/day5/action_lab_result.json",
    "outputs/day5/action_lab_trace.jsonl",
    "outputs/day5/edge_case_test_results.md",
    "outputs/day5/edge_case_test_results.json",
    "outputs/day5/final_trace_summary.md",
    "outputs/day5/final_trace_summary.json",
]


# 현재 파일 위치를 기준으로 프로젝트 루트를 찾습니다.
def find_project_root():
    """
    src/day5/action_lab_streamlit_app.py 기준으로 프로젝트 루트를 계산합니다.
    C 드라이브, F 드라이브 등 위치가 바뀌어도 코드 수정 없이 동작하게 하기 위한 함수입니다.
    """
    return Path(__file__).resolve().parents[2]


# day5 모듈을 import할 수 있도록 src 폴더를 Python 경로에 추가합니다.
def add_src_to_python_path(project_root):
    """
    Streamlit은 실행 위치에 따라 import 경로가 달라질 수 있습니다.
    그래서 프로젝트의 src 폴더를 sys.path에 안전하게 추가합니다.
    """
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


# outputs/day5 폴더 경로를 반환합니다.
def get_output_dir(project_root):
    """
    5일차 결과 파일이 저장되는 outputs/day5 폴더를 반환합니다.
    폴더가 없으면 화면에서 파일 없음으로 표시할 수 있게 생성합니다.
    """
    output_dir = project_root / "outputs" / "day5"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# 오류 메시지에서 민감정보처럼 보이는 내용을 가립니다.
def safe_error_preview(error, max_length=500):
    """
    오류 메시지에 token, password, api key 같은 표현이 있으면 그대로 보여주지 않습니다.
    교육용 UI라도 민감정보가 노출되지 않게 하기 위한 함수입니다.
    """
    text = str(error)
    lowered = text.lower()
    sensitive_words = ["api_key", "api key", "token", "password", "secret", "authorization", "bearer"]
    for word in sensitive_words:
        if word in lowered:
            return "[MASKED_SECRET] 민감정보처럼 보이는 내용이 포함되어 오류 상세를 숨겼습니다."
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


# 텍스트 파일을 안전하게 읽습니다.
def safe_read_text(path):
    """
    Markdown 같은 텍스트 파일을 읽습니다.
    파일이 없거나 인코딩 문제가 있어도 앱이 멈추지 않도록 dict로 상태를 반환합니다.
    """
    file_path = Path(path)
    if not file_path.exists():
        return {"exists": False, "content": "", "error": None}

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return {"exists": True, "content": file_path.read_text(encoding=encoding), "error": None}
        except Exception as error:
            last_error = error
    return {"exists": True, "content": "", "error": safe_error_preview(last_error)}


# JSON 파일을 안전하게 읽습니다.
def safe_read_json(path):
    """
    JSON 파일을 읽어 dict 또는 list로 반환합니다.
    파싱에 실패해도 화면 전체가 중단되지 않게 처리합니다.
    """
    text_result = safe_read_text(path)
    if not text_result.get("exists"):
        return {"exists": False, "data": None, "error": None}
    if text_result.get("error"):
        return {"exists": True, "data": None, "error": text_result.get("error")}
    try:
        return {"exists": True, "data": json.loads(text_result.get("content", "")), "error": None}
    except Exception as error:
        return {"exists": True, "data": None, "error": safe_error_preview(error)}


# JSONL 파일을 한 줄씩 안전하게 읽습니다.
def safe_read_jsonl(path):
    """
    JSONL은 한 줄에 JSON 하나가 들어 있는 형식입니다.
    깨진 줄은 건너뛰고 broken_rows 수만 표시합니다.
    """
    text_result = safe_read_text(path)
    if not text_result.get("exists"):
        return {"exists": False, "records": [], "broken_rows": 0, "error": None}
    if text_result.get("error"):
        return {"exists": True, "records": [], "broken_rows": 0, "error": text_result.get("error")}

    records = []
    broken_rows = 0
    for line in text_result.get("content", "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            broken_rows += 1
    return {"exists": True, "records": records, "broken_rows": broken_rows, "error": None}


# 파일 하나의 존재 상태를 확인합니다.
def file_status(project_root, relative_path):
    """
    Streamlit 표에 보여주기 좋은 파일 상태 dict를 만듭니다.
    """
    path = project_root / relative_path
    return {
        "file": relative_path,
        "status": "생성됨" if path.exists() else "아직 없음",
        "exists": path.exists(),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if path.exists() else "-",
    }


# 실행 파일과 출력 파일 상태를 모읍니다.
def collect_file_statuses(project_root):
    """
    수강생이 어떤 파일이 준비되었고 어떤 결과 파일이 아직 없는지 한눈에 볼 수 있게 합니다.
    """
    source_statuses = [file_status(project_root, item) for item in SOURCE_FILES]
    output_statuses = [file_status(project_root, item) for item in OUTPUT_FILES]
    return {"source_files": source_statuses, "output_files": output_statuses}


# final_agent_action_lab.py의 실행 함수를 import합니다.
def import_action_lab_runner(project_root):
    """
    subprocess나 input() 기반 CLI를 사용하지 않고, Python 함수를 직접 import해서 호출합니다.
    import에 실패하면 앱이 멈추지 않도록 오류 정보를 반환합니다.
    """
    add_src_to_python_path(project_root)
    try:
        from day5.final_agent_action_lab import run_action_by_type
        return {"success": True, "runner": run_action_by_type, "error": None}
    except Exception as error:
        return {"success": False, "runner": None, "error": safe_error_preview(error)}


# 사용자가 선택한 Agent Action을 실행합니다.
def run_selected_agent_action(project_root, action_type):
    """
    UI에서 선택한 action_type을 final_agent_action_lab.py의 run_action_by_type()으로 실행합니다.
    실패해도 Streamlit 앱 전체가 중단되지 않게 결과 dict를 반환합니다.
    """
    imported = import_action_lab_runner(project_root)
    if not imported.get("success"):
        return {
            "success": False,
            "error": "final_agent_action_lab.py에서 run_action_by_type 함수를 찾을 수 없습니다. 먼저 final_agent_action_lab.py에 Streamlit 연동용 run_action_by_type(action_type) 함수가 추가되어 있는지 확인해 주세요.",
            "detail": imported.get("error"),
            "result": None,
        }
    try:
        result = imported["runner"](action_type)
        return {"success": True, "error": None, "detail": None, "result": result}
    except Exception as error:
        return {"success": False, "error": "Agent Action 실행 중 오류가 발생했습니다.", "detail": safe_error_preview(error), "result": None}


# 여러 값을 카드처럼 표시합니다.
def render_metric_cards(items):
    """
    Streamlit columns를 이용해 작은 지표 카드를 만듭니다.
    items는 [(제목, 값), ...] 형태로 전달합니다.
    """
    if not items:
        return
    columns = st.columns(len(items))
    for column, item in zip(columns, items):
        label, value = item
        column.metric(label, value)


# 상단 제목과 보안 안내를 표시합니다.
def render_header():
    """
    앱의 목적과 보안 안내를 화면 상단에 보여줍니다.
    """
    st.title("Day5 Manufacturing Agent Action Lab")
    st.caption("Agent Action을 선택 실행하고, 결과·Trace·Guardrail 검증을 한 화면에서 확인하는 교육용 로컬 UI입니다.")
    st.info(
        "본 UI는 실제 사내 데이터가 아닌 교육용 가상 디스플레이 박막 제조 시나리오 결과만 표시합니다. "
        "외부 API를 호출하지 않으며, 로컬 Python 함수와 outputs/day5 파일만 사용합니다."
    )
    st.markdown(
        "- 본 실습은 OLED 박막 증착 공정, 챔버 온도 편차, 진공도 변동, 증착률 변동, "
        "박막 두께 균일도, 파티클 증가 가능성, 품질 지표 관찰 같은 일반화된 제조 맥락을 사용합니다.\n"
        "- 실제 회사명, 실제 내부 라인명, 실제 설비명, 실제 레시피, 실제 수율, 실제 운영 데이터는 사용하지 않습니다."
    )


# 사이드바를 표시합니다.
def render_sidebar(project_root, output_dir):
    """
    프로젝트 경로, 결과 파일 상태, 권장 실행 순서를 사이드바에 표시합니다.
    """
    statuses = collect_file_statuses(project_root)
    output_done = sum(1 for item in statuses["output_files"] if item.get("exists"))
    output_total = len(statuses["output_files"])

    st.sidebar.title("Day5 Agent Action Lab UI")
    st.sidebar.write("**프로젝트 루트 경로**")
    st.sidebar.code(str(project_root))
    st.sidebar.write("**outputs/day5 경로**")
    st.sidebar.code(str(output_dir))
    st.sidebar.write("**결과 파일 생성 상태 요약**")
    st.sidebar.write(f"{output_done} / {output_total} 생성됨")

    st.sidebar.write("**권장 실행 순서**")
    st.sidebar.code(
        "python src/day5/final_mcp_multi_agent.py\n"
        "python src/day5/final_agent_action_lab.py\n"
        "python src/day5/final_edge_case_runner.py\n"
        "python src/day5/final_trace_reviewer.py\n"
        "streamlit run src/day5/action_lab_streamlit_app.py"
    )

    if st.sidebar.button("결과 파일 다시 읽기"):
        st.rerun()

    st.sidebar.warning(
        "본 UI는 로컬 파일과 로컬 Python 함수를 사용하는 교육용 화면입니다. "
        "외부 API를 호출하지 않으며 실제 사내 데이터나 민감정보를 사용하지 않습니다."
    )
    st.sidebar.caption("Streamlit이 없다면 먼저 실행: pip install streamlit")


# Action 선택 UI를 표시합니다.
def render_action_selector():
    """
    사용자가 실행할 Agent Action을 고르게 합니다.
    자유 입력창을 만들지 않고 정해진 5개 옵션만 제공합니다.
    """
    label = st.radio("실행할 Agent Action을 선택하세요.", list(ACTION_MAP.keys()), horizontal=False)
    return label, ACTION_MAP[label]


# 탭 1: Agent Action 실행 화면입니다.
def render_action_result_tab(project_root):
    """
    선택한 Agent Action을 직접 실행하고 결과 Markdown을 화면에 표시합니다.
    """
    st.subheader("Agent Action 실행")
    st.write("이 탭은 사용자가 선택한 Agent Action을 직접 실행합니다. 같은 제조 이상 상황이라도 업무 목적에 따라 결과가 달라지는 것을 확인할 수 있습니다.")

    label, action_type = render_action_selector()
    st.write(f"선택한 Action: **{label}** (`{action_type}`)")

    if st.button("선택한 Agent Action 실행", type="primary"):
        with st.spinner("Agent Action을 실행하는 중입니다..."):
            run_result = run_selected_agent_action(project_root, action_type)
        if not run_result.get("success"):
            st.error(run_result.get("error"))
            if run_result.get("detail"):
                st.caption(run_result.get("detail"))
        else:
            st.success("선택한 Agent Action 실행이 완료되었습니다.")
            result = run_result.get("result") or {}
            if isinstance(result, dict):
                render_metric_cards([
                    ("action_type", result.get("action_type", action_type)),
                    ("action_name", result.get("action_name", label)),
                    ("status", result.get("status", "-")),
                ])
                output_files = result.get("output_files", {})
                guardrail_result = result.get("guardrail_result", {})
                with st.expander("실행 결과 요약 보기", expanded=True):
                    st.write("**output_files**")
                    st.json(output_files)
                    st.write("**guardrail_result**")
                    st.json(guardrail_result)
                markdown_text = result.get("markdown_text") or ""
            else:
                markdown_text = ""

            if not markdown_text:
                fallback_path = project_root / "outputs" / "day5" / "action_lab_result.md"
                markdown_text = safe_read_text(fallback_path).get("content", "")
            if markdown_text:
                st.markdown(markdown_text)
            else:
                st.info("실행은 완료되었지만 표시할 Markdown 결과를 찾지 못했습니다.")

    st.markdown("### 권장 실행 순서")
    st.code(
        "python src/day5/final_mcp_multi_agent.py\n"
        "python src/day5/final_agent_action_lab.py\n"
        "python src/day5/final_edge_case_runner.py\n"
        "python src/day5/final_trace_reviewer.py\n"
        "streamlit run src/day5/action_lab_streamlit_app.py"
    )


# 탭 2: Action JSON 결과를 표시합니다.
def render_json_result_tab(project_root):
    """
    outputs/day5/action_lab_result.json 파일을 읽어 요약과 전체 JSON을 표시합니다.
    """
    st.subheader("Action JSON 결과")
    path = project_root / "outputs" / "day5" / "action_lab_result.json"
    result = safe_read_json(path)
    if not result.get("exists"):
        st.info("아직 outputs/day5/action_lab_result.json 파일이 없습니다. 먼저 탭 1에서 Agent Action을 실행하거나 아래 명령을 실행해 주세요.")
        st.code("python src/day5/final_agent_action_lab.py")
        return
    if result.get("error"):
        st.error(result.get("error"))
        return

    data = result.get("data") or {}
    render_metric_cards([
        ("action_type", data.get("action_type", "-")),
        ("action_name", data.get("action_name", "-")),
        ("used_tools", len(data.get("used_tools", []) or [])),
    ])
    st.write("**used_tools**")
    st.write(data.get("used_tools", []))
    st.write("**education_message**")
    st.write(data.get("education_message", "-"))

    scenario = data.get("scenario", {}) if isinstance(data, dict) else {}
    if scenario:
        st.write("**scenario**")
        st.json({
            "equipment_id": scenario.get("equipment_id"),
            "alarm_code": scenario.get("alarm_code"),
            "process_name": scenario.get("process_name"),
        })

    with st.expander("JSON 전체 보기"):
        st.json(data)


# 탭 3: Action Trace를 표시합니다.
def render_trace_tab(project_root):
    """
    outputs/day5/action_lab_trace.jsonl 파일을 읽어 Trace 목록과 가장 최근 Trace를 표시합니다.
    """
    st.subheader("Action Trace")
    path = project_root / "outputs" / "day5" / "action_lab_trace.jsonl"
    result = safe_read_jsonl(path)
    if not result.get("exists"):
        st.info("아직 outputs/day5/action_lab_trace.jsonl 파일이 없습니다. 먼저 탭 1에서 Agent Action을 실행하거나 아래 명령을 실행해 주세요.")
        st.code("python src/day5/final_agent_action_lab.py")
        return
    if result.get("error"):
        st.error(result.get("error"))
        return

    records = result.get("records", [])
    broken_rows = result.get("broken_rows", 0)
    render_metric_cards([("Trace 이벤트 수", len(records)), ("깨진 JSONL 줄 수", broken_rows)])

    if not records:
        st.info("표시할 Trace record가 없습니다.")
        return

    latest = records[-1]
    st.markdown("### 가장 최근 Trace")
    guardrail = latest.get("guardrail_result", {}) if isinstance(latest, dict) else {}
    st.json({
        "action_type": latest.get("action_type"),
        "action_name": latest.get("action_name"),
        "scenario_id": latest.get("scenario_id"),
        "equipment_id": latest.get("equipment_id"),
        "alarm_code": latest.get("alarm_code"),
        "used_tools": latest.get("used_tools"),
        "status": latest.get("status"),
        "guardrail_blocked": guardrail.get("blocked") if isinstance(guardrail, dict) else None,
    })

    table_records = []
    for item in records:
        guardrail_item = item.get("guardrail_result", {}) if isinstance(item, dict) else {}
        table_records.append({
            "action_type": item.get("action_type"),
            "action_name": item.get("action_name"),
            "scenario_id": item.get("scenario_id"),
            "equipment_id": item.get("equipment_id"),
            "alarm_code": item.get("alarm_code"),
            "used_tools": ", ".join(item.get("used_tools", []) or []),
            "status": item.get("status"),
            "guardrail_blocked": guardrail_item.get("blocked") if isinstance(guardrail_item, dict) else None,
        })
    st.dataframe(table_records, use_container_width=True)


# 탭 4: Edge Case / Guardrail 결과를 표시합니다.
def render_edge_case_tab(project_root):
    """
    final_edge_case_runner.py가 만든 Markdown/JSON 결과를 화면에 표시합니다.
    """
    st.subheader("Edge Case / Guardrail")
    json_path = project_root / "outputs" / "day5" / "edge_case_test_results.json"
    md_path = project_root / "outputs" / "day5" / "edge_case_test_results.md"

    json_result = safe_read_json(json_path)
    md_result = safe_read_text(md_path)

    if not json_result.get("exists") and not md_result.get("exists"):
        st.info("아직 Edge Case 결과 파일이 없습니다. 먼저 아래 명령을 실행해 주세요.")
        st.code("python src/day5/final_edge_case_runner.py")
        return

    if json_result.get("exists") and not json_result.get("error"):
        data = json_result.get("data") or {}
        summary = data.get("summary", {}) if isinstance(data, dict) else {}
        render_metric_cards([
            ("전체 케이스 수", summary.get("total_cases", 0)),
            ("Guardrail 차단 수", summary.get("guardrail_blocked_count", 0)),
            ("Tool 실행 수", summary.get("tool_execution_count", 0)),
            ("추가 정보 필요", summary.get("need_more_info_count", 0)),
        ])
        rows = []
        for item in data.get("results", []) if isinstance(data, dict) else []:
            rows.append({
                "case_id": item.get("case_id"),
                "title": item.get("title"),
                "guardrail_code": item.get("guardrail_code"),
                "blocked": item.get("blocked"),
                "final_judgement": item.get("final_judgement"),
                "passed_expected_behavior": item.get("passed_expected_behavior"),
            })
        if rows:
            st.dataframe(rows, use_container_width=True)
    elif json_result.get("error"):
        st.error(json_result.get("error"))

    if md_result.get("exists") and md_result.get("content"):
        st.markdown(md_result.get("content"))


# 탭 5: Final Report Action 결과를 표시합니다.
def render_final_report_tab(project_root):
    """
    final_mcp_multi_agent.py가 만든 리포트 생성형 Action 결과를 표시합니다.
    """
    st.subheader("Final Report Action")
    st.info("이 리포트는 Agent의 여러 Action 중 하나인 ‘리포트 생성형 Action’입니다.")
    report_path = project_root / "outputs" / "day5" / "final_incident_report.md"
    review_path = project_root / "outputs" / "day5" / "final_tool_control_review.md"

    report = safe_read_text(report_path)
    if not report.get("exists"):
        st.info("아직 outputs/day5/final_incident_report.md 파일이 없습니다. 먼저 아래 명령을 실행해 주세요.")
        st.code("python src/day5/final_mcp_multi_agent.py")
    elif report.get("error"):
        st.error(report.get("error"))
    else:
        st.markdown(report.get("content", ""))

    review = safe_read_text(review_path)
    if review.get("exists") and review.get("content"):
        with st.expander("final_tool_control_review.md 보기"):
            st.markdown(review.get("content"))


# 탭 6: 실행 파일과 출력 파일 상태를 표시합니다.
def render_file_status_tab(project_root):
    """
    실습에 필요한 Python 파일과 결과 파일이 존재하는지 표로 표시합니다.
    """
    st.subheader("실행 파일 상태 점검")
    statuses = collect_file_statuses(project_root)
    st.markdown("### Python 실행 파일")
    st.dataframe(statuses["source_files"], use_container_width=True)
    st.markdown("### 출력 결과 파일")
    st.dataframe(statuses["output_files"], use_container_width=True)
    st.markdown("### 권장 실행 순서")
    st.code(
        "python src/day5/final_mcp_multi_agent.py\n"
        "python src/day5/final_agent_action_lab.py\n"
        "python src/day5/final_edge_case_runner.py\n"
        "python src/day5/final_trace_reviewer.py\n"
        "streamlit run src/day5/action_lab_streamlit_app.py"
    )


# 탭 7: 사내 PoC 전환 메모를 표시합니다.
def render_poc_memo_tab():
    """
    교육용 데모를 실제 사내 PoC로 전환할 때 고려할 점을 정리합니다.
    """
    st.markdown(
        "# 사내 PoC 전환 시 고려사항\n\n"
        "- 교육용 fallback Tool은 실제 PoC에서 내부 API 또는 MCP Server로 대체할 수 있습니다.\n"
        "- 교육용 Markdown 문서는 실제 PoC에서 내부 기술문서 저장소나 사내 검색 시스템으로 대체할 수 있습니다.\n"
        "- 교육용 Trace는 실제 PoC에서 감사 로그, 실행 이력, 모니터링 지표로 확장할 수 있습니다.\n"
        "- Streamlit UI는 교육용 데모 화면이며, 실제 사내 적용 시에는 내부 포털, 사내 Wiki, Dashboard, 운영 시스템 UI로 대체할 수 있습니다.\n"
        "- 실제 사내 데이터, 실제 라인명, 실제 설비명, 실제 레시피, 실제 수율은 승인 없이 외부 도구나 개인 PC에 저장하면 안 됩니다.\n"
        "- 실제 적용 시에는 내부 표준 절차, 보안 정책, 품질 기준, 승인 체계가 필요합니다."
    )


# Streamlit 앱의 전체 흐름입니다.
def main():
    """
    Streamlit 앱을 구성하고 각 탭을 렌더링합니다.
    """
    st.set_page_config(
        page_title="Day5 Agent Action Lab",
        page_icon="🧭",
        layout="wide",
    )

    project_root = find_project_root()
    add_src_to_python_path(project_root)
    output_dir = get_output_dir(project_root)

    render_sidebar(project_root, output_dir)
    render_header()

    tabs = st.tabs([
        "Agent Action 실행",
        "Action JSON 결과",
        "Action Trace",
        "Edge Case / Guardrail",
        "Final Report Action",
        "실행 파일 상태 점검",
        "사내 PoC 전환 메모",
    ])

    with tabs[0]:
        render_action_result_tab(project_root)
    with tabs[1]:
        render_json_result_tab(project_root)
    with tabs[2]:
        render_trace_tab(project_root)
    with tabs[3]:
        render_edge_case_tab(project_root)
    with tabs[4]:
        render_final_report_tab(project_root)
    with tabs[5]:
        render_file_status_tab(project_root)
    with tabs[6]:
        render_poc_memo_tab()


if __name__ == "__main__":
    main()
