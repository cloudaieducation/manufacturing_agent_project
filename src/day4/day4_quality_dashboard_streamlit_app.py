"""
Day4 Quality Dashboard Streamlit App

설치:
    pip install streamlit

실행:
    streamlit run src/day4/day4_quality_dashboard_streamlit_app.py

역할:
- Day4 CLI 실습 파일을 Streamlit 화면에서 subprocess로 실행합니다.
- outputs/day4 결과 파일을 화면에서 확인합니다.
- LLM Tool Selection prompt Mustache 템플릿을 직접 수정하고 저장할 수 있습니다.

주의:
- 기존 Day4 파일은 수정하지 않습니다.
- .env 파일 내용과 API Key는 화면에 표시하지 않습니다.
- LLM 호출은 llm_tool_selector.py를 subprocess로 실행할 때만 발생합니다.
"""

from pathlib import Path
from datetime import datetime
import json
import os
import re
import shutil
import subprocess
import sys

import streamlit as st


STAGE_CONFIGS = {
    "trace_analyzer": {
        "label": "Trace Analyzer",
        "pattern": "trace_analyzer*.py",
        "button": "Trace Analyzer 실행",
    },
    "rule_based_router": {
        "label": "Rule Based Router",
        "pattern": "rule_based_router*.py",
        "button": "Rule Based Router 실행",
    },
    "guardrail": {
        "label": "Guardrail",
        "pattern": "guardrail*.py",
        "button": "Guardrail 실행",
    },
    "llm_tool_selector": {
        "label": "LLM Tool Selector",
        "pattern": "llm_tool_selector*.py",
        "button": "LLM Tool Selector 실행",
    },
    "llm_tool_plan_validator": {
        "label": "Tool Plan Validator",
        "pattern": "llm_tool_plan_validator*.py",
        "button": "Tool Plan Validator 실행",
    },
    "quality_gate_runner": {
        "label": "Quality Gate Runner",
        "pattern": "quality_gate_runner*.py",
        "button": "Quality Gate 실행",
    },
}

REQUIRED_RESULT_FILES = [
    "outputs/day4/trace_summary.json",
    "outputs/day4/rule_based_tool_plan.json",
    "outputs/day4/guardrail_test_results.json",
    "outputs/day4/llm_tool_plan_results.json",
    "outputs/day4/llm_tool_plan_validation_result.json",
    "outputs/day4/quality_gate_result.json",
]

OPTIONAL_MARKDOWN_FILES = [
    "outputs/day4/trace_review_result.md",
    "outputs/day4/rule_based_routing_report.md",
    "outputs/day4/guardrail_report.md",
    "outputs/day4/llm_tool_selection_report_draft.md",
    "outputs/day4/llm_tool_plan_validation_report.md",
    "outputs/day4/mcp_multi_agent_quality_gate.md",
]


# ------------------------------------------------------------
# 공통 유틸리티
# ------------------------------------------------------------
def find_project_root():
    return Path(__file__).resolve().parents[2]


def safe_error_preview(value, max_length=2000):
    text = "" if value is None else str(value)

    # 명확한 secret 패턴만 마스킹합니다.
    # 긴 파일명이나 outputs/day4/*.json, *.md 경로는 마스킹하지 않습니다.
    text = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
        r"\1[MASKED_SECRET]",
        text,
    )
    text = re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9_\-\.]{8,}",
        r"\1[MASKED_SECRET]",
        text,
    )
    text = re.sub(
        r"(?i)(api[_-]?key|api key|token|secret|password|credential)\s*[:=]\s*[^\s,;]+",
        r"\1=[MASKED_SECRET]",
        text,
    )

    if len(text) > max_length:
        return text[:max_length].rstrip() + "..."
    return text


def safe_read_text(path):
    if not path.exists():
        return {
            "exists": False,
            "text": "",
            "error": "파일이 없습니다.",
        }

    last_error = None

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return {
                "exists": True,
                "text": path.read_text(encoding=encoding),
                "error": "",
            }
        except Exception as error:
            last_error = error

    return {
        "exists": True,
        "text": "",
        "error": safe_error_preview(last_error),
    }


