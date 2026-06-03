# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 - LangGraph State 정의 (state)

[이 파일의 역할]
LangGraph 그래프가 Node 사이에서 주고받는 상태(State) 스키마를 정의합니다.
이 단계 그래프는 supervisor → (하나의 agent) → answer 의 '단일 경로'라 병렬 충돌은 없지만,
여러 Node 가 메시지/오류를 누적할 수 있으므로 messages/errors 에는 reducer(operator.add)를 둡니다.

[프로젝트 스타일]
mcp_client02 와 동일하게 TypedDict + Annotated reducer 방식을 사용합니다(Pydantic 미사용).
"""
from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict


class ClientState(TypedDict, total=False):
    """mcp_client04 멀티 에이전트 그래프의 공유 상태.

    [필드]
        user_query     : 사용자 질문(입력).
        route          : supervisor 가 정한 경로(tools/db/safety/rag/answer).
        available_tools: tool_discovery 가 채운 업무 Tool 이름 목록.
        tool_results   : 각 agent 가 담은 Tool 호출 요약 결과(dict).
        sql            : (safety 관련) 감지/차단 대상 SQL 텍스트(있을 때만).
        safety_status  : safety_agent 판정(OK / BLOCKED 등).
        rag_status     : rag_agent 판정(이 단계 기본 SKIPPED).
        messages       : 각 Node 가 남기는 사람이 읽을 메시지(누적 → reducer).
        final_answer   : answer_agent 가 만든 최종 응답.
        errors         : 오류 누적(reducer).
        allow_rag      : RAG(search_manual) 실제 호출 허용 여부(기본 False → rag_agent SKIPPED).
    """
    user_query: str
    route: Optional[str]
    available_tools: list
    tool_results: dict
    sql: Optional[str]
    safety_status: Optional[str]
    rag_status: Optional[str]
    messages: Annotated[list, operator.add]
    final_answer: str
    errors: Annotated[list, operator.add]
    allow_rag: bool


def build_initial_state(user_query: str, allow_rag: bool = False) -> dict:
    """invoke 에 넘길 초기 State 를 만든다(필수 입력 + reducer 채널 초기화).

    [입력]
        user_query: 사용자 질문.
        allow_rag : RAG(search_manual) 실제 호출 허용 여부. 기본 False(rag_agent 가 SKIPPED).
                    True 면 rag_agent 가 ToolCaller(주로 HTTP)로 search_manual 을 실제 호출한다.
    [반환] messages/errors 를 빈 리스트로 초기화하고 tool_results 를 빈 dict 로 둔 State.
    """
    return {
        "user_query": user_query,
        "tool_results": {},
        "messages": [],
        "errors": [],
        "allow_rag": bool(allow_rag),
    }
