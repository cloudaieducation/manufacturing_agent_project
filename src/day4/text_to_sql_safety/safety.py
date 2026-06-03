# -*- coding: utf-8 -*-
"""
Day4 Text-to-SQL Safety 판정 모듈

생성된 SQL 문자열과 사용자 자연어 의도의 안전성을 rule 기반으로 판정하는 함수들을 모은 모듈입니다.
text_to_sql_safety_checker.py(진입점)에서 import해 사용합니다.

[이 모듈이 담당하는 것]
- SQL 정규화 / 테이블 추출 helper (_normalize_sql, _detect_tables)
- 생성 SQL 안전성 검사 (check_sql_safety) → PASS / WARNING / BLOCK
- MCP/Agent 통합용 wrapper (check_text_to_sql_safety)
- 사용자 의도(자연어) 안전성 검사 (check_user_intent_safety)
- 의도+SQL 판정 병합 (merge_intent_and_sql_safety)
- intent BLOCK으로 SQL 검사를 생략했음을 나타내는 결과 (_skipped_sql_safety)

[이 모듈이 담당하지 않는 것]
- mock SQL 생성 / LLM 호출 / trace 기록 / report 생성 / CLI 실행 (checker.py가 담당)

[의존성]
- 표준 라이브러리: re
- src.day4.text_to_sql_safety.policies 의 정책 상수
- checker.py를 import하지 않습니다(순환 import 방지). 의존 방향: safety -> policies.

판정 기준·문자열 메시지·반환 dict 구조는 기존 checker.py와 1글자도 다르지 않게 유지합니다.
"""
import re

from src.day4.text_to_sql_safety.policies import (
    ALLOWED_TABLES,
    SENSITIVE_COLUMNS,
    BLOCKED_KEYWORDS,
    SQL_INJECTION_PATTERNS,
    INTENT_DELETE_KEYWORDS,
    INTENT_UPDATE_KEYWORDS,
    INTENT_INSERT_KEYWORDS,
    INTENT_SCHEMA_KEYWORDS,
    INTENT_DB_STRUCTURE_KEYWORDS,
    INTENT_SENSITIVE_KEYWORDS,
    INTENT_INJECTION_KEYWORDS,
    INTENT_REAL_INTERNAL_KEYWORDS,
    INTENT_OVER_QUERY_BLOCK_KEYWORDS,
    INTENT_BROAD_QUERY_WARN_KEYWORDS,
)


# ──────────────────────────────────────────────────────────────────────
# 4. 핵심 함수: SQL 안전성 검사
# ──────────────────────────────────────────────────────────────────────
def _normalize_sql(sql: str) -> str:
    """SQL을 비교/검사하기 쉽게 정규화합니다. (공백 1칸으로 축약 + 소문자)"""
    return re.sub(r"\s+", " ", (sql or "").strip()).lower()


def _detect_tables(normalized_sql: str) -> list[str]:
    """FROM / JOIN / INTO / UPDATE 뒤에 오는 테이블 이름을 추출합니다(중복 제거)."""
    found = re.findall(r"\b(?:from|join|into|update)\s+([a-z_][\w\.]*)", normalized_sql)
    tables: list[str] = []
    for table in found:
        if table not in tables:
            tables.append(table)
    return tables


