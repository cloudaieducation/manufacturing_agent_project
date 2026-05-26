"""
Day5 Final MCP Multi-Agent

수강생용 단순화 버전입니다.

핵심 메시지:
- Agent는 리포트만 작성하는 프로그램이 아닙니다.
- Agent는 Tool 선택, 실행 검증, Guardrail, Trace 기반으로 업무 Action을 수행합니다.
- Tool 선택과 Tool 실행은 LLM에게 맡기지 않습니다.
- 최종 실행 통제는 Rule + Validator + Guardrail이 담당합니다.
- LLM은 마지막 최종 리포트 문장 생성 단계에서만 사용합니다.
- 리포트 생성은 Agent Action 중 하나입니다.

필요 패키지:
pip install chevron python-dotenv
"""

from pathlib import Path
from datetime import datetime
import json
import re
import sys
import time

import chevron
from dotenv import load_dotenv


ALLOWED_TOOLS = [
    "get_equipment_status",
    "get_recent_alarm_events",
    "get_process_status",
    "get_quality_metrics",
    "get_maintenance_history",
    "search_manual",
]

REQUIRED_ARGUMENTS = {
    "get_equipment_status": ["equipment_id"],
    "get_recent_alarm_events": ["equipment_id", "alarm_code", "limit"],
    "get_process_status": ["equipment_id", "limit"],
    "get_quality_metrics": ["equipment_id", "limit"],
    "get_maintenance_history": ["equipment_id", "limit"],
}

SENSITIVE_FIELDS = {
    "operator_name",
    "operator_phone",
    "employee_id",
    "internal_note",
    "password",
    "token",
    "api_key",
    "technician_note",
}


def find_project_root():
    """현재 파일 위치를 기준으로 프로젝트 루트를 계산합니다."""
    return Path(__file__).resolve().parents[2]


def get_user_query():
    """Day5 최종 실습용 사용자 요청 문자열을 반환합니다."""
    return (
        "EQP-EV-03 설비에서 ALM-TEMP-402 알람이 반복 발생했습니다. "
        "최근 알람 이력, 공정 상태, 품질 영향, 정비 이력, 매뉴얼 근거를 종합해 주세요. "
        "교육용 장애 대응 리포트 형식으로 정리해 주세요."
    )


def extract_ids(user_query):
    """사용자 요청에서 equipment_id와 alarm_code를 정규식으로 추출합니다."""
    equipment_match = re.search(r"\b[A-Z]{2,10}-[A-Z]{2,10}-\d{2,4}\b", user_query or "")
    alarm_match = re.search(r"\bALM-[A-Z]{2,10}-\d{2,4}\b", user_query or "", flags=re.IGNORECASE)
    return {
        "equipment_id": equipment_match.group(0) if equipment_match else None,
        "alarm_code": alarm_match.group(0).upper() if alarm_match else None,
    }


def apply_guardrail(user_query):
    """간단한 금지어 기반 Guardrail을 수행합니다."""
    lowered = (user_query or "").lower()
    guardrail_groups = [
        (
            "SENSITIVE_REQUEST_BLOCKED",
            [
                "개인정보", "개인 정보", "연락처", "전화번호", "휴대폰", "작업자 이름", "작업자명",
                "사번", "주민번호", "이메일", "비밀번호", "api key", "token", "secret", "password",
            ],
            "민감정보 요청 표현이 포함되어 Tool 실행을 차단했습니다.",
        ),
        (
            "OVER_QUERY_BLOCKED",
            ["전체 조회", "모든 데이터", "전체 데이터", "전부 조회", "전체 로그", "모든 로그", "제한 없이", "무제한 조회"],
            "범위가 과도한 전체 조회 요청으로 판단되어 Tool 실행을 차단했습니다.",
        ),
        (
            "INTERNAL_SYSTEM_ACCESS_BLOCKED",
            [
                "실제 사내 db", "실제 사내 데이터", "실제 내부 시스템", "운영 db", "운영 서버",
                "사내망", "내부망", "실제 라인명", "실제 설비명", "실제 레시피", "실제 수율",
                "삼성디스플레이 내부 데이터", "실제 운영 데이터",
            ],
            "실제 내부 정보 또는 운영 시스템 접근 요청 표현이 포함되어 Tool 실행을 차단했습니다.",
        ),
    ]

    for code, keywords, explanation in guardrail_groups:
        if any(keyword.lower() in lowered for keyword in keywords):
            return {"blocked": True, "detected_guardrail": code, "explanation": explanation}

    return {
        "blocked": False,
        "detected_guardrail": None,
        "explanation": "차단 대상 표현이 없어 정상 요청으로 판단했습니다.",
    }


