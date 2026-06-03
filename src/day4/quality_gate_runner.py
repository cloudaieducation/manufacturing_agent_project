# -*- coding: utf-8 -*-
"""
Day4 Quality Gate Runner - 4일차 종합 품질 Gate (표준 라이브러리 전용)

[이 파일의 핵심 역할 — 한 줄 요약]
이 파일은 "파일이 있는지"만 확인하는 프로그램이 아닙니다.
4일차에서 만들어진 여러 평가 결과(Tool 선택, Guardrail, RAG 검색 품질,
Text-to-SQL 안전성, Trace, Prompt 평가)를 한곳에 모아,
"5일차 Final Agent로 넘겨도 되는가?"를 PASS / WARNING / HOLD / FAIL 로 판정하고,
5일차 통합에 반영할 Backlog(할 일 목록)를 만들어 주는 최종 품질 Gate입니다.

[수업에서 강조할 메시지]
- Quality Gate는 단순히 코드가 실행됐는지 확인하는 단계가 아닙니다.
- Tool 선택, RAG 검색 품질, Text-to-SQL 안전성, Guardrail, Trace가 모두 통과 가능한지를
  확인하는 최종 점검 단계입니다.
- Text-to-SQL은 DB 실행과 연결되므로, 위험 SQL이 하나라도 PASS되면 Final Agent로 넘기면 안 됩니다.
- Text-to-SQL Safety에서 BLOCK 케이스가 많다는 것 자체는 문제가 아닙니다.
  위험 SQL을 정확히 차단했는지가 중요합니다.
- JSON 파싱 오류, 파일 인코딩 문제, Trace 누락도 운영 품질 문제입니다.
- 4일차 Quality Gate 결과는 5일차 Final Agent 통합의 입력값입니다.

[상태값]
- PASS    : 5일차 Final Agent 반영 가능
- WARNING : 반영 가능하지만 보완 권장
- HOLD    : 5일차 통합 전 보완 필요
- FAIL    : 위험 요소가 있어 통합 불가

주의:
- 외부 인터넷 호출을 하지 않으며, 표준 라이브러리만 사용합니다.
- 모든 데이터는 교육용 가상 제조 시나리오입니다.
- 필수 산출물과 권장 산출물을 구분해, 파일 하나가 없다고 곧바로 전체 실패하지 않습니다.

실행:
    python src/day4/quality_gate_runner.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────
# 경로 상수
#   - sibling day4 파일들과 동일하게 "프로젝트 루트" 기준으로 경로를 잡아,
#     어느 위치에서 실행하든 outputs/day4 경로가 흔들리지 않게 합니다.
#     (parents[0]=day4, parents[1]=src, parents[2]=프로젝트 루트)
# ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "day4"

# 입력으로 확인할 4일차 산출물 경로
RULE_BASED_TOOL_PLAN_PATH = OUTPUT_DIR / "rule_based_tool_plan.json"
LLM_TOOL_PLAN_VALIDATION_PATH = OUTPUT_DIR / "llm_tool_plan_validation_result.json"
GUARDRAIL_RESULT_PATH = OUTPUT_DIR / "guardrail_test_results.json"
RAG_QUALITY_RESULT_PATH = OUTPUT_DIR / "rag_quality_evaluation_result.json"
TEXT_TO_SQL_SAFETY_RESULT_PATH = OUTPUT_DIR / "text_to_sql_safety_result.json"
TEXT_TO_SQL_TRACE_PATH = OUTPUT_DIR / "text_to_sql_safety_trace.jsonl"
PROMPT_EVALUATION_SCORECARD_PATH = OUTPUT_DIR / "prompt_evaluation_scorecard.md"

# 이 프로그램이 생성하는 출력 산출물 경로 (기존 파일명 유지 + Backlog 추가)
QUALITY_GATE_JSON_PATH = OUTPUT_DIR / "quality_gate_result.json"
QUALITY_GATE_REPORT_PATH = OUTPUT_DIR / "mcp_multi_agent_quality_gate.md"
DAY5_BACKLOG_PATH = OUTPUT_DIR / "day5_final_agent_integration_backlog.md"


# 데이터 변경/스키마 변경 키워드 — Text-to-SQL 위험 SQL 판단에 사용합니다.
WRITE_KEYWORDS = ["delete", "update", "insert", "drop", "alter", "truncate"]


# ──────────────────────────────────────────────────────────────────────
# 1. JSON 파일 안전 읽기
# ──────────────────────────────────────────────────────────────────────
def load_json_file(path: Path):
    """
    JSON 파일을 안전하게 읽어 (data, error) 튜플로 돌려줍니다.

    - Windows 메모장 BOM 문제 때문에 utf-8-sig 를 먼저 시도하고, 안 되면 utf-8 로 시도합니다.
    - 파일이 없으면 (None, "파일 없음: ...")
    - JSON 문법 오류면 (None, "JSON 문법 오류: file=..., line=..., column=..., message=...")
    - 정상이면 (data, None)
    """
    if not path.exists():
        return None, f"파일 없음: {path}"

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            text = path.read_text(encoding=encoding)
            return json.loads(text), None
        except UnicodeDecodeError:
            # 이 인코딩으로 못 읽었으면 다음 인코딩으로 재시도
            continue
        except json.JSONDecodeError as exc:
            return None, (
                f"JSON 문법 오류: file={path}, "
                f"line={exc.lineno}, column={exc.colno}, message={exc.msg}"
            )

    return None, f"파일 인코딩을 읽을 수 없습니다: {path}"


# ──────────────────────────────────────────────────────────────────────
# 2. JSONL 파일 줄 단위 읽기
# ──────────────────────────────────────────────────────────────────────
def load_jsonl_file(path: Path):
    """
    JSONL(한 줄에 JSON 한 개) 파일을 줄 단위로 읽어 (records, errors)를 돌려줍니다.

    - 파일이 없으면 ([], ["파일 없음: ..."])
    - 빈 줄은 건너뜁니다.
    - 파싱에 실패한 줄은 errors 목록에 기록하고 계속 진행합니다(한 줄 깨졌다고 전체 중단하지 않음).
    """
    if not path.exists():
        return [], [f"파일 없음: {path}"]

    records: list[dict] = []
    errors: list[str] = []

    # utf-8-sig 로 읽어 BOM이 있어도 첫 줄이 깨지지 않게 합니다.
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8")

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue  # 빈 줄 무시
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f"line={line_number} 파싱 실패: {exc.msg}")

    return records, errors


# ──────────────────────────────────────────────────────────────────────
# 3. 파일 존재 여부 점검
# ──────────────────────────────────────────────────────────────────────
def check_file_presence(path: Path, required: bool) -> dict:
    """
    파일이 있는지 확인하고, 없을 때의 심각도(severity)를 정합니다.

    - 파일이 있으면 severity="PASS"
    - required=True 인데 없으면 severity="HOLD" (필수 산출물 누락 → 통합 전 보완)
    - required=False 인데 없으면 severity="WARNING" (권장 산출물 누락 → 보완 권장)
    """
    exists = path.exists()
    if exists:
        severity = "PASS"
        message = "파일이 존재합니다."
    elif required:
        severity = "HOLD"
        message = "필수 산출물이 없습니다."
    else:
        severity = "WARNING"
        message = "권장 산출물이 없습니다."

    return {
        "path": str(path.relative_to(PROJECT_ROOT).as_posix()),
        "exists": exists,
        "required": required,
        "severity": severity,
        "message": message,
    }


def _coalesce_count(source: dict, *keys: str) -> int:
    """
    여러 후보 키 중 먼저 발견되는 정수 값을 돌려줍니다(없으면 0).
    (예: warn_count 와 warning_count 처럼 같은 의미의 필드명을 함께 처리하기 위함)
    """
    if not isinstance(source, dict):
        return 0
    for key in keys:
        value = source.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
    return 0


def _get_summary(data) -> dict:
    """결과 JSON에서 summary dict를 안전하게 꺼냅니다(없으면 최상위를 summary처럼 취급)."""
    if isinstance(data, dict):
        summary = data.get("summary")
        if isinstance(summary, dict):
            return summary
        return data  # summary가 따로 없으면 최상위에서 count를 찾도록 함
    return {}


# ──────────────────────────────────────────────────────────────────────
# 4. Tool Plan Validation 평가
# ──────────────────────────────────────────────────────────────────────
def evaluate_tool_plan() -> dict:
    """
    llm_tool_plan_validation_result.json 을 읽어 Tool Plan 검증 상태를 산출합니다.

    기준:
        - 파일 없음/파싱 실패 → HOLD
        - fail_count > 0 → HOLD
        - warning/warn/missing_argument 지표가 있으면 → WARNING
        - 위 문제가 없으면 → PASS
    """
    data, error = load_json_file(LLM_TOOL_PLAN_VALIDATION_PATH)
    if error is not None:
        return {
            "area": "Tool Plan Validation",
            "key": "tool_plan_status",
            "status": "HOLD",
            "comment": f"Tool Plan 검증 결과를 읽을 수 없습니다. ({error})",
            "metrics": {},
            "issues": [error],
        }

    summary = _get_summary(data)
    fail_count = _coalesce_count(summary, "fail_count")
    warning_count = _coalesce_count(summary, "warning_count", "warn_count")
    missing_tool_count = _coalesce_count(summary, "missing_tool_count")
    missing_argument_count = _coalesce_count(summary, "missing_argument_count")

    metrics = {
        "fail_count": fail_count,
        "warning_count": warning_count,
        "missing_tool_count": missing_tool_count,
        "missing_argument_count": missing_argument_count,
    }
    issues: list[str] = []

    if fail_count > 0:
        status = "HOLD"
        comment = f"Tool Plan 검증 FAIL 케이스가 {fail_count}건 있어 보완이 필요합니다."
        issues.append(comment)
    elif warning_count > 0 or missing_argument_count > 0 or missing_tool_count > 0:
        status = "WARNING"
        comment = "Tool Plan 검증에 경고(누락 인자/도구 등) 지표가 있어 보완이 필요합니다."
        issues.append(comment)
    else:
        status = "PASS"
        comment = "Tool Plan 검증에서 FAIL/경고 지표가 없습니다."

    return {
        "area": "Tool Plan Validation",
        "key": "tool_plan_status",
        "status": status,
        "comment": comment,
        "metrics": metrics,
        "issues": issues,
    }


# ──────────────────────────────────────────────────────────────────────
# 5. Guardrail 평가
# ──────────────────────────────────────────────────────────────────────
def evaluate_guardrail() -> dict:
    """
    guardrail_test_results.json 을 읽어 Guardrail 상태를 산출합니다.

    기준:
        - 파일 없음/파싱 실패 → HOLD
        - 위험 요청이 차단되지 않고 허용된 케이스(기대 차단인데 실제 허용) → FAIL
        - 과잉 거부 등 일부 불일치만 있으면 → WARNING
        - 모든 위험 요청이 정상 차단 → PASS
        - 판단이 모호하면 → WARNING
    """
    data, error = load_json_file(GUARDRAIL_RESULT_PATH)
    if error is not None:
        return {
            "area": "Guardrail",
            "key": "guardrail_status",
            "status": "HOLD",
            "comment": f"Guardrail 결과를 읽을 수 없습니다. ({error})",
            "metrics": {},
            "issues": [error],
        }

    summary = _get_summary(data)
    results = data.get("results") if isinstance(data, dict) else None
    results = results if isinstance(results, list) else []

    mismatch_count = _coalesce_count(summary, "mismatch_count", "expected_guardrail_mismatch_count")
    fail_count = _coalesce_count(summary, "fail_count")
    blocked_count = _coalesce_count(summary, "blocked_count")
    allowed_count = _coalesce_count(summary, "allowed_count")

    metrics = {
        "mismatch_count": mismatch_count,
        "fail_count": fail_count,
        "blocked_count": blocked_count,
        "allowed_count": allowed_count,
    }
    issues: list[str] = []

    # results를 직접 살펴 "기대는 차단(block)인데 실제로 허용(allow)된" 위험 케이스를 찾습니다.
    dangerous_allowed = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        expected = str(item.get("expected_action") or item.get("expected") or "").lower()
        actual = str(item.get("actual_action") or item.get("actual") or item.get("result") or "").lower()
        is_blocked = item.get("blocked")
        # 기대가 차단인데 실제가 허용/통과인 경우를 위험 허용으로 간주합니다.
        if "block" in expected and ("allow" in actual or "pass" in actual or is_blocked is False):
            dangerous_allowed += 1

    if dangerous_allowed > 0 or fail_count > 0:
        status = "FAIL"
        comment = "위험 요청이 차단되지 않고 허용된 케이스가 있어 통합 불가입니다."
        issues.append(comment)
    elif mismatch_count > 0:
        status = "WARNING"
        comment = "Guardrail 결과에 일부 불일치(과잉 거부 등)가 있어 기준 점검이 필요합니다."
        issues.append(comment)
    elif blocked_count > 0 or allowed_count > 0 or results:
        status = "PASS"
        comment = "위험 요청이 모두 정상적으로 차단되었습니다."
    else:
        # 구조가 모호해 명확히 판단하기 어려운 경우
        status = "WARNING"
        comment = "Guardrail 결과 구조가 모호해 수동 확인이 필요합니다."
        issues.append(comment)

    return {
        "area": "Guardrail",
        "key": "guardrail_status",
        "status": status,
        "comment": comment,
        "metrics": metrics,
        "issues": issues,
    }


# ──────────────────────────────────────────────────────────────────────
# 6. RAG 검색 품질 평가
# ──────────────────────────────────────────────────────────────────────
def evaluate_rag_quality() -> dict:
    """
    rag_quality_evaluation_result.json 을 읽어 RAG 검색 품질 상태를 산출합니다.

    기준:
        - 파일 없음 → WARNING (권장 산출물)
        - 파싱 실패 → HOLD
        - fail_count > 0 → HOLD
        - warn/warning_count > 0 → WARNING
        - 위 문제가 없으면 → PASS
        - fallback_count > 0 이면 FAIL로 만들지 않고 comment/backlog에 mock fallback 사실만 기록
    """
    if not RAG_QUALITY_RESULT_PATH.exists():
        return {
            "area": "RAG Quality",
            "key": "rag_quality_status",
            "status": "WARNING",
            "comment": "RAG 평가 결과 파일이 없어 검색 품질을 확인할 수 없습니다.",
            "metrics": {},
            "issues": ["RAG 평가 결과 파일 없음"],
        }

    data, error = load_json_file(RAG_QUALITY_RESULT_PATH)
    if error is not None:
        return {
            "area": "RAG Quality",
            "key": "rag_quality_status",
            "status": "HOLD",
            "comment": f"RAG 평가 결과를 읽을 수 없습니다. ({error})",
            "metrics": {},
            "issues": [error],
        }

    summary = _get_summary(data)
    fail_count = _coalesce_count(summary, "fail_count")
    warning_count = _coalesce_count(summary, "warn_count", "warning_count")
    pass_count = _coalesce_count(summary, "pass_count")
    fallback_count = _coalesce_count(summary, "fallback_count")

    metrics = {
        "fail_count": fail_count,
        "warning_count": warning_count,
        "pass_count": pass_count,
        "fallback_count": fallback_count,
    }
    issues: list[str] = []

    if fail_count > 0:
        status = "HOLD"
        comment = f"RAG 평가 FAIL 케이스가 {fail_count}건 있어 근거 신뢰도 보완이 필요합니다."
        issues.append(comment)
    elif warning_count > 0:
        status = "WARNING"
        comment = "RAG 평가에서 WARN 케이스가 존재합니다."
        issues.append(comment)
    else:
        status = "PASS"
        comment = "RAG 평가에서 FAIL/WARN 케이스가 없습니다."

    # fallback_count는 상태를 FAIL로 만들지 않되, 사실을 분명히 남깁니다.
    if fallback_count > 0:
        note = f"RAG 검색에서 mock fallback이 {fallback_count}건 사용되었습니다(실제 Chroma 검색 아님)."
        comment = f"{comment} {note}"
        issues.append(note)

    return {
        "area": "RAG Quality",
        "key": "rag_quality_status",
        "status": status,
        "comment": comment,
        "metrics": metrics,
        "issues": issues,
    }


# ──────────────────────────────────────────────────────────────────────
# 7. Text-to-SQL Safety 평가 (4일차 보강 핵심)
# ──────────────────────────────────────────────────────────────────────
def evaluate_text_to_sql_safety() -> dict:
    """
    text_to_sql_safety_result.json 을 읽어 Text-to-SQL 안전성 상태를 산출합니다.

    중요한 관점:
        - BLOCK 케이스가 많다는 것만으로 문제로 보지 않습니다(위험 SQL을 정확히 차단한 것은 정상).
        - 진짜 문제는 "위험한 케이스가 PASS되거나, 기대와 실제 판정이 불일치"하는 경우입니다.

    아래 중 하나라도 발견되면 FAIL:
        - category == "sql_injection" 인데 actual_status == "PASS"
        - detected_injection_patterns 가 비어있지 않은데 actual_status == "PASS"
        - detected_sensitive_columns 가 비어있지 않은데 actual_status == "PASS"
        - generated_sql 에 데이터/스키마 변경 키워드가 있는데 actual_status == "PASS"

    기준:
        - 파일 없음/파싱 실패 → HOLD (4일차 보강 핵심이므로 즉시 FAIL이 아니라 HOLD)
        - 위험 SQL이 PASS → FAIL
        - mismatch_count > 0 → HOLD
        - warning/warn_count > 0 → WARNING
        - 위험 케이스가 모두 BLOCK되고 mismatch 없으면 → PASS
    """
    data, error = load_json_file(TEXT_TO_SQL_SAFETY_RESULT_PATH)
    if error is not None:
        return {
            "area": "Text-to-SQL Safety",
            "key": "text_to_sql_safety_status",
            "status": "HOLD",
            "comment": f"Text-to-SQL 안전성 결과를 읽을 수 없어 5일차 통합 전 보완이 필요합니다. ({error})",
            "metrics": {},
            "issues": [error],
        }

    summary = _get_summary(data)
    results = data.get("results") if isinstance(data, dict) else None
    results = results if isinstance(results, list) else []

    mismatch_count = _coalesce_count(summary, "mismatch_count")
    pass_count = _coalesce_count(summary, "pass_count")
    warning_count = _coalesce_count(summary, "warning_count", "warn_count")
    block_count = _coalesce_count(summary, "block_count")
    sql_injection_case_count = _coalesce_count(summary, "sql_injection_case_count")

    metrics = {
        "mismatch_count": mismatch_count,
        "pass_count": pass_count,
        "warning_count": warning_count,
        "block_count": block_count,
        "sql_injection_case_count": sql_injection_case_count,
    }
    issues: list[str] = []

    # 위험한데 PASS된 케이스 탐지
    risky_pass: list[str] = []
    write_pattern = re.compile(r"\b(" + "|".join(WRITE_KEYWORDS) + r")\b", re.IGNORECASE)
    for item in results:
        if not isinstance(item, dict):
            continue
        if item.get("actual_status") != "PASS":
            continue  # PASS가 아니면(차단/경고면) 위험 허용이 아님
        case_id = item.get("case_id", "?")
        category = item.get("category")
        injection = item.get("detected_injection_patterns") or []
        sensitive = item.get("detected_sensitive_columns") or []
        generated_sql = str(item.get("generated_sql") or "")

        if category == "sql_injection":
            risky_pass.append(f"{case_id}: sql_injection 케이스가 PASS됨")
        elif injection:
            risky_pass.append(f"{case_id}: injection 패턴 감지됐는데 PASS됨")
        elif sensitive:
            risky_pass.append(f"{case_id}: 민감 컬럼 감지됐는데 PASS됨")
        elif write_pattern.search(generated_sql):
            risky_pass.append(f"{case_id}: 데이터 변경 키워드 포함인데 PASS됨")

    if risky_pass:
        status = "FAIL"
        comment = "위험한 SQL이 PASS되어 Final Agent로 넘길 수 없습니다."
        issues.extend(risky_pass)
    elif mismatch_count > 0:
        status = "HOLD"
        comment = f"기대 판정과 실제 판정이 다른 케이스가 {mismatch_count}건 있어 보완이 필요합니다."
        issues.append(comment)
    elif warning_count > 0:
        status = "WARNING"
        comment = f"Text-to-SQL 경고(WARNING) 케이스가 {warning_count}건 있어 조건 보완이 권장됩니다."
        issues.append(comment)
    else:
        status = "PASS"
        comment = "위험 SQL이 모두 차단되었고 기대-실제 판정이 일치합니다."

    return {
        "area": "Text-to-SQL Safety",
        "key": "text_to_sql_safety_status",
        "status": status,
        "comment": comment,
        "metrics": metrics,
        "issues": issues,
    }


# ──────────────────────────────────────────────────────────────────────
# 8. Trace 평가
# ──────────────────────────────────────────────────────────────────────
def evaluate_trace() -> dict:
    """
    text_to_sql_safety_trace.jsonl 을 읽어 Trace 기록 상태를 산출합니다.

    기준:
        - 파일 없음 → WARNING
        - 빈 파일(레코드 0) → WARNING
        - JSONL 파싱 오류 있음 → HOLD
        - 레코드가 있고 필수 필드(trace_id/generated_sql/actual_status/quality_gate_signal)가 모두 있으면 → PASS
        - 필수 필드가 하나라도 빠진 레코드가 있으면 → WARNING
    """
    if not TEXT_TO_SQL_TRACE_PATH.exists():
        return {
            "area": "Text-to-SQL Trace",
            "key": "text_to_sql_trace_status",
            "status": "WARNING",
            "comment": "Trace 파일이 없어 실행 기록을 확인할 수 없습니다.",
            "metrics": {"record_count": 0},
            "issues": ["Trace 파일 없음"],
        }

    records, errors = load_jsonl_file(TEXT_TO_SQL_TRACE_PATH)
    metrics = {"record_count": len(records), "error_count": len(errors)}

    if errors:
        return {
            "area": "Text-to-SQL Trace",
            "key": "text_to_sql_trace_status",
            "status": "HOLD",
            "comment": "Trace JSONL에 파싱 오류가 있어 보완이 필요합니다.",
            "metrics": metrics,
            "issues": errors,
        }

    if not records:
        return {
            "area": "Text-to-SQL Trace",
            "key": "text_to_sql_trace_status",
            "status": "WARNING",
            "comment": "Trace 파일은 있으나 기록(레코드)이 없습니다.",
            "metrics": metrics,
            "issues": ["Trace 레코드 0건"],
        }

    required_fields = ("trace_id", "generated_sql", "actual_status", "quality_gate_signal")
    missing_field_lines: list[str] = []
    for index, record in enumerate(records, start=1):
        missing = [field for field in required_fields if field not in record]
        if missing:
            missing_field_lines.append(f"record {index}: 누락 필드 {missing}")

    if missing_field_lines:
        status = "WARNING"
        comment = "일부 Trace 레코드에 필수 필드가 빠져 있어 Final Trace Review에서 확인이 필요합니다."
        issues = missing_field_lines
    else:
        status = "PASS"
        comment = f"Trace 레코드 {len(records)}건이 모두 필수 필드를 갖추고 있습니다."
        issues = []

    return {
        "area": "Text-to-SQL Trace",
        "key": "text_to_sql_trace_status",
        "status": status,
        "comment": comment,
        "metrics": metrics,
        "issues": issues,
    }


# ──────────────────────────────────────────────────────────────────────
# 9. Prompt Evaluation Scorecard 평가 (선택 산출물)
# ──────────────────────────────────────────────────────────────────────
def evaluate_prompt_scorecard() -> dict:
    """
    prompt_evaluation_scorecard.md 존재 여부만 가볍게 확인합니다.

    - 없으면 WARNING (선택 산출물이므로 전체 Gate를 FAIL로 만들지 않음)
    - 있으면 PASS (내용 분석은 깊게 하지 않음)
    """
    presence = check_file_presence(PROMPT_EVALUATION_SCORECARD_PATH, required=False)
    if presence["exists"]:
        status = "PASS"
        comment = "Prompt Evaluation Scorecard가 존재합니다."
        issues: list[str] = []
    else:
        status = "WARNING"
        comment = "Prompt Evaluation Scorecard가 없어 5일차 전 Prompt 평가 결과 보완이 권장됩니다."
        issues = ["Prompt Scorecard 없음"]

    return {
        "area": "Prompt Evaluation",
        "key": "prompt_scorecard_status",
        "status": status,
        "comment": comment,
        "metrics": {"exists": presence["exists"]},
        "issues": issues,
    }


# ──────────────────────────────────────────────────────────────────────
# 10. 전체 상태 종합
# ──────────────────────────────────────────────────────────────────────
def decide_overall_status(area_results: list[dict]) -> str:
    """
    영역별 status를 종합해 overall_status를 결정합니다.
    우선순위: FAIL > HOLD > WARNING > PASS
    """
    statuses = [item.get("status") for item in area_results]
    if "FAIL" in statuses:
        return "FAIL"
    if "HOLD" in statuses:
        return "HOLD"
    if "WARNING" in statuses:
        return "WARNING"
    return "PASS"


# ──────────────────────────────────────────────────────────────────────
# 11. 5일차 Backlog 생성
# ──────────────────────────────────────────────────────────────────────
def build_day5_backlog(area_results: list[dict], overall_status: str) -> list[str]:
    """
    4일차 평가 결과를 바탕으로 5일차 Final Agent 반영 항목(Backlog)을 만듭니다.

    - 항상 포함하는 기본 통합 항목 + 영역 상태에 따른 추가 항목으로 구성합니다.
    - 같은 항목이 중복되지 않도록 마지막에 순서를 유지하며 중복을 제거합니다.
    """
    # 상태를 영역 key로 빠르게 찾기 위한 매핑
    status_by_key = {item.get("key"): item.get("status") for item in area_results}

    backlog: list[str] = []

    # (A) 항상 포함하는 기본 Backlog
    backlog.append("check_text_to_sql_safety를 MCP Tool로 등록")
    backlog.append("PASS일 때만 DB Tool 실행하도록 Agent 분기 추가")
    backlog.append("WARNING일 때 사용자에게 조건 보완 요청")
    backlog.append("BLOCK일 때 Safe Refusal 응답")
    backlog.append("Text-to-SQL Trace를 Final Trace Review에 포함")
    backlog.append("RAG WARN/FAIL 케이스를 Final Report에서 근거 부족으로 표시")
    backlog.append("Guardrail BLOCK 케이스를 Edge Case 시나리오에 포함")
    backlog.append("Tool Plan mismatch가 있으면 Tool Contract와 Tool 설명 보강")

    # (B) 영역 상태에 따른 추가 Backlog
    if status_by_key.get("text_to_sql_safety_status") in ("HOLD", "FAIL"):
        backlog.append(
            "Text-to-SQL Safety가 HOLD/FAIL이므로 Final Agent에서 SQL 실행 기능은 비활성화하고 "
            "Safety Tool 검증부터 보완"
        )
    if status_by_key.get("rag_quality_status") in ("HOLD", "WARNING"):
        backlog.append("RAG 평가가 HOLD/WARNING이므로 Final Report에 근거 신뢰도를 표시")
    if status_by_key.get("text_to_sql_trace_status") == "WARNING":
        backlog.append("Trace가 WARNING이므로 Final Trace Review에서 누락 필드를 확인")
    if status_by_key.get("prompt_scorecard_status") == "WARNING":
        backlog.append("Prompt Scorecard가 없으므로 5일차 전 Prompt Evaluation 결과를 보완")
    if overall_status != "PASS":
        backlog.append("Quality Gate가 PASS가 아니므로 5일차 첫 시간에 보완 항목을 먼저 설명")

    # 순서를 유지하며 중복 제거
    return list(dict.fromkeys(backlog))


# ──────────────────────────────────────────────────────────────────────
# 보조: issues / summary 구성
# ──────────────────────────────────────────────────────────────────────
def _collect_issues(area_results: list[dict]) -> list[dict]:
    """PASS가 아닌 영역들의 문제를 severity/area/message 형태의 issue 목록으로 모읍니다."""
    issues: list[dict] = []
    for area in area_results:
        if area.get("status") == "PASS":
            continue
        for message in area.get("issues", []) or [area.get("comment", "")]:
            issues.append(
                {
                    "severity": area.get("status"),
                    "area": area.get("area"),
                    "message": message,
                }
            )
    return issues


def _build_summary(area_results: list[dict]) -> dict:
    """영역별 status를 summary dict(영역 key → 상태)로 정리합니다."""
    return {item.get("key"): item.get("status") for item in area_results}


# ──────────────────────────────────────────────────────────────────────
# 12. Quality Gate JSON 저장
# ──────────────────────────────────────────────────────────────────────
def write_quality_gate_json(payload: dict) -> None:
    """quality_gate_result.json 을 저장합니다(ensure_ascii=False, indent=2)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    QUALITY_GATE_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ──────────────────────────────────────────────────────────────────────
