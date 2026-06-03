# -*- coding: utf-8 -*-
"""
Day4 Tool Selection Validation
================================
Tool Plan을 rule 기반으로 검증해 PASS / WARNING / FAIL status와 issue 목록을 만드는 모듈입니다.
판정 기준·issue type·issue_counts 구조는 기존 runner와 동일하게 유지합니다.

-----------------------------------------------------------------------
전체 파이프라인에서 이 모듈의 위치
  normalizer  →  [validation]  →  repair  →  finalize  →  results  →  report  →  output_writer

  * runner는 각 단계를 순서대로 호출하는 "실행 흐름"을 담당합니다.
  * 이 모듈(validation)은 runner로부터 전달받은 Tool Plan의 구조적 올바름과
    Tool Contract 일치 여부만 판정합니다.
  * runner를 import하지 않기 때문에 순환 import(circular import)가 발생하지 않습니다.

수업 안내
  generate → validate → repair → finalize 네 단계 중 "validate" 단계를 설명할 때
  이 파일을 함께 열어 두면 판정 흐름을 코드 레벨에서 바로 확인할 수 있습니다.
  특히 _finalize_validation() 의 FAIL/WARNING/PASS 결정 로직과
  _make_empty_issue_counts()의 issue 유형 목록을 수업 중 대조하면 이해에 도움이 됩니다.

-----------------------------------------------------------------------
의존: contracts(ALLOWED_TOOLS, FORBIDDEN_SQL_TOOLS, ALLOWED_PLAN_ITEM_FIELDS,
                MIN_REASON_LENGTH, TOOL_CONTRACTS).
runner / normalizer / fallback / results / report를 import하지 않습니다(순환 import 방지).
"""
from day5.mcp_server02.contracts import (
    ALLOWED_TOOLS,
    FORBIDDEN_SQL_TOOLS,
    ALLOWED_PLAN_ITEM_FIELDS,
    MIN_REASON_LENGTH,
    TOOL_CONTRACTS,
)


