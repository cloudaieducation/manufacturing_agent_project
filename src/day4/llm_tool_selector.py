"""
Day4 LLM Tool Selector - 초보자용 real LLM 전용 버전

이 파일은 제조 AI Agent 교육용 예제입니다.

역할:
- data/tool_selection_test_cases.json 파일에서 사용자 질문을 읽습니다.
- Guardrail 대상 요청은 LLM 호출 전에 Python 코드에서 먼저 차단합니다.
- 실제 LLM은 어떤 Tool을 호출할지 selected_tools만 JSON으로 선택합니다.
- Python 코드는 Tool 이름을 검증하고 arguments를 붙여 Tool Plan으로 정리합니다.
- LLM prompt와 Markdown 보고서는 Mustache 템플릿으로 분리합니다.

필요 패키지:
    pip install chevron

주의:
- 실제 사내 데이터나 민감정보를 사용하지 않는 교육용 가상 제조 시나리오입니다.
- API Key, DB 비밀번호, 전체 환경변수 값은 출력하지 않습니다.
- requirements.txt는 수정하지 않습니다.
"""

from pathlib import Path
from datetime import datetime
import importlib.util
import inspect
import json
import re
import sys

import chevron


TOOL_ORDER = [
    "get_equipment_status",
    "get_recent_alarm_events",
    "get_process_status",
    "get_quality_metrics",
    "get_maintenance_history",
    "search_manual",
]

TOOL_REASONS = {
    "get_equipment_status": "설비 기본 정보를 확인하기 위해 선택했습니다.",
    "get_recent_alarm_events": "최근 알람 이력을 확인하기 위해 선택했습니다.",
    "get_process_status": "공정 상태 값을 확인하기 위해 선택했습니다.",
    "get_quality_metrics": "품질 지표를 확인하기 위해 선택했습니다.",
    "get_maintenance_history": "정비 이력을 확인하기 위해 선택했습니다.",
    "search_manual": "관련 매뉴얼과 조치 절차를 확인하기 위해 선택했습니다.",
}

SENSITIVE_KEYWORDS = [
    "개인정보", "개인 정보", "연락처", "전화번호", "휴대폰",
    "작업자 이름", "작업자명", "담당자 연락처", "사번", "주민번호", "이메일",
    "실제 내부 라인명", "실제 설비명", "실제 수율", "실제 사내 데이터",
    "내부 라인명", "내부 설비명",
]

OVER_QUERY_KEYWORDS = [
    "전체 조회", "모든 데이터", "전체 데이터", "전부 조회", "전체 로그", "모든 로그",
    "제한 없이", "제한 없는 조회", "무제한",
]


def find_project_root():
    """현재 파일 위치(src/day4)를 기준으로 프로젝트 루트를 계산합니다."""
    current_file = Path(__file__).resolve()
    return current_file.parents[2]


def prepare_environment(project_root):
    """src import 경로를 추가하고, 프로젝트 루트의 .env 파일을 읽습니다."""
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    env_path = project_root / ".env"
    if env_path.exists() and importlib.util.find_spec("dotenv") is not None:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, encoding="utf-8-sig", override=True)


def load_test_cases(project_root):
    """data/tool_selection_test_cases.json 파일을 읽습니다."""
    input_path = project_root / "data" / "tool_selection_test_cases.json"
    text = input_path.read_text(encoding="utf-8-sig")
    cases = json.loads(text)
    return cases, input_path


def extract_ids(user_query):
    """사용자 질문에서 첫 번째 equipment_id와 alarm_code를 추출합니다."""
    text = user_query or ""
    upper_text = text.upper()

    equipment_pattern = r"(?<![A-Z0-9])(?:EQP|ENCAP|SPT|CVD)-[A-Z]{2,10}-\d{2,4}(?![A-Z0-9])"
    alarm_pattern = r"(?<![A-Z0-9])ALM-[A-Z]{2,10}-\d{2,4}(?![A-Z0-9])"

    equipment_match = re.search(equipment_pattern, upper_text)
    alarm_match = re.search(alarm_pattern, upper_text)

    equipment_id = equipment_match.group(0) if equipment_match else None
    alarm_code = alarm_match.group(0) if alarm_match else None

    return equipment_id, alarm_code


