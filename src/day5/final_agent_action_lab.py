"""
Day5 Agent Action Lab

수강생용 단순화 버전입니다.

핵심 메시지:
- Agent는 리포트 작성기만이 아닙니다.
- Agent는 상황에 따라 다양한 업무 행동을 수행할 수 있습니다.
- 동일한 제조 알람 상황을 바탕으로 원인 후보 랭킹, 조치 체크리스트,
  담당 부서 라우팅, 재발 감시 조건 생성, Agent 자기 점검을 수행할 수 있습니다.
- 본 실습은 실제 사내 데이터가 아닌 교육용 가상 제조 데이터를 사용합니다.

필요 패키지:
pip install chevron
"""

from pathlib import Path
from datetime import datetime
import json
import os

import chevron


ACTION_MAP = {
    "1": ("root_cause_ranking", "원인 후보 랭킹"),
    "2": ("checklist_generation", "조치 체크리스트"),
    "3": ("team_routing", "담당 부서 라우팅"),
    "4": ("monitoring_rule_generation", "재발 감시 조건"),
    "5": ("self_review", "Agent 자기 점검"),
}


# 1
def find_project_root():
    """현재 파일 위치를 기준으로 프로젝트 루트를 계산합니다."""
    return Path(__file__).resolve().parents[2]


# 2
def get_default_scenario():
    """외부 파일을 읽지 않고 교육용 가상 제조 시나리오를 반환합니다."""
    return {
        "scenario_id": "ACTION-LAB-DEFAULT",
        "user_query": "교육용 제조 알람 상황을 바탕으로 Agent 업무 행동을 생성합니다.",
        "equipment_id": "EQP-EV-03",
        "equipment_name": "Training Evaporation Equipment 03",
        "line_id": "TRAINING-LINE-07",
        "process_name": "OLED 박막 증착 공정",
        "equipment_type": "Vacuum Evaporation Chamber",
        "alarm_code": "ALM-TEMP-402",
        "alarm_name": "챔버 온도 편차 알람",
        "situation": "교육용 디스플레이 박막 제조 라인의 EQP-EV-03에서 ALM-TEMP-402가 최근 반복 발생한 가상 상황",
        "business_context": "박막 증착 공정에서 챔버 온도 안정성, 진공도, 박막 두께 균일도, 파티클, 검사 불량률을 함께 확인해야 하는 교육용 상황",
        "equipment_status": {
            "status": "WARNING",
            "criticality": "HIGH",
            "note": "교육용 가상 설비이며 실제 사내 설비 정보가 아님",
        },
        "recent_alarm_events": {
            "summary": "최근 24시간 내 ALM-TEMP-402 4회 발생",
            "severity": "WARNING, MAJOR",
            "repeat_possibility": "반복 발생 가능성 있음",
            "related_observation": "동일 시간대에 진공도 변동 알림이 1회 관찰됨",
        },
        "process_status": {
            "chamber_temperature": "기준 범위 상단에 근접",
            "pressure": "정상 범위",
            "vacuum_level": "일부 변동",
            "deposition_rate": "약간의 변동 가능성",
            "thin_film_uniformity": "관찰 필요",
            "process_status": "CHECK_REQUIRED",
        },
        "quality_metrics": {
            "defect_rate": "최근 소폭 상승 가능성",
            "yield_rate": "큰 급락은 아니지만 관찰 필요",
            "particle_count": "일부 증가 가능성",
            "thickness_uniformity_risk": "MEDIUM",
            "quality_risk": "MEDIUM",
        },
        "maintenance_history": {
            "temperature_sensor_check": "최근 온도 센서 점검 이력 있음",
            "temperature_control_unit_check": "챔버 온도 제어부 확인 이력 있음",
            "part_replacement": "부품 교체 여부는 추가 확인 필요",
            "repeat_after_maintenance": "정비 이후 동일 알람 재발 여부 확인 필요",
        },
        "manual_search_result": {
            "alarm_meaning": "ALM-TEMP-402는 챔버 온도 편차와 관련",
            "process_consideration": "챔버 온도 안정성, 진공도, 증착률, 박막 두께 균일도, 파티클 증가 가능성을 함께 확인해야 함",
            "first_check_items": ["온도 센서", "챔버 온도 로그", "냉각/가열 제어 상태", "진공도 변동", "최근 정비 이력"],
            "quality_check_items": ["defect_rate", "particle_count", "thickness_uniformity_risk"],
            "caution": "원인을 단정하지 말고 추가 확인 항목을 함께 제시해야 함",
        },
    }


