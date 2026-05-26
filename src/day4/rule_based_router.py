"""
Day4 규칙 기반 Tool Router - 초보자 교육용 단순화 버전

역할:
- 테스트 케이스 JSON 파일을 읽습니다.
- 사용자 질문에서 설비 ID와 알람 코드를 찾습니다.
- Guardrail 규칙으로 민감정보/과도한 전체 조회 요청을 차단합니다.
- 키워드 규칙으로 필요한 Tool을 선택합니다.
- JSON 보고서와 Mustache 기반 Markdown 보고서를 저장합니다.

필요 패키지:
    pip install chevron
"""

from pathlib import Path
import json
import re
from datetime import datetime

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
    "get_equipment_status": "설비 상태나 위치 확인이 필요해 선택했습니다.",
    "get_recent_alarm_events": "알람 반복 또는 이력 확인이 필요해 선택했습니다.",
    "get_process_status": "온도, 압력, 진공도 같은 공정 상태 확인이 필요해 선택했습니다.",
    "get_quality_metrics": "품질, 불량률, 수율 확인이 필요해 선택했습니다.",
    "get_maintenance_history": "정비, 점검, 수리 이력 확인이 필요해 선택했습니다.",
    "search_manual": "매뉴얼, 조치 절차, 원인 후보 확인이 필요해 선택했습니다.",
}

SENSITIVE_KEYWORDS = [
    "개인정보",
    "개인 정보",
    "연락처",
    "전화번호",
    "휴대폰",
    "작업자 이름",
    "작업자명",
    "담당자 이름",
    "담당자 연락처",
    "사번",
    "주민번호",
    "이메일",
    "실제 내부 라인명",
    "실제 설비명",
    "실제 수율",
    "실제 사내 데이터",
    "내부 라인명",
    "내부 설비명",
    "내부 수율",
]

OVER_QUERY_KEYWORDS = [
    "전체 조회",
    "모든 데이터",
    "전체 데이터",
    "전부 조회",
    "전체 로그",
    "모든 로그",
    "전체 라인",
    "전체 설비",
    "모든 설비",
    "제한 없이",
    "제한 없는 조회",
    "무제한",
]


def find_project_root():
    """현재 파일 위치(src/day4)를 기준으로 프로젝트 루트를 계산합니다."""
    current_file = Path(__file__).resolve()
    return current_file.parents[2]


def load_test_cases(project_root):
    """data/tool_selection_test_cases.json 파일을 읽습니다."""
    input_path = project_root / "data" / "tool_selection_test_cases.json"
    text = input_path.read_text(encoding="utf-8-sig")
    cases = json.loads(text)
    return cases, input_path


def extract_ids(user_query):
    """사용자 질문에서 설비 ID 목록과 알람 코드를 추출합니다."""
    text = user_query or ""
    upper_text = text.upper()

    equipment_pattern = r"(?<![A-Z0-9])(?:EQP|ENCAP|SPT|CVD)-[A-Z]{2,10}-\d{2,4}(?![A-Z0-9])"
    alarm_pattern = r"(?<![A-Z0-9])ALM-[A-Z]{2,10}-\d{2,4}(?![A-Z0-9])"

    equipment_ids = list(dict.fromkeys(re.findall(equipment_pattern, upper_text)))
    alarm_match = re.search(alarm_pattern, upper_text)

    return {
        "equipment_ids": equipment_ids,
        "equipment_id": equipment_ids[0] if equipment_ids else None,
        "alarm_code": alarm_match.group(0) if alarm_match else None,
    }


def check_guardrail(user_query):
    """민감정보 요청 또는 과도한 전체 조회 요청을 차단합니다."""
    text = (user_query or "").lower()

    for keyword in SENSITIVE_KEYWORDS:
        if keyword.lower() in text:
            return "SENSITIVE_REQUEST_BLOCKED"

    for keyword in OVER_QUERY_KEYWORDS:
        if keyword.lower() in text:
            return "OVER_QUERY_BLOCKED"

    return None