def check_guardrail(user_query):
    """민감정보 요청 또는 과도한 전체 조회 요청을 단순 키워드로 차단합니다."""
    text = (user_query or "").lower()

    for keyword in SENSITIVE_KEYWORDS:
        if keyword.lower() in text:
            return "SENSITIVE_REQUEST_BLOCKED"

    for keyword in OVER_QUERY_KEYWORDS:
        if keyword.lower() in text:
            return "OVER_QUERY_BLOCKED"

    return None


def build_prompt(project_root, user_query):
    """Mustache 템플릿으로 LLM Tool Selection prompt를 생성합니다."""
    template_path = project_root / "templates" / "day4" / "llm_tool_selection_prompt.mustache"
    template_text = template_path.read_text(encoding="utf-8")

    prompt_data = {
        "user_query": user_query,
        "tools": [
            {
                "tool_name": "get_equipment_status",
                "description": "설비 위치, 설비 상태, 담당 공정 등 설비 기본 정보 조회",
            },
            {
                "tool_name": "get_recent_alarm_events",
                "description": "최근 알람 이력, 반복 발생, 재발 여부 조회",
            },
            {
                "tool_name": "get_process_status",
                "description": "온도, 압력, 진공도 등 공정 상태 조회",
            },
            {
                "tool_name": "get_quality_metrics",
                "description": "불량률, 수율, 검사 결과 등 품질 지표 조회",
            },
            {
                "tool_name": "get_maintenance_history",
                "description": "정비, 점검, 부품 교체 이력 조회",
            },
            {
                "tool_name": "search_manual",
                "description": "매뉴얼, 조치 절차, 기준서, 원인 후보 문서 검색",
            },
        ],
    }

    return chevron.render(template_text, prompt_data).strip()


def sort_tools(tool_names):
    """허용된 Tool 이름만 남기고 교육용 Tool 순서로 정렬합니다."""
    unique_tools = set(tool_names or [])
    sorted_tools = []

    for tool_name in TOOL_ORDER:
        if tool_name in unique_tools:
            sorted_tools.append(tool_name)

    return sorted_tools


def select_tools_with_llm(project_root, user_query):
    """src/llm_client.py의 generate_json_response()로 실제 LLM Tool 선택을 수행합니다."""
    from llm_client import generate_json_response

    prompt = build_prompt(project_root, user_query)
    signature = inspect.signature(generate_json_response)

    if "allow_fallback" in signature.parameters:
        llm_result = generate_json_response(prompt, allow_fallback=False)
    else:
        llm_result = generate_json_response(prompt)

    if not isinstance(llm_result, dict):
        raise ValueError("LLM result must be a dict")

    selected_tools = llm_result.get("selected_tools")

    if not isinstance(selected_tools, list):
        raise ValueError("selected_tools must be a list")

    return sort_tools(selected_tools)


