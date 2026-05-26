"""
Day4 Quality Gate Runner - 초보자용 단순 버전

이 파일은 제조 AI Agent 교육용 예제입니다.

역할:
- Day4 산출물 파일이 준비되었는지 확인합니다.
- Trace, Rule Based Routing, LLM Tool Selection, Validator, Guardrail 결과를 함께 점검합니다.
- 5일차 Final MCP Multi-Agent 실습으로 넘어갈 수 있는지 PASS / CONDITIONAL_PASS / HOLD로 판단합니다.

필요 패키지:
    pip install chevron

주의:
- 실제 사내 데이터나 민감정보를 사용하지 않는 교육용 가상 제조 시나리오입니다.
- API Key, DB 비밀번호, 전체 환경변수 값은 출력하지 않습니다.
- requirements.txt는 수정하지 않습니다.
- before_after_comparison.md는 생성하지 않습니다.
"""

from pathlib import Path
from datetime import datetime
import json

import chevron


REQUIRED_FILES = {
    "trace_summary": "outputs/day4/trace_summary.json",
    "rule_based_tool_plan": "outputs/day4/rule_based_tool_plan.json",
    "llm_tool_plan_results": "outputs/day4/llm_tool_plan_results.json",
    "llm_tool_plan_validation_result": "outputs/day4/llm_tool_plan_validation_result.json",
    "guardrail_test_results": "outputs/day4/guardrail_test_results.json",
}

OPTIONAL_FILES = {
    "trace_review_result": "outputs/day4/trace_review_result.md",
    "rule_based_routing_report": "outputs/day4/rule_based_routing_report.md",
    "llm_tool_selection_report_draft": "outputs/day4/llm_tool_selection_report_draft.md",
    "llm_tool_plan_validation_report": "outputs/day4/llm_tool_plan_validation_report.md",
    "guardrail_report": "outputs/day4/guardrail_report.md",
}

CHECK_NAMES = {
    "trace_analysis": "Trace 분석",
    "rule_based_routing": "Rule Based Routing",
    "llm_tool_selection": "LLM Tool Selection",
    "llm_tool_plan_validation": "Tool Plan Validator",
    "guardrail": "Guardrail",
}


def find_project_root():
    """현재 파일 위치(src/day4)를 기준으로 프로젝트 루트를 계산합니다."""
    current_file = Path(__file__).resolve()
    return current_file.parents[2]


def read_json_safely(path):
    """JSON 파일을 읽고 missing / parse_error / valid 상태로 반환합니다."""
    if not path.exists():
        return {
            "data": None,
            "status": "missing",
            "message": "파일이 없습니다.",
        }

    text = path.read_text(encoding="utf-8")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return {
            "data": None,
            "status": "parse_error",
            "message": f"JSON 문법 오류가 있습니다. line={error.lineno}, column={error.colno}",
        }

    return {
        "data": data,
        "status": "valid",
        "message": "JSON 파일을 정상적으로 읽었습니다.",
    }


def check_file_status(path):
    """필수/선택 파일의 존재 여부와 JSON 파싱 가능 여부를 확인합니다."""
    if path.suffix.lower() == ".json":
        result = read_json_safely(path)
        return {
            "status": result["status"],
            "message": result["message"],
        }

    if not path.exists():
        return {
            "status": "missing",
            "message": "파일이 없습니다.",
        }

    return {
        "status": "exists",
        "message": "파일이 존재합니다.",
    }


