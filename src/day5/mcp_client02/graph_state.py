# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 - LangGraph State 정의 (ClientState)

[이 파일의 역할]
LangGraph 그래프가 Node 사이에서 주고받는 '상태(State)' 스키마를 정의합니다.
멀티 에이전트 병렬 구조에서 '어떤 key 를 누가 쓰는지'를 명확히 해 충돌을 막는 것이 핵심입니다.

[State 는 '노드 사이에서 공유되는 작업 기록지']
LangGraph 는 하나의 State dict 를 Node → Node 로 전달합니다. 각 Node 는 이 기록지에서 필요한
칸(key)을 읽고, 자기가 책임지는 칸만 채워서 돌려줍니다. 그러면 LangGraph 가 그 부분 업데이트를
전체 State 에 합쳐 다음 Node 로 넘깁니다. 즉 State 는 노드들이 번갈아 적어 나가는 공용 작업 기록지이며,
이 파일은 그 기록지에 '어떤 칸이 있고, 각 칸은 누가 쓰고 누가 읽는지'를 미리 약속해 둔 양식입니다.

[State 충돌 방지 설계 — 매우 중요]
- 병렬로 실행되는 Agent Node 들은 '자기 전용 key' 만 업데이트한다.
    rag_agent → rag_result, equipment_agent → equipment_result, alarm_agent → alarm_result,
    quality_agent → quality_result, maintenance_agent → maintenance_result
  → 서로 다른 key 만 쓰므로 LangGraph 의 동시 업데이트 충돌이 생기지 않는다.
- 여러 Node 가 누적해야 하는 errors 는 reducer(operator.add)를 둬서 안전하게 합친다.
  (각 Agent 가 errors=[...] 를 돌려주면 LangGraph 가 기존 리스트에 더해 준다.)

[저장 정책]
- Tool 결과 '전체 dict' 가 아니라 '요약/표준화된 구조' 만 저장한다(민감정보/문서 전문 미보관).
"""
from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict


class ClientState(TypedDict, total=False):
    """LangGraph 멀티 에이전트 client 의 공유 상태.

    total=False 로 두어, 각 Node 가 '자기가 채우는 key' 만 부분 업데이트해도 되게 한다.
    """
    # 입력: client_app/build_initial_state 가 채우고, planner 와 각 agent 가 읽는다.
    user_query: str

    # Planner 가 추출하는 식별자(단일 writer = planner / reader = 각 agent, evidence_check)
    equipment_id: Optional[str]
    alarm_code: Optional[str]
    metric_name: Optional[str]

    # Planner 가 정하는 Agent 실행 여부 flag(단일 writer = planner / reader = 해당 agent)
    # 각 agent 는 자기 need_* 가 True 일 때만 Tool 을 호출하고, False 면 skip 한다.
    need_rag: bool
    need_equipment: bool
    need_alarm: bool
    need_quality: bool
    need_maintenance: bool

    # 각 Agent 전용 결과 key(에이전트별 단일 writer → 병렬 충돌 없음)
    # writer = 같은 이름의 agent_node / reader = evidence_check, synthesis(최종 답변 구성).
    rag_result: Optional[dict]
    equipment_result: Optional[dict]
    alarm_result: Optional[dict]
    quality_result: Optional[dict]
    maintenance_result: Optional[dict]

    # 여러 Node 가 누적할 수 있는 오류 목록 → reducer(operator.add)로 안전 병합
    # 여러 agent 가 동시에 errors=[...] 를 돌려줘도 reducer 가 리스트를 '더해' 합치므로 충돌 없음.
    errors: Annotated[list, operator.add]

    # Evidence Check 결과(단일 writer = evidence_check / reader = synthesis, client_app 출력)
    evidence_flags: dict

    # 최종 답변(단일 writer = synthesis / reader = client_app 의 화면 출력)
    final_answer: str
