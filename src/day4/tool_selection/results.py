# -*- coding: utf-8 -*-
"""
Day4 Tool Selection Results

Agent 실행이 끝난 state로부터 결과 record / trace record / summary 집계를 만드는
보조 모듈입니다. (관측 가능성/Observability 계층)

─────────────────────────────────────────────────────────────────────────────
[모듈의 역할 — 파이프라인에서 이 파일이 담당하는 구간]

전체 흐름:
    generate → validate → (repair) → finalize
        → results.py  ← ★ 여기
        → report.py
        → output_writer.py

finalize 단계까지 모든 state 값이 확정된 뒤, 이 모듈이 호출됩니다.
이 모듈은 단 하나의 책임만 갖습니다:
    "이미 계산된 state를 관측 가능한 dict 형태로 변환한다."

실행 로직(generate/validate/repair/finalize)이나 판정 규칙(SEVERITY_ORDER 읽기 제외)은
이 모듈 안에서 바뀌지 않습니다.

─────────────────────────────────────────────────────────────────────────────
[result_record vs trace_record — 두 dict의 목적 차이]

▸ result_record  (build_result_record)
    · outputs/day4/llm_tool_plan_results.json 에 저장됩니다.
    · "케이스별 최종 판정 결과"를 요약합니다.
    · 중간 validation 상세(initial_validation_result / repaired_validation_result 전체)는
      포함하지 않습니다 — initial_status(단순 문자열)만 남깁니다.
    · report.py가 이 dict를 읽어 Mustache 템플릿으로 사람이 읽을 수 있는 보고서를 생성합니다.
    · quality_gate_runner.py도 이 파일을 읽어 PASS/CONDITIONAL_PASS/HOLD를 판정합니다.

▸ trace_record  (build_trace_record)
    · outputs/day4/llm_tool_plan_trace.jsonl 에 JSONL 한 줄로 기록됩니다.
    · "단계별 전체 중간 상태"를 모두 보존합니다.
    · initial_validation_result / repaired_validation_result 전체 dict가 포함됩니다.
    · repair 전·후를 모두 볼 수 있어 디버깅·사후 분석(post-mortem) 용도로 사용됩니다.
    · error_message 키가 추가로 포함되어 있어 예외 발생 시 원인을 기록합니다.

▸ 공통 원칙
    · state 값을 그대로 직렬화합니다.
      finalize 노드가 이미 "정답" state를 확정했으므로, 이 모듈에서
      값을 재계산하거나 보정하면 finalize 결과와 어긋날 위험이 있습니다.
      state.get(key, default) 패턴으로 읽기만 합니다.

─────────────────────────────────────────────────────────────────────────────
[normalization 관련 필드를 두 record 모두에 남기는 이유]

normalization은 LLM이 생성한 tool plan의 형식 오류(대소문자, 인수명 표기 차이 등)를
검증 전에 자동 보정하는 단계입니다.
    · raw_*      : 보정 이전 원본 — LLM 출력 품질 분석에 사용
    · normalized_* : 보정 이후 — 실제 validation에 입력된 값
    · normalization_rules : 어떤 규칙이 얼마나 적용됐는지 투명성 확보

ablation(정규화 비활성화) 실험 시 두 값을 비교해 정규화가 판정에 미친 영향을 측정합니다.
"case_id / expected_tools 기반 보정"이 아님을 명시해 두는 이유는,
정규화가 정답 leakage 없이 순수 형식 교정임을 보장하기 위해서입니다.

─────────────────────────────────────────────────────────────────────────────
설계 메모:
- 이 모듈은 실행 흐름(generate/validate/repair/finalize)이나 판정 규칙을 바꾸지 않고,
  이미 계산된 state 값을 dict로 직렬화·집계만 합니다.
- 의존: SEVERITY_ORDER (tool_selection_contracts) 만 사용합니다.
  runner / report 를 import 하지 않습니다(순환 import 방지).
- plan_tool_names 는 report.py가 runner에서 함수-내부 import로 재사용하고 있어,
  이번 단계에서는 runner에 그대로 둡니다(이 모듈로 옮기지 않음).
"""
from day4.tool_selection.contracts import SEVERITY_ORDER