def check_day4_outputs(project_root):
    """Day4 산출물 파일과 주요 결과 값을 한 번에 점검합니다."""
    input_files = {}
    input_file_rows = []

    for name, relative_path in {**REQUIRED_FILES, **OPTIONAL_FILES}.items():
        status = check_file_status(project_root / relative_path)
        item = {
            "name": name,
            "path": relative_path,
            "status": status["status"],
            "message": status["message"],
        }
        input_files[name] = item
        input_file_rows.append(item)

    checks = {}

    # 1. Trace 분석 결과 점검
    trace_path = project_root / REQUIRED_FILES["trace_summary"]
    trace_read = read_json_safely(trace_path)
    trace_data = trace_read["data"] if isinstance(trace_read["data"], dict) else {}
    trace_overall = trace_data.get("overall", {}) if isinstance(trace_data, dict) else {}
    trace_tool_summary = trace_data.get("tool_summary") if isinstance(trace_data, dict) else None
    trace_by_tool = trace_data.get("by_tool") if isinstance(trace_data, dict) else None

    if isinstance(trace_tool_summary, list):
        trace_tool_summary_count = len(trace_tool_summary)
    elif isinstance(trace_by_tool, dict):
        trace_tool_summary_count = len(trace_by_tool)
    else:
        trace_tool_summary_count = 0

    trace_total = trace_overall.get("total_records", 0) or 0
    trace_summary = {
        "file_status": trace_read["status"],
        "total_records": trace_total,
        "success_count": trace_overall.get("success_count", 0) or 0,
        "error_count": trace_overall.get("error_count", 0) or 0,
        "tool_summary_count": trace_tool_summary_count,
    }

    if trace_read["status"] != "valid":
        trace_status = "HOLD"
        trace_reason = trace_read["message"]
    elif trace_total > 0:
        trace_status = "PASS"
        trace_reason = "Trace 개수가 확인되어 분석 결과를 사용할 수 있습니다."
    else:
        trace_status = "CONDITIONAL_PASS"
        trace_reason = "Trace 파일은 있으나 total_records가 0이거나 overall 정보가 부족합니다."

    checks["trace_analysis"] = {
        "status": trace_status,
        "summary": trace_summary,
        "summary_text": (
            f"total_records={trace_summary['total_records']}, "
            f"success_count={trace_summary['success_count']}, "
            f"error_count={trace_summary['error_count']}, "
            f"tool_summary_count={trace_summary['tool_summary_count']}"
        ),
        "reason": trace_reason,
    }

    # 2. Rule Based Routing 결과 점검
    rule_path = project_root / REQUIRED_FILES["rule_based_tool_plan"]
    rule_read = read_json_safely(rule_path)
    rule_data = rule_read["data"] if isinstance(rule_read["data"], dict) else {}
    rule_results = rule_data.get("results", []) if isinstance(rule_data, dict) else []
    if not isinstance(rule_results, list):
        rule_results = []

    rule_total = rule_data.get("total_cases", len(rule_results)) or len(rule_results)
    rule_matched = 0
    for item in rule_results:
        if not isinstance(item, dict):
            continue
        matched = (
            item.get("matched") is True
            or item.get("match_result", {}).get("matched") is True
            or item.get("matched_text") == "일치"
        )
        if matched:
            rule_matched += 1

    rule_summary = {
        "file_status": rule_read["status"],
        "total_cases": rule_total,
        "matched_count": rule_matched,
        "mismatch_count": max(len(rule_results) - rule_matched, 0),
        "results_count": len(rule_results),
    }

    if rule_read["status"] != "valid":
        rule_status = "HOLD"
        rule_reason = rule_read["message"]
    elif rule_results and rule_total > 0:
        rule_status = "PASS"
        rule_reason = "Rule Based Routing 결과와 results 배열이 확인되었습니다."
    else:
        rule_status = "CONDITIONAL_PASS"
        rule_reason = "파일은 있으나 total_cases 또는 results 배열이 부족합니다."

    checks["rule_based_routing"] = {
        "status": rule_status,
        "summary": rule_summary,
        "summary_text": (
            f"total_cases={rule_summary['total_cases']}, "
            f"matched_count={rule_summary['matched_count']}, "
            f"mismatch_count={rule_summary['mismatch_count']}"
        ),
        "reason": rule_reason,
    }

    # 3. LLM Tool Selection 결과 점검
    llm_path = project_root / REQUIRED_FILES["llm_tool_plan_results"]
    llm_read = read_json_safely(llm_path)
    llm_data = llm_read["data"] if isinstance(llm_read["data"], dict) else {}
    llm_results = llm_data.get("results", []) if isinstance(llm_data, dict) else []
    if not isinstance(llm_results, list):
        llm_results = []

    llm_summary_data = llm_data.get("summary", {}) if isinstance(llm_data, dict) else {}
    llm_selector_type = llm_data.get("selector_type", "") if isinstance(llm_data, dict) else ""
    llm_total = llm_summary_data.get("total_cases", llm_data.get("total_cases", len(llm_results))) or len(llm_results)
    llm_matched = llm_summary_data.get("matched_count")
    if llm_matched is None:
        llm_matched = sum(1 for item in llm_results if isinstance(item, dict) and item.get("matched") is True)
    llm_mismatch = llm_summary_data.get("mismatch_count")
    if llm_mismatch is None:
        llm_mismatch = max(len(llm_results) - llm_matched, 0)
    llm_guardrail_count = llm_summary_data.get("guardrail_count")
    if llm_guardrail_count is None:
        llm_guardrail_count = sum(1 for item in llm_results if isinstance(item, dict) and item.get("guardrail_result"))

    llm_summary = {
        "file_status": llm_read["status"],
        "selector_type": llm_selector_type,
        "total_cases": llm_total,
        "results_count": len(llm_results),
        "matched_count": llm_matched,
        "mismatch_count": llm_mismatch,
        "guardrail_count": llm_guardrail_count,
    }

    if llm_read["status"] != "valid":
        llm_status = "HOLD"
        llm_reason = llm_read["message"]
    elif not llm_results or llm_total <= 0:
        llm_status = "HOLD"
        llm_reason = "LLM Tool Selection 결과에 results 배열이 없거나 total_cases가 0입니다."
    elif llm_selector_type == "real_llm":
        llm_status = "PASS"
        llm_reason = "real_llm 전용 LLM Tool Selection 결과가 확인되었습니다."
    else:
        llm_status = "CONDITIONAL_PASS"
        llm_reason = "results는 있으나 selector_type이 real_llm이 아닙니다."

    checks["llm_tool_selection"] = {
        "status": llm_status,
        "summary": llm_summary,
        "summary_text": (
            f"selector_type={llm_summary['selector_type'] or '-'}, "
            f"total_cases={llm_summary['total_cases']}, "
            f"matched_count={llm_summary['matched_count']}, "
            f"mismatch_count={llm_summary['mismatch_count']}, "
            f"guardrail_count={llm_summary['guardrail_count']}"
        ),
        "reason": llm_reason,
    }

    # 4. Tool Plan Validator 결과 점검
    validator_path = project_root / REQUIRED_FILES["llm_tool_plan_validation_result"]
    validator_read = read_json_safely(validator_path)
    validator_data = validator_read["data"] if isinstance(validator_read["data"], dict) else {}
    validator_summary_data = validator_data.get("summary", {}) if isinstance(validator_data, dict) else {}
    validator_results = validator_data.get("results", []) if isinstance(validator_data, dict) else []
    if not isinstance(validator_results, list):
        validator_results = []

    validator_total = validator_summary_data.get("total_cases", 0) or 0
    warning_count = validator_summary_data.get("warning_count")
    if warning_count is None:
        warning_count = validator_summary_data.get("conditional_pass_count", 0) or 0
    fail_count = validator_summary_data.get("fail_count", 0) or 0

    validator_summary = {
        "file_status": validator_read["status"],
        "total_cases": validator_total,
        "pass_count": validator_summary_data.get("pass_count", 0) or 0,
        "warning_count": warning_count,
        "fail_count": fail_count,
        "has_results": bool(validator_results),
    }

    if validator_read["status"] != "valid":
        validator_status = "HOLD"
        validator_reason = validator_read["message"]
    elif validator_total <= 0:
        validator_status = "HOLD"
        validator_reason = "Validator 결과는 있으나 total_cases가 0입니다."
    elif fail_count == 0:
        validator_status = "PASS"
        validator_reason = "Validator FAIL 없이 검증 결과가 확인되었습니다."
    elif validator_results:
        validator_status = "CONDITIONAL_PASS"
        validator_reason = "Validator FAIL 케이스가 있으나 상세 results가 있어 보완 가능합니다."
    else:
        validator_status = "HOLD"
        validator_reason = "Validator FAIL이 있으나 상세 results가 없습니다."

    checks["llm_tool_plan_validation"] = {
        "status": validator_status,
        "summary": validator_summary,
        "summary_text": (
            f"total_cases={validator_summary['total_cases']}, "
            f"pass_count={validator_summary['pass_count']}, "
            f"warning_count={validator_summary['warning_count']}, "
            f"fail_count={validator_summary['fail_count']}"
        ),
        "reason": validator_reason,
    }

    # 5. Guardrail 결과 점검
    guardrail_path = project_root / REQUIRED_FILES["guardrail_test_results"]
    guardrail_read = read_json_safely(guardrail_path)
    guardrail_data = guardrail_read["data"] if isinstance(guardrail_read["data"], dict) else {}
    guardrail_summary_data = guardrail_data.get("summary", {}) if isinstance(guardrail_data, dict) else {}

    guardrail_total = guardrail_summary_data.get("total_cases", 0) or 0
    guardrail_blocked = guardrail_summary_data.get("blocked_count", 0) or 0
    allowed_count = guardrail_summary_data.get("allowed_count")
    if allowed_count is None:
        allowed_count = guardrail_summary_data.get("pass_count")
    if allowed_count is None:
        allowed_count = max(guardrail_total - guardrail_blocked, 0)
    guardrail_mismatch = guardrail_summary_data.get("expected_guardrail_mismatch_count", 0) or 0

    guardrail_summary = {
        "file_status": guardrail_read["status"],
        "total_cases": guardrail_total,
        "blocked_count": guardrail_blocked,
        "allowed_count": allowed_count,
        "warning_count": guardrail_summary_data.get("warning_count", 0) or 0,
        "sensitive_block_count": guardrail_summary_data.get("sensitive_block_count", 0) or 0,
        "over_query_block_count": guardrail_summary_data.get("over_query_block_count", 0) or 0,
        "internal_access_block_count": guardrail_summary_data.get("internal_access_block_count", 0) or 0,
        "expected_guardrail_mismatch_count": guardrail_mismatch,
    }

    if guardrail_read["status"] != "valid":
        guardrail_status = "HOLD"
        guardrail_reason = guardrail_read["message"]
    elif guardrail_total <= 0:
        guardrail_status = "HOLD"
        guardrail_reason = "Guardrail 결과는 있으나 total_cases가 0입니다."
    elif guardrail_mismatch == 0:
        guardrail_status = "PASS"
        guardrail_reason = "기대 Guardrail과 실제 Guardrail 결과가 모두 일치합니다."
    else:
        guardrail_status = "CONDITIONAL_PASS"
        guardrail_reason = "Guardrail 불일치가 일부 있어 차단 키워드 또는 기준값 확인이 필요합니다."

    checks["guardrail"] = {
        "status": guardrail_status,
        "summary": guardrail_summary,
        "summary_text": (
            f"total_cases={guardrail_summary['total_cases']}, "
            f"blocked_count={guardrail_summary['blocked_count']}, "
            f"allowed_count={guardrail_summary['allowed_count']}, "
            f"warning_count={guardrail_summary['warning_count']}, "
            f"mismatch_count={guardrail_summary['expected_guardrail_mismatch_count']}"
        ),
        "reason": guardrail_reason,
    }

    check_rows = []
    for key, item in checks.items():
        check_rows.append({
            "name": CHECK_NAMES.get(key, key),
            "status": item["status"],
            "summary_text": item["summary_text"],
            "reason": item["reason"],
            "need_fix_text": "아니오" if item["status"] == "PASS" else "예",
        })

    return input_files, input_file_rows, checks, check_rows


