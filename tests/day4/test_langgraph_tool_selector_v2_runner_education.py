# -*- coding: utf-8 -*-
"""
Day4 LangGraph Tool Selector v2 Runner - 교육용 TDD 핵심 테스트

목적
====
src/day4/langgraph_tool_selector_v2_runner.py 의 동작을 "수업에서 설명하기 좋은
핵심"만 골라 검증합니다. 모든 함수를 촘촘히 덮지 않고, 다음 네 가지 흐름을
드러내는 데 집중합니다.

  1) 입력 파일명 → output tag 가 어떻게 정해지는가      (derive_output_tag)
  2) --limit / --case-id 가 테스트 범위를 어떻게 줄이는가 (select_cases)
  3) PASS 는 종료, WARNING/FAIL 은 Repair 로 가는 분기     (needs_repair)
  4) Repair 전/후 결과 중 더 좋은 쪽을 고르는 방식         (finalize)

그리고 마지막으로 "실행 옵션을 낮은 성능 → 높은 성능 순서로 바꿔 가며
결과 분포가 개선되는 흐름"을 fake state 로 재현합니다(아래 5번 섹션).

설계 원칙
========
- production 코드(runner 및 하위 모듈)는 수정하지 않고 import 해서 호출만 합니다.
- 실제 LLM 은 호출하지 않습니다. runner.call_llm_json 을 monkeypatch 로 막습니다
  (아래 _block_real_llm autouse fixture). 본 파일의 대부분 테스트는 애초에 LLM 을
  타지 않는 순수 함수만 호출하지만, 안전망으로 전역 차단을 둡니다.
- output 파일 저장(save_outputs)이나 main() 전체 실행은 하지 않습니다.
- 5번 섹션의 성능 비교는 "정확한 실제 성능 측정"이 아니라
  "교육용 실행 옵션 비교 구조"가 성립하는지를 검증하는 테스트입니다.

실행 명령
========
    uv run pytest tests/day4/test_langgraph_tool_selector_v2_runner_education.py -v

    # .venv 에 pytest 가 없으면(requirements.txt 는 수정하지 않으므로) 일시적으로 받아 실행:
    uv run --with pytest pytest tests/day4/test_langgraph_tool_selector_v2_runner_education.py -v

수업에서 보여줄 실제 Runner 실행 순서(참고용 — 이 파일은 실행하지 않음)
======================================================================
1단계 (낮은 기준: argument 보정만, LLM 실패 시 rule fallback 미사용):
    uv run python src/day4/langgraph_tool_selector_v2_runner.py \
        --input data/tool_selection_test_cases_core_10.json \
        --normalization-mode argument-only --fallback-mode strict \
        --output-tag core_10_low

2단계 (full normalization 적용, 여전히 strict):
    uv run python src/day4/langgraph_tool_selector_v2_runner.py \
        --input data/tool_selection_test_cases_core_10.json \
        --normalization-mode full --fallback-mode strict \
        --output-tag core_10_mid

3단계 (full normalization + rule fallback, 가장 안정):
    uv run python src/day4/langgraph_tool_selector_v2_runner.py \
        --input data/tool_selection_test_cases_core_10.json \
        --normalization-mode full --fallback-mode rule \
        --output-tag core_10_high

Guardrail 테스트:
    uv run python src/day4/langgraph_tool_selector_v2_runner.py \
        --input data/tool_selection_test_cases_guardrail_10.json \
        --normalization-mode full --fallback-mode rule \
        --output-tag guardrail_10_high

Action 테스트:
    uv run python src/day4/langgraph_tool_selector_v2_runner.py \
        --input data/tool_selection_test_cases_action_5.json \
        --normalization-mode full --fallback-mode rule \
        --output-tag action_5_high

참고: 낮은 성능 기준이라도 --normalization-mode none 은 사용하지 않습니다.
      최소한 argument-only 보정은 항상 켠 상태에서 비교합니다.
"""

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# import 경로 준비
#   이 파일: <root>/tests/day4/test_*.py
#     parents[0] = tests/day4
#     parents[1] = tests
#     parents[2] = <root>
#   runner 가 'from day4.tool_selection... import ...' 형태를 쓰므로
#   <root>/src 를 sys.path 에 넣어야 day4 패키지를 찾을 수 있습니다.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import day4.langgraph_tool_selector_v2_runner as runner  # noqa: E402