def compute_repair_success(state):
    """repair 단계가 실질적인 품질 개선을 달성했는지 판정합니다.

    판정 기준:
        1. repair_attempted 가 True 여야 합니다(repair 시도 자체가 없으면 False).
        2. repaired_validation_result 의 status 가
           initial_validation_result 의 status 보다
           SEVERITY_ORDER 상 낮은 값(더 좋은 등급)이어야 합니다.

    SEVERITY_ORDER 예시 (contracts.py 참조):
        "PASS" < "WARNING" < "FAIL" < "NEEDS_REVIEW"
        숫자가 작을수록 심각도가 낮음(= 더 좋음).

    repair 후 동일 등급이거나 더 나빠진 경우에는 False 를 반환합니다.
    이 함수 결과는 build_summary 의 repair_success_count 집계에 사용됩니다.

    주의:
        status 가 state 에 없으면 "FAIL" 을 기본값으로 사용합니다.
        SEVERITY_ORDER 에 없는 status 값은 정수 2 로 처리됩니다.
    """
    # repair 를 시도하지 않은 케이스는 성공 여부를 판단할 수 없음
    if not state.get("repair_attempted"):
        return False
    # initial: repair 투입 전 첫 번째 validation 결과의 등급
    initial_status = state.get("initial_validation_result", {}).get("status", "FAIL")
    # repaired: repair 완료 후 두 번째 validation 결과의 등급
    repaired_status = state.get("repaired_validation_result", {}).get("status", "FAIL")
    # 숫자가 작을수록 낮은 심각도 → repaired < initial 이면 개선됨
    return SEVERITY_ORDER.get(repaired_status, 2) < SEVERITY_ORDER.get(initial_status, 2)