def select_tools_by_rule(user_query, equipment_ids):
    """키워드 규칙으로 Tool을 선택합니다."""
    q = user_query or ""
    selected_tools = []

    department_keywords = ["설비팀", "공정팀", "품질팀", "정비팀"]
    asks_department_routing = (
        "어디에 먼저 공유" in q
        or "먼저 공유해야" in q
        or "부서 라우팅" in q
        or all(keyword in q for keyword in department_keywords)
    )

    if asks_department_routing:
        return TOOL_ORDER[:]

    if len(equipment_ids) >= 2 and "우선순위" in q:
        return [
            "get_equipment_status",
            "get_recent_alarm_events",
            "get_quality_metrics",
            "get_maintenance_history",
        ]

    if any(keyword in q for keyword in ["설비", "장비", "위치", "상태"]):
        selected_tools.append("get_equipment_status")

    if any(keyword in q for keyword in ["알람", "반복", "재발", "이력"]):
        selected_tools.append("get_recent_alarm_events")

    if any(keyword in q for keyword in ["공정", "온도", "압력", "진공도"]):
        selected_tools.append("get_process_status")

    if any(keyword in q for keyword in ["품질", "불량률", "수율", "검사"]):
        selected_tools.append("get_quality_metrics")

    if any(keyword in q for keyword in ["정비", "점검", "부품 교체", "수리"]):
        selected_tools.append("get_maintenance_history")

    if any(keyword in q for keyword in ["매뉴얼", "조치", "절차", "가이드", "원인 후보"]):
        selected_tools.append("search_manual")

    selected_set = set(selected_tools)
    return [tool_name for tool_name in TOOL_ORDER if tool_name in selected_set]


def route_cases(cases):
    """전체 테스트 케이스를 규칙 기반으로 Routing합니다."""
    results = []

    for case in cases:
        case_id = case.get("case_id", "")
        user_query = case.get("user_query", "") or ""
        expected_tools = case.get("expected_tools", [])
        if not isinstance(expected_tools, list):
            expected_tools = []

        ids = extract_ids(user_query)
        guardrail_result = check_guardrail(user_query)

        if guardrail_result:
            selected_tools = []
        else:
            selected_tools = select_tools_by_rule(user_query, ids["equipment_ids"])

        tool_plan = []
        for tool_name in selected_tools:
            arguments = {}

            if ids["equipment_id"]:
                arguments["equipment_id"] = ids["equipment_id"]

            if ids["alarm_code"] and tool_name in ["get_recent_alarm_events", "search_manual"]:
                arguments["alarm_code"] = ids["alarm_code"]

            if tool_name in [
                "get_recent_alarm_events",
                "get_process_status",
                "get_quality_metrics",
                "get_maintenance_history",
            ]:
                arguments["limit"] = 5

            tool_plan.append(
                {
                    "tool_name": tool_name,
                    "reason": TOOL_REASONS[tool_name],
                    "arguments": arguments,
                    "arguments_text": json.dumps(arguments, ensure_ascii=False),
                }
            )

        missing_tools = [tool for tool in expected_tools if tool not in selected_tools]
        extra_tools = [tool for tool in selected_tools if tool not in expected_tools]
        matched = not missing_tools and not extra_tools

        result = {
            "case_id": case_id,
            "user_query": user_query,
            "expected_tools": expected_tools,
            "selected_tools": selected_tools,
            "selected_tools_text": ", ".join(selected_tools) if selected_tools else "-",
            "expected_tools_text": ", ".join(expected_tools) if expected_tools else "-",
            "guardrail_result": guardrail_result,
            "guardrail_text": guardrail_result or "-",
            "equipment_id": ids["equipment_id"] or "-",
            "alarm_code": ids["alarm_code"] or "-",
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
    mismatch_results = [item for item in results if not item["matched"]]
    guardrail_count = sum(1 for item in results if item["guardrail_result"])

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "router_type": "rule_based",
        "description": "키워드 규칙 기반 Tool 선택 결과입니다.",
        "total_cases": len(results),
        "matched_count": matched_count,
        "mismatch_count": len(mismatch_results),
        "guardrail_count": guardrail_count,
        "results": results,
        "mismatch_results": mismatch_results,
    }


def save_outputs(project_root, report):
    """JSON 보고서와 Mustache 기반 Markdown 보고서를 저장합니다."""
    output_dir = project_root / "outputs" / "day4"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_output_path = output_dir / "rule_based_tool_plan.json"
    markdown_output_path = output_dir / "rule_based_routing_report.md"
    template_path = project_root / "templates" / "day4" / "rule_based_routing_report.mustache"

    json_output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )

    template_text = template_path.read_text(encoding="utf-8")
    markdown_text = chevron.render(template_text, report)
    markdown_output_path.write_text(markdown_text, encoding="utf-8-sig")

    return json_output_path, markdown_output_path


def main():
    """Rule-Based Router의 전체 실행 흐름입니다."""
    print("[Day4 Rule-Based Router]")

    project_root = find_project_root()
    cases, input_path = load_test_cases(project_root)
    report = route_cases(cases)
    json_output_path, markdown_output_path = save_outputs(project_root, report)

    print(f"입력 파일 경로: {input_path}")
    print(f"전체 테스트 케이스 수: {report['total_cases']}")
    print(f"정상 매칭 수: {report['matched_count']}")
    print(f"불일치 수: {report['mismatch_count']}")
    print(f"Guardrail 차단 수: {report['guardrail_count']}")
    print("결과 저장 경로:")
    print(f"- {json_output_path}")
    print(f"- {markdown_output_path}")


if __name__ == "__main__":
    main()
