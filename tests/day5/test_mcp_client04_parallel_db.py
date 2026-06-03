# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 - DB Tool 병렬 실행 데모 단위 테스트

[설계]
외부 MCP 서버/실제 DB/Ollama 에 의존하지 않는 '순수 단위 테스트'다. Tool 목록(schema)과
Tool 호출 결과를 모두 fake 로 주입해, 아래 '병렬 데모 로직'만 검증한다.
  - get_safe_parallel_db_tool_specs : 안전한 조회 Tool 만 선택 + schema 기준 인자 구성 + skipped 처리.
  - run_parallel_db_tools_demo      : 병렬 실행 결과 dict 구조 / 부분 실패 / sanitizing / caller 비공유.
실제 HTTP 서버를 호출하는 통합 테스트는 만들지 않는다(수동 검증은 README 참고).

[실행]
    uv run pytest tests/day5/test_mcp_client04_parallel_db.py -v
    (pytest 없이) python tests/day5/test_mcp_client04_parallel_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from day5.mcp_client04 import runner


# ---------------------------------------------------------------------------
# Fake schema / Fake ToolCaller (실제 서버/DB 없이 검증)
# ---------------------------------------------------------------------------
def _fake_tool_schemas():
    """list_mcp_tools 가 돌려주는 형태의 fake Tool schema 목록(서버 contract 와 동일한 구조).

    안전한 조회 Tool 4종 + 비대상 Tool(execute_sql/search_manual/get_equipment_status)을 섞어,
    화이트리스트/위험 Tool 제외가 제대로 동작하는지 검증할 수 있게 한다.
    """
    return [
        {"name": "get_equipment_overview",
         "inputSchema": {"type": "object",
                         "properties": {"equipment_id": {"type": "string"}},
                         "required": ["equipment_id"]}},
        {"name": "get_recent_alarm_events",
         "inputSchema": {"type": "object",
                         "properties": {"equipment_id": {"type": "string"},
                                        "alarm_code": {"type": "string"},
                                        "limit": {"type": "integer"}},
                         "required": ["equipment_id"]}},
        {"name": "get_quality_metrics",
         "inputSchema": {"type": "object",
                         "properties": {"metric_name": {"type": "string"},
                                        "equipment_id": {"type": "string"},
                                        "line_id": {"type": "string"},
                                        "date_range": {"type": "string"},
                                        "limit": {"type": "integer"}},
                         "required": []}},
        {"name": "get_maintenance_history",
         "inputSchema": {"type": "object",
                         "properties": {"equipment_id": {"type": "string"},
                                        "date_range": {"type": "string"},
                                        "part_replaced": {"type": "string"}},
                         "required": ["equipment_id"]}},
        # --- 아래는 병렬 데모 비대상(제외되어야 함) ---
        {"name": "execute_sql",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}},
                         "required": ["query"]}},
        {"name": "search_manual",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}},
                         "required": ["query"]}},
        {"name": "get_equipment_status",  # 조회 Tool 이지만 병렬 데모 화이트리스트엔 없음 → 조용히 제외
         "inputSchema": {"type": "object", "properties": {"equipment_id": {"type": "string"}},
                         "required": ["equipment_id"]}},
    ]


class FakeParallelToolCaller:
    """테스트용 ToolCaller. 실제 서버 없이 schema 목록과 호출 결과를 돌려준다.

    - list_tool_schemas(): fake schema 목록.
    - call_tool(name, args): error_tools 에 속하면 client_error envelope, 아니면 executed envelope.
      executed envelope 의 result 에는 민감 key(operator_note)를 일부러 넣어 sanitizing 을 검증한다.
    """

    def __init__(self, schemas=None, error_tools=()):
        self.schemas = schemas if schemas is not None else _fake_tool_schemas()
        self.error_tools = set(error_tools)
        self.calls = []  # (tool_name, arguments) — 어떤 Tool 이 호출됐는지 검증용.

    def list_tool_schemas(self):
        return self.schemas

    def list_tools(self):
        return [s["name"] for s in self.schemas]

    def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments or {})))
        if tool_name in self.error_tools:
            # 한 Tool 실패 시뮬레이션(client 측 오류 envelope).
            return {"status": "error", "_client_error": "FakeClientError"}
        return {"status": "executed", "validation_status": "PASS",
                "results": [{"tool_name": tool_name,
                             "result": {"equipment_id": arguments.get("equipment_id"),
                                        "data_source": "db",
                                        "record_count": 3,
                                        "operator_note": "민감-노트(마스킹 대상)",
                                        "fallback_used": False}}]}