def check_sql_safety(sql: str) -> dict:
    """
    SQL 한 개를 검사해 PASS / WARNING / BLOCK 으로 판정합니다. (이 파일의 핵심 함수)

    검사 순서:
        1) SQL 정규화
        2) SELECT 문 여부
        3) 차단 키워드(DELETE/UPDATE/INSERT/DROP/ALTER/TRUNCATE/CREATE)
        4) SQL Injection 의심 패턴
        5) 허용 테이블 여부
        6) 민감 컬럼 포함 여부
        7) SELECT * 여부
        8) WHERE 포함 여부
        9) LIMIT 포함 여부
        10) 최종 상태 판정

    판정 규칙:
        - BLOCK : Injection 패턴 / SELECT 아님 / 차단 키워드 / 허용되지 않은 테이블 / 민감 컬럼
        - WARNING: (읽기 전용이지만) SELECT * / WHERE 없음 / LIMIT 없음
        - PASS  : 위 위반이 없고 WHERE·LIMIT 포함, SELECT * 미사용, 허용 테이블만 사용

    반환 dict:
        actual_status, reasons, warnings, blocked_reasons,
        detected_tables, detected_sensitive_columns, detected_injection_patterns, normalized_sql
    """
    normalized = _normalize_sql(sql)

    blocked_reasons: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    # 2) SELECT 문인지 확인
    # 교육용 단순 정책:
    # 4일차 실습에서는 SELECT로 시작하는 단순 조회만 PASS 후보로 봅니다.
    # WITH로 시작하는 CTE 쿼리는 실제로 읽기 전용일 수 있지만,
    # 교육용 안전성 검증에서는 우선 BLOCK 또는 보완 대상으로 둡니다.
    # WITH 허용이 필요하면 별도 정책으로 확장할 수 있습니다.
    # (참고: _extract_sql_from_text는 위험 SQL 보존을 위해 WITH도 '추출'하지만,
    #  여기 판정에서는 WITH를 PASS 후보로 보지 않습니다 — 추출과 판정의 책임이 다릅니다.)
    is_select = normalized.startswith("select")
    if not is_select:
        blocked_reasons.append("SELECT 문이 아니므로 읽기 전용 정책에 위반됩니다.")

    # 3) 차단 키워드 확인 (단어 경계로 검사)
    for keyword in BLOCKED_KEYWORDS:
        if re.search(rf"\b{keyword}\b", normalized):
            blocked_reasons.append(f"차단 대상 SQL 키워드가 포함되어 있습니다: {keyword.upper()}")

    # 4) SQL Injection 의심 패턴 확인
    detected_injection_patterns: list[str] = []
    for name, pattern in SQL_INJECTION_PATTERNS.items():
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            detected_injection_patterns.append(name)
            blocked_reasons.append(f"SQL Injection 의심 패턴이 포함되어 있습니다: {name}")

    # 5) 허용 테이블 확인
    detected_tables = _detect_tables(normalized)
    for table in detected_tables:
        if table not in ALLOWED_TABLES:
            blocked_reasons.append(f"허용되지 않은 테이블에 접근합니다: {table}")

    # 6) 민감 컬럼 확인
    detected_sensitive_columns = [
        column for column in SENSITIVE_COLUMNS if re.search(rf"\b{column}\b", normalized)
    ]
    if detected_sensitive_columns:
        blocked_reasons.append(
            "민감 컬럼이 포함되어 있습니다: " + ", ".join(detected_sensitive_columns)
        )

    # 7~9) SELECT 문일 때만 범위/컬럼 관련 경고를 평가합니다.
    uses_select_star = False
    has_where = False
    has_limit = False
    if is_select:
        uses_select_star = bool(re.search(r"select\s+\*", normalized))
        has_where = bool(re.search(r"\bwhere\b", normalized))
        has_limit = bool(re.search(r"\blimit\b", normalized))

        if uses_select_star:
            warnings.append("SELECT * 를 사용해 불필요하거나 민감한 컬럼까지 노출될 수 있습니다.")
        if not has_where:
            warnings.append("WHERE 조건이 없어 조회 범위가 넓습니다.")
        if not has_limit:
            warnings.append("LIMIT이 없어 결과 건수가 과도하게 늘어날 수 있습니다.")

    # 10) 최종 상태 판정: BLOCK 우선 → WARNING → PASS
    if blocked_reasons:
        actual_status = "BLOCK"
    elif warnings:
        actual_status = "WARNING"
    else:
        actual_status = "PASS"
        # PASS일 때만 "왜 안전한지" 긍정 근거를 채워 둡니다.
        reasons.append("읽기 전용 SELECT 문입니다.")
        reasons.append("허용된 테이블을 사용했습니다.")
        reasons.append("WHERE 조건이 포함되어 있습니다.")
        reasons.append("LIMIT이 포함되어 있습니다.")

    return {
        "actual_status": actual_status,
        "reasons": reasons,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "detected_tables": detected_tables,
        "detected_sensitive_columns": detected_sensitive_columns,
        "detected_injection_patterns": detected_injection_patterns,
        "normalized_sql": normalized,
    }


# ──────────────────────────────────────────────────────────────────────
# MCP / Agent 통합용 wrapper 함수
# ──────────────────────────────────────────────────────────────────────
def check_text_to_sql_safety(
    generated_sql: str,
    user_query: str = "",
    generation_source: str = "llm",
) -> dict:
    """
    MCP Tool이나 Agent에서 import해 사용할 수 있는 안전성 검사 wrapper입니다.

    - 내부에서 check_sql_safety(generated_sql)만 호출합니다.
    - DB를 실행하지 않습니다. 오직 SQL 안전성 검사만 수행합니다.
    - 나중에 3일차 MCP 서버에 'check_text_to_sql_safety' Tool로 등록할 수 있도록
      입력/출력을 단순한 dict 형태로 유지합니다.

    Agent 분기 예시:
        PASS    → DB Tool 실행 가능
        WARNING → 사용자 확인 또는 조건 보완 요청
        BLOCK   → DB 실행 중단 및 안전 응답
    """
    safety = check_sql_safety(generated_sql)
    return {
        "user_query": user_query,
        "generated_sql": generated_sql,
        "generation_source": generation_source,
        "actual_status": safety["actual_status"],
        "reasons": safety["reasons"],
        "warnings": safety["warnings"],
        "blocked_reasons": safety["blocked_reasons"],
        "detected_tables": safety["detected_tables"],
        "detected_sensitive_columns": safety["detected_sensitive_columns"],
        "detected_injection_patterns": safety["detected_injection_patterns"],
        "normalized_sql": safety["normalized_sql"],
        "safety": safety,
    }


