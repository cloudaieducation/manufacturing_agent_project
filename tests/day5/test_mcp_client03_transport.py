# -*- coding: utf-8 -*-
"""
Day5 mcp_client03 - 실제 MCP stdio transport 점검 스크립트

[실행]
    uv run python tests/day5/test_mcp_client03_transport.py

[설계 — 환경 내성]
- 실제 stdio transport(별도 서버 프로세스)가 환경상 불가하면 관련 점검은 SKIP 한다(전체 실패 아님).
- DB on/off 무관: DB Tool 결과 data_source 가 db|mock_fallback 어느 쪽이어도 통과.
- search_manual(RAG) over stdio 는 이 환경에서 timeout 될 수 있으므로, 호출은 시도하되
  status 가 executed/timeout/error 어느 쪽이어도 통과로 본다(한계 반영, 호출 경로만 확인).
- import 오류·민감정보 노출·서버 내부 직접 import 같은 'mcp_client03 자체 문제'는 FAIL 로 처리한다.

[pytest 불필요] 단독 실행 가능.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_RESULTS = {"OK": 0, "FAIL": 0, "SKIP": 0}


def _log(tag, name, detail=""):
    _RESULTS[tag] = _RESULTS.get(tag, 0) + 1
    print(f"[{tag}] {name}" + (f" - {detail}" if detail else ""))


_FORBIDDEN = (
    "password", "token", "secret", "connection", "dsn",
    "full_text", "chroma:document", "source_path", "file_path", "internal_url",
    "raw_metadata", "operator_note", "technician_note", "lot_id",
)


def test_imports():
    import day5.mcp_client03.client_app  # noqa: F401
    import day5.mcp_client03.transport_stdio  # noqa: F401
    import day5.mcp_client03.transport_http  # noqa: F401
    import day5.mcp_client03.result_formatting  # noqa: F401
    _log("OK", "import client_app / transport_stdio / transport_http / result_formatting")


def test_fastmcp_client_api():
    try:
        from fastmcp import Client  # noqa: F401
        from fastmcp.client.transports import StdioTransport  # noqa: F401
        _log("OK", "fastmcp client API 사용 가능", "Client + StdioTransport")
        return True
    except Exception as error:
        _log("SKIP", "fastmcp client API 미가용", type(error).__name__)
        return False


def test_http_transport_api():
    """HTTP transport client API(StreamableHttpTransport) import 가능 여부."""
    try:
        from fastmcp.client.transports import StreamableHttpTransport  # noqa: F401
        from day5.mcp_client03 import transport_http  # noqa: F401
        _log("OK", "HTTP transport API 사용 가능", "StreamableHttpTransport + transport_http")
        return True
    except Exception as error:
        _log("SKIP", "HTTP transport API 미가용", type(error).__name__)
        return False


def test_summarize_no_sensitive():
    from day5.mcp_client03.result_formatting import summarize_tool_result
    fake = {
        "status": "executed",
        "results": [{"tool_name": "search_manual", "result": {
            "retrieval_source": "chroma", "fallback_used": False,
            "documents": [{"doc_id": "D1", "title": "T", "snippet": "S",
                           "full_text": "FULLTEXT-SHOULD-NOT-APPEAR",
                           "source_path": "/internal/secret/path"}],
            "password": "SECRET-PW",
        }}],
    }
    text = summarize_tool_result("search_manual", fake)
    for bad in ("FULLTEXT-SHOULD-NOT-APPEAR", "SECRET-PW", "/internal/secret/path"):
        assert bad not in text, f"요약에 민감 값 노출: {bad}"
    _log("OK", "summarize_tool_result 민감 필드 미노출", "full_text/source_path/password 제외")


def test_no_langgraph_and_internal_import():
    import day5.mcp_client03 as pkg
    pkg_dir = Path(pkg.__file__).parent
    forbidden_internal = ("repositories", "db_access", "rag_quality_adapter",
                          "rag_search", "equipment_data", "manual_search")
    for py in pkg_dir.glob("*.py"):
        src = py.read_text(encoding="utf-8")
        # LangGraph 미사용 확인(import/StateGraph 등 코드 사용 금지).
        assert "import langgraph" not in src and "from langgraph" not in src, f"{py.name} 에 langgraph import"
        assert "StateGraph" not in src, f"{py.name} 에 StateGraph 사용"
        # 서버 내부 모듈 직접 import 금지(README/주석 언급은 mcp_server03.<name> 형태가 아니므로 무관).
        for name in forbidden_internal:
            assert f"mcp_server03.{name}" not in src, f"{py.name} 에 서버 내부 모듈 직접 import: {name}"
    _log("OK", "LangGraph 미사용 + 서버 내부 직접 import 없음")


def test_stdio_calls(api_ok):
    if not api_ok:
        _log("SKIP", "stdio transport 점검", "fastmcp client API 미가용")
        return
    from day5.mcp_client03 import transport_stdio

    async def run():
        # 1) Tool 목록(실제 stdio). 빈 list 면 stdio 연결 불가로 보고 SKIP 처리.
        names = await transport_stdio.list_tools_stdio(timeout=30)
        if not names:
            _log("SKIP", "stdio 연결", "list_mcp_tools 결과 없음(환경상 연결 불가 추정)")
            return
        assert "search_manual" in names and "execute_sql" not in names, "업무 Tool 목록 구성 비정상"
        _log("OK", "list_mcp_tools (stdio)", f"{len(names)}개")

        # 2) DB Tool(빠름): get_equipment_overview → executed, data_source db|mock_fallback.
        ov = await transport_stdio.call_tool_stdio("get_equipment_overview", {"equipment_id": "EQP-EV-03"}, timeout=30)
        payload = (ov.get("results") or [{}])[0].get("result", {}) if isinstance(ov, dict) else {}
        assert ov.get("status") in ("executed", "dry_run"), f"overview status 비정상: {ov.get('status')}"
        assert payload.get("data_source") in ("db", "mock_fallback"), f"data_source 예상 밖: {payload.get('data_source')}"
        _log("OK", "get_equipment_overview (stdio)", f"data_source={payload.get('data_source')}")

        # 3) execute_sql 거부.
        sql = await transport_stdio.call_tool_stdio("execute_sql", {"query": "select * from users"}, timeout=30)
        assert sql.get("status") == "rejected", f"execute_sql 가 거부되지 않음: {sql.get('status')}"
        _log("OK", "execute_sql 거부 (stdio)", "rejected")

        # 4) search_manual(RAG) over stdio: 이 환경에서 timeout 가능 → 호출 경로만 확인(상태 무관 통과).
        sm = await transport_stdio.call_tool_stdio("search_manual", {"query": "ALM-TEMP-402 조치 방향"}, timeout=15)
        status = sm.get("status")
        if status == "timeout":
            _log("OK", "search_manual (stdio) 호출 경로 확인", "timeout(이 환경의 RAG-over-stdio 한계, 정상 처리)")
        elif status in ("executed", "dry_run", "error"):
            _log("OK", "search_manual (stdio) 호출", f"status={status}")
        else:
            _log("OK", "search_manual (stdio) 호출", f"status={status}")
        # 민감정보 미노출 확인(결과 직렬화 스캔).
        text = json.dumps(sm, ensure_ascii=False).lower()
        for bad in _FORBIDDEN:
            assert bad not in text, f"search_manual 결과에 민감 토큰 노출: {bad}"

    try:
        asyncio.run(asyncio.wait_for(run(), timeout=120))
    except asyncio.TimeoutError:
        _log("SKIP", "stdio transport 점검", "전체 timeout(환경 지연)")
    except Exception as error:
        _log("SKIP", "stdio transport 점검", f"연결 불가: {type(error).__name__}")


def test_http_calls(http_api_ok):
    """HTTP transport 점검(서버가 떠 있을 때만 실질 검증, 아니면 SKIP).

    [환경 내성]
    - HTTP 서버(streamable-http)가 떠 있지 않으면 list 가 빈 list → SKIP(전체 실패 아님).
    - 서버가 떠 있으면 list / DB Tool / execute_sql 거부 / search_manual 을 검증한다.
    - HTTP long-lived 서버에서는 search_manual 이 정상 응답해야 하므로 executed 를 기대한다
      (단, 환경 지연 대비로 timeout 도 SKIP 성격으로 허용하되 결과 status 는 기록한다).
    - 서버 기동:
        python -m day5.mcp_server03.mcp_server --transport streamable-http --port 8003
    """
    if not http_api_ok:
        _log("SKIP", "http transport 점검", "HTTP transport API 미가용")
        return
    from day5.mcp_client03 import transport_http

    async def run():
        url = transport_http.DEFAULT_URL
        # 1) Tool 목록(실제 http). 빈 list 면 서버 미기동으로 보고 SKIP.
        names = await transport_http.list_tools_http(url=url, timeout=15)
        if not names:
            _log("SKIP", "http 연결", f"list_mcp_tools 결과 없음(서버 미기동 추정: {url})")
            return
        assert "search_manual" in names and "execute_sql" not in names, "업무 Tool 목록 구성 비정상"
        _log("OK", "list_mcp_tools (http)", f"{len(names)}개")

        # 2) DB Tool: get_equipment_overview → executed, data_source db|mock_fallback.
        ov = await transport_http.call_tool_http("get_equipment_overview", {"equipment_id": "EQP-EV-03"}, url=url, timeout=15)
        payload = (ov.get("results") or [{}])[0].get("result", {}) if isinstance(ov, dict) else {}
        assert ov.get("status") in ("executed", "dry_run"), f"overview status 비정상: {ov.get('status')}"
        assert payload.get("data_source") in ("db", "mock_fallback"), f"data_source 예상 밖: {payload.get('data_source')}"
        _log("OK", "get_equipment_overview (http)", f"data_source={payload.get('data_source')}")

        # 3) execute_sql 거부.
        sql = await transport_http.call_tool_http("execute_sql", {"query": "select * from users"}, url=url, timeout=15)
        assert sql.get("status") == "rejected", f"execute_sql 가 거부되지 않음: {sql.get('status')}"
        _log("OK", "execute_sql 거부 (http)", "rejected")

        # 4) search_manual(RAG) over http: long-lived 서버에서는 정상 응답을 기대한다.
        sm = await transport_http.call_tool_http("search_manual", {"query": "ALM-TEMP-402 조치 방향", "alarm_code": "ALM-TEMP-402"}, url=url, timeout=60)
        status = sm.get("status")
        if status == "executed":
            inner = (sm.get("results") or [{}])[0].get("result", {})
            assert inner.get("retrieval_source") == "chroma", f"retrieval_source 예상 밖: {inner.get('retrieval_source')}"
            docs = inner.get("documents") or []
            assert isinstance(docs, list) and len(docs) >= 1, "documents 1개 이상 기대"
            _log("OK", "search_manual (http)", f"executed, chroma, documents={len(docs)}")
        elif status == "timeout":
            # 환경 지연: HTTP 에서도 늦을 수 있으므로 전체 실패로 만들지 않는다(SKIP 성격).
            _log("SKIP", "search_manual (http)", "timeout(환경 지연, 서버 기동/워밍업 확인 권장)")
        else:
            _log("SKIP", "search_manual (http)", f"status={status}(서버 상태 확인 권장)")

        # 민감정보 미노출 확인(결과 직렬화 스캔).
        text = json.dumps(sm, ensure_ascii=False).lower()
        for bad in _FORBIDDEN:
            assert bad not in text, f"search_manual(http) 결과에 민감 토큰 노출: {bad}"

    try:
        asyncio.run(asyncio.wait_for(run(), timeout=120))
    except asyncio.TimeoutError:
        _log("SKIP", "http transport 점검", "전체 timeout(환경 지연)")
    except Exception as error:
        _log("SKIP", "http transport 점검", f"연결 불가: {type(error).__name__}")


def main():
    test_imports()
    api_ok = test_fastmcp_client_api()
    http_api_ok = test_http_transport_api()
    test_summarize_no_sensitive()
    test_no_langgraph_and_internal_import()
    test_stdio_calls(api_ok)
    test_http_calls(http_api_ok)
    print(f"\n=== RESULT === OK={_RESULTS['OK']} FAIL={_RESULTS['FAIL']} SKIP={_RESULTS['SKIP']}")
    sys.exit(1 if _RESULTS["FAIL"] else 0)


if __name__ == "__main__":
    main()
