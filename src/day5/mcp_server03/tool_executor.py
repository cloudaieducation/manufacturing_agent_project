# -*- coding: utf-8 -*-
"""
Day5 mcp_server03 - Tool Executor (검증된 Tool Plan 실행 계층)

[이 모듈의 역할]
Tool Plan 을 받아 normalizer → validation 을 통과시키고,
validation status 가 PASS 일 때만 실제 Tool 을 실행하는 공통 실행 계층입니다.
mcp_server 가 호출하는 핵심 실행 파일입니다.

[Tool Selection 과 Tool Execution 의 분리]
- Selection(어떤 Tool 을 쓸지 결정)은 tool_selector 가 담당합니다.
- Execution(검증된 plan 을 실제 조회로 실행)은 이 모듈이 담당합니다.
- 두 책임을 같은 함수에 섞지 않습니다. 이 모듈은 plan 을 '생성'하지 않습니다.

[실행 게이트 정책]
    normalizer.normalize_plan_for_validation()  ← (1) 먼저 정규화
        ↓
    validation.validate_plan()                  ← (2) 그다음 검증
        ↓
    status 분기:
      PASS         → 실행(executed) 또는 dry_run
      WARNING      → 기본 미실행 → needs_review (dry_run=True 면 dry_run)
      FAIL         → rejected (실행 안 함)
      NEEDS_REVIEW → rejected (실행 안 함)
    * allow_warning_execute=True 일 때만 WARNING 도 실행(기본 False).

[검증을 '구조/계약 검증'으로 쓰는 방법]
validation.validate_plan() 은 원래 평가용(정답 expected_tools 와 비교)이라,
실행 시점에는 정답이 없습니다. 그래서 expected_tools 를 'plan 자신의 Tool 목록'으로
넣어 missing/extra 비교를 중립화하고, 남는 검사(허용 Tool 여부, 금지 Tool, 필수 인자,
스키마, reason/condition 품질)만 작동시킵니다.
→ 결과적으로 PASS=구조·계약 완전 충족, WARNING=품질 경고, FAIL=실행 불가 로 매핑됩니다.

[보안]
- FORBIDDEN_SQL_TOOLS / unknown tool 은 절대 실행하지 않습니다(validation 이 FAIL 처리).
- 각 Tool 결과는 security.sanitize_result() 로 정리해 반환합니다(raw 응답 미반환).
- 예외는 security.safe_error_message() 로 안전하게 변환합니다.

[runner.py 미사용]
Day4 runner.py 를 import 하지 않습니다.
"""
# [import 구성 = 실행 게이트가 거치는 단계 순서]
# 이 모듈은 plan 을 '실행'하기 전에 아래 계층을 순서대로 통과시킨다.
#   - contracts                 : 허용/금지 Tool 판단 기준(방어적 1차 게이트).
#   - normalize_plan_for_validation : 검증 '전' 구조 보정(정규화) 진입점.
#   - validate_plan             : 정규화된 plan 의 구조/계약 검증.
#   - equipment_data            : 설비 조회 Tool 의 데이터 소스(DB 우선 + mock fallback).
#   - manual_search             : search_manual(매뉴얼/RAG 검색) client(설비 조회와 분리).
#   - security                  : 결과/인자/에러를 외부로 내보내기 전 sanitize 하는 경계 계층.
from day5.mcp_server03.contracts import ALLOWED_TOOLS, FORBIDDEN_SQL_TOOLS
from day5.mcp_server03.normalizer import normalize_plan_for_validation
from day5.mcp_server03.validation import validate_plan
from day5.mcp_server03 import equipment_data
from day5.mcp_server03 import manual_search
from day5.mcp_server03 import security