def _make_empty_issue_counts():
    """
    모든 issue 유형의 카운터를 0으로 초기화한 dict를 반환합니다.

    반환 dict의 각 key 의미
    ─────────────────────────────────────────────────────────────
    missing_tool         : 정답(expected_tools)에 있어야 할 Tool이 plan에 없는 경우.
                           예) expected=['search_logs'] 인데 plan에 'search_logs'가 없을 때.
                           → FAIL 유형.

    extra_tool           : plan에 포함됐지만 expected_tools에 없는 Tool.
                           LLM이 불필요한 Tool을 추가로 선택한 경우.
                           forbidden/unknown은 별도 계산되므로 여기서는 ALLOWED_TOOLS 한정.
                           → FAIL 유형.

    missing_argument     : Tool Contract에서 required로 지정된 argument가
                           plan item의 arguments dict에 없거나 값이 빈 문자열/None인 경우.
                           → FAIL 유형.

    wrong_argument_name  : Tool Contract에 정의되지 않은 argument key를 LLM이 생성한 경우.
                           오타나 환각(hallucination)으로 알 수 없는 key를 넣은 상황.
                           missing_argument와의 차이: missing_argument는 "있어야 할 key가 없다",
                           wrong_argument_name은 "있어서는 안 되는 key가 있다".
                           → FAIL 유형.

    missing_condition    : plan item의 'condition' 필드가 비어 있거나 공백만 있는 경우.
                           condition은 "해당 step을 실행해야 하는 선행 조건"이므로
                           없으면 실행 시점 판단이 불가능. → WARNING 유형.

    weak_reason          : plan item의 'reason' 필드가 없거나 MIN_REASON_LENGTH(10자) 미만인 경우.
                           reason은 Tool을 선택한 근거이며, 너무 짧으면 설명력이 부족.
                           구조적 오류는 아니므로 실행 자체에는 영향을 주지 않아 WARNING에 그침.
                           → WARNING 유형.

    json_parse_error     : LLM 응답이 올바른 dict로 파싱되지 않았거나
                           llm_error_code 필드가 존재하는 경우.
                           schema_error와의 차이: json_parse_error는 JSON 자체가 깨진 상황이고,
                           schema_error는 JSON은 정상이지만 필드 구조가 계약과 다른 상황.
                           → FAIL 유형.

    tool_contract_mismatch : expected_arguments로 전달된 정답 값과
                             plan item의 argument 실제 값이 다른 경우.
                             Tool 이름은 맞지만 argument 값이 틀린 "부분 오답" 상황.
                             → FAIL 유형.

    forbidden_tool       : FORBIDDEN_SQL_TOOLS에 등재된 Text-to-SQL/SQL 관련 Tool을 선택한 경우.
                           이 Tool들은 Day4 과정에서 보안·설계 이유로 명시적으로 금지됨.
                           unknown_tool과의 차이: forbidden_tool은 "존재는 알지만 사용 금지",
                           unknown_tool은 "계약 어디에도 없는 이름".
                           → FAIL 유형.

    unknown_tool         : ALLOWED_TOOLS에도, FORBIDDEN_SQL_TOOLS에도 없는 Tool 이름.
                           LLM 환각이나 오타로 존재하지 않는 Tool을 선택한 경우.
                           → FAIL 유형.

    schema_error         : top-level 'plan' key 누락, plan이 list가 아님,
                           plan item이 dict가 아님, 필수 필드 누락, 허용되지 않은 추가 필드 등
                           Tool Plan JSON 구조 자체가 계약 스키마를 위반한 경우.
                           json_parse_error와의 차이: schema_error는 파싱은 됐지만
                           구조(스키마)가 잘못된 경우. → FAIL 유형.

    empty_plan_error     : expected_tools가 비어 있지 않은데 plan 자체가 비어 있는 경우.
                           LLM이 아무 Tool도 선택하지 않아 응답이 무의미한 상황.
                           → FAIL 유형.
    ─────────────────────────────────────────────────────────────
    주의: 이 dict 구조는 results.py / report.py / quality_gate_runner.py의
    집계 로직과 직접 연결됩니다. key를 추가·삭제하면 해당 모듈도 함께 수정해야 합니다.
    """
    return {
        "missing_tool": 0,         # 정답 Tool이 plan에 없음 → FAIL
        "extra_tool": 0,           # plan에 불필요한 Tool이 있음 → FAIL
        "missing_argument": 0,     # required argument가 누락됨 → FAIL
        "wrong_argument_name": 0,  # 계약에 없는 argument key 사용 → FAIL
        "missing_condition": 0,    # condition 필드가 비어 있음 → WARNING
        "weak_reason": 0,          # reason이 없거나 너무 짧음 → WARNING
        "json_parse_error": 0,     # LLM 응답 자체가 파싱 불가 → FAIL
        "tool_contract_mismatch": 0,  # argument 값이 정답과 다름 → FAIL
        "forbidden_tool": 0,       # 명시적으로 금지된 Tool 사용 → FAIL
        "unknown_tool": 0,         # 계약에 없는 알 수 없는 Tool 사용 → FAIL
        "schema_error": 0,         # Tool Plan 구조(스키마) 위반 → FAIL
        "empty_plan_error": 0,     # 정답이 있는데 plan이 비어 있음 → FAIL
    }


