# -*- coding: utf-8 -*-
"""
Day5 mcp_server02 - Equipment Data (설비 데이터 조회 모듈)

[이 모듈의 역할]
설비 상태/알람/공정/품질/정비/개요를 조회하는 내부 데이터 조회 모듈입니다.
1차 구현은 'mock mode' 중심이며, 실제 API Gateway / DB 호출은 구현하지 않습니다.

[모드 구분 — 매우 중요]
- 기본 모드는 mock 입니다. (LLM 기반 Tool Selection 이 기본이라고 해서
  실제 API/DB 를 자동 호출하면 안 됩니다. 두 축은 분리되어 있습니다.)
- 환경변수 MCP_EQUIPMENT_CLIENT_MODE 가 "real" 일 때만 real mode 를 고려합니다.
- real mode 라도 1차에서는 실제 HTTP/DB 호출을 하지 않고,
  "아직 구현되지 않았다"는 안전한 안내 dict 를 반환합니다(TODO 로 남김).

[search_manual 은 여기 없음]
search_manual 은 설비 API/DB 조회가 아니라 매뉴얼/RAG 검색 성격이므로
manual_search.py 로 분리되어 있습니다. 이 모듈에는 두지 않습니다.

[보안 원칙]
- mock 응답에도 실제 host/endpoint/자격증명/작업자 개인정보를 넣지 않는다.
- 반환값은 security.sanitize_result() 를 통과하기 쉬운 '요약 dict' 형태로 만든다.
- real mode 환경변수 '값'은 절대 출력/반환하지 않는다(이름만 README 에 적는다).

[전체 흐름에서의 위치]
    tool_executor.execute_single_tool()
        ↓ (설비 조회 Tool 인 경우)
    [equipment_data] (mock/real)
        ↓
    security.sanitize_result() 로 정리되어 외부로 반환

TODO(2차):
    - real mode 에서 사내 API Gateway(읽기 전용) 호출 구현
    - 호출 실패/타임아웃 처리, 재시도 정책
    - endpoint/credential 은 환경변수에서만 읽고 절대 로깅하지 않기
"""
import os  # real/mock 모드를 결정하는 환경변수를 읽기 위해 사용(값 자체는 출력하지 않음).

# enforce_limit: 조회 건수(limit)를 안전 범위로 강제해 과도한 전체 조회를 막는다.
#                설비 조회 결과도 MCP 를 통해 외부로 나가므로 반환량 상한을 둔다.
from day5.mcp_server02.security import enforce_limit


# real mode 활성화 여부를 결정하는 환경변수 이름.
# [주의] 이 변수의 '값'은 출력하지 않는다. 이름만 코드/문서에 노출한다.
CLIENT_MODE_ENV = "MCP_EQUIPMENT_CLIENT_MODE"


def get_client_mode():
    """현재 client 모드를 돌려준다. 기본값은 "mock".

    [반환]
        "real"  : 환경변수 MCP_EQUIPMENT_CLIENT_MODE 가 정확히 "real"(대소문자 무관)일 때.
        "mock"  : 그 외 모든 경우(미설정 포함). 안전 기본값.

    [설계 의도]
        '명시적으로 real 을 켰을 때만 real' 이라는 보수적 기본값을 사용한다.
        실수로 실제 설비를 호출하는 것을 막기 위한 안전장치다.

    [주의]
        환경변수 값 자체는 반환/출력하지 않고, "real"/"mock" 으로 정규화해서만 다룬다.
    """
    value = os.environ.get(CLIENT_MODE_ENV, "")
    return "real" if value.strip().lower() == "real" else "mock"


def _real_mode_notice(tool_name):
    """real mode 가 요청됐을 때 반환할 '미구현 안내' 요약 dict 를 만든다.

    [반환]
        실제 호출 없이, 안전한 안내만 담은 dict.
        - mode: "real"
        - implemented: False
        - message: 2차 작업 안내 (민감정보 없음)

    [왜 이렇게 하는가]
        1차에서는 실제 HTTP/DB 호출을 구현하지 않는다.
        예외를 던지는 대신, 흐름이 끊기지 않도록 안전한 dict 를 반환해
        교육 환경에서 전체 구조를 점검할 수 있게 한다.
    """
    return {
        "mode": "real",
        "implemented": False,
        "tool": tool_name,
        # endpoint/credential 등 민감정보를 일절 담지 않는다.
        "message": "real mode 는 2차 작업에서 사내 API Gateway(읽기 전용) 연동으로 구현 예정입니다.",
    }


def _is_real():
    """real mode 여부 헬퍼."""
    return get_client_mode() == "real"


# ===========================================================================
# 설비 조회 함수들 (1차: mock 응답)
# ===========================================================================
# 아래 모든 mock 응답은 DisplayEdu Fab 가상 시나리오 기준의 허구 데이터입니다.
# 실제 설비/라인/수율 값이 아니며, 내부 host/endpoint/개인정보를 포함하지 않습니다.

