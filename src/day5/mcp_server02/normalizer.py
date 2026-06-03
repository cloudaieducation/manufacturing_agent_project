# -*- coding: utf-8 -*-
"""
Day4 Tool Selection Normalizer
==============================

[이 모듈의 역할 — 전체 파이프라인에서의 위치]
사용자 질문(user_query)
  → prompt_builder          : 질문을 LLM 프롬프트로 구성
  → runner.generate_tool_plan: LLM(또는 fallback) 호출로 raw Tool Plan 생성
  → ★ normalizer (이 파일)  : 검증 전 plan 구조 보정  ← 현재 파일
  → validation              : Tool Contract 규칙 검증
  → repair                  : 검증 실패 항목 수정 시도
  → finalize / results      : 최종 plan 확정 및 결과 집계
  → report / output_writer  : 리포트 렌더링 및 JSON 저장

[핵심 원칙 — 반드시 숙지]
1. normalization은 validation rule을 '완화'하는 것이 아니라,
   검증 전에 plan의 구조를 보정하는 것이다.
   즉 Tool Contract 기준을 바꾸거나 느슨하게 하는 것이 아니라,
   LLM/repair가 만든 plan을 계약이 요구하는 형태로 사전 정렬하는 과정이다.
   이 점을 파이프라인 전체에서 반드시 구분해야 한다.

2. normalization은 case_id, expected_tools, expected_arguments를 절대 보지 않는다.
   모든 보정은 (1) Tool Contract, (2) user_query에서 추출한 entity,
   (3) 교육용 가상 제조 시나리오 master data(EDUCATIONAL_EQUIPMENT_CONTEXT 등) 만으로 수행한다.
   테스트 정답(expected_*)이 개입하면 보정이 정답 맞추기로 변질되므로 엄격히 금지한다.

3. runner.py는 normalize_plan_for_validation()을 호출해 generate → validate 흐름을 유지한다.
   normalization 결과(normalized_plan)는 validation/repair 단계에서 base plan으로 사용된다.

[모드 요약]
- "none"         : 보정 없음. raw plan을 그대로 validation에 넘긴다.
- "argument-only": argument 값만 보정(Tool 추가 없음). action tool policy 미적용.
- "full"         : argument 보정 → 중복 제거 → action tool policy → 재보정 → 재중복제거 → renumber.

[강한 차단(strong block) 요청에서는 normalization을 적용하지 않는 이유]
개인정보·무제한 조회·실제 내부 데이터 요청은 guardrail이 거부해야 할 요청이다.
이런 요청에 normalization으로 Tool을 채우거나 argument를 보강하면,
guardrail이 거부한 요청을 우회시키는 결과가 될 수 있다.
따라서 강한 차단 요청에서는 "none" 모드 제외, 어떤 보정도 수행하지 않는다.
"""
# copy: none 모드/강한 차단 요청에서 raw plan 을 deepcopy 해 원본 훼손 없이 그대로 돌려줄 때 사용.
import copy
# json: deduplicate 시 arguments 를 sort_keys 로 직렬화해 '동일 (tool_name, arguments)' 중복 키를 만들 때 사용.
import json
# re: user_query 에서 설비 ID/알람 코드/라인 ID 같은 교육용 entity 를 추출하는 정규식에 사용.
import re

# TOOL_CONTRACTS: 정규화의 모든 기준. required/any_of/optional 정의에 맞춰 argument 를 보정한다.
#                 normalization 은 이 계약을 '완화'하지 않고, plan 을 계약 형태로 사전 정렬할 뿐이다.
from day5.mcp_server02.contracts import TOOL_CONTRACTS


# ===========================================================================
# 운영형 Plan Normalization (validation 전에 Tool Contract에 맞춰 plan 정규화)
#
# ─── 매우 중요한 원칙 (전체 파이프라인에서 반복 숙지) ───────────────────────
# 1. 여기 있는 어떤 함수도 case_id / expected_tools / expected_arguments를 보지 않는다.
#    → 테스트 케이스의 정답을 몰래 참조하면 평가 자체가 무의미해진다.
#
# 2. 모든 보정은 (1) Tool Contract, (2) user_query에서 추출한 entity,
#    (3) 교육용 가상 제조 시나리오 기준 master data만으로 수행한다.
#    → 아래 EDUCATIONAL_EQUIPMENT_CONTEXT / EDUCATIONAL_ALARM_CONTEXT 참조.
#
# 3. normalization은 validation rule 또는 Tool Contract를 절대 완화하지 않는다.
#    LLM/repair가 만든 plan을 검증 전에 계약 형태로 정상화할 뿐이다.
#    "정답 보정"이 아닌 "구조 보정"임을 항상 명심한다.
# ===========================================================================

# ---------------------------------------------------------------------------
# [상수 그룹 1] EDUCATIONAL_EQUIPMENT_CONTEXT
# ---------------------------------------------------------------------------
# 목적: 설비 ID(EQP-*)로부터 라인 ID, 공정명, 설비 유형을 연결하는 교육용 master data.
#
# 사용 시점: extract_entities_from_query()에서 user_query에 설비 ID가 있을 때
#           라인·공정 컨텍스트를 자동 보강하기 위해 참조한다.
#           normalize_tool_arguments()에서 argument 보정 근거 source로도 사용된다.
#
# 변경 시 영향: 이 dict를 수정하면 entity 추출 결과(equipment_id → line_id, process_name)가
#              달라지고, argument 보정 내용이 바뀐다.
#              테스트 케이스 정답 기준이 아니라 교육 시나리오 가상 설비 정의임에 유의한다.
#
# 교육용 가상 시나리오 기준:
#   EQP-EV-03 → EDU-LINE-01 / 증착 공정 (DisplayEdu Fab 허구 데이터)
#   실제 제조 기업의 설비 ID·라인명이 아니다.
EDUCATIONAL_EQUIPMENT_CONTEXT = {
    "EQP-EV-03": {
        "line_id": "EDU-LINE-01",
        "process_name": "증착 공정",
        "equipment_type": "증착 설비",
    },
}

# ---------------------------------------------------------------------------
# [상수 그룹 2] EDUCATIONAL_ALARM_CONTEXT
# ---------------------------------------------------------------------------
# 목적: 알람 코드(ALM-*)로부터 기본 설비 ID, 공정명, 라인 ID를 연결하는 교육용 master data.
#
# 사용 시점: extract_entities_from_query()에서 user_query에 알람 코드만 있고
#           설비 ID가 없을 때, 알람 코드로부터 기본 설비 ID 등을 보강하기 위해 참조한다.
#           설비 ID가 명시된 경우에는 이 dict를 참조하지 않는다(우선순위 낮음).
#
# 변경 시 영향: 알람→설비 매핑이 변경되면 entity 추출 결과가 달라지고
#              downstream argument 보정에도 영향을 준다.
#
# 교육용 가상 시나리오 기준:
#   ALM-TEMP-402 → EQP-EV-03 / 증착 공정 / EDU-LINE-01 (DisplayEdu Fab 허구 데이터)
#   실제 알람 코드 체계가 아니다.
EDUCATIONAL_ALARM_CONTEXT = {
    "ALM-TEMP-402": {
        "default_equipment_id": "EQP-EV-03",
        "process_name": "증착 공정",
        "line_id": "EDU-LINE-01",
    },
}