def safe_read_json(path):
    text_result = safe_read_text(path)
    if not text_result["exists"]:
        return {
            "exists": False,
            "data": None,
            "error": text_result["error"],
        }

    if text_result["error"]:
        return {
            "exists": True,
            "data": None,
            "error": text_result["error"],
        }

    text = text_result["text"].lstrip("\ufeff")

    if not text.strip():
        return {
            "exists": True,
            "data": None,
            "error": "JSON 파일 내용이 비어 있습니다.",
        }

    try:
        return {
            "exists": True,
            "data": json.loads(text),
            "error": "",
        }
    except Exception as error:
        return {
            "exists": True,
            "data": None,
            "error": safe_error_preview(error),
        }


def make_display_rows(items, columns=None):
    rows = []
    if not isinstance(items, list):
        return rows

    for item in items:
        if not isinstance(item, dict):
            rows.append({"value": str(item)})
            continue

        if columns is None:
            source = item
        else:
            source = {column: item.get(column) for column in columns}

        row = {}
        for key, value in source.items():
            if isinstance(value, (list, dict)):
                row[key] = json.dumps(value, ensure_ascii=False)
            elif value is None:
                row[key] = "-"
            else:
                row[key] = value
        rows.append(row)

    return rows


def show_json_error_or_hint(json_result, hint):
    if not json_result["exists"]:
        st.info(hint)
        return False
    if json_result["error"]:
        st.error(json_result["error"])
        return False
    return True


def show_markdown_preview(path):
    text_result = safe_read_text(path)
    st.subheader("Markdown 보고서 미리보기")
    if not text_result["exists"]:
        st.info("Markdown 보고서 파일이 아직 없습니다.")
        return
    if text_result["error"]:
        st.error(text_result["error"])
        return
    st.markdown(text_result["text"])


# ------------------------------------------------------------
# 실행 파일 검색과 subprocess 실행
# ------------------------------------------------------------
def find_candidate_files(project_root, pattern):
    day4_dir = project_root / "src" / "day4"
    candidates = []

    for path in day4_dir.glob(pattern):
        name = path.name.lower()
        if name == "day4_quality_dashboard_streamlit_app.py":
            continue
        if "streamlit" in name:
            continue
        if path.is_file():
            candidates.append(path)

    candidates.sort(key=lambda item: (item.stat().st_mtime, item.name), reverse=True)
    return candidates


def run_python_file(project_root, script_path):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    command = [
        sys.executable,
        "-X",
        "utf8",
        str(script_path.relative_to(project_root)),
    ]

    result = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    return {
        "returncode": result.returncode,
        "stdout": safe_error_preview(result.stdout, max_length=6000),
        "stderr": safe_error_preview(result.stderr, max_length=6000),
        "command": " ".join(command),
    }


def render_run_result(title, result):
    st.markdown(f"#### {title}")
    st.caption(f"명령: `{result['command']}`")

    if result["stdout"]:
        st.text_area("stdout", result["stdout"], height=180, key=f"stdout_{title}_{datetime.now().timestamp()}")
    if result["stderr"]:
        st.text_area("stderr", result["stderr"], height=180, key=f"stderr_{title}_{datetime.now().timestamp()}")

    if result["returncode"] == 0:
        st.success("실행 완료")
    else:
        st.error(f"실행 실패: returncode={result['returncode']}")


def get_selected_scripts(project_root):
    selections = {}
    for key, config in STAGE_CONFIGS.items():
        candidates = find_candidate_files(project_root, config["pattern"])
        selections[key] = candidates
    return selections


# ------------------------------------------------------------
# 파일 상태 표시
# ------------------------------------------------------------
def get_file_status_rows(project_root):
    rows = []
    for relative_path in REQUIRED_RESULT_FILES + OPTIONAL_MARKDOWN_FILES:
        path = project_root / relative_path
        if path.exists():
            modified_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
            exists = "예"
        else:
            modified_at = "-"
            exists = "아니오"
        rows.append({"file": relative_path, "exists": exists, "modified_at": modified_at})
    return rows