def fetch_equipment_status(equipment_id):
    """설비의 현재 상태를 조회한다(1차: mock).

    [입력] equipment_id: 설비 식별자(예: "EQP-EV-03").
    [반환] 요약 dict (equipment_id / status_code / status_label / updated_at).
           real mode 요청 시 _real_mode_notice 반환(실제 호출 없음).
    """
    if _is_real():
        return _real_mode_notice("get_equipment_status")
    # mock: 가상 상태값. 실제 의미 없는 교육용 더미.
    return {
        "equipment_id": equipment_id,
        "status_code": "NORMAL",
        "status_label": "정상 가동",
        "updated_at": "2026-06-01T09:00:00",
    }


def fetch_alarm_events(equipment_id, alarm_code=None, limit=20):
    """설비/알람 코드의 최근 알람 이력을 조회한다(1차: mock).

    [입력]
        equipment_id: 설비 식별자.
        alarm_code  : 특정 알람 코드로 좁힐 때 사용(선택).
        limit       : 반환 최대 건수. security.enforce_limit 로 상한 강제.
    [반환]
        요약 dict (equipment_id / alarm_code / event_count / recent_events / limit).
    """
    if _is_real():
        return _real_mode_notice("get_recent_alarm_events")
    safe_limit = enforce_limit(limit)
    code = alarm_code or "ALM-TEMP-402"
    # mock: 최근 알람 2건(요약). 실제 로그 dump 가 아니라 요약만 제공.
    events = [
        {"alarm_code": code, "occurred_at": "2026-06-01T08:30:00", "severity": "WARNING"},
        {"alarm_code": code, "occurred_at": "2026-05-31T22:10:00", "severity": "WARNING"},
    ]
    return {
        "equipment_id": equipment_id,
        "alarm_code": alarm_code,
        "event_count": len(events),
        "recent_events": events[:safe_limit],
        "limit": safe_limit,
    }


def fetch_process_status(process_name=None, line_id=None, equipment_id=None, limit=20):
    """공정/라인의 현재 상태를 조회한다(1차: mock).

    [입력]
        process_name / line_id : 둘 중 하나 이상으로 대상을 특정(any_of).
        equipment_id           : 범위를 좁힐 때 사용(선택).
        limit                  : 반환 상한.
    [반환]
        요약 dict (process_name / line_id / process_state / updated_at).
    """
    if _is_real():
        return _real_mode_notice("get_process_status")
    return {
        "process_name": process_name or "증착 공정",
        "line_id": line_id or "EDU-LINE-01",
        "process_state": "RUNNING",
        "updated_at": "2026-06-01T09:00:00",
    }


def fetch_quality_metrics(metric_name=None, equipment_id=None, line_id=None,
                          date_range=None, limit=20):
    """품질 지표를 조회한다(1차: mock).

    [입력]
        metric_name / equipment_id / line_id : 셋 중 하나 이상으로 대상 특정(any_of).
        date_range                           : 조회 기간(선택).
        limit                                : 반환 상한.
    [반환]
        요약 dict (metric_name / equipment_id / line_id / value / unit / period).
    """
    if _is_real():
        return _real_mode_notice("get_quality_metrics")
    return {
        "metric_name": metric_name or "defect_rate",
        "equipment_id": equipment_id,
        "line_id": line_id or "EDU-LINE-01",
        "value": 0.012,            # 가상 수치(교육용)
        "unit": "ratio",
        "period": date_range or "recent",
    }


def fetch_maintenance_history(equipment_id, date_range=None, part_replaced=None):
    """설비 정비/부품 교체 이력을 조회한다(1차: mock).

    [입력]
        equipment_id : 설비 식별자(필수).
        date_range   : 조회 기간(선택).
        part_replaced: 교체/정비 대상 부품명으로 좁힐 때 사용(선택).
                       실제 정비 이력 테이블의 'part_replaced' 컬럼 의미에 맞춘 이름이다.
    [반환]
        요약 dict (equipment_id / history / count).
        history 항목에는 작업자 개인정보를 넣지 않는다(part_replaced/action/performed_at 만).
    """
    if _is_real():
        return _real_mode_notice("get_maintenance_history")
    history = [
        {"part_replaced": part_replaced or "heater", "action": "정기 점검", "performed_at": "2026-05-20"},
    ]
    return {
        "equipment_id": equipment_id,
        "history": history,
        "count": len(history),
    }


def fetch_equipment_overview(equipment_id):
    """설비 개요(정적 메타)를 조회한다(1차: mock).

    [입력] equipment_id: 설비 식별자(필수).
    [반환] 요약 dict (equipment_id / equipment_type / line_id).
           실제 설비 마스터 스키마에 없는 값(예: 설치연도 같은 미정의 필드)은 mock 에도 넣지 않는다.
    """
    if _is_real():
        return _real_mode_notice("get_equipment_overview")
    return {
        "equipment_id": equipment_id,
        "equipment_type": "증착 설비",
        "line_id": "EDU-LINE-01",
    }
