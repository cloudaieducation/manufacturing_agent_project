# -*- coding: utf-8 -*-
"""
Day5 mcp_server_final - DB Access (PostgreSQL 읽기 전용 접근 계층)

[이 모듈의 역할]
repositories.py 가 사용할 'PostgreSQL 읽기 전용' 저수준 접근 계층입니다.
연결 생성 / SELECT 전용 실행 / 결과 dict 변환 / 안전 예외 처리를 한 곳에 모읍니다.

[DB 종류 — 매우 중요]
이 프로젝트의 DB 는 SQLite 가 아니라 **PostgreSQL**(db/docker-compose.yml 의 postgres:16)입니다.
따라서 sqlite3 / *.db / MCP_SERVER03_DB_PATH 같은 파일경로 모델은 사용하지 않으며,
psycopg2 + POSTGRES_* 환경변수로 접속합니다.

[day3 와의 관계]
src/day3/postgres_db_tool.py 의 '연결 방식(psycopg2.connect), RealDictCursor, params 바인딩,
closing 으로 커넥션 닫기' 아이디어만 참고했습니다. day3 파일을 import 하거나 함수를 통째로
복사하지 않았고, day3 의 전체컬럼(별표) 조회 방식은 쓰지 않습니다(컬럼 명시 SELECT 는 repositories.py).

[보안 원칙]
- raw SQL 을 외부 Tool argument 로 받지 않는다. fetch_* 는 repositories 내부 고정 SQL 만 받는다.
- 반드시 parameter binding(%s) 으로만 값 전달(SQL 인젝션 방지).
- SELECT 전용. INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE 등은 실행하지 않는다(이중 방어).
- 세션을 default_transaction_read_only=on 으로 열어 쓰기를 한 번 더 차단한다.
- POSTGRES_PASSWORD 등 접속 비밀값은 절대 로그/반환에 노출하지 않는다.
- DB 스키마를 수정하지 않는다.

[예외 정책]
- DBUnavailableError: 연결 실패(미기동/네트워크). 호출부(equipment_data)는 mock fallback 가능.
- ValueError: 잘못된 SQL(SELECT 아님 등) / 사용 오류. mock 으로 숨기지 않는다.
"""
import os   # POSTGRES_* 접속 환경변수를 읽기 위해 사용(접속 정보를 코드에 직접 쓰지 않는다).
import re   # SELECT 전용/쓰기 키워드 차단을 검사하는 방어용 정규식에 사용.
from contextlib import closing  # 커넥션/커서를 with 블록 종료 시 확실히 닫기 위해 사용(누수 방지).

# psycopg2: PostgreSQL 드라이버. SQLite/파일 DB 가 아니라 실제 PostgreSQL 에 접속한다.
import psycopg2
# RealDictCursor: 조회 결과 row 를 dict(컬럼명 → 값)로 받기 위한 커서.
#                 row 를 그대로 JSON/응답에 쓰기 좋게 하려고 사용한다(DB row → dict 변환).
from psycopg2.extras import RealDictCursor


class DBUnavailableError(Exception):
    """PostgreSQL 연결 실패(미기동/네트워크 등). mock fallback 대상 신호."""


# SELECT 전용 방어용: 첫 토큰은 SELECT/WITH 만 허용.
_ALLOWED_PREFIX = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
# 쓰기/DDL 키워드(단어 경계). 하나라도 있으면 실행하지 않는다(이중 방어).
_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|copy|call|do)\b",
    re.IGNORECASE,
)

# limit 안전 상한(과도 조회 방지). repositories 가 넘긴 limit 도 이 상한으로 깎인다.
_MAX_LIMIT = 100
_DEFAULT_LIMIT = 10

# 연결/쿼리 타임아웃(초/밀리초). 미기동 환경에서 빨리 실패해 mock fallback 으로 넘어가게 한다.
_CONNECT_TIMEOUT = 3
_STATEMENT_TIMEOUT_MS = 5000

# is_postgres_available() 결과 캐시(런타임 중 DB 가동 상태는 잘 바뀌지 않으므로 1회 확인 후 재사용).
_availability_cache = {"checked": False, "value": False}


def get_db_config():
    """POSTGRES_* 환경변수에서 접속 설정을 읽어 dict 로 돌려준다.

    [기본값] db/docker-compose.yml 과 일치(localhost:5432 / manufacturing_agent_db / agent_user).
    [주의] 반환 dict 에는 password 가 포함되므로 '로그/콘솔/응답에 그대로 출력하지 않는다'.
           표시용으로는 safe_db_config() 를 사용한다.
    """
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "manufacturing_agent_db"),
        "user": os.getenv("POSTGRES_USER", "agent_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "agent_password"),
    }


def safe_db_config():
    """표시/로그용 접속 설정(비밀값은 [REDACTED])."""
    cfg = get_db_config()
    return {**cfg, "password": "[REDACTED]"}


def get_connection():
    """PostgreSQL 읽기 전용 연결을 생성한다.

    [반환] psycopg2 연결 객체.
    [예외] 연결 실패 시 DBUnavailableError(원본 메시지는 비밀값이 섞일 수 있어 축약/마스킹).

    [읽기 전용 강제]
        options 로 default_transaction_read_only=on 을 설정해 세션 차원에서 쓰기를 막는다.
        statement_timeout 으로 장시간 쿼리를 방지한다.
    """
    cfg = get_db_config()
    options = f"-c default_transaction_read_only=on -c statement_timeout={_STATEMENT_TIMEOUT_MS}"
    try:
        return psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["dbname"],
            user=cfg["user"],
            password=cfg["password"],
            connect_timeout=_CONNECT_TIMEOUT,
            options=options,
        )
    except Exception as error:
        # 연결 실패 메시지에 호스트/계정 등이 섞일 수 있어, 타입명만 남기고 비밀값은 노출하지 않는다.
        raise DBUnavailableError(f"PostgreSQL 연결 실패: {type(error).__name__}") from None