def build_tool_plan(equipment_id, alarm_code):
    """Rule 기반으로 6개 Tool Plan을 생성합니다."""
    return [
        {
            "step": 1,
            "tool_name": "get_equipment_status",
            "reason": "장애 대상 설비의 기본 정보와 중요도를 확인합니다.",
            "arguments": {"equipment_id": equipment_id},
        },
        {
            "step": 2,
            "tool_name": "get_recent_alarm_events",
            "reason": "동일 알람의 반복 발생 이력을 확인합니다.",
            "arguments": {"equipment_id": equipment_id, "alarm_code": alarm_code, "limit": 3},
        },
        {
            "step": 3,
            "tool_name": "get_process_status",
            "reason": "온도, 진공도, 증착률 등 공정 상태를 확인합니다.",
            "arguments": {"equipment_id": equipment_id, "limit": 3},
        },
        {
            "step": 4,
            "tool_name": "get_quality_metrics",
            "reason": "알람과 품질 지표의 연계 가능성을 확인합니다.",
            "arguments": {"equipment_id": equipment_id, "limit": 2},
        },
        {
            "step": 5,
            "tool_name": "get_maintenance_history",
            "reason": "최근 정비 이력과 재발 가능성을 확인합니다.",
            "arguments": {"equipment_id": equipment_id, "limit": 2},
        },
        {
            "step": 6,
            "tool_name": "search_manual",
            "reason": "알람 코드 기준 매뉴얼/RAG 근거를 확인합니다.",
            "arguments": {"alarm_code": alarm_code},
        },
    ]


def validate_tool_plan(tool_plan):
    """Tool 실행 전 Tool 이름과 입력값을 검증합니다."""
    issues = []
    seen_tools = set()

    if not isinstance(tool_plan, list):
        return {"valid": False, "issues": ["tool_plan이 list가 아닙니다."], "issues_text": "tool_plan이 list가 아닙니다."}

    for item in tool_plan:
        tool_name = item.get("tool_name") if isinstance(item, dict) else None
        arguments = item.get("arguments") if isinstance(item, dict) else None

        if tool_name not in ALLOWED_TOOLS:
            issues.append(f"허용되지 않은 Tool입니다: {tool_name}")
            continue
        if tool_name in seen_tools:
            issues.append(f"중복 Tool입니다: {tool_name}")
        seen_tools.add(tool_name)
        if not isinstance(arguments, dict):
            issues.append(f"{tool_name}의 arguments가 dict가 아닙니다.")
            continue
        if tool_name == "search_manual":
            if not arguments.get("alarm_code") and not arguments.get("query"):
                issues.append("search_manual에는 alarm_code 또는 query 중 하나가 필요합니다.")
            continue
        for key in REQUIRED_ARGUMENTS.get(tool_name, []):
            if not arguments.get(key):
                issues.append(f"{tool_name}에 필수 argument가 없습니다: {key}")

    return {"valid": not issues, "issues": issues, "issues_text": "없음" if not issues else "; ".join(issues)}