# ---------------------------------------------------------------------------
# [상수 그룹 3] METRIC_KEYWORD_MAP
# ---------------------------------------------------------------------------
# 목적: user_query에서 측정 지표(metric) 키워드를 탐지하여
#       get_quality_metrics 등의 metric_name argument를 보정할 때 사용한다.
#
# 구조: (metric_name, [키워드 목록]) 튜플 리스트.
#   - metric_name: Tool Contract의 metric_name argument에 채울 표준 값
#   - 키워드 목록: user_query(소문자 변환)에서 검색할 표현들
#
# 사용 시점: extract_entities_from_query() → metric_candidates 리스트 생성 시.
#           _resolve_entity_value("metric_name", ...)에서 첫 번째 후보를 반환한다.
#
# 변경 시 영향: 키워드를 추가하면 entity 추출의 metric_candidates가 달라지고,
#              get_quality_metrics의 metric_name 보정 결과가 바뀐다.
#              교육용 가상 시나리오의 측정 지표 명칭 기준이다.
METRIC_KEYWORD_MAP = [
    ("defect_rate", ["defect_rate", "불량률"]),
    ("particle_count", ["particle_count", "particles", "파티클"]),
    ("yield_rate", ["수율", "yield"]),
    ("thickness_uniformity", ["박막 두께 균일도", "thickness", "uniformity", "균일도"]),
]

# ---------------------------------------------------------------------------
# [상수 그룹 4] ACTION_TOOL_POLICY
# ---------------------------------------------------------------------------
# 목적: user_query에서 추론된 action intent별로 근거 수집에 필요한 Tool 목록을 정의한다.
#
# 핵심 원칙(반복):
#   - 이 Policy는 expected_tools를 참조하거나 대체하는 것이 아니다.
#   - user_query의 표현에서 드러난 action intent에 필요한 근거 Tool을 보강하는 일반 규칙이다.
#   - normalization은 이 Policy를 사용해 누락된 Tool을 추가하고,
#     이후 normalize_tool_arguments에서 argument를 채운다.
#
# 사용 시점: apply_action_tool_policy_if_needed() → full 모드에서만 적용.
#           argument-only / none 모드에서는 사용하지 않는다.
#
# 변경 시 영향:
#   - Tool 목록을 바꾸면 full 모드에서 plan에 추가되는 Tool이 달라진다.
#   - 새 intent를 추가하면 ACTION_INTENT_KEYWORDS에도 동일한 키를 추가해야 한다.
#
# intent별 설명:
#   root_cause_ranking    : 원인 후보를 근거 기반으로 순위 매기기 (전체 근거 Tool 필요)
#   checklist_generation  : 현장 초기 점검 체크리스트 생성 (이력·상태·메뉴얼 필요)
#   team_routing          : 정보를 공유할 부서/팀 결정 (전체 근거 Tool 필요)
#   monitoring_rule_generation: 재발 감시 조건 생성 (이벤트·상태·메뉴얼 필요)
#   work_instruction_draft: 점검 작업 지시 초안 생성 (설비·이벤트·이력·메뉴얼 필요)
ACTION_TOOL_POLICY = {
    "root_cause_ranking": [
        "get_equipment_status",
        "get_recent_alarm_events",
        "get_process_status",
        "get_quality_metrics",
        "get_maintenance_history",
        "search_manual",
    ],
    "checklist_generation": [
        "get_recent_alarm_events",
        "get_process_status",
        "get_quality_metrics",
        "search_manual",
    ],
    "team_routing": [
        "get_equipment_status",
        "get_recent_alarm_events",
        "get_process_status",
        "get_quality_metrics",
        "get_maintenance_history",
        "search_manual",
    ],
    "monitoring_rule_generation": [
        "get_recent_alarm_events",
        "get_process_status",
        "get_quality_metrics",
        "search_manual",
    ],
    "work_instruction_draft": [
        "get_equipment_status",
        "get_recent_alarm_events",
        "get_process_status",
        "get_maintenance_history",
        "search_manual",
    ],
}


# ---------------------------------------------------------------------------
# [상수 그룹 5] ACTION_INTENT_KEYWORDS
# ---------------------------------------------------------------------------
# 목적: user_query 텍스트에서 action intent를 추론하기 위한 키워드 사전.
#
# 구조: {intent: {"strong": [...], "weak": [...]}}
#   strong 키워드: 1개만 있어도 해당 intent를 후보로 인정한다.
#                 명확하게 특정 산출물을 지시하는 표현들.
#   weak 키워드  : 2개 이상 있어야 후보로 인정한다.
#                 단어 하나로 intent를 과도하게 확정하는 오탐을 방지하기 위한 장치.
#
# 핵심 원칙(반복):
#   - 이 키워드는 user_query 표현에서 intent를 추론하는 용도이다.
#   - case_id / expected_tools / expected_arguments를 전혀 보지 않는다.
#   - intent 추론 결과는 ACTION_TOOL_POLICY와 연동되어 누락 Tool을 보강한다.
#
# 사용 시점: infer_action_intent() → apply_action_tool_policy_if_needed()
#           → full 모드에서만 적용.
#
# 변경 시 영향:
#   - 키워드를 추가/제거하면 intent 추론 결과가 달라지고,
#     plan에 추가되는 Tool이 바뀐다.
#   - weak 키워드를 너무 넓게 잡으면 오탐이 늘어난다(팀명 단어 하나 등).
ACTION_INTENT_KEYWORDS = {
    "root_cause_ranking": {
        # 원인 후보를 명시적으로 순서화/랭킹 요청하는 표현
        "strong": ["원인 후보", "가능성 순서", "랭킹", "원인 후보를"],
        # 원인 분석·나열 요청이지만 단어 하나로는 과확정되는 표현
        "weak": [
            "가능한 원인", "원인 가능성", "발생 원인", "발생 배경",
            "확인해야 할 원인", "원인 관점", "근거를 바탕으로 원인",
            "원인을 단정하지 말고", "확정 원인은 말하지 말고",
            "가능성 있는 원인",
        ],
    },
    "checklist_generation": {
        # 체크리스트·1차 확인 등 산출물 유형을 직접 명시하는 표현
        "strong": ["체크리스트", "1차 확인", "10분 안에 확인"],
        # 초기 점검·빠른 확인 계열이지만 단독으로는 모호한 표현
        "weak": [
            "초기 점검 항목", "먼저 확인해야 할 항목", "현장 초기 확인",
            "빠르게 먼저 확인", "빠르게 확인해야 할", "점검 항목",
            "초기 대응 항목", "현장에서 먼저 확인", "초기 점검",
            "초기 점검 항목을 묶어",
        ],
    },
    "team_routing": {
        # 어느 부서/팀에 정보를 공유·전달할지 명시적으로 묻는 표현
        "strong": [
            "어디에 먼저 공유", "라우팅", "우선 공유 대상",
            "우선 검토 부서", "어느 팀에 전달", "누구에게 공유",
        ],
        # 팀명 단어·방향 판단 계열이지만 단독으로는 모호한 표현
        # (오탐 방지: _is_team_routing_candidate 방향 marker와 함께 있을 때만 후보 인정)
        "weak": [
            "어느 관점에서 먼저", "설비팀", "공정팀", "품질팀", "정비팀",
            "먼저 봐야 할지", "판단할 수 있도록", "공유", "전달", "부서",
        ],
    },
    "monitoring_rule_generation": {
        # 재발 감시·모니터링 조건 생성을 명시적으로 요청하는 표현
        "strong": ["감시 조건", "재발 감시", "모니터링 조건"],
        # 재발 여부·추적 기준 계열이지만 단독으로는 모호한 표현
        "weak": [
            "추적 기준", "다시 나타나는지", "재발 여부", "발생 패턴",
            "감지 기준", "관찰 기준", "기준을 만들", "다시 발생하는지",
            "알람 발생 패턴", "추적할 기준",
        ],
    },
    "work_instruction_draft": {
        # 점검 작업 지시 초안 생성을 명시적으로 요청하는 표현
        "strong": ["작업 지시 초안", "점검 작업 지시", "점검 항목 중심"],
        # 점검 안내·가이드 계열이지만 단독으로는 모호한 표현
        "weak": [
            "교육용 점검 안내", "점검 안내 초안", "점검 가이드",
            "점검 절차 초안", "작업 안내 초안", "실제 조치가 아니라",
            "점검 중심으로 구성", "교육용 1차 점검", "점검 중심으로",
        ],
    },
}

