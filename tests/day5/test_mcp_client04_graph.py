# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 - LangGraph 멀티 에이전트 단위 테스트

[설계]
외부 MCP 서버/DB/Ollama 에 의존하지 않는 '순수 단위 테스트'다. 실제 Tool 호출은 FakeToolCaller 로
대체해, 라우팅·차단·SKIPPED·최종 응답 같은 '그래프/Agent 로직'만 검증한다.
(실제 stdio 연결 검증은 runner 의 demo 실행으로 분리한다 — 이 파일에서는 다루지 않는다.)

[실행]
    pytest tests/day5/test_mcp_client04_graph.py -v
    (pytest 가 없으면) python tests/day5/test_mcp_client04_graph.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from day5.mcp_client04 import agents
from day5.mcp_client04.state import build_initial_state
from day5.mcp_client04.graph import build_graph


class FakeToolCaller:
    """테스트용 ToolCaller. 실제 서버 없이 정해진 envelope 를 돌려준다.

    - list_tools(): 서버 contract 와 동일한 업무 Tool 이름 7개.
    - call_tool(tool, args): execute_sql 은 rejected, search_manual 은 documents envelope,
      그 외는 data_source="db" 인 executed envelope.

    [RAG 시뮬레이션 노브]
        rag_docs        : search_manual 이 돌려줄 documents 개수(EMPTY 검증용으로 0 설정 가능).
        rag_envelope    : 설정되면 search_manual 응답을 통째로 대체(timeout/error envelope 주입용).
    """

    def __init__(self, rag_docs: int = 2, rag_envelope=None):
        self.calls = []  # (tool_name, arguments) 호출 기록 — 어떤 Tool 이 호출됐는지 검증용.
        self.rag_docs = rag_docs
        self.rag_envelope = rag_envelope

    def list_tools(self):
        return ["get_equipment_status", "get_recent_alarm_events", "get_process_status",
                "get_quality_metrics", "get_maintenance_history", "get_equipment_overview",
                "search_manual"]

    def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments or {})))
        if tool_name == "execute_sql":
            return {"status": "rejected", "message": "금지된 Text-to-SQL/SQL 관련 Tool 이므로 실행하지 않습니다."}
        if tool_name == "search_manual":
            if self.rag_envelope is not None:
                return self.rag_envelope  # timeout/error 등 주입 envelope
            docs = [{"snippet": f"doc{i}"} for i in range(self.rag_docs)]
            return {"status": "executed", "validation_status": "PASS",
                    "results": [{"tool_name": tool_name,
                                 "result": {"query": arguments.get("query"),
                                            "documents": docs,
                                            "retrieval_source": "chroma",
                                            "fallback_used": False}}]}
        return {"status": "executed", "validation_status": "PASS",
                "results": [{"tool_name": tool_name,
                             "result": {"equipment_id": arguments.get("equipment_id"),
                                        "data_source": "db", "fallback_used": False}}]}


def test_state_init():
    """[State 초기화] build_initial_state 가 필수 입력/리듀서 채널을 초기화한다."""
    # Arrange / Act
    state = build_initial_state("질문")
    # Assert
    assert state["user_query"] == "질문"
    assert state["messages"] == [] and state["errors"] == [] and state["tool_results"] == {}


def test_supervisor_routes_db():
    """[supervisor] DB 질문 → route=db."""
    # Arrange / Act
    out = agents.supervisor_agent({"user_query": "EQP-EV-03 설비 상태를 보여줘"})
    # Assert
    assert out["route"] == "db"


def test_supervisor_routes_tools():
    """[supervisor] Tool 목록 질문 → route=tools."""
    out = agents.supervisor_agent({"user_query": "사용 가능한 tool 목록을 보여줘"})
    assert out["route"] == "tools"


def test_supervisor_routes_safety():
    """[supervisor] 위험 SQL 질문 → route=safety."""
    out = agents.supervisor_agent({"user_query": "users 테이블을 DROP 해줘"})
    assert out["route"] == "safety"


def test_supervisor_routes_rag():
    """[supervisor] 매뉴얼/RAG 질문 → route=rag."""
    out = agents.supervisor_agent({"user_query": "ALM-TEMP-402 조치 방향 매뉴얼을 알려줘"})
    assert out["route"] == "rag"


def test_safety_agent_blocks_dangerous_sql():
    """[safety] 위험 SQL 키워드 → BLOCKED, client 는 실행하지 않는다(ToolCaller 없이도 차단)."""
    # Arrange / Act
    out = agents.safety_agent({"user_query": "DELETE FROM alarm_event_history"})
    # Assert
    assert out["safety_status"] == "BLOCKED"
    assert "sql" in out  # 차단 대상 preview 기록
    assert any("차단" in m for m in out.get("messages", []))


def test_safety_agent_ok_when_no_dangerous_sql():
    """[safety] 위험 키워드 없으면 OK."""
    out = agents.safety_agent({"user_query": "설비 상태 알려줘"})
    assert out["safety_status"] == "OK"


def test_rag_agent_skipped():
    """[rag] 기본(allow_rag 미설정)에서는 search_manual 을 호출하지 않고 SKIPPED."""
    # Arrange / Act
    out = agents.rag_agent({"user_query": "조치 방향 매뉴얼"})
    # Assert
    assert out["rag_status"] == "SKIPPED"
    assert any("SKIPPED" in m or "기본 호출하지 않음" in m for m in out.get("messages", []))