# 3
def choose_action():
    """메뉴를 출력하고 실행할 Agent Action을 선택합니다."""
    print("[Day5 Agent Action Lab]")
    print("실행할 Action을 선택하세요.")
    print("1. 원인 후보 랭킹")
    print("2. 조치 체크리스트 생성")
    print("3. 담당 부서 라우팅")
    print("4. 재발 감시 조건 생성")
    print("5. Agent 자기 점검")
    print("엔터 또는 잘못된 입력: 1번 기본 실행")

    choice = os.getenv("ACTION_LAB_CHOICE")
    if choice is None:
        choice = input("선택 번호 입력: ").strip()

    return ACTION_MAP.get(choice, ACTION_MAP["1"])


# 4
def run_guardrail_check(scenario):
    """교육용 범위를 벗어날 수 있는 표현을 제한된 필드에서만 검사합니다."""
    check_text = " ".join([
        scenario.get("user_query", ""),
        scenario.get("situation", ""),
        scenario.get("business_context", ""),
    ])
    keywords = [
        "실제 사내 DB", "실제 내부 시스템", "실제 라인명", "실제 설비명", "실제 레시피", "실제 수율",
        "전체 로그", "모든 작업자", "연락처", "사번", "비밀번호", "API Key", "원인을 확정",
        "근거 없이 단정", "삼성디스플레이 내부 데이터", "실제 운영 데이터",
    ]
    found_keywords = [keyword for keyword in keywords if keyword in check_text]

    if found_keywords:
        return {
            "status": "WARNING",
            "found_keywords": found_keywords,
            "message": "교육용 실습 범위를 벗어날 수 있는 표현이 있어 주의가 필요합니다.",
        }

    return {
        "status": "PASS",
        "found_keywords": [],
        "message": "교육용 가상 시나리오 범위에서 실행 가능합니다.",
    }