# ---------------------------------------------------------------------------
# [상수 그룹 6] ACTION_INTENT_PRIORITY
# ---------------------------------------------------------------------------
# 목적: 여러 intent 후보의 score가 동점일 때만 적용하는 우선순위 리스트.
#
# 설계 의도:
#   - score가 다른 경우에는 이 우선순위를 무시하고 score가 높은 intent를 선택한다.
#   - 동점에서만 아래 순서를 사용해 더 구체적인 산출물 intent를 앞에 둔다.
#   - root_cause_ranking은 "원인" 계열 표현이 넓게 잡힐 수 있어 가장 뒤에 두어
#     다른 구체적 intent와 공존할 때 우선순위를 낮게 유지한다.
#
# 사용 시점: infer_action_intent() → score 동점 처리 시.
#
# 변경 시 영향: 우선순위 변경은 동점 발생 케이스에서만 결과를 바꾼다.
#             score 차이가 있는 케이스에는 영향 없음.
ACTION_INTENT_PRIORITY = [
    "work_instruction_draft",      # 작업 지시 — 가장 구체적·명시적 산출물
    "monitoring_rule_generation",  # 감시 조건 — 구체적 산출물
    "team_routing",                # 팀 라우팅 — 방향 결정
    "checklist_generation",        # 체크리스트 — 점검 목록
    "root_cause_ranking",          # 원인 랭킹 — 표현이 넓어 후순위
]


def extract_entities_from_query(user_query):
    """
    user_query 텍스트에서만 entity를 추출한다.

    [반환 형태]
    {
        "equipment_id"       : str | None  — 설비 ID (EQP-*)
        "equipment_id_in_text": bool       — user_query에 설비 ID가 명시되어 있는지 여부
                                             (교육 컨텍스트로 보강된 경우 False)
        "alarm_code"         : str | None  — 알람 코드 (ALM-*)
        "process_name"       : str | None  — 공정명 (예: "증착 공정")
        "line_id"            : str | None  — 라인 ID (EDU-LINE-*)
        "metric_candidates"  : list[str]   — 측정 지표 후보 목록 (METRIC_KEYWORD_MAP 기준)
    }

    [호출 시점]
    normalize_tool_arguments() 진입 시점에 호출되어 argument 보정의 근거 entity를 준비한다.
    infer_action_intent()에서는 직접 호출하지 않는다(키워드 기반 추론이므로 별도).

    [핵심 원칙 반복]
    case_id / expected_tools / expected_arguments는 절대 보지 않는다.
    교육용 시나리오 master data(EDUCATIONAL_EQUIPMENT_CONTEXT, EDUCATIONAL_ALARM_CONTEXT)로
    설비 ↔ 공정 ↔ 라인 컨텍스트를 연결한다.
    이 master data는 테스트 정답이 아니라 가상 제조 시나리오의 컨텍스트 정의다.

    [주의사항]
    equipment_id_in_text=False인 경우(알람 컨텍스트로 보강된 경우),
    argument 보정의 reason source 레이블을 "educational scenario context"로 표기한다.
    이 구분은 normalize_tool_arguments()의 source 레이블 분기에서 사용된다.
    """
    text = str(user_query or "")
    upper = text.upper()
    lower = text.lower()

    # ── 정규식 패턴 설명 ──────────────────────────────────────────────────
    # Python re의 \b는 한글 인접 시 숫자-한글 경계를 인식하지 못한다.
    # 예: "EQP-EV-03에서" → \b로는 "03"과 "에" 사이에 경계가 없어 매칭 실패.
    # 해결: (?<![A-Z0-9]) / (?![A-Z0-9]) 로 앞뒤에 영숫자가 없음을 확인한다.
    #
    # EQP-[A-Z]+-\d+ : 설비 ID 패턴 (EQP-EV-03, EQP-CV-01 등 교육 시나리오 ID)
    # ALM-[A-Z]+-\d+ : 알람 코드 패턴 (ALM-TEMP-402 등 교육 시나리오 알람 코드)
    # EDU-LINE-\d+   : 라인 ID 패턴 (EDU-LINE-01 등 교육 시나리오 라인 ID)
    equip_match = re.search(r"(?<![A-Z0-9])EQP-[A-Z]+-\d+(?![A-Z0-9])", upper)
    alarm_match = re.search(r"(?<![A-Z0-9])ALM-[A-Z]+-\d+(?![A-Z0-9])", upper)
    line_match = re.search(r"(?<![A-Z0-9])EDU-LINE-\d+(?![A-Z0-9])", upper)

    # ── 기본 entity 추출 ─────────────────────────────────────────────────
    equipment_id = equip_match.group(0) if equip_match else None
    alarm_code = alarm_match.group(0) if alarm_match else None
    line_id = line_match.group(0) if line_match else None
    # 설비 ID가 user_query 텍스트에 직접 명시되어 있는지 여부를 기록.
    # 이후 argument 보정 시 source 레이블("query entity" vs "educational scenario context")을
    # 구분하는 데 사용한다.
    equipment_id_in_text = equipment_id is not None

    # ── 공정명 추출 (키워드 기반) ────────────────────────────────────────
    # 현재는 "증착 공정"만 지원한다. 다른 공정(식각·세정 등)이 추가되면 여기에 분기 추가.
    process_name = None
    if any(k in text for k in ["박막 증착", "증착"]) or any(
        k in lower for k in ["thin film deposition", "deposition"]
    ):
        process_name = "증착 공정"

    # ── 설비 ID 기준 컨텍스트 연결 ───────────────────────────────────────
    # user_query에 설비 ID가 있고 EDUCATIONAL_EQUIPMENT_CONTEXT에 등록된 경우,
    # 라인 ID / 공정명을 자동 보강한다(이미 추출된 값은 덮어쓰지 않는다).
    if equipment_id in EDUCATIONAL_EQUIPMENT_CONTEXT:
        ctx = EDUCATIONAL_EQUIPMENT_CONTEXT[equipment_id]
        if not line_id:
            line_id = ctx["line_id"]
        if not process_name:
            process_name = ctx["process_name"]

    # ── 알람 코드 기준 컨텍스트 연결 (설비 ID가 없을 때만) ──────────────
    # 설비 ID가 없고 알람 코드만 있으면, EDUCATIONAL_ALARM_CONTEXT에서
    # 기본 설비 ID·라인 ID·공정명을 가져온다.
    # 이 경우 equipment_id_in_text는 False로 유지되어
    # normalize_tool_arguments에서 source 레이블이 "educational scenario context"로 표기된다.
    if not equipment_id and alarm_code in EDUCATIONAL_ALARM_CONTEXT:
        ctx = EDUCATIONAL_ALARM_CONTEXT[alarm_code]
        equipment_id = ctx["default_equipment_id"]
        if not line_id:
            line_id = ctx["line_id"]
        if not process_name:
            process_name = ctx["process_name"]

    # ── 측정 지표 후보 목록 생성 ──────────────────────────────────────────
    # METRIC_KEYWORD_MAP의 각 항목에 대해 user_query(소문자)에서 키워드를 탐색.
    # 여러 지표가 매칭될 수 있으므로 리스트로 수집한다.
    # _resolve_entity_value에서 첫 번째 후보만 사용하므로 순서가 중요하다.
    metric_candidates = []
    for metric_name, keywords in METRIC_KEYWORD_MAP:
        if any(kw.lower() in lower for kw in keywords):
            metric_candidates.append(metric_name)

    return {
        "equipment_id": equipment_id,
        "equipment_id_in_text": equipment_id_in_text,
        "alarm_code": alarm_code,
        "process_name": process_name,
        "line_id": line_id,
        "metric_candidates": metric_candidates,
    }


