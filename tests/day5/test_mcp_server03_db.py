# -*- coding: utf-8 -*-
"""
Day5 mcp_server03 - PostgreSQL DB 조회 통합 점검 스크립트

[실행]
    uv run python tests/day5/test_mcp_server03_db.py

[설계]
- pytest 가 없어도 단독 실행되도록 작성(각 점검을 함수로 두고 __main__ 에서 순차 실행).
- DB(PostgreSQL)가 떠 있지 않아도 전체가 실패하지 않게 한다:
  DB 가용 시에는 data_source="db" 를, 미가용 시에는 mock_fallback 을 확인한다.
- 비밀값/문서 전문/metadata 원문 전체를 콘솔에 출력하지 않는다.

[점검 항목]
1) import  2) POSTGRES_* 환경변수 읽기(비밀값 미출력)  3) DB 연결 가능 여부
4) repository import  5) 각 Tool call  6) 민감 컬럼 미반환  7) SQL Tool 거부 유지
8) search_manual RAG 경로 유지  9) mock fallback(강제 mock 모드)
* mcp_server01/02 무수정은 git diff 로 별도 확인(보고서 기록).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# 결과 집계용(간단 카운터).
_RESULTS = {"OK": 0, "FAIL": 0, "SKIP": 0}


def _log(tag, name, detail=""):
    _RESULTS[tag] = _RESULTS.get(tag, 0) + 1
    print(f"[{tag}] {name}" + (f" - {detail}" if detail else ""))


def _payload_of(tool_result):
    """call_mcp_tool 결과에서 sanitize 된 단일 Tool result payload 를 꺼낸다."""
    results = tool_result.get("results") if isinstance(tool_result, dict) else None
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return results[0].get("result") or {}
    return {}


def test_import():
    import day5.mcp_server03.mcp_server  # noqa: F401
    import day5.mcp_server03.db_access  # noqa: F401
    import day5.mcp_server03.repositories  # noqa: F401
    import day5.mcp_server03.equipment_data  # noqa: F401
    _log("OK", "import mcp_server03 (server/db_access/repositories/equipment_data)")


def test_env_config():
    from day5.mcp_server03 import db_access
    cfg = db_access.get_db_config()
    safe = db_access.safe_db_config()
    assert set(["host", "port", "dbname", "user", "password"]).issubset(cfg.keys())
    assert safe["password"] == "[REDACTED]", "표시용 config 의 password 는 [REDACTED] 여야 함"
    # 비밀값 원문은 출력하지 않는다(host/db/user 정도만 표시).
    _log("OK", "POSTGRES_* 환경변수 읽기", f"host={safe['host']} db={safe['dbname']} user={safe['user']} password=[REDACTED]")


def test_db_availability():
    from day5.mcp_server03 import db_access
    available = db_access.is_postgres_available()
    _log("OK", "is_postgres_available", f"{available}")
    return available


def test_repository_import():
    from day5.mcp_server03 import repositories
    for fn in ("get_equipment_status_rows", "get_recent_alarm_event_rows",
               "get_process_status_rows", "get_quality_metric_rows",
               "get_maintenance_history_rows", "get_equipment_overview_row"):
        assert hasattr(repositories, fn), f"repository 함수 누락: {fn}"
    _log("OK", "repositories 함수 import", "6개 고정 조회 함수 확인")


def test_tool_calls(available):
    from day5.mcp_server03.mcp_server import call_mcp_tool
    cases = [
        ("get_equipment_overview", {"equipment_id": "EQP-EV-03"}),
        ("get_equipment_status", {"equipment_id": "EQP-EV-03"}),
        ("get_recent_alarm_events", {"equipment_id": "EQP-EV-03", "alarm_code": "ALM-TEMP-402"}),
        ("get_process_status", {"line_id": "LINE-07"}),
        ("get_quality_metrics", {"line_id": "LINE-07", "metric_name": "yield_rate"}),
        ("get_maintenance_history", {"equipment_id": "EQP-EV-03"}),
    ]
    expected_source = "db" if available else "mock_fallback"
    for tool_name, args in cases:
        result = call_mcp_tool(tool_name, args)
        payload = _payload_of(result)
        src = payload.get("data_source")
        assert result.get("status") in ("executed", "dry_run"), f"{tool_name} 실행 상태 비정상"
        assert src == expected_source, f"{tool_name} data_source={src} (기대 {expected_source})"
        _log("OK", f"Tool call {tool_name}", f"status={result.get('status')} data_source={src}")


def test_sensitive_columns_absent():
    from day5.mcp_server03.mcp_server import call_mcp_tool
    # 알람: message/operator_note/lot_id 및 원문 미반환
    alarm = _payload_of(call_mcp_tool("get_recent_alarm_events", {"equipment_id": "EQP-EV-03"}))
    s_alarm = json.dumps(alarm, ensure_ascii=False)
    for bad in ('"message"', "operator_note", "lot_id", "LOT-", "threshold"):
        assert bad not in s_alarm, f"알람 응답에 민감 항목 노출: {bad}"
    # 정비: technician_note 미반환
    maint = _payload_of(call_mcp_tool("get_maintenance_history", {"equipment_id": "EQP-EV-03"}))
    assert "technician_note" not in json.dumps(maint, ensure_ascii=False), "정비 응답에 technician_note 노출"
    # 개요: owner_team/location 미반환
    ov = _payload_of(call_mcp_tool("get_equipment_overview", {"equipment_id": "EQP-EV-03"}))
    s_ov = json.dumps(ov, ensure_ascii=False)
    for bad in ("owner_team", "location"):
        assert bad not in s_ov, f"개요 응답에 민감 항목 노출: {bad}"
    _log("OK", "민감 컬럼 미반환", "message/operator_note/lot_id/technician_note/owner_team/location 없음")


def test_metric_name_allowlist(available):
    from day5.mcp_server03.mcp_server import call_mcp_tool
    bad = _payload_of(call_mcp_tool("get_quality_metrics", {"line_id": "LINE-07", "metric_name": "owner_team"}))
    # 허용 밖 metric_name 은 mock 으로 숨기지 않고 값 None + (DB 가용 시) data_source=db
    assert bad.get("value") is None, "허용되지 않은 metric_name 인데 value 가 채워짐"
    if available:
        assert bad.get("data_source") == "db", "허용 밖 metric_name 을 mock 으로 숨기면 안 됨"
    _log("OK", "metric_name allowlist", f"owner_team→value=None source={bad.get('data_source')}")


def test_sql_tool_rejected():
    from day5.mcp_server03.mcp_server import call_mcp_tool
    r = call_mcp_tool("execute_sql", {"query": "select * from users"})
    assert r.get("status") == "rejected", "execute_sql 가 거부되지 않음"
    _log("OK", "SQL/Text-to-SQL Tool 거부 유지", "execute_sql → rejected")


def test_search_manual_rag():
    from day5.mcp_server03.mcp_server import call_mcp_tool
    payload = _payload_of(call_mcp_tool("search_manual", {"query": "ALM-TEMP-402 조치 방향"}))
    docs = payload.get("documents")
    assert isinstance(docs, list) and len(docs) >= 1, "search_manual documents 없음"
    s = json.dumps(payload, ensure_ascii=False)
    for bad in ("full_text", "chroma:document", "source_path", "file_path", "internal_url"):
        assert bad not in s, f"RAG 응답에 금지 필드 노출: {bad}"
    _log("OK", "search_manual RAG 경로 유지", f"src={payload.get('retrieval_source')} docs={len(docs)}")


def test_mock_fallback():
    # 강제 mock 모드: DB 가용 여부와 무관하게 mock_fallback 이어야 한다.
    os.environ["MCP_EQUIPMENT_CLIENT_MODE"] = "mock"
    try:
        from day5.mcp_server03 import db_access
        db_access.reset_availability_cache()
        from day5.mcp_server03.mcp_server import call_mcp_tool
        payload = _payload_of(call_mcp_tool("get_equipment_overview", {"equipment_id": "EQP-EV-03"}))
        assert payload.get("data_source") == "mock_fallback", "강제 mock 모드인데 mock_fallback 아님"
        assert payload.get("fallback_used") is True
        _log("OK", "mock fallback(강제 mock 모드)", "data_source=mock_fallback")
    finally:
        os.environ["MCP_EQUIPMENT_CLIENT_MODE"] = ""
        from day5.mcp_server03 import db_access as _db
        _db.reset_availability_cache()


def main():
    test_import()
    test_env_config()
    available = test_db_availability()
    test_repository_import()
    if available:
        test_tool_calls(available)
        test_sensitive_columns_absent()
        test_metric_name_allowlist(available)
    else:
        _log("SKIP", "DB 의존 점검(Tool call/민감컬럼/metric allowlist)", "PostgreSQL 미가용 — mock fallback 경로만 점검")
        test_tool_calls(available)  # mock_fallback 경로로 동작 확인
    test_sql_tool_rejected()
    test_search_manual_rag()
    test_mock_fallback()

    print(f"\n=== RESULT === OK={_RESULTS['OK']} FAIL={_RESULTS['FAIL']} SKIP={_RESULTS['SKIP']}")
    # 통합 점검 스크립트는 DB 미가용을 실패로 보지 않는다(교육 안정성). 하드 실패만 비0 코드.
    sys.exit(1 if _RESULTS["FAIL"] else 0)


if __name__ == "__main__":
    main()
