# -*- coding: utf-8 -*-
"""
Day4 Tool Selection Fallback Planner

LLM 호출 실패, LLM 응답 파싱 실패, llm_client 사용 불가 상황에서
강의/실습 흐름을 유지하기 위해 사용하는 rule 기반 fallback plan 생성 모듈입니다.

【모듈의 위치】
  전체 파이프라인: 사용자 질문 → prompt_builder → runner.generate_tool_plan
                   → (LLM 성공 시) normalizer → validation → repair → finalize
                   → (LLM 실패 시) 이 모듈(fallback.py)이 대신 Tool Plan 생성
                   → results → report → output_writer

  runner.generate_tool_plan 이 LLM 호출을 시도한 뒤:
    - fallback_mode == "strict" 이면  → build_llm_error_plan() 을 호출
    - fallback_mode == "rule"   이면  → build_fallback_plan()   을 호출
  두 경로 모두 반환값을 normalizer에 넘겨 이후 파이프라인이 동일하게 진행된다.

중요:
- 이 fallback 결과는 순수 LLM 성능이 아닙니다.
  반드시 runner의 fallback_used / generation_source / repair_generation_source 로
  구분해서 해석해야 합니다.
- case_id / expected_tools / expected_arguments 를 참조하지 않습니다.
- 오직 user_query 와 일반 keyword rule 만 사용합니다.
- 실제 운영 환경에서는 더 정교한 fallback policy / 에러 처리 정책으로 대체될 수 있습니다.
"""
import re


# ===========================================================================
# fallback rule marker 상수 (가독성 목적, 의미/동작은 기존과 동일)
# ===========================================================================
# 민감정보 / 과도한 전체 조회로 판단되면 빈 plan을 반환한다.
#
# ─── 상수 그룹 설계 원칙 ──────────────────────────────────────────────────
# 아래 모든 상수는 "LLM이 판단한 결과"가 아니라 단순 문자열 포함 여부로
# tool을 선택하는 "rule marker" 입니다.
# LLM 성능 지표(precision / recall 등)와 무관하며,
# 이 규칙으로 생성된 plan은 반드시 generation_source == "rule_fallback" 으로
# 기록되어 LLM 생성 plan과 명확히 구분돼야 합니다.
# 각 그룹은 build_fallback_plan() 내부의 wants_* 불리언 변수와 1:1로 대응합니다.
# ──────────────────────────────────────────────────────────────────────────

# ─── 보안/가드레일 그룹 ────────────────────────────────────────────────────
# SENSITIVE_MARKERS: 개인정보·사번 등 민감 정보를 요청하는 키워드.
#   용도: build_fallback_plan 진입 직후 가드레일 검사에서 사용.
#   매칭 즉시 plan=[] 인 빈 plan을 반환하고 이후 tool 추가 로직은 실행하지 않는다.
#   이유: fallback 경로에서도 민감정보 노출을 방지해야 하며,
#         guardrail.py 의 사전 차단 여부와 무관하게 이중으로 방어한다.
SENSITIVE_MARKERS = [
    "연락처",
    "휴대폰",
    "전화번호",
    "개인정보",
    "사번",
    "주민번호",
    "이메일",
    "담당자",
]

# OVER_QUERY_MARKERS: DB/API 전체 조회를 유발할 수 있는 과도한 범위 요청 키워드.
#   용도: SENSITIVE_MARKERS와 동일한 가드레일 검사 단계에서 OR 조건으로 함께 판단.
#   매칭 즉시 plan=[] 반환. 이유: 교육 환경의 DB 부하 방지 및
#   실무에서도 무제한 조회는 별도 권한 처리가 필요하다는 점을 학습자에게 전달.
OVER_QUERY_MARKERS = [
    "전체 데이터",
    "모든 데이터",
    "제한 없이",
    "무제한",
    "전부 조회",
    "전체 조회",
]

# ─── 도메인 의도 판단 그룹 ─────────────────────────────────────────────────
# 아래 6개 그룹은 build_fallback_plan 내부에서 wants_* 불리언 플래그를 계산하는 데 쓰인다.
# 각 플래그가 True 이면 대응하는 tool 이 plan에 추가된다.
# 우선순위(더하기 순서)는 코드 내 if 분기 순서와 동일하다.