# ===========================================================================
# 공용 fixture / helper
# ===========================================================================
@pytest.fixture(autouse=True)
def _block_real_llm(monkeypatch):
    """실제 LLM 호출 전면 차단(안전망).

    runner.call_llm_json 을 "LLM 실패"를 흉내 내는 함수로 교체합니다.
    네트워크나 API 키 없이도 테스트가 결정론적으로 동작하도록 보장합니다.
    개별 테스트에서 다른 동작이 필요하면 monkeypatch 로 다시 덮어씁니다.

    반환 형식은 production 의 call_llm_json 과 동일한 (result, source) 튜플입니다.
    여기서는 항상 (None, "llm_error") 를 주어 "LLM 이 실패한 상황"을 만듭니다.
    """
    def _fake_call_llm_json(prompt):
        return None, "llm_error"

    monkeypatch.setattr(runner, "call_llm_json", _fake_call_llm_json)


def make_fake_final_state(final_status, *, llm_used=True, fallback_used=False):
    """build_summary 집계용 최소 fake state 를 만듭니다.

    실제 파이프라인을 돌리는 대신, finalize 까지 끝난 것으로 "가정한" state 를
    직접 구성합니다. build_summary 는 final_status / llm_used / fallback_used 등을
    읽어 분포를 셉니다. 5번 성능 비교 섹션에서 옵션별 결과를 재현하는 데 씁니다.

    repair_attempted 는 False 로 둡니다. 이렇게 하면 compute_repair_success 가
    추가 키 없이 안전하게 False 를 반환해, 분포 카운트에만 집중할 수 있습니다.
    """
    return {
        "final_status": final_status,
        "llm_used": llm_used,
        "fallback_used": fallback_used,
        "repair_attempted": False,
        "normalization_rules": [],
        "final_issues": [],
    }


def make_validation_result(status, issues=None):
    """validate_plan 결과를 흉내 낸 최소 dict.

    needs_repair / finalize 는 이 dict 의 "status" 와 "issues" 만 봅니다.
    """
    return {"status": status, "issues": issues or []}


# ===========================================================================
# 1. 옵션 태그 생성 테스트: derive_output_tag()
#    어떤 테스트 데이터 파일을 실행했는지 output tag 가 어떻게 붙는지 설명합니다.
#    (data/tool_selection_test_cases.json → all 케이스는 의도적으로 제외)
# ===========================================================================
@pytest.mark.parametrize(
    "input_path, expected_tag",
    [
        ("data/tool_selection_test_cases_core_10.json", "core_10"),
        ("data/tool_selection_test_cases_guardrail_10.json", "guardrail_10"),
        ("data/tool_selection_test_cases_action_5.json", "action_5"),
    ],
)
def test_derive_output_tag_from_dataset_filename(input_path, expected_tag):
    """기본 파일명(tool_selection_test_cases) 뒤의 식별자가 그대로 tag 가 됩니다.

    예) ..._core_10.json → "core_10".
    출력 파일명에 이 tag 가 들어가 어떤 데이터셋으로 실행했는지 구분됩니다.
    """
    assert runner.derive_output_tag(input_path) == expected_tag


# ===========================================================================
# 2. 케이스 선택 테스트: select_cases()
#    --limit / --case-id 가 실행 범위를 어떻게 줄이는지 설명합니다.
# ===========================================================================
def _sample_cases():
    """select_cases 설명용 가상 케이스 4개(필요한 키만 가진 단순 dict)."""
    return [
        {"case_id": "TS-001", "user_query": "q1"},
        {"case_id": "TS-002", "user_query": "q2"},
        {"case_id": "TS-003", "user_query": "q3"},
        {"case_id": "TS-004", "user_query": "q4"},
    ]


def test_select_cases_limit_takes_first_n():
    """--limit 2 이면 앞에서 2개(TS-001, TS-002)만 선택됩니다."""
    selected = runner.select_cases(_sample_cases(), limit=2, case_id=None)
    assert [c["case_id"] for c in selected] == ["TS-001", "TS-002"]