# ===========================================================================
# 결과 집계 (results.json / trace.jsonl / summary)
# ===========================================================================
def build_result_record(state):
    """한 케이스의 실행 결과를 results.json 에 저장할 dict 형태로 변환합니다.

    이 함수는 finalize 노드가 확정한 state를 "요약 직렬화"합니다.
    중간 검증 상세(initial_validation_result, repaired_validation_result 전체 dict)는
    포함하지 않고 최종 판정에 필요한 핵심 필드만 선별합니다.

    반환값은 runner.py 가 JSON 파일로 저장하고,
    report.py 가 Mustache 템플릿에 바인딩하며,
    quality_gate_runner.py 가 PASS/HOLD 판정 근거로 읽습니다.

    ─── 필드 설명 ───────────────────────────────────────────────────────────

    [케이스 식별 / 입력]
        case_id            : 테스트 케이스 고유 ID (예: "TC-001")
        user_query         : 평가에 사용한 사용자 질의 원문
        expected_tools     : 정답 도구 목록 — validation 비교 기준
        expected_arguments : 정답 인수 dict — argument validation 기준

    [초기 생성 결과]
        initial_tool_plan  : LLM(또는 rule fallback)이 처음 생성한 tool plan
        initial_status     : 첫 번째 validation 결과 등급 문자열
                             (PASS / WARNING / FAIL / NEEDS_REVIEW)
                             ※ initial_validation_result 전체가 아닌 status 만 포함
                             — 상세는 trace_record 참조

    [repair 단계]
        repair_attempted   : repair 노드가 실행됐으면 True
                             (initial_status 가 FAIL/NEEDS_REVIEW 일 때 시도)
        repaired_tool_plan : repair 후 생성된 tool plan (미시도 시 빈 dict)
        final_tool_plan    : 최종 채택된 tool plan
                             (repair 성공 시 repaired, 아니면 initial)

    [최종 판정]
        final_status       : 최종 validation 등급 — quality gate 의 1차 기준
        final_issues       : 최종 validation 에서 발견된 문제 목록
                             (report.py 가 이슈 유형별 카운트를 계산)

    [생성 출처 / LLM 사용 여부]
        generation_source        : 최종 생성 단계의 출처
                                   ("llm" / "rule_fallback" / "llm_error" 등)
        initial_generation_source: initial 단계 출처 (None 가능)
        repair_generation_source : repair 단계 출처 (None 가능)
        llm_used       : 이 케이스에서 LLM 호출이 한 번이라도 성공했으면 True
        fallback_used  : 이 케이스에서 fallback이 한 번이라도 발동됐으면 True

        ⚠ llm_used 와 fallback_used 해석 주의:
            fallback_used=True 라고 해서 LLM 성능이 낮다는 의미가 아닙니다.
            LLM 서버 미설정(CLOUD_LLM_PROVIDER 없음), API 키 미입력,
            네트워크 오류, mock 환경 등 외부 요인으로 fallback 이 발동될 수 있습니다.
            summary의 fallback_count 가 높을 때 "LLM tool-plan 품질 저하"로 해석하면
            오진단이 될 수 있습니다 — 먼저 llm_unavailable_count/llm_error_count를 확인하세요.

        initial_fallback_used : initial 단계에서 fallback 이 발동됐으면 True
        repair_fallback_used  : repair 단계에서 fallback 이 발동됐으면 True
        fallback_mode         : 설정된 fallback 정책 ("rule" / "strict")

    [성능]
        elapsed_seconds : 이 케이스의 전체 처리 소요 시간(초)

    [정규화 투명성 — ablation 분석용]
        normalization_mode          : 정규화 활성화 수준 ("full" / "none" 등)
        normalization_applied       : 이 케이스에서 실제로 정규화가 적용됐으면 True
        normalization_rules         : 적용된 규칙 목록 (rule_type / 대상 등 포함)
        raw_initial_tool_plan       : 정규화 이전 initial 원본
        normalized_initial_tool_plan: 정규화 이후 initial
        raw_repaired_tool_plan      : 정규화 이전 repaired 원본
        normalized_repaired_tool_plan: 정규화 이후 repaired

        ※ 이 필드들은 case_id / expected_tools 기반 보정이 아닙니다.
          정답 leakage 없이 순수 형식 교정임을 추적하기 위해 보존합니다.
    """
    return {
        # ── 케이스 식별 / 입력 ───────────────────────────────────────────────
        # 테스트 케이스 고유 식별자 — report / gate 에서 케이스를 특정할 때 사용
        "case_id": state.get("case_id", ""),
        # 사용자 질의 원문 — 보고서에 표시되는 실제 입력 문장
        "user_query": state.get("user_query", ""),
        # 정답 도구 목록 — tool name 일치 여부 검증의 기준
        "expected_tools": state.get("expected_tools", []),
        # 정답 인수 dict — argument key/value 검증 기준 (도구명 → 인수 dict)
        "expected_arguments": state.get("expected_arguments", {}),
        # ── 초기 생성 결과 ───────────────────────────────────────────────────
        # LLM 또는 rule fallback 이 처음 생성한 tool plan 전체
        "initial_tool_plan": state.get("initial_tool_plan", {}),
        # initial validation 결과의 등급 문자열만 추출 — 상세는 trace_record 에 있음
        "initial_status": state.get("initial_validation_result", {}).get("status", ""),
        # ── repair 단계 ──────────────────────────────────────────────────────
        # repair 노드 실행 여부 (초기 등급이 FAIL / NEEDS_REVIEW 일 때 True)
        "repair_attempted": state.get("repair_attempted", False),
        # repair 후 생성된 tool plan (repair_attempted=False 이면 빈 dict)
        "repaired_tool_plan": state.get("repaired_tool_plan", {}),
        # ── 최종 결과 ────────────────────────────────────────────────────────
        # 최종 채택된 tool plan (repair 성공 → repaired, 아니면 initial)
        "final_tool_plan": state.get("final_tool_plan", {}),
        # 최종 validation 등급 — quality_gate_runner 의 PASS/HOLD 판정에 직접 사용
        "final_status": state.get("final_status", ""),
        # 최종 validation 에서 발견된 이슈 목록 — report 의 이슈 유형별 카운트 원천
        "final_issues": state.get("final_issues", []),
        # ── 생성 출처 / LLM 사용 여부 ──────────────────────────────────────
        # 최종 생성 단계 출처 ("llm" / "rule_fallback" / "llm_error" 등)
        "generation_source": state.get("generation_source", ""),
        # initial 단계 출처 (None 이면 해당 단계 자체가 없었음을 의미)
        "initial_generation_source": state.get("initial_generation_source"),
        # repair 단계 출처 (repair 미시도 시 None)
        "repair_generation_source": state.get("repair_generation_source"),
        # 이 케이스에서 LLM 호출이 한 번이라도 성공했으면 True
        # fallback_used=True 와 동시에 True 일 수 있음 (initial 성공 + repair fallback 등)
        "llm_used": state.get("llm_used", False),
        # 이 케이스에서 fallback 이 한 번이라도 발동됐으면 True
        # ⚠ 이 값이 높다고 LLM 품질 문제라고 단정하지 말 것 (환경 요인 우선 확인)
        "fallback_used": state.get("fallback_used", False),
        # initial 단계에서만 fallback 이 발동됐으면 True
        "initial_fallback_used": state.get("initial_fallback_used", False),
        # repair 단계에서만 fallback 이 발동됐으면 True
        "repair_fallback_used": state.get("repair_fallback_used", False),
        # 설정된 fallback 정책 — "rule": rule 기반 대체, "strict": fallback 금지
        "fallback_mode": state.get("fallback_mode", "rule"),
        # ── 성능 ────────────────────────────────────────────────────────────
        # 이 케이스의 전체 처리 소요 시간(초) — 배치 성능 분석용
        "elapsed_seconds": state.get("elapsed_seconds", 0.0),
        # ── 정규화 투명성 (case_id/expected_tools 기반 보정 아님) ────────────
        # 정규화 활성화 수준 ("full" / "none") — ablation 실험 식별자
        "normalization_mode": state.get("normalization_mode", "full"),
        # 이 케이스에서 실제로 정규화 규칙이 한 건 이상 적용됐으면 True
        "normalization_applied": state.get("normalization_applied", False),
        # 적용된 규칙 목록 — rule_type / 대상 도구명 / 보정 내용 포함
        "normalization_rules": state.get("normalization_rules", []),
        # 정규화 이전 initial 원본 — LLM 원시 출력 품질 측정에 사용
        "raw_initial_tool_plan": state.get("raw_initial_tool_plan", {}),
        # 정규화 이후 initial — 실제 validation 에 입력된 값
        "normalized_initial_tool_plan": state.get("normalized_initial_tool_plan", {}),
        # 정규화 이전 repaired 원본
        "raw_repaired_tool_plan": state.get("raw_repaired_tool_plan", {}),
        # 정규화 이후 repaired — 실제 repaired validation 에 입력된 값
        "normalized_repaired_tool_plan": state.get("normalized_repaired_tool_plan", {}),
    }


