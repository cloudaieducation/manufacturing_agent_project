# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 - LangGraph Agent 노드 (agents)

[이 파일의 역할]
멀티 에이전트 그래프의 각 Node(=Agent) 로직을 둡니다.
- supervisor_agent      : 규칙 기반 라우팅(LLM 미사용).
- tool_discovery_agent  : 업무 Tool 목록 조회(ToolCaller 경유 = MCP list_tools).
- db_agent              : DB Tool 호출(ToolCaller 경유 = MCP call_tool, 직접 DB 접속 금지).
- safety_agent          : 위험 SQL/데이터 변경 차단(+서버 SQL 거부 Tool 확인은 선택).
- rag_agent             : 기본 SKIPPED, allow_rag 면 search_manual 실제 호출(주로 HTTP transport).
- answer_agent          : 중간 결과를 최종 응답으로 정리.

[ToolCaller 주입 — 단위 테스트 용이]
실제 Tool 호출이 필요한 agent(tool_discovery/db/safety/rag)는 인자 tool_caller(ToolCaller)를 통해
서버 Tool 을 호출합니다. 테스트에서는 Fake ToolCaller 를 주입해 외부 서버 없이 흐름만 검증합니다.
(graph.py 가 functools.partial 로 실제 ToolCaller 를 묶어 Node 로 등록합니다.)