# ALARM_MARKERS: 알람/이벤트 조회 의도를 나타내는 키워드.
#   → 매칭 시 get_recent_alarm_events 추가 (alarm_code 있으면 인수에 포함).
ALARM_MARKERS = ["알람", "alarm"]

# MANUAL_MARKERS: 조치 절차·문서·근거 조회 의도를 나타내는 키워드.
#   → 매칭 시 search_manual 추가 (alarm_code 있으면 인수에 포함).
MANUAL_MARKERS = ["매뉴얼", "조치", "절차", "원인", "문서", "근거"]

# MAINTENANCE_MARKERS: 설비 정비·부품 교체 이력 조회 의도.
#   → 매칭 시 get_maintenance_history 추가.
MAINTENANCE_MARKERS = ["정비", "보전", "부품", "교체"]

# QUALITY_MARKERS: 품질·수율·검사 관련 데이터 조회 의도.
#   → 매칭 시 get_quality_metrics 추가 (equipment_id 있으면 인수에 포함).
QUALITY_MARKERS = ["품질", "불량", "수율", "검사"]

# PROCESS_MARKERS: 공정·라인·압력·온도·진공 등 공정 파라미터 조회 의도.
#   → 매칭 시 get_process_status 추가 (line_id는 추출 불가 시 None).
PROCESS_MARKERS = ["공정", "라인", "압력", "온도", "진공"]

# STATUS_MARKERS / OVERVIEW_MARKERS: 설비 상태·개요 조회 의도.
#   → 다른 tool이 하나도 추가되지 않은 경우에만 "최후 보루"로 추가된다.
#      이는 기본 조회를 뜻하며, 더 구체적인 의도가 이미 plan에 있으면 중복을 피한다.
STATUS_MARKERS = ["상태", "정상"]
OVERVIEW_MARKERS = ["개요", "요약", "기본 정보"]


def build_llm_error_plan(error_code, message=""):
    """strict fallback mode 전용 LLM 실패 plan.

    --fallback-mode strict 에서 LLM 실패 시 rule fallback을 사용하지 않고,
    실패 상태를 Tool Plan 형태(plan=[])로 남깁니다. validate_plan()이 기존 구조대로
    llm_error_code를 감지해 json_parse_error로 처리할 수 있게 합니다.

    【호출 시점】
      runner.generate_tool_plan 에서 LLM 호출이 실패했고
      fallback_mode == "strict" 일 때 호출된다.
      strict 모드에서는 rule 기반 fallback을 "사용하지 않는다"는 정책을 시행하기 위해
      build_fallback_plan() 대신 이 함수를 호출한다.
      결과는 normalizer → validate_plan → repair 로 전달되며,
      validate_plan이 llm_error_code 키를 감지해 json_parse_error 로 처리한다.

    【반환값 구조】
      {
        "llm_error_code":    str,  # 오류 유형 식별자
        "llm_error_message": str,  # 안전한 짧은 설명 문자열
        "plan":              [],   # 항상 빈 리스트 — tool 없음
      }

    중요:
    - 항상 dict를 반환하며 항상 plan: [] 을 포함합니다.
    - error_code가 None/빈 값이면 "unknown_llm_error"로 정규화합니다.
    - message는 짧고 안전한 문자열만 사용합니다. exception 전체 문자열,
      API Key, token, 환경변수 값은 넣지 않습니다.
    - case_id / expected_tools / expected_arguments를 참조하지 않습니다.

    Args:
        error_code (str | None): LLM 오류 유형 코드. None 이면 "unknown_llm_error" 사용.
        message (str): 사람이 읽을 수 있는 짧은 오류 설명. 민감 정보 금지.

    Returns:
        dict: llm_error_code, llm_error_message, plan(=[]) 을 포함하는 plan dict.
    """
    # None/빈 값이 넘어오면 추적 가능한 기본 코드로 정규화한다.
    safe_code = error_code or "unknown_llm_error"
    # 메시지도 None/빈 값 방어: 호출자가 message를 생략할 수 있으므로 기본값 사용.
    safe_message = message or "LLM 실패, strict mode로 rule fallback 미사용"
    # plan=[] 로 빈 plan을 명시적으로 기록한다.
    # downstream(validate_plan)이 llm_error_code 키를 감지해 오류 경로로 분기한다.
    return {
        "llm_error_code": safe_code,
        "llm_error_message": safe_message,
        "plan": [],
    }


