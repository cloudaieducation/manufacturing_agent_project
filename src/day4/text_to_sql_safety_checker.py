# -*- coding: utf-8 -*-
"""
Day4 Text-to-SQL 안전성 검증기 (Text-to-SQL Safety Checker) - 교육용

[이 파일의 핵심 한 줄 요약]
이 파일은 "SQL 생성기"가 아니라 "SQL 실행 전 안전성 검사기"입니다.
LLM 또는 mock Text-to-SQL이 만든 SQL을 DB나 MCP Tool에 곧바로 넘기지 않고,
먼저 안전성 기준으로 검사해 PASS / WARNING / BLOCK 으로 판정합니다.

[왜 필요한가 — 수업 핵심]
- 자연어 → SQL 변환(Text-to-SQL)은 편리하지만, 생성된 SQL을 그대로 실행하면
  데이터 삭제/변경, 개인정보 노출, SQL Injection 같은 사고로 이어질 수 있습니다.
- 그래서 "생성 단계"와 "실행 단계" 사이에 안전성 검사 게이트를 둡니다.
  · PASS    → DB Tool 실행 가능
  · WARNING → 사용자 확인 또는 조건 보완 요청
  · BLOCK   → DB 실행 중단 및 안전 응답

[지원 실행 모드]
1) Batch        : data/day4_text_to_sql_cases.json 전체 평가 (옵션 없이 실행)
2) --sql        : 사용자가 직접 입력한 SQL 검사
3) --ask        : 자연어 → mock Text-to-SQL → 안전성 검사
4) --llm-ask    : 자연어 → (선택)LLM Text-to-SQL → 안전성 검사 (실패 시 mock fallback)
5) --interactive: 자연어를 반복 입력받아 mock 변환 + 안전성 검사

[안전/제약]
- 기본 LLM 모드는 mock이며, 명시적으로 openai/nvidia 모드 + Key를 설정하지 않으면
  외부 인터넷 호출을 하지 않습니다. (LLM은 선택 기능, 실패 시 mock fallback)
- LLM 호출은 외부 SDK 없이 표준 라이브러리(urllib)로 OpenAI 호환 API만 호출합니다.
- API Key 등 비밀값은 출력/로그에 남기지 않습니다.
- 모든 데이터는 교육용 가상 제조 시나리오이며, 실제 사내 시스템/개인정보를 쓰지 않습니다.

실행 예시(프로젝트 루트에서):
    uv run python src/day4/text_to_sql_safety_checker.py
    uv run python src/day4/text_to_sql_safety_checker.py --sql "SELECT * FROM alarm_logs;"
    uv run python src/day4/text_to_sql_safety_checker.py --ask "EQP-VD-03 최근 알람 이력 조회해줘"
    uv run python src/day4/text_to_sql_safety_checker.py --llm-ask "EQP-VD-03 최근 알람 이력 조회해줘"
    uv run python src/day4/text_to_sql_safety_checker.py --interactive
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────
# import 경로 보정(bootstrap) — `src.day4...` 패키지 import가 직접 실행에서도 되도록
#   프로젝트 루트를 sys.path에 넣어 둡니다.
#   · _BOOTSTRAP_PROJECT_ROOT는 'import 경로 보정 전용' 임시 상수입니다.
#     (실행에서 쓰는 경로 상수 PROJECT_ROOT/DATA_PATH/OUTPUT_DIR 등은 아래 config.py에서 가져옵니다.)
#   · parents[0]=day4, parents[1]=src, parents[2]=프로젝트 루트
# ──────────────────────────────────────────────────────────────────────
_BOOTSTRAP_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_BOOTSTRAP_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_PROJECT_ROOT))

# ──────────────────────────────────────────────────────────────────────
# 경로/출력 설정과 LLM timeout 설정 — (교육용 리팩토링 2단계) text_to_sql_safety/config.py로 옮겼습니다.
#   - 값/순서/주석은 config.py에 그대로 보존되어 있습니다.
#   - 아래 import로 기존과 동일한 상수명/함수명을 그대로 사용합니다(동작 변화 없음).
#   - 상세 설명은 src/day4/text_to_sql_safety/config.py 를 참고하세요.
# ──────────────────────────────────────────────────────────────────────
from src.day4.text_to_sql_safety.config import (
    PROJECT_ROOT,
    DATA_PATH,
    OUTPUT_DIR,
    RESULT_JSON_PATH,
    REPORT_MD_PATH,
    TRACE_LOG_PATH,
    LLM_BATCH_RESULT_JSON_PATH,
    LLM_BATCH_REPORT_MD_PATH,
    _resolve_llm_timeout,
)


# ──────────────────────────────────────────────────────────────────────
# 안전성/Intent 정책 상수 — "무엇을 허용/차단할지"의 규칙표입니다.
# (교육용 리팩토링 1단계) 정책 상수의 정의는 text_to_sql_safety/policies.py로 옮겼습니다.
#   - 값/순서/주석은 policies.py에 그대로 보존되어 있습니다.
#   - 아래 import로 기존과 동일한 상수명을 그대로 사용합니다(동작 변화 없음).
#   - 상세 설명은 src/day4/text_to_sql_safety/policies.py 를 참고하세요.
#   (sys.path 보정은 위 bootstrap에서 이미 처리되어 있습니다.)
# ──────────────────────────────────────────────────────────────────────
from src.day4.text_to_sql_safety.policies import (
    ALLOWED_TABLES,
    SENSITIVE_COLUMNS,
    BLOCKED_KEYWORDS,
    SQL_INJECTION_PATTERNS,
    ALLOWED_COLUMNS_BY_TABLE,
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
    MOCK_ALARM_DOMAIN_KEYWORDS,
)


# Trace ID 생성을 위한 실행 내 일련번호 카운터입니다.
#   trace_id 형식: TXTSQL-YYYYMMDD-NNNN (예: TXTSQL-20260530-0001)
_TRACE_SEQUENCE = {"count": 0}


def _next_trace_id() -> str:
    """실행 중 호출될 때마다 1씩 증가하는 고유 Trace ID를 만들어 돌려줍니다."""
    _TRACE_SEQUENCE["count"] += 1
    today = datetime.now().strftime("%Y%m%d")
    return f"TXTSQL-{today}-{_TRACE_SEQUENCE['count']:04d}"


# ──────────────────────────────────────────────────────────────────────
# 1. 테스트 케이스 로딩
# ──────────────────────────────────────────────────────────────────────
def load_cases() -> list[dict]:
    """
    data/day4_text_to_sql_cases.json 을 읽어 테스트 케이스 list[dict]를 돌려줍니다.

    - utf-8-sig(BOM 허용) → utf-8 순으로 읽기를 시도합니다.
    - 파일이 없거나 JSON 문법 오류가 있어도 프로그램을 멈추지 않고,
      친절한 안내를 출력한 뒤 빈 리스트([])를 돌려줍니다.
    - 최상위가 list가 아니면 경고 후 빈 리스트를 돌려줍니다.
    """
    if not DATA_PATH.exists():
        print(f"[오류] 입력 파일을 찾을 수 없습니다: {DATA_PATH}")
        print("       프로젝트 루트에서 실행했는지, 파일 경로가 맞는지 확인해 주세요.")
        return []

    raw_text = None
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            raw_text = DATA_PATH.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    if raw_text is None:
        print(f"[오류] 파일 인코딩을 해석하지 못했습니다(UTF-8 계열 아님): {DATA_PATH}")
        return []

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as error:
        print(f"[오류] JSON 문법 오류: {DATA_PATH}")
        print(f"       line {error.lineno}, column {error.colno} - {error.msg}")
        return []

    if not isinstance(data, list):
        print(f"[경고] JSON 최상위가 list가 아닙니다(현재 형태: {type(data).__name__}): {DATA_PATH}")
        return []

    return [item for item in data if isinstance(item, dict)]


# ──────────────────────────────────────────────────────────────────────
# 2. Mock Text-to-SQL (규칙 기반, LLM 없이 동작)
# ──────────────────────────────────────────────────────────────────────
def _extract_equipment_id(text: str) -> str:
    """질문에서 EQP-XX-00 형태의 교육용 설비 ID를 뽑습니다. 없으면 예시 기본값을 씁니다."""
    match = re.search(r"EQP-[A-Z]{2}-\d{2}", (text or "").upper())
    return match.group(0) if match else "EQP-VD-03"


def _mock_time_condition(user_query: str, time_column: str) -> str:
    """
    mock 전용 helper: 사용자 질문의 시간 표현을 해당 도메인의 '기존 시간 컬럼' 기준
    WHERE 조건 본문으로 만듭니다. (WHERE/AND 접속사는 호출부가 붙입니다.)

    처리 규칙(이번 작업 범위):
    - "최근 24시간" / "최근 하루" / "지난 24시간"
        → "{col} >= CURRENT_TIMESTAMP - INTERVAL '24 hours'"
    - "오늘"
        → "DATE({col}) = CURRENT_DATE"
    - "최근"(단독, 명확한 기간 없음) 등
        → "" (빈 문자열) : 24시간 조건을 임의로 붙이지 않습니다(정렬/LIMIT는 기존 SQL 유지).

    time_column 은 각 도메인의 '기존' 시간 컬럼명을 그대로 넣어 사용합니다
    (alarm_logs=occurred_at / quality_metrics=measured_at / maintenance_history=performed_at /
     equipment_status=updated_at). 명확한 컬럼이 없을 때만 호출부가 event_time을 넘깁니다.
    """
    query = user_query or ""
    if ("최근 24시간" in query) or ("최근 하루" in query) or ("지난 24시간" in query):
        return f"{time_column} >= CURRENT_TIMESTAMP - INTERVAL '24 hours'"
    if "오늘" in query:
        return f"DATE({time_column}) = CURRENT_DATE"
    return ""


# mock 전용 알람 도메인 키워드(MOCK_ALARM_DOMAIN_KEYWORDS)의 정의도 policies.py로 옮겼습니다.
#   - 값/순서/주석은 src/day4/text_to_sql_safety/policies.py 에 그대로 보존되어 있습니다.
def _is_mock_alarm_domain(user_query: str) -> bool:
    """mock 전용: 질문이 명확히 알람 로그 도메인을 가리키는지 판단합니다."""
    query = user_query or ""
    return any(keyword in query for keyword in MOCK_ALARM_DOMAIN_KEYWORDS)


def mock_text_to_sql(user_query: str) -> str:
    """
    자연어 질문을 규칙(rule) 기반으로 SQL 문자열로 바꿉니다. (실제 LLM 호출 없음)

    목적은 'SQL 생성 성능'이 아니라 'Safety Checker 흐름을 보여 주기' 위함입니다.
    그래서 안전한 질문은 안전한 SELECT로, 위험한 의도가 담긴 질문은 일부러
    위험한 SQL(삭제/민감컬럼/전체조회 등)로 변환해 검사 결과를 시연합니다.
    """
    query = user_query or ""
    lowered = query.lower()
    equipment_id = _extract_equipment_id(query)

    # (1) 위험 의도부터 먼저 처리 — 안전성 검사가 BLOCK을 어떻게 잡는지 보여 주기 위함
    if "삭제" in query or "delete" in lowered:
        return f"DELETE FROM alarm_logs WHERE equipment_id = '{equipment_id}';"
    if "drop" in lowered or "테이블 삭제" in query:
        return "DROP TABLE alarm_logs;"
    if ("작업자" in query) or ("연락처" in query) or ("개인정보" in query):
        return (
            "SELECT worker_name, phone, email FROM maintenance_history "
            f"WHERE equipment_id = '{equipment_id}' LIMIT 20;"
        )
    # "전체 알람 로그"처럼 명확히 알람 도메인을 가리키는 질문은 이 demo 분기보다
    # 아래 알람 도메인 분기를 우선 적용합니다(도메인 매핑 오류 방지).
    if "전체" in query and not _is_mock_alarm_domain(query):
        # WHERE/LIMIT 없는 SELECT * → 넓은 조회 (WARNING 시연)
        return "SELECT * FROM equipment_status;"

    # (2) 도메인별 정상 조회 (안전한 SELECT 시연)
    #     시간 표현이 있으면 각 도메인의 기존 시간 컬럼 기준으로 WHERE 조건만 자연스럽게 덧붙입니다.
    #     (기존 WHERE가 있으면 AND로 연결하고, ORDER BY/LIMIT 앞에 올바르게 배치합니다.)
    if ("품질" in query) or ("불량률" in query) or ("수율" in query):
        time_cond = _mock_time_condition(query, "measured_at")
        where = "WHERE line_id = 'EDU-LINE-01'"
        if time_cond:
            where += f" AND {time_cond}"
        return (
            "SELECT line_id, metric_name, metric_value, measured_at FROM quality_metrics "
            f"{where} ORDER BY measured_at DESC LIMIT 50;"
        )
    if "정비" in query:
        time_cond = _mock_time_condition(query, "performed_at")
        where = f"WHERE equipment_id = '{equipment_id}'"
        if time_cond:
            where += f" AND {time_cond}"
        return (
            "SELECT equipment_id, action, performed_at FROM maintenance_history "
            f"{where} ORDER BY performed_at DESC LIMIT 20;"
        )
    if "설비 상태" in query or "상태" in query:
        time_cond = _mock_time_condition(query, "updated_at")
        where = f"WHERE equipment_id = '{equipment_id}'"
        if time_cond:
            where += f" AND {time_cond}"
        return (
            "SELECT equipment_id, status_code, updated_at FROM equipment_status "
            f"{where} LIMIT 20;"
        )
    if ("알람" in query) or ("이력" in query):
        time_cond = _mock_time_condition(query, "occurred_at")
        where = f"WHERE equipment_id = '{equipment_id}'"
        if time_cond:
            where += f" AND {time_cond}"
        return (
            "SELECT equipment_id, alarm_code, occurred_at FROM alarm_logs "
            f"{where} ORDER BY occurred_at DESC LIMIT 20;"
        )

    # (3) 매칭되는 규칙이 없으면 안전한 기본 알람 조회로 변환합니다.
    time_cond = _mock_time_condition(query, "occurred_at")
    where = f"WHERE equipment_id = '{equipment_id}'"
    if time_cond:
        where += f" AND {time_cond}"
    return (
        "SELECT equipment_id, alarm_code, occurred_at FROM alarm_logs "
        f"{where} ORDER BY occurred_at DESC LIMIT 20;"
    )


# ──────────────────────────────────────────────────────────────────────
# 3. (선택) LLM Text-to-SQL — 실패하면 mock으로 fallback
# ──────────────────────────────────────────────────────────────────────
def _build_allowed_columns_block() -> str:
    """테이블별 허용 컬럼 목록을 system prompt에 넣을 수 있는 문자열로 만듭니다."""
    lines: list[str] = []
    for table, columns in ALLOWED_COLUMNS_BY_TABLE.items():
        lines.append(f"{table}:")
        for column in columns:
            lines.append(f"- {column}")
    return "\n".join(lines)


def _build_llm_messages(user_query: str) -> list[dict]:
    """LLM에 보낼 메시지를 만듭니다. 안전한 SELECT만 생성하도록 제약을 명시합니다.

    위험 요청(삭제/변경/민감정보 등)을 LLM이 직접 거부하게 하지 않습니다.
    위험 요청 차단은 check_user_intent_safety()가 담당하고, 여기서는 LLM이
    '허용된 조회 요청'에 대해 안전한 SELECT를 잘 생성하는 데 집중하게 합니다.
    """
    system_rules = (
        "당신은 교육용 가상 제조 데이터베이스의 Text-to-SQL 도우미입니다.\n"
        "반드시 아래 규칙을 지키세요.\n"
        "1) 반드시 SELECT 문만 생성합니다.\n"
        "2) DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE, CREATE 는 생성하지 않습니다.\n"
        f"3) 허용된 테이블만 사용합니다: {', '.join(ALLOWED_TABLES)}\n"
        f"4) 민감 컬럼은 사용하지 않습니다: {', '.join(SENSITIVE_COLUMNS)}\n"
        "5) WHERE 조건과 LIMIT 을 포함합니다.\n"
        "6) SQL 한 문장만 출력합니다.\n"
        "7) 설명 문장, Markdown, 코드블록은 출력하지 않습니다.\n"
        "8) SELECT * 를 절대 사용하지 않습니다.\n"
        "9) 반드시 필요한 컬럼만 명시합니다.\n"
        "10) 아래 허용 컬럼만 사용합니다.\n"
        "11) 존재하지 않는 컬럼을 만들지 않습니다.\n"
        "12) 컬럼명을 추측하지 않습니다.\n"
        "13) 허용된 테이블과 허용된 컬럼 조합만 사용합니다.\n"
        "\n"
        "[테이블별 허용 컬럼]\n"
        f"{_build_allowed_columns_block()}\n"
        "\n"
        "created_at, recorded_at, line_name, alarm_time, maintenance_type, "
        "maintenance_date 같은 컬럼은 존재하지 않으므로 절대 사용하지 마세요.\n"
        "\n"
        "[나쁜 예]\n"
        "SELECT * FROM alarm_logs;\n"
        "SELECT line_name, recorded_at FROM quality_metrics;\n"
        "SELECT alarm_time FROM alarm_logs;\n"
        "SELECT maintenance_type, maintenance_date FROM maintenance_history;\n"
        "\n"
        "[좋은 예]\n"
        "SELECT equipment_id, alarm_code, occurred_at\n"
        "FROM alarm_logs\n"
        "WHERE equipment_id = 'EQP-VD-03'\n"
        "ORDER BY occurred_at DESC\n"
        "LIMIT 20;"
    )
    return [
        {"role": "system", "content": system_rules},
        {"role": "user", "content": user_query},
    ]


# SQL 문장이 시작될 수 있는 키워드 목록입니다.
#   SELECT뿐 아니라 DELETE/UPDATE/INSERT/DROP/ALTER/TRUNCATE/CREATE 같은 위험 구문의
#   시작어도 포함합니다. → 추출 단계에서 위험 SQL을 잘라내지 않고 '보존'하기 위함입니다.
SQL_START_KEYWORDS = [
    "select", "with", "delete", "update", "insert",
    "drop", "alter", "truncate", "create",
]


def _mask_secrets(text: str) -> str:
    """Trace에 원본 응답을 남길 때 비밀값처럼 보이는 문자열을 마스킹합니다."""
    masked = str(text or "")
    masked = re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", masked)
    masked = re.sub(r"\bsk-[A-Za-z0-9._\-]{8,}", "sk-***", masked)
    masked = re.sub(
        r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+",
        r"\1=***",
        masked,
    )
    return masked


def _safe_preview(text: str, limit: int = 1000) -> str:
    """비밀값을 마스킹하고 앞부분 limit자만 남긴 미리보기 문자열을 만듭니다."""
    return _mask_secrets(text)[:limit]


def _extract_sql_from_text(text: str) -> str:
    """
    LLM 응답에서 '검사 대상 SQL 후보'를 최대한 보존해 추출합니다.

    [설계 원칙 — 매우 중요]
    - 이 함수는 SQL을 안전하게 '정제'하는 함수가 아니라, LLM 응답에서 검사할 SQL 후보를
      최대한 '보존'하는 함수입니다. 위험 여부 판단은 전적으로 check_sql_safety()가 합니다.
    - 따라서 '첫 번째 세미콜론'에서 자르지 않습니다. 첫 ';' 뒤에 오는
      DROP/DELETE/UPDATE 같은 위험한 후속 문장까지 그대로 남겨 검사 대상에 포함합니다.
      (첫 ';'에서 자르면 "SELECT ...; DROP TABLE ...;" 의 DROP이 사라져 위험을 놓칩니다.)
    - 코드펜스/설명 문장 같은 '포맷 노이즈'만 줄이고, SQL 내용 자체는 바꾸지 않습니다.
    - 코드펜스가 여러 개면 SQL로 보이는 블록을 합쳐 함께 검사합니다(둘째 블록의 위험 SQL 누락 방지).
    - SELECT뿐 아니라 DELETE/UPDATE/INSERT/DROP/ALTER/TRUNCATE/CREATE로 시작하는 응답도 추출합니다.

    SQL을 찾지 못하면 빈 문자열을 돌려줍니다(→ 호출부에서 mock fallback).
    """
    if not text:
        return ""

    cleaned = text.strip()
    start_pattern = r"\b(?:" + "|".join(SQL_START_KEYWORDS) + r")\b"

    # (1) Markdown 코드펜스가 있으면, SQL로 보이는 블록을 모두 모아 합칩니다(여러 블록 보존).
    fences = re.findall(r"```(?:sql)?\s*(.*?)```", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if fences:
        sql_blocks = [
            block.strip()
            for block in fences
            if re.search(start_pattern, block, flags=re.IGNORECASE)
        ]
        # SQL 키워드가 든 블록이 하나도 없으면, 보수적으로 모든 블록을 합쳐 둡니다.
        cleaned = "\n".join(sql_blocks if sql_blocks else [b.strip() for b in fences]).strip()

    # (2) SQL 시작 키워드 위치부터 '끝까지'를 검사 대상으로 삼습니다. 세미콜론에서 자르지 않습니다.
    match = re.search(start_pattern, cleaned, flags=re.IGNORECASE)
    if not match:
        return ""
    return cleaned[match.start():].strip()


# [확인 케이스] 아래 입력은 check_sql_safety()에서 반드시 BLOCK 이어야 합니다.
#   SELECT equipment_id, alarm_code FROM alarm_logs WHERE equipment_id = 'EQP-VD-03'; DROP TABLE alarm_logs;
#   → 추출 단계에서 DROP 문장이 보존되고, check_sql_safety가
#     '다중 SQL 문장(multiple_statements)' + 'DROP 키워드'를 감지해 BLOCK 으로 판정합니다.


def _call_openai_compatible(user_query: str, base_url: str, api_key: str, model: str) -> str:
    """
    OpenAI 호환 Chat Completions API를 표준 라이브러리(urllib)로 호출합니다.

    - 외부 SDK를 쓰지 않습니다(프로젝트 정책).
    - 성공 시 응답 본문(content) 문자열을 돌려줍니다.
    - 어떤 이유로든 실패하면 예외를 올려 보내고, 호출부가 mock으로 fallback 합니다.
    - 예외 메시지에 API Key 같은 비밀값을 노출하지 않습니다.
    """
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": _build_llm_messages(user_query),
        "temperature": 0,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    # timeout을 두어 응답이 없을 때 무한 대기하지 않도록 합니다.
    # (기본 120초, TEXT_TO_SQL_LLM_TIMEOUT 환경변수로 조정 가능 — 느린 엔드포인트의 timeout→fallback 완화)
    with urllib.request.urlopen(request, timeout=_resolve_llm_timeout()) as response:
        response_json = json.loads(response.read().decode("utf-8"))

    # OpenAI 호환 응답 구조: choices[0].message.content
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def llm_text_to_sql(user_query: str) -> tuple[str, dict]:
    """
    자연어를 SQL로 변환합니다. LLM 모드면 LLM을, 아니면(또는 실패 시) mock을 사용합니다.

    환경 변수:
        TEXT_TO_SQL_LLM_MODE      : mock | openai | nvidia | disabled (기본 mock)
        TEXT_TO_SQL_LLM_API_KEY   : OpenAI 호환 API Key
        TEXT_TO_SQL_LLM_BASE_URL  : OpenAI 호환 Base URL (예: https://.../v1)
        TEXT_TO_SQL_LLM_MODEL     : 모델 이름

    반환: (generated_sql, meta)
        meta = {
            "generation_source": "llm" | "llm_fallback_mock" | "mock",
            "llm_mode": "openai" | "nvidia" | "mock" | "disabled",
            "llm_fallback_used": True | False,
            "llm_fallback_reason": str | None,
        }
    """
    mode = (os.environ.get("TEXT_TO_SQL_LLM_MODE", "mock") or "mock").strip().lower()

    # mock / disabled / 알 수 없는 값 → 그냥 mock 사용 (fallback 아님)
    if mode in ("mock", "disabled") or mode not in ("openai", "nvidia"):
        normalized_mode = mode if mode in ("mock", "disabled") else "mock"
        return mock_text_to_sql(user_query), {
            "generation_source": "mock",
            "llm_mode": normalized_mode,
            "llm_fallback_used": False,
            "llm_fallback_reason": None,
        }

    # 여기부터 openai/nvidia 모드: 설정이 없으면 mock으로 fallback
    api_key = (os.environ.get("TEXT_TO_SQL_LLM_API_KEY", "") or "").strip()
    base_url = (os.environ.get("TEXT_TO_SQL_LLM_BASE_URL", "") or "").strip()
    model = (os.environ.get("TEXT_TO_SQL_LLM_MODEL", "") or "").strip()

    missing = [
        name
        for name, value in (
            ("TEXT_TO_SQL_LLM_API_KEY", api_key),
            ("TEXT_TO_SQL_LLM_BASE_URL", base_url),
            ("TEXT_TO_SQL_LLM_MODEL", model),
        )
        if not value
    ]
    if missing:
        reason = f"LLM 설정 누락({', '.join(missing)})으로 mock으로 대체했습니다."
        return mock_text_to_sql(user_query), {
            "generation_source": "llm_fallback_mock",
            "llm_mode": mode,
            "llm_fallback_used": True,
            "llm_fallback_reason": reason,
        }

    # 실제 LLM 호출 시도 — 실패/빈 응답이면 mock fallback
    try:
        raw_text = _call_openai_compatible(user_query, base_url, api_key, model)
        generated_sql = _extract_sql_from_text(raw_text)
        if not generated_sql:
            reason = "LLM이 빈 응답 또는 SQL이 아닌 응답을 반환하여 mock으로 대체했습니다."
            return mock_text_to_sql(user_query), {
                "generation_source": "llm_fallback_mock",
                "llm_mode": mode,
                "llm_fallback_used": True,
                "llm_fallback_reason": reason,
                "raw_llm_response_preview": _safe_preview(raw_text),
            }
        return generated_sql, {
            "generation_source": "llm",
            "llm_mode": mode,
            "llm_fallback_used": False,
            "llm_fallback_reason": None,
            "raw_llm_response_preview": _safe_preview(raw_text),
        }
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as error:
        # 비밀값이 새지 않도록 예외 타입/짧은 메시지만 남깁니다.
        reason = f"LLM 호출 실패({type(error).__name__})로 mock으로 대체했습니다."
        return mock_text_to_sql(user_query), {
            "generation_source": "llm_fallback_mock",
            "llm_mode": mode,
            "llm_fallback_used": True,
            "llm_fallback_reason": reason,
        }


# ──────────────────────────────────────────────────────────────────────
# SQL/Intent Safety 판정 함수는 src/day4/text_to_sql_safety/safety.py로 분리되어 있습니다.
#   - _normalize_sql / _detect_tables / check_sql_safety / check_text_to_sql_safety /
#     check_user_intent_safety / merge_intent_and_sql_safety / _skipped_sql_safety
#   - 아래에서 import해 기존 호출부(run_batch / run_llm_batch / run_direct_sql 등)가
#     그대로 사용합니다. 판정 기준/문구/반환 구조는 변경되지 않았습니다.
#   (SQL_START_KEYWORDS는 _extract_sql_from_text(추출)에서도 쓰여 Safety 전용이 아니므로
#    이 파일에 그대로 남겨 둡니다.)
# ──────────────────────────────────────────────────────────────────────
from src.day4.text_to_sql_safety.safety import (
    _normalize_sql,
    _detect_tables,
    check_sql_safety,
    check_text_to_sql_safety,
    check_user_intent_safety,
    merge_intent_and_sql_safety,
    _skipped_sql_safety,
)


# ──────────────────────────────────────────────────────────────────────
# 5. Trace record 생성
# ──────────────────────────────────────────────────────────────────────
def _default_teaching_point(actual_status: str) -> str:
    """배치 케이스가 아닌 모드에서 사용할 기본 teaching_point를 상태별로 만듭니다."""
    if actual_status == "PASS":
        return "자연어 질문이 안전한 SELECT로 변환되고 Safety Checker를 통과했습니다."
    if actual_status == "WARNING":
        return "읽기 전용이지만 조회 범위·컬럼 측면에서 주의가 필요한 SQL입니다."
    return "안전성 위반이 감지되어 DB/MCP Tool 실행 전에 차단해야 하는 SQL입니다."


def build_trace_record(
    mode: str,
    generated_sql: str,
    safety: dict,
    user_query: str = "",
    input_sql: str | None = None,
    generation_source: str = "mock",
    gen_meta: dict | None = None,
    case: dict | None = None,
    intent_status: str | None = None,
    sql_status: str | None = None,
    final_status: str | None = None,
    intent_blocked_reasons: list | None = None,
    intent_warnings: list | None = None,
) -> dict:
    """
    SQL 검사 1건의 실행 기록(Trace)을 표준 dict로 만듭니다.

    모든 실행 모드(batch, sql, ask, llm-ask, interactive)가 이 함수를 통해 Trace를 만듭니다.
    quality_gate_signal 규칙: PASS→"pass", WARNING→"warning", BLOCK→"fail"

    Intent/Final 관련 인자는 선택(Optional)입니다. LLM Batch 모드만 채워 넣으며,
    그 외 모드와의 호환을 위해 기본값은 None 또는 빈 list로 둡니다.
    """
    gen_meta = gen_meta or {}
    case = case or {}

    actual_status = safety["actual_status"]
    quality_gate_map = {"PASS": "pass", "WARNING": "warning", "BLOCK": "fail"}

    expected_status = case.get("expected_status")  # 배치가 아니면 None
    matched_expected = (
        (actual_status == expected_status) if expected_status is not None else None
    )

    # teaching_point: 배치 케이스면 데이터의 값을, 아니면 상태 기반 기본 문구를 사용합니다.
    teaching_point = case.get("teaching_point") or _default_teaching_point(actual_status)

    return {
        "trace_id": _next_trace_id(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "case_id": case.get("case_id"),
        "category": case.get("category", _category_for_mode(mode)),
        "user_query": user_query,
        "input_sql": input_sql,
        "generation_source": generation_source,
        "llm_mode": gen_meta.get("llm_mode"),
        "llm_fallback_used": gen_meta.get("llm_fallback_used", False),
        "llm_fallback_reason": gen_meta.get("llm_fallback_reason"),
        # 선택 필드: LLM 모드일 때만 채워지며(그 외 None), 비밀값은 마스킹되고 1000자로 제한됩니다.
        "raw_llm_response_preview": gen_meta.get("raw_llm_response_preview"),
        "generated_sql": generated_sql,
        "normalized_sql": safety["normalized_sql"],
        "detected_tables": safety["detected_tables"],
        "detected_sensitive_columns": safety["detected_sensitive_columns"],
        "detected_injection_patterns": safety["detected_injection_patterns"],
        "blocked_reasons": safety["blocked_reasons"],
        "warnings": safety["warnings"],
        "reasons": safety["reasons"],
        "actual_status": actual_status,
        "expected_status": expected_status,
        "matched_expected": matched_expected,
        "quality_gate_signal": quality_gate_map.get(actual_status, "warning"),
        "teaching_point": teaching_point,
        # 선택 필드(LLM Batch 전용): 그 외 모드는 None/빈 list로 남습니다.
        "intent_status": intent_status,
        "sql_status": sql_status,
        "final_status": final_status,
        "intent_blocked_reasons": intent_blocked_reasons if intent_blocked_reasons is not None else [],
        "intent_warnings": intent_warnings if intent_warnings is not None else [],
    }


def _category_for_mode(mode: str) -> str:
    """배치 케이스가 아닐 때, 모드별 기본 category 값을 정합니다."""
    return {
        "sql": "direct_sql",
        "ask": "mock_ask",
        "llm-ask": "llm_ask",
        "interactive": "interactive_mock",
    }.get(mode, mode)


# ──────────────────────────────────────────────────────────────────────
# 6. Trace 로그 적재 (JSONL)
# ──────────────────────────────────────────────────────────────────────
def append_trace_log(record: dict) -> None:
    """Trace record 1건을 outputs/day4/text_to_sql_safety_trace.jsonl 에 한 줄 추가합니다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with TRACE_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


# ──────────────────────────────────────────────────────────────────────
# 7. Batch 결과 요약
# ──────────────────────────────────────────────────────────────────────
def build_summary(results: list[dict]) -> dict:
    """Batch 평가 결과 목록(results)으로 전체 요약 통계를 만듭니다."""
    summary = {
        "total_cases": len(results),
        "pass_count": 0,
        "warning_count": 0,
        "block_count": 0,
        "matched_expected_count": 0,
        "mismatch_count": 0,
        "sql_injection_case_count": 0,
    }
    for result in results:
        status = result.get("actual_status")
        if status == "PASS":
            summary["pass_count"] += 1
        elif status == "WARNING":
            summary["warning_count"] += 1
        elif status == "BLOCK":
            summary["block_count"] += 1

        if result.get("matched_expected"):
            summary["matched_expected_count"] += 1
        else:
            summary["mismatch_count"] += 1

        if result.get("category") == "sql_injection":
            summary["sql_injection_case_count"] += 1
    return summary


# ──────────────────────────────────────────────────────────────────────
# 8. 결과 저장 (JSON + Markdown)
# ──────────────────────────────────────────────────────────────────────
def _escape_table_cell(value) -> str:
    """Markdown 표 칸이 깨지지 않도록 줄바꿈과 | 문자를 정리합니다."""
    return str(value if value is not None else "").replace("\n", " ").replace("|", "/")


def write_outputs(results: list[dict], summary: dict) -> None:
    """
    Batch 결과를 JSON과 Markdown 보고서로 저장합니다.

    - JSON: outputs/day4/text_to_sql_safety_result.json (ensure_ascii=False, indent=2)
    - MD  : outputs/day4/text_to_sql_safety_report.md
    (새 템플릿 파일을 만들지 않기 위해 Markdown 문자열을 코드에서 직접 조립합니다.)
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # (1) JSON 저장
    payload = {"summary": summary, "results": results}
    RESULT_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # (2) Markdown 보고서 저장
    lines: list[str] = []
    lines.append("# Day4 Text-to-SQL Safety Report")
    lines.append("")

    # Summary 섹션
    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"- Total cases: {summary.get('total_cases', 0)}")
    lines.append(f"- PASS: {summary.get('pass_count', 0)}")
    lines.append(f"- WARNING: {summary.get('warning_count', 0)}")
    lines.append(f"- BLOCK: {summary.get('block_count', 0)}")
    lines.append(f"- Matched expected: {summary.get('matched_expected_count', 0)}")
    lines.append(f"- Mismatch: {summary.get('mismatch_count', 0)}")
    lines.append(f"- SQL Injection cases: {summary.get('sql_injection_case_count', 0)}")
    lines.append("")

    # Case Results 섹션 (요약 표 + 케이스별 상세)
    lines.append("## 2. Case Results")
    lines.append("")
    lines.append("| Case ID | Category | Expected | Actual | Matched |")
    lines.append("|---|---|---|---|---|")
    for result in results:
        lines.append(
            f"| {_escape_table_cell(result.get('case_id'))} "
            f"| {_escape_table_cell(result.get('category'))} "
            f"| {_escape_table_cell(result.get('expected_status'))} "
            f"| {_escape_table_cell(result.get('actual_status'))} "
            f"| {_escape_table_cell(result.get('matched_expected'))} |"
        )
    lines.append("")

    for result in results:
        lines.append(f"### {result.get('case_id')}")
        lines.append("")
        lines.append(f"- Category: {result.get('category')}")
        lines.append(f"- User Query: {result.get('user_query', '')}")
        lines.append(f"- Generated SQL: `{_escape_table_cell(result.get('generated_sql'))}`")
        lines.append(f"- Expected / Actual: {result.get('expected_status')} / {result.get('actual_status')}")
        lines.append(f"- Matched Expected: {result.get('matched_expected')}")
        blocked = result.get("blocked_reasons", [])
        warns = result.get("warnings", [])
        lines.append(f"- Blocked Reasons: {' / '.join(blocked) if blocked else '없음'}")
        lines.append(f"- Warnings: {' / '.join(warns) if warns else '없음'}")
        detected = result.get("detected_injection_patterns", [])
        lines.append(f"- Detected Injection Patterns: {', '.join(detected) if detected else '없음'}")
        lines.append(f"- Expected Reason: {result.get('expected_reason', '')}")
        lines.append("")

    # Trace Log 안내 섹션
    lines.append("## 3. Trace Log")
    lines.append("")
    lines.append("- 모든 검사 실행 기록은 아래 JSONL 파일에 한 줄씩 누적됩니다.")
    lines.append(f"- `{TRACE_LOG_PATH.relative_to(PROJECT_ROOT).as_posix()}`")
    lines.append("- Batch/직접 SQL/mock 자연어/LLM 자연어/대화형 모드의 기록이 같은 형식으로 남습니다.")
    lines.append("")

    # Teaching Notes 섹션
    lines.append("## 4. Teaching Notes")
    lines.append("")
    lines.append("- Text-to-SQL 결과는 바로 실행하면 안 된다.")
    lines.append("- 실행 전 SELECT 제한, 허용 테이블, 민감 컬럼, LIMIT 여부를 확인해야 한다.")
    lines.append("- SQL Injection 의심 패턴은 DB Tool 또는 MCP Tool 호출 전에 차단해야 한다.")
    lines.append("- 이 예제의 SQL Injection 검사는 교육용 정규식 기반 검사이다.")
    lines.append("- 실제 운영에서는 Prepared Statement, Query Builder, 권한 분리, DB Proxy, 감사 로그가 함께 필요하다.")
    lines.append("- 생성 SQL은 PASS여도 Trace에 남겨야 한다.")
    lines.append("")

    REPORT_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# 콘솔 출력 helper
# ──────────────────────────────────────────────────────────────────────
def _print_check_result(record: dict) -> None:
    """단건 검사 결과(Trace record)를 콘솔에 보기 좋게 출력합니다."""
    print("-" * 70)
    print(f"mode            : {record.get('mode')}")
    if record.get("case_id"):
        print(f"case_id         : {record.get('case_id')}")
    print(f"user_query      : {record.get('user_query') or '(없음)'}")
    print(f"generated_sql   : {record.get('generated_sql')}")
    print(f"actual_status   : {record.get('actual_status')}")
    reasons = record.get("reasons", [])
    warnings = record.get("warnings", [])
    blocked = record.get("blocked_reasons", [])
    print(f"reasons         : {' / '.join(reasons) if reasons else '없음'}")
    print(f"warnings        : {' / '.join(warnings) if warnings else '없음'}")
    print(f"blocked_reasons : {' / '.join(blocked) if blocked else '없음'}")
    print(f"trace_id        : {record.get('trace_id')}")
    print(f"trace_file      : {TRACE_LOG_PATH.relative_to(PROJECT_ROOT).as_posix()}")


# ──────────────────────────────────────────────────────────────────────
# 9. 대화형 모드
# ──────────────────────────────────────────────────────────────────────
def run_interactive() -> None:
    """
    자연어 질문을 반복 입력받아 mock 변환 + 안전성 검사 + Trace 기록을 수행합니다.
    'exit' 또는 'quit' 입력 시 종료합니다.
    """
    print("[Day4 Text-to-SQL Safety Checker] 대화형 모드")
    print("자연어 질문을 입력하세요. 종료하려면 exit 또는 quit 를 입력하세요.")
    while True:
        try:
            user_query = input("자연어 질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_query.lower() in ("exit", "quit"):
            print("대화형 모드를 종료합니다.")
            break
        if not user_query:
            continue

        generated_sql = mock_text_to_sql(user_query)
        safety = check_sql_safety(generated_sql)
        record = build_trace_record(
            mode="interactive",
            generated_sql=generated_sql,
            safety=safety,
            user_query=user_query,
            generation_source="mock",
        )
        append_trace_log(record)
        _print_check_result(record)


# ──────────────────────────────────────────────────────────────────────
# 모드별 실행 함수 (Batch 외 단건 모드)
# ──────────────────────────────────────────────────────────────────────
def run_direct_sql(sql: str) -> None:
    """--sql: 사용자가 직접 입력한 SQL을 그대로 검사합니다."""
    safety = check_sql_safety(sql)
    record = build_trace_record(
        mode="sql",
        generated_sql=sql,
        safety=safety,
        user_query="",
        input_sql=sql,
        generation_source="direct_sql",
    )
    append_trace_log(record)
    _print_check_result(record)


def run_mock_ask(user_query: str) -> None:
    """--ask: 자연어를 mock으로 SQL 변환한 뒤 검사합니다."""
    generated_sql = mock_text_to_sql(user_query)
    safety = check_sql_safety(generated_sql)
    record = build_trace_record(
        mode="ask",
        generated_sql=generated_sql,
        safety=safety,
        user_query=user_query,
        generation_source="mock",
    )
    append_trace_log(record)
    _print_check_result(record)


def run_llm_ask(user_query: str) -> None:
    """--llm-ask: 자연어를 (선택)LLM으로 SQL 변환(실패 시 mock)한 뒤 검사합니다."""
    generated_sql, gen_meta = llm_text_to_sql(user_query)
    safety = check_sql_safety(generated_sql)
    record = build_trace_record(
        mode="llm-ask",
        generated_sql=generated_sql,
        safety=safety,
        user_query=user_query,
        generation_source=gen_meta.get("generation_source", "mock"),
        gen_meta=gen_meta,
    )
    append_trace_log(record)
    if gen_meta.get("llm_fallback_used"):
        print(f"[안내] LLM fallback 사용: {gen_meta.get('llm_fallback_reason')}")
    _print_check_result(record)


def run_batch() -> None:
    """옵션이 없을 때의 기본 모드: 테스트 케이스 전체를 평가하고 결과를 저장합니다."""
    print("[Day4 Text-to-SQL Safety Checker] Batch 모드")
    cases = load_cases()
    if not cases:
        print("평가할 테스트 케이스가 없습니다.")
        return

    results: list[dict] = []
    for case in cases:
        generated_sql = str(case.get("generated_sql", "") or "")
        safety = check_sql_safety(generated_sql)
        record = build_trace_record(
            mode="batch",
            generated_sql=generated_sql,
            safety=safety,
            user_query=str(case.get("user_query", "") or ""),
            generation_source="dataset",
            case=case,
        )
        append_trace_log(record)

        # 결과 JSON에 담을 케이스 단위 항목 구성
        results.append(
            {
                "case_id": case.get("case_id"),
                "trace_id": record["trace_id"],
                "category": case.get("category"),
                "user_query": str(case.get("user_query", "") or ""),
                "generated_sql": generated_sql,
                "expected_status": case.get("expected_status"),
                "actual_status": safety["actual_status"],
                "matched_expected": record["matched_expected"],
                "expected_reason": case.get("expected_reason", ""),
                "reasons": safety["reasons"],
                "warnings": safety["warnings"],
                "blocked_reasons": safety["blocked_reasons"],
                "detected_tables": safety["detected_tables"],
                "detected_sensitive_columns": safety["detected_sensitive_columns"],
                "detected_injection_patterns": safety["detected_injection_patterns"],
            }
        )

    summary = build_summary(results)
    write_outputs(results, summary)

    # 콘솔 요약 출력
    print(f"입력 파일: {DATA_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"총 케이스: {summary['total_cases']}")
    print(f"PASS: {summary['pass_count']} / WARNING: {summary['warning_count']} / BLOCK: {summary['block_count']}")
    print(f"기대와 일치: {summary['matched_expected_count']} / 불일치: {summary['mismatch_count']}")
    print(f"SQL Injection 케이스: {summary['sql_injection_case_count']}")
    print("결과 저장:")
    print(f"- {RESULT_JSON_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"- {REPORT_MD_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"- {TRACE_LOG_PATH.relative_to(PROJECT_ROOT).as_posix()}")

    if summary["mismatch_count"] > 0:
        print("[안내] 기대 판정과 다른 케이스가 있습니다. 보고서를 확인해 주세요.")


# ──────────────────────────────────────────────────────────────────────
# LLM Batch 모드 (--llm-batch): dataset의 user_query를 실제 LLM으로 변환해 전체 평가
#   - 기본 Batch는 dataset에 이미 있는 generated_sql을 검사하지만,
#     LLM Batch는 같은 user_query를 LLM에 보내 새 SQL을 생성해 검사합니다.
#   - 결과는 기본 Batch 산출물을 덮어쓰지 않고 별도 파일에 저장합니다.
# ──────────────────────────────────────────────────────────────────────
def build_llm_batch_summary(results: list[dict]) -> dict:
    """LLM Batch 결과 요약. 기본 build_summary와 분리하여 LLM 사용/fallback 집계를 포함합니다.

    - actual_status에는 final_status(의도+SQL 병합 판정)가 들어오므로 pass/warning/block 집계는
      최종 판정 기준입니다.
    - Intent/SQL 단계별 집계(intent_block_count 등)를 함께 제공합니다.
    """
    summary = {
        "total_cases": len(results),
        "pass_count": 0,
        "warning_count": 0,
        "block_count": 0,
        "matched_expected_count": 0,
        "mismatch_count": 0,
        "llm_used_count": 0,
        "llm_fallback_count": 0,
        # 보고서 해석 안내용 생성 출처 집계 (case item 구조는 변경하지 않음, summary 숫자 필드만 추가)
        "mock_used_count": 0,
        "skipped_generation_count": 0,
        # Intent/SQL/Final 단계별 집계 (LLM Batch 보강)
        "intent_block_count": 0,
        "intent_warning_count": 0,
        "sql_block_count": 0,
        # sql_status == "SKIPPED" (intent BLOCK으로 SQL 문장 검사를 생략한 케이스) 집계
        "sql_skipped_count": 0,
        "final_block_count": 0,
        "llm_skipped_by_intent_count": 0,
    }
    for result in results:
        status = result.get("actual_status")  # = final_status
        if status == "PASS":
            summary["pass_count"] += 1
        elif status == "WARNING":
            summary["warning_count"] += 1
        elif status == "BLOCK":
            summary["block_count"] += 1

        if result.get("matched_expected"):
            summary["matched_expected_count"] += 1
        else:
            summary["mismatch_count"] += 1

        # llm_used_count는 실제 LLM을 호출한 케이스만 셉니다(의도 차단으로 생략한 케이스는 제외).
        if result.get("generation_source") == "llm":
            summary["llm_used_count"] += 1
        if result.get("llm_fallback_used"):
            summary["llm_fallback_count"] += 1
        # 생성 출처 집계(보고서 해석 안내용): mock 생성 / intent_blocked 생성 생략
        if result.get("generation_source") == "mock":
            summary["mock_used_count"] += 1
        if result.get("generation_source") == "intent_blocked":
            summary["skipped_generation_count"] += 1

        if result.get("intent_status") == "BLOCK":
            summary["intent_block_count"] += 1
        elif result.get("intent_status") == "WARNING":
            summary["intent_warning_count"] += 1
        if result.get("sql_status") == "BLOCK":
            summary["sql_block_count"] += 1
        elif result.get("sql_status") == "SKIPPED":
            summary["sql_skipped_count"] += 1
        if result.get("final_status") == "BLOCK":
            summary["final_block_count"] += 1
        if result.get("generation_source") == "intent_blocked":
            summary["llm_skipped_by_intent_count"] += 1
    return summary


def write_llm_batch_outputs(results: list[dict], summary: dict) -> None:
    """LLM Batch 결과를 전용 JSON/Markdown으로 저장합니다(기본 Batch 산출물은 건드리지 않음)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # (1) JSON 저장
    payload = {"summary": summary, "results": results}
    LLM_BATCH_RESULT_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # (2) Markdown 보고서 저장
    total = summary.get("total_cases", 0)
    fallback = summary.get("llm_fallback_count", 0)
    used = summary.get("llm_used_count", 0)

    lines: list[str] = []
    lines.append("# Day4 Text-to-SQL LLM Batch Report")
    lines.append("")
    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"- Total cases: {total}")
    lines.append(f"- PASS: {summary.get('pass_count', 0)}")
    lines.append(f"- WARNING: {summary.get('warning_count', 0)}")
    lines.append(f"- BLOCK: {summary.get('block_count', 0)}")
    lines.append(f"- Matched expected: {summary.get('matched_expected_count', 0)}")
    lines.append(f"- Mismatch: {summary.get('mismatch_count', 0)}")
    lines.append(f"- LLM used count: {used}")
    lines.append(f"- LLM fallback count: {fallback}")
    lines.append(f"- Mock used count: {summary.get('mock_used_count', 0)}")
    lines.append(f"- Skipped generation count: {summary.get('skipped_generation_count', 0)}")
    lines.append(f"- Intent BLOCK: {summary.get('intent_block_count', 0)}")
    lines.append(f"- Intent WARNING: {summary.get('intent_warning_count', 0)}")
    lines.append(f"- SQL BLOCK: {summary.get('sql_block_count', 0)}")
    lines.append(f"- SQL SKIPPED: {summary.get('sql_skipped_count', 0)}")
    lines.append(f"- Final BLOCK: {summary.get('final_block_count', 0)}")
    lines.append(f"- LLM skipped by intent: {summary.get('llm_skipped_by_intent_count', 0)}")
    lines.append("")
    # 실제 LLM 여부 안내 문구
    if total > 0 and fallback == total:
        lines.append("> 안내: llm_fallback_count가 total_cases와 같습니다. 실제 LLM이 아니라 mock fallback으로 실행되었습니다.")
    if used > 0:
        lines.append("> 안내: llm_used_count가 0보다 큽니다. 실제 LLM이 생성한 SQL이 포함되어 있습니다.")
    lines.append("")

    # ──────────────────────────────────────────────────────────────
    # 실행 해석 안내 섹션 (보고서 해석을 돕는 안내일 뿐, 판정 로직과 무관)
    # ──────────────────────────────────────────────────────────────
    lines.append("## 2. 실행 해석 안내")
    lines.append("")

    # 2-1. 실제 LLM 사용 여부
    lines.append("### 2-1. 실제 LLM 사용 여부")
    lines.append("")
    if used == 0:
        lines.append(
            "- 이번 LLM Batch는 실제 외부 LLM을 호출하지 않았습니다(llm_used_count=0). "
            "결과는 `mock_text_to_sql()` 기반 생성 또는 intent_blocked(생성 생략)으로 "
            "안전성 흐름을 검증한 실행입니다."
        )
        lines.append("- 따라서 이 결과를 실제 LLM 검증으로 해석하면 안 됩니다.")
    else:
        lines.append(f"- 실제 LLM이 생성한 SQL이 {used}건 포함되어 있습니다(llm_used_count={used}).")
    lines.append(
        f"- 생성 출처 집계: LLM {used}건 / mock {summary.get('mock_used_count', 0)}건 / "
        f"생성 생략(intent_blocked) {summary.get('skipped_generation_count', 0)}건"
    )
    lines.append("")

    # 2-2. 상태값(status) 범례
    lines.append("### 2-2. 상태값(status) 범례")
    lines.append("")
    lines.append("- intent_status: 사용자 질문의 의도를 기준으로 사전에 허용/차단 여부를 판단한 상태")
    lines.append("- sql_status: 생성된 SQL 문장 자체에 SQL Safety 검사를 수행한 결과 상태")
    lines.append("- final_status: intent_status와 sql_status를 병합한 최종 안전 판정 상태(실행 가능 여부 기준)")
    lines.append(
        "- actual_status: expected_status와 비교하기 위한 대표 실행 상태. "
        "현재 구조에서는 하위 호환을 위해 final_status와 동일하게 유지됩니다."
    )
    lines.append(
        "- SKIPPED: Intent 단계에서 이미 차단되어 SQL 생성 또는 SQL 검사를 수행하지 않은 상태. "
        "PASS가 아니라 '검사 생략'을 의미하며, 최종 차단 여부는 final_status로 확인해야 합니다."
    )
    lines.append("")

    # 2-3. generation_source 범례 (실제 결과에 기록된 값만 설명 — 없는 값은 표시하지 않음)
    lines.append("### 2-3. generation_source 범례")
    lines.append("")
    source_desc = {
        "mock": "실제 LLM이 아니라 mock_text_to_sql() 규칙 기반으로 SQL을 생성한 경우",
        "llm": "실제 LLM 호출 결과로 SQL을 생성한 경우",
        "llm_fallback_mock": "LLM 호출에 실패해 mock으로 대체 생성한 경우",
        "intent_blocked": "Intent Safety에서 차단되어 SQL 생성을 생략한 경우(SQL 검사는 SKIPPED)",
    }
    present_sources: list[str] = []
    for r in results:
        src = r.get("generation_source")
        if src and src not in present_sources:
            present_sources.append(src)
    for src in present_sources:
        lines.append(f"- `{src}`: {source_desc.get(src, '설명이 정의되지 않은 값')}")
    lines.append("")

    # Case Results 표
    lines.append("## 3. Case Results")
    lines.append("")
    lines.append("| Case ID | Category | Expected | Intent | SQL | Final | Matched | Generation |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {_escape_table_cell(r.get('case_id'))} "
            f"| {_escape_table_cell(r.get('category'))} "
            f"| {_escape_table_cell(r.get('expected_status'))} "
            f"| {_escape_table_cell(r.get('intent_status'))} "
            f"| {_escape_table_cell(r.get('sql_status'))} "
            f"| {_escape_table_cell(r.get('final_status'))} "
            f"| {_escape_table_cell(r.get('matched_expected'))} "
            f"| {_escape_table_cell(r.get('generation_source'))} |"
        )
    lines.append("")

    # LLM 생성 SQL 상세
    lines.append("## 4. LLM Generated SQL Details")
    lines.append("")
    for r in results:
        preview = r.get("raw_llm_response_preview")
        lines.append(f"### {r.get('case_id')}")
        lines.append("")
        lines.append(f"- User Query: {r.get('user_query', '')}")
        lines.append(f"- Dataset SQL: `{_escape_table_cell(r.get('dataset_generated_sql'))}`")
        lines.append(f"- LLM Generated SQL: `{_escape_table_cell(r.get('llm_generated_sql'))}`")
        lines.append(f"- Expected / Actual(Final): {r.get('expected_status')} / {r.get('final_status')}")
        lines.append(f"- Intent Status: {r.get('intent_status')}")
        lines.append(f"- SQL Status: {r.get('sql_status')}")
        lines.append(f"- Final Status: {r.get('final_status')}")
        lines.append(f"- Matched Expected: {r.get('matched_expected')}")
        lines.append(f"- LLM Mode: {r.get('llm_mode')}")
        lines.append(f"- Generation Source: {r.get('generation_source')}")
        lines.append(f"- Fallback Used: {r.get('llm_fallback_used')}")
        lines.append(f"- Fallback Reason: {r.get('llm_fallback_reason') or '없음'}")
        lines.append(f"- Raw LLM Response Preview: {_escape_table_cell(preview) if preview else '없음'}")
        intent_blocked = r.get("intent_blocked_reasons", [])
        intent_warns = r.get("intent_warnings", [])
        sql_blocked = r.get("sql_blocked_reasons", r.get("blocked_reasons", []))
        sql_warns = r.get("sql_warnings", r.get("warnings", []))
        lines.append(f"- Intent Blocked Reasons: {' / '.join(intent_blocked) if intent_blocked else '없음'}")
        lines.append(f"- Intent Warnings: {' / '.join(intent_warns) if intent_warns else '없음'}")
        lines.append(f"- SQL Blocked Reasons: {' / '.join(sql_blocked) if sql_blocked else '없음'}")
        lines.append(f"- SQL Warnings: {' / '.join(sql_warns) if sql_warns else '없음'}")
        if r.get("generation_source") == "intent_blocked":
            lines.append("- Generation Note: SQL generation was skipped by intent safety.")
            lines.append("- 이 케이스의 실제 차단 근거는 SQL Blocked Reasons가 아니라 Intent Blocked Reasons입니다.")
            lines.append("- SQL Status는 SKIPPED이며, SQL 문장 검사는 수행하지 않았습니다.")
        else:
            lines.append("- Generation Note: 없음")
        lines.append(f"- Detected Tables: {', '.join(r.get('detected_tables', [])) or '없음'}")
        lines.append(f"- Detected Sensitive Columns: {', '.join(r.get('detected_sensitive_columns', [])) or '없음'}")
        lines.append(f"- Detected Injection Patterns: {', '.join(r.get('detected_injection_patterns', [])) or '없음'}")
        lines.append("")

    # Teaching Notes
    lines.append("## 5. Teaching Notes")
    lines.append("")
    lines.append("- 기본 Batch는 사람이 준비한 SQL을 검사한다.")
    lines.append("- LLM Batch는 같은 user_query를 실제 LLM에 보내 새 SQL을 생성한다.")
    lines.append("- 두 결과는 달라질 수 있다.")
    lines.append("- 모델이 바뀌면 SQL 생성 결과와 Safety 판정도 달라질 수 있다.")
    lines.append("- 어떤 모델이 SQL을 생성하더라도 Safety Checker를 반드시 통과해야 한다.")
    lines.append("- fallback_count가 높으면 실제 LLM 테스트가 아니라 mock 기반 테스트였을 수 있다.")
    lines.append("- LLM이 안전한 SELECT를 생성하더라도 사용자 의도가 데이터 변경, 삭제, 민감정보 조회라면 최종 판정은 BLOCK입니다.")
    lines.append("- Text-to-SQL 안전성은 SQL 문자열만 검사하는 것이 아니라 사용자 의도와 생성 SQL을 함께 검사해야 합니다.")
    lines.append("- Intent Safety는 SQL 생성 전 Gate이고, SQL Safety는 생성 후 Gate입니다.")
    lines.append("- 최종 실행 가능 여부는 final_status 기준으로 판단합니다.")
    lines.append("- 전체/모든 조회는 무조건 BLOCK이 아니며, 제한 없는 조회는 BLOCK, 넓은 조회는 WARNING으로 구분합니다.")
    lines.append("")

    LLM_BATCH_REPORT_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def run_llm_batch() -> None:
    """--llm-batch: dataset의 각 user_query를 실제 LLM(실패 시 mock)으로 SQL 변환 후 검사합니다."""
    print("[Day4 Text-to-SQL Safety Checker] LLM Batch 모드")
    cases = load_cases()
    if not cases:
        print("평가할 테스트 케이스가 없습니다.")
        return

    results: list[dict] = []
    llm_mode_seen = None
    quality_gate_map = {"PASS": "pass", "WARNING": "warning", "BLOCK": "fail"}
    for case in cases:
        user_query = str(case.get("user_query", "") or "")
        dataset_sql = str(case.get("generated_sql", "") or "")

        # (1) Intent Safety: SQL 생성 전 사용자 의도 게이트
        intent_safety = check_user_intent_safety(user_query)

        # (2) 명확한 BLOCK 의도면 LLM 호출과 SQL 문장 검사를 모두 생략합니다.
        #     - placeholder는 SQL 주석(/* */)을 쓰지 않습니다 → sql_comment 오탐 방지.
        if intent_safety["intent_status"] == "BLOCK" and not intent_safety["should_generate_sql"]:
            llm_sql = "SQL generation skipped by intent safety"
            gen_meta = {
                "generation_source": "intent_blocked",
                "llm_mode": "skipped_by_intent",
                "llm_fallback_used": False,
                "llm_fallback_reason": None,
                "raw_llm_response_preview": "SQL generation skipped by intent safety.",
            }
            # (3a) SQL 문장 검사 생략 → SKIPPED 진단 상태 (placeholder를 검사하지 않음)
            safety = _skipped_sql_safety()
        else:
            # 같은 user_query를 LLM으로 새로 SQL 변환 (실패 시 mock fallback)
            llm_sql, gen_meta = llm_text_to_sql(user_query)
            # (3b) SQL Safety: 실제 생성된 SQL 문장 검사
            safety = check_sql_safety(llm_sql)

        # (4) Final Safety: 의도 + SQL 병합 → final_status
        final_safety = merge_intent_and_sql_safety(intent_safety, safety)
        final_status = final_safety["final_status"]

        # (5) expected_status 비교는 final_status 기준으로 합니다.
        matched_expected = final_status == case.get("expected_status")

        record = build_trace_record(
            mode="llm_batch",
            generated_sql=llm_sql,
            safety=safety,
            user_query=user_query,
            generation_source=gen_meta.get("generation_source", "mock"),
            gen_meta=gen_meta,
            case=case,
            intent_status=final_safety["intent_status"],
            sql_status=final_safety["sql_status"],
            final_status=final_status,
            intent_blocked_reasons=final_safety["intent_blocked_reasons"],
            intent_warnings=final_safety["intent_warnings"],
        )
        # LLM Batch의 Trace 최종 판정/일치 여부는 final_status 기준으로 재정의합니다.
        record["actual_status"] = final_status
        record["matched_expected"] = matched_expected
        record["quality_gate_signal"] = quality_gate_map.get(final_status, "warning")
        append_trace_log(record)
        llm_mode_seen = gen_meta.get("llm_mode") or llm_mode_seen

        results.append(
            {
                "case_id": case.get("case_id"),
                "trace_id": record["trace_id"],
                "category": case.get("category"),
                "user_query": user_query,
                "dataset_generated_sql": dataset_sql,
                "llm_generated_sql": llm_sql,
                "expected_status": case.get("expected_status"),
                # 기존 호환: actual_status는 final_status와 같게 둡니다.
                "actual_status": final_status,
                "intent_status": final_safety["intent_status"],
                "sql_status": final_safety["sql_status"],
                "final_status": final_status,
                "matched_expected": matched_expected,
                "generation_source": gen_meta.get("generation_source"),
                "llm_mode": gen_meta.get("llm_mode"),
                "llm_fallback_used": gen_meta.get("llm_fallback_used", False),
                "llm_fallback_reason": gen_meta.get("llm_fallback_reason"),
                "raw_llm_response_preview": gen_meta.get("raw_llm_response_preview"),
                "intent_blocked_reasons": final_safety["intent_blocked_reasons"],
                "intent_warnings": final_safety["intent_warnings"],
                "sql_blocked_reasons": final_safety["sql_blocked_reasons"],
                "sql_warnings": final_safety["sql_warnings"],
                # 기존 필드 유지(현재는 SQL 단계 결과를 노출)
                "warnings": safety["warnings"],
                "blocked_reasons": safety["blocked_reasons"],
                "detected_tables": safety["detected_tables"],
                "detected_sensitive_columns": safety["detected_sensitive_columns"],
                "detected_injection_patterns": safety["detected_injection_patterns"],
            }
        )

    summary = build_llm_batch_summary(results)
    write_llm_batch_outputs(results, summary)

    # 콘솔 요약
    print(f"입력 파일: {DATA_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"LLM mode: {llm_mode_seen or '-'}")
    print(f"총 케이스: {summary['total_cases']}")
    print(f"PASS: {summary['pass_count']} / WARNING: {summary['warning_count']} / BLOCK: {summary['block_count']} (final_status 기준)")
    print(f"기대와 일치: {summary['matched_expected_count']} / 불일치: {summary['mismatch_count']}")
    print(
        f"Intent BLOCK: {summary['intent_block_count']} / Intent WARNING: {summary['intent_warning_count']} / "
        f"SQL BLOCK: {summary['sql_block_count']} / Final BLOCK: {summary['final_block_count']}"
    )
    print(f"LLM used: {summary['llm_used_count']} / LLM fallback: {summary['llm_fallback_count']} / LLM skipped by intent: {summary['llm_skipped_by_intent_count']}")
    print("결과 저장:")
    print(f"- {LLM_BATCH_RESULT_JSON_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"- {LLM_BATCH_REPORT_MD_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"- {TRACE_LOG_PATH.relative_to(PROJECT_ROOT).as_posix()}")

    if summary["total_cases"] > 0 and summary["llm_fallback_count"] == summary["total_cases"]:
        print("[안내] 전부 mock fallback으로 실행되었습니다(실제 LLM 아님). 보고서를 확인해 주세요.")


# ──────────────────────────────────────────────────────────────────────
# 10. main (argparse)
# ──────────────────────────────────────────────────────────────────────
def main() -> None:
    """명령행 옵션을 해석해 알맞은 실행 모드를 고릅니다. 옵션이 없으면 Batch 모드입니다."""
    parser = argparse.ArgumentParser(
        description="Day4 Text-to-SQL 안전성 검증기 (SQL 실행 전 PASS/WARNING/BLOCK 판정)"
    )
    parser.add_argument("--sql", help="직접 입력한 SQL을 검사합니다.")
    parser.add_argument("--ask", help="자연어를 mock Text-to-SQL로 변환해 검사합니다.")
    parser.add_argument("--llm-ask", dest="llm_ask", help="자연어를 LLM으로 변환해 검사합니다(실패 시 mock).")
    parser.add_argument("--interactive", action="store_true", help="대화형 모드로 실행합니다.")
    parser.add_argument(
        "--llm-batch",
        dest="llm_batch",
        action="store_true",
        help="data/day4_text_to_sql_cases.json의 user_query를 실제 LLM으로 변환해 전체 평가합니다.",
    )
    args = parser.parse_args()

    # 여러 모드 옵션이 동시에 들어오면 하나만 쓰도록 안내합니다.
    selected = [
        name
        for name, value in (
            ("--sql", args.sql),
            ("--ask", args.ask),
            ("--llm-ask", args.llm_ask),
            ("--interactive", args.interactive),
            ("--llm-batch", args.llm_batch),
        )
        if value
    ]
    if len(selected) > 1:
        print(f"[안내] 한 번에 하나의 모드만 사용해 주세요. 입력된 옵션: {', '.join(selected)}")
        return

    if args.sql:
        run_direct_sql(args.sql)
    elif args.ask:
        run_mock_ask(args.ask)
    elif args.llm_ask:
        run_llm_ask(args.llm_ask)
    elif args.interactive:
        run_interactive()
    elif args.llm_batch:
        run_llm_batch()
    else:
        run_batch()


if __name__ == "__main__":
    main()