def is_strong_block_request(user_query):
    """
    강한 차단 요청인지 판단한다. True이면 normalization을 적용하지 않는다.

    [강한 차단 요청 유형]
    1. 개인정보 요청 : 작업자 이름, 사번, 이메일, 연락처 등
    2. 과도 조회 요청: 전체 데이터·모든 로그·무제한 조회 등
    3. 실제 내부 정보: 실제 사내 라인명·설비명·수율 등 (교육 시나리오 범위 초과)
    4. 입력 부족    : "모르지만"처럼 필수 정보가 없음을 인정한 채 진행 요구
    5. 승인 없는 작업: 승인 없이 실제 작업자가 수행할 지시 작성 요청

    [normalization을 적용하지 않는 이유]
    강한 차단 요청은 guardrail이 거부해야 하는 요청이다.
    이런 요청에 normalization으로 Tool을 보강하거나 argument를 채우면
    guardrail의 거부 대상 요청을 우회시키는 결과가 된다.
    따라서 "none" 모드를 제외한 argument-only/full 모드 모두에서
    강한 차단 요청이면 raw plan을 그대로 반환하고 어떤 보정도 수행하지 않는다.

    [주의] 원인 확정 요구(단정·단언 요청)는 강한 차단이 아니다.
    원인 확정을 요구해도 근거 수집 Tool 선택 자체는 가능하며,
    LLM/validation 단계에서 별도로 처리된다.

    [호출 시점]
    normalize_plan_for_validation()에서 none 모드 분기 이후 즉시 호출된다.
    """
    text = str(user_query or "")
    lower = text.lower()

    # ── 그룹별 차단 키워드 ────────────────────────────────────────────────
    # 개인정보 관련: 작업자 개인 식별 정보 요청
    personal_info = ["작업자 이름", "담당자 이름", "담당자", "사번", "이메일", "연락처", "전화번호", "개인 연락처"]
    # 과도 조회: 데이터 범위 제한 없는 전체 조회 요청
    over_query = ["전체 데이터", "모든 데이터", "모든 로그", "전체 로그", "제한 없이", "무제한", "전부 조회", "전체 조회"]
    # 실제 내부 정보: 교육 시나리오 범위를 넘어 실제 사내 데이터 요청
    real_internal = ["실제 내부", "실제 사내", "실제 라인명", "실제 설비명", "실제 수율", "내부 라인명", "내부 설비명"]
    # 입력 부족: 필수 정보가 없음을 인정하면서 진행을 요구하는 표현
    insufficient = ["모르지만"]
    # 승인 없는 실제 작업 지시: 안전 절차 우회 위험
    unsafe_work = ["승인 없이", "승인 없는", "실제 작업자가 바로 수행할 작업 지시"]

    # 하나라도 매칭되면 즉시 True 반환
    for group in (personal_info, over_query, real_internal, insufficient, unsafe_work):
        if any(keyword in text for keyword in group):
            return True
    # 영문 표현 보조 검사 (소문자 변환 후 매칭)
    if any(k in lower for k in ["without approval", "no limit", "unlimited"]):
        return True
    return False


def _is_empty(value):
    """argument 값이 비어있는지(None 또는 빈 문자열) 판단.

    normalize_tool_arguments에서 required·any_of·optional argument의
    누락 여부를 확인하는 데 사용한다.
    0, False, 빈 리스트 등은 빈 값으로 보지 않는다.
    """
    return value in (None, "")


def _resolve_entity_value(arg_name, entities, user_query):
    """argument 이름별로 entity/교육 컨텍스트에서 채울 값을 돌려준다 (없으면 None).

    [입력]
    - arg_name  : Tool Contract의 argument 이름 (예: "equipment_id", "limit")
    - entities  : extract_entities_from_query()가 반환한 entity dict
    - user_query: 원본 질문 텍스트 ("query" argument 보정 시 사용)

    [반환]
    보정에 사용할 값. entity에서 찾을 수 없으면 None을 반환한다.
    None 반환 시 normalize_tool_arguments에서 해당 argument를 보정하지 않는다.

    [호출 시점]
    normalize_tool_arguments()의 required 보정 루프 및
    any_of_required 미충족 보정 루프에서 각 argument 이름에 대해 호출된다.

    [각 argument별 보정 방식]
    - equipment_id : entities["equipment_id"] (설비 ID — 텍스트 or 알람 컨텍스트 보강)
    - process_name : entities["process_name"] (공정명 — 컨텍스트 연결 후 값)
    - line_id      : entities["line_id"] (라인 ID)
    - alarm_code   : entities["alarm_code"] (알람 코드)
    - metric_name  : metric_candidates 첫 번째 후보 (없으면 None)
    - limit        : 고정값 20 (과도 조회 방지를 위한 기본 제한)
    - date_range   : 고정값 "recent" (최근 데이터 조회 기본값)
    - query        : user_query 앞 200자 (검색 질의) 또는 알람코드+"조치 절차"
    - 그 외        : None (보정하지 않음)
    """
    if arg_name == "equipment_id":
        return entities.get("equipment_id")
    if arg_name == "process_name":
        return entities.get("process_name")
    if arg_name == "line_id":
        return entities.get("line_id")
    if arg_name == "alarm_code":
        return entities.get("alarm_code")
    if arg_name == "metric_name":
        cands = entities.get("metric_candidates") or []
        return cands[0] if cands else None
    if arg_name == "limit":
        return 20
    if arg_name == "date_range":
        return "recent"
    if arg_name == "query":
        alarm = entities.get("alarm_code")
        base = str(user_query or "").strip()
        if base:
            return base[:200]
        if alarm:
            return f"{alarm} 조치 절차"
        return None
    return None