# 5
def build_action_sections(action_type, scenario):
    """5개 Agent Action 결과를 action_type에 따라 sections 리스트로 생성합니다."""
    sections = [
        {
            "title": "교육용 가상 시나리오 안내",
            "lines": [
                "- 본 실습은 실제 사내 데이터가 아닌 교육용 가상 제조 데이터를 사용합니다.",
                "- 실제 운영 적용 시에는 내부 표준 절차와 보안 검토가 필요합니다.",
                "- 결과는 현장 지시가 아니라 수업용 Agent Action 예시입니다.",
            ],
        },
        {
            "title": "입력 상황 요약",
            "lines": [
                f"- 설비 ID: {scenario['equipment_id']}",
                f"- 알람 코드: {scenario['alarm_code']}",
                f"- 공정명: {scenario['process_name']}",
                f"- 상황: {scenario['situation']}",
                f"- 업무 맥락: {scenario['business_context']}",
            ],
        },
        {
            "title": "사용한 Tool 근거",
            "lines": [
                "- get_equipment_status: 설비 기본 정보 확인",
                "- get_recent_alarm_events: 반복 알람 여부 확인",
                "- get_process_status: 온도/압력/진공 상태 확인",
                "- get_quality_metrics: 품질 영향 가능성 확인",
                "- get_maintenance_history: 정비 이력 확인",
                "- search_manual: 알람 대응 절차 검색",
            ],
        },
    ]

    if action_type == "checklist_generation":
        sections.extend([
            {
                "title": "10분 이내 1차 확인 체크리스트",
                "lines": [
                    "- [ ] 최근 24시간 내 동일 알람 반복 여부 확인",
                    "- [ ] 챔버 온도 로그 확인",
                    "- [ ] 온도 센서 상태 확인",
                    "- [ ] 냉각/가열 제어 상태 확인",
                    "- [ ] 동일 시간대 진공도 변동 여부 확인",
                ],
            },
            {
                "title": "박막 증착 공정 관점의 추가 확인 체크리스트",
                "lines": [
                    "- [ ] 진공도 변동 여부 확인",
                    "- [ ] 증착률 변동 여부 확인",
                    "- [ ] 박막 두께 균일도 관련 품질 지표 확인",
                    "- [ ] 파티클 증가 가능성 확인",
                    "- [ ] 검사 불량률이 같은 시간대에 상승했는지 확인",
                ],
            },
            {
                "title": "확인 후 기록해야 할 항목",
                "lines": [
                    "- 확인 시간과 알람 발생 시간대",
                    "- 챔버 온도 로그 요약",
                    "- 진공도, 증착률, 품질 지표의 동시 변화 여부",
                    "- 추가 조치 필요 여부",
                ],
            },
            {
                "title": "안전 주의 문구",
                "lines": [
                    "- 본 체크리스트는 교육용 확인 항목이며 실제 작업 지시가 아닙니다.",
                    "- 실제 설비 조작은 승인된 내부 표준 절차와 권한 체계를 따라야 합니다.",
                ],
            },
        ])
    elif action_type == "team_routing":
        sections.extend([
            {
                "title": "우선 공유 대상",
                "lines": [
                    "- 설비팀: 챔버 온도 편차와 설비 상태 확인이 우선 필요합니다.",
                    "- 제조 운영 담당: 반복 알람 상황과 확인 진행 상태를 관리합니다.",
                ],
            },
            {
                "title": "동시 공유 대상",
                "lines": [
                    "- 공정팀: 진공도, 증착률, 박막 두께 균일도 영향 가능성을 확인합니다.",
                    "- 품질팀: defect_rate, particle_count, thickness_uniformity_risk를 관찰합니다.",
                    "- 정비팀: 최근 정비 이후 동일 알람 재발 여부를 확인합니다.",
                ],
            },
            {
                "title": "공유 제외 또는 보류 대상",
                "lines": [
                    "- 직접 관련 근거가 부족한 부서는 우선 공유 대상에서 제외합니다.",
                    "- 전체 조직 대상 공유는 과도한 알림이 될 수 있으므로 보류합니다.",
                    "- 실제 담당자 이름, 연락처, 사번은 포함하지 않습니다.",
                ],
            },
            {
                "title": "부서별 전달 메시지 초안",
                "lines": [
                    "- 설비팀: 챔버 온도 로그와 제어부 상태 확인이 필요합니다.",
                    "- 공정팀: 진공도 일부 변동과 증착률 변동 가능성을 확인해 주십시오.",
                    "- 품질팀: 품질 지표의 동시 변화를 관찰해 주십시오.",
                    "- 정비팀: 최근 점검 이후 동일 알람 재발 여부를 확인해 주십시오.",
                ],
            },
        ])
    elif action_type == "monitoring_rule_generation":
        sections.extend([
            {
                "title": "감시 대상",
                "lines": [
                    f"- 설비: {scenario['equipment_id']}",
                    f"- 알람: {scenario['alarm_code']}",
                    "- 연계 지표: 진공도, 증착률, 박막 두께 균일도, 파티클, 검사 불량률",
                ],
            },
            {
                "title": "감시 조건",
                "lines": [
                    "- 최근 24시간 내 동일 알람 3회 이상 발생 시 재점검합니다.",
                    "- 챔버 온도 편차가 기준 범위 상단에 반복 접근하면 관찰 대상으로 표시합니다.",
                    "- 진공도 변동이 함께 발생하면 공정 조건 영향 가능성을 확인합니다.",
                ],
            },
            {
                "title": "품질 연계 감시 조건",
                "lines": [
                    "- defect_rate 또는 particle_count가 상승하면 품질팀 동시 확인 대상으로 표시합니다.",
                    "- thickness_uniformity_risk가 MEDIUM 이상이면 공정팀과 품질팀이 함께 확인합니다.",
                    "- 증착률 변동과 박막 두께 균일도 변화가 같은 시간대에 발생하는지 확인합니다.",
                ],
            },
            {
                "title": "Trace에 남겨야 할 항목",
                "lines": [
                    "- 감시 시작 시간과 종료 시간",
                    "- 알람 발생 횟수와 함께 관찰된 공정 지표",
                    "- 함께 관찰된 품질 지표와 알림 대상",
                    "- 본 조건은 교육용 예시이며 실제 자동 알림 정책이 아닙니다.",
                ],
            },
        ])
    elif action_type == "self_review":
        sections.extend([
            {
                "title": "점검 대상 문장 예시",
                "lines": [
                    "- 문제 표현: 온도 센서 이상으로 판단됩니다.",
                    "- 문제 표현: 이 알람은 실제 특정 라인의 수율 저하 원인입니다.",
                    "- 문제 표현: 전체 로그와 모든 작업자 정보를 조회해야 합니다.",
                ],
            },
            {
                "title": "자기 점검 항목",
                "lines": [
                    "- 원인 단정 표현이 있는지 확인합니다.",
                    "- 근거 부족 표현이 있는지 확인합니다.",
                    "- 민감정보, 과도한 조회 요청, 실제 사내 데이터처럼 보이는 표현을 확인합니다.",
                ],
            },
            {
                "title": "수정 제안 문장",
                "lines": [
                    "- 기존: 온도 센서 이상으로 판단됩니다.",
                    "- 수정: 온도 센서 이상 가능성이 있으므로 추가 확인이 필요합니다.",
                    "- 기존: 전체 로그와 모든 작업자 정보를 조회해야 합니다.",
                    "- 수정: 최근 24시간의 해당 설비 알람 이력과 관련 공정 지표만 우선 확인합니다.",
                ],
            },
            {
                "title": "주의 사항",
                "lines": [
                    "- 실제 라인명, 실제 설비명, 실제 레시피, 실제 수율처럼 보이는 표현은 피합니다.",
                    "- 교육용 가상 설비 ID와 가상 알람 코드만 사용합니다.",
                ],
            },
        ])
    else:
        sections.extend([
            {
                "title": "디스플레이 박막 제조 업무 관점에서의 확인 포인트",
                "lines": [
                    "- 챔버 온도 안정성이 반복 알람과 관련되는지 확인합니다.",
                    "- 진공도 변동이 증착률과 박막 두께 균일도에 영향을 줄 가능성을 함께 봅니다.",
                    "- defect_rate, particle_count, thickness_uniformity_risk를 함께 확인합니다.",
                    "- 최근 정비 이력 이후 동일 알람이 재발했는지 확인합니다.",
                ],
            },
            {
                "title": "사용한 근거",
                "lines": [
                    "- 설비 상태: WARNING, 중요도 HIGH",
                    "- 최근 알람 이력: 최근 24시간 내 동일 알람 4회 발생",
                    "- 공정 상태: 챔버 온도 기준 범위 상단 근접, 진공도 일부 변동",
                    "- 품질 지표: defect_rate 소폭 상승 가능성, particle_count 일부 증가 가능성",
                    "- 매뉴얼 근거: 원인을 단정하지 말고 추가 확인 항목을 함께 제시해야 함",
                ],
            },
            {
                "title": "원인 후보 랭킹",
                "lines": [
                    "1. 챔버 온도 제어 불안정 가능성 / 가능성: 높음",
                    "2. 온도 센서 보정 또는 점검 필요 가능성 / 가능성: 중간",
                    "3. 진공도 변동에 따른 증착 조건 영향 가능성 / 가능성: 중간",
                    "- 위 항목은 확정 원인이 아니라 교육용 원인 후보입니다.",
                ],
            },
            {
                "title": "추가 확인 필요 항목",
                "lines": [
                    "- 챔버 온도 로그의 시간대별 변화",
                    "- 온도 센서 보정 상태와 최근 점검 결과",
                    "- 진공도 변동과 증착률 변동의 동시 발생 여부",
                    "- 박막 두께 균일도, 파티클, 검사 불량률 변화 추세",
                ],
            },
            {
                "title": "주의 사항",
                "lines": [
                    "- 이 결과는 원인을 확정하지 않고 후보로만 제시합니다.",
                    "- 실제 운영 판단은 내부 표준 절차와 승인 체계가 필요합니다.",
                ],
            },
        ])

    return sections