def validate_plan(tool_plan, expected_tools, expected_arguments, expected_guardrail, evaluable):
    """
    Rule 기반으로 Tool Plan을 검증하고 validation_result dict를 반환합니다.

    이 함수는 Day4 파이프라인에서 "validate" 단계를 담당합니다.
    normalizer가 정규화한 tool_plan을 받아 구조·계약 일치 여부를 확인하고,
    _finalize_validation()으로 최종 PASS/WARNING/FAIL status를 결정합니다.
    결과는 repair → finalize → results → report 순으로 전달됩니다.

    매개변수
    ─────────────────────────────────────────────────────────────
    tool_plan          : normalizer가 반환한 dict. 올바른 Tool Plan이면
                         {"plan": [{"step": 1, "tool_name": ..., ...}, ...]} 형태.
                         LLM 파싱 실패 시 llm_error_code key가 포함된 dict일 수 있음.

    expected_tools     : 이 테스트 케이스의 정답 Tool 이름 목록 (list[str]).
                         evaluable=True일 때만 비교에 사용. None이면 [] 처리.

    expected_arguments : 정답 argument 값을 담은 dict. 구조: {tool_name: {arg_key: arg_value}}.
                         Tool Contract 이름 검사와 별개로 "값까지" 맞는지 확인할 때 사용.
                         None이면 값 비교를 건너뜀.

    expected_guardrail : 현재 이 함수에서는 직접 사용하지 않음.
                         runner 레벨에서 guardrail 판정에 활용되므로 시그니처에 포함.

    evaluable          : True → expected_tools/expected_guardrail 기준으로 정확도 평가 가능한 케이스.
                         False → 정답을 알 수 없는 케이스(예: 신규 유형 또는 범위 밖 쿼리).
                         evaluable=False이면 스키마 문제가 없어도 WARNING을 반환합니다.
                         이유: 정답 없이 "PASS"를 주면 실제로는 틀렸을 수도 있는 결과를
                         옳다고 확정하는 셈이 되기 때문입니다.

    반환값 (dict)
    ─────────────────────────────────────────────────────────────
    {
      "status"      : "PASS" | "WARNING" | "FAIL"
                      FAIL  → 구조적 오류 또는 정답 불일치(FAIL 유형 issue 존재)
                      WARNING → evaluable=False 이거나 weak_reason/missing_condition 만 존재
                      PASS  → 모든 검사 통과, evaluable=True
      "issues"      : list[dict]. 각 dict는 {"type": ..., "message": ..., 기타 필드}.
                      type 값은 _make_empty_issue_counts()의 key와 동일.
      "issue_counts": _make_empty_issue_counts()와 동일한 구조의 dict.
                      각 issue type별 발생 횟수.
      "evaluable"   : 입력으로 받은 evaluable 값을 그대로 반환 (추적용).
    }

    주의사항
    ─────────────────────────────────────────────────────────────
    * 판정 기준(FAIL 유형 집합, WARNING 유형 집합)을 변경하면
      _finalize_validation()과 results.py / report.py / quality_gate_runner.py의
      집계 로직이 모두 영향을 받습니다. 반드시 연관 파일을 함께 수정하세요.
    * 이 함수는 runner를 import하지 않습니다(순환 import 방지).
      runner → validate_plan 방향으로만 호출이 흐릅니다.

    evaluable: expected_tools/expected_guardrail 기준으로 정확도 평가가 가능한 케이스인지.
    """
    # ── 함수 내부 import 사용 이유 ──────────────────────────────────────────
    # runner를 스크립트로 실행하면 sys.path에 src/day5가 함께 올라가
    # 이 모듈이 day5.mcp_server02.validation / tool_selection.validation 두 이름으로
    # 이중 로드될 수 있고, 그때 한쪽 사본의 module-global 바인딩이 누락될 수 있다.
    # 함수-내부 import로 fully-loaded contracts에서 가져오면 값이 동일하면서 항상 안전하다.
    # (report.py가 utils를 함수-내부 import로 재사용하는 패턴과 동일.)
    # ────────────────────────────────────────────────────────────────────────
    from day5.mcp_server02.contracts import (
        ALLOWED_TOOLS,
        FORBIDDEN_SQL_TOOLS,
        ALLOWED_PLAN_ITEM_FIELDS,
        MIN_REASON_LENGTH,
    )

    # issue 누적 리스트와 유형별 카운터를 초기화
    issues = []
    counts = _make_empty_issue_counts()

    def add_issue(issue_type, message, **extra):
        """issue를 issues 리스트에 추가하고 counts를 증가시키는 내부 헬퍼."""
        record = {"type": issue_type, "message": message}
        record.update(extra)          # tool_name, argument 등 추가 필드 병합
        issues.append(record)
        if issue_type in counts:
            counts[issue_type] += 1   # 해당 유형 카운터 증가

    # ══════════════════════════════════════════════════════════════════════
    # 1단계) 최상위 구조 검사 (json_parse_error / schema_error)
    #        이 단계에서 문제가 발견되면 plan_items를 순회하는 2단계를 건너뜁니다.
    #        즉시 _finalize_validation()으로 조기 반환합니다.
    # ══════════════════════════════════════════════════════════════════════

    # tool_plan이 dict가 아니면 LLM 응답이 아예 파싱되지 않은 것 → json_parse_error
    if not isinstance(tool_plan, dict):
        add_issue("json_parse_error", "Tool Plan이 dict가 아닙니다.")
        return _finalize_validation(issues, counts, evaluable, plan_items=[], expected_tools=expected_tools)

    # llm_error_code가 있으면 llm_client.py에서 파싱 실패 마커를 넣은 것 → json_parse_error
    # schema_error가 아니라 json_parse_error로 분류하는 이유:
    # 구조 문제가 아니라 LLM 응답 자체를 읽어올 수 없었던 것이기 때문.
    if tool_plan.get("llm_error_code"):
        add_issue("json_parse_error",
                  f"LLM 응답 파싱 실패: {tool_plan.get('llm_error_code')}")
        return _finalize_validation(issues, counts, evaluable, plan_items=[], expected_tools=expected_tools)

    # Tool Plan의 최상위 key는 반드시 'plan' 하나여야 함 → 없으면 schema_error
    if "plan" not in tool_plan:
        add_issue("schema_error", "top-level에 'plan' key가 없습니다.")
        return _finalize_validation(issues, counts, evaluable, plan_items=[], expected_tools=expected_tools)

    # 'plan' 외의 추가 key가 있으면 계약 외 필드 → schema_error
    # (조기 반환은 하지 않고 계속 검사)
    extra_top_keys = [k for k in tool_plan.keys() if k != "plan"]
    if extra_top_keys:
        add_issue("schema_error",
                  f"top-level에 허용되지 않은 key가 있습니다: {', '.join(extra_top_keys)}")

    # plan 값은 반드시 list여야 함; dict나 str이면 순회 불가 → schema_error 후 조기 반환
    plan_items = tool_plan.get("plan")
    if not isinstance(plan_items, list):
        add_issue("schema_error", "'plan'이 list가 아닙니다.")
        return _finalize_validation(issues, counts, evaluable, plan_items=[], expected_tools=expected_tools)

    # ══════════════════════════════════════════════════════════════════════
    # 2단계) 각 plan item 검사 (schema_error / tool 계약 / condition / reason)
    #        plan_items 리스트를 순회하며 step 단위로 검증합니다.
    # ══════════════════════════════════════════════════════════════════════
    plan_tool_names = []  # 이후 missing/extra 비교를 위해 plan에서 추출한 tool 이름 수집
    for index, item in enumerate(plan_items):
        step_label = f"step {index + 1}"  # 오류 메시지에서 몇 번째 step인지 표시하기 위한 레이블

        # plan item 자체가 dict가 아니면 필드 접근 자체가 불가 → schema_error 후 다음 item으로 건너뜀
        if not isinstance(item, dict):
            add_issue("schema_error", f"{step_label}: plan item이 dict가 아닙니다.")
            continue

        # ── 필수 필드 존재 여부 확인 ─────────────────────────────────────
        # 다섯 필드(step, tool_name, arguments, condition, reason) 중 하나라도 없으면 schema_error.
        # 값이 비어 있는 경우는 아래의 condition/reason 검사에서 별도 처리함.
        for field in ("step", "tool_name", "arguments", "condition", "reason"):
            if field not in item:
                add_issue("schema_error", f"{step_label}: 필수 필드 '{field}'가 없습니다.")

        # ── 허용되지 않은 추가 필드 확인 ─────────────────────────────────
        # ALLOWED_PLAN_ITEM_FIELDS(contracts에 정의)에 없는 key가 있으면 계약 위반 → schema_error
        extra_fields = [k for k in item.keys() if k not in ALLOWED_PLAN_ITEM_FIELDS]
        if extra_fields:
            add_issue("schema_error",
                      f"{step_label}: 허용되지 않은 필드 {', '.join(extra_fields)}")

        # 이후 검사에 사용할 값 추출
        tool_name = item.get("tool_name")
        arguments = item.get("arguments")
        condition = item.get("condition")
        reason = item.get("reason")

        # arguments가 dict가 아니면(null, 문자열 등) 빈 dict로 대체해 안전하게 처리
        # (schema_error는 위 필수 필드 검사에서 이미 기록됨)
        if not isinstance(arguments, dict):
            arguments = {}

        # ── tool_name 검사 ────────────────────────────────────────────────
        if tool_name:
            # 이 step에서 선택된 tool 이름을 수집 (3단계 missing/extra 비교에 사용)
            plan_tool_names.append(tool_name)

            if tool_name in FORBIDDEN_SQL_TOOLS:
                # 명시적으로 금지된 SQL/Text-to-SQL Tool을 선택한 경우 → forbidden_tool (FAIL)
                # unknown_tool과의 차이: 이름 자체는 시스템에 알려져 있지만 사용이 금지된 Tool.
                add_issue("forbidden_tool",
                          f"{step_label}: Text-to-SQL/SQL 관련 Tool '{tool_name}'은 선택할 수 없습니다.",
                          tool_name=tool_name)
            elif tool_name not in ALLOWED_TOOLS:
                # ALLOWED_TOOLS에도, FORBIDDEN_SQL_TOOLS에도 없는 완전히 미지의 이름 → unknown_tool (FAIL)
                # LLM 환각(hallucination)이나 오타가 원인인 경우가 대부분.
                add_issue("unknown_tool",
                          f"{step_label}: 허용되지 않은 Tool '{tool_name}'.",
                          tool_name=tool_name)
            else:
                # ALLOWED_TOOLS에 있는 정상 Tool → Tool Contract 기반 argument 상세 검사
                _validate_arguments(
                    tool_name, arguments, expected_arguments, step_label, add_issue
                )

        # ── condition 검사 ────────────────────────────────────────────────
        # condition이 None이거나 공백만 있으면 실행 선행 조건이 없는 것 → missing_condition (WARNING)
        # 구조적 오류가 아니라 품질 문제이므로 FAIL이 아닌 WARNING에 해당.
        if not condition or (isinstance(condition, str) and not condition.strip()):
            add_issue("missing_condition", f"{step_label}: condition이 비어 있습니다.",
                      tool_name=tool_name)

        # ── reason 검사 ───────────────────────────────────────────────────
        # reason이 없거나 공백만 있으면 근거가 전혀 없는 것 → weak_reason (WARNING)
        # reason이 MIN_REASON_LENGTH(10자) 미만이면 설명력이 부족 → weak_reason (WARNING)
        # condition과 마찬가지로 실행 가능 여부에는 영향이 없으므로 FAIL이 아닌 WARNING.
        if reason is None or (isinstance(reason, str) and not reason.strip()):
            add_issue("weak_reason", f"{step_label}: reason이 없습니다.",
                      tool_name=tool_name)
        elif isinstance(reason, str) and len(reason.strip()) < MIN_REASON_LENGTH:
            add_issue("weak_reason",
                      f"{step_label}: reason이 너무 짧습니다 (10자 미만).",
                      tool_name=tool_name)

    # ══════════════════════════════════════════════════════════════════════
    # 3단계) expected_tools 대비 missing_tool / extra_tool 판정
    #        evaluable=False인 케이스는 정답을 알 수 없으므로 이 비교를 건너뜁니다.
    # ══════════════════════════════════════════════════════════════════════
    plan_tool_set = set(plan_tool_names)         # plan에 실제로 존재하는 Tool 집합
    expected_set = set(expected_tools or [])     # 정답 Tool 집합 (None이면 빈 set)

    if evaluable:
        # ── missing_tool: 정답에는 있는데 plan에 없는 Tool ─────────────────
        # expected_set - plan_tool_set 으로 계산. 정렬 후 issue 추가(재현성 보장).
        for tool_name in sorted(expected_set - plan_tool_set):
            add_issue("missing_tool",
                      f"기대 Tool '{tool_name}'이(가) plan에 없습니다.",
                      tool_name=tool_name)
        # ── extra_tool: plan에는 있는데 정답에 없는 Tool ───────────────────
        # forbidden/unknown은 위 2단계에서 이미 별도 보고됐으므로
        # ALLOWED_TOOLS에 속한 Tool에 한해서만 extra_tool로 분류.
        for tool_name in sorted(plan_tool_set - expected_set):
            # forbidden/unknown은 이미 별도 보고했으므로 allowed 한정 extra만
            if tool_name in ALLOWED_TOOLS:
                add_issue("extra_tool",
                          f"기대하지 않은 Tool '{tool_name}'이(가) plan에 있습니다.",
                          tool_name=tool_name)

        # ── empty_plan / 빈 정답 케이스 ───────────────────────────────────
        # empty plan 관련
        if expected_set and not plan_tool_names:
            # 정답 Tool이 있는데 LLM이 아무것도 선택하지 않은 경우
            add_issue("empty_plan_error",
                      "기대 Tool이 있는데 plan이 비어 있습니다.")
        if not expected_set and plan_tool_names:
            # expected_tools가 빈 배열(차단/범위 밖)인데 Tool을 선택함
            # 예: 보안 차단 케이스에서 LLM이 Tool을 선택한 경우
            add_issue("extra_tool",
                      "빈 plan이 정답인 케이스인데 Tool이 선택되었습니다.")

    # 최종 status(PASS/WARNING/FAIL) 결정 후 반환
    return _finalize_validation(
        issues, counts, evaluable,
        plan_items=plan_items, expected_tools=expected_tools,
        empty_ok=(not expected_set),  # expected가 빈 set이면 빈 plan이 정답
    )