# ---------------------------------------------------------------------------
# tool_name → client 함수 디스패치 규칙
# ---------------------------------------------------------------------------
# [용도] execute_single_tool() 에서 tool_name 에 따라 어떤 client 함수를 호출할지 결정.
# [원칙] 설비 조회 Tool 은 equipment_data, search_manual 은 manual_search 로 연결.
#        각 항목은 (호출 함수, 사용할 argument 이름 목록) 형태.
#        argument 이름 목록은 contracts 의 required/any_of/optional 과 일치한다.
_EQUIPMENT_DISPATCH = {
    "get_equipment_status": ("fetch_equipment_status", ["equipment_id"]),
    "get_recent_alarm_events": (
        "fetch_alarm_events", ["equipment_id", "alarm_code", "limit"],
    ),
    "get_process_status": (
        "fetch_process_status", ["process_name", "line_id", "equipment_id", "limit"],
    ),
    "get_quality_metrics": (
        "fetch_quality_metrics",
        ["metric_name", "equipment_id", "line_id", "date_range", "limit"],
    ),
    "get_maintenance_history": (
        "fetch_maintenance_history", ["equipment_id", "date_range", "part_replaced"],
    ),
    "get_equipment_overview": ("fetch_equipment_overview", ["equipment_id"]),
}


def _plan_tool_names(tool_plan):
    """tool_plan 의 plan 항목에서 tool_name 목록을 추출하는 내부 헬퍼.

    [반환] tool_name 이 비어 있지 않은 항목만 순서대로 담은 list[str].
           구조가 맞지 않으면 빈 list.
    [용도] validate_plan 에 expected_tools 로 넘겨 missing/extra 비교를 중립화한다.
    """
    if not isinstance(tool_plan, dict):
        return []
    items = tool_plan.get("plan")
    if not isinstance(items, list):
        return []
    names = []
    for item in items:
        if isinstance(item, dict) and item.get("tool_name"):
            names.append(item.get("tool_name"))
    return names


def build_single_tool_plan(tool_name, arguments):
    """단일 Tool 호출을 표준 Tool Plan 형태로 감싼다.

    [입력]
        tool_name: 호출할 Tool 이름.
        arguments: 호출 인자 dict.
    [반환]
        {"plan": [{"step":1, "tool_name":..., "arguments":..., "condition":"always",
                   "reason": "<10자 이상 설명>"}]}

    [왜 reason/condition 을 채우는가]
        validation 의 품질 검사(weak_reason/missing_condition, WARNING)를 통과시켜,
        정상적인 단일 Tool 호출이 PASS 로 실행될 수 있게 한다.

    [용도]
        mcp_server.call_mcp_tool() 이 개별 Tool 을 실행할 때, execute_tool_plan 의
        입력 형태로 변환하기 위해 사용한다.
    """
    return {
        "plan": [
            {
                "step": 1,
                "tool_name": tool_name,
                "arguments": dict(arguments or {}),
                "condition": "always",
                "reason": f"{tool_name} 단일 Tool 을 직접 실행하기 위한 요청입니다.",
            }
        ]
    }


