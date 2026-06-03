# -*- coding: utf-8 -*-
"""
Day5 mcp_server_final - Equipment Data (설비 데이터 조회 모듈, PostgreSQL 우선 + mock fallback)

[이 모듈의 역할]
설비 상태/알람/공정/품질/정비/개요를 조회하는 내부 데이터 interface 입니다.
mcp_server03 부터는 **실제 PostgreSQL 조회를 우선** 시도하고, DB 연결이 불가하면
기존 mock 응답으로 안전하게 fallback 합니다(교육 안정성).

[데이터 소스 표시]
- DB 조회 성공: data_source="db", fallback_used=False
- DB 미가용(연결 실패): data_source="mock_fallback", fallback_used=True
- DB 사용 오류(예: 허용되지 않은 metric_name): mock 으로 숨기지 않고 data_source="db" + 빈/None 값

[모드 토글]
- 환경변수 MCP_EQUIPMENT_CLIENT_MODE 가 "mock" 이면 DB 를 시도하지 않고 mock 만 사용한다(테스트/오프라인용).
- 그 외(미설정 포함)에는 DB 우선 + 실패 시 mock fallback.
- 환경변수 '값'은 출력/반환하지 않는다.

[search_manual 은 여기 없음]
search_manual 은 매뉴얼/RAG 검색이므로 manual_search.py(→ rag_quality_adapter → rag_search)로 분리.

[보안 원칙]
- 민감 컬럼(message/operator_note/lot_id/technician_note/owner_team/location)은 repository 에서
  애초에 SELECT 하지 않으며, security.sanitize_result 가 2차로 한 번 더 제한한다.
- 접속 비밀값/연결 문자열/stack trace 원문을 반환하지 않는다.

[전체 흐름]
    tool_executor.execute_single_tool()
        ↓ (설비 조회 Tool)
    [equipment_data]  ──(DB 우선)──▶ repositories → db_access → PostgreSQL
        └──(DB 실패)──▶ mock fallback
        ↓
    security.sanitize_result() 로 정리되어 외부로 반환
"""
import os  # 모드 토글 환경변수(MCP_EQUIPMENT_CLIENT_MODE)를 읽기 위해 사용. 값은 출력하지 않는다.

# [import 구성 = DB 우선 + mock fallback 흐름의 계층]
#   - enforce_limit : 조회 건수 상한을 강제(과도 조회 방지). 결과가 MCP 로 외부에 나가므로 둔다.
#   - db_access     : PostgreSQL 가용성 확인 + 연결 실패 신호(DBUnavailableError) 제공.
#   - repositories  : Tool별 '고정 SQL' 조회 함수. 이 모듈은 raw SQL 을 직접 다루지 않고
#                     repositories 를 통해서만 DB 를 읽는다(SQL 통제 + 책임 분리).
from day5.mcp_server_final.security import enforce_limit
from day5.mcp_server_final import db_access
from day5.mcp_server_final import repositories


# DB 사용 모드를 끄고 mock 만 쓰도록 강제할 때 사용하는 환경변수 이름.
# [주의] 값은 출력하지 않는다. 이름만 코드/문서에 노출한다.
CLIENT_MODE_ENV = "MCP_EQUIPMENT_CLIENT_MODE"


def get_client_mode():
    """현재 모드를 돌려준다. "mock" 이면 DB 미사용(강제 mock), 그 외에는 "db"(DB 우선)."""
    value = os.environ.get(CLIENT_MODE_ENV, "")
    return "mock" if value.strip().lower() == "mock" else "db"


def _use_db():
    """DB 조회를 시도해도 되는 상태인지 판단한다(모드 + 가용성 캐시).

    [판단 순서]
        1) 강제 mock 모드면 DB 를 아예 시도하지 않는다(False).
        2) 그 외에는 db_access.is_postgres_available() 로 연결 가능 여부를 확인한다.
           (가용성은 캐시되어 매 호출마다 느린 연결 타임아웃을 반복하지 않는다.)

    [흐름상 의미]
        이 함수가 False 면 곧바로 mock 응답(data_source="mock_fallback")으로 넘어가고,
        True 면 repositories 를 통해 실제 DB(data_source="db")를 조회한다.
        즉 'DB 우선 / 실패 시 mock' 분기의 첫 갈림길이다.
    """
    if get_client_mode() == "mock":
        return False
    return db_access.is_postgres_available()


