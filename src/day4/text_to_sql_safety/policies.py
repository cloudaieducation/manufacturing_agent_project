# -*- coding: utf-8 -*-
"""
Day4 Text-to-SQL Safety 정책 상수 - 교육용

이 파일은 Safety Checker의 "규칙표"(정책 상수)만 모아 둔 순수 상수 모듈입니다.
text_to_sql_safety_checker.py가 import 해서 사용하며, 값/순서/주석을 그대로 옮겨
"무엇을 허용하고 무엇을 차단하는지"를 한곳에서 볼 수 있게 합니다.

(설계 원칙)
- 이 모듈은 다른 실행 모듈(checker/runners/safety/config 등)을 import 하지 않습니다.
  순환 import를 피하기 위해 '값만' 담는 순수 상수 모듈로 유지합니다.
"""


# ──────────────────────────────────────────────────────────────────────
# 안전성 정책 상수 — "무엇을 허용/차단할지"를 한곳에 모아 둡니다.
# (이 값들이 곧 Safety Checker의 규칙표이며, 수업에서 가장 먼저 설명할 부분입니다.)
# ──────────────────────────────────────────────────────────────────────
ALLOWED_TABLES = [
    "alarm_logs",
    "equipment_status",
    "quality_metrics",
    "maintenance_history",
]

SENSITIVE_COLUMNS = [
    "worker_name",
    "phone",
    "email",
    "employee_id",
    "resident_id",
    "account_id",
    "password",
    "token",
]

BLOCKED_KEYWORDS = [
    "delete",
    "update",
    "insert",
    "drop",
    "alter",
    "truncate",
    "create",
]

# SQL Injection 의심 패턴 (정규식). normalized_sql(소문자) 기준으로 검사합니다.
#   - 교육용 정규식 기반 검사입니다. 실제 운영에서는 이것만으로 충분하지 않습니다.
SQL_INJECTION_PATTERNS = {
    "multiple_statements": r";\s*(drop|delete|update|insert|alter|truncate|create)\b",
    "sql_comment": r"(--|/\*|\*/)",
    "always_true_or_1_eq_1": r"\bor\s+1\s*=\s*1\b",
    "always_true_string": r"'\s*or\s*'[^']+'\s*=\s*'[^']+'",
    "union_select": r"\bunion\s+select\b",
    "system_table_access": r"\b(information_schema|pg_catalog|sqlite_master|sysobjects)\b",
    "time_delay_function": r"\b(sleep|pg_sleep|benchmark)\s*\(",
}


# ──────────────────────────────────────────────────────────────────────
# Intent Safety 정책 상수 (LLM Batch 전용 보강)
#   - SQL 문자열이 아니라 "사용자 질문(자연어)" 자체의 위험 의도를 검사하기 위한 키워드표입니다.
#   - 한국어/영어 키워드를 함께 둡니다(영어는 소문자 기준으로 검사).
#   - 교육용이므로 복잡한 NLP 없이 키워드/부분 문자열 매칭만 사용합니다.
#   - 핵심 구분: '전체/모든/전부' 같은 넓은 조회는 WARNING, '제한 없이/무제한' 같은
#     제한 제거형 과도 조회는 BLOCK 으로 나눕니다.
# ──────────────────────────────────────────────────────────────────────
INTENT_DELETE_KEYWORDS = ["삭제", "지워", "제거", "delete"]
INTENT_UPDATE_KEYWORDS = ["수정", "바꿔", "변경", "정상으로 바꿔", "update"]
INTENT_INSERT_KEYWORDS = ["추가", "등록", "입력", "insert"]
INTENT_SCHEMA_KEYWORDS = ["테이블 삭제", "drop", "alter", "truncate", "create"]
INTENT_DB_STRUCTURE_KEYWORDS = [
    "db 구조", "디비 구조", "테이블 목록", "information_schema", "pg_catalog",
]
INTENT_SENSITIVE_KEYWORDS = [
    "작업자 이름", "담당자 이름", "연락처", "전화번호", "이메일", "사번",
    "비밀번호", "password", "token", "계정", "사용자 계정",
]
# SQL Injection 의심 자연어 표현. lowered(소문자) 기준 부분 문자열 매칭입니다.
#   - "느려도"는 Time-based Blind Injection을 유도하는 사회공학적 신호(응답이 느려도 괜찮다)로 봅니다.
INTENT_INJECTION_KEYWORDS = [
    "1'='1", "or '1'='1", "union", "--", "/*", "*/",
    "pg_sleep", "sleep", "benchmark", "주석", "느려도",
]
INTENT_REAL_INTERNAL_KEYWORDS = [
    "실제 내부", "실제 사내", "실제 라인명", "실제 설비명", "실제 수율",
]
# 범위 제한을 명시적으로 제거하는 과도한 조회 → BLOCK
INTENT_OVER_QUERY_BLOCK_KEYWORDS = [
    "제한 없이", "제한없이", "무제한", "전부 조회", "전체 조회",
    "전체 데이터", "모든 데이터", "모든 로그를 제한 없이", "limit 없이", "리밋 없이",
]
# 넓은 조회(특정 기간/최근/정렬/LIMIT 성격이 암시되는) → WARNING (무조건 BLOCK 아님)
INTENT_BROAD_QUERY_WARN_KEYWORDS = ["전체", "모든", "모두", "전부"]

# LLM SQL 생성 시 테이블별 허용 컬럼 (교육용 스키마 기준).
#   - LLM이 created_at/recorded_at/line_name/alarm_time 같은 임의 컬럼을 추측하지 못하게 합니다.
ALLOWED_COLUMNS_BY_TABLE = {
    "alarm_logs": ["equipment_id", "alarm_code", "occurred_at"],
    "equipment_status": ["equipment_id", "status_code", "updated_at"],
    "quality_metrics": ["line_id", "metric_name", "metric_value", "measured_at"],
    "maintenance_history": ["equipment_id", "action", "performed_at"],
}


# mock 전용: "전체 알람 로그"처럼 명확히 알람 도메인을 가리키는 표현 목록.
#   - 이 표현이 있으면 일반 "전체" demo 분기(SELECT * FROM equipment_status)보다
#     alarm_logs 알람 도메인 분기를 '우선' 적용하기 위해 사용합니다.
#   - (참고) 나열한 표현은 모두 "알람"을 포함하므로 실질적으로 "알람" 포함 여부와 같지만,
#     수업에서 의도를 분명히 보여 주기 위해 명시적으로 적어 둡니다.
MOCK_ALARM_DOMAIN_KEYWORDS = [
    "전체 알람 로그", "알람 로그", "알람 이력", "알람 내역",
    "최근 발생한 알람", "발생한 알람", "알람 발생", "반복 알람", "알람 코드", "알람",
]