def decide_overall_status(checks, input_files):
    """영역별 점검 결과와 필수 파일 상태를 기준으로 전체 Quality Gate 상태를 결정합니다."""
    core_required = [
        "trace_summary",
        "llm_tool_plan_results",
        "llm_tool_plan_validation_result",
        "guardrail_test_results",
    ]

    for key in core_required:
        status = input_files.get(key, {}).get("status")
        if status in ("missing", "parse_error"):
            return "HOLD", f"핵심 필수 파일({REQUIRED_FILES[key]})을 읽을 수 없어 5일차 진행 전 보완이 필요합니다."

    if any(item.get("status") == "HOLD" for item in checks.values()):
        return "HOLD", "하나 이상의 핵심 품질 점검 영역이 HOLD 상태입니다."

    if (
        checks["trace_analysis"]["status"] == "PASS"
        and checks["rule_based_routing"]["status"] in ("PASS", "CONDITIONAL_PASS")
        and checks["llm_tool_selection"]["status"] == "PASS"
        and checks["llm_tool_plan_validation"]["status"] == "PASS"
        and checks["guardrail"]["status"] == "PASS"
    ):
        return "PASS", "5일차 Final MCP Multi-Agent 통합 실습으로 진행할 수 있는 상태입니다."

    return "CONDITIONAL_PASS", "필수 산출물은 있으나 일부 보완 또는 확인이 필요한 항목이 있습니다."