def _iso(value):
    """datetime/date 류를 ISO 문자열로 안전 변환(그 외는 str)."""
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else str(value)


_STATUS_LABELS = {"NORMAL": "정상 가동", "WARNING": "경고", "ALARM": "알람", "STOP": "정지"}


def _label_for_status(status):
    """상태 코드 → 한국어 라벨(미정의면 코드 그대로)."""
    return _STATUS_LABELS.get(str(status or "").upper(), str(status or ""))


# ===========================================================================
# mock 응답 (DB 미가용 시 fallback). DisplayEdu Fab 가상 시나리오 허구 데이터.
# ===========================================================================
# [이 블록의 역할]
#   PostgreSQL 연결이 불가할 때(미기동/네트워크) 교육 실습 흐름이 끊기지 않도록
#   대체 응답을 만든다. 아래 모든 mock 응답은 'DB 결과가 아님'을 분명히 표시하기 위해
#   data_source="mock_fallback", fallback_used=True 를 항상 포함한다.
#   - data_source  : 이 응답의 출처. "mock_fallback" 은 실제 DB 가 아닌 대체 데이터라는 뜻.
#   - fallback_used : 실제 DB 대신 대체 데이터를 썼는지 여부(True). 운영 점검/테스트에서
#                     "실제 DB 를 못 읽고 mock 으로 넘어갔다"를 식별하는 신호다.
#   [주의] 이 값들과 반환 dict 구조는 테스트/화면 표시가 의존하므로 변경하지 않는다.
def _mock_equipment_status(equipment_id):
    """설비 상태 조회의 mock fallback 응답을 만든다(DB 미가용 시 사용).

    data_source="mock_fallback" / fallback_used=True 로, 실제 DB 결과(data_source="db")와
    구분되도록 표시한다. 반환 dict 의 key 구조는 DB 경로 응답과 동일하게 맞춘다.
    """
    return {
        "equipment_id": equipment_id, "status_code": "NORMAL", "status_label": "정상 가동",
        "updated_at": "2026-06-01T09:00:00",
        "data_source": "mock_fallback", "fallback_used": True,
    }


def _mock_alarm_events(equipment_id, alarm_code, safe_limit):
    """최근 알람 이력 조회의 mock fallback 응답을 만든다(DB 미가용 시 사용).

    실제 DB 결과와 동일한 key 구조에 data_source="mock_fallback" / fallback_used=True 를 붙인다.
    민감 컬럼(message/operator_note/lot_id)은 mock 에도 담지 않는다.
    """
    code = alarm_code or "ALM-TEMP-402"
    events = [
        {"alarm_code": code, "occurred_at": "2026-06-01T08:30:00", "severity": "WARNING"},
        {"alarm_code": code, "occurred_at": "2026-05-31T22:10:00", "severity": "WARNING"},
    ]
    return {
        "equipment_id": equipment_id, "alarm_code": alarm_code, "event_count": len(events),
        "recent_events": events[:safe_limit], "limit": safe_limit,
        "data_source": "mock_fallback", "fallback_used": True,
    }


def _mock_process_status(process_name, line_id):
    """공정/라인 상태 조회의 mock fallback 응답을 만든다(DB 미가용 시 사용).

    DB 경로 응답과 동일한 key 구조에 data_source="mock_fallback" / fallback_used=True 를 붙인다.
    """
    return {
        "process_name": process_name or "증착 공정", "line_id": line_id or "EDU-LINE-01",
        "process_state": "RUNNING", "updated_at": "2026-06-01T09:00:00",
        "data_source": "mock_fallback", "fallback_used": True,
    }