def _make_factory(error_tools=(), schemas=None):
    """호출 때마다 '새' FakeParallelToolCaller 를 만드는 팩토리와, 생성된 caller 리스트를 돌려준다.

    [용도] run_parallel_db_tools_demo 가 작업마다 caller 를 새로 만드는지(공유하지 않는지) 검증한다.
    """
    created = []

    def factory():
        caller = FakeParallelToolCaller(schemas=schemas, error_tools=error_tools)
        created.append(caller)
        return caller

    return factory, created


# ---------------------------------------------------------------------------
# get_safe_parallel_db_tool_specs
# ---------------------------------------------------------------------------
def test_specs_only_safe_read_tools():
    """[1] 병렬 호출 대상은 안전한 조회 Tool 화이트리스트만 포함한다."""
    out = runner.get_safe_parallel_db_tool_specs(
        _fake_tool_schemas(), equipment_id="EQP-EV-03", line_id="EDU-LINE-01", limit=5)
    names = [s["tool_name"] for s in out["specs"]]
    assert set(names) == set(runner.SAFE_PARALLEL_DB_TOOLS)
    assert all(n in runner.SAFE_PARALLEL_DB_TOOLS for n in names)


def test_specs_exclude_execute_sql_and_rag():
    """[2] execute_sql / search_manual 은 호출 대상에 포함되지 않는다."""
    out = runner.get_safe_parallel_db_tool_specs(
        _fake_tool_schemas(), equipment_id="EQP-EV-03", line_id="EDU-LINE-01", limit=5)
    names = [s["tool_name"] for s in out["specs"]]
    assert "execute_sql" not in names
    assert "search_manual" not in names
    # 화이트리스트에 없는 조회 Tool 도 병렬 대상이 아니다.
    assert "get_equipment_status" not in names


def test_specs_build_only_schema_arguments():
    """[3][4] Tool schema 에 있는 인자만 구성하고, schema 에 없는 인자는 넣지 않는다."""
    out = runner.get_safe_parallel_db_tool_specs(
        _fake_tool_schemas(), equipment_id="EQP-EV-03", line_id="EDU-LINE-01", limit=5)
    by_name = {s["tool_name"]: s["arguments"] for s in out["specs"]}

    # 설비 개요: schema 에 equipment_id 만 있음 → line_id/limit 는 넣지 않는다.
    assert by_name["get_equipment_overview"] == {"equipment_id": "EQP-EV-03"}
    assert "line_id" not in by_name["get_equipment_overview"]
    assert "limit" not in by_name["get_equipment_overview"]

    # 최근 알람: equipment_id + limit(schema 에 있음). line_id 는 schema 에 없으므로 미전달.
    assert by_name["get_recent_alarm_events"] == {"equipment_id": "EQP-EV-03", "limit": 5}
    assert "line_id" not in by_name["get_recent_alarm_events"]

    # 품질 지표: equipment_id + line_id + limit 모두 schema 에 있음.
    assert by_name["get_quality_metrics"] == {
        "equipment_id": "EQP-EV-03", "line_id": "EDU-LINE-01", "limit": 5}

    # 정비 이력: equipment_id 만(schema 에 limit 없음 → 미전달).
    assert by_name["get_maintenance_history"] == {"equipment_id": "EQP-EV-03"}
    assert "limit" not in by_name["get_maintenance_history"]


def test_specs_skip_when_required_argument_missing():
    """[5] 필수 인자를 구성할 수 없는 Tool 은 호출하지 않고 skipped 로 기록한다."""
    # equipment_id 미지정 → equipment_id 가 필수인 Tool 들은 skipped, 품질 지표만 호출(required 없음).
    out = runner.get_safe_parallel_db_tool_specs(
        _fake_tool_schemas(), equipment_id="", line_id="EDU-LINE-01", limit=5)
    called = [s["tool_name"] for s in out["specs"]]
    skipped = {s["tool_name"]: s["reason"] for s in out["skipped_tools"]}

    assert called == ["get_quality_metrics"]  # line_id 로 충족(required 비어 있음)
    for name in ("get_equipment_overview", "get_recent_alarm_events", "get_maintenance_history"):
        assert name in skipped
        assert "필수 입력 schema를 구성할 수 없어" in skipped[name]