def show_file_status(project_root):
    st.subheader("결과 파일 생성 여부")
    st.dataframe(get_file_status_rows(project_root), use_container_width=True)


# ------------------------------------------------------------
# 탭 1. 실행 대시보드
# ------------------------------------------------------------
def tab_run_dashboard(project_root):
    outputs_dir = project_root / "outputs" / "day4"
    st.write(f"프로젝트 루트: `{project_root}`")
    st.write(f"outputs/day4 경로: `{outputs_dir}`")
    st.warning("LLM Tool Selector 단계는 실제 LLM API를 호출할 수 있습니다. .env 설정과 네트워크 상태를 확인하세요.")

    candidate_map = get_selected_scripts(project_root)
    selected_paths = {}

    st.subheader("단계별 실행 파일 선택")
    for key, config in STAGE_CONFIGS.items():
        candidates = candidate_map[key]
        labels = [str(path.relative_to(project_root)) for path in candidates]
        if not labels:
            st.error(f"{config['label']} 실행 후보 파일이 없습니다.")
            selected_paths[key] = None
            continue
        selected_label = st.selectbox(config["label"], labels, index=0, key=f"select_{key}")
        selected_paths[key] = project_root / selected_label

    st.subheader("단계별 실행")
    for key, config in STAGE_CONFIGS.items():
        if st.button(config["button"], key=f"run_{key}"):
            if selected_paths[key] is None:
                st.error("실행할 파일을 선택할 수 없습니다.")
            else:
                result = run_python_file(project_root, selected_paths[key])
                render_run_result(config["label"], result)

    st.subheader("전체 실행")
    include_llm = st.checkbox("전체 실행에 LLM Tool Selector 포함", value=False)
    if not include_llm:
        st.info("체크하지 않으면 전체 실행에서 LLM Tool Selector 단계는 건너뜁니다. llm_tool_plan_results.json이 없으면 Validator 단계가 실패할 수 있습니다.")

    if st.button("전체 실행", key="run_all"):
        order = [
            "trace_analyzer",
            "rule_based_router",
            "guardrail",
            "llm_tool_selector",
            "llm_tool_plan_validator",
            "quality_gate_runner",
        ]

        for key in order:
            if key == "llm_tool_selector" and not include_llm:
                st.info("LLM Tool Selector 단계는 체크박스가 꺼져 있어 건너뛰었습니다.")
                llm_result_path = project_root / "outputs" / "day4" / "llm_tool_plan_results.json"
                if not llm_result_path.exists():
                    st.warning("llm_tool_plan_results.json이 없어 다음 Validator 단계가 실패할 수 있습니다.")
                continue

            if selected_paths[key] is None:
                st.error(f"{STAGE_CONFIGS[key]['label']} 실행 후보가 없어 전체 실행을 중단합니다.")
                break

            result = run_python_file(project_root, selected_paths[key])
            render_run_result(STAGE_CONFIGS[key]["label"], result)

            if result["returncode"] != 0:
                st.error("중간 단계에서 실패하여 이후 단계 실행을 중단합니다.")
                break

    show_file_status(project_root)


# ------------------------------------------------------------
# 탭 2. LLM Prompt 수정
# ------------------------------------------------------------
def tab_prompt_editor(project_root):
    prompt_path = project_root / "templates" / "day4" / "llm_tool_selection_prompt.mustache"
    backup_path = prompt_path.with_suffix(prompt_path.suffix + ".bak")

    st.write("이 prompt는 `llm_tool_selector.py`가 LLM에게 전달하는 Tool Selection 지시문입니다.")
    st.write("Markdown 결과 보고서 템플릿이 아니라, LLM 입력 prompt 템플릿입니다.")
    st.write(f"대상 파일: `{prompt_path.relative_to(project_root)}`")

    if not prompt_path.exists():
        st.warning("LLM Tool Selection prompt 템플릿 파일이 없습니다.")
        return

    if "prompt_template_text" not in st.session_state:
        text_result = safe_read_text(prompt_path)
        if text_result["error"]:
            st.error(text_result["error"])
            st.session_state["prompt_template_text"] = ""
        else:
            st.session_state["prompt_template_text"] = text_result["text"]

    col1, col2 = st.columns(2)
    with col1:
        if st.button("다시 읽기"):
            text_result = safe_read_text(prompt_path)
            if text_result["error"]:
                st.error(text_result["error"])
            else:
                st.session_state["prompt_template_text"] = text_result["text"]
                st.success("템플릿 파일을 다시 읽었습니다.")
    with col2:
        if st.button("Prompt 템플릿 저장"):
            if not backup_path.exists():
                shutil.copy2(prompt_path, backup_path)
            prompt_path.write_text(st.session_state["prompt_template_text"], encoding="utf-8")
            st.success("Prompt 템플릿을 저장했습니다.")

    st.text_area(
        "LLM Tool Selection Prompt Mustache 템플릿",
        key="prompt_template_text",
        height=520,
    )


