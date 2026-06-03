# -*- coding: utf-8 -*-
"""
Day5 mcp_server03 - Repositories (Tool별 고정 SQL 조회 함수)

[이 모듈의 역할]
설비/알람/공정/품질/정비 Tool 각각에 대응하는 '고정 SQL 조회 함수'를 제공합니다.
db_access.fetch_all 을 통해서만 PostgreSQL 을 읽으며, 외부에 raw SQL 실행을 노출하지 않습니다.

[핵심 보안 원칙]
- 범용 execute_sql / table_name / sql_query 는 만들지 않는다. Tool별 고정 SQL 만 둔다.
- 모든 사용자 입력은 parameter binding(%s)으로만 전달한다(문자열 결합 금지 → SQL 인젝션 방지).
- 컬럼 명시 SELECT 만 사용한다(전체컬럼 별표 조회 금지). 민감 컬럼은 애초에 SELECT 하지 않는다.
  · alarm_event_history.message / operator_note / lot_id  → 미조회
  · maintenance_history.technician_note                  → 미조회
  · equipment_master.owner_team / location               → 미조회
- limit 은 db_access 의 안전 상한으로 강제한다.

[day3 와의 관계]
src/day3/postgres_db_tool.py 의 Tool 함수 '아이디어(어떤 테이블을 어떤 키로 조회하는가)'만
참고했고, day3 의 전체컬럼(별표) 조회는 민감 컬럼을 노출하므로 **사용하지 않았다**.
여기서는 모두 컬럼 명시 SELECT 로 새로 작성했고, contract 의 any_of(process_name/line_id 등)를
위해 equipment_master 조인을 추가했다(day3 에는 없던 부분).

[DDL 기준 컬럼(db/init_manufacturing_db.sql)]
- equipment_master(equipment_id, line_id, process_name, equipment_type, location, criticality, owner_team)
- process_status(status_id, timestamp, equipment_id, temperature, pressure, vacuum_level, speed, status)
- quality_metrics(metric_id, timestamp, line_id, defect_rate, yield_rate, inspection_result, abnormal_flag)
- maintenance_history(maintenance_id, maintenance_date, equipment_id, maintenance_type, part_replaced, technician_note, downtime_min)
- alarm_event_history(alarm_id, timestamp, line_id, equipment_id, alarm_code, severity, message, lot_id, operator_note)
"""
# db_access: PostgreSQL 읽기 전용 저수준 접근 계층. 이 모듈의 모든 SQL 은 db_access.fetch_all/
#            fetch_one 을 통해서만 실행된다(연결/SELECT 전용 방어/결과 dict 변환을 한 곳에 모으기 위함).
#            repository 가 'Tool별 고정 SQL' 을, db_access 가 '안전한 실행' 을 맡아 책임을 분리한다.
from day5.mcp_server03 import db_access


class MetricNameNotAllowed(ValueError):
    """허용 목록(allowlist)에 없는 metric_name 이 들어온 경우. mock 으로 숨기지 않는다."""


# get_quality_metrics 의 metric_name → 실제 컬럼 매핑(allowlist).
# [중요] 임의 metric_name 을 SQL 컬럼명에 직접 넣지 않는다. 이 매핑에 있는 값만 컬럼으로 해석한다.
_METRIC_COLUMN_ALLOWLIST = {
    "defect_rate": "defect_rate",
    "yield_rate": "yield_rate",
    "inspection_result": "inspection_result",
    "abnormal_flag": "abnormal_flag",
}
_DEFAULT_METRIC = "defect_rate"


def get_allowed_metric_names():
    """허용된 metric_name 목록(검증/안내용)."""
    return sorted(_METRIC_COLUMN_ALLOWLIST.keys())


def get_equipment_status_rows(equipment_id=None, line_id=None, limit=10):
    """설비 현재 상태(최신 process_status)를 조회한다.

    [설계] 별도 equipment_status 테이블이 없으므로 process_status 의 최신행을 상태로 본다.
    [조건] equipment_id 직접 / 또는 line_id → equipment_master 조인으로 해당 설비들.
    [반환 컬럼] equipment_id, status, status_time(=timestamp). (센서 raw 시계열은 반환하지 않음)
    """
    # [DB 조회 흐름 — 교육용 설명]
    # 지원 Tool: get_equipment_status / 조회 테이블: process_status(상태 시계열).
    # 아래 SQL 두 개는 repository 안에 '고정'되어 있다. LLM/사용자가 SQL 을 만들지 않으므로
    # 조회 가능한 테이블·컬럼·조건이 코드로 통제된다(임의 SQL 실행 구조보다 안전).
    # equipment_id / line_id '값'은 SQL 문자열에 직접 합치지 않고 %s 파라미터 바인딩으로만 전달한다
    # → 입력값과 SQL 구조를 분리해 예기치 않은 SQL 변형을 막는다.
    safe_limit = min(int(limit) if str(limit).isdigit() else 10, 100)
    if equipment_id:
        sql = """
            SELECT ps.equipment_id AS equipment_id,
                   ps.status       AS status,
                   ps.timestamp    AS status_time
            FROM process_status AS ps
            WHERE ps.equipment_id = %s
            ORDER BY ps.timestamp DESC
            LIMIT %s
        """
        return db_access.fetch_all(sql, (equipment_id.strip(), safe_limit), limit=safe_limit)
    if line_id:
        sql = """
            SELECT ps.equipment_id AS equipment_id,
                   ps.status       AS status,
                   ps.timestamp    AS status_time
            FROM process_status AS ps
            JOIN equipment_master AS em ON em.equipment_id = ps.equipment_id
            WHERE em.line_id = %s
            ORDER BY ps.timestamp DESC
            LIMIT %s
        """
        return db_access.fetch_all(sql, (line_id.strip(), safe_limit), limit=safe_limit)
    return []