def execute_single_tool(tool_name, arguments, dry_run=False):
    """단일 Tool 을 실제로 실행(또는 dry_run)하고 안전한 결과 dict 를 반환한다.

    [입력]
        tool_name: 실행할 Tool 이름.
        arguments: 실행 인자 dict.
        dry_run  : True 면 실제 client 호출 없이 실행 계획만 반환한다.
    [반환]
        {
          "step": <설정 시 채워짐, 여기서는 1>,
          "tool_name": ...,
          "status": "executed" | "dry_run" | "rejected" | "error",
          "result": <sanitize 된 결과 dict 또는 None>,
          "message": <안내 문자열>
        }

    [방어 순서]
        1) 금지 Tool / 미허용 Tool → rejected (절대 실행 안 함)
        2) dry_run → 실행하지 않고 안전 인자 요약만 반환
        3) search_manual → manual_search, 그 외 → equipment_data 디스패치
        4) 결과는 security.sanitize_result() 로 정리
        5) 예외는 security.safe_error_message() 로 변환해 status="error"

    [보안]
        - raw 응답 전체를 그대로 반환하지 않는다(sanitize_result 경유).
        - 예외 메시지에 endpoint/키 등이 섞여도 마스킹 후 반환한다.
    """
    args = dict(arguments or {})

    # 1) 금지/미허용 Tool 차단 (방어적 이중 검사: validation 외에 실행부에서도 막는다)
    if tool_name in FORBIDDEN_SQL_TOOLS:
        return {
            "tool_name": tool_name,
            "status": "rejected",
            "result": None,
            "message": "금지된 Text-to-SQL/SQL 관련 Tool 이므로 실행하지 않습니다.",
        }
    if tool_name not in ALLOWED_TOOLS:
        return {
            "tool_name": tool_name,
            "status": "rejected",
            "result": None,
            "message": "허용 목록에 없는 Tool 이므로 실행하지 않습니다.",
        }

    # 2) dry_run: 실제 호출 없이 인자 요약만 반환(민감정보는 마스킹)
    if dry_run:
        return {
            "tool_name": tool_name,
            "status": "dry_run",
            "result": None,
            "message": "dry_run 모드: 실제 조회를 수행하지 않았습니다.",
            "arguments_preview": security.sanitize_arguments(args),
        }

    # 3) 실제 실행 (예외는 안전 메시지로 변환)
    try:
        if tool_name == "search_manual":
            # 매뉴얼 검색은 manual_search 로 연결한다(설비 조회와 분리).
            payload = manual_search.search_manual(
                query=args.get("query"),
                alarm_code=args.get("alarm_code"),
                equipment_type=args.get("equipment_type"),
            )
        else:
            # 설비 조회 Tool: 디스패치 표에서 함수명과 사용할 argument 목록을 가져온다.
            func_name, arg_names = _EQUIPMENT_DISPATCH[tool_name]
            func = getattr(equipment_data, func_name)
            # contracts 기준 argument 만 추려서 전달(정의 외 인자는 넘기지 않는다).
            call_kwargs = {k: args.get(k) for k in arg_names if k in args}
            payload = func(**call_kwargs)

        # 4) 결과를 tool_name 별 허용 필드만 남겨 안전하게 반환
        safe_result = security.sanitize_result(tool_name, payload)
        return {
            "tool_name": tool_name,
            "status": "executed",
            "result": safe_result,
            "message": "정상 실행되었습니다(mock 또는 real 안내).",
        }
    except Exception as error:
        # 5) 예외는 민감정보 제거 후 안전 메시지만 반환
        return {
            "tool_name": tool_name,
            "status": "error",
            "result": None,
            "message": security.safe_error_message(error),
        }