# ------------------------------------------------------------
# 결과 표시 탭
# ------------------------------------------------------------
def tab_quality_gate(project_root):
    json_path = project_root / "outputs" / "day4" / "quality_gate_result.json"
    md_path = project_root / "outputs" / "day4" / "mcp_multi_agent_quality_gate.md"
    result = safe_read_json(json_path)

    if not show_json_error_or_hint(result, "quality_gate_result.json이 없습니다. quality_gate_runner.py를 실행하세요."):
        return

    data = result["data"] or {}
    st.metric("overall_status", data.get("overall_status", "-"))
    st.write("status_reason:", data.get("status_reason", "-"))

    st.subheader("영역별 점검")
    check_rows = data.get("check_rows")
    if not check_rows and isinstance(data.get("checks"), dict):
        check_rows = []
        for key, item in data["checks"].items():
            check_rows.append({
                "name": key,
                "status": item.get("status"),
                "summary_text": item.get("summary_text") or json.dumps(item.get("summary", {}), ensure_ascii=False),
                "reason": item.get("reason"),
            })
    st.dataframe(make_display_rows(check_rows), use_container_width=True)

    st.subheader("Backlog")
    backlog = data.get("backlog", [])
    if backlog:
        for item in backlog:
            st.write(f"- {item}")
    else:
        st.write("보완 Backlog가 없습니다.")

    show_markdown_preview(md_path)


def tab_trace(project_root):
    json_path = project_root / "outputs" / "day4" / "trace_summary.json"
    md_path = project_root / "outputs" / "day4" / "trace_review_result.md"
    result = safe_read_json(json_path)

    if not show_json_error_or_hint(result, "trace_summary.json이 없습니다. trace_analyzer.py를 실행하세요."):
        return

    data = result["data"] or {}
    overall = data.get("overall", {})

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("total_records", overall.get("total_records", 0))
    col2.metric("success_count", overall.get("success_count", 0))
    col3.metric("error_count", overall.get("error_count", 0))
    col4.metric("average_latency_ms", overall.get("average_latency_ms", 0))

    tool_summary = data.get("tool_summary")
    if tool_summary is None and isinstance(data.get("by_tool"), dict):
        tool_summary = []
        for tool_name, item in data["by_tool"].items():
            row = {"tool_name": tool_name}
            if isinstance(item, dict):
                row.update(item)
            tool_summary.append(row)

    st.subheader("Tool별 요약")
    st.dataframe(make_display_rows(tool_summary), use_container_width=True)

    st.subheader("느린 호출 Top 5")
    st.dataframe(make_display_rows(data.get("slow_calls") or data.get("slow_calls_top5")), use_container_width=True)

    st.subheader("실패 호출 목록")
    st.dataframe(make_display_rows(data.get("failed_calls")), use_container_width=True)

    show_markdown_preview(md_path)


