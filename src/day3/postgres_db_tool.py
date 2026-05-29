"""
Day3 PostgreSQL 제조 DB Tool 단순화 버전

교육용 제조 AI Agent 실습에서 PostgreSQL 데이터를 조회하기 위한 최소 Tool 모듈입니다.

[이 파일이 Day3 아키텍처에서 맡는 역할]
- 이 파일은 단순한 "DB 조회 코드"가 아니라, 제조 DB/Log 조회 기능을 Agent가
  호출할 수 있는 "Tool" 형태로 감싸 주는 계층입니다.
- 학습 목표는 SQL 문법을 익히는 것이 아니라, "DB 기능을 어떻게 Agent Tool로
  포장하는가"라는 설계 구조를 이해하는 것입니다.
- 여기서 정의한 함수들은 그대로 MCP Server(manufacturing_mcp_server.py)와
  fallback registry(tool_registry_fallback.py)에서 Tool로 등록되어,
  DBInvestigationAgent 같은 Agent가 호출하게 됩니다.

[중요: 여기서 다루는 PostgreSQL은 실제 사내 DB가 아닙니다]
- 본 실습의 PostgreSQL은 docker compose로 띄우는 교육용 샘플 환경이며,
  설비 ID(EQP-*), 알람 코드(ALM-*), 라인 ID(LINE-*)는 모두 가상의 값입니다.
- 실제 운영 DB가 아니므로, 여기서 보이는 테이블/필드 구조도 교육용 예시입니다.

특징:
- 외부 DB 연결 모듈을 import하지 않습니다. (psycopg2만 직접 사용)
- 프로젝트 루트의 .env 파일에서 PostgreSQL 접속 정보를 읽습니다.
- DB 비밀번호, API Key, 전체 환경변수 값은 출력하지 않습니다. (보안 원칙)
- 복잡한 오류 처리 대신 Python 오류가 그대로 보이도록 둡니다. (교육용으로 의도된 단순화)
- MCP Server/Client가 사용할 수 있도록 개별 DB Tool 6개를 제공합니다.

[현업 적용 시 검토 포인트 — 전체 모듈 공통]
- DB 접속 정보(host/계정/비밀번호)는 .env 평문이 아니라 사내 보안 저장소(Vault 등)나
  관리형 시크릿으로 다뤄야 합니다.
- 테이블 구조, 조회 권한(읽기 전용 계정), row limit, 반환 필드 범위, 감사 로그(누가 무엇을
  조회했는지)를 함께 설계해야 Agent가 안전하게 DB를 다룰 수 있습니다.
"""

from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path
from typing import Any

import psycopg2
# RealDictCursor를 쓰면 조회 결과가 (값, 값, ...) 튜플이 아니라
# {컬럼명: 값} 형태의 dict로 돌아옵니다.
# Agent/MCP가 결과를 JSON으로 다루기 쉬워지므로 일부러 이 커서를 사용합니다.
from psycopg2.extras import RealDictCursor

# python-dotenv가 설치되어 있으면 .env를 자동 로딩하고,
# 없으면 아래 get_connection()에서 직접 파싱하는 방식으로 동작합니다.
# (교육 환경마다 설치 상태가 달라도 멈추지 않도록 한 방어 코드입니다.)
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


# parents[2] = 프로젝트 루트 (src/day3/이 파일 → src → 프로젝트 루트)
# .env는 프로젝트 루트 바로 아래에 있다고 가정합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"