def extract_ids(user_query):
    """사용자 질문에서 equipment_id, alarm_code를 추출합니다 (fallback plan용).

    【역할】
      fallback 경로에서는 LLM이 없으므로 정규식으로 설비 ID와 알람 코드를
      직접 추출해 tool arguments 에 채워넣는다.
      LLM이 NER(Named Entity Recognition)을 수행하던 역할을 단순 패턴으로 대체한다.
      이 함수도 rule 기반 처리이므로 LLM 성능과 무관하다.

    【호출 시점】
      build_fallback_plan() 의 초반부에서 한 번 호출된다.
      추출된 값은 get_recent_alarm_events, get_maintenance_history 등
      특정 설비/알람 인수가 필요한 tool의 arguments 에 직접 삽입된다.

    【주의】
      - 추출하지 못하면 None 을 반환한다. 호출자(build_fallback_plan)는
        None 을 그대로 arguments 에 넣거나 키 자체를 생략하는 방식으로 처리한다.
      - 교육용 가상 ID 규칙(EQP-*, ENCAP-*, SPT-*, CVD-* / ALM-*)에 맞춰
        패턴이 설계되어 있다. 실제 운영 규칙과 다를 수 있다.

    【정규식 패턴 설명】
      equipment_pattern:
        (?<![A-Z0-9])  — 앞에 영숫자가 없어야 함 (부분 매칭 방지)
        (?:EQP|ENCAP|SPT|CVD)  — 허용된 설비 접두어
        -[A-Z]{2,10}-  — 중간 영문 코드 (2~10자)
        \\d{1,4}        — 뒤 숫자 (1~4자리)
        (?![A-Z0-9])   — 뒤에 영숫자가 없어야 함

      alarm_pattern:
        ALM-[A-Z]{2,12}-[A-Z0-9]{1,12}
        동일한 lookaround 로 경계 보호.

    Args:
        user_query (str | None): 원본 사용자 질문 문자열.

    Returns:
        tuple[str | None, str | None]: (equipment_id, alarm_code).
            각각 매칭된 첫 번째 값 또는 None.
    """
    # 대소문자 혼용 쿼리에 대비해 전체를 대문자로 변환한 뒤 정규식을 적용한다.
    text = (user_query or "").upper()

    # 교육용 가상 설비 ID 패턴: EQP-XX-0000 형식을 허용하는 패턴.
    # lookahead/lookbehind 로 더 긴 문자열의 일부가 잘못 매칭되는 것을 방지.
    equipment_pattern = r"(?<![A-Z0-9])(?:EQP|ENCAP|SPT|CVD)-[A-Z]{2,10}-\d{1,4}(?![A-Z0-9])"

    # 교육용 가상 알람 코드 패턴: ALM-XX-XXXXX 형식.
    alarm_pattern = r"(?<![A-Z0-9])ALM-[A-Z]{2,12}-[A-Z0-9]{1,12}(?![A-Z0-9])"

    # 각 패턴의 첫 번째 매칭만 사용한다. 복수 매칭은 현재 fallback 정책상 무시.
    equipment_match = re.search(equipment_pattern, text)
    alarm_match = re.search(alarm_pattern, text)

    equipment_id = equipment_match.group(0) if equipment_match else None
    alarm_code = alarm_match.group(0) if alarm_match else None
    return equipment_id, alarm_code