# 6
def main():
    """Action 선택부터 결과 저장까지 전체 실행 흐름을 담당합니다."""
    project_root = find_project_root()
    output_dir = project_root / "outputs" / "day5"
    template_dir = project_root / "templates" / "day5"
    output_dir.mkdir(parents=True, exist_ok=True)
    template_dir.mkdir(parents=True, exist_ok=True)

    action_type, action_name = choose_action()
    scenario = get_default_scenario()
    guardrail_result = run_guardrail_check(scenario)
    sections = build_action_sections(action_type, scenario)

    template_path = template_dir / "action_lab_result.mustache"
    template_text = template_path.read_text(encoding="utf-8")
    markdown_text = chevron.render(template_text, {
        "action_name": action_name,
        "sections": sections,
    })

    markdown_path = output_dir / "action_lab_result.md"
    json_path = output_dir / "action_lab_result.json"
    trace_path = output_dir / "action_lab_trace.jsonl"

    output_files = {
        "markdown": "outputs/day5/action_lab_result.md",
        "json": "outputs/day5/action_lab_result.json",
        "trace": "outputs/day5/action_lab_trace.jsonl",
    }
    json_result = {
        "action_type": action_type,
        "action_name": action_name,
        "scenario": {
            "scenario_id": scenario["scenario_id"],
            "equipment_id": scenario["equipment_id"],
            "alarm_code": scenario["alarm_code"],
            "process_name": scenario["process_name"],
            "situation": scenario["situation"],
        },
        "guardrail_result": guardrail_result,
        "sections": sections,
        "output_files": output_files,
        "education_message": "Agent는 리포트 작성기만이 아니라 다양한 업무 행동을 수행할 수 있습니다.",
    }
    trace = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "action_type": action_type,
        "action_name": action_name,
        "equipment_id": scenario["equipment_id"],
        "alarm_code": scenario["alarm_code"],
        "status": "success",
    }

    markdown_path.write_text(markdown_text, encoding="utf-8-sig")
    json_path.write_text(json.dumps(json_result, ensure_ascii=False, indent=2), encoding="utf-8")
    trace_path.write_text(json.dumps(trace, ensure_ascii=False) + "\n", encoding="utf-8")

    print("[Day5 Agent Action Lab]")
    print(f"- 실행 Action: {action_name}")
    print(f"- Guardrail 결과: {guardrail_result['status']}")
    print("- 사용 시나리오: 교육용 가상 제조 시나리오")
    print("- 결과 저장 경로:")
    print("  - outputs/day5/action_lab_result.md")
    print("  - outputs/day5/action_lab_result.json")
    print("  - outputs/day5/action_lab_trace.jsonl")


if __name__ == "__main__":
    main()