[경계]
- 서버 내부 함수/모듈을 직접 import 하지 않습니다(DB/RAG 직접 접속 금지). 데이터 접근은 ToolCaller 만.
- search_manual 은 stdio 환경 timeout 가능성으로 기본 호출하지 않습니다(SKIPPED). allow_rag(주로 HTTP)일 때만 실제 호출.
"""
from __future__ import annotations

import re

from day5.mcp_client04 import config


# [이 상수들의 역할 — 자유 텍스트 질문을 '경로'와 'Tool 인자'로 바꾸는 재료]
#   이 패키지에는 LLM 라우팅이 없다. 대신 아래 정규식/키워드로
#     (1) supervisor 가 어느 agent 로 보낼지(route) 결정하고,
#     (2) 사용자 질문에서 equipment_id/line_id/alarm_code/metric 을 뽑아 call_tool 의 arguments 로 만든다.
#   즉 '사용자 입력 → tool argument 변환'의 출발점이다(정규식=식별자 추출, 키워드=의도 분류).
#   가상 식별자 체계(EDU-LINE-*/EQP-*/ALM-*)만 인식하며, 정답 라벨/case_id 같은 건 쓰지 않는다.

# 식별자 추출 정규식(일반화 가능, case_id/정답 라벨 미사용). 단어 경계로 오탐을 줄인다.
_ALARM_PATTERN = re.compile(r"(?<![A-Za-z0-9])ALM-(?:[A-Z]+-)?\d+(?![A-Za-z0-9-])", re.IGNORECASE)
_EQUIP_PATTERN = re.compile(r"(?<![A-Za-z0-9])EQP-[A-Z]+-\d+(?![A-Za-z0-9])", re.IGNORECASE)
_LINE_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:EDU-)?LINE-[A-Z0-9]+", re.IGNORECASE)

# metric_name 키워드 → 서버 allowlist 컬럼.
_METRIC_KEYWORDS = [
    (("수율", "yield"), "yield_rate"),
    (("불량률", "defect"), "defect_rate"),
    (("검사 결과", "검사", "inspection"), "inspection_result"),
    (("이상", "abnormal"), "abnormal_flag"),
]

# 라우팅 키워드.
_TOOLS_KEYWORDS = ("tool 목록", "도구 목록", "tool list", "list tools", "어떤 tool", "사용 가능한 tool", "사용 가능한 도구")
_RAG_KEYWORDS = ("매뉴얼", "조치", "근거", "문서", "방향", "원인", "트러블슈팅", "설명", "절차", "검색")
_DB_KEYWORDS = ("설비", "상태", "알람", "품질", "수율", "불량률", "검사", "정비", "이력", "공정", "개요", "장비", "equipment", "line")
_QUALITY_KEYWORDS = ("품질", "수율", "불량률", "검사")
_MAINT_KEYWORDS = ("정비", "교체", "부품", "보전")


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _detect_dangerous_sql(text: str) -> str | None:
    """위험 SQL/데이터 변경 키워드가 단어 경계로 들어 있으면 그 키워드를 돌려준다(없으면 None)."""
    low = text.lower()
    for kw in config.DANGEROUS_SQL_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", low):
            return kw
    return None


def _detect_metric(text: str):
    """질문에서 metric_name(allowlist 컬럼)을 추론한다(없으면 None)."""
    low = text.lower()
    for keywords, column in _METRIC_KEYWORDS:
        if any(kw.lower() in low for kw in keywords):
            return column
    return None


def _extract_ids(text: str) -> dict:
    """질문에서 equipment_id / line_id / alarm_code 를 추출한다(없으면 None)."""
    eq = _EQUIP_PATTERN.search(text)
    ln = _LINE_PATTERN.search(text)
    al = _ALARM_PATTERN.search(text)
    return {
        "equipment_id": eq.group(0) if eq else None,
        "line_id": ln.group(0) if ln else None,
        "alarm_code": al.group(0) if al else None,
    }


def _summarize_envelope(tool_name: str, envelope: dict) -> dict:
    """서버 envelope 를 '작고 비민감한 요약 dict' 로 만든다(전체 dict/민감정보 미저장).

    payload 의 스칼라(비민감)와 출처(data_source/fallback_used/retrieval_source), 리스트는 개수만 담는다.
    """
    summary = {"tool": tool_name, "status": envelope.get("status") if isinstance(envelope, dict) else None}
    if not isinstance(envelope, dict):
        return summary
    if envelope.get("_client_error"):
        summary["error"] = f"client_error:{envelope['_client_error']}"
        return summary
    results = envelope.get("results")
    payload = {}
    if isinstance(results, list) and results and isinstance(results[0], dict):
        payload = results[0].get("result") or {}
    if not isinstance(payload, dict):
        return summary
    # 민감 key 는 제외하고, 스칼라/출처만 담는다. 리스트는 개수만.
    sensitive = ("message", "operator_note", "technician_note", "lot_id", "owner_team",
                 "location", "full_text", "chroma:document", "source_path", "file_path", "internal_url")
    for key, value in payload.items():
        if any(m in str(key).lower() for m in sensitive):
            continue
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            continue
        else:
            summary[key] = value
    return summary


# ---------------------------------------------------------------------------
# 1) supervisor_agent — 규칙 기반 라우팅
# ---------------------------------------------------------------------------
def supervisor_agent(state: dict, tool_caller=None) -> dict:
    """사용자 질문을 보고 다음 route 를 정한다(LLM 미사용).

    [라우팅 우선순위] safety > tools > rag > db > answer
        - 위험 SQL/데이터 변경 키워드 → safety
        - Tool 목록 의도 → tools
        - 매뉴얼/RAG/문서 의도 → rag
        - 설비/알람/품질/정비/공정 등 DB 의도(또는 식별자 존재) → db
        - 그 외 → answer
    [반환] {route, messages}
    """
    query = str(state.get("user_query", "") or "")
    low = query.lower()
    ids = _extract_ids(query)

    if _detect_dangerous_sql(query):
        route = "safety"
    elif any(k in low for k in _TOOLS_KEYWORDS) or ("tool" in low and ("목록" in query or "list" in low)):
        route = "tools"
    elif any(k in query for k in _RAG_KEYWORDS):
        route = "rag"
    elif any(k in low for k in _DB_KEYWORDS) or ids["equipment_id"] or ids["line_id"] or ids["alarm_code"]:
        route = "db"
    else:
        route = "answer"

    return {"route": route, "messages": [f"[supervisor] route={route}"]}


# ---------------------------------------------------------------------------
# 2) tool_discovery_agent — 업무 Tool 목록 조회
# ---------------------------------------------------------------------------
def tool_discovery_agent(state: dict, tool_caller=None) -> dict:
    """업무 Tool 목록을 ToolCaller(=실제 transport 또는 Fake)로 조회해 available_tools 에 담는다."""
    if tool_caller is None:
        return {"available_tools": [], "messages": ["[tools] ToolCaller 없음 — 목록 조회 생략"]}
    try:
        # MCP list_tools: 서버가 제공하는 업무 Tool '목록'을 받아온다(client 가 직접 구현하지 않음).
        names = tool_caller.list_tools()
    except Exception as error:
        return {"available_tools": [], "errors": [f"tool_discovery: {type(error).__name__}"],
                "messages": ["[tools] 목록 조회 실패"]}
    names = names if isinstance(names, list) else []
    return {"available_tools": names, "messages": [f"[tools] {len(names)}개 업무 Tool 확인"]}


# ---------------------------------------------------------------------------
# 3) db_agent — DB Tool 호출(ToolCaller 경유)
# ---------------------------------------------------------------------------
def _pick_db_tool(query: str, ids: dict) -> tuple[str, dict]:
    """질문/식별자로 호출할 DB Tool 과 인자를 고른다(안전한 SELECT 계열 업무 Tool 만).

    위험 SQL 을 만들지 않는다. 미리 정의된 업무 Tool 이름(서버 contract 와 일치, mcp_client03 검증)만 사용.
    """
    low = query.lower()
    eq, ln = ids.get("equipment_id"), ids.get("line_id")
    if "알람" in query and eq:
        args = {"equipment_id": eq}
        if ids.get("alarm_code"):
            args["alarm_code"] = ids["alarm_code"]
        return "get_recent_alarm_events", args
    if any(k in low for k in _QUALITY_KEYWORDS):
        args = {}
        metric = _detect_metric(query)
        if metric:
            args["metric_name"] = metric
        if eq:
            args["equipment_id"] = eq
        if ln:
            args["line_id"] = ln
        return "get_quality_metrics", args
    if any(k in query for k in _MAINT_KEYWORDS) and eq:
        return "get_maintenance_history", {"equipment_id": eq}
    # 기본: 설비 개요(equipment_id 우선, 없으면 line_id).
    args = {}
    if eq:
        args["equipment_id"] = eq
    elif ln:
        args["line_id"] = ln
    return "get_equipment_overview", args


def db_agent(state: dict, tool_caller=None) -> dict:
    """DB 의도 질문을 받아 DB Tool 하나를 ToolCaller 로 호출하고 결과 요약을 담는다.

    [경계] 직접 DB 접속 금지. 위험 SQL 생성 금지(미리 정의된 SELECT 계열 업무 Tool 만 호출).
    [반환] {tool_results, messages, (선택)errors}
    """
    query = str(state.get("user_query", "") or "")
    ids = _extract_ids(query)
    # 사용자 입력 → tool argument 변환: 질문/식별자로 호출할 Tool 이름과 인자(dict)를 고른다.
    tool_name, args = _pick_db_tool(query, ids)

    if tool_caller is None:
        return {"messages": [f"[db] ToolCaller 없음 — {tool_name} 호출 생략"]}
    try:
        # MCP call_tool: 고른 Tool 을 서버에 '실행 요청'한다(결과 envelope 수신). 직접 DB 접속 아님.
        envelope = tool_caller.call_tool(tool_name, args)
    except Exception as error:
        return {"errors": [f"db_agent: {type(error).__name__}"],
                "messages": [f"[db] {tool_name} 호출 실패"]}
    summary = _summarize_envelope(tool_name, envelope)
    results = dict(state.get("tool_results") or {})
    results[tool_name] = summary
    return {"tool_results": results,
            "messages": [f"[db] {tool_name} → status={summary.get('status')} "
                         f"data_source={summary.get('data_source')}"]}


# ---------------------------------------------------------------------------
# 4) safety_agent — 위험 SQL/데이터 변경 차단
# ---------------------------------------------------------------------------
def safety_agent(state: dict, tool_caller=None) -> dict:
    """위험 SQL/데이터 변경 요청을 차단(표시)한다. (Guardrail 전체가 아니라 1차 차단)

    [동작]
        - 질문에서 위험 키워드(DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE 등) 감지 시 BLOCKED.
        - 차단 사유와 대상(query preview)을 state 에 기록한다. client 가 SQL 을 실행하지 않는다.
        - (선택) ToolCaller 가 있으면 서버의 SQL 거부 Tool(execute_sql)을 호출해 '서버도 거부함'을 확인한다.
          서버 execute_sql 은 금지 Tool 이라 rejected 되며, 이는 mcp_client03 에서 검증되었다.
    [반환] {safety_status, sql, tool_results?, messages}
    """
    query = str(state.get("user_query", "") or "")
    keyword = _detect_dangerous_sql(query)

    if not keyword:
        return {"safety_status": "OK", "messages": ["[safety] 위험 SQL 키워드 없음"]}

    # 위험 요청: client 는 절대 실행하지 않고 차단 표시만 한다.
    out = {
        "safety_status": "BLOCKED",
        "sql": query[:120],  # 원문 전체가 아니라 미리보기만(민감/장문 방지)
        "messages": [f"[safety] 위험 키워드 '{keyword}' 감지 → 차단(BLOCKED). client 는 실행하지 않음"],
    }
    # (선택) 서버도 SQL 실행 Tool 을 거부하는지 transport 로 확인(서버 미수정, execute_sql 은 금지 Tool).
    if tool_caller is not None:
        try:
            envelope = tool_caller.call_tool("execute_sql", {"query": query})
            out_results = dict(state.get("tool_results") or {})
            out_results["execute_sql"] = {"tool": "execute_sql",
                                          "status": envelope.get("status") if isinstance(envelope, dict) else None}
            out["tool_results"] = out_results
            out["messages"] = out["messages"] + [
                f"[safety] 서버 execute_sql 응답 status={out_results['execute_sql']['status']}(거부 확인용)"]
        except Exception as error:
            out["errors"] = [f"safety_agent: {type(error).__name__}"]
    return out


# ---------------------------------------------------------------------------
# 5) rag_agent — 기본 SKIPPED, allow_rag 면 search_manual 실제 호출(주로 HTTP)
# ---------------------------------------------------------------------------
def rag_agent(state: dict, tool_caller=None) -> dict:
    """RAG 의도 질문을 처리한다. 기본은 SKIPPED, allow_rag 면 search_manual 을 실제 호출한다.

    [기본(allow_rag=False 또는 ToolCaller 없음) → SKIPPED]
        mcp_client03 검증 결과, search_manual(chroma+Ollama)을 stdio 서버 서브프로세스로 호출하면
        timeout/hang 가능성이 있다. 따라서 기본은 호출하지 않고 SKIPPED 로 명시한다(timeout 을
        성공처럼 표시하지 않음).

    [활성(allow_rag=True + ToolCaller) → search_manual 실제 호출]
        long-lived streamable-http 서버에 접속하는 HttpToolCaller 를 주입받았을 때 사용한다.
        search_manual 은 직접 등록 Tool 이 아니라 call_mcp_tool 경유로 호출한다(서버 내부 함수 직접
        호출 아님 — transport 경계 유지). 결과는 비민감 요약(documents 는 개수만)으로만 담는다.

    [rag_status 의미]
        SKIPPED : 비활성(기본). / OK : 문서 검색 성공. / EMPTY : 호출됐으나 문서 0건.
        ERROR   : timeout/연결 실패 등(정직 표기 — 성공으로 위장하지 않음).
    [반환] {rag_status, (선택)tool_results, (선택)errors, messages}
    """
    allow_rag = bool(state.get("allow_rag"))
    query = str(state.get("user_query", "") or "")

    # 기본 경로: 비활성이거나 ToolCaller 가 없으면 호출하지 않고 SKIPPED.
    if not allow_rag or tool_caller is None:
        return {
            "rag_status": "SKIPPED",
            "messages": ["[rag] search_manual 은 stdio transport 환경에서 timeout 가능성이 있어 "
                         "기본 호출하지 않음(SKIPPED). 실제 호출은 --allow-rag + HTTP transport."],
        }

    # 활성 경로: search_manual 을 call_mcp_tool 경유로 실제 호출한다(required=query, optional=alarm_code).
    ids = _extract_ids(query)
    args = {"query": query}
    if ids.get("alarm_code"):
        args["alarm_code"] = ids["alarm_code"]
    try:
        envelope = tool_caller.call_tool(config.MCP_SEARCH_TOOL, args)
    except Exception as error:
        return {"rag_status": "ERROR",
                "errors": [f"rag_agent: {type(error).__name__}"],
                "messages": ["[rag] search_manual 호출 실패(ERROR). HTTP 서버 기동/연결 확인 필요."]}

    # 결과는 비민감 요약만(documents 는 개수, retrieval_source/fallback_used 등 스칼라).
    summary = _summarize_envelope(config.MCP_SEARCH_TOOL, envelope)
    results = dict(state.get("tool_results") or {})
    results[config.MCP_SEARCH_TOOL] = summary

    status = summary.get("status")
    if summary.get("error") or status in ("timeout", "error"):
        # timeout/연결 오류 → 성공으로 위장하지 않고 ERROR 로 정직 표기.
        rag_status = "ERROR"
        msg = "[rag] search_manual 응답 실패/timeout(ERROR). HTTP 서버/Ollama 상태를 확인하세요."
    elif (summary.get("documents_count") or 0) == 0:
        rag_status = "EMPTY"
        msg = "[rag] search_manual 호출됨 — 관련 문서 0건(EMPTY)."
    else:
        rag_status = "OK"
        msg = (f"[rag] search_manual 호출됨 — 문서 {summary.get('documents_count')}건(OK), "
               f"retrieval_source={summary.get('retrieval_source')}.")

    return {"rag_status": rag_status, "tool_results": results, "messages": [msg]}


# ---------------------------------------------------------------------------
# 6) answer_agent — 최종 응답 정리
# ---------------------------------------------------------------------------
def answer_agent(state: dict, tool_caller=None) -> dict:
    """중간 결과(route/tool_results/safety/rag)를 사람이 읽기 쉬운 최종 응답으로 정리한다.

    [원칙] 전체 dict/민감정보를 출력하지 않는다. 요약 dict 의 비민감 스칼라/개수만 사용한다.
    [반환] {final_answer, messages}
    """
    route = state.get("route")
    lines = ["=" * 56, "[mcp_client04 결과 요약] (LangGraph 멀티 에이전트 / standalone stdio)", "=" * 56]
    lines.append(f"- 질문: {str(state.get('user_query',''))[:150]}")
    lines.append(f"- 선택된 route: {route}")

    if state.get("available_tools"):
        lines.append(f"- 사용 가능한 업무 Tool({len(state['available_tools'])}): "
                     f"{', '.join(map(str, state['available_tools']))}")

    if state.get("safety_status"):
        lines.append(f"- 안전성 판정: {state.get('safety_status')}")
        if state.get("safety_status") == "BLOCKED":
            lines.append("  · 위험 SQL/데이터 변경 요청은 client 가 실행하지 않습니다(차단).")

    if state.get("rag_status"):
        lines.append(f"- RAG 처리: {state.get('rag_status')}")
        if state.get("rag_status") == "SKIPPED":
            lines.append("  · search_manual 은 stdio 환경 timeout 가능성으로 이번 단계 미실행(2차 확장).")

    results = state.get("tool_results") or {}
    if results:
        lines.append("- Tool 결과(요약):")
        for tool, summary in results.items():
            parts = [f"{k}={v}" for k, v in summary.items() if k not in ("tool",)]
            lines.append(f"  · {tool}: " + ", ".join(parts))

    if state.get("errors"):
        lines.append(f"- 오류({len(state['errors'])}): {', '.join(map(str, state['errors']))}")

    lines.append("- 주의: 조회/검색 결과를 곧바로 원인으로 단정하지 않으며, 장비 제어 지시는 제공하지 않습니다(교육용).")
    return {"final_answer": "\n".join(lines), "messages": ["[answer] 최종 응답 생성"]}