# ──────────────────────────────────────────────────────────────────────
# 4-1. Intent Safety: 사용자 질문(자연어) 자체의 위험 의도 검사 (LLM Batch 전용 보강)
#   - SQL은 안전해 보여도 사용자의 의도가 삭제/변경/민감정보 조회면 최종 판정은 BLOCK이어야 합니다.
#   - 예: "EQP-VD-03 상태를 정상으로 바꿔줘"는 UPDATE 의도이므로, LLM이 SELECT를 만들어도 BLOCK.
# ──────────────────────────────────────────────────────────────────────
def check_user_intent_safety(user_query: str) -> dict:
    """
    SQL을 생성하기 '전에' 사용자 질문 자체가 위험한 요청인지 판단합니다.

    [왜 필요한가]
    - check_sql_safety()는 생성된 SQL 문자열만 검사합니다.
    - 그러나 LLM이 위험한 사용자 의도(삭제/변경/민감정보)를 안전한 SELECT로 바꿔버리면
      SQL만으로는 PASS가 되어 기대 판정(BLOCK)과 어긋납니다.
    - 그래서 SQL 생성 전 '의도 게이트'로 사용자 질문을 먼저 검사합니다.

    [판정 기준 요약]
    - BLOCK : 삭제/수정/추가, 스키마 변경, DB 구조 조회, 개인정보/민감정보,
              SQL Injection 의심 표현, 실제 내부 정보 요청, 제한 없는 과도 조회
    - WARNING: 전체/모든/전부 같은 넓은 범위 조회(제한이 암시되는 넓은 조회)
    - PASS  : 특정 설비/라인/기간/품질 지표를 조회하는 읽기 전용 질문

    반환 dict:
        intent_status: PASS | WARNING | BLOCK
        intent_reasons / intent_warnings / intent_blocked_reasons: list[str]
        should_generate_sql: bool  (BLOCK이면 False → LLM 호출을 생략할 수 있음)
    """
    query = user_query or ""
    # 한글은 lower()의 영향을 받지 않고, 영문 키워드는 소문자 기준으로 검사하기 위해 한 번만 소문자화합니다.
    lowered = query.lower()

    blocked_reasons: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    def _found(keywords: list[str]) -> list[str]:
        """키워드(부분 문자열) 중 lowered 질문에 포함된 것을 돌려줍니다."""
        return [kw for kw in keywords if kw.lower() in lowered]

    # 1) BLOCK 의도 ──────────────────────────────────────────────
    if _found(INTENT_DELETE_KEYWORDS):
        blocked_reasons.append("사용자 요청에 데이터 삭제 의도가 포함되어 있습니다.")
    if _found(INTENT_UPDATE_KEYWORDS):
        blocked_reasons.append("사용자 요청에 데이터 변경(수정) 의도가 포함되어 있습니다.")
    if _found(INTENT_INSERT_KEYWORDS):
        blocked_reasons.append("사용자 요청에 데이터 추가(등록) 의도가 포함되어 있습니다.")
    if _found(INTENT_SCHEMA_KEYWORDS):
        blocked_reasons.append("사용자 요청에 테이블/스키마 변경·삭제 의도가 포함되어 있습니다.")
    if _found(INTENT_DB_STRUCTURE_KEYWORDS):
        blocked_reasons.append("사용자 요청에 DB 구조/시스템 테이블 조회 의도가 포함되어 있습니다.")
    sensitive_hits = _found(INTENT_SENSITIVE_KEYWORDS)
    if sensitive_hits:
        blocked_reasons.append(
            "사용자 요청에 개인정보/민감정보 조회 의도가 포함되어 있습니다: "
            + ", ".join(sensitive_hits)
        )
    if _found(INTENT_INJECTION_KEYWORDS):
        blocked_reasons.append("사용자 요청에 SQL Injection 의심 표현이 포함되어 있습니다.")
    if _found(INTENT_REAL_INTERNAL_KEYWORDS):
        blocked_reasons.append("사용자 요청에 실제 내부/사내 정보 요청 의도가 포함되어 있습니다.")
    if _found(INTENT_OVER_QUERY_BLOCK_KEYWORDS):
        blocked_reasons.append("사용자 요청에 범위 제한을 제거한 과도한 조회 의도가 포함되어 있습니다.")

    # 2) WARNING 의도 ────────────────────────────────────────────
    #    BLOCK이 아닌 경우에만, 전체/모든/전부 같은 넓은 조회를 WARNING으로 남깁니다.
    broad_hits = _found(INTENT_BROAD_QUERY_WARN_KEYWORDS)
    if broad_hits and not blocked_reasons:
        warnings.append(
            "전체/모든/전부 등 넓은 범위 조회 의도가 있어 조회 범위(WHERE/기간/LIMIT)를 좁히도록 유도해야 합니다."
        )

    # 3) 상태 판정: BLOCK 우선 → WARNING → PASS
    if blocked_reasons:
        intent_status = "BLOCK"
        should_generate_sql = False
    elif warnings:
        intent_status = "WARNING"
        should_generate_sql = True
    else:
        intent_status = "PASS"
        should_generate_sql = True
        reasons.append("특정 설비/라인/기간/지표를 조회하는 읽기 전용 의도로 보입니다.")

    return {
        "intent_status": intent_status,
        "intent_reasons": reasons,
        "intent_warnings": warnings,
        "intent_blocked_reasons": blocked_reasons,
        "should_generate_sql": should_generate_sql,
    }


