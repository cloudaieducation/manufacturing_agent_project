# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 - LangGraph 그래프 빌더 (fan-out / fan-in)

[이 파일의 역할]
Planner → 5개 Agent(병렬) → Evidence Check → Synthesis 의 LangGraph 그래프를 조립/compile 합니다.

[그래프 구조]
    START → planner
    planner → rag_agent / equipment_agent / alarm_agent / quality_agent / maintenance_agent   (fan-out)
    (5 Agent) → evidence_check                                                                  (fan-in: 모두 끝난 뒤 1회)
    evidence_check → synthesis → END

[병렬에 대한 정확한 설명 — 매우 중요]
- 위 fan-out 은 'LangGraph 구조상' 5개 Agent 가 같은 단계(super-step)에 놓이는 '논리적 병렬' 구조다.
- call_mcp_tool 이 동기(sync) 함수이므로, 이 단계에서 sync Node 들은 한 스레드에서 차례로 실행된다.
  즉 '벽시계 시간 동시 실행'은 보장하지 않는다(그래프 모양만 병렬).
- 진짜 동시 실행이 필요하면 후속 단계에서 async Node + asyncio.to_thread 또는 ThreadPoolExecutor 를
  검토한다(이번 단계 범위 밖, mcp_client03/후속 TODO).

[State 충돌]
- 각 Agent 는 자기 전용 key 만 반환하므로 병렬 업데이트 충돌이 없다.
- errors 는 graph_state 의 reducer(operator.add)로 누적된다.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from day5.mcp_client02.graph_state import ClientState
from day5.mcp_client02.graph_nodes import (
    planner_node,
    rag_agent_node,
    equipment_agent_node,
    alarm_agent_node,
    quality_agent_node,
    maintenance_agent_node,
    evidence_check_node,
)
from day5.mcp_client02.result_synthesis import synthesis_node


# 병렬로 실행될 Agent Node 이름 ↔ 함수 매핑(고정 Node + 내부 skip 방식).
_AGENT_NODES = {
    "rag_agent": rag_agent_node,
    "equipment_agent": equipment_agent_node,
    "alarm_agent": alarm_agent_node,
    "quality_agent": quality_agent_node,
    "maintenance_agent": maintenance_agent_node,
}


def build_graph():
    """멀티 에이전트 LangGraph 를 조립하고 compile 한 실행 객체를 돌려준다.

    [반환] compiled graph (invoke(state) 로 실행).
    [구조] START→planner→(5 Agent fan-out)→evidence_check(fan-in)→synthesis→END.
    """
    # StateGraph(ClientState): 이 그래프가 주고받을 State 스키마(graph_state.ClientState)를 지정한다.
    graph = StateGraph(ClientState)

    # Node 등록: add_node("이름", 함수) 로 '이름→실행 함수'를 그래프에 등록한다(아래 add_edge 가 이 이름으로 연결).
    graph.add_node("planner", planner_node)
    for name, fn in _AGENT_NODES.items():
        graph.add_node(name, fn)
    graph.add_node("evidence_check", evidence_check_node)
    graph.add_node("synthesis", synthesis_node)

    # 진입: START(그래프 시작 가상 지점) → planner. add_edge(a, b) 는 'a 다음에 b 를 실행'하라는 방향 연결.
    graph.add_edge(START, "planner")

    # fan-out: planner → 각 Agent. 한 Node(planner)에서 여러 Node 로 동시에 갈라진다(같은 super-step = 논리적 병렬).
    for name in _AGENT_NODES:
        graph.add_edge("planner", name)

    # fan-in: 각 Agent → evidence_check. 여러 Node 가 한 Node 로 모이며, 모든 Agent 가 끝난 뒤 evidence_check 가 1회 실행된다.
    for name in _AGENT_NODES:
        graph.add_edge(name, "evidence_check")

    # 종합: evidence_check → synthesis → END(그래프 종료 가상 지점). 여기는 단순 순차 연결이다.
    graph.add_edge("evidence_check", "synthesis")
    graph.add_edge("synthesis", END)

    # compile(): 위에서 정의한 Node/Edge 구성을 '실행 가능한 그래프 객체'로 확정한다(이후 invoke 로 실행).
    return graph.compile()


def build_initial_state(user_query: str) -> dict:
    """invoke 에 넘길 초기 State 를 만든다(필수 입력 + reducer 채널 초기화)."""
    return {
        "user_query": user_query,
        "errors": [],  # operator.add reducer 채널을 빈 리스트로 시작
    }