def _fill_reason(arg_name, entities, source_label):
    """normalization rule용 reason 문자열을 만든다.

    [호출 시점]
    normalize_tool_arguments()에서 required argument 보정 시
    rule 항목의 "reason" 필드를 생성할 때 사용한다.

    [source_label]
    - "query entity"              : user_query 텍스트에서 직접 추출한 경우
    - "educational scenario context": 알람 컨텍스트 등 master data에서 보강한 경우
    이 구분은 downstream 리포트에서 보정 근거를 투명하게 설명하는 데 사용된다.
    """
    return (
        f"Tool Contract requires/normalizes '{arg_name}'. "
        f"Filled from {source_label}."
    )


def normalize_tool_arguments(tool_plan, user_query):
    """
    plan의 각 Tool item을 Tool Contract에 맞게 argument 정규화한다.

    [반환] (정규화된 plan dict, rules 리스트)

    [수행 순서 — 4단계]
    (1) 정의되지 않은 argument 제거  : Tool Contract에 없는 key 삭제 (rule_type: argument_removed)
    (2) required argument 보정      : 누락된 필수 argument를 entity로 채움 (argument_normalization)
    (3) any_of_required 미충족 보정 : any_of_required 중 하나도 없으면 우선순위에 따라 채움
    (4) 유용한 optional argument 보정: limit / date_range / alarm_code를 기본값으로 채움

    [핵심 원칙 반복]
    - case_id / expected_* 는 절대 보지 않는다. 이 함수는 정답 맞추기 수단이 아니다.
    - normalization은 Tool Contract를 완화하는 것이 아니라,
      plan을 검증 전에 계약 형태로 정렬하는 구조 보정이다.
    - Tool Contract에 없는 Tool(unknown/forbidden)은 건드리지 않고 validation에 넘긴다.

    [호출 시점]
    normalize_plan_for_validation()에서
    - argument-only 모드: 1회 호출
    - full 모드: action tool policy 적용 전후 2회 호출 (새로 추가된 Tool의 argument 보정 포함)

    [변경 시 영향]
    이 함수를 수정하면 argument 보정 결과, rule 생성 내용,
    downstream validation 통과율이 달라진다.
    """
    rules = []
    # plan 형태 검증: dict가 아니거나 "plan" 키가 없으면 보정 없이 반환
    if not isinstance(tool_plan, dict) or not isinstance(tool_plan.get("plan"), list):
        return tool_plan, rules

    # user_query에서 entity 추출 — 이 함수의 모든 보정은 이 entity 기반
    entities = extract_entities_from_query(user_query)
    # 설비 ID가 텍스트에 직접 명시되어 있는지 여부 (source 레이블 분기용)
    eq_in_text = entities.get("equipment_id_in_text", False)
    new_items = []

    for item in tool_plan["plan"]:
        # 비정상 item(dict가 아닌 경우)은 그대로 유지하고 validation에 넘긴다
        if not isinstance(item, dict):
            new_items.append(item)
            continue

        tool_name = item.get("tool_name")
        contract = TOOL_CONTRACTS.get(tool_name)
        new_item = dict(item)
        args = dict(new_item.get("arguments") or {})

        # ── contract가 없는 Tool: unknown/forbidden Tool ────────────────
        # Tool Contract에 등록되지 않은 Tool은 normalization 대상이 아니다.
        # 건드리지 않고 그대로 new_items에 추가하여 validation이 거부하게 한다.
        if not contract:
            new_item["arguments"] = args
            new_items.append(new_item)
            continue

        # Tool Contract에서 argument 분류 추출
        required = contract.get("required_arguments", []) or []
        any_of = contract.get("any_of_required_arguments", []) or []
        optional = contract.get("optional_arguments", []) or []
        # Contract에 정의된 모든 argument 이름 집합 (정의 외 argument 제거 기준)
        known = set(required) | set(any_of) | set(optional)

        # ── (1) 정의되지 않은 argument 제거 ────────────────────────────
        # Tool Contract에 없는 key가 있으면 validation 전에 제거한다.
        # 이는 Contract를 완화하는 것이 아니라, LLM이 잘못 생성한 key를 사전 정리하는 것이다.
        for key in list(args.keys()):
            if key not in known:
                removed_val = args.pop(key)
                rules.append({
                    "rule_id": f"ARGRM-{tool_name}-{key}",
                    "rule_type": "argument_removed",
                    "tool_name": tool_name,
                    "before": {key: removed_val},
                    "after": {},
                    "reason": f"'{key}' is not defined in the Tool Contract for {tool_name}; removed before validation.",
                })

        # ── (2) required argument 보정 ──────────────────────────────────
        # required argument가 누락(None/"")인 경우 entity에서 값을 찾아 채운다.
        # entity에서 값을 찾지 못하면(value is None) 보정하지 않는다.
        # → validation에서 required argument 누락으로 검증 실패하게 된다.
        for key in required:
            if _is_empty(args.get(key)):
                value = _resolve_entity_value(key, entities, user_query)
                if value is not None:
                    # source 레이블: 설비 ID가 텍스트에 있으면 "query entity",
                    # 알람 컨텍스트 보강이면 "educational scenario context"
                    source = "query entity" if (key == "equipment_id" and eq_in_text) else "educational scenario context"
                    # limit / date_range / query는 query에서 직접 파생되므로 "query entity"
                    if key in ("limit", "date_range", "query"):
                        source = "query entity"
                    args[key] = value
                    rules.append({
                        "rule_id": f"ARG-{tool_name}-{key}",
                        "rule_type": "argument_normalization",
                        "tool_name": tool_name,
                        "before": {key: None},
                        "after": {key: value},
                        "reason": _fill_reason(key, entities, source),
                    })

        # ── (3) any_of_required 미충족 시 보정 ─────────────────────────
        # any_of_required는 "리스트 중 최소 1개 이상 있어야 함" 조건이다.
        # 하나도 없을 때만 Tool별 우선순위(_anyof_fill_order)에 따라 하나를 채운다.
        # 여러 개를 채우면 Contract 의도를 넘어서므로 첫 번째로 채울 수 있는 값 하나만 보정.
        if any_of:
            satisfied = any((not _is_empty(args.get(k))) for k in any_of)
            if not satisfied:
                fill_order = _anyof_fill_order(tool_name, any_of)
                for key in fill_order:
                    value = _resolve_entity_value(key, entities, user_query)
                    if value is not None:
                        source = "query entity" if (key == "equipment_id" and eq_in_text) else "educational scenario context"
                        args[key] = value
                        rules.append({
                            "rule_id": f"ARG-{tool_name}-anyof-{key}",
                            "rule_type": "argument_normalization",
                            "tool_name": tool_name,
                            "before": {k: None for k in any_of},
                            "after": {key: value},
                            "reason": (
                                f"{tool_name} requires one of {any_of}; "
                                f"filled '{key}' from {source}."
                            ),
                        })
                        break  # any_of 조건 충족 → 더 이상 보정하지 않음

        # ── (4) 유용한 optional argument 기본값 보정 ─────────────────
        # limit / date_range는 optional이지만 누락 시 과도 조회나 범위 미지정 문제가 있다.
        # alarm_code는 optional이지만 entity에 있으면 채우는 편이 Tool 실행에 유리하다.
        # rule 기록 없이 조용히 채운다(사소한 기본값 보정).
        if "limit" in optional and _is_empty(args.get("limit")):
            args["limit"] = 20
        if "date_range" in optional and _is_empty(args.get("date_range")):
            args["date_range"] = "recent"
        if "alarm_code" in optional and _is_empty(args.get("alarm_code")) and entities.get("alarm_code"):
            args["alarm_code"] = entities["alarm_code"]

        new_item["arguments"] = args
        new_items.append(new_item)

    return {"plan": new_items}, rules