def build_backlog(checks, input_files):
    """PASS가 아닌 항목과 파일 상태를 바탕으로 보완 Backlog를 만듭니다."""
    backlog = []

    for key, relative_path in REQUIRED_FILES.items():
        status = input_files.get(key, {}).get("status")

        if status == "missing":
            if key == "trace_summary":
                backlog.append("trace_summary.json이 없으므로 trace_analyzer.py를 실행해야 합니다.")
            elif key == "rule_based_tool_plan":
                backlog.append("rule_based_tool_plan.json이 없으므로 rule_based_router.py를 실행해야 합니다.")
            elif key == "llm_tool_plan_results":
                backlog.append("llm_tool_plan_results.json이 없으므로 llm_tool_selector.py를 실행해야 합니다.")
            elif key == "llm_tool_plan_validation_result":
                backlog.append("llm_tool_plan_validation_result.json이 없으므로 llm_tool_plan_validator.py를 실행해야 합니다.")
            elif key == "guardrail_test_results":
                backlog.append("guardrail_test_results.json이 없으므로 guardrail.py를 실행해야 합니다.")

        if status == "parse_error":
            backlog.append(f"{relative_path} 파일에 JSON 파싱 오류가 있으므로 파일 형식을 점검해야 합니다.")

    if checks.get("trace_analysis", {}).get("status") == "CONDITIONAL_PASS":
        backlog.append("Trace 분석 결과가 부족하므로 MCP Tool 호출 Trace 생성 여부를 확인해야 합니다.")

    validator_summary = checks.get("llm_tool_plan_validation", {}).get("summary", {})
    if (validator_summary.get("fail_count", 0) or 0) > 0:
        backlog.append("Validator에 FAIL 케이스가 있으므로 Tool 선택, Guardrail, arguments 경고를 확인해야 합니다.")

    guardrail_summary = checks.get("guardrail", {}).get("summary", {})
    if (guardrail_summary.get("expected_guardrail_mismatch_count", 0) or 0) > 0:
        backlog.append("Guardrail mismatch가 있으므로 차단 키워드 또는 expected_guardrail 기준을 점검해야 합니다.")

    llm_summary = checks.get("llm_tool_selection", {}).get("summary", {})
    if llm_summary.get("selector_type") != "real_llm":
        backlog.append("LLM Tool Selection 결과가 real_llm이 아니므로 selector_type을 확인해야 합니다.")

    return list(dict.fromkeys(backlog))