def merge_intent_and_sql_safety(intent_safety: dict, sql_safety: dict) -> dict:
    """
    Intent Safety(의도 검사)와 SQL Safety(생성 SQL 검사)를 병합해 최종 판정을 만듭니다.

    [병합 규칙]
        intent_status == BLOCK  → final_status = BLOCK
        sql_status    == BLOCK  → final_status = BLOCK
        intent_status == WARNING 또는 sql_status == WARNING → final_status = WARNING
        둘 다 PASS → final_status = PASS

    - SQL 자체 판정은 반드시 sql_status로 별도 보존합니다(기존 호환).
    - sql_status는 기존 check_sql_safety() 반환의 actual_status에서 읽습니다.
    """
    intent_status = intent_safety.get("intent_status", "PASS")
    sql_status = sql_safety.get("actual_status", "PASS")

    intent_reasons = list(intent_safety.get("intent_reasons", []))
    intent_warnings = list(intent_safety.get("intent_warnings", []))
    intent_blocked_reasons = list(intent_safety.get("intent_blocked_reasons", []))

    sql_reasons = list(sql_safety.get("reasons", []))
    sql_warnings = list(sql_safety.get("warnings", []))
    sql_blocked_reasons = list(sql_safety.get("blocked_reasons", []))

    if intent_status == "BLOCK" or sql_status == "BLOCK":
        final_status = "BLOCK"
    elif intent_status == "WARNING" or sql_status == "WARNING":
        final_status = "WARNING"
    else:
        final_status = "PASS"

    return {
        "intent_status": intent_status,
        "sql_status": sql_status,
        "final_status": final_status,
        "intent_reasons": intent_reasons,
        "intent_warnings": intent_warnings,
        "intent_blocked_reasons": intent_blocked_reasons,
        "sql_reasons": sql_reasons,
        "sql_warnings": sql_warnings,
        "sql_blocked_reasons": sql_blocked_reasons,
        "final_reasons": intent_reasons + sql_reasons,
        "final_warnings": intent_warnings + sql_warnings,
        "final_blocked_reasons": intent_blocked_reasons + sql_blocked_reasons,
    }


def _skipped_sql_safety() -> dict:
    """
    intent 단계에서 BLOCK되어 'SQL 문장 검사를 생략'했음을 나타내는 안전성 결과를 만듭니다.

    [왜 필요한가]
    - 예전에는 intent_blocked 케이스에 placeholder SQL("/* ... */")을 넣고 check_sql_safety()로
      검사했는데, 이 주석이 sql_comment Injection 패턴으로 '오탐'되어 BLOCK 사유가 부자연스러웠습니다.
      (DELETE를 막은 진짜 이유는 의도(intent)인데, 보고서에는 sql_comment가 찍혔습니다.)
    - 그래서 SQL 생성을 생략한 경우에는 SQL 문장 검사 자체를 건너뛰고 진단 상태 "SKIPPED"를 둡니다.

    actual_status="SKIPPED": 실행 가능 상태가 아니라 'SQL 검사를 수행하지 않았다'는 진단 표시입니다.
    (병합 시 intent_status가 항상 BLOCK이므로 final_status는 BLOCK이 유지됩니다.)
    """
    return {
        "actual_status": "SKIPPED",
        "reasons": [],
        "warnings": [],
        "blocked_reasons": [],
        "detected_tables": [],
        "detected_sensitive_columns": [],
        "detected_injection_patterns": [],
        "normalized_sql": "",
    }