def run_cases(project_root, cases):
    """전체 테스트 케이스에 대해 Guardrail 확인, LLM 선택, Tool Plan 생성을 수행합니다."""
    results = []

    for case in cases:
        case_id = case.get("case_id", "")
        user_query = case.get("user_query") or ""
        scenario_note = case.get("scenario_note") or ""
        expected_tools = case.get("expected_tools") or []

        equipment_id, alarm_code = extract_ids(user_query)
        guardrail_result = check_guardrail(user_query)

        if guardrail_result is not None:
            selected_tools = []
            tool_plan = []
        else:
            selected_tools = select_tools_with_llm(project_root, user_query)
            tool_plan = []

            for tool_name in selected_tools:
                arguments = {}

                if tool_name != "search_manual" and equipment_id:
                    arguments["equipment_id"] = equipment_id

                if tool_name == "get_recent_alarm_events" and alarm_code:
                    arguments["alarm_code"] = alarm_code

                if tool_name in [
                    "get_recent_alarm_events",
                    "get_process_status",
                    "get_quality_metrics",
                    "get_maintenance_history",
                ]:
                    arguments["limit"] = 5

                if tool_name == "search_manual" and alarm_code:
                    arguments["alarm_code"] = alarm_code

                tool_plan.append({
                    "tool_name": tool_name,
                    "reason": TOOL_REASONS.get(tool_name, "질문에 필요한 Tool로 선택했습니다."),
                    "arguments": arguments,
                })

        selected_set = set(selected_tools)
        expected_set = set(expected_tools)
        missing_tools = sort_tools(list(expected_set - selected_set))
        extra_tools = sort_tools(list(selected_set - expected_set))
        matched = not missing_tools and not extra_tools

        result = {
            "case_id": case_id,
            "user_query": user_query,
            "scenario_note": scenario_note,
            "expected_tools": expected_tools,
            "selected_tools": selected_tools,
            "expected_tools_text": ", ".join(expected_tools) if expected_tools else "-",
            "selected_tools_text": ", ".join(selected_tools) if selected_tools else "-",
            "guardrail_result": guardrail_result,
            "guardrail_text": guardrail_result or "-",
            "equipment_id": equipment_id,
            "alarm_code": alarm_code,
            "tool_plan": tool_plan,
            "matched": matched,
            "matched_text": "일치" if matched else "불일치",
            "missing_tools": missing_tools,
            "extra_tools": extra_tools,
            "missing_tools_text": ", ".join(missing_tools) if missing_tools else "-",
            "extra_tools_text": ", ".join(extra_tools) if extra_tools else "-",
        }
        results.append(result)

    matched_count = sum(1 for item in results if item["matched"])
    guardrail_count = sum(1 for item in results if item["guardrail_result"] is not None)
    mismatch_results = [item for item in results if not item["matched"]]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "selector_type": "real_llm",
        "description": "실제 LLM이 selected_tools만 선택하고, Python 코드가 Tool Plan으로 정리한 결과입니다.",
        "input_file": "data/tool_selection_test_cases.json",
        "total_cases": len(results),
        "summary": {
            "total_cases": len(results),
            "matched_count": matched_count,
            "mismatch_count": len(results) - matched_count,
            "guardrail_count": guardrail_count,
        },
        "results": results,
        "mismatch_results": mismatch_results,
    }


def save_outputs(project_root, report):
    """JSON 결과와 Mustache 기반 Markdown 보고서를 저장합니다."""
    output_dir = project_root / "outputs" / "day4"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_output_path = output_dir / "llm_tool_plan_results.json"
    markdown_output_path = output_dir / "llm_tool_selection_report_draft.md"
    report_template_path = project_root / "templates" / "day4" / "llm_tool_selection_report.mustache"

    with json_output_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    template_text = report_template_path.read_text(encoding="utf-8")
    markdown_text = chevron.render(template_text, report)
    markdown_output_path.write_text(markdown_text, encoding="utf-8")

    return json_output_path, markdown_output_path


def main():
    """LLM Tool Selector의 전체 실행 흐름입니다."""
    print("[Day4 LLM Tool Selector]")

    project_root = find_project_root()
    prepare_environment(project_root)

    cases, input_path = load_test_cases(project_root)
    report = run_cases(project_root, cases)
    json_output_path, markdown_output_path = save_outputs(project_root, report)

    print(f"입력 파일: {input_path.relative_to(project_root)}")
    print("Tool Selector 모드: real_llm")
    print(f"전체 테스트 케이스 수: {report['summary']['total_cases']}")
    print(f"매칭 수: {report['summary']['matched_count']}")
    print(f"불일치 수: {report['summary']['mismatch_count']}")
    print(f"Guardrail 차단 수: {report['summary']['guardrail_count']}")
    print("결과 저장:")
    print(f"- {json_output_path.relative_to(project_root)}")
    print(f"- {markdown_output_path.relative_to(project_root)}")


if __name__ == "__main__":
    main()