def _mock_quality_metrics(metric_name, equipment_id, line_id, date_range):
    """품질 지표 조회의 mock fallback 응답을 만든다(DB 미가용 시 사용).

    DB 경로 응답과 동일한 key 구조에 data_source="mock_fallback" / fallback_used=True 를 붙인다.
    value 는 교육용 가상 수치다.
    """
    return {
        "metric_name": metric_name or "defect_rate", "equipment_id": equipment_id,
        "line_id": line_id or "EDU-LINE-01", "value": 0.012, "unit": "ratio",
        "period": date_range or "recent",
        "data_source": "mock_fallback", "fallback_used": True,
    }


def _mock_maintenance_history(equipment_id, part_replaced):
    """정비/부품 교체 이력 조회의 mock fallback 응답을 만든다(DB 미가용 시 사용).

    DB 경로 응답과 동일한 key 구조에 data_source="mock_fallback" / fallback_used=True 를 붙인다.
    민감 컬럼(technician_note)은 mock 에도 담지 않는다.
    """
    history = [{"part_replaced": part_replaced or "heater", "action": "정기 점검",
                "performed_at": "2026-05-20"}]
    return {
        "equipment_id": equipment_id, "history": history, "count": len(history),
        "data_source": "mock_fallback", "fallback_used": True,
    }


def _mock_equipment_overview(equipment_id):
    """설비 개요 조회의 mock fallback 응답을 만든다(DB 미가용 시 사용).

    DB 경로 응답과 동일한 key 구조에 data_source="mock_fallback" / fallback_used=True 를 붙인다.
    민감 컬럼(owner_team/location)은 mock 에도 담지 않는다.
    """
    return {
        "equipment_id": equipment_id, "equipment_type": "증착 설비", "line_id": "EDU-LINE-01",
        "data_source": "mock_fallback", "fallback_used": True,
    }


# ===========================================================================
# 설비 조회 함수 (DB 우선 → 실패 시 mock fallback)
# ===========================================================================
def fetch_equipment_status(equipment_id):
    """설비 현재 상태(최신 process_status)를 조회한다. DB 우선, 연결 실패 시 mock.

    [입력] equipment_id: 상태를 조회할 설비 식별자.
    [반환]
        dict — {equipment_id, status_code, status_label, updated_at, data_source, fallback_used}.
        DB 성공: data_source="db", fallback_used=False.
        DB 미가용: _mock_equipment_status (data_source="mock_fallback", fallback_used=True).

    [흐름]
        1) _use_db() 가 False(강제 mock 또는 연결 불가)면 곧바로 mock 응답.
        2) repositories.get_equipment_status_rows() 로 최신 1건 조회(고정 SQL + parameter binding).
        3) 조회 결과가 없으면(rows 빈 list) latest={} → status_code 등이 None 으로 채워진다.
           '결과 없음'은 정상 응답이며 mock 으로 대체하지 않는다(DBUnavailableError 만 mock).

    [Notes]
        이 함수는 MCP tool(get_equipment_status)의 데이터 소스다. 반환 dict 의 key 구조와
        data_source/fallback_used 표기를 변경하면 클라이언트/테스트/화면 표시에 영향을 준다.
        '연결 실패'(mock 대상)와 '결과 없음'(DB 정상 응답)을 구분하는 점에 유의한다.
    """
    if not _use_db():
        return _mock_equipment_status(equipment_id)
    try:
        rows = repositories.get_equipment_status_rows(equipment_id=equipment_id, limit=1)
        latest = rows[0] if rows else {}
        return {
            "equipment_id": equipment_id,
            "status_code": latest.get("status"),
            "status_label": _label_for_status(latest.get("status")),
            "updated_at": _iso(latest.get("status_time")),
            "data_source": "db", "fallback_used": False,
        }
    except db_access.DBUnavailableError:
        # 연결 실패(DB 미기동/네트워크)만 mock fallback 대상이다.
        # SQL 사용 오류 등은 repository/db_access 에서 ValueError 로 올라와 숨기지 않는다.
        return _mock_equipment_status(equipment_id)