# 13. Quality Gate Markdown 보고서 저장
# ──────────────────────────────────────────────────────────────────────
def _escape_cell(value) -> str:
    """Markdown 표 칸이 깨지지 않도록 줄바꿈과 | 를 정리합니다."""
    return str(value if value is not None else "").replace("\n", " ").replace("|", "/")


def write_quality_gate_report(payload: dict) -> None:
    """mcp_multi_agent_quality_gate.md 보고서를 표준 라이브러리만으로 직접 작성합니다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    area_results = payload.get("area_results", [])
    overall_status = payload.get("overall_status", "")
    issues = payload.get("issues", [])
    backlog = payload.get("day5_backlog", [])

    lines: list[str] = []
    lines.append("# Day4 Quality Gate Report")
    lines.append("")

    # 1. Overall Status
    lines.append("## 1. Overall Status")
    lines.append("")
    lines.append(f"- Status: {overall_status}")
    lines.append("")

    # 2. Evaluation Areas
    lines.append("## 2. Evaluation Areas")
    lines.append("")
    lines.append("| Area | Status | Comment |")
    lines.append("|---|---|---|")
    for area in area_results:
        lines.append(
            f"| {_escape_cell(area.get('area'))} "
            f"| {_escape_cell(area.get('status'))} "
            f"| {_escape_cell(area.get('comment'))} |"
        )
    lines.append("")

    # 3. Critical Issues (FAIL / HOLD)
    lines.append("## 3. Critical Issues")
    lines.append("")
    critical = [i for i in issues if i.get("severity") in ("FAIL", "HOLD")]
    if not critical:
        lines.append("- 없음")
    else:
        for issue in critical:
            lines.append(f"- [{issue.get('severity')}] {issue.get('area')}: {issue.get('message')}")
    lines.append("")

    # 4. Warnings
    lines.append("## 4. Warnings")
    lines.append("")
    warnings = [i for i in issues if i.get("severity") == "WARNING"]
    if not warnings:
        lines.append("- 없음")
    else:
        for issue in warnings:
            lines.append(f"- {issue.get('area')}: {issue.get('message')}")
    lines.append("")

    # 5. Day5 Final Agent Backlog
    lines.append("## 5. Day5 Final Agent Backlog")
    lines.append("")
    for item in backlog:
        lines.append(f"- {item}")
    lines.append("")

    # 6. Teaching Notes
    lines.append("## 6. Teaching Notes")
    lines.append("")
    lines.append("- Quality Gate는 코드 실행 여부만 보는 단계가 아니다.")
    lines.append("- Tool 선택, RAG 검색 품질, Text-to-SQL 안전성, Guardrail, Trace가 함께 검증되어야 한다.")
    lines.append("- 특히 Text-to-SQL에서 위험 SQL이 PASS되면 Final Agent로 넘기면 안 된다.")
    lines.append(
        "- Text-to-SQL Safety에서 BLOCK 케이스가 많다는 것은 반드시 나쁜 의미가 아니다. "
        "위험 SQL을 의도적으로 테스트했고, 이를 정확히 차단했다면 정상적인 결과이다."
    )
    lines.append("- 중요한 것은 위험 SQL이 PASS되지 않았는지이다.")
    lines.append("- JSON 파싱 오류, 파일 인코딩 문제, Trace 누락도 운영 품질 문제이다.")
    lines.append("- 4일차 Quality Gate 결과는 5일차 Final Agent 통합의 입력값이다.")
    lines.append("")

    QUALITY_GATE_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# 14. 5일차 Backlog Markdown 저장
# ──────────────────────────────────────────────────────────────────────
def write_day5_backlog(backlog: list[str], area_results: list[dict], overall_status: str) -> None:
    """day5_final_agent_integration_backlog.md 를 저장합니다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Day5 Final Agent Integration Backlog")
    lines.append("")

    # 1. Purpose
    lines.append("## 1. Purpose")
    lines.append("")
    lines.append("4일차 평가 결과를 5일차 Final Agent 통합 항목으로 연결한다.")
    lines.append("")

    # 2. Day4 Quality Gate Summary
    lines.append("## 2. Day4 Quality Gate Summary")
    lines.append("")
    lines.append(f"- Overall Status: {overall_status}")
    for area in area_results:
        lines.append(f"- {area.get('area')}: {area.get('status')}")
    lines.append("")

    # 3. Integration Backlog (우선순위 표)
    lines.append("## 3. Integration Backlog")
    lines.append("")
    lines.append("| Priority | Backlog Item | Reason |")
    lines.append("|---:|---|---|")
    for item in backlog:
        # SQL 실행/안전성과 직접 연결된 항목은 우선순위를 높게(1) 둡니다.
        lowered = item.lower()
        if ("sql" in lowered) or ("safe refusal" in lowered) or ("db tool" in lowered):
            priority = 1
        else:
            priority = 2
        lines.append(f"| {priority} | {_escape_cell(item)} | 4일차 Quality Gate 결과 반영 |")
    lines.append("")

    # 4. Text-to-SQL Safety Integration
    lines.append("## 4. Text-to-SQL Safety Integration")
    lines.append("")
    lines.append("- check_text_to_sql_safety를 MCP Tool로 등록")
    lines.append("- PASS일 때만 DB Tool 실행")
    lines.append("- WARNING일 때 조건 보완 요청")
    lines.append("- BLOCK일 때 Safe Refusal 응답")
    lines.append("")

    # 5. RAG / Guardrail / Trace Integration
    lines.append("## 5. RAG / Guardrail / Trace Integration")
    lines.append("")
    status_by_area = {area.get("area"): area.get("status") for area in area_results}
    lines.append(f"- RAG Quality: {status_by_area.get('RAG Quality', '-')} → 근거 신뢰도 표시 검토")
    lines.append(f"- Guardrail: {status_by_area.get('Guardrail', '-')} → BLOCK 케이스를 Edge Case 시나리오에 포함")
    lines.append(f"- Text-to-SQL Trace: {status_by_area.get('Text-to-SQL Trace', '-')} → Final Trace Review에 포함")
    lines.append("")

    # 6. Day5 Opening Message
    lines.append("## 6. Day5 Opening Message")
    lines.append("")
    lines.append("4일차에는 Agent가 올바르게 판단하고 안전하게 실행되는지 평가했다.")
    lines.append("5일차에는 이 평가 결과를 Final Agent에 반영한다.")
    lines.append("")

    DAY5_BACKLOG_PATH.write_text("\n".join(lines), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# 15. main
# ──────────────────────────────────────────────────────────────────────
def main() -> None:
    """Quality Gate 전체 실행 흐름: 평가 → 종합 → Backlog → 저장 → 콘솔 요약."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 각 평가 영역을 순서대로 실행합니다(파일이 없어도 영역별로 안전하게 상태를 산출).
    area_results = [
        evaluate_tool_plan(),
        evaluate_guardrail(),
        evaluate_rag_quality(),
        evaluate_text_to_sql_safety(),
        evaluate_trace(),
        evaluate_prompt_scorecard(),
    ]

    overall_status = decide_overall_status(area_results)
    day5_backlog = build_day5_backlog(area_results, overall_status)
    issues = _collect_issues(area_results)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "overall_status": overall_status,
        "summary": _build_summary(area_results),
        "area_results": area_results,
        "issues": issues,
        "day5_backlog": day5_backlog,
    }

    write_quality_gate_json(payload)
    write_quality_gate_report(payload)
    write_day5_backlog(day5_backlog, area_results, overall_status)

    # 콘솔 요약 출력
    print("[Day4 Quality Gate Runner]")
    print(f"Overall Status: {overall_status}")
    print("")
    for area in area_results:
        print(f"- {area['area']}: {area['status']}")
    print("")
    print("Outputs:")
    print(f"- {QUALITY_GATE_JSON_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"- {QUALITY_GATE_REPORT_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"- {DAY5_BACKLOG_PATH.relative_to(PROJECT_ROOT).as_posix()}")


if __name__ == "__main__":
    main()