def get_recent_alarm_event_rows(equipment_id=None, alarm_code=None, date_range=None, limit=10):
    """최근 알람 이력을 조회한다(민감 컬럼 message/operator_note/lot_id 미조회).

    [반환 컬럼] equipment_id, alarm_code, severity, event_time(=timestamp).
    [조건] equipment_id 필수, alarm_code 선택. (date_range 는 추후 확장 — 현재는 미적용 표시)
    """
    if not equipment_id:
        return []
    safe_limit = min(int(limit) if str(limit).isdigit() else 10, 100)
    equipment_id = equipment_id.strip()
    alarm_code = alarm_code.strip() if alarm_code else None
    # [DB 조회 흐름 — 교육용 설명]
    # 지원 Tool: get_recent_alarm_events / 조회 테이블: alarm_event_history.
    # ORDER BY timestamp DESC + LIMIT 으로 '최근 것부터 N건만' 가져와 과도 조회를 막는다.
    # 컬럼 명시 SELECT — message / operator_note / lot_id 는 의도적으로 제외(민감/장문).
    base_cols = """
            equipment_id,
            alarm_code,
            severity,
            timestamp AS event_time
    """
    if alarm_code:
        sql = f"""
            SELECT {base_cols}
            FROM alarm_event_history
            WHERE equipment_id = %s AND alarm_code = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        return db_access.fetch_all(sql, (equipment_id, alarm_code, safe_limit), limit=safe_limit)
    sql = f"""
        SELECT {base_cols}
        FROM alarm_event_history
        WHERE equipment_id = %s
        ORDER BY timestamp DESC
        LIMIT %s
    """
    return db_access.fetch_all(sql, (equipment_id, safe_limit), limit=safe_limit)


def get_process_status_rows(equipment_id=None, process_name=None, line_id=None, limit=10):
    """공정/라인 상태를 조회한다(process_status ⋈ equipment_master).

    [설계] process_status 에는 process_name/line_id 가 없으므로 equipment_master 조인으로 해석.
    [반환 컬럼] process_name, line_id, status, status_time(=timestamp).
    """
    # [DB 조회 흐름 — 교육용 설명]
    # 지원 Tool: get_process_status / 조회 테이블: process_status ⋈ equipment_master.
    # process_status 에는 process_name/line_id 컬럼이 없어, equipment_master 와 조인해 의미를 해석한다.
    # (Tool Contract 의 any_of(process_name/line_id)를 DB 스키마와 맞추는 조인 — repository 가 흡수한다.)
    # 모든 조건 값은 %s 파라미터 바인딩으로 전달하고, SELECT 컬럼/조인/조건은 고정해 둔다.
    safe_limit = min(int(limit) if str(limit).isdigit() else 10, 100)
    select_cols = """
            em.process_name AS process_name,
            em.line_id      AS line_id,
            ps.status       AS status,
            ps.timestamp    AS status_time
    """
    join = """
        FROM process_status AS ps
        JOIN equipment_master AS em ON em.equipment_id = ps.equipment_id
    """
    if equipment_id:
        sql = f"SELECT {select_cols} {join} WHERE ps.equipment_id = %s ORDER BY ps.timestamp DESC LIMIT %s"
        return db_access.fetch_all(sql, (equipment_id.strip(), safe_limit), limit=safe_limit)
    if line_id:
        sql = f"SELECT {select_cols} {join} WHERE em.line_id = %s ORDER BY ps.timestamp DESC LIMIT %s"
        return db_access.fetch_all(sql, (line_id.strip(), safe_limit), limit=safe_limit)
    if process_name:
        sql = f"SELECT {select_cols} {join} WHERE em.process_name = %s ORDER BY ps.timestamp DESC LIMIT %s"
        return db_access.fetch_all(sql, (process_name.strip(), safe_limit), limit=safe_limit)
    return []


def get_quality_metric_rows(equipment_id=None, line_id=None, metric_name=None, limit=10):
    """품질 지표를 조회한다(quality_metrics, equipment_id 는 equipment_master 로 line_id 매핑).

    [metric_name allowlist] 임의 컬럼명 직결 금지. 허용 목록 밖이면 MetricNameNotAllowed 발생.
    [반환 컬럼] line_id, metric_name, metric_value, metric_time(=timestamp).
    """
    # [DB 조회 흐름 — 교육용 설명]
    # 지원 Tool: get_quality_metrics / 조회 테이블: quality_metrics (+equipment_master 로 line_id 해석).
    # 핵심 보안 포인트: metric_name 은 '임의 컬럼명'으로 SQL 에 들어가면 안 된다(컬럼 인젝션 위험).
    # → 아래에서 allowlist 를 통과한 '고정 컬럼명'만 SQL 에 들어가고, line_id/limit 같은 값은 %s 바인딩으로 전달한다.
    safe_limit = min(int(limit) if str(limit).isdigit() else 10, 100)
    # metric_name allowlist 검증(없으면 기본 지표).
    requested = (metric_name or "").strip() or _DEFAULT_METRIC
    if requested not in _METRIC_COLUMN_ALLOWLIST:
        raise MetricNameNotAllowed(
            f"허용되지 않은 metric_name 입니다. 허용: {get_allowed_metric_names()}"
        )
    column = _METRIC_COLUMN_ALLOWLIST[requested]  # allowlist 를 거친 '고정 컬럼명'만 SQL 에 들어간다.

    # equipment_id 로 line_id 를 먼저 해석(라인 단위 품질).
    resolved_line_id = line_id.strip() if line_id else None
    if not resolved_line_id and equipment_id:
        row = db_access.fetch_one(
            "SELECT line_id FROM equipment_master WHERE equipment_id = %s",
            (equipment_id.strip(),),
        )
        if row:
            resolved_line_id = row.get("line_id")
    if not resolved_line_id:
        return []

    # column 은 allowlist 를 통과한 안전한 식별자이므로 f-string 으로 컬럼만 넣는다.
    # 값(line_id/limit)은 모두 parameter binding 으로 전달한다.
    sql = f"""
        SELECT line_id        AS line_id,
               %s             AS metric_name,
               {column}       AS metric_value,
               timestamp      AS metric_time
        FROM quality_metrics
        WHERE line_id = %s
        ORDER BY timestamp DESC
        LIMIT %s
    """
    return db_access.fetch_all(sql, (requested, resolved_line_id, safe_limit), limit=safe_limit)


def get_maintenance_history_rows(equipment_id=None, date_range=None, part_replaced=None, limit=10):
    """정비/부품 교체 이력을 조회한다(technician_note 미조회).

    [반환 컬럼] equipment_id, maintenance_type, part_replaced, maintenance_date, downtime_min.
    [조건] equipment_id 필수, part_replaced 선택(값 일치). (date_range 는 추후 확장)
    """
    if not equipment_id:
        return []
    # [DB 조회 흐름 — 교육용 설명]
    # 지원 Tool: get_maintenance_history / 조회 테이블: maintenance_history.
    # technician_note(작업자 자유서술 메모)는 SELECT 목록에서 제외한다(민감 컬럼 1차 차단).
    # part_replaced 로 좁힐 수 있고, 최신 정비일(maintenance_date DESC) LIMIT 건수만 가져온다.
    # equipment_id / part_replaced '값'은 %s 파라미터 바인딩으로만 전달한다.
    safe_limit = min(int(limit) if str(limit).isdigit() else 10, 100)
    equipment_id = equipment_id.strip()
    part = part_replaced.strip() if part_replaced else None
    cols = """
            equipment_id,
            maintenance_type,
            part_replaced,
            maintenance_date,
            downtime_min
    """
    if part:
        sql = f"""
            SELECT {cols}
            FROM maintenance_history
            WHERE equipment_id = %s AND part_replaced = %s
            ORDER BY maintenance_date DESC
            LIMIT %s
        """
        return db_access.fetch_all(sql, (equipment_id, part, safe_limit), limit=safe_limit)
    sql = f"""
        SELECT {cols}
        FROM maintenance_history
        WHERE equipment_id = %s
        ORDER BY maintenance_date DESC
        LIMIT %s
    """
    return db_access.fetch_all(sql, (equipment_id, safe_limit), limit=safe_limit)


def get_equipment_overview_row(equipment_id=None, line_id=None):
    """설비 개요를 조회한다(equipment_master, owner_team/location 미조회).

    [반환 컬럼] equipment_id, equipment_type, line_id, process_name, criticality.
    [주의] DB 에 없는 install_year 는 조회/반환하지 않는다.
    """
    # [DB 조회 흐름 — 교육용 설명]
    # 지원 Tool: get_equipment_overview / 조회 테이블: equipment_master(설비 정적 메타).
    # owner_team / location(내부 조직·위치)은 SELECT 에서 제외한다(민감 컬럼 1차 차단).
    # DB 에 존재하지 않는 install_year 는 조회하지 않는다(없는 컬럼을 가정하지 않음).
    # equipment_id / line_id '값'은 %s 파라미터 바인딩으로 전달한다.
    cols = """
            equipment_id,
            equipment_type,
            line_id,
            process_name,
            criticality
    """
    if equipment_id:
        sql = f"SELECT {cols} FROM equipment_master WHERE equipment_id = %s LIMIT 1"
        return db_access.fetch_one(sql, (equipment_id.strip(),))
    if line_id:
        sql = f"SELECT {cols} FROM equipment_master WHERE line_id = %s LIMIT 1"
        return db_access.fetch_one(sql, (line_id.strip(),))
    return None