def run_tool(tool_name, arguments):
    """실제 DB나 MCP Server를 호출하지 않고 교육용 Tool 결과를 반환합니다."""
    equipment_id = (arguments or {}).get("equipment_id", "EQP-EV-03")
    alarm_code = (arguments or {}).get("alarm_code", "ALM-TEMP-402")

    data_by_tool = {
        "get_equipment_status": {
            "equipment_id": equipment_id,
            "line_id": "TRAINING-LINE-07",
            "process_name": "OLED 박막 증착 공정",
            "equipment_type": "Vacuum Evaporation Chamber",
            "location": "Training EVAP Zone",
            "status": "warning",
            "criticality": "high",
            "note": "교육용 가상 설비이며 실제 사내 설비 정보가 아닙니다.",
            "operator_name": "교육용 제거 대상",
            "operator_phone": "010-0000-0000",
            "internal_note": "LLM에 전달하지 않는 내부 메모",
        },
        "get_recent_alarm_events": {
            "records": [
                {
                    "timestamp": "2026-05-18T09:10:00",
                    "equipment_id": equipment_id,
                    "alarm_code": alarm_code,
                    "severity": "warning",
                    "message": "챔버 온도 편차 알람이 반복 관찰되었습니다.",
                },
                {
                    "timestamp": "2026-05-18T09:35:00",
                    "equipment_id": equipment_id,
                    "alarm_code": alarm_code,
                    "severity": "warning",
                    "message": "공정 단계 이후 챔버 온도 회복 지연 가능성이 관찰되었습니다.",
                },
                {
                    "timestamp": "2026-05-18T10:05:00",
                    "equipment_id": equipment_id,
                    "alarm_code": alarm_code,
                    "severity": "major",
                    "message": "동일 알람 반복과 진공도 변동 알림이 함께 관찰되었습니다.",
                },
            ]
        },
        "get_process_status": {
            "records": [
                {
                    "timestamp": "2026-05-18T09:10:00",
                    "equipment_id": equipment_id,
                    "chamber_temperature": "기준 범위 상단 근접",
                    "vacuum_level": "stable",
                    "deposition_rate": "정상 범위이나 추적 관찰 필요",
                    "process_status": "CHECK_REQUIRED",
                },
                {
                    "timestamp": "2026-05-18T09:35:00",
                    "equipment_id": equipment_id,
                    "chamber_temperature": "기준 범위 상단 반복 접근",
                    "vacuum_level": "minor fluctuation",
                    "deposition_rate": "약간의 변동 가능성",
                    "process_status": "CHECK_REQUIRED",
                },
                {
                    "timestamp": "2026-05-18T10:05:00",
                    "equipment_id": equipment_id,
                    "chamber_temperature": "회복 지연 가능성",
                    "vacuum_level": "minor fluctuation",
                    "deposition_rate": "변동 가능성 관찰",
                    "process_status": "CHECK_REQUIRED",
                },
            ]
        },
        "get_quality_metrics": {
            "records": [
                {
                    "timestamp": "2026-05-18T09:00:00",
                    "line_id": "TRAINING-LINE-07",
                    "defect_rate": "소폭 상승 가능성",
                    "yield_rate": "큰 급락은 아니지만 관찰 필요",
                    "particle_count_status": "일부 증가 가능성",
                    "thickness_uniformity_risk": "MEDIUM",
                },
                {
                    "timestamp": "2026-05-18T10:00:00",
                    "line_id": "TRAINING-LINE-07",
                    "defect_rate": "소폭 상승 가능성",
                    "yield_rate": "관찰 필요",
                    "particle_count_status": "일부 증가 가능성",
                    "thickness_uniformity_risk": "MEDIUM",
                },
            ]
        },
        "get_maintenance_history": {
            "records": [
                {
                    "date": "2026-05-15",
                    "equipment_id": equipment_id,
                    "maintenance_type": "온도 센서 점검",
                    "check_summary": "온도 센서 상태 점검 후 재발 여부 확인이 필요합니다.",
                    "downtime_min": 15,
                    "technician_note": "교육용 제거 대상 정비 메모",
                },
                {
                    "date": "2026-05-17",
                    "equipment_id": equipment_id,
                    "maintenance_type": "챔버 온도 제어부 확인",
                    "check_summary": "제어부 확인 후 동일 알람 재발 여부 관찰이 필요합니다.",
                    "downtime_min": 20,
                    "technician_note": "교육용 제거 대상 기술자 메모",
                },
            ]
        },
        "search_manual": {
            "records": [
                {
                    "doc_name": "교육용 OLED 박막 증착 알람 가이드",
                    "chunk_id": "TRAINING-MANUAL-ALM-TEMP-001",
                    "score": 0.92,
                    "text": f"{alarm_code}는 챔버 온도 편차 관련 교육용 알람입니다. 온도 센서, 챔버 온도 로그, 냉각/가열 제어 상태, 진공도 변동을 확인합니다.",
                    "source": "education_sample_manual",
                },
                {
                    "doc_name": "교육용 품질 연계 확인 가이드",
                    "chunk_id": "TRAINING-QUALITY-TEMP-002",
                    "score": 0.87,
                    "text": "defect_rate, particle_count_status, thickness_uniformity_risk를 함께 확인하고 원인은 후보로 표현합니다.",
                    "source": "education_sample_manual",
                },
            ]
        },
    }

    return {
        "status": "success",
        "tool_name": tool_name,
        "message": "교육용 fallback Tool 결과를 반환했습니다.",
        "data": data_by_tool[tool_name],
    }


def remove_sensitive_fields(data):
    """dict와 list 내부의 민감 필드를 재귀적으로 제거합니다."""
    if isinstance(data, list):
        return [remove_sensitive_fields(item) for item in data]
    if isinstance(data, dict):
        return {key: remove_sensitive_fields(value) for key, value in data.items() if key not in SENSITIVE_FIELDS}
    return data


def render_template(template_path, data):
    """Mustache 템플릿을 읽어 Markdown 또는 LLM 프롬프트를 생성합니다."""
    template_text = template_path.read_text(encoding="utf-8")
    return chevron.render(template_text, data)