def _validate_arguments(tool_name, arguments, expected_arguments, step_label, add_issue):
    """
    Tool Contract 기반 argument 검사.

    TOOL_CONTRACTS에서 tool_name에 해당하는 계약을 조회해
    세 가지 유형의 argument 위반을 검사합니다.

    매개변수
    ─────────────────────────────────────────────────────────────
    tool_name          : 검사 대상 Tool 이름. ALLOWED_TOOLS에 속한다고 보장됨.
    arguments          : plan item에서 추출한 arguments dict.
    expected_arguments : 정답 argument 값을 담은 dict. {tool_name: {arg_key: val}} 구조.
                         None이면 값 비교 건너뜀.
    step_label         : 오류 메시지에 표시할 "step N" 문자열.
    add_issue          : validate_plan 내부의 클로저. issue를 기록하는 콜백.

    검사 항목
    ─────────────────────────────────────────────────────────────
    1) missing_argument  : required_arguments 중 arguments에 없거나 빈 값인 key
       → FAIL. "있어야 할 argument가 없다"는 의미.
    2) missing_argument  : any_of_required_arguments 목록 중 하나도 채워지지 않은 경우
       → FAIL. 선택적 필수(OR 조건) 구조.
    3) wrong_argument_name: arguments에 있지만 contract 어디에도 정의되지 않은 key
       → FAIL. "있어서는 안 되는 argument가 있다"는 의미.
       missing_argument와의 차이: missing_argument는 "누락", wrong_argument_name은 "초과·오타".
    4) tool_contract_mismatch: expected_arguments가 주어진 경우 값까지 비교
       → FAIL. Tool 이름과 argument 이름은 맞지만 실제 값이 정답과 다른 경우.

    함수 내부 import 사용 이유
    ─────────────────────────────────────────────────────────────
    모듈-레벨 import(파일 상단)와 별개로 함수 내부에서 다시 TOOL_CONTRACTS를 가져옵니다.
    runner를 스크립트로 직접 실행 시 sys.path 설정 차이로 이 모듈이 두 이름으로
    이중 로드될 수 있어, 모듈-레벨 바인딩이 누락될 위험이 있습니다.
    함수 내부에서 import하면 항상 fully-loaded canonical 모듈의 값을 참조하므로 안전합니다.
    """
    # 이중 로드 사본에서도 안전하도록 호출 시점에 canonical 모듈에서 가져온다(값 동일).
    from day5.mcp_server02.contracts import TOOL_CONTRACTS

    # Tool Contract에서 argument 목록 추출
    contract = TOOL_CONTRACTS.get(tool_name, {})
    required = contract.get("required_arguments", []) or []        # 반드시 있어야 하는 argument
    any_of   = contract.get("any_of_required_arguments", []) or [] # 이 중 하나 이상 있어야 하는 argument
    optional = contract.get("optional_arguments", []) or []        # 있어도 없어도 되는 argument
    # 계약에서 인정하는 모든 argument key 집합 (wrong_argument_name 판정에 사용)
    known = set(required) | set(any_of) | set(optional)

    # ── 검사 1) required argument 누락 ────────────────────────────────────
    # key가 없거나 값이 빈 문자열/None이면 missing_argument (FAIL)
    for key in required:
        if key not in arguments or arguments.get(key) in ("", None):
            add_issue("missing_argument",
                      f"{step_label}: '{tool_name}'의 필수 argument '{key}' 누락.",
                      tool_name=tool_name, argument=key)

    # ── 검사 2) any_of_required: 하나 이상 채워져야 함 ───────────────────
    # OR 조건 필수 argument: 목록 중 하나도 유효하지 않으면 missing_argument (FAIL)
    if any_of:
        satisfied = any(
            (k in arguments and arguments.get(k) not in ("", None)) for k in any_of
        )
        if not satisfied:
            add_issue("missing_argument",
                      f"{step_label}: '{tool_name}'은 {', '.join(any_of)} 중 "
                      "하나 이상이 필요합니다.",
                      tool_name=tool_name)

    # ── 검사 3) contract에 없는 argument 사용 ────────────────────────────
    # known 집합에 없는 key → wrong_argument_name (FAIL)
    # 오타나 LLM 환각으로 잘못된 argument 이름을 생성한 경우.
    for key in arguments.keys():
        if key not in known:
            add_issue("wrong_argument_name",
                      f"{step_label}: '{tool_name}'에 정의되지 않은 argument '{key}'.",
                      tool_name=tool_name, argument=key)

    # ── 검사 4) expected_arguments가 주어진 경우 값까지 비교 ──────────────
    # expected_arguments는 테스트 케이스가 지정한 "정답 값"이므로
    # 이 검사는 평가용이며, argument 이름·필수 여부와는 독립적으로 수행됨.
    # 값이 다르면 tool_contract_mismatch (FAIL)
    if isinstance(expected_arguments, dict):
        expected_for_tool = expected_arguments.get(tool_name)
        if isinstance(expected_for_tool, dict):
            for key, expected_value in expected_for_tool.items():
                if arguments.get(key) != expected_value:
                    add_issue("tool_contract_mismatch",
                              f"{step_label}: '{tool_name}'의 argument '{key}' 값이 "
                              "기대값과 다릅니다.",
                              tool_name=tool_name, argument=key)