def _anyof_fill_order(tool_name, any_of):
    """any_of_required 보정 시 Tool별 우선순위 순서를 돌려준다.

    [입력]
    - tool_name: 대상 Tool 이름
    - any_of   : Tool Contract의 any_of_required_arguments 리스트

    [반환]
    any_of 항목을 Tool별 선호 순서대로 재배열한 리스트.
    순서대로 값이 있는 첫 번째 항목을 보정에 사용한다.

    [Tool별 우선순위 설계 의도]
    - get_process_status   : 공정 조회이므로 process_name이 line_id보다 의미 있음
    - get_quality_metrics  : 설비→라인→지표 순으로 시도
    - 그 외 Tool           : Contract 정의 순서 그대로 사용

    [호출 시점]
    normalize_tool_arguments()의 any_of_required 보정 분기에서 호출된다.
    """
    if tool_name == "get_process_status":
        order = ["process_name", "line_id"]
    elif tool_name == "get_quality_metrics":
        order = ["equipment_id", "line_id", "metric_name"]
    else:
        order = list(any_of)
    # any_of에 정의된 것만, 우선순위대로 정렬 + 순서에 없는 항목은 뒤에 추가
    return [k for k in order if k in any_of] + [k for k in any_of if k not in order]


def deduplicate_tool_plan(tool_plan):
    """
    같은 tool_name + 같은 argument 조합의 중복 항목을 제거한다.

    [반환] (중복 제거된 plan dict, rules 리스트)

    [중복 판단 기준]
    (tool_name, JSON-직렬화된-arguments) 쌍이 동일한 경우를 중복으로 본다.
    arguments를 sort_keys=True로 직렬화하므로 key 순서 차이는 무시된다.

    [중복 허용 케이스]
    get_quality_metrics처럼 metric_name 등 argument가 다른 경우는
    같은 Tool이더라도 중복이 아니므로 유지한다.

    [deduplicate가 필요한 이유]
    full 모드에서 action tool policy로 Tool이 추가되면,
    LLM이 이미 생성한 Tool과 중복이 생길 수 있다.
    중복 항목이 있으면 validation에서 "동일 Tool 중복 호출" 오류가 발생할 수 있으므로
    renumber 전에 중복을 제거해 clean한 plan을 만든다.

    [호출 시점]
    normalize_plan_for_validation()에서
    - argument-only 모드: normalize_tool_arguments 이후 1회
    - full 모드: normalize_tool_arguments 이후 2회(action policy 전·후 각 1회)
    """
    rules = []
    # plan 형태 검증
    if not isinstance(tool_plan, dict) or not isinstance(tool_plan.get("plan"), list):
        return tool_plan, rules

    seen = set()
    new_items = []
    for item in tool_plan["plan"]:
        # 비정상 item은 그대로 통과
        if not isinstance(item, dict):
            new_items.append(item)
            continue
        tool_name = item.get("tool_name")
        args = item.get("arguments") or {}
        # JSON 직렬화로 중복 키 생성 (sort_keys로 key 순서 차이 무시)
        try:
            args_key = json.dumps(args, ensure_ascii=False, sort_keys=True)
        except Exception:
            # JSON 직렬화 실패 시(비직렬화 가능 값 등) str() fallback
            args_key = str(args)
        key = (tool_name, args_key)
        if key in seen:
            # 이미 동일한 (tool_name, arguments) 항목이 있으면 제거하고 rule 기록
            rules.append({
                "rule_id": f"DEDUP-{tool_name}",
                "rule_type": "deduplicate",
                "tool_name": tool_name,
                "before": {"duplicate_of": tool_name},
                "after": {},
                "reason": f"Removed duplicate {tool_name} with identical arguments.",
            })
            continue
        seen.add(key)
        new_items.append(item)

    return {"plan": new_items}, rules


def _keyword_hits(text, lower, keywords):
    """text/lower에 포함된 keyword 목록을 돌려준다.

    [입력]
    - text    : 원본 user_query 텍스트 (대소문자 구분 검색용)
    - lower   : text.lower() (소문자 변환 검색용)
    - keywords: 검색할 키워드 목록

    [반환]
    text 또는 lower에서 발견된 keyword 목록 (빈 keyword는 제외).

    [호출 시점]
    infer_action_intent()에서 각 intent의 strong/weak 키워드 hit 수를 계산할 때 사용한다.
    hit 수가 strong 1개 이상 또는 weak 2개 이상이면 해당 intent가 후보가 된다.
    """
    hits = []
    for keyword in keywords:
        if not keyword:
            continue
        if keyword in text or keyword.lower() in lower:
            hits.append(keyword)
    return hits


# ---------------------------------------------------------------------------
# [상수 그룹 7] TEAM_ROUTING_DIRECTION_MARKERS
# ---------------------------------------------------------------------------
# 목적: team_routing intent를 확정하기 위한 "방향 결정" marker 리스트.
#
# 설계 이유: ACTION_INTENT_KEYWORDS의 team_routing weak 키워드에는
#   "설비팀", "공정팀" 같은 팀명이 포함되어 있는데,
#   이 단어들은 단독으로 등장해도 team_routing과 무관한 문장일 수 있다.
#   예: "공정팀 측정 결과에 따르면..." → team_routing이 아닌 사실 언급.
#   방향 결정 marker("공유", "전달", "어느 팀", "라우팅" 등)가 함께 있을 때만
#   team_routing 후보로 인정하여 오탐을 줄인다.
#
# 사용 시점: infer_action_intent()에서 team_routing 후보 인정 여부를
#           _is_team_routing_candidate()를 통해 사전 검사할 때.
#
# 변경 시 영향: marker를 추가하면 team_routing 인정 범위가 넓어지고,
#             제거하면 좁아진다. 오탐/미탐의 균형에 영향을 준다.
TEAM_ROUTING_DIRECTION_MARKERS = [
    "공유", "전달", "부서", "먼저 봐야", "어느 관점에서 먼저",
    "어디에 먼저", "우선 검토", "우선 공유", "라우팅", "판단할 수 있도록",
    "어느 팀", "누구에게",
]