def save_outputs(project_root, report):
    """Quality Gate JSON 결과와 Mustache 기반 Markdown 보고서를 저장합니다."""
    output_dir = project_root / "outputs" / "day4"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_output_path = output_dir / "quality_gate_result.json"
    markdown_output_path = output_dir / "mcp_multi_agent_quality_gate.md"
    template_path = project_root / "templates" / "day4" / "quality_gate_report.mustache"

    with json_output_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    template_text = template_path.read_text(encoding="utf-8")
    markdown_text = chevron.render(template_text, report)
    markdown_output_path.write_text(markdown_text, encoding="utf-8")

    return json_output_path, markdown_output_path


def main():
    """Day4 Quality Gate Runner의 전체 실행 흐름입니다."""
    print("[Day4 Quality Gate Runner]")

    project_root = find_project_root()
    input_files, input_file_rows, checks, check_rows = check_day4_outputs(project_root)
    backlog = build_backlog(checks, input_files)
    overall_status, status_reason = decide_overall_status(checks, input_files)

    if overall_status == "PASS" and backlog:
        overall_status = "CONDITIONAL_PASS"
        status_reason = "주요 산출물은 준비되었지만 확인할 Backlog가 있어 조건부 통과로 판정했습니다."

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "quality_gate_name": "day4_mcp_multi_agent_quality_gate",
        "overall_status": overall_status,
        "status_reason": status_reason,
        "input_files": input_files,
        "input_file_rows": input_file_rows,
        "checks": checks,
        "check_rows": check_rows,
        "backlog": backlog,
    }

    json_output_path, markdown_output_path = save_outputs(project_root, report)

    print(f"Trace 분석: {checks['trace_analysis']['status']}")
    print(f"Rule Based Routing: {checks['rule_based_routing']['status']}")
    print(f"LLM Tool Selection: {checks['llm_tool_selection']['status']}")
    print(f"Tool Plan Validator: {checks['llm_tool_plan_validation']['status']}")
    print(f"Guardrail: {checks['guardrail']['status']}")
    print(f"전체 판정: {overall_status}")
    print("결과 저장:")
    print(f"- {json_output_path.relative_to(project_root)}")
    print(f"- {markdown_output_path.relative_to(project_root)}")


if __name__ == "__main__":
    main()
