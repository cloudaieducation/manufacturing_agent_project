# -*- coding: utf-8 -*-
"""
Day5 mcp_client01 - direct mode MCP Client 점검 스크립트

[실행]
    uv run python tests/day5/test_mcp_client01.py

[설계]
- pytest 가 없어도 단독 실행되도록 작성(각 점검을 함수로 두고 __main__ 에서 순차 실행).
- PostgreSQL 이 꺼져 있어도 전체가 실패하지 않게 한다:
  DB Tool 결과의 data_source 가 "db" 또는 "mock_fallback" 둘 중 하나면 통과로 본다.
- 비밀값/문서 전문/민감 컬럼이 요약 출력에 섞이지 않는지 확인한다.

[점검 항목]
1) client_app / result_formatting import
2) direct mode 기본 시나리오(run_demo) 실행 가능
3) summarize_tool_result 가 민감 필드(full_text/source_path/password 등)를 출력하지 않음
4) search_manual 결과 요약 가능
5) get_equipment_overview 결과 요약(data_source db|mock_fallback)
6) execute_sql 거부 확인
"""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_RESULTS = {"OK": 0, "FAIL": 0, "SKIP": 0}


def _log(tag, name, detail=""):
    _RESULTS[tag] = _RESULTS.get(tag, 0) + 1
    print(f"[{tag}] {name}" + (f" - {detail}" if detail else ""))


# 요약 출력에 절대 나오면 안 되는 민감 토큰(원문 노출 여부 점검용).
_FORBIDDEN_IN_OUTPUT = (
    "password", "token", "secret", "connection", "dsn",
    "full_text", "chroma:document", "source_path", "file_path", "internal_url",
    "raw_metadata", "operator_note", "technician_note", "lot_id",
)


def test_imports():
    import day5.mcp_client01.client_app  # noqa: F401
    import day5.mcp_client01.result_formatting  # noqa: F401
    _log("OK", "import client_app / result_formatting")


def test_summarize_no_sensitive():
    from day5.mcp_client01.result_formatting import summarize_tool_result
    # 민감 필드가 섞인 가짜 결과를 넣어도 요약에 노출되지 않아야 한다.
    fake = {
        "status": "executed",
        "results": [{
            "tool_name": "search_manual",
            "result": {
                "query": "q", "retrieval_source": "chroma", "fallback_used": False,
                "documents": [{
                    "doc_id": "D1", "title": "T", "snippet": "S",
                    # 아래는 절대 노출되면 안 되는 필드(서버는 반환하지 않지만 방어 점검).
                    "full_text": "FULLTEXT-SHOULD-NOT-APPEAR",
                    "source_path": "/internal/secret/path",
                }],
                "password": "SECRET-PW-SHOULD-NOT-APPEAR",
            },
        }],
    }
    text = summarize_tool_result("search_manual", fake)
    for bad in ("FULLTEXT-SHOULD-NOT-APPEAR", "SECRET-PW-SHOULD-NOT-APPEAR", "/internal/secret/path"):
        assert bad not in text, f"요약에 민감 값 노출: {bad}"
    assert "documents: 1" in text, "documents 요약이 없음"
    _log("OK", "summarize_tool_result 민감 필드 미노출", "full_text/source_path/password 제외")


def test_demo_runs():
    # run_demo 를 stdout 캡처로 실행하고, 민감 토큰이 출력에 없는지 확인한다.
    from day5.mcp_client01 import client_app

    class _Args:
        query = None
        equipment_id = None
        alarm_code = None
        metric_name = None

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            client_app.run_demo(_Args())
    except Exception as error:
        _log("FAIL", "run_demo 실행", f"{type(error).__name__}")
        return
    output = buf.getvalue()
    # 기본 시나리오의 단계 표지가 모두 있는지(요약 흐름 확인).
    for marker in ("[1]", "[2]", "[3]", "[4]", "[5]", "[6]"):
        assert marker in output, f"데모 단계 표지 누락: {marker}"
    # 거부 확인 단계가 rejected 로 나오는지.
    assert "rejected" in output, "execute_sql 거부 표시가 없음"
    # 민감 토큰 원문이 출력에 없는지.
    low = output.lower()
    for bad in _FORBIDDEN_IN_OUTPUT:
        assert bad not in low, f"데모 출력에 민감 토큰 노출: {bad}"
    _log("OK", "run_demo 기본 시나리오 실행 + 민감 토큰 미노출")


def test_single_tools():
    from day5.mcp_client01.client_app import _load_server_entrypoints
    from day5.mcp_client01.result_formatting import summarize_tool_result
    call_mcp_tool, list_mcp_tools = _load_server_entrypoints()

    # list_mcp_tools: 7개 업무 Tool 이름이 보이고 금지 Tool 은 없어야 한다.
    names = [t.get("name") for t in list_mcp_tools()]
    assert "search_manual" in names and "execute_sql" not in names, "Tool 목록 구성 비정상"
    _log("OK", "list_mcp_tools", f"{len(names)}개 노출, execute_sql 미노출")

    # search_manual 요약 가능.
    sm = call_mcp_tool("search_manual", {"query": "ALM-TEMP-402 조치 방향"})
    assert "status:" in summarize_tool_result("search_manual", sm)
    _log("OK", "search_manual 요약", f"status={sm.get('status')}")

    # get_equipment_overview: data_source 가 db 또는 mock_fallback.
    ov = call_mcp_tool("get_equipment_overview", {"equipment_id": "EQP-EV-03"})
    payload = (ov.get("results") or [{}])[0].get("result", {}) if ov.get("results") else {}
    ds = payload.get("data_source")
    assert ds in ("db", "mock_fallback"), f"data_source 예상 밖: {ds}"
    _log("OK", "get_equipment_overview 요약", f"data_source={ds}")

    # execute_sql 거부.
    sql = call_mcp_tool("execute_sql", {"query": "select * from users"})
    assert sql.get("status") == "rejected", "execute_sql 가 거부되지 않음"
    _log("OK", "execute_sql 거부 확인", "rejected")


def main():
    test_imports()
    test_summarize_no_sensitive()
    test_demo_runs()
    test_single_tools()
    print(f"\n=== RESULT === OK={_RESULTS['OK']} FAIL={_RESULTS['FAIL']} SKIP={_RESULTS['SKIP']}")
    sys.exit(1 if _RESULTS["FAIL"] else 0)


if __name__ == "__main__":
    main()