# ---------------------------------------------------------------------------
# run_parallel_db_tools_demo
# ---------------------------------------------------------------------------
def test_run_parallel_result_structure():
    """[6] 병렬 실행 결과 dict 가 예상 필드를 모두 포함한다."""
    factory, _created = _make_factory()
    result = runner.run_parallel_db_tools_demo(
        equipment_id="EQP-EV-03", line_id="EDU-LINE-01", limit=5,
        transport="http", tool_caller_factory=factory)

    for key in ("status", "mode", "transport", "tool_count", "called_count", "success_count",
                "error_count", "skipped_count", "elapsed_sec", "inputs", "called_tools",
                "skipped_tools", "results", "errors"):
        assert key in result, f"결과에 '{key}' 필드가 없습니다."
    assert result["status"] == "executed"
    assert result["mode"] == "parallel_db_tools"
    assert result["transport"] == "http"
    assert result["called_count"] == 4 and result["success_count"] == 4
    assert result["error_count"] == 0
    assert set(result["called_tools"]) == set(runner.SAFE_PARALLEL_DB_TOOLS)
    assert result["tool_count"] == result["called_count"] + result["skipped_count"]


def test_run_parallel_partial_failure_keeps_other_results():
    """[7] 일부 Tool 실패 시 error_count 가 증가하고 나머지 결과는 유지된다."""
    factory, _created = _make_factory(error_tools=("get_quality_metrics",))
    result = runner.run_parallel_db_tools_demo(
        equipment_id="EQP-EV-03", line_id="EDU-LINE-01", limit=5,
        transport="http", tool_caller_factory=factory)

    assert result["error_count"] >= 1
    assert result["success_count"] == result["called_count"] - result["error_count"]
    # 실패한 Tool 도, 성공한 Tool 도 모두 results 에 남는다(전체 실패로 키우지 않음).
    assert "get_quality_metrics" in result["results"]
    assert "get_equipment_overview" in result["results"]
    assert result["results"]["get_equipment_overview"].get("data_source") == "db"
    # 실패는 Tool별 오류에 type 중심으로 기록된다.
    assert any(e.get("tool_name") == "get_quality_metrics" for e in result["errors"])


def test_run_parallel_sanitizes_sensitive_fields():
    """[8] 민감정보성 key(operator_note)는 결과 요약에 포함되지 않는다."""
    factory, _created = _make_factory()
    result = runner.run_parallel_db_tools_demo(
        equipment_id="EQP-EV-03", line_id="EDU-LINE-01", limit=5,
        transport="http", tool_caller_factory=factory)

    for tool_name, summary in result["results"].items():
        assert "operator_note" not in summary, f"{tool_name} 요약에 민감 필드가 노출됨"
        # 비민감 스칼라/개수는 남는다(데이터 출처 등).
    assert result["results"]["get_equipment_overview"].get("data_source") == "db"


def test_run_parallel_creates_independent_caller_per_task():
    """[9] caller 를 공유하지 않는다 — 목록 조회 1회 + 호출 대상 수만큼 새 caller 가 생성된다."""
    factory, created = _make_factory()
    result = runner.run_parallel_db_tools_demo(
        equipment_id="EQP-EV-03", line_id="EDU-LINE-01", limit=5,
        transport="http", tool_caller_factory=factory)

    # schema 조회용 1개 + 병렬 호출용(called_count)개 = 서로 다른 caller 인스턴스.
    assert len(created) == 1 + result["called_count"]
    assert len({id(c) for c in created}) == len(created)  # 모두 별개 인스턴스(공유 아님)


def test_run_parallel_connection_error_when_no_schemas():
    """[보너스] schema 조회가 비면(서버 미기동) connection_error 로 정직하게 표기한다."""
    def factory():
        return FakeParallelToolCaller(schemas=[])  # 빈 목록 = 연결 실패 시뮬레이션

    result = runner.run_parallel_db_tools_demo(transport="http", tool_caller_factory=factory)
    assert result["status"] == "connection_error"
    assert result["called_count"] == 0
    assert result["errors"]  # 연결 실패 사유 기록


def _run_all():
    """pytest 없이 직접 실행할 때의 간이 러너."""
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    ok = fail = 0
    for fn in tests:
        try:
            fn()
            ok += 1
            print(f"[OK] {fn.__name__}")
        except AssertionError as error:
            fail += 1
            print(f"[FAIL] {fn.__name__}: {error}")
        except Exception as error:  # noqa: BLE001
            fail += 1
            print(f"[FAIL] {fn.__name__}: {type(error).__name__}: {error}")
    print(f"\n=== RESULT === OK={ok} FAIL={fail}")
    return fail


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