def fetch_alarm_events(equipment_id, alarm_code=None, limit=20):
    """최근 알람 이력을 조회한다(민감 컬럼 제외). DB 우선, 연결 실패 시 mock.

    [입력]
        equipment_id: 알람 이력을 조회할 설비 식별자(필수).
        alarm_code  : 특정 알람 코드로 범위를 좁힐 때 사용(선택).
        limit       : 반환 최대 건수. enforce_limit 로 안전 상한을 강제한다.
    [반환]
        dict — {equipment_id, alarm_code, event_count, recent_events, limit,
                data_source, fallback_used}.
        DB 성공: data_source="db". DB 미가용: mock(data_source="mock_fallback").

    [Notes]
        repository 가 message/operator_note/lot_id 같은 민감 컬럼을 애초에 SELECT 하지 않으며,
        security.sanitize_result 가 recent_events 내부 key 까지 한 번 더 제한한다(2차 방어).
        반환 구조/표기 값을 변경하면 클라이언트/테스트에 영향을 준다.
    """
    safe_limit = enforce_limit(limit)
    if not _use_db():
        return _mock_alarm_events(equipment_id, alarm_code, safe_limit)
    try:
        rows = repositories.get_recent_alarm_event_rows(
            equipment_id=equipment_id, alarm_code=alarm_code, limit=safe_limit
        )
        events = [{
            "alarm_code": r.get("alarm_code"),
            "occurred_at": _iso(r.get("event_time")),
            "severity": r.get("severity"),
        } for r in rows]
        return {
            "equipment_id": equipment_id, "alarm_code": alarm_code,
            "event_count": len(events), "recent_events": events, "limit": safe_limit,
            "data_source": "db", "fallback_used": False,
        }
    except db_access.DBUnavailableError:
        return _mock_alarm_events(equipment_id, alarm_code, safe_limit)


def fetch_process_status(process_name=None, line_id=None, equipment_id=None, limit=20):
    """공정/라인 상태를 조회한다(process_status ⋈ equipment_master). DB 우선, 연결 실패 시 mock.

    [입력] process_name / line_id / equipment_id 중 하나 이상으로 대상을 특정(선택 인자).
    [반환]
        dict — {process_name, line_id, process_state, updated_at, data_source, fallback_used}.
        DB 성공: data_source="db". DB 미가용: mock(data_source="mock_fallback").

    [Notes]
        process_status 테이블에는 process_name/line_id 가 없어 equipment_master 조인으로 해석한다.
        반환 구조/표기 값은 클라이언트/테스트가 의존하므로 변경하지 않는다.
    """
    if not _use_db():
        return _mock_process_status(process_name, line_id)
    try:
        rows = repositories.get_process_status_rows(
            equipment_id=equipment_id, process_name=process_name, line_id=line_id, limit=1
        )
        latest = rows[0] if rows else {}
        return {
            "process_name": latest.get("process_name") or process_name,
            "line_id": latest.get("line_id") or line_id,
            "process_state": latest.get("status"),
            "updated_at": _iso(latest.get("status_time")),
            "data_source": "db", "fallback_used": False,
        }
    except db_access.DBUnavailableError:
        return _mock_process_status(process_name, line_id)