def tab_rule_based(project_root):
    json_path = project_root / "outputs" / "day4" / "rule_based_tool_plan.json"
    md_path = project_root / "outputs" / "day4" / "rule_based_routing_report.md"
    result = safe_read_json(json_path)

    if not show_json_error_or_hint(result, "rule_based_tool_plan.json이 없습니다. rule_based_router.py를 실행하세요."):
        return

    data = result["data"] or {}
    summary = data.get("summary", {})
    results = data.get("results", [])
    matched_count = data.get("matched_count", summary.get("matched_count", sum(1 for item in results if item.get("matched") is True)))
    total_cases = data.get("total_cases", summary.get("total_cases", len(results)))
    mismatch_count = data.get("mismatch_count", summary.get("mismatch_count", total_cases - matched_count))
    guardrail_count = data.get("guardrail_count", summary.get("guardrail_count", sum(1 for item in results if item.get("guardrail_result"))))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("total_cases", total_cases)
    col2.metric("matched_count", matched_count)
    col3.metric("mismatch_count", mismatch_count)
    col4.metric("guardrail_count", guardrail_count)

    st.subheader("results")
    st.dataframe(make_display_rows(results, ["case_id", "user_query", "expected_tools_text", "selected_tools_text", "guardrail_text", "matched_text"]), use_container_width=True)

    st.subheader("mismatch_results")
    mismatch_results = data.get("mismatch_results") or [item for item in results if item.get("matched") is False or item.get("matched_text") == "불일치"]
    st.dataframe(make_display_rows(mismatch_results, ["case_id", "missing_tools_text", "extra_tools_text", "guardrail_text"]), use_container_width=True)

    show_markdown_preview(md_path)


def tab_llm_selection(project_root):
    json_path = project_root / "outputs" / "day4" / "llm_tool_plan_results.json"
    md_path = project_root / "outputs" / "day4" / "llm_tool_selection_report_draft.md"
    result = safe_read_json(json_path)

    if not show_json_error_or_hint(result, "llm_tool_plan_results.json이 없습니다. llm_tool_selector.py를 실행하세요."):
        return

    data = result["data"] or {}
    summary = data.get("summary", {})

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("selector_type", data.get("selector_type", "-"))
    col2.metric("total_cases", summary.get("total_cases", data.get("total_cases", 0)))
    col3.metric("matched_count", summary.get("matched_count", 0))
    col4.metric("mismatch_count", summary.get("mismatch_count", 0))
    col5.metric("guardrail_count", summary.get("guardrail_count", 0))

    st.subheader("results")
    st.dataframe(make_display_rows(data.get("results"), ["case_id", "user_query", "expected_tools_text", "selected_tools_text", "guardrail_text", "matched_text"]), use_container_width=True)

    st.subheader("mismatch_results")
    st.dataframe(make_display_rows(data.get("mismatch_results"), ["case_id", "missing_tools_text", "extra_tools_text", "guardrail_text"]), use_container_width=True)

    show_markdown_preview(md_path)


def tab_validator(project_root):
    json_path = project_root / "outputs" / "day4" / "llm_tool_plan_validation_result.json"
    md_path = project_root / "outputs" / "day4" / "llm_tool_plan_validation_report.md"
    result = safe_read_json(json_path)

    if not show_json_error_or_hint(result, "llm_tool_plan_validation_result.json이 없습니다. llm_tool_plan_validator.py를 실행하세요."):
        return

    data = result["data"] or {}
    summary = data.get("summary", {})

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("total_cases", summary.get("total_cases", 0))
    col2.metric("pass_count", summary.get("pass_count", 0))
    col3.metric("warning_count", summary.get("warning_count", 0))
    col4.metric("fail_count", summary.get("fail_count", 0))

    st.subheader("results")
    st.dataframe(make_display_rows(data.get("results"), ["case_id", "validation_status", "expected_tools_text", "selected_tools_text", "guardrail_text", "validation_errors_text", "validation_warnings_text"]), use_container_width=True)

    st.subheader("fail_results")
    st.dataframe(make_display_rows(data.get("fail_results"), ["case_id", "validation_errors_text", "missing_tools_text", "extra_tools_text", "unknown_tools_text"]), use_container_width=True)

    st.subheader("warning_results")
    st.dataframe(make_display_rows(data.get("warning_results"), ["case_id", "validation_warnings_text", "missing_arguments_text"]), use_container_width=True)

    show_markdown_preview(md_path)


