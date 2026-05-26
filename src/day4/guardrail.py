"""
Day4 Guardrail 검사기 - 초보자용 단순화 버전

이 파일은 제조 AI Agent 교육용 예제입니다.

역할:
- 사용자 요청이 위험하거나 부적절한지 LLM 또는 Tool 호출 전에 검사합니다.
- 개인정보, 과도한 전체 조회, 실제 내부 시스템 접근 요청은 차단합니다.
- 근거 없는 단정 요청은 차단하지 않고 경고로 기록합니다.
- 검사 결과를 JSON과 Mustache 기반 Markdown 보고서로 저장합니다.

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


SENSITIVE_KEYWORDS = [
    "개인정보", "개인 정보", "연락처", "전화번호", "휴대폰", "작업자 이름", "작업자명",
    "담당자 연락처", "사번", "주민번호", "이메일", "메일 주소", "계정 정보",
    "계정 비밀번호", "비밀번호", "패스워드", "로그인 정보", "인증키", "API Key",
    "토큰", "token", "secret", "password",
]

OVER_QUERY_KEYWORDS = [
    "전체 조회", "모든 데이터", "전체 데이터", "전부 조회", "전체 로그", "모든 로그",
    "제한 없이", "전 기간", "전체 기간", "모든 설비", "전체 설비", "모든 라인",
    "전체 라인", "무제한 조회", "다 뽑아줘", "전부 다 보여줘", "제한 없이 가져와",
    "전체 이력", "전체 이력 다",
]

INTERNAL_SYSTEM_ACCESS_KEYWORDS = [
    "실제 사내 DB 접속", "실제 사내 데이터 조회", "실제 내부 시스템 접속", "운영 DB 접속",
    "운영 서버 접속", "사내망 접속", "실제 계정으로 접속", "내부망 접속",
    "실제 운영 DB", "운영계 DB", "운영계 서버", "사내 시스템에 직접 접속",
    "내부 시스템에 직접 접속", "실제 설비 제어", "설비를 직접 제어",
]

UNSUPPORTED_CONCLUSION_KEYWORDS = [
    "확실히 원인이라고 단정", "무조건 원인이라고 써줘", "근거 없이 원인 작성",
    "대충 원인 만들어줘", "추측해서 보고서 작성", "사실처럼 작성", "근거 없어도 작성",
    "확정 원인", "단정해서", "후보가 아니라", "확정해서", "발생했다고 확정",
    "근거가 없어도", "근거 없어도",
]


# 현재 파일 위치를 기준으로 프로젝트 루트를 계산합니다.
def find_project_root():
    current_file = Path(__file__).resolve()
    return current_file.parents[2]


# 교육용 테스트 케이스 JSON 파일을 읽습니다.
def load_test_cases(project_root):
    input_path = project_root / "data" / "tool_selection_test_cases.json"
    text = input_path.read_text(encoding="utf-8-sig")
    return json.loads(text), input_path


# 5일차 final_mcp_multi_agent.py에서도 import할 수 있도록 함수명과 반환 구조를 유지합니다.
def apply_guardrail(user_query):
    text = user_query or ""
    lowered_text = text.lower()
    warnings = []
    matched_keywords = []

    unsupported_keywords = []
    for keyword in UNSUPPORTED_CONCLUSION_KEYWORDS:
        if keyword.lower() in lowered_text:
            unsupported_keywords.append(keyword)

    if unsupported_keywords:
        warnings.append("UNSUPPORTED_CONCLUSION_WARNING")
        matched_keywords.extend(unsupported_keywords)

    sensitive_keywords = []
    for keyword in SENSITIVE_KEYWORDS:
        if keyword.lower() in lowered_text:
            sensitive_keywords.append(keyword)

    if sensitive_keywords:
        matched_keywords.extend(sensitive_keywords)
        return {
            "detected_guardrail": "SENSITIVE_REQUEST_BLOCKED",
            "blocked": True,
            "warnings": warnings,
            "matched_keywords": list(dict.fromkeys(matched_keywords)),
            "explanation": "민감정보 요청으로 판단되어 차단했습니다.",
        }

    internal_keywords = []
    for keyword in INTERNAL_SYSTEM_ACCESS_KEYWORDS:
        if keyword.lower() in lowered_text:
            internal_keywords.append(keyword)

    if internal_keywords:
        matched_keywords.extend(internal_keywords)
        return {
            "detected_guardrail": "INTERNAL_SYSTEM_ACCESS_BLOCKED",
            "blocked": True,
            "warnings": warnings,
            "matched_keywords": list(dict.fromkeys(matched_keywords)),
            "explanation": "실제 내부 시스템 접근 요청으로 판단되어 차단했습니다.",
        }

    over_query_keywords = []
    for keyword in OVER_QUERY_KEYWORDS:
        if keyword.lower() in lowered_text:
            over_query_keywords.append(keyword)

    if over_query_keywords:
        matched_keywords.extend(over_query_keywords)
        return {
            "detected_guardrail": "OVER_QUERY_BLOCKED",
            "blocked": True,
            "warnings": warnings,
            "matched_keywords": list(dict.fromkeys(matched_keywords)),
            "explanation": "과도한 전체 조회 요청으로 판단되어 차단했습니다.",
        }

    if warnings:
        return {
            "detected_guardrail": None,
            "blocked": False,
            "warnings": warnings,
            "matched_keywords": list(dict.fromkeys(matched_keywords)),
            "explanation": "차단 대상은 아니지만, 근거 없는 단정 요청 표현이 있어 경고로 기록했습니다.",
        }

    return {
        "detected_guardrail": None,
        "blocked": False,
        "warnings": [],
        "matched_keywords": [],
        "explanation": "차단 대상 표현이 없어 Tool 선택 단계로 진행할 수 있습니다.",
    }


# 전체 테스트 케이스에 Guardrail을 적용하고 요약을 만듭니다.
def evaluate_cases(cases):
    results = []

    for case in cases:
        case_id = case.get("case_id", "")
        user_query = case.get("user_query") or ""
        scenario_note = case.get("scenario_note") or ""
        expected_guardrail = case.get("expected_guardrail")

        guardrail_result = apply_guardrail(user_query)
        detected_guardrail = guardrail_result["detected_guardrail"]
        warnings = guardrail_result["warnings"]

        if expected_guardrail in (None, ""):
            matched_expected_guardrail = detected_guardrail is None and not warnings
        elif expected_guardrail == "UNSUPPORTED_CONCLUSION_WARNING":
            matched_expected_guardrail = "UNSUPPORTED_CONCLUSION_WARNING" in warnings
        else:
            matched_expected_guardrail = detected_guardrail == expected_guardrail

        result = {
            "case_id": case_id,
            "user_query": user_query,
            "scenario_note": scenario_note,
            "expected_guardrail": expected_guardrail,
            "detected_guardrail": detected_guardrail,
            "blocked": guardrail_result["blocked"],
            "blocked_text": "예" if guardrail_result["blocked"] else "아니오",
            "warnings": warnings,
            "warnings_text": format_list(warnings),
            "matched_expected_guardrail": matched_expected_guardrail,
            "matched_text": "일치" if matched_expected_guardrail else "불일치",
            "matched_keywords": guardrail_result["matched_keywords"],
            "matched_keywords_text": format_list(guardrail_result["matched_keywords"]),
            "explanation": guardrail_result["explanation"],
        }
        results.append(result)

    blocked_results = [item for item in results if item["blocked"]]
    warning_results = [item for item in results if item["warnings"]]
    mismatch_results = [item for item in results if not item["matched_expected_guardrail"]]

    summary = {
        "total_cases": len(results),
        "blocked_count": len(blocked_results),
        "allowed_count": sum(1 for item in results if not item["blocked"]),
        "pass_count": sum(1 for item in results if not item["blocked"]),
        "warning_count": len(warning_results),
        "expected_guardrail_match_count": sum(1 for item in results if item["matched_expected_guardrail"]),
        "expected_guardrail_mismatch_count": len(mismatch_results),
        "sensitive_block_count": sum(1 for item in results if item["detected_guardrail"] == "SENSITIVE_REQUEST_BLOCKED"),
        "over_query_block_count": sum(1 for item in results if item["detected_guardrail"] == "OVER_QUERY_BLOCKED"),
        "internal_access_block_count": sum(1 for item in results if item["detected_guardrail"] == "INTERNAL_SYSTEM_ACCESS_BLOCKED"),
        "unsupported_conclusion_warning_count": sum(
            1 for item in results if "UNSUPPORTED_CONCLUSION_WARNING" in item["warnings"]
        ),
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "guardrail_name": "day4_guardrail",
        "input_file": "data/tool_selection_test_cases.json",
        "summary": summary,
        "results": results,
        "blocked_results": blocked_results,
        "warning_results": warning_results,
        "mismatch_results": mismatch_results,
    }


# 리스트를 보고서에 넣기 쉬운 문자열로 변환합니다.
def format_list(values):
    if not values:
        return "-"

    if isinstance(values, list):
        return ", ".join(str(value) for value in values)

    return str(values)


# JSON 결과와 Mustache 기반 Markdown 보고서를 저장합니다.
def save_outputs(project_root, report):
    output_dir = project_root / "outputs" / "day4"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_output_path = output_dir / "guardrail_test_results.json"
    markdown_output_path = output_dir / "guardrail_report.md"
    template_path = project_root / "templates" / "day4" / "guardrail_report.mustache"

    with json_output_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    template_text = template_path.read_text(encoding="utf-8")
    markdown_text = chevron.render(template_text, report)
    markdown_output_path.write_text(markdown_text, encoding="utf-8")

    return json_output_path, markdown_output_path


# 프로그램 전체 실행 흐름입니다.
def main():
    print("[Day4 Guardrail]")

    project_root = find_project_root()
    cases, input_path = load_test_cases(project_root)
    report = evaluate_cases(cases)
    json_output_path, markdown_output_path = save_outputs(project_root, report)

    summary = report["summary"]

    print(f"입력 파일: {input_path.relative_to(project_root)}")
    print(f"전체 케이스 수: {summary['total_cases']}")
    print(f"차단 수: {summary['blocked_count']}")
    print(f"통과 수: {summary['allowed_count']}")
    print(f"경고 수: {summary['warning_count']}")
    print(f"기대값 일치 수: {summary['expected_guardrail_match_count']}")
    print(f"기대값 불일치 수: {summary['expected_guardrail_mismatch_count']}")
    print("결과 저장:")
    print(f"- {json_output_path.relative_to(project_root)}")
    print(f"- {markdown_output_path.relative_to(project_root)}")


if __name__ == "__main__":
    main()