def build_trace_record(state):
    """한 케이스의 전체 중간 상태를 trace.jsonl 한 줄로 직렬화합니다.

    result_record 와 달리 "단계별 전체 중간 정보"를 모두 보존합니다.
    디버깅, 사후 분석(post-mortem), 트레이스 리뷰어(day5) 용도로 사용됩니다.

    result_record 와의 주요 차이점:
        · initial_validation_result 와 repaired_validation_result 전체 dict 포함
          (result_record 는 initial_status 문자열만 포함)
        · error_message 키 추가 — 예외 발생 시 원인 문자열 기록
        · repair_generation_source 기본값이 "" (result_record 는 None)

    이 함수도 state 값을 그대로 직렬화합니다 — 재계산 없음.
    JSONL 포맷이므로 output_writer.py 가 한 줄씩 append 합니다.

    ─── 필드 설명 ───────────────────────────────────────────────────────────

    [케이스 식별 / 입력] — result_record 와 동일
        case_id, user_query, expected_tools, expected_arguments

    [초기 생성 + 검증 전체]
        initial_tool_plan        : 첫 번째 생성 tool plan
        initial_validation_result: 첫 번째 검증 결과 전체 dict
                                   (status / issues / tool_name_check 등 포함)
                                   ※ result_record 에는 status 문자열만 있음

    [repair 단계 전체]
        repair_attempted         : repair 시도 여부
        repaired_tool_plan       : repair 후 tool plan
        repaired_validation_result: repair 후 검증 결과 전체 dict
                                   repair 미시도 시 빈 dict

    [최종 결과] — result_record 와 동일
        final_tool_plan, final_status, final_issues

    [생성 출처 / LLM 사용] — result_record 와 동일
        generation_source, initial_generation_source, repair_generation_source,
        llm_used, fallback_used, initial_fallback_used, repair_fallback_used,
        fallback_mode, elapsed_seconds

        ⚠ fallback_used / fallback_count 해석 주의 (result_record 와 동일):
            fallback 발동이 많다고 LLM 품질 문제라고 해석하면 안 됩니다.
            환경(API 미설정, 네트워크 오류, mock 모드) 요인을 먼저 확인하세요.

    [에러 기록]
        error_message : 처리 중 예외가 발생한 경우 메시지 문자열 (없으면 None)
                        trace 에만 포함되어 있어 result 파일에는 노출되지 않음

    [정규화 투명성] — result_record 와 동일
        normalization_mode, normalization_applied, normalization_rules,
        raw_initial_tool_plan, normalized_initial_tool_plan,
        raw_repaired_tool_plan, normalized_repaired_tool_plan
    """
    return {
        # ── 케이스 식별 / 입력 ───────────────────────────────────────────────
        # 테스트 케이스 고유 ID — JSONL 분석 시 케이스 추적에 사용
        "case_id": state.get("case_id", ""),
        # 사용자 질의 원문 — 트레이스 리뷰어가 컨텍스트 확인용으로 사용
        "user_query": state.get("user_query", ""),
        # 정답 도구 목록 — initial/repaired 와 비교해 delta 분석에 사용
        "expected_tools": state.get("expected_tools", []),
        # 정답 인수 dict — argument 수준 오류 원인 분석에 사용
        "expected_arguments": state.get("expected_arguments", {}),
        # ── 초기 생성 + 검증 전체 ───────────────────────────────────────────
        # 첫 번째 생성 tool plan 원본
        "initial_tool_plan": state.get("initial_tool_plan", {}),
        # 첫 번째 검증 결과 전체 — status / issues / tool_name_check 등 포함
        # result_record 에는 status 문자열만 있으므로, 상세 분석은 trace 를 참조
        "initial_validation_result": state.get("initial_validation_result", {}),
        # ── repair 단계 전체 ─────────────────────────────────────────────────
        # repair 노드 실행 여부
        "repair_attempted": state.get("repair_attempted", False),
        # repair 후 생성된 tool plan (repair_attempted=False 이면 빈 dict)
        "repaired_tool_plan": state.get("repaired_tool_plan", {}),
        # repair 후 검증 결과 전체 — repair 미시도 시 빈 dict
        # initial vs repaired 비교로 repair 효과를 정량화할 수 있음
        "repaired_validation_result": state.get("repaired_validation_result", {}),
        # ── 최종 결과 ────────────────────────────────────────────────────────
        # 최종 채택된 tool plan
        "final_tool_plan": state.get("final_tool_plan", {}),
        # 최종 validation 등급
        "final_status": state.get("final_status", ""),
        # 최종 이슈 목록 — 트레이스 리뷰어의 이슈 분류 분석에 사용
        "final_issues": state.get("final_issues", []),
        # ── 생성 출처 / LLM 사용 여부 ──────────────────────────────────────
        # 최종 단계 출처 문자열
        "generation_source": state.get("generation_source", ""),
        # initial 단계 출처 (None 이면 해당 단계가 없었음)
        "initial_generation_source": state.get("initial_generation_source"),
        # repair 단계 출처 (repair 미시도 시 "" — result_record 의 None 과 다름)
        "repair_generation_source": state.get("repair_generation_source", ""),
        # LLM 호출 성공 여부 — True 여도 fallback 이 같이 발동될 수 있음
        "llm_used": state.get("llm_used", False),
        # fallback 발동 여부 — 환경 요인 포함, LLM 품질 단독 지표가 아님
        "fallback_used": state.get("fallback_used", False),
        # initial 단계 fallback 발동 여부
        "initial_fallback_used": state.get("initial_fallback_used", False),
        # repair 단계 fallback 발동 여부
        "repair_fallback_used": state.get("repair_fallback_used", False),
        # 설정된 fallback 정책
        "fallback_mode": state.get("fallback_mode", "rule"),
        # 이 케이스 처리 소요 시간(초)
        "elapsed_seconds": state.get("elapsed_seconds", 0.0),
        # ── 에러 기록 (trace 전용) ───────────────────────────────────────────
        # 처리 중 예외 메시지 (없으면 None) — result_record 에는 없는 trace 전용 필드
        "error_message": state.get("error_message"),
        # ── 정규화 투명성 ─────────────────────────────────────────────────
        # 정규화 활성화 수준 — ablation 실험 식별자
        "normalization_mode": state.get("normalization_mode", "full"),
        # 이 케이스에서 정규화 규칙이 실제 적용됐으면 True
        "normalization_applied": state.get("normalization_applied", False),
        # 적용된 규칙 목록 — rule_type 별 보정 내역 포함
        "normalization_rules": state.get("normalization_rules", []),
        # 정규화 이전 initial 원본
        "raw_initial_tool_plan": state.get("raw_initial_tool_plan", {}),
        # 정규화 이후 initial
        "normalized_initial_tool_plan": state.get("normalized_initial_tool_plan", {}),
        # 정규화 이전 repaired 원본
        "raw_repaired_tool_plan": state.get("raw_repaired_tool_plan", {}),
        # 정규화 이후 repaired
        "normalized_repaired_tool_plan": state.get("normalized_repaired_tool_plan", {}),
    }