def execute_tool_plan(tool_plan, user_query="", normalization_mode="full",
                      allow_warning_execute=False, dry_run=False):
    """Tool Plan 을 정규화·검증한 뒤, PASS 일 때만 순서대로 실행한다.

    [입력]
        tool_plan            : {"plan": [...]} 형태의 Tool Plan.
        user_query           : 정규화 entity 추출에 사용(선택).
        normalization_mode   : "none" | "argument-only" | "full"(기본).
        allow_warning_execute: True 면 WARNING 도 실행(기본 False).
        dry_run              : True 면 실제 client 호출 없이 실행 계획만 반환.
    [반환]
        {
          "status": "executed" | "dry_run" | "needs_review" | "rejected" | "error",
          "validation_status": "PASS" | "WARNING" | "FAIL" | "NEEDS_REVIEW",
          "executed_count": int,
          "results": [ {step, tool_name, status, result}, ... ],
          "issues": [ ...validation issues... ],
          "message": str
        }

    [실행 순서]
        1) normalizer.normalize_plan_for_validation() 로 정규화(검증 전 구조 보정)
        2) validate_plan() 로 검증
           - expected_tools = 정규화된 plan 자신의 Tool 목록(구조/계약 검증으로 사용)
           - evaluable=True (PASS 가 나올 수 있도록), expected_arguments/guardrail=None
        3) validation_status 분기:
           - 빈 plan      → rejected (실행할 Tool 없음)
           - FAIL/NEEDS_REVIEW → rejected
           - WARNING      → allow_warning_execute=False 면 needs_review(미실행)
           - PASS(또는 허용된 WARNING) → 각 step 을 execute_single_tool 로 실행

    [예외 처리]
        정규화/검증 중 예외가 나면 status="error" 로 안전 메시지만 반환한다.
    """
    # ── (0) 정규화/검증은 예외로 흐름이 끊기지 않게 감싼다 ──
    try:
        # (1) 정규화: 검증 '전에' 먼저 수행한다(normalizer → validation 순서 보장).
        normalized, _rules, _applied = normalize_plan_for_validation(
            tool_plan, user_query, normalization_mode=normalization_mode
        )

        # (2) 검증: expected_tools 를 plan 자신의 Tool 목록으로 넣어
        #     missing/extra 비교를 중립화하고 구조/계약 검증만 작동시킨다.
        plan_tools = _plan_tool_names(normalized)
        validation_result = validate_plan(
            normalized,
            plan_tools,        # expected_tools = 자기 자신(평가가 아닌 구조 검증 목적)
            None,              # expected_arguments 없음(값 비교 비활성)
            None,              # expected_guardrail 미사용
            True,              # evaluable=True → 구조 완전 충족 시 PASS 가능
        )
    except Exception as error:
        return {
            "status": "error",
            "validation_status": "FAIL",
            "executed_count": 0,
            "results": [],
            "issues": [],
            "message": security.safe_error_message(error),
        }

    status = validation_result.get("status", "FAIL")
    issues = validation_result.get("issues", [])
    plan_items = normalized.get("plan", []) if isinstance(normalized, dict) else []

    # ── (3a) 빈 plan: 실행할 Tool 이 없음 → rejected ──
    # (개인정보/과도조회 차단 등으로 plan 이 비는 경우도 여기로 들어온다.)
    if not plan_items:
        return {
            "status": "rejected",
            "validation_status": status,
            "executed_count": 0,
            "results": [],
            "issues": issues,
            "message": "실행할 Tool 이 없습니다(빈 plan). 차단되었거나 선택된 Tool 이 없습니다.",
        }

    # ── (3b) FAIL / NEEDS_REVIEW → rejected (실행 안 함) ──
    if status in ("FAIL", "NEEDS_REVIEW"):
        return {
            "status": "rejected",
            "validation_status": status,
            "executed_count": 0,
            "results": [],
            "issues": issues,
            "message": "검증 결과가 FAIL/NEEDS_REVIEW 이므로 실행하지 않습니다.",
        }

    # ── (3c) WARNING → 기본 미실행(needs_review). 옵션 시에만 실행 허용 ──
    if status == "WARNING" and not allow_warning_execute:
        return {
            "status": "needs_review",
            "validation_status": status,
            "executed_count": 0,
            "results": [],
            "issues": issues,
            "message": "검증 결과가 WARNING 입니다. 기본 정책상 실행하지 않고 검토가 필요합니다.",
        }

    # ── (3d) PASS(또는 허용된 WARNING): step 순서대로 실행 ──
    results = []
    executed_count = 0
    for item in plan_items:
        if not isinstance(item, dict):
            continue
        tool_name = item.get("tool_name")
        arguments = item.get("arguments") or {}
        step = item.get("step")

        single = execute_single_tool(tool_name, arguments, dry_run=dry_run)
        single["step"] = step
        results.append(single)
        if single.get("status") in ("executed", "dry_run"):
            executed_count += 1

    # 전체 응답 status: dry_run 이면 dry_run, 아니면 executed
    overall = "dry_run" if dry_run else "executed"
    return {
        "status": overall,
        "validation_status": status,
        "executed_count": executed_count,
        "results": results,
        "issues": issues,
        "message": "검증을 통과하여 Tool Plan 을 실행했습니다."
                   if not dry_run else "dry_run 모드로 실행 계획만 확인했습니다.",
    }