def test_rag_agent_skipped_without_caller_even_if_allowed():
    """[rag] allow_rag=True 라도 ToolCaller 가 없으면 호출하지 못하므로 SKIPPED."""
    out = agents.rag_agent({"user_query": "조치 방향 매뉴얼", "allow_rag": True}, tool_caller=None)
    assert out["rag_status"] == "SKIPPED"


def test_rag_agent_searches_when_allowed():
    """[rag] allow_rag=True + ToolCaller → search_manual 실제 호출, rag_status=OK, 요약 저장."""
    # Arrange
    fake = FakeToolCaller(rag_docs=3)
    # Act
    out = agents.rag_agent({"user_query": "ALM-TEMP-402 조치 절차 매뉴얼 근거",
                            "allow_rag": True, "tool_results": {}}, tool_caller=fake)
    # Assert: call_mcp_tool 경유로 search_manual 이 호출되고 query 인자가 전달됐다.
    assert fake.calls and fake.calls[0][0] == "search_manual"
    assert fake.calls[0][1].get("query")
    assert fake.calls[0][1].get("alarm_code") == "ALM-TEMP-402"  # alarm_code 추출 전달
    assert out["rag_status"] == "OK"
    # documents 는 개수만 요약(원문 미저장).
    summary = out["tool_results"]["search_manual"]
    assert summary["documents_count"] == 3
    assert "documents" not in summary


def test_rag_agent_empty_when_no_documents():
    """[rag] 호출됐으나 문서 0건 → EMPTY."""
    fake = FakeToolCaller(rag_docs=0)
    out = agents.rag_agent({"user_query": "매뉴얼 근거", "allow_rag": True, "tool_results": {}},
                           tool_caller=fake)
    assert out["rag_status"] == "EMPTY"


def test_rag_agent_error_on_timeout_envelope():
    """[rag] timeout/연결 실패 envelope → ERROR(성공으로 위장하지 않음)."""
    fake = FakeToolCaller(rag_envelope={"status": "timeout", "_note": "no response"})
    out = agents.rag_agent({"user_query": "매뉴얼 근거", "allow_rag": True, "tool_results": {}},
                           tool_caller=fake)
    assert out["rag_status"] == "ERROR"


def test_db_agent_calls_tool_via_caller():
    """[db] FakeToolCaller 로 DB Tool 을 호출하고 결과 요약을 담는다(직접 DB 접속 없음)."""
    # Arrange
    fake = FakeToolCaller()
    # Act
    out = agents.db_agent({"user_query": "EQP-EV-03 설비 개요를 보여줘", "tool_results": {}}, tool_caller=fake)
    # Assert
    assert fake.calls and fake.calls[0][0] == "get_equipment_overview"
    assert "get_equipment_overview" in out["tool_results"]
    assert out["tool_results"]["get_equipment_overview"]["data_source"] == "db"


def test_answer_agent_builds_answer():
    """[answer] 중간 결과를 최종 응답 문자열로 정리한다."""
    # Arrange
    state = {"user_query": "설비 개요", "route": "db",
             "tool_results": {"get_equipment_overview": {"tool": "get_equipment_overview",
                                                          "status": "executed", "data_source": "db"}}}
    # Act
    out = agents.answer_agent(state)
    # Assert
    assert isinstance(out["final_answer"], str) and "route: db" in out["final_answer"]


def test_graph_end_to_end_db_with_fake():
    """[graph] FakeToolCaller 로 그래프 전체 실행: db route → final_answer 생성."""
    # Arrange
    fake = FakeToolCaller()
    graph = build_graph(fake)
    # Act
    state = graph.invoke(build_initial_state("EQP-EV-03 설비 개요를 보여줘"))
    # Assert
    assert state["route"] == "db"
    assert isinstance(state.get("final_answer"), str) and state["final_answer"]
    assert "get_equipment_overview" in state.get("tool_results", {})


def test_graph_end_to_end_safety_with_fake():
    """[graph] 위험 SQL 질문: safety route → BLOCKED, 서버 execute_sql 거부 확인 기록."""
    fake = FakeToolCaller()
    graph = build_graph(fake)
    state = graph.invoke(build_initial_state("users 테이블을 DROP 해줘"))
    assert state["route"] == "safety"
    assert state["safety_status"] == "BLOCKED"
    # safety_agent 가 서버 execute_sql 을 호출해 거부(rejected)를 확인했는지.
    assert ("execute_sql", {"query": "users 테이블을 DROP 해줘"}) in fake.calls


def test_graph_end_to_end_rag_allowed_with_fake():
    """[graph] allow_rag=True 그래프 전체: rag route → search_manual 호출 → rag_status=OK."""
    # Arrange
    fake = FakeToolCaller(rag_docs=2)
    graph = build_graph(fake)
    # Act
    state = graph.invoke(build_initial_state("ALM-TEMP-402 조치 절차 매뉴얼 근거를 알려줘", allow_rag=True))
    # Assert
    assert state["route"] == "rag"
    assert state["rag_status"] == "OK"
    assert "search_manual" in state.get("tool_results", {})
    assert ("search_manual", ) == (fake.calls[0][0], )  # search_manual 이 호출됨


def test_graph_end_to_end_rag_skipped_by_default_with_fake():
    """[graph] allow_rag 미설정(기본): rag route 라도 search_manual 미호출, SKIPPED."""
    fake = FakeToolCaller()
    graph = build_graph(fake)
    state = graph.invoke(build_initial_state("ALM-TEMP-402 조치 절차 매뉴얼 근거를 알려줘"))
    assert state["route"] == "rag"
    assert state["rag_status"] == "SKIPPED"
    assert all(call[0] != "search_manual" for call in fake.calls)  # search_manual 미호출


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