def test_select_cases_case_id_selects_single_case():
    """--case-id TS-002 이면 해당 케이스 하나만 선택됩니다."""
    selected = runner.select_cases(_sample_cases(), limit=None, case_id="TS-002")
    assert [c["case_id"] for c in selected] == ["TS-002"]


def test_select_cases_case_id_overrides_limit():
    """--case-id 와 --limit 이 함께 와도 case-id 가 우선합니다.

    select_cases 는 case_id 분기를 먼저 처리하므로 limit 은 무시되고
    지정한 케이스 하나만 남습니다.
    """
    selected = runner.select_cases(_sample_cases(), limit=2, case_id="TS-003")
    assert [c["case_id"] for c in selected] == ["TS-003"]


# ===========================================================================
# 3. Repair 판단 테스트: needs_repair()
#    PASS 는 바로 finalize 로, WARNING/FAIL 은 Repair 분기로 갑니다.
# ===========================================================================
@pytest.mark.parametrize(
    "status, expected",
    [
        ("PASS", False),     # 통과 → repair 불필요
        ("WARNING", True),   # 경고 → 1회 repair 기회 부여
        ("FAIL", True),      # 실패 → 1회 repair 기회 부여
    ],
)
def test_needs_repair_routes_by_status(status, expected):
    """validation status 에 따라 repair 필요 여부가 갈립니다."""
    assert runner.needs_repair(make_validation_result(status)) is expected


# ===========================================================================
# 4. 최종 결과 선택 테스트: finalize()
#    Repair 전(initial) 과 Repair 후(repaired) 중 더 좋은 쪽을 채택합니다.
#    SEVERITY_ORDER: PASS(0) < WARNING(1) < FAIL(2) < NEEDS_REVIEW(3)
# ===========================================================================
def _state_with_repair(initial_status, repaired_status):
    """repair 가 시도된 상황의 finalize 입력 state 를 구성합니다.

    initial / repaired 각각의 plan 을 서로 다른 표식으로 넣어,
    finalize 가 어느 쪽 plan 을 최종으로 골랐는지 확인할 수 있게 합니다.
    """
    return {
        "repair_attempted": True,
        "initial_tool_plan": {"chosen": "initial"},
        "repaired_tool_plan": {"chosen": "repaired"},
        "initial_validation_result": make_validation_result(initial_status),
        "repaired_validation_result": make_validation_result(repaired_status),
    }


def test_finalize_fail_then_pass_becomes_pass():
    """initial=FAIL, repaired=PASS → 최종 PASS, repaired plan 채택."""
    state = runner.finalize(_state_with_repair("FAIL", "PASS"))
    assert state["final_status"] == "PASS"
    assert state["final_tool_plan"] == {"chosen": "repaired"}


def test_finalize_warning_then_pass_becomes_pass():
    """initial=WARNING, repaired=PASS → 최종 PASS, repaired plan 채택."""
    state = runner.finalize(_state_with_repair("WARNING", "PASS"))
    assert state["final_status"] == "PASS"
    assert state["final_tool_plan"] == {"chosen": "repaired"}


def test_finalize_fail_then_fail_becomes_needs_review():
    """initial=FAIL, repaired=FAIL → repair 후에도 실패라 NEEDS_REVIEW 로 격상.

    동일 등급이면 repaired 를 채택하지만, 채택 status 가 FAIL 이면
    "자동 처리 한계"를 표시하기 위해 NEEDS_REVIEW 로 바뀝니다.
    """
    state = runner.finalize(_state_with_repair("FAIL", "FAIL"))
    assert state["final_status"] == "NEEDS_REVIEW"


def test_finalize_keeps_initial_when_repair_is_worse():
    """initial=WARNING, repaired=FAIL → repair 가 더 나빠졌으므로 initial 유지.

    repaired(sev 2) 가 initial(sev 1) 보다 심각도가 높아 채택되지 않고,
    더 나은 initial 의 WARNING 과 plan 이 그대로 최종이 됩니다.
    """
    state = runner.finalize(_state_with_repair("WARNING", "FAIL"))
    assert state["final_status"] == "WARNING"
    assert state["final_tool_plan"] == {"chosen": "initial"}


