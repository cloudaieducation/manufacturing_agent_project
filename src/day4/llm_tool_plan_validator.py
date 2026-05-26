"""
Day4 LLM Tool Plan Validator - 초보자용 단순화 버전

이 파일은 제조 AI Agent 교육용 예제입니다.

역할:
- outputs/day4/llm_tool_plan_results.json 파일을 읽습니다.
- data/tool_selection_test_cases.json 기준으로 Tool 선택 결과를 검증합니다.
- selected_tools, expected_tools, Guardrail, tool_plan 구조를 확인합니다.
- arguments 부족은 FAIL이 아니라 WARNING으로 처리합니다.
- JSON 검증 결과와 Mustache 기반 Markdown 보고서를 저장합니다.

필요 패키지:
    pip install chevron

주의:
- 실제 사내 데이터나 민감정보를 사용하지 않는 교육용 가상 제조 시나리오입니다.
- API Key, DB 비밀번호, 전체 환경변수 값은 출력하지 않습니다.
- requirements.txt는 수정하지 않습니다.
"""

from pathlib import Path
from datetime import datetime
import json

import chevron


ALLOWED_TOOLS = [
    "get_equipment_status",
    "get_recent_alarm_events",
    "get_process_status",
    "get_quality_metrics",
    "get_maintenance_history",
    "search_manual",
]

GUARDRAIL_CODES = [
    "SENSITIVE_REQUEST_BLOCKED",
    "OVER_QUERY_BLOCKED",
]

RECOMMENDED_ARGUMENTS = {
    "get_equipment_status": ["equipment_id"],
    "get_recent_alarm_events": ["equipment_id", "alarm_code", "limit"],
    "get_process_status": ["equipment_id", "limit"],
    "get_quality_metrics": ["equipment_id", "limit"],
    "get_maintenance_history": ["equipment_id", "limit"],
}


def find_project_root():
    """현재 파일 위치(src/day4)를 기준으로 프로젝트 루트를 계산합니다."""
    current_file = Path(__file__).resolve()
    return current_file.parents[2]


def load_json(path):
    """JSON 파일을 단순하게 읽습니다. 오류가 있으면 Python 오류가 그대로 보입니다."""
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def build_reference_map(test_cases):
    """기준 테스트 케이스를 case_id 기준 dict로 변환합니다."""
    reference_map = {}

    for case in test_cases:
        case_id = case.get("case_id", "")
        if not case_id:
            continue

        expected_tools = case.get("expected_tools") or []
        if not isinstance(expected_tools, list):
            expected_tools = []

        reference_map[case_id] = {
            "expected_tools": expected_tools,
            "expected_guardrail": case.get("expected_guardrail"),
            "user_query": case.get("user_query", ""),
            "scenario_note": case.get("scenario_note", ""),
        }

    return reference_map


def sort_tools(tool_names):
    """허용 Tool 순서에 맞춰 정렬합니다."""
    unique_tools = set(tool_names or [])
    result = []

    for tool_name in ALLOWED_TOOLS:
        if tool_name in unique_tools:
            result.append(tool_name)

    for tool_name in sorted(unique_tools):
        if tool_name not in ALLOWED_TOOLS:
            result.append(tool_name)

    return result


def format_list(values):
    """Mustache 보고서에서 보기 좋도록 list를 문자열로 바꿉니다."""
    if not values:
        return "-"

    if not isinstance(values, list):
        return str(values)

    parts = []
    for value in values:
        if isinstance(value, dict):
            tool_name = value.get("tool_name", "")
            missing = value.get("missing", [])
            parts.append(f"{tool_name}: {', '.join(missing)}")
        else:
            parts.append(str(value))

    return ", ".join(parts) if parts else "-"