def _is_team_routing_candidate(text):
    """team_routing 방향 결정 marker가 하나라도 text에 있는지 반환한다.

    [호출 시점]
    infer_action_intent()에서 team_routing 후보 인정 사전 검사용.
    marker가 없으면 team_routing 후보에서 제외하여 오탐을 방지한다.
    """
    return any(marker in text for marker in TEAM_ROUTING_DIRECTION_MARKERS)


def infer_action_intent(user_query):
    """user_query에서 Action intent를 추론한다 (없으면 None).

    [반환]
    추론된 intent 문자열 (ACTION_INTENT_KEYWORDS의 key 중 하나) 또는 None.

    [추론 규칙 — 순서대로 적용]
    1. strong keyword 1개 이상 → intent 후보 인정, score = 2 + strong_count + min(weak_count, 2)
    2. strong 없고 weak 2개 이상 → intent 후보 인정, score = weak_count
    3. team_routing: TEAM_ROUTING_DIRECTION_MARKERS 중 하나라도 없으면 후보에서 제외(오탐 방지)
    4. 후보 중 score 최고값 intent를 선택한다.
    5. score 동점이면 ACTION_INTENT_PRIORITY 순서를 적용한다.

    [핵심 원칙 반복]
    - case_id / expected_tools / expected_arguments는 절대 보지 않는다.
    - user_query의 텍스트 표현만으로 intent를 추론한다.
    - 단어 하나로 intent를 과도하게 확정하지 않는다(strong/weak 임계값 설계 이유).

    [호출 시점]
    apply_action_tool_policy_if_needed()에서 action policy 적용 전 intent 판단용으로 사용한다.
    full 모드에서만 호출된다.
    """
    text = str(user_query or "")
    lower = text.lower()

    candidates = {}

    for intent, keyword_groups in ACTION_INTENT_KEYWORDS.items():
        strong_hits = _keyword_hits(text, lower, keyword_groups.get("strong", []))
        weak_hits = _keyword_hits(text, lower, keyword_groups.get("weak", []))

        # ── team_routing 오탐 방지 ──────────────────────────────────────
        # 방향 결정 marker 없이 팀명 단어만 있는 경우는 후보에서 제외한다.
        if intent == "team_routing" and not _is_team_routing_candidate(text):
            continue

        # ── 후보 score 계산 ──────────────────────────────────────────────
        if strong_hits:
            # strong keyword가 있으면 base score 2점 + strong 개수 + weak 최대 2점 가산
            # weak를 최대 2점으로 캡핑하여 weak 다수가 strong 효과를 과도히 올리지 않게 함
            candidates[intent] = 2 + len(strong_hits) + min(len(weak_hits), 2)
        elif len(weak_hits) >= 2:
            # strong 없이 weak만 있을 때는 2개 이상이어야 후보 인정 (오탐 방지 임계값)
            candidates[intent] = len(weak_hits)

    # 후보가 없으면 action intent 없음
    if not candidates:
        return None

    # ── score 우선, 동점이면 ACTION_INTENT_PRIORITY 순서 적용 ──────────
    best_intent = None
    best_score = -1
    best_priority_index = len(ACTION_INTENT_PRIORITY) + 1

    for intent, score in candidates.items():
        try:
            priority_index = ACTION_INTENT_PRIORITY.index(intent)
        except ValueError:
            # ACTION_INTENT_PRIORITY에 없는 intent(확장 케이스)는 가장 낮은 우선순위로
            priority_index = len(ACTION_INTENT_PRIORITY) + 1

        # score가 높거나, 동점일 때 priority 인덱스가 낮은(앞에 있는) intent를 선택
        if score > best_score or (score == best_score and priority_index < best_priority_index):
            best_intent = intent
            best_score = score
            best_priority_index = priority_index

    return best_intent


def apply_action_tool_policy_if_needed(tool_plan, user_query):
    """
    user_query의 action intent에 필요한 근거 수집 Tool이 누락되어 있으면 plan에 추가한다.

    [반환] (보강된 plan dict, rules 리스트)

    [핵심 원칙 반복]
    - expected_tools를 보지 않고 action intent 기반으로만 동작한다.
    - intent는 infer_action_intent()가 user_query 텍스트만으로 추론한다.
    - 추가된 Tool의 argument는 이후 normalize_tool_arguments로 다시 채워진다.
    - step 번호는 _renumber_steps에서 최종 정리되므로 추가 시 step=0으로 설정한다.

    [Tool 추가 policy가 expected_tools 기반이 아닌 이유]
    expected_tools를 참조하면 보정이 "정답 맞추기"가 되어 버린다.
    이 함수는 user_query의 의도에서 드러난 근거 수집 필요성을 채우는 것이며,
    테스트 케이스가 어떤 정답을 기대하는지와 독립적으로 동작해야 한다.

    [호출 시점]
    normalize_plan_for_validation()의 full 모드에서만 호출된다.
    순서: normalize_tool_arguments → deduplicate → apply_action_tool_policy_if_needed
          → normalize_tool_arguments(재보정) → deduplicate(재중복제거) → renumber
    """
    rules = []
    # plan 형태 검증
    if not isinstance(tool_plan, dict) or not isinstance(tool_plan.get("plan"), list):
        return tool_plan, rules

    # action intent 추론 — user_query 텍스트만으로 판단
    intent = infer_action_intent(user_query)
    # intent를 추론할 수 없으면 보강 없이 반환
    if not intent:
        return tool_plan, rules

    # intent에 필요한 Tool 목록 조회 (ACTION_TOOL_POLICY 기준)
    required_tools = ACTION_TOOL_POLICY.get(intent, [])
    # 이미 plan에 있는 Tool 이름 집합 (중복 추가 방지)
    present = {
        item.get("tool_name")
        for item in tool_plan["plan"]
        if isinstance(item, dict)
    }

    new_items = list(tool_plan["plan"])
    for tool_name in required_tools:
        # 이미 plan에 있으면 추가하지 않음
        if tool_name in present:
            continue
        # 새 Tool 항목 추가 — argument는 빈 dict, step은 임시 0
        # (step은 _renumber_steps에서 순서대로 재번호 매김)
        new_items.append({
            "step": 0,  # step은 마지막에 renumber 됨
            "tool_name": tool_name,
            "arguments": {},
            "condition": "always",
            "reason": (
                f"Action intent '{intent}' requires {tool_name} as an evidence-collection "
                "tool; added by action tool policy (not based on expected_tools)."
            ),
        })
        rules.append({
            "rule_id": f"POLICY-{intent}-{tool_name}",
            "rule_type": "action_tool_policy",
            "tool_name": tool_name,
            "before": {},
            "after": {"tool_name": tool_name},
            "reason": f"Action intent '{intent}' inferred from user_query requires {tool_name}.",
        })

    return {"plan": new_items}, rules