def build_fallback_plan(user_query):
    """
    LLM 사용이 불가능할 때 쓰는 단순 rule 기반 fallback plan.

    강의 안정성용이며, 순수 LLM 성능과 반드시 구분해 기록한다.

    【역할】
      runner.generate_tool_plan 에서 LLM 호출이 실패했고
      fallback_mode == "rule" 일 때 호출된다.
      user_query 에 포함된 키워드를 rule marker 상수(ALARM_MARKERS 등)와 대조해
      tool plan 을 구성하고 반환한다.
      - case_id, expected_tools, expected_arguments 는 일절 참조하지 않는다.
        이 함수의 입력은 오직 user_query 하나이다.
      - 반환된 plan dict 는 runner 에서 fallback_used=True 로 기록된 뒤
        normalizer → validate_plan → repair → finalize 로 전달된다.

    【처리 흐름 요약】
      1. 보안 가드레일: 민감정보 / 과도조회 키워드 감지 → 즉시 빈 plan 반환
      2. ID 추출: extract_ids() 로 equipment_id, alarm_code 를 정규식으로 추출
      3. 의도 판단: wants_* 불리언 플래그를 키워드 매칭으로 계산
      4. Tool 추가: 각 플래그에 따라 add() 헬퍼로 plan 에 tool step 추가
      5. 결과 반환: {"plan": [...]} 형태로 반환

    【주의】
      - 이 함수는 LLM 없이 동작하므로 LLM 성능 평가 대상이 아니다.
        generation_source 가 "rule_fallback" 으로 기록되어야 하며,
        day4 품질 게이트(quality_gate_runner.py)도 이를 구분해 평가한다.
      - STATUS_MARKERS / OVERVIEW_MARKERS 는 plan 이 비어 있을 때만 추가된다.
        다른 더 구체적인 tool 이 이미 추가됐다면 기본 상태/개요 조회는 생략한다.

    Args:
        user_query (str | None): 원본 사용자 질문 문자열.

    Returns:
        dict: {"plan": list[dict]} 형태. 각 step dict 는
              step, tool_name, arguments, condition, reason 키를 포함한다.
              키워드 매칭이 없거나 가드레일에 걸리면 plan=[] 의 빈 plan 반환.
    """
    # None 방어: user_query 가 None 으로 넘어올 수 있으므로 빈 문자열로 치환.
    text = (user_query or "")
    lower = text.lower()

    # step 1 — ID 추출
    # equipment_id, alarm_code 는 이후 여러 tool 의 arguments 에 공통으로 사용된다.
    equipment_id, alarm_code = extract_ids(user_query)

    # ── step 2: 보안 가드레일 ─────────────────────────────────────────────
    # 민감정보(SENSITIVE_MARKERS) 또는 과도한 전체 조회(OVER_QUERY_MARKERS) 키워드가
    # user_query 에 포함되어 있으면 tool 을 아무것도 추가하지 않고 빈 plan 을 반환한다.
    # 이유:
    #   - 민감정보: 개인정보 보호. fallback 경로에서도 민감 데이터 노출 방지.
    #   - 과도조회: DB 전체 dump 등 범위 무제한 조회는 별도 권한/정책이 필요하며,
    #     교육 환경에서 DB 부하 방지 목적으로도 차단한다.
    if any(m in text for m in SENSITIVE_MARKERS) or any(m in text for m in OVER_QUERY_MARKERS):
        # 빈 plan 반환: tool step 없음 → downstream 에서 "선택된 tool 없음"으로 처리
        return {"plan": []}

    # ── step 3: plan 컨테이너 및 헬퍼 초기화 ────────────────────────────
    plan = []
    step = 1

    def add(tool_name, arguments, reason):
        """plan 리스트에 tool step 을 순서대로 추가하는 내부 헬퍼.

        step 번호는 nonlocal 로 공유된 카운터를 통해 자동 증가한다.
        condition 은 항상 "always" 로 고정한다 (rule fallback 은 조건 분기 없음).

        Args:
            tool_name (str): 추가할 tool 의 이름.
            arguments (dict): 해당 tool 에 전달할 인수 dict.
            reason (str): 이 tool 을 선택한 이유 (한국어 설명).
        """
        nonlocal step
        plan.append({
            "step": step,
            "tool_name": tool_name,
            "arguments": arguments,
            "condition": "always",
            "reason": reason,
        })
        step += 1

    # ── step 4: 도메인 의도 판단 ─────────────────────────────────────────
    # 각 marker 그룹과 text 를 비교해 wants_* 불리언 플래그를 계산한다.
    # 이 판단은 단순 문자열 포함 여부(in 연산자)이며 LLM 의미 이해와 무관하다.
    wants_alarm = any(k in text for k in ALARM_MARKERS)
    wants_manual = any(k in text for k in MANUAL_MARKERS)
    wants_maint = any(k in text for k in MAINTENANCE_MARKERS)
    wants_quality = any(k in text for k in QUALITY_MARKERS)
    wants_process = any(k in text for k in PROCESS_MARKERS)
    wants_status = any(k in text for k in STATUS_MARKERS)
    wants_overview = any(k in text for k in OVERVIEW_MARKERS)

    # ── step 5: 의도별 tool 추가 ─────────────────────────────────────────
    # 각 wants_* 플래그가 True 이면 대응하는 tool 을 plan 에 추가한다.
    # 추가 순서(알람 → 매뉴얼 → 정비 → 품질 → 공정)가 step 번호의 순서가 된다.

    # 알람 조회: ALARM_MARKERS 매칭 시 최근 알람 이력 tool 추가.
    # alarm_code 가 추출됐으면 인수에 포함해 더 좁은 범위로 조회한다.
    if wants_alarm:
        args = {"equipment_id": equipment_id}
        if alarm_code:
            # 알람 코드가 있으면 해당 코드로 필터링해 조회 범위를 좁힌다.
            args["alarm_code"] = alarm_code
        add("get_recent_alarm_events", args, "최근 알람 이력을 확인하기 위해 선택했습니다.")

    # 매뉴얼/절차 조회: MANUAL_MARKERS 매칭 시 벡터 검색 기반 search_manual 추가.
    # user_query 전체를 검색 쿼리로 사용하고, alarm_code 가 있으면 추가 필터로 넣는다.
    if wants_manual:
        args = {"query": user_query}
        if alarm_code:
            # 알람 코드로 매뉴얼 검색 범위를 좁혀 관련도 높은 문서를 우선한다.
            args["alarm_code"] = alarm_code
        add("search_manual", args, "관련 매뉴얼과 조치 절차 근거를 확인하기 위해 선택했습니다.")

    # 정비 이력 조회: MAINTENANCE_MARKERS 매칭 시 설비 정비 이력 tool 추가.
    if wants_maint:
        add("get_maintenance_history", {"equipment_id": equipment_id},
            "정비 이력을 확인하기 위해 선택했습니다.")

    # 품질 지표 조회: QUALITY_MARKERS 매칭 시 품질 메트릭 tool 추가.
    # equipment_id 가 없으면 빈 dict 로 전달해 전체 라인 집계를 요청한다.
    if wants_quality:
        args = {}
        if equipment_id:
            # 설비 ID 가 있으면 해당 설비의 품질 지표만 조회한다.
            args["equipment_id"] = equipment_id
        add("get_quality_metrics", args, "품질 지표를 확인하기 위해 선택했습니다.")

    # 공정/라인 상태 조회: PROCESS_MARKERS 매칭 시 공정 상태 tool 추가.
    # line_id 는 정규식으로 추출하지 않으므로 None 으로 고정해 전체 라인을 조회한다.
    if wants_process:
        add("get_process_status", {"line_id": None},
            "공정/라인 상태를 확인하기 위해 선택했습니다.")

    # ── 최후 보루 tool: 위 플래그가 하나도 매칭되지 않은 경우 ─────────────
    # OVERVIEW_MARKERS / STATUS_MARKERS 는 plan 이 비어 있을 때만 추가된다.
    # 이미 더 구체적인 tool 이 있다면 기본 개요/상태 조회는 중복이므로 생략한다.

    # 개요 조회: OVERVIEW_MARKERS 매칭 + 다른 tool 없음 → 설비 개요 tool 추가.
    if wants_overview and not plan:
        add("get_equipment_overview", {"equipment_id": equipment_id},
            "설비 개요를 확인하기 위해 선택했습니다.")

    # 상태 조회: STATUS_MARKERS 매칭 + 다른 tool 없음 → 설비 상태 tool 추가.
    if wants_status and not plan:
        add("get_equipment_status", {"equipment_id": equipment_id},
            "설비 상태를 확인하기 위해 선택했습니다.")

    # 최종 plan dict 반환. plan=[] 이면 어떤 의도도 감지하지 못한 것.
    return {"plan": plan}
