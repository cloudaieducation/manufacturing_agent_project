# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 - LangGraph 그래프 구성 (graph)

[이 파일의 역할]
supervisor → (조건부 분기) → 각 Agent → answer 의 LangGraph StateGraph 를 조립/compile 합니다.

[그래프 구조]
    START → supervisor
    supervisor ─(route)→ tools | db | safety | rag        (조건부 분기, 하나만 실행)
    tools/db/safety/rag → answer                          (합류)
    answer → END
    (route=="answer" 이면 supervisor → answer 로 바로 갈 수도 있게 분기 대상에 answer 포함)

[ToolCaller 주입]
Tool 호출이 필요한 Node(tools/db/safety)는 functools.partial 로 ToolCaller 를 묶어 등록합니다.
테스트는 build_graph(fake_caller) 로 외부 서버 없이 그래프를 돌릴 수 있습니다.

[단일 경로 — 충돌 없음]
supervisor 가 route 를 하나만 고르므로, 한 번 invoke 에 Agent 하나만 실행됩니다(병렬 아님).
따라서 State 동시 업데이트 충돌이 없습니다(messages/errors 는 그래도 reducer 로 누적).
"""
from __future__ import annotations

from functools import partial

from langgraph.graph import StateGraph, START, END

from day5.mcp_client04.state import ClientState
from day5.mcp_client04 import agents


def _route_selector(state: dict) -> str:
    """supervisor 가 정한 route 값을 그대로 다음 Node 이름으로 사용한다(없으면 answer)."""
    route = state.get("route")
    return route if route in ("tools", "db", "safety", "rag", "answer") else "answer"


def build_graph(tool_caller=None):
    """mcp_client04 멀티 에이전트 그래프를 조립하고 compile 한 실행 객체를 돌려준다.

    [입력] tool_caller: 업무 Tool 호출자(실제 StdioToolCaller 또는 테스트용 Fake). None 이면 Tool 미호출.
    [반환] compiled graph (invoke(state) 로 실행).
    """
    graph = StateGraph(ClientState)

    # Node 등록: Tool 이 필요한 Node 는 partial 로 tool_caller 를 묶어, LangGraph 가 node(state) 로 호출해도
    # 내부적으로 agents.x(state, tool_caller=tool_caller) 가 되게 한다.
    graph.add_node("supervisor", partial(agents.supervisor_agent, tool_caller=tool_caller))
    graph.add_node("tools", partial(agents.tool_discovery_agent, tool_caller=tool_caller))
    graph.add_node("db", partial(agents.db_agent, tool_caller=tool_caller))
    graph.add_node("safety", partial(agents.safety_agent, tool_caller=tool_caller))
    graph.add_node("rag", partial(agents.rag_agent, tool_caller=tool_caller))
    graph.add_node("answer", partial(agents.answer_agent, tool_caller=tool_caller))

    # 진입: START → supervisor.
    graph.add_edge(START, "supervisor")

    # 조건부 분기: supervisor 가 정한 route 로 한 Node 만 실행한다.
    graph.add_conditional_edges(
        "supervisor",
        _route_selector,
        {"tools": "tools", "db": "db", "safety": "safety", "rag": "rag", "answer": "answer"},
    )

    # 합류: tools/db/safety/rag 는 모두 answer 로 모인다(answer 는 아래에서 END 로).
    for node in ("tools", "db", "safety", "rag"):
        graph.add_edge(node, "answer")

    # 종료: answer → END.
    graph.add_edge("answer", END)

    return graph.compile()