def _assert_select_only(sql: str) -> None:
    """주어진 SQL 이 SELECT 전용인지 방어적으로 검사한다(이중 방어).

    - 첫 토큰이 SELECT/WITH 가 아니면 ValueError.
    - 쓰기/DDL 키워드가 포함되면 ValueError.
    - 여러 문장(중간 세미콜론)으로 보이면 ValueError(스택 쿼리 차단).
    [주의] 이 검사는 보조 방어선이며, 1차 방어는 'repositories 의 고정 SQL + parameter binding' 이다.
    """
    text = str(sql or "")
    if not _ALLOWED_PREFIX.search(text):
        raise ValueError("SELECT/WITH 로 시작하는 조회문만 허용됩니다.")
    if _FORBIDDEN_SQL.search(text):
        raise ValueError("쓰기/DDL 키워드가 포함된 SQL 은 실행할 수 없습니다(SELECT 전용).")
    # 마지막 세미콜론 1개는 허용하되, 중간 세미콜론(스택 쿼리)은 막는다.
    if ";" in text.rstrip().rstrip(";"):
        raise ValueError("복수 SQL 문(세미콜론 분리)은 허용되지 않습니다.")


def _safe_limit(limit):
    """limit 을 1.._MAX_LIMIT 범위 정수로 강제(None/이상치는 기본값)."""
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT
    if n < 1:
        return _DEFAULT_LIMIT
    return min(n, _MAX_LIMIT)


def fetch_all(sql: str, params=None, limit=None):
    """SELECT 결과 전체를 list[dict] 로 반환한다(내부 repository 전용).

    [입력]
        sql   : repositories 내부 '고정 SQL'(외부 Tool argument 가 아님).
        params: parameter binding 값(tuple/dict). 사용자 입력은 반드시 여기로만 전달.
        limit : 참고용 상한(실제 LIMIT 절은 sql 에 두고, 여기서는 안전 상한만 검증).
    [반환] list[dict] (결과 없으면 빈 list).
    [예외]
        DBUnavailableError: 연결 실패(mock fallback 대상).
        ValueError        : SELECT 전용 위반 등(숨기지 않고 전달).

    [보안] raw SQL 을 외부에 노출하지 않는다. 이 함수는 repositories 에서만 호출한다.
    """
    _assert_select_only(sql)
    if limit is not None:
        _safe_limit(limit)  # 상한 검증(값 자체는 sql 의 LIMIT 파라미터로 전달됨)
    bind = params if params is not None else ()
    try:
        # closing() 으로 with 블록을 벗어날 때 커넥션을 자동으로 닫아 누수를 막는다.
        # RealDictCursor 를 쓰면 결과 행이 (값, 값, ...) 튜플이 아니라 {컬럼명: 값} dict 로 와서,
        # 이후 MCP 응답(JSON dict) 으로 변환하기 쉽다(컬럼 의미가 키에 그대로 드러남).
        with closing(get_connection()) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # 값은 bind(%s 파라미터)로만 전달한다 — sql 문자열에 직접 합치지 않는다(SQL 인젝션 방지).
                cursor.execute(sql, bind)
                rows = cursor.fetchall()
                # 조회 결과가 0건이어도 '실패'가 아니라 '없음'이다 → 빈 list 를 그대로 돌려준다.
                # (호출부 equipment_data 는 '결과 없음'을 mock fallback 대상으로 보지 않는다.)
                return [dict(row) for row in rows]
    # [예외 구분 — mock fallback 판단의 핵심 포인트]
    # (1) DBUnavailableError(연결 실패: 미기동/네트워크)는 그대로 올려, 호출부가 mock fallback 하게 한다.
    except DBUnavailableError:
        raise
    # (2) 그 외(테이블 없음/SQL 오류 등 '쿼리 실행 단계' 예외)는 ValueError 로 올려 숨기지 않는다.
    #     연결은 됐는데 쿼리가 잘못된 경우이므로 mock 으로 조용히 덮지 않고 드러낸다.
    #     원본 메시지에는 내부 정보가 섞일 수 있어 타입명만 남기고, from None 으로 원본 트레이스를 차단한다.
    except Exception as error:
        raise ValueError(f"DB 조회 실패: {type(error).__name__}") from None


def fetch_one(sql: str, params=None):
    """SELECT 결과 첫 행만 dict 로 반환한다(없으면 None). 내부 repository 전용."""
    rows = fetch_all(sql, params=params)
    return rows[0] if rows else None


def is_postgres_available(use_cache: bool = True) -> bool:
    """PostgreSQL 연결 가능 여부를 돌려준다(예외 없이 True/False).

    [동작]
        간단한 연결 시도로 가용성을 확인한다. 런타임 중 상태가 잘 바뀌지 않으므로 결과를 캐시한다.
        equipment_data 가 매 호출마다 느린 연결 타임아웃을 겪지 않도록 캐시를 둔다.
    [주의] 비밀값/연결 문자열은 출력하지 않는다.
    """
    if use_cache and _availability_cache["checked"]:
        return _availability_cache["value"]
    available = False
    try:
        with closing(get_connection()):
            available = True
    except Exception:
        available = False
    _availability_cache["checked"] = True
    _availability_cache["value"] = available
    return available


def reset_availability_cache() -> None:
    """가용성 캐시를 초기화한다(테스트/재확인용)."""
    _availability_cache["checked"] = False
    _availability_cache["value"] = False
