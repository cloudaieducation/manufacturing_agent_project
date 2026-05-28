"""
Day3 PostgreSQL 제조 DB Tool 단순화 버전

교육용 제조 AI Agent 실습에서 PostgreSQL 데이터를 조회하기 위한 최소 Tool 모듈입니다.

특징:
- 외부 DB 연결 모듈을 import하지 않습니다.
- 프로젝트 루트의 .env 파일에서 PostgreSQL 접속 정보를 읽습니다.
- DB 비밀번호, API Key, 전체 환경변수 값은 출력하지 않습니다.
- 복잡한 오류 처리 대신 Python 오류가 그대로 보이도록 둡니다.
- MCP Server/Client가 사용할 수 있도록 개별 DB Tool 6개를 제공합니다.
"""

from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"


def get_connection():
    """
    PostgreSQL DB 연결 객체를 반환합니다.

    .env 파일은 프로젝트 루트 바로 아래의 .env 파일을 사용합니다.
    예: 프로젝트루트/.env
    """
    if not ENV_PATH.exists():
        raise FileNotFoundError(f".env 파일을 찾을 수 없습니다: {ENV_PATH}")

    if load_dotenv is not None:
        load_dotenv(dotenv_path=ENV_PATH, override=True)
    else:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "manufacturing_agent_db"),
        user=os.getenv("POSTGRES_USER", "agent_user"),
        password=os.getenv("POSTGRES_PASSWORD", "agent_password"),
    )


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    """
    SELECT 결과 중 첫 번째 행만 dict 형태로 반환합니다.
    조회 결과가 없으면 None을 반환합니다.
    """
    with closing(get_connection()) as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """
    SELECT 결과 전체를 list[dict] 형태로 반환합니다.
    """
    with closing(get_connection()) as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]


def get_equipment_status(equipment_id: str) -> dict[str, Any] | None:
    """
    설비 ID를 기준으로 설비 기본 정보만 조회합니다.
    """
    query = """
        SELECT
            equipment_id,
            line_id,
            process_name,
            equipment_type,
            location,
            criticality,
            owner_team
        FROM equipment_master
        WHERE equipment_id = %s
    """
    return fetch_one(query, (equipment_id.strip(),))


def get_recent_alarm_events(
    equipment_id: str,
    alarm_code: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    설비 ID를 기준으로 최근 알람 이력을 조회합니다.

    alarm_code가 있으면 특정 알람 코드만 조회합니다.
    """
    equipment_id = equipment_id.strip()
    alarm_code = alarm_code.strip() if alarm_code else None
    limit = int(limit)

    if alarm_code:
        query = """
            SELECT *
            FROM alarm_event_history
            WHERE equipment_id = %s
              AND alarm_code = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        return fetch_all(query, (equipment_id, alarm_code, limit))

    query = """
        SELECT *
        FROM alarm_event_history
        WHERE equipment_id = %s
        ORDER BY timestamp DESC
        LIMIT %s
    """
    return fetch_all(query, (equipment_id, limit))


def get_process_status(equipment_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    설비 ID를 기준으로 최근 공정 상태를 조회합니다.
    """
    query = """
        SELECT *
        FROM process_status
        WHERE equipment_id = %s
        ORDER BY timestamp DESC
        LIMIT %s
    """
    return fetch_all(query, (equipment_id.strip(), int(limit)))


def get_quality_metrics(line_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    라인 ID를 기준으로 최근 품질 지표를 조회합니다.
    """
    query = """
        SELECT *
        FROM quality_metrics
        WHERE line_id = %s
        ORDER BY timestamp DESC
        LIMIT %s
    """
    return fetch_all(query, (line_id.strip(), int(limit)))


def get_maintenance_history(equipment_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    설비 ID를 기준으로 최근 정비 이력을 조회합니다.
    """
    query = """
        SELECT *
        FROM maintenance_history
        WHERE equipment_id = %s
        ORDER BY maintenance_date DESC
        LIMIT %s
    """
    return fetch_all(query, (equipment_id.strip(), int(limit)))


def get_equipment_overview(
    equipment_id: str,
    alarm_code: str | None = None,
) -> dict[str, Any]:
    """
    설비 기본 정보, 최근 알람, 공정 상태, 품질 지표, 정비 이력을 한 번에 조회합니다.

    반환 구조:
    {
        "equipment": {...},
        "alarms": [...],
        "process": [...],
        "quality": [...],
        "maintenance": [...]
    }

    내부 SQL을 직접 반복하지 않고,
    위에서 만든 개별 DB Tool 함수를 재사용합니다.
    """
    equipment_id = equipment_id.strip()
    alarm_code = alarm_code.strip() if alarm_code else None

    equipment = get_equipment_status(equipment_id)
    line_id = equipment.get("line_id") if equipment else None

    return {
        "equipment": equipment,
        "alarms": get_recent_alarm_events(
            equipment_id=equipment_id,
            alarm_code=alarm_code,
            limit=5,
        ),
        "process": get_process_status(
            equipment_id=equipment_id,
            limit=3,
        ),
        "quality": get_quality_metrics(
            line_id=line_id,
            limit=3,
        ) if line_id else [],
        "maintenance": get_maintenance_history(
            equipment_id=equipment_id,
            limit=3,
        ),
    }


def run_sample_tests() -> None:
    """
    6개 DB Tool을 순서대로 한 번씩 실행합니다.

    초보자 교육용이므로 JSON pretty print나 복잡한 로그 저장은 하지 않습니다.
    """
    print("[Day3 PostgreSQL DB Tool 순차 실행 테스트]")

    print("\n1. 설비 기본 정보 조회")
    result_1 = get_equipment_status("EQP-EV-03")
    print(result_1)

    print("\n2. 최근 알람 이력 조회")
    result_2 = get_recent_alarm_events(
        equipment_id="EQP-EV-03",
        alarm_code="ALM-TEMP-402",
        limit=5,
    )
    print(result_2)

    print("\n3. 최근 공정 상태 조회")
    result_3 = get_process_status(
        equipment_id="EQP-EV-03",
        limit=3,
    )
    print(result_3)

    print("\n4. 최근 품질 지표 조회")
    result_4 = get_quality_metrics(
        line_id="LINE-07",
        limit=3,
    )
    print(result_4)

    print("\n5. 최근 정비 이력 조회")
    result_5 = get_maintenance_history(
        equipment_id="EQP-EV-03",
        limit=3,
    )
    print(result_5)

    print("\n6. 설비 통합 Overview 조회")
    result_6 = get_equipment_overview(
        equipment_id="EQP-EV-03",
        alarm_code="ALM-TEMP-402",
    )
    print(result_6)


if __name__ == "__main__":
    run_sample_tests()