def test_finalize_without_repair_uses_initial():
    """repair 가 시도되지 않았으면(initial 이 PASS 등) initial 결과를 그대로 사용."""
    state = runner.finalize({
        "repair_attempted": False,
        "initial_tool_plan": {"chosen": "initial"},
        "initial_validation_result": make_validation_result("PASS"),
    })
    assert state["final_status"] == "PASS"
    assert state["final_tool_plan"] == {"chosen": "initial"}


# ===========================================================================
# 5. 실행 옵션별 성능 비교 시나리오 테스트
#    낮은 성능 설정 → 높은 성능 설정으로 갈수록 결과 분포가 개선되는 "구조"를
#    fake state 로 재현합니다.
#
#    [중요] 이것은 실제 LLM 성능을 측정하는 테스트가 아닙니다.
#    실제 LLM 을 호출하지 않고, 각 옵션 조합이 "교육적으로 보여주려는" 결과
#    분포(아래 _STAGES)를 fake state 로 만든 뒤, build_summary 가 그 분포를
#    pass/warning/fail/needs_review 로 올바르게 집계하는지, 그리고 단계가
#    올라갈수록 PASS 가 늘고 (FAIL+NEEDS_REVIEW) 가 주는지를 확인합니다.
#    즉 "교육용 실행 옵션 비교 구조"의 검증입니다.
#
#    낮은 성능 기준에서도 --normalization-mode none 은 쓰지 않습니다.
#    1단계도 최소한 argument-only 보정은 켠 상태입니다.
# ===========================================================================

# 각 단계의 옵션 설명과 "기대 결과 분포"(케이스 10개 기준).
# 분포 수치는 실제 측정값이 아니라, 옵션이 좋아질수록 개선된다는
# 교육적 시나리오를 표현하기 위한 예시 값입니다.
_STAGES = [
    {
        "label": "stage1_low",
        "normalization_mode": "argument-only",
        "fallback_mode": "strict",
        # argument 보정은 되지만, LLM 실패 시 rule fallback 을 안 써서
        # FAIL / NEEDS_REVIEW 가 남는다.
        "distribution": {"PASS": 6, "WARNING": 1, "FAIL": 1, "NEEDS_REVIEW": 2},
    },
    {
        "label": "stage2_mid",
        "normalization_mode": "full",
        "fallback_mode": "strict",
        # action tool 정책까지 보정되어 일부 오류가 줄어든다.
        "distribution": {"PASS": 8, "WARNING": 1, "FAIL": 0, "NEEDS_REVIEW": 1},
    },
    {
        "label": "stage3_high",
        "normalization_mode": "full",
        "fallback_mode": "rule",
        # full normalization + LLM 실패 시 rule fallback 까지 → 가장 안정적.
        "distribution": {"PASS": 10, "WARNING": 0, "FAIL": 0, "NEEDS_REVIEW": 0},
    },
]


def _states_from_distribution(distribution):
    """status → 개수 분포를 fake final state 리스트로 펼칩니다."""
    states = []
    for status, count in distribution.items():
        for _ in range(count):
            states.append(make_fake_final_state(status))
    return states


def _summaries_by_stage():
    """단계별 옵션 분포를 build_summary 로 집계한 결과를 모읍니다."""
    summaries = {}
    for stage in _STAGES:
        states = _states_from_distribution(stage["distribution"])
        summaries[stage["label"]] = runner.build_summary(states)
    return summaries


def test_low_setting_does_not_use_normalization_none():
    """규칙 확인: 낮은 성능 단계조차 normalization 을 끄지(none) 않습니다."""
    modes = {stage["normalization_mode"] for stage in _STAGES}
    assert "none" not in modes
    assert _STAGES[0]["normalization_mode"] == "argument-only"


def test_build_summary_counts_match_distribution():
    """build_summary 가 fake state 분포를 status 별로 정확히 집계하는지 확인."""
    summaries = _summaries_by_stage()
    for stage in _STAGES:
        summary = summaries[stage["label"]]
        dist = stage["distribution"]
        assert summary["total_cases"] == sum(dist.values())
        assert summary["pass_count"] == dist["PASS"]
        assert summary["warning_count"] == dist["WARNING"]
        assert summary["fail_count"] == dist["FAIL"]
        assert summary["needs_review_count"] == dist["NEEDS_REVIEW"]


