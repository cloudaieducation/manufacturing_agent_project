# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 - LangGraph Node 구현 (Planner / Agent / Evidence Check)

[이 파일의 역할]
멀티 에이전트 그래프의 각 Node 로직을 둡니다. 모든 데이터 접근은 tool_calling 의
서버 Tool entrypoint wrapper 만 사용합니다(서버 내부 구현 직접 호출 금지).

[Node 구성]
- planner_node          : 규칙 기반으로 식별자/need_* flag 추출(LLM 미사용).
- rag/equipment/alarm/quality/maintenance _agent_node : need_* 가 True 면 Tool 호출, 아니면 skip.
- evidence_check_node   : 직접 근거/out_of_scope/ mock fallback 사용 여부 '표시'(차단 아님).

[병렬/충돌]
- Agent Node 는 각자 '전용 key' 만 반환한다(rag_result/equipment_result/...) → State 충돌 없음.
- 일부 Agent 실패는 status="error" 결과로 담고 errors 에 누적할 뿐, 전체 그래프를 멈추지 않는다.

[Synthesis]
- 최종 답변 생성(synthesis)은 result_synthesis.py 에 분리되어 있고, graph_builder 가 연결한다.
"""
from __future__ import annotations

import re

from day5.mcp_client02 import tool_calling
from day5.mcp_client02.result_formatting import compact_payload, extract_payload


# ---------------------------------------------------------------------------
# Planner 규칙(정규식/키워드) — 일반화 가능 규칙만 사용(case_id/expected_* 미사용)
# ---------------------------------------------------------------------------
# alarm_code: 문자형(ALM-TEMP-402)·숫자형(ALM-9999) 모두, 한글 조사 인접에도 전체 추출.
_ALARM_PATTERN = re.compile(r"(?<![A-Za-z0-9])ALM-(?:[A-Z]+-)?\d+(?![A-Za-z0-9-])", re.IGNORECASE)
# equipment_id: EQP-EV-03 / EQP-CVD-02
_EQUIP_PATTERN = re.compile(r"(?<![A-Za-z0-9])EQP-[A-Z]+-\d+(?![A-Za-z0-9])", re.IGNORECASE)

# metric_name 키워드 → 서버 allowlist 컬럼(수율/불량률/검사/이상).
_METRIC_KEYWORDS = [
    (("수율", "yield"), "yield_rate"),
    (("불량률", "defect"), "defect_rate"),
    (("검사 결과", "검사", "inspection"), "inspection_result"),
    (("이상", "abnormal"), "abnormal_flag"),
]

# need_* 판단 키워드(질문 의도 기반, 일반화 가능).
_NEED_RAG = ("조치", "매뉴얼", "근거", "설명", "주의", "이유", "방향", "트러블슈팅")
_NEED_ALARM = ("알람", "반복", "최근", "발생", "이력")
_NEED_QUALITY = ("품질", "수율", "불량률", "검사", "지표", "yield", "defect")
_NEED_EQUIPMENT = ("설비", "장비", "공정", "개요", "상태")
_NEED_MAINTENANCE = ("정비", "교체", "부품", "보전", "점검 이력")


def _detect_metric_name(text: str):
    """질문 텍스트에서 metric_name(allowlist 컬럼)을 추론한다(없으면 None)."""
    low = text.lower()
    for keywords, column in _METRIC_KEYWORDS:
        if any(kw.lower() in low for kw in keywords):
            return column
    return None


def planner_node(state: dict) -> dict:
    """규칙 기반 Planner: 식별자와 need_* flag 를 추출해 State 에 채운다(LLM 미사용).

    [입력] state["user_query"].
    [반환] equipment_id/alarm_code/metric_name + need_* flag dict.
    [주의] 특정 평가 질문/케이스에 맞춘 하드코딩 없이, 일반 정규식/키워드만 사용한다.
    """
    # 입력 State 에서 사용자 질문만 읽는다(Planner 는 그래프의 첫 작업 Node).
    query = str(state.get("user_query", "") or "")
    low = query.lower()

    # 정규식으로 질문 안의 식별자를 뽑는다(없으면 None). 어느 한 건만 매칭돼도 그 첫 매칭을 쓴다.
    alarm_match = _ALARM_PATTERN.search(query)
    equip_match = _EQUIP_PATTERN.search(query)
    alarm_code = alarm_match.group(0) if alarm_match else None
    equipment_id = equip_match.group(0) if equip_match else None
    metric_name = _detect_metric_name(query)

    # 질문 의도 키워드로 어떤 Agent 를 돌릴지(need_*) 판단한다. 뒤 Agent Node 들이 이 flag 를 읽는다.
    need_rag = any(k in query for k in _NEED_RAG)
    need_alarm = any(k in query for k in _NEED_ALARM)
    need_quality = any(k in low for k in (k.lower() for k in _NEED_QUALITY))
    need_equipment = any(k in query for k in _NEED_EQUIPMENT)
    need_maintenance = any(k in query for k in _NEED_MAINTENANCE)

    # 아무 의도도 잡히지 않으면 최소한 RAG 근거 검색은 시도한다(빈 응답 방지).
    if not any([need_rag, need_alarm, need_quality, need_equipment, need_maintenance]):
        need_rag = True

    return {
        "equipment_id": equipment_id,
        "alarm_code": alarm_code,
        "metric_name": metric_name,
        "need_rag": need_rag,
        "need_equipment": need_equipment,
        "need_alarm": need_alarm,
        "need_quality": need_quality,
        "need_maintenance": need_maintenance,
        "errors": [],  # reducer 채널 초기화(이후 Agent 가 누적)
    }


# ---------------------------------------------------------------------------
# Agent Node 공통 (고정 Node + 내부 skip 방식)
#   - 5개 Agent Node 는 항상 그래프에 존재한다(graph_builder 가 고정 등록).
#   - 각 Node 는 입력 State 에서 자기 need_* flag 와 식별자를 '읽고', 자기 전용 *_result key 만 '쓴다'.
#   - need_* 가 False 면 Tool 을 부르지 않고 _skipped 결과를 둔다(실행 안 함은 실패가 아니다).
# ---------------------------------------------------------------------------
def _skipped(agent: str, tool: str) -> dict:
    """Planner 가 필요 없다고 판단한 Agent 의 표준 'skipped' 결과(실패 아님)."""
    return {"agent": agent, "status": "skipped", "tool_name": tool,
            "result_summary": {}, "error_summary": None}


def _skipped_missing(agent: str, tool: str, reason: str) -> dict:
    """식별자 부족 등으로 호출하지 않고 건너뛴 Agent 결과(_skipped + 사유).

    _skipped() 와 동일한 표준 구조이며, error_summary 에 '왜 건너뛰었는지' 만 덧붙인다.
    """
    skip = _skipped(agent, tool)
    skip["error_summary"] = reason
    return skip


def _run_agent(agent: str, tool: str, arguments: dict) -> dict:
    """서버 Tool 을 호출하고 표준 Agent 결과 구조로 변환한다(executed/error).

    [표준 구조] {agent, status, tool_name, result_summary, error_summary}
    - 서버 envelope status 가 정상이면 payload 를 compact_payload 로 요약해 result_summary 에 담는다.
    - 호출 실패/예외/거부면 status="error" + 안전한 error_summary(원문 trace 미노출).
    """
    # 데이터 접근은 반드시 tool_calling wrapper 를 거친다(서버 Tool entrypoint 만 호출 / DB 직접 접속 금지).
    envelope = tool_calling.call_server_tool(tool, arguments)
    status = envelope.get("status") if isinstance(envelope, dict) else None

    # 클라이언트 측 예외(wrapper 가 만든 신호) 또는 서버 거부/오류 → error 로 표준화.
    if envelope.get("_client_error"):
        return {"agent": agent, "status": "error", "tool_name": tool,
                "result_summary": {}, "error_summary": f"client_error: {envelope.get('_client_error')}"}
    if status in ("rejected", "error"):
        return {"agent": agent, "status": "error", "tool_name": tool,
                "result_summary": {}, "error_summary": f"server_status: {status}"}

    # 정상 envelope → 단일 Tool result payload 를 꺼내(extract_payload) 민감정보 없는 요약으로 압축한다.
    payload = extract_payload(envelope)
    return {"agent": agent, "status": "executed", "tool_name": tool,
            "result_summary": compact_payload(payload), "error_summary": None}


def rag_agent_node(state: dict) -> dict:
    """RAG Agent: need_rag 면 search_manual 호출(매뉴얼/조치 근거). 결과 key = rag_result."""
    if not state.get("need_rag"):
        return {"rag_result": _skipped("rag_agent", "search_manual")}
    args = {"query": state.get("user_query", "")}
    if state.get("alarm_code"):
        args["alarm_code"] = state["alarm_code"]
    return {"rag_result": _run_agent("rag_agent", "search_manual", args)}


def equipment_agent_node(state: dict) -> dict:
    """Equipment Agent: need_equipment 면 get_equipment_overview 호출. 결과 key = equipment_result.

    초기 구현은 단순화를 위해 get_equipment_overview 우선(get_process_status 는 후속 확장 TODO).
    """
    if not state.get("need_equipment"):
        return {"equipment_result": _skipped("equipment_agent", "get_equipment_overview")}
    args = {}
    if state.get("equipment_id"):
        args["equipment_id"] = state["equipment_id"]
    return {"equipment_result": _run_agent("equipment_agent", "get_equipment_overview", args)}


def alarm_agent_node(state: dict) -> dict:
    """Alarm Agent: need_alarm 면 get_recent_alarm_events 호출. 결과 key = alarm_result."""
    if not state.get("need_alarm"):
        return {"alarm_result": _skipped("alarm_agent", "get_recent_alarm_events")}
    args = {}
    if state.get("equipment_id"):
        args["equipment_id"] = state["equipment_id"]
    if state.get("alarm_code"):
        args["alarm_code"] = state["alarm_code"]
    return {"alarm_result": _run_agent("alarm_agent", "get_recent_alarm_events", args)}


def quality_agent_node(state: dict) -> dict:
    """Quality Agent: need_quality 면 get_quality_metrics 호출. 결과 key = quality_result.

    [식별자 안전 처리]
        metric_name 또는 equipment_id 중 하나라도 있어야 서버가 대상 라인을 특정할 수 있다.
        둘 다 없으면 호출 대신 skipped 로 둔다(서버 contract any_of 위반/빈 결과 방지).
        metric_name 이 없고 equipment_id 만 있으면 서버가 기본 지표(defect_rate)로 처리한다.
    """
    if not state.get("need_quality"):
        return {"quality_result": _skipped("quality_agent", "get_quality_metrics")}
    metric_name = state.get("metric_name")
    equipment_id = state.get("equipment_id")
    if not metric_name and not equipment_id:
        # 대상 라인을 특정할 식별자가 없으면 호출하지 않고 skip(안전).
        return {"quality_result": _skipped_missing(
            "quality_agent", "get_quality_metrics", "식별자 부족(metric_name/equipment_id 없음)")}
    args = {}
    if metric_name:
        args["metric_name"] = metric_name
    if equipment_id:
        args["equipment_id"] = equipment_id
    return {"quality_result": _run_agent("quality_agent", "get_quality_metrics", args)}


def maintenance_agent_node(state: dict) -> dict:
    """Maintenance Agent: need_maintenance 면 get_maintenance_history 호출. 결과 key = maintenance_result."""
    if not state.get("need_maintenance"):
        return {"maintenance_result": _skipped("maintenance_agent", "get_maintenance_history")}
    if not state.get("equipment_id"):
        return {"maintenance_result": _skipped_missing(
            "maintenance_agent", "get_maintenance_history", "식별자 부족(equipment_id 없음)")}
    return {"maintenance_result": _run_agent(
        "maintenance_agent", "get_maintenance_history", {"equipment_id": state["equipment_id"]})}


# ---------------------------------------------------------------------------
# Evidence Check (Guardrail 전체가 아니라 '직접 근거 표시'만)
#   - fan-in Node: 5개 Agent 가 모두 끝난 뒤 1회 실행되며, 모든 *_result 를 한꺼번에 '읽기만' 한다.
#   - 출력은 evidence_flags 한 칸뿐이고, 이후 synthesis 가 이 flag 를 읽어 주의 문구에 반영한다.
# ---------------------------------------------------------------------------
_AGENT_RESULT_KEYS = (
    "rag_result", "equipment_result", "alarm_result", "quality_result", "maintenance_result",
)


def _result_text(result_summary: dict) -> str:
    """result_summary 를 소문자 문자열로 평탄화(식별자 포함 여부 검사용)."""
    return str(result_summary or "").lower()


def evidence_check_node(state: dict) -> dict:
    """직접 근거/ out_of_scope 가능성/ mock fallback 사용 여부를 '표시'한다(차단 아님).

    [출력] evidence_flags:
        {direct_evidence_found, missing_identifiers, out_of_scope_warning, used_mock_fallback, safety_notes}

    [중요] 이것은 Guardrail 전체가 아니다. 거절/차단하지 않고 '표시'만 한다.
           검색 결과가 있다는 이유만으로 원인을 확정하지 않는다(Synthesis 가 주의 문구로 반영).
    """
    alarm_code = (state.get("alarm_code") or "").lower()
    equipment_id = (state.get("equipment_id") or "").lower()

    # 실행된 Agent 결과들의 요약 텍스트를 합쳐, 추출 식별자가 직접 등장하는지 본다.
    executed_summaries = []
    used_mock_fallback = False
    for key in _AGENT_RESULT_KEYS:
        res = state.get(key) or {}
        if res.get("status") == "executed":
            summary = res.get("result_summary") or {}
            executed_summaries.append(_result_text(summary))
            if summary.get("data_source") == "mock_fallback" or summary.get("fallback_used") is True:
                used_mock_fallback = True
    combined = " ".join(executed_summaries)

    missing = []
    if alarm_code and alarm_code not in combined:
        missing.append(state.get("alarm_code"))
    if equipment_id and equipment_id not in combined:
        missing.append(state.get("equipment_id"))

    # 추출한 식별자가 하나라도 있고, 그 중 어떤 것도 결과에 직접 등장하지 않으면 out_of_scope 경고.
    # direct_found: (결과에 안 나타난 식별자 수 missing) < (추출한 식별자 총개수) → 하나라도 직접 매칭됨.
    extracted_any = bool(alarm_code or equipment_id)
    direct_found = extracted_any and (len(missing) < (bool(alarm_code) + bool(equipment_id)))
    out_of_scope_warning = extracted_any and not direct_found

    safety_notes = []
    if used_mock_fallback:
        safety_notes.append("일부 DB 결과가 mock_fallback 입니다(실제 DB 미연결 가능).")
    if out_of_scope_warning:
        safety_notes.append("질문의 식별자가 조회 결과에 직접 나타나지 않았습니다(직접 근거 부족 가능).")

    return {
        "evidence_flags": {
            "direct_evidence_found": bool(direct_found),
            "missing_identifiers": [m for m in missing if m],
            "out_of_scope_warning": bool(out_of_scope_warning),
            "used_mock_fallback": bool(used_mock_fallback),
            "safety_notes": safety_notes,
        }
    }