def fetch_quality_metrics(metric_name=None, equipment_id=None, line_id=None,
                          date_range=None, limit=20):
    """품질 지표를 조회한다(metric_name allowlist). DB 우선, '연결 실패만' mock fallback.

    [입력]
        metric_name / equipment_id / line_id : 대상 특정(선택). equipment_id 는 라인으로 매핑됨.
        date_range / limit                   : 기간/건수(현재 date_range 는 표시용).
    [반환]
        dict — {metric_name, equipment_id, line_id, value, unit, period, data_source, fallback_used}.

    [예외 처리의 핵심 — 세 가지 경우를 구분]
        1) 연결 실패(DBUnavailableError): mock fallback(data_source="mock_fallback").
        2) 사용 오류(MetricNameNotAllowed): 허용 목록 밖 metric_name 은 '사용자 입력 오류'다.
           mock 으로 숨기지 않고 data_source="db" + value=None 으로 반환해, 잘못된 요청임을
           투명하게 드러낸다(연결 실패와 다르게 취급).
        3) 결과 없음: rows 가 비면 value 등이 None 으로 채워지는 정상 DB 응답이다.

    [Notes]
        '연결 실패'와 '입력 오류'를 같은 mock 으로 뭉뚱그리지 않는 것이 이 함수의 학습 포인트다.
        반환 구조/표기 값은 변경하지 않는다.
    """
    if not _use_db():
        return _mock_quality_metrics(metric_name, equipment_id, line_id, date_range)
    try:
        rows = repositories.get_quality_metric_rows(
            equipment_id=equipment_id, line_id=line_id, metric_name=metric_name, limit=1
        )
        latest = rows[0] if rows else {}
        return {
            "metric_name": latest.get("metric_name") or (metric_name or "defect_rate"),
            "equipment_id": equipment_id,
            "line_id": latest.get("line_id") or line_id,
            "value": latest.get("metric_value"),
            "unit": "ratio",
            "period": date_range or "recent",
            "data_source": "db", "fallback_used": False,
        }
    except repositories.MetricNameNotAllowed:
        # 사용 오류 → mock 으로 숨기지 않는다. DB 소스로 표시하되 값은 비운다.
        return {
            "metric_name": metric_name, "equipment_id": equipment_id, "line_id": line_id,
            "value": None, "unit": "ratio", "period": date_range or "recent",
            "data_source": "db", "fallback_used": False,
        }
    except db_access.DBUnavailableError:
        return _mock_quality_metrics(metric_name, equipment_id, line_id, date_range)


def fetch_maintenance_history(equipment_id, date_range=None, part_replaced=None):
    """정비/부품 교체 이력을 조회한다(technician_note 제외). DB 우선, 연결 실패 시 mock.

    [입력]
        equipment_id : 이력을 조회할 설비 식별자(필수).
        date_range   : 조회 기간(현재 표시용).
        part_replaced: 교체/정비 부품명으로 좁힐 때 사용(선택).
    [반환]
        dict — {equipment_id, history, count, data_source, fallback_used}.
        DB 성공: data_source="db". DB 미가용: mock(data_source="mock_fallback").

    [Notes]
        repository 가 technician_note(작업자 메모) 같은 민감/장문 컬럼을 SELECT 하지 않는다.
        반환 구조/표기 값은 클라이언트/테스트가 의존하므로 변경하지 않는다.
    """
    if not _use_db():
        return _mock_maintenance_history(equipment_id, part_replaced)
    try:
        rows = repositories.get_maintenance_history_rows(
            equipment_id=equipment_id, date_range=date_range, part_replaced=part_replaced, limit=10
        )
        history = [{
            "part_replaced": r.get("part_replaced"),
            "action": r.get("maintenance_type"),
            "performed_at": _iso(r.get("maintenance_date")),
        } for r in rows]
        return {
            "equipment_id": equipment_id, "history": history, "count": len(history),
            "data_source": "db", "fallback_used": False,
        }
    except db_access.DBUnavailableError:
        return _mock_maintenance_history(equipment_id, part_replaced)


def fetch_equipment_overview(equipment_id):
    """설비 개요(정적 메타)를 조회한다(owner_team/location 제외). DB 우선, 연결 실패 시 mock.

    [입력] equipment_id: 개요를 조회할 설비 식별자.
    [반환]
        dict — {equipment_id, equipment_type, line_id, data_source, fallback_used}.
        DB 성공: data_source="db". DB 미가용: mock(data_source="mock_fallback").

    [Notes]
        repository 가 owner_team/location(민감) 을 SELECT 하지 않으며, DB 에 없는 install_year 는
        조회/반환하지 않는다. 반환 구조/표기 값은 변경하지 않는다.
    """
    if not _use_db():
        return _mock_equipment_overview(equipment_id)
    try:
        row = repositories.get_equipment_overview_row(equipment_id=equipment_id) or {}
        return {
            "equipment_id": row.get("equipment_id") or equipment_id,
            "equipment_type": row.get("equipment_type"),
            "line_id": row.get("line_id"),
            "data_source": "db", "fallback_used": False,
        }
    except db_access.DBUnavailableError:
        return _mock_equipment_overview(equipment_id)