def save_jsonl(path, records):
    """Trace records 리스트를 BOM 없는 JSONL 파일로 한 번에 저장합니다."""
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    """Day5 수강생용 최종 통합 실습 실행 흐름입니다."""
    project_root = find_project_root()
    load_dotenv(project_root / ".env", encoding="utf-8-sig")

    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    output_dir = project_root / "outputs" / "day5"
    output_dir.mkdir(parents=True, exist_ok=True)

    template_dir = project_root / "templates" / "day5"
    template_dir.mkdir(parents=True, exist_ok=True)

    user_query = get_user_query()
    ids = extract_ids(user_query)
    equipment_id = ids["equipment_id"]
    alarm_code = ids["alarm_code"]
    guardrail = apply_guardrail(user_query)
    tool_plan = build_tool_plan(equipment_id, alarm_code)
    validation = validate_tool_plan(tool_plan)
    tool_results = {}
    trace_records = []

    if guardrail["blocked"]:
        print("[Day5 Final MCP Multi-Agent]")
        print("- Guardrail 차단으로 Tool을 실행하지 않았습니다.")
        print(f"- 차단 사유: {guardrail['explanation']}")
        return

    if not validation["valid"]:
        print("[Day5 Final MCP Multi-Agent]")
        print("- Validator 실패로 Tool을 실행하지 않았습니다.")
        print(f"- 문제: {validation['issues_text']}")
        return

    for item in tool_plan:
        start_time = time.perf_counter()
        tool_result = run_tool(item["tool_name"], item["arguments"])
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        safe_result = remove_sensitive_fields(tool_result)
        tool_results[item["tool_name"]] = safe_result
        trace_records.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "step": item["step"],
            "tool_name": item["tool_name"],
            "status": safe_result["status"],
            "latency_ms": latency_ms,
        })

    report_data = {
        "user_query": user_query,
        "equipment": tool_results["get_equipment_status"]["data"],
        "alarms": tool_results["get_recent_alarm_events"]["data"].get("records") or [{"timestamp": "-", "equipment_id": "-", "alarm_code": "-", "severity": "-", "message": "최근 알람 이력을 확인하지 못했습니다."}],
        "process_records": tool_results["get_process_status"]["data"].get("records") or [{"timestamp": "-", "chamber_temperature": "-", "vacuum_level": "-", "deposition_rate": "-", "process_status": "공정 상태를 확인하지 못했습니다."}],
        "quality_records": tool_results["get_quality_metrics"]["data"].get("records") or [{"timestamp": "-", "defect_rate": "-", "yield_rate": "-", "particle_count_status": "-", "thickness_uniformity_risk": "품질 지표를 확인하지 못했습니다."}],
        "maintenance_records": tool_results["get_maintenance_history"]["data"].get("records") or [{"date": "-", "maintenance_type": "-", "check_summary": "정비 이력을 확인하지 못했습니다.", "downtime_min": "-"}],
        "manuals": tool_results["search_manual"]["data"].get("records") or [{"doc_name": "-", "chunk_id": "-", "score": "-", "text": "매뉴얼 검색 결과를 확인하지 못했습니다."}],
    }

    base_report = render_template(template_dir / "final_incident_report.mustache", report_data)
    prompt = render_template(template_dir / "final_llm_report_prompt.mustache", {
        "user_query": user_query,
        "equipment_id": equipment_id,
        "alarm_code": alarm_code,
        "tool_results_json": json.dumps(tool_results, ensure_ascii=False, indent=2),
        "base_report": base_report,
    })

    from llm_client import generate_response

    llm_report = generate_response(prompt)
    review_text = render_template(template_dir / "final_tool_control_review.mustache", {
        "user_query": user_query,
        "guardrail": guardrail,
        "tool_plan": tool_plan,
        "validation": validation,
    })

    trace_records.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "step": "llm_report_generation",
        "event_type": "llm_report_generation",
        "status": "success",
    })

    (output_dir / "final_incident_report.md").write_text(llm_report, encoding="utf-8-sig")
    (output_dir / "final_tool_control_review.md").write_text(review_text, encoding="utf-8-sig")
    save_jsonl(output_dir / "final_mcp_call_trace.jsonl", trace_records)

    print("[Day5 Final MCP Multi-Agent]")
    print("- 사용자 요청 준비 완료")
    print(f"- Guardrail 통과 여부: {not guardrail['blocked']}")
    print(f"- Tool Plan 생성 수: {len(tool_plan)}")
    print(f"- Validator 통과 여부: {validation['valid']}")
    print(f"- 실행 Tool 수: {len(tool_results)}")
    print("- LLM 최종 리포트 생성 완료")
    print("- 결과 저장 경로:")
    print("  - outputs/day5/final_incident_report.md")
    print("  - outputs/day5/final_mcp_call_trace.jsonl")
    print("  - outputs/day5/final_tool_control_review.md")


if __name__ == "__main__":
    main()