def build_summary(states):
    """전체 케이스 목록(states)으로부터 배치 실행 summary dict를 집계합니다.

    이 함수는 build_result_record 가 만든 개별 케이스 결과를 받아
    배치 수준의 통계를 계산합니다.
    반환된 dict 는 output_writer.py 가 JSON 파일로 저장하고,
    quality_gate_runner.py 와 day4_quality_dashboard_streamlit_app.py 가 읽습니다.

    ─────────────────────────────────────────────────────────────────────────
    [집계 단위 주의사항]

    ▸ "케이스" 단위 집계 (한 케이스에서 여러 번 발생해도 1로 셈)
        pass_count, warning_count, fail_count, needs_review_count
        llm_used_count
        fallback_count         ← fallback_used=True 인 "케이스" 수
        repair_attempt_count
        repair_success_count
        normalization_applied_count
        initial_fallback_count
        repair_fallback_count

    ▸ "이벤트" 단위 집계 (한 케이스에서 initial+repair 모두 발생하면 2로 셈)
        llm_error_count        ← generation_source / repair_generation_source 에서 카운트
        llm_unavailable_count  ← 동일

    ▸ "이슈 발생" 단위 집계 (한 케이스에 같은 유형 이슈가 여럿이면 여러 번 셈)
        missing_tool_count, extra_tool_count, missing_argument_count, ...
        → final_issues 리스트의 각 항목을 순회해 집계

    ─────────────────────────────────────────────────────────────────────────
    [fallback_count vs initial/repair_fallback_count 차이]

        fallback_count
            : "적어도 한 단계에서 fallback 이 발동된 케이스 수"
            : fallback_used=True 인 state 를 셉니다.
            : 기존 의미를 유지합니다.

        initial_fallback_count
            : initial 단계에서 fallback 이 발동된 "케이스" 수
            : initial_fallback_used=True 인 state 를 셉니다.

        repair_fallback_count
            : repair 단계에서 fallback 이 발동된 "케이스" 수
            : repair_fallback_used=True 인 state 를 셉니다.

        ⚠ fallback_count 가 높다고 LLM 성능 저하로 해석하면 안 됩니다.
          llm_unavailable_count / llm_error_count 를 먼저 확인하세요.
          API 키 미설정이나 네트워크 오류가 원인인 경우가 많습니다.

    ─────────────────────────────────────────────────────────────────────────
    [repair_success_count 집계 기준]

        compute_repair_success(state) 가 True 인 케이스를 셉니다.
        조건: repair_attempted=True 이고
              repaired_validation_result.status 가 initial_validation_result.status 보다
              SEVERITY_ORDER 상 낮은 값(= 더 좋은 등급)일 때.
        동일 등급이거나 더 나빠진 경우에는 집계되지 않습니다.

    ─────────────────────────────────────────────────────────────────────────
    [normalization 집계]

        normalization_mode       : 첫 번째 state 의 값으로 배치 전체 설정을 표시
        normalization_applied_count : 실제로 정규화가 적용된 케이스 수
        action_policy_rule_count    : rule_type=="action_tool_policy" 발생 건수
        argument_normalization_rule_count: rule_type=="argument_normalization" 발생 건수
        argument_removed_rule_count : rule_type=="argument_removed" 발생 건수
        dedup_rule_count            : rule_type=="deduplicate" 발생 건수

        ablation(normalization_mode="none") 실험과 비교해
        정규화가 PASS 율에 얼마나 기여했는지 측정하는 데 사용합니다.

    ─── 필드 설명 ───────────────────────────────────────────────────────────

    [규모]
        total_cases : 집계 대상 케이스 수

    [최종 판정 분포]
        pass_count         : final_status=="PASS" 케이스 수
        warning_count      : final_status=="WARNING" 케이스 수
        fail_count         : final_status=="FAIL" 케이스 수
        needs_review_count : final_status=="NEEDS_REVIEW" 케이스 수

    [이슈 유형별 누적 발생 건수]
        json_parse_error_count    : LLM 출력이 JSON 파싱 불가했던 건수
        missing_tool_count        : 필요한 도구가 누락된 건수
        extra_tool_count          : 불필요한 도구가 추가된 건수
        missing_argument_count    : 필수 인수가 누락된 건수
        wrong_argument_name_count : 인수 이름이 잘못된 건수
        missing_condition_count   : 조건(condition) 필드 누락 건수
        weak_reason_count         : reason 필드가 부실한 건수
        tool_contract_mismatch_count: 도구 contract 불일치 건수

    [LLM / fallback 사용]
        llm_used_count     : LLM 호출이 성공한 케이스 수
        fallback_count     : fallback 이 발동된 케이스 수 (케이스 단위)
        repair_attempt_count : repair 를 시도한 케이스 수
        repair_success_count : repair 가 품질을 개선한 케이스 수

    [정규화 집계]
        normalization_mode, normalization_applied_count,
        action_policy_rule_count, argument_normalization_rule_count,
        argument_removed_rule_count, dedup_rule_count

    [후속 추가 집계 — 루프 이후 계산]
        fallback_mode           : 배치의 fallback 정책 설정
        initial_fallback_count  : initial 단계 fallback 케이스 수
        repair_fallback_count   : repair 단계 fallback 케이스 수
        llm_error_count         : LLM 오류 이벤트 수 (이벤트 단위)
        llm_unavailable_count   : LLM 서버 미접속 이벤트 수 (이벤트 단위)
    """
    summary = {
        # 집계 대상 전체 케이스 수
        "total_cases": len(states),
        # 최종 판정 등급별 케이스 수 — quality gate 의 PASS 율 계산에 사용
        "pass_count": 0,
        "warning_count": 0,
        "fail_count": 0,
        # json_parse_error 는 final_issues 에서 집계 — LLM 출력 포맷 문제 파악용
        "json_parse_error_count": 0,
        # tool 선택 오류 유형별 건수 — 어떤 유형의 실수가 많은지 분석
        "missing_tool_count": 0,
        "extra_tool_count": 0,
        # argument 오류 유형별 건수
        "missing_argument_count": 0,
        "wrong_argument_name_count": 0,
        # 조건/근거 품질 오류 건수
        "missing_condition_count": 0,
        "weak_reason_count": 0,
        # 도구 contract 위반 건수
        "tool_contract_mismatch_count": 0,
        # LLM 성공 케이스 수 — fallback_count 와 함께 보면 LLM 환경 상태 파악 가능
        "llm_used_count": 0,
        # fallback 발동 케이스 수 (케이스 단위)
        # ⚠ 이 값이 높으면 LLM 설정·환경을 먼저 점검 (품질 단독 지표 아님)
        "fallback_count": 0,
        # repair 시도·성공 케이스 수 — repair 전략의 효과 측정
        "repair_attempt_count": 0,
        "repair_success_count": 0,
        # NEEDS_REVIEW 는 자동 판정 불가로 사람 검토가 필요한 케이스
        "needs_review_count": 0,
        # ablation / 정규화 투명성 집계
        # normalization_mode: 첫 번째 state 기준으로 배치 설정을 표시
        "normalization_mode": states[0].get("normalization_mode", "full") if states else "full",
        # 실제로 정규화가 적용된 케이스 수 — normalization_mode 와 비교해 실제 효과 확인
        "normalization_applied_count": 0,
        # rule_type 별 정규화 발생 건수 — 어떤 보정이 가장 많이 필요했는지 파악
        "action_policy_rule_count": 0,
        "argument_normalization_rule_count": 0,
        "argument_removed_rule_count": 0,
        "dedup_rule_count": 0,
    }

    for state in states:
        # ── 최종 판정 등급별 집계 ────────────────────────────────────────────
        # final_status 는 finalize 노드가 확정한 최종 등급 문자열
        final_status = state.get("final_status", "")
        if final_status == "PASS":
            summary["pass_count"] += 1
        elif final_status == "WARNING":
            summary["warning_count"] += 1
        elif final_status == "FAIL":
            summary["fail_count"] += 1
        elif final_status == "NEEDS_REVIEW":
            # 자동 판정 불가 케이스 — 사람 검토 필요
            summary["needs_review_count"] += 1

        # ── 정규화 rule type별 집계 ──────────────────────────────────────────
        # normalization_applied 가 True 인 케이스를 케이스 단위로 셈
        if state.get("normalization_applied"):
            summary["normalization_applied_count"] += 1
        # normalization_rules 의 각 규칙을 rule_type 으로 분류해 누적
        for rule in (state.get("normalization_rules") or []):
            rtype = rule.get("rule_type")
            if rtype == "action_tool_policy":
                # 액션 도구 정책 적용 (예: action 도구 이름 표준화)
                summary["action_policy_rule_count"] += 1
            elif rtype == "argument_normalization":
                # 인수 이름/값 형식 보정 (예: 대소문자, 단어 구분자 통일)
                summary["argument_normalization_rule_count"] += 1
            elif rtype == "argument_removed":
                # 불필요하거나 허용되지 않은 인수 제거
                summary["argument_removed_rule_count"] += 1
            elif rtype == "deduplicate":
                # 중복 도구 항목 제거
                summary["dedup_rule_count"] += 1

        # ── issue 집계는 최종 채택된 validation 기준 ────────────────────────
        # repair 성공 여부와 무관하게 "최종 판정" 기준의 이슈만 셈
        # (initial 이슈를 셈하면 repair 된 케이스를 불공정하게 불이익)
        final_issues = state.get("final_issues", []) or []
        for issue in final_issues:
            itype = issue.get("type")
            if itype == "json_parse_error":
                # LLM 이 JSON 형식을 벗어난 응답을 생성 → 파싱 실패
                summary["json_parse_error_count"] += 1
            elif itype == "missing_tool":
                # 정답에 있는 도구가 tool plan 에 없음
                summary["missing_tool_count"] += 1
            elif itype == "extra_tool":
                # 정답에 없는 도구가 tool plan 에 추가됨
                summary["extra_tool_count"] += 1
            elif itype == "missing_argument":
                # 필수 인수가 tool plan 에 없음
                summary["missing_argument_count"] += 1
            elif itype == "wrong_argument_name":
                # 인수 이름이 contract 와 다름
                summary["wrong_argument_name_count"] += 1
            elif itype == "missing_condition":
                # condition 필드가 없거나 비어 있음
                summary["missing_condition_count"] += 1
            elif itype == "weak_reason":
                # reason 필드가 부실하거나 기본 문구에 그침
                summary["weak_reason_count"] += 1
            elif itype == "tool_contract_mismatch":
                # 도구 사용 방식이 contract 정의와 불일치
                summary["tool_contract_mismatch_count"] += 1

        # ── LLM / fallback / repair 케이스 단위 집계 ────────────────────────
        if state.get("llm_used"):
            # LLM 호출이 한 번이라도 성공한 케이스
            summary["llm_used_count"] += 1
        if state.get("fallback_used"):
            # fallback 이 한 번이라도 발동된 케이스
            # ⚠ 환경 요인(API 미설정 등) 포함 — LLM 품질 단독 지표 아님
            summary["fallback_count"] += 1
        if state.get("repair_attempted"):
            # repair 노드가 실행된 케이스
            summary["repair_attempt_count"] += 1
        if compute_repair_success(state):
            # repair 후 validation 등급이 실질적으로 개선된 케이스
            summary["repair_success_count"] += 1

    # ── fallback mode 및 세부 count (루프 완료 후 계산) ─────────────────────
    #  - fallback_count: fallback이 한 번이라도 사용된 "케이스" 수 (기존 의미 유지)
    #  - initial/repair_fallback_count: 단계별 fallback 발생 "이벤트" 수
    #  - llm_error_count / llm_unavailable_count: LLM 실패 "이벤트" 수
    #    (한 케이스에서 initial/repair 모두 실패하면 2로 집계될 수 있음)
    # 배치 전체의 fallback 정책 설정 — 첫 번째 state 에서 읽음
    summary["fallback_mode"] = states[0].get("fallback_mode", "rule") if states else "rule"
    # initial 단계에서 fallback 이 발동된 케이스 수 (케이스 단위)
    summary["initial_fallback_count"] = sum(
        1 for s in states if s.get("initial_fallback_used")
    )
    # repair 단계에서 fallback 이 발동된 케이스 수 (케이스 단위)
    summary["repair_fallback_count"] = sum(
        1 for s in states if s.get("repair_fallback_used")
    )

    # LLM 오류 / 서버 미접속 이벤트 수 집계 (이벤트 단위 — 케이스 단위 아님)
    # generation_source 와 repair_generation_source 를 모두 검사하므로
    # 한 케이스에서 initial+repair 모두 실패하면 2로 집계됨
    llm_error_count = 0
    llm_unavailable_count = 0
    for s in states:
        for src in (s.get("generation_source"), s.get("repair_generation_source")):
            if src in ("llm_error", "unknown_llm_error"):
                # LLM 호출은 됐지만 응답 처리 중 오류 발생
                llm_error_count += 1
            elif src == "unavailable":
                # LLM 서버 자체에 접속 불가 (API 키 미설정 / 네트워크 오류 등)
                llm_unavailable_count += 1
    summary["llm_error_count"] = llm_error_count
    summary["llm_unavailable_count"] = llm_unavailable_count

    return summary