def validate_cases(llm_results, reference_map):
    """전체 케이스를 검증하고 결과와 요약을 만듭니다."""
    validation_results = []

    for result in llm_results:
        case_id = result.get("case_id", "")
        reference = reference_map.get(case_id, {})

        user_query = result.get("user_query") or reference.get("user_query", "")
        expected_tools = reference.get("expected_tools", result.get("expected_tools", [])) or []
        expected_guardrail = reference.get("expected_guardrail")

        selected_tools = result.get("selected_tools", [])
        if not isinstance(selected_tools, list):
            selected_tools = []
            selected_tools_not_list = True
        else:
            selected_tools_not_list = False

        tool_plan = result.get("tool_plan", [])
        if not isinstance(tool_plan, list):
            tool_plan = []
            tool_plan_not_list = True
        else:
            tool_plan_not_list = False

        guardrail_result = result.get("guardrail_result")

        selected_tools = sort_tools(selected_tools)
        expected_tools = sort_tools(expected_tools)

        tool_plan_tools = []
        missing_arguments = []

        for item in tool_plan:
            if not isinstance(item, dict):
                continue

            tool_name = item.get("tool_name")
            if tool_name:
                tool_plan_tools.append(tool_name)

            arguments = item.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}

            if tool_name == "search_manual":
                if not arguments.get("alarm_code") and not arguments.get("query"):
                    missing_arguments.append({
                        "tool_name": tool_name,
                        "missing": ["alarm_code 또는 query"],
                    })
                continue

            required_keys = RECOMMENDED_ARGUMENTS.get(tool_name, [])
            missing_keys = []

            for key in required_keys:
                if arguments.get(key) in ("", None):
                    missing_keys.append(key)

            if missing_keys:
                missing_arguments.append({
                    "tool_name": tool_name,
                    "missing": missing_keys,
                })

        tool_plan_tools = sort_tools(tool_plan_tools)
        missing_tools = sort_tools(list(set(expected_tools) - set(selected_tools)))
        extra_tools = sort_tools(list(set(selected_tools) - set(expected_tools)))
        plan_missing = sort_tools(list(set(selected_tools) - set(tool_plan_tools)))
        plan_extra = sort_tools(list(set(tool_plan_tools) - set(selected_tools)))

        unknown_tools = []
        for tool_name in selected_tools + tool_plan_tools:
            if tool_name not in ALLOWED_TOOLS and tool_name not in unknown_tools:
                unknown_tools.append(tool_name)

        validation_errors = []
        validation_warnings = []

        if selected_tools_not_list:
            validation_errors.append("SELECTED_TOOLS_NOT_LIST")

        if tool_plan_not_list:
            validation_errors.append("TOOL_PLAN_NOT_LIST")

        if unknown_tools:
            validation_errors.append("UNKNOWN_TOOL")

        if missing_tools:
            validation_errors.append("MISSING_EXPECTED_TOOL")

        if extra_tools:
            validation_errors.append("EXTRA_UNEXPECTED_TOOL")

        if plan_missing or plan_extra:
            validation_errors.append("SELECTED_TOOLS_TOOL_PLAN_MISMATCH")

        if expected_guardrail:
            if guardrail_result != expected_guardrail or selected_tools or tool_plan:
                validation_errors.append("GUARDRAIL_MISMATCH")
        else:
            if guardrail_result:
                validation_errors.append("UNEXPECTED_GUARDRAIL")

        if missing_arguments:
            validation_warnings.append("MISSING_REQUIRED_ARGUMENT")

        if validation_errors:
            validation_status = "FAIL"
        elif validation_warnings:
            validation_status = "WARNING"
        else:
            validation_status = "PASS"

        validation_results.append({
            "case_id": case_id,
            "user_query": user_query,
            "expected_tools": expected_tools,
            "selected_tools": selected_tools,
            "expected_tools_text": format_list(expected_tools),
            "selected_tools_text": format_list(selected_tools),
            "guardrail_result": guardrail_result,
            "expected_guardrail": expected_guardrail,
            "guardrail_text": guardrail_result or "-",
            "tool_plan": tool_plan,
            "validation_status": validation_status,
            "validation_errors": validation_errors,
            "validation_warnings": validation_warnings,
            "validation_errors_text": format_list(validation_errors),
            "validation_warnings_text": format_list(validation_warnings),
            "missing_tools": missing_tools,
            "extra_tools": extra_tools,
            "unknown_tools": unknown_tools,
            "missing_arguments": missing_arguments,
            "missing_tools_text": format_list(missing_tools),
            "extra_tools_text": format_list(extra_tools),
            "unknown_tools_text": format_list(unknown_tools),
            "missing_arguments_text": format_list(missing_arguments),
        })

    fail_results = [item for item in validation_results if item["validation_status"] == "FAIL"]
    warning_results = [item for item in validation_results if item["validation_status"] == "WARNING"]

    summary = {
        "total_cases": len(validation_results),
        "pass_count": sum(1 for item in validation_results if item["validation_status"] == "PASS"),
        "warning_count": len(warning_results),
        "fail_count": len(fail_results),
        "guardrail_count": sum(1 for item in validation_results if item.get("guardrail_result") in GUARDRAIL_CODES),
        "unknown_tool_count": sum(len(item["unknown_tools"]) for item in validation_results),
        "missing_tool_count": sum(len(item["missing_tools"]) for item in validation_results),
        "extra_tool_count": sum(len(item["extra_tools"]) for item in validation_results),
        "missing_argument_count": sum(len(item["missing_arguments"]) for item in validation_results),
    }

    return validation_results, summary, fail_results, warning_results