def _finalize_validation(issues, counts, evaluable, plan_items, expected_tools,
                         empty_ok=False):
    """
    issue 목록과 카운터를 바탕으로 최종 validation status를 결정하고 반환합니다.

    매개변수
    ─────────────────────────────────────────────────────────────
    issues         : validate_plan에서 누적된 issue dict 리스트.
    counts         : _make_empty_issue_counts() 형태의 카운터 dict.
    evaluable      : 정확도 평가 가능 여부.
    plan_items     : 원본 plan 리스트 (현재는 status 결정에 직접 사용하지 않음; 추적용).
    expected_tools : 정답 Tool 목록 (현재는 status 결정에 직접 사용하지 않음; 추적용).
    empty_ok       : expected_set이 빈 set인 경우 True. 빈 plan이 정답인 케이스.

    반환값 (dict)
    ─────────────────────────────────────────────────────────────
    {
      "status"      : "PASS" | "WARNING" | "FAIL"
      "issues"      : 누적된 issue 리스트 (그대로 전달)
      "issue_counts": 유형별 카운터 dict (그대로 전달)
      "evaluable"   : 입력 evaluable 값 그대로
    }

    status 결정 우선순위
    ─────────────────────────────────────────────────────────────
    1. has_fail=True  → "FAIL"  (구조 오류, 계약 불일치, 정답 불일치)
    2. evaluable=False → "WARNING"
       이유: 정답을 알 수 없는 케이스에서 "PASS"를 부여하면
             실제로는 틀렸을 수 있는 결과를 옳다고 확정하는 셈이 됩니다.
             구조는 맞지만 정확도를 확인할 수 없다는 의미로 WARNING을 반환합니다.
    3. has_warning=True → "WARNING"  (weak_reason, missing_condition)
    4. 위 조건이 모두 False → "PASS"

    FAIL로 이어지는 issue 유형
    ─────────────────────────────────────────────────────────────
    fail_types 집합에 포함된 유형:
      missing_tool, missing_argument, json_parse_error,
      forbidden_tool, unknown_tool, schema_error, empty_plan_error
    추가 FAIL 조건 (counts 기반):
      extra_tool > 0           → has_fail=True
      tool_contract_mismatch > 0 → has_fail=True
      wrong_argument_name > 0  → has_fail=True

    WARNING에만 해당되는 issue 유형
    ─────────────────────────────────────────────────────────────
    warning_types: weak_reason, missing_condition
    이 두 유형은 plan 실행 자체를 막지 않는 품질 문제이므로
    FAIL이 아닌 WARNING으로 처리합니다.

    주의사항
    ─────────────────────────────────────────────────────────────
    이 함수의 status 판정 기준을 변경하면
    results.py / report.py / quality_gate_runner.py의 집계 결과가 모두 달라집니다.
    반드시 연관 모듈도 함께 검토하고 수정하세요.
    """
    # ── FAIL 판정 기준 ────────────────────────────────────────────────────
    # fail_types: issue type이 이 집합에 속하면 곧바로 has_fail=True
    fail_types = {
        "missing_tool",      # 정답 Tool이 plan에 없음
        "missing_argument",  # 필수 argument 누락
        "json_parse_error",  # LLM 응답 파싱 실패
        "forbidden_tool",    # 명시적 금지 Tool 사용
        "unknown_tool",      # 계약에 없는 Tool 사용
        "schema_error",      # 구조(스키마) 위반
        "empty_plan_error",  # 정답 있는데 plan이 비어 있음
    }
    # extra_tool 다수 / tool_contract_mismatch 도 FAIL 취급
    has_fail = any(i["type"] in fail_types for i in issues)

    # extra_tool이 하나라도 있으면 FAIL (불필요한 Tool 선택 = 정답 불일치)
    if counts.get("extra_tool", 0) > 0:
        has_fail = True
    # tool_contract_mismatch가 하나라도 있으면 FAIL (argument 값이 정답과 다름)
    if counts.get("tool_contract_mismatch", 0) > 0:
        has_fail = True
    # wrong_argument_name이 하나라도 있으면 FAIL (계약에 없는 argument key 사용)
    if counts.get("wrong_argument_name", 0) > 0:
        has_fail = True

    # ── WARNING 판정 기준 ─────────────────────────────────────────────────
    # weak_reason / missing_condition 만 있으면 실행 가능하지만 품질이 낮은 상태 → WARNING
    warning_types = {"weak_reason", "missing_condition"}
    has_warning = any(i["type"] in warning_types for i in issues)

    # ── 최종 status 결정 (우선순위: FAIL > evaluable=False WARNING > has_warning WARNING > PASS)
    if has_fail:
        status = "FAIL"
    elif not evaluable:
        # 정확도 평가 제외 케이스: 스키마 문제 없으면 WARNING
        # 정답 없이 PASS를 주면 신뢰할 수 없는 결과가 되므로 WARNING으로 보수적 처리
        status = "WARNING"
    elif has_warning:
        # FAIL issue는 없지만 품질 경고(weak_reason, missing_condition)가 있음
        status = "WARNING"
    else:
        # 모든 검사 통과, evaluable=True → PASS
        status = "PASS"

    # ── 반환값 조립 ──────────────────────────────────────────────────────
    # 이 dict는 results.py, report.py, quality_gate_runner.py에서 그대로 참조합니다.
    # key 이름이나 구조를 바꾸면 해당 모듈도 반드시 함께 수정해야 합니다.
    return {
        "status": status,            # "PASS" | "WARNING" | "FAIL"
        "issues": issues,            # issue dict 리스트 (유형·메시지·추가 필드 포함)
        "issue_counts": counts,      # 유형별 카운터 dict
        "evaluable": evaluable,      # 정확도 평가 가능 여부 (호출자로부터 전달받은 값 그대로)
    }
