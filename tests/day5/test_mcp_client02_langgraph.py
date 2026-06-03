# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 - LangGraph 멀티 에이전트 client 점검 스크립트

[실행]
    uv run python tests/day5/test_mcp_client02_langgraph.py

[설계]
- pytest 가 없어도 단독 실행되도록 작성(각 점검을 함수로 두고 __main__ 에서 순차 실행).
- PostgreSQL 이 꺼져 있어도 전체가 실패하지 않게 한다(DB Tool 결과가 db/mock_fallback 어느 쪽이어도 통과).
- 비밀값/문서 전문/민감 컬럼이 출력에 섞이지 않는지 확인한다.

[점검 항목]
1) import / graph build
2) Planner 가 alarm_code/equipment_id/need_* 추출
3) Agent 결과 표준 구조 + 전용 key 사용
4) need_*=False 질문에서 해당 Agent 가 skipped
5) 기본 query 실행 + final_answer 생성
6) DB on/off 무관(db|mock_fallback) 통과
7) 출력에 민감 토큰 미노출
8) graph_nodes 가 서버 내부 모듈을 직접 import 하지 않음(정적 검사)
"""
from __future__ import annotations

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


_FORBIDDEN_IN_OUTPUT = (
    "password", "token", "secret", "connection", "dsn",
    "full_text", "chroma:document", "source_path", "file_path", "internal_url",
    "raw_metadata", "operator_note", "technician_note", "lot_id",
)
_AGENT_KEYS = ("rag_result", "equipment_result", "alarm_result", "quality_result", "maintenance_result")
_STANDARD_FIELDS = ("agent", "status", "tool_name", "result_summary", "error_summary")


def test_import_and_build():
    import day5.mcp_client02.client_app  # noqa: F401
    from day5.mcp_client02.graph_builder import build_graph
    graph = build_graph()
    assert graph is not None, "graph build 실패"
    _log("OK", "import + graph build")


def test_planner_extraction():
    from day5.mcp_client02.graph_nodes import planner_node
    out = planner_node({"user_query": "EQP-EV-03에서 ALM-TEMP-402 반복 발생 시 조치 방향과 품질 영향"})
    assert out.get("equipment_id") == "EQP-EV-03", "equipment_id 추출 실패"
    assert out.get("alarm_code") == "ALM-TEMP-402", "alarm_code 추출 실패(잘림 등)"
    assert out.get("need_rag") is True and out.get("need_quality") is True, "need_* 추출 실패"
    _log("OK", "Planner 추출", f"eq={out['equipment_id']} alarm={out['alarm_code']} need_rag={out['need_rag']}")


def test_agent_standard_structure_and_keys():
    from day5.mcp_client02.graph_nodes import rag_agent_node, quality_agent_node
    # rag_agent 는 rag_result 전용 key 만 반환해야 한다.
    out = rag_agent_node({"user_query": "ALM-TEMP-402 조치 방향", "need_rag": True, "alarm_code": "ALM-TEMP-402"})
    assert list(out.keys()) == ["rag_result"], f"rag_agent 가 전용 key 외를 반환: {list(out.keys())}"
    res = out["rag_result"]
    for f in _STANDARD_FIELDS:
        assert f in res, f"표준 결과 필드 누락: {f}"
    assert res["status"] in ("executed", "error"), f"rag status 비정상: {res['status']}"
    _log("OK", "Agent 표준 구조 + 전용 key", f"rag status={res['status']}")
    # quality_agent: need_quality=False → skipped, quality_result 전용 key.
    sk = quality_agent_node({"need_quality": False})
    assert list(sk.keys()) == ["quality_result"], "quality_agent 전용 key 위반"
    assert sk["quality_result"]["status"] == "skipped", "need_quality=False 인데 skipped 아님"
    _log("OK", "need_*=False → skipped", "quality_agent skipped")


def test_run_query_and_answer():
    from day5.mcp_client02.client_app import run_query
    state = run_query("EQP-EV-03에서 ALM-TEMP-402 반복 발생 시 조치 방향과 품질 영향을 알려줘")
    # final_answer 생성.
    assert isinstance(state.get("final_answer"), str) and state["final_answer"], "final_answer 미생성"
    # 각 Agent 결과가 표준 구조이고 status 가 허용 집합.
    for key in _AGENT_KEYS:
        res = state.get(key) or {}
        assert res.get("status") in ("executed", "skipped", "error"), f"{key} status 비정상: {res.get('status')}"
    # DB on/off 무관: executed 인 DB Agent 의 data_source 가 db|mock_fallback.
    for key in ("equipment_result", "alarm_result", "quality_result", "maintenance_result"):
        res = state.get(key) or {}
        if res.get("status") == "executed":
            ds = (res.get("result_summary") or {}).get("data_source")
            assert ds in ("db", "mock_fallback"), f"{key} data_source 예상 밖: {ds}"
    _log("OK", "run_query + final_answer", "DB on/off 무관 통과")
    return state


def test_no_sensitive_in_output(state):
    # final_answer + 전체 state 직렬화에 민감 토큰 원문이 없어야 한다.
    import json
    text = (state.get("final_answer", "") + " " + json.dumps(state, ensure_ascii=False, default=str)).lower()
    for bad in _FORBIDDEN_IN_OUTPUT:
        assert bad not in text, f"출력/state 에 민감 토큰 노출: {bad}"
    _log("OK", "민감 토큰 미노출", "final_answer + state 스캔")


def test_no_internal_import():
    # graph_nodes / tool_calling 소스에 서버 내부 모듈 직접 import 가 없어야 한다.
    forbidden = ("repositories", "db_access", "rag_quality_adapter", "rag_search",
                 "equipment_data", "manual_search")
    for mod in ("graph_nodes.py", "tool_calling.py"):
        src = (_SRC / "day5" / "mcp_client02" / mod).read_text(encoding="utf-8")
        # 'from day5.mcp_server03.<forbidden> import' / 'import day5.mcp_server03.<forbidden>' 패턴 점검.
        for name in forbidden:
            assert f"mcp_server03.{name}" not in src, f"{mod} 에 서버 내부 모듈 직접 import: {name}"
    _log("OK", "서버 내부 모듈 직접 import 없음", "Tool entrypoint 만 사용")


def main():
    test_import_and_build()
    test_planner_extraction()
    test_agent_standard_structure_and_keys()
    state = test_run_query_and_answer()
    test_no_sensitive_in_output(state)
    test_no_internal_import()
    print(f"\n=== RESULT === OK={_RESULTS['OK']} FAIL={_RESULTS['FAIL']} SKIP={_RESULTS['SKIP']}")
    sys.exit(1 if _RESULTS["FAIL"] else 0)


if __name__ == "__main__":
    main()