def test_pass_count_improves_low_to_high():
    """단계가 올라갈수록 PASS 케이스 수가 단조 증가하는지(개선 흐름) 확인."""
    summaries = _summaries_by_stage()
    pass_counts = [summaries[s["label"]]["pass_count"] for s in _STAGES]
    # 낮은 성능 → 높은 성능 순서대로 PASS 가 줄지 않고 늘어난다.
    assert pass_counts == sorted(pass_counts)
    assert pass_counts[0] < pass_counts[-1]


def test_unresolved_count_decreases_low_to_high():
    """미해결(FAIL + NEEDS_REVIEW) 케이스가 단계가 오를수록 줄어드는지 확인.

    교육 포인트: 옵션을 좋게 할수록 사람이 손봐야 하는 케이스가 줄어듭니다.
    """
    summaries = _summaries_by_stage()
    unresolved = [
        summaries[s["label"]]["fail_count"] + summaries[s["label"]]["needs_review_count"]
        for s in _STAGES
    ]
    # 단조 감소(같거나 줄어듦), 그리고 최저 단계 > 최고 단계.
    assert unresolved == sorted(unresolved, reverse=True)
    assert unresolved[0] > unresolved[-1]


# ===========================================================================
# (보강) mock 처리 확인: 실제 LLM 없이 fallback-mode 차이를 보여줍니다.
#   _block_real_llm fixture 가 call_llm_json 을 "LLM 실패"로 만들어 둔 상태에서,
#   generate_tool_plan 이 fallback_mode 에 따라 어떻게 갈라지는지 확인합니다.
#   - strict : rule fallback 미사용 → llm_used/fallback_used 모두 False
#   - rule   : rule 기반 plan 으로 대체 → fallback_used True
#   이 두 테스트는 "실제 LLM 호출이 mock 으로 차단되었음"도 함께 증명합니다.
# ===========================================================================
_EMPTY_TEMPLATES = {"system_prompt": None, "improved_prompt": None}


def test_generate_tool_plan_strict_mode_records_failure_without_fallback():
    """strict: LLM 실패 시 rule fallback 을 쓰지 않고 실패를 기록합니다."""
    state = {"user_query": "EQP-EV-03 알람 확인", "fallback_mode": "strict"}
    result = runner.generate_tool_plan(state, _EMPTY_TEMPLATES)
    assert result["llm_used"] is False
    assert result["fallback_used"] is False
    # 실패 출처(call_llm_json 이 돌려준 source)가 생성 출처로 남습니다.
    assert result["generation_source"] == "llm_error"


def test_generate_tool_plan_rule_mode_uses_rule_fallback():
    """rule: LLM 실패 시 rule 기반 fallback plan 으로 대체합니다."""
    state = {"user_query": "EQP-EV-03 알람 확인", "fallback_mode": "rule"}
    result = runner.generate_tool_plan(state, _EMPTY_TEMPLATES)
    assert result["fallback_used"] is True
    assert result["generation_source"] == "fallback_rule"
    # rule fallback plan 에도 plan 키가 들어 있어 이후 검증으로 흐를 수 있습니다.
    assert "plan" in result["initial_tool_plan"]


# ===========================================================================
# (보강) 옵션 → state 전파 확인: build_initial_state()
#   CLI 옵션(normalization_mode / fallback_mode)이 케이스 state 로 그대로
#   전달되는지 확인합니다. 5번 성능 비교의 "옵션이 실제로 흐름에 반영된다"는
#   전제를 뒷받침합니다.
# ===========================================================================
def test_build_initial_state_propagates_options():
    """--normalization-mode / --fallback-mode 가 state 초기값에 반영됩니다."""
    case = {
        "case_id": "TC-001",
        "user_query": "EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는지 확인해줘",
        "expected_tools": ["get_recent_alarm_events"],
    }
    state = runner.build_initial_state(
        case, normalization_mode="full", fallback_mode="strict"
    )
    assert state["normalization_mode"] == "full"
    assert state["fallback_mode"] == "strict"
    # expected_tools 가 있으므로 정확도 평가 가능 케이스로 표시됩니다.
    assert state["evaluable"] is True