def save_outputs(project_root, report):
    """JSON 검증 결과와 Mustache 기반 Markdown 보고서를 저장합니다."""
    output_dir = project_root / "outputs" / "day4"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_output_path = output_dir / "llm_tool_plan_validation_result.json"
    markdown_output_path = output_dir / "llm_tool_plan_validation_report.md"
    template_path = project_root / "templates" / "day4" / "llm_tool_plan_validation_report.mustache"

    with json_output_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    template_text = template_path.read_text(encoding="utf-8")
    markdown_text = chevron.render(template_text, report)
    markdown_output_path.write_text(markdown_text, encoding="utf-8")

    return json_output_path, markdown_output_path


def main():
    """Validator의 전체 실행 흐름입니다."""
    print("[Day4 LLM Tool Plan Validator]")

    project_root = find_project_root()

    input_path = project_root / "outputs" / "day4" / "llm_tool_plan_results.json"
    reference_path = project_root / "data" / "tool_selection_test_cases.json"

    llm_data = load_json(input_path)
    test_cases = load_json(reference_path)

    reference_map = build_reference_map(test_cases)
    llm_results = llm_data["results"]

    validation_results, summary, fail_results, warning_results = validate_cases(
        llm_results,
        reference_map,
    )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "validator_name": "llm_tool_plan_validator",
        "input_file": "outputs/day4/llm_tool_plan_results.json",
        "reference_file": "data/tool_selection_test_cases.json",
        "summary": summary,
        "results": validation_results,
        "fail_results": fail_results,
        "warning_results": warning_results,
    }

    json_output_path, markdown_output_path = save_outputs(project_root, report)

    print("입력 파일: outputs/day4/llm_tool_plan_results.json")
    print("기준 파일: data/tool_selection_test_cases.json")
    print(f"전체 케이스 수: {summary['total_cases']}")
    print(f"PASS: {summary['pass_count']}")
    print(f"WARNING: {summary['warning_count']}")
    print(f"FAIL: {summary['fail_count']}")
    print(f"Guardrail 검증 수: {summary['guardrail_count']}")
    print("결과 저장:")
    print(f"- {json_output_path.relative_to(project_root)}")
    print(f"- {markdown_output_path.relative_to(project_root)}")


if __name__ == "__main__":
    main()