def _renumber_steps(tool_plan):
    """plan item의 step을 1부터 순서대로 다시 매긴다.

    [역할]
    action tool policy로 Tool이 추가되거나 deduplicate로 Tool이 제거되면
    step 번호가 불연속이 되거나 중복될 수 있다.
    최종 plan이 확정된 후 step을 1부터 순서대로 재번호 매겨 일관성을 보장한다.

    [호출 시점]
    normalize_plan_for_validation()의 argument-only / full 모드 모두에서
    마지막 단계로 호출된다.

    [변경 시 영향]
    step 번호가 달라지면 downstream validation/report에서 step 참조가 바뀔 수 있다.
    """
    if not isinstance(tool_plan, dict) or not isinstance(tool_plan.get("plan"), list):
        return tool_plan
    for index, item in enumerate(tool_plan["plan"], start=1):
        if isinstance(item, dict):
            item["step"] = index
    return tool_plan


def normalize_plan_for_validation(raw_plan, user_query, normalization_mode="full"):
    """
    validation 전에 plan을 정규화한다. 이 함수가 normalizer 모듈의 진입점이다.

    [반환] (normalized_plan, rules, applied)
    - normalized_plan: 정규화된 plan dict (또는 raw_plan 그대로)
    - rules          : 적용된 normalization rule 목록 (각 보정마다 rule 항목 1개)
    - applied        : bool — 실제로 보정이 1건 이상 수행되었는지 여부

    [normalization_mode 상세]

    ▶ "none" 모드 — 정규화 완전 비활성화
      - raw plan을 deepcopy하여 그대로 반환한다.
      - 강한 차단 요청 여부도 확인하지 않는다.
      - ablation 실험: normalization을 완전히 끄면 validation 통과율이 어떻게 달라지는지 확인.
      - 반환: (deepcopy(raw_plan), [], False)

    ▶ "argument-only" 모드 — argument 보정만, Tool 추가 없음
      - 강한 차단 요청이면 보정 없이 raw plan 반환.
      - action tool policy를 적용하지 않는다(Tool 추가 없음).
      - 순서: normalize_tool_arguments → deduplicate → renumber
      - ablation 실험: Tool 추가 없이 argument 보정만으로 통과율 개선 기여를 측정.

    ▶ "full" 모드 — 전체 정규화 (기본값)
      - 강한 차단 요청이면 보정 없이 raw plan 반환.
      - 순서:
        1) normalize_tool_arguments  (기존 Tool argument 보정)
        2) deduplicate               (중복 제거)
        3) apply_action_tool_policy  (누락 근거 수집 Tool 추가)
        4) normalize_tool_arguments  (새로 추가된 Tool argument 보정)
        5) deduplicate               (재중복 제거)
        6) renumber                  (step 번호 1부터 재번호)
      - action policy 적용 후 argument를 다시 보정하므로
        새로 추가된 Tool의 argument도 올바르게 채워진다.

    [핵심 원칙 반복]
    - normalization은 validation rule을 완화하는 것이 아니다.
      plan을 검증 전에 Tool Contract 형태로 구조 보정하는 것이다.
    - case_id / expected_tools / expected_arguments는 어떤 모드에서도 참조하지 않는다.
    - 강한 차단 요청에서는(none 제외) 어떤 보정도 수행하지 않는다.
      guardrail이 거부해야 할 요청을 normalization이 우회시켜서는 안 된다.

    [호출 시점]
    runner.py의 generate → validate 흐름에서 LLM plan 생성 직후 호출된다.
    반환된 normalized_plan이 validation의 입력이 된다.
    """
    rules = []
    # ── 입력 형태 검증 ──────────────────────────────────────────────────
    # plan 형태가 아니면 어떤 보정도 하지 않고 그대로 반환한다.
    if not isinstance(raw_plan, dict) or not isinstance(raw_plan.get("plan"), list):
        return raw_plan, rules, False

    # ── none 모드: 정규화 완전 비활성화 ───────────────────────────────
    # raw plan을 deepcopy하여 그대로 반환한다. applied=False로 보정 없음을 명시.
    if normalization_mode == "none":
        return copy.deepcopy(raw_plan), rules, False

    # ── 강한 차단 요청 검사 (argument-only / full 공통) ──────────────
    # 강한 차단 요청이면 어떤 보정도 하지 않는다.
    # guardrail 거부 대상 요청을 normalization이 활성화시켜서는 안 된다.
    if is_strong_block_request(user_query):
        return copy.deepcopy(raw_plan), rules, False

    # ── argument-only 모드: argument 보정만, Tool 추가 없음 ──────────
    if normalization_mode == "argument-only":
        plan = copy.deepcopy(raw_plan)
        plan, r1 = normalize_tool_arguments(plan, user_query)
        plan, r2 = deduplicate_tool_plan(plan)
        plan = _renumber_steps(plan)
        rules = r1 + r2
        return plan, rules, len(rules) > 0

    # ── full 모드: 전체 정규화 파이프라인 ───────────────────────────
    if normalization_mode == "full":
        plan = copy.deepcopy(raw_plan)
        # 1단계: 기존 Tool argument 보정
        plan, r1 = normalize_tool_arguments(plan, user_query)
        # 2단계: 중복 제거
        plan, r2 = deduplicate_tool_plan(plan)
        # 3단계: action intent 기반 누락 Tool 추가
        plan, r3 = apply_action_tool_policy_if_needed(plan, user_query)
        # 4단계: 새로 추가된 Tool의 argument 보정 (2회차)
        plan, r4 = normalize_tool_arguments(plan, user_query)
        # 5단계: 재중복 제거 (action policy 후 발생 가능한 중복 처리)
        plan, r5 = deduplicate_tool_plan(plan)
        # 6단계: step 번호 1부터 재번호
        plan = _renumber_steps(plan)
        rules = r1 + r2 + r3 + r4 + r5
        return plan, rules, len(rules) > 0

    # ── 지원하지 않는 mode: 방어적 처리 ─────────────────────────────
    # CLI 인자 choices 검증으로 일반적으로는 도달하지 않지만,
    # 프로그래밍 방식 호출에서 잘못된 mode가 전달되면 명확하게 오류를 낸다.
    raise ValueError(f"Unsupported normalization_mode: {normalization_mode}")


def _record_normalization(state, rules, applied):
    """normalization 결과를 LangGraph state에 누적 기록한다.

    [입력]
    - state  : LangGraph 상태 dict (normalization_rules / normalization_applied 키를 업데이트)
    - rules  : normalize_plan_for_validation()이 반환한 rule 목록
    - applied: normalize_plan_for_validation()이 반환한 applied bool

    [역할]
    LangGraph 그래프에서 normalizer 노드가 실행된 후 state에 결과를 반영할 때 사용한다.
    - normalization_rules: 누적 리스트 — 여러 노드에서 보정 이력을 쌓아야 할 때 extend
    - normalization_applied: 1회라도 보정이 수행되면 True로 고정
      (한 번 True가 된 후 False로 되돌아가지 않는다)

    [호출 시점]
    runner.py 또는 graph 노드에서 normalize_plan_for_validation 호출 직후 사용한다.
    """
    existing = state.get("normalization_rules") or []
    existing.extend(rules)
    state["normalization_rules"] = existing
    if applied:
        state["normalization_applied"] = True
    elif "normalization_applied" not in state:
        state["normalization_applied"] = False