def tab_guardrail(project_root):
    json_path = project_root / "outputs" / "day4" / "guardrail_test_results.json"
    md_path = project_root / "outputs" / "day4" / "guardrail_report.md"
    result = safe_read_json(json_path)

    if not show_json_error_or_hint(result, "guardrail_test_results.json이 없습니다. guardrail.py를 실행하세요."):
        return

    data = result["data"] or {}
    summary = data.get("summary", {})

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("total_cases", summary.get("total_cases", 0))
    col2.metric("blocked_count", summary.get("blocked_count", 0))
    col3.metric("allowed_count", summary.get("allowed_count", summary.get("pass_count", 0)))
    col4.metric("warning_count", summary.get("warning_count", summary.get("unsupported_conclusion_warning_count", 0)))
    col5.metric("match_count", summary.get("expected_guardrail_match_count", 0))
    col6.metric("mismatch_count", summary.get("expected_guardrail_mismatch_count", 0))

    st.subheader("blocked_results")
    st.dataframe(make_display_rows(data.get("blocked_results"), ["case_id", "detected_guardrail", "matched_keywords_text", "explanation"]), use_container_width=True)

    st.subheader("warning_results")
    st.dataframe(make_display_rows(data.get("warning_results"), ["case_id", "warnings_text", "matched_keywords_text", "explanation"]), use_container_width=True)

    st.subheader("mismatch_results")
    st.dataframe(make_display_rows(data.get("mismatch_results"), ["case_id", "expected_guardrail", "detected_guardrail", "warnings_text", "matched_text"]), use_container_width=True)

    show_markdown_preview(md_path)


# ------------------------------------------------------------
# 탭 9. 실행 순서 안내
# ------------------------------------------------------------
def tab_guide():
    st.markdown(
        """
## 권장 실행 순서

1. `trace_analyzer.py`
2. `rule_based_router.py`
3. `guardrail.py`
4. `llm_tool_selector.py`
5. `llm_tool_plan_validator.py`
6. `quality_gate_runner.py`
7. Streamlit 대시보드 확인

## PowerShell 예시

```powershell
python src/day4/trace_analyzer.py
python src/day4/rule_based_router.py
python src/day4/guardrail.py
python src/day4/llm_tool_selector.py
python src/day4/llm_tool_plan_validator.py
python src/day4/quality_gate_runner.py
streamlit run src/day4/day4_quality_dashboard_streamlit_app.py
```

timestamp 버전 파일을 사용하는 경우에는 실행 대시보드에서 현재 생성된 최신 파일명을 선택해서 실행하면 됩니다.

## 참고

- LLM Tool Selector는 실제 LLM API를 호출할 수 있습니다.
- `.env` 설정과 네트워크 상태를 먼저 확인하세요.
- 이 대시보드는 `.env` 내용을 화면에 표시하지 않습니다.
"""
    )


# ------------------------------------------------------------
# main
# ------------------------------------------------------------
def main():
    st.set_page_config(page_title="Day4 Quality Dashboard", layout="wide")
    st.title("Day4 제조 AI Agent Quality Dashboard")

    project_root = find_project_root()

    tabs = st.tabs([
        "실행 대시보드",
        "LLM Prompt 수정",
        "Quality Gate 결과",
        "Trace 분석 결과",
        "Rule Based Routing 결과",
        "LLM Tool Selection 결과",
        "Tool Plan Validator 결과",
        "Guardrail 결과",
        "실행 순서 안내",
    ])

    with tabs[0]:
        tab_run_dashboard(project_root)
    with tabs[1]:
        tab_prompt_editor(project_root)
    with tabs[2]:
        tab_quality_gate(project_root)
    with tabs[3]:
        tab_trace(project_root)
    with tabs[4]:
        tab_rule_based(project_root)
    with tabs[5]:
        tab_llm_selection(project_root)
    with tabs[6]:
        tab_validator(project_root)
    with tabs[7]:
        tab_guardrail(project_root)
    with tabs[8]:
        tab_guide()


if __name__ == "__main__":
    main()