def get_connection():
    """
    PostgreSQL DB 연결 객체를 반환합니다.

    설계 의미:
        - 모든 DB Tool 함수가 이 함수 하나만 통해 접속하도록 하여,
          접속 정보 관리 지점을 한 곳으로 모읍니다. (접속 설정의 단일 진입점)
        - 접속 정보는 코드에 하드코딩하지 않고 .env 환경변수에서 읽습니다.

    입력: 없음 (환경변수에서 접속 정보를 읽음)
    출력: psycopg2 연결 객체

    현업 적용 시:
        - host/계정/비밀번호는 .env 평문이 아니라 보안 저장소나 관리형 시크릿으로
          관리해야 하며, 가능하면 읽기 전용(read-only) 계정을 사용해야 합니다.
    """
    # .env가 없으면 접속 정보를 알 수 없으므로 명확한 오류로 멈춥니다.
    if not ENV_PATH.exists():
        raise FileNotFoundError(f".env 파일을 찾을 수 없습니다: {ENV_PATH}")

    # python-dotenv가 있으면 표준 방식으로 .env를 로딩합니다.
    if load_dotenv is not None:
        load_dotenv(dotenv_path=ENV_PATH, override=True)
    else:
        # dotenv가 없을 때를 대비한 최소 파서입니다.
        # 주석(#)이나 '=' 없는 줄은 건너뛰고, KEY=VALUE 형식만 환경변수로 등록합니다.
        # 따옴표로 감싼 값도 처리할 수 있게 양끝 따옴표를 제거합니다.
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")

    # os.getenv의 두 번째 인자는 "환경변수가 없을 때 쓰는 기본값"입니다.
    # 교육 환경에서 .env 설정을 빠뜨려도 로컬 docker DB로 바로 붙도록 기본값을 둡니다.
    # 현업에서는 이런 기본 계정/비밀번호를 코드에 두지 않습니다.
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

    설계 의미:
        - 개별 Tool 함수들이 직접 커넥션/커서를 다루지 않도록 공통화한 헬퍼입니다.
        - params를 SQL과 분리해서 넘기므로, 값이 SQL에 직접 끼어드는 SQL Injection을
          예방합니다. (반드시 %s 자리표시자 + params 튜플 방식을 사용)

    입력: query(SQL 문자열), params(바인딩할 값 튜플)
    출력: 첫 행 dict 또는 None
    """
    # closing()으로 감싸면 with 블록을 벗어날 때 커넥션을 자동으로 닫아,
    # 커넥션 누수를 방지합니다.
    with closing(get_connection()) as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            # 결과가 없을 때 빈 dict가 아니라 None을 돌려주어,
            # 호출 측이 "조회 실패/없음"을 명확히 구분할 수 있게 합니다.
            if row is None:
                return None
            return dict(row)


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """
    SELECT 결과 전체를 list[dict] 형태로 반환합니다.

    설계 의미:
        - 여러 행을 돌려주는 모든 DB Tool(알람 이력, 공정 상태 등)이 공유하는 헬퍼입니다.
        - fetch_one과 마찬가지로 params 바인딩 방식을 강제해 안전하게 조회합니다.

    입력: query(SQL 문자열), params(바인딩할 값 튜플)
    출력: 행 dict들의 list (결과가 없으면 빈 list)
    """
    with closing(get_connection()) as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]


def get_equipment_status(equipment_id: str) -> dict[str, Any] | None:
    """
    설비 ID를 기준으로 설비 기본 정보만 조회하는 DB Tool입니다.

    Agent 관점:
        - 설비 ID로 그 설비가 어떤 라인/공정/설비 유형인지 등 "기본 신상 정보"를 확인합니다.
        - 반복 알람 분석에서 가장 먼저 확인하는 근거 데이터이며, 여기서 얻은 line_id는
          이후 품질 지표 조회(get_quality_metrics)의 입력으로 이어집니다.

    입력: equipment_id (예: "EQP-EV-03")
    출력: 설비 한 건의 정보 dict, 없으면 None

    현업 적용 시:
        - 조회 가능한 설비 범위(권한)와 반환 필드를 제한하고, 감사 로그 기준을 함께 설계합니다.
    """
    # SELECT에서 필요한 컬럼만 명시적으로 골라 옵니다.
    # SELECT * 대신 필요한 필드만 지정하는 것은 "Tool이 노출하는 데이터 범위를
    # 명확히 통제"하는 설계 장치입니다. (현업에서는 반환 필드를 더 엄격히 제한)
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
    # equipment_id는 단일 건 조회이므로 fetch_one을 사용합니다.
    # .strip()으로 앞뒤 공백을 정리해 입력 흔들림을 줄입니다.
    return fetch_one(query, (equipment_id.strip(),))


def get_recent_alarm_events(
    equipment_id: str,
    alarm_code: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    설비 ID를 기준으로 최근 알람 이력을 조회하는 DB Tool입니다.

    Agent 관점:
        - "이 설비에서 최근에 어떤 알람이 몇 번 떴는지"라는 실제 이력 데이터를 확인합니다.
        - 반복 알람 시나리오에서 alarm_code를 같이 넘기면 특정 알람의 재발 패턴을 봅니다.

    입력:
        - equipment_id: 설비 ID
        - alarm_code: 특정 알람만 보고 싶을 때 지정 (없으면 전체 알람 조회)
        - limit: 최대 조회 건수 (과도한 조회 방지)
    출력: 알람 이벤트 행들의 list

    현업 적용 시:
        - timestamp 인덱스, 보존 기간, row limit, 반환 필드 범위를 함께 검토합니다.
    """
    # 입력값 정리 단계입니다.
    # alarm_code는 None일 수도 있으므로, 값이 있을 때만 strip()을 적용합니다.
    equipment_id = equipment_id.strip()
    alarm_code = alarm_code.strip() if alarm_code else None
    limit = int(limit)

    # 분기 설계:
    # alarm_code가 주어졌으면 "특정 알람 코드"로 좁혀 조회하고,
    # 없으면 그 설비의 "전체 알람"을 조회합니다.
    # ORDER BY timestamp DESC + LIMIT은 "최근 것부터 N건만" 가져오기 위한 장치로,
    # 과도한 조회를 막는 설계 장치입니다.
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
    설비 ID를 기준으로 최근 공정 상태를 조회하는 DB Tool입니다.

    Agent 관점:
        - 온도/압력/진공 등 공정 상태 값을 시간순으로 확인해, 알람과의 연관성을 봅니다.
        - "알람이 떴을 때 공정 상태가 어땠는가"를 비교할 때 쓰는 근거 데이터입니다.

    입력: equipment_id, limit(최근 N건)
    출력: 공정 상태 행들의 list
    """
    # 최근 공정 상태를 timestamp 내림차순 + LIMIT로 제한해 가져옵니다.
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
    라인 ID를 기준으로 최근 품질 지표를 조회하는 DB Tool입니다.

    Agent 관점:
        - 수율/불량률 같은 품질 지표가 알람과 함께 흔들렸는지 확인합니다.
        - 다른 Tool들은 equipment_id 기준이지만, 품질 지표는 "라인(line_id)" 단위라는 점에
          유의합니다. 그래서 get_equipment_status에서 얻은 line_id가 입력으로 필요합니다.

    입력: line_id, limit(최근 N건)
    출력: 품질 지표 행들의 list
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
    설비 ID를 기준으로 최근 정비 이력을 조회하는 DB Tool입니다.

    Agent 관점:
        - 최근 점검/부품 교체/조건 변경 같은 정비 이벤트가 알람 재발의 원인인지 살펴봅니다.
        - "정비 직후부터 알람이 늘었는가" 같은 인과 가설을 세울 때 쓰는 근거입니다.

    입력: equipment_id, limit(최근 N건)
    출력: 정비 이력 행들의 list

    설계 메모:
        - 정렬 기준이 timestamp가 아니라 maintenance_date라는 점에 주의합니다.
          (정비는 "발생 시각"보다 "정비 일자" 단위로 관리되기 때문입니다.)
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
    설비 기본 정보, 최근 알람, 공정 상태, 품질 지표, 정비 이력을 한 번에 조회하는
    "통합 조회" DB Tool입니다.

    Agent 관점:
        - 여러 개별 Tool을 일일이 호출하는 대신, 한 번의 호출로 설비 주변 정보를 모아 줍니다.
        - fallback registry에서 대표 DB Tool로 등록되는 함수이기도 합니다.

    입력: equipment_id, alarm_code(선택)
    출력:
        {
            "equipment": {...},     # 설비 기본 정보
            "alarms": [...],        # 최근 알람 이력
            "process": [...],       # 최근 공정 상태
            "quality": [...],       # 최근 품질 지표 (line_id가 있을 때만)
            "maintenance": [...]    # 최근 정비 이력
        }

    설계상의 트레이드오프(현업 적용 시 주의):
        - 한 번에 많은 것을 돌려주어 편리하지만, 그만큼 이 Tool 하나의 "역할/권한 범위"가
          커집니다. Tool이 너무 많은 데이터를 한꺼번에 노출하면 권한 통제와 감사 추적이
          어려워지므로, 현업에서는 통합 Tool의 반환 범위를 신중히 제한해야 합니다.
        - 또한 내부 SQL을 새로 작성하지 않고 위의 개별 Tool 함수를 재사용하므로,
          개별 Tool이 바뀌면 이 통합 Tool 결과도 함께 바뀝니다.
    """
    equipment_id = equipment_id.strip()
    alarm_code = alarm_code.strip() if alarm_code else None

    # 1) 먼저 설비 기본 정보를 조회합니다.
    equipment = get_equipment_status(equipment_id)
    # 2) 품질 지표는 line_id가 있어야 조회할 수 있으므로, 여기서 line_id를 꺼냅니다.
    #    설비를 못 찾으면(None) line_id도 None이 됩니다.
    line_id = equipment.get("line_id") if equipment else None

    # 3) 개별 Tool들을 재사용해 결과를 하나의 dict로 묶어 반환합니다.
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
        # line_id를 못 찾았으면 품질 지표 조회를 시도조차 하지 않고 빈 list를 둡니다.
        # (없는 line_id로 조회를 시도하다 오류 나는 것을 피하는 안전 분기입니다.)
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
    6개 DB Tool을 순서대로 한 번씩 실행하는 자체 점검(self-test) 함수입니다.

    용도:
        - `python src/day3/postgres_db_tool.py`로 직접 실행했을 때,
          DB 연결과 각 Tool이 정상 동작하는지 빠르게 확인하기 위한 것입니다.
        - 여기 쓰인 EQP-EV-03, ALM-TEMP-402, LINE-07은 모두 교육용 가상 값입니다.

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
    # 이 파일을 직접 실행하면 6개 DB Tool 자체 점검만 수행합니다.
    # (다른 모듈에서 import할 때는 이 블록이 실행되지 않습니다.)
    run_sample_tests()
