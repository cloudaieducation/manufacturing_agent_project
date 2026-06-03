# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 - 실행 흐름 (runner)

[이 파일의 역할]
LangGraph 그래프를 실제 ToolCaller 와 연결해 실행하는 '진입 흐름'을 둡니다. CLI(__main__.py)와
Streamlit UI(mcp_client05/streamlit_app.py)가 모두 이 계층의 함수만 호출합니다(핵심 로직 중복 구현 없음).
- run_query : 질문 1건을 그래프에 흘려보내 최종 State 를 받는다.
- run_list_tools : 업무 Tool 목록을 조회한다(MCP list_tools).
- run_demo : 기본 데모 시나리오(연결→목록→DB→위험SQL차단→RAG SKIPPED)를 순차 실행한다.

[transport / ToolCaller 선택]
- 기본은 StdioToolCaller(서버를 서브프로세스로 spawn). transport="http" 또는 allow_rag=True 면
  HttpToolCaller(외부 long-lived 서버 URL 접속)를 쓴다(_build_caller 가 단일 생성 지점).

[경계]
실제 데이터 접근은 ToolCaller(transport)만 사용한다. 서버 내부 함수 직접 import 금지.
search_manual 은 기본 호출하지 않는다(rag_agent SKIPPED). allow_rag(주로 HTTP)일 때만 실제 호출.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# [import 경로 보강] 이 파일 <root>/src/day5/mcp_client04/runner.py → parents[3] = <root>
_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from day5.mcp_client04 import agents, config
from day5.mcp_client04.graph import build_graph
from day5.mcp_client04.state import build_initial_state
from day5.mcp_client04.mcp_tools import StdioToolCaller, HttpToolCaller


def _resolve_transport(transport, allow_rag: bool) -> str:
    """사용할 transport('stdio'|'http')를 결정한다.

    [규칙]
        - transport 가 명시되면 그대로 사용한다.
        - 미지정(None)이고 allow_rag 면 'http' 로 전환한다(stdio RAG 는 timeout 가능성).
        - 그 외에는 config.DEFAULT_TRANSPORT('stdio').
    """
    if transport in ("stdio", "http"):
        return transport
    return "http" if allow_rag else config.DEFAULT_TRANSPORT


def _build_caller(timeout: int, allow_rag: bool = False,
                  transport: str | None = None, http_url: str | None = None):
    """transport/allow_rag 에 맞는 ToolCaller 를 만든다(단일 생성 지점).

    [반환]
        - http : HttpToolCaller(외부 long-lived 서버 URL 접속). RAG 는 더 넉넉한 timeout 사용.
        - stdio: StdioToolCaller(서버 서브프로세스 spawn — 기존 동작).
    [경계] client 는 http 서버를 spawn 하지 않는다. 사용자가 미리 띄운 URL 에 접속만 한다.
    """
    mode = _resolve_transport(transport, allow_rag)
    if mode == "http":
        url = http_url or config.MCP_HTTP_URL
        # RAG 를 쓰는 http 경로는 RAG_TIMEOUT 을 하한으로(짧은 timeout 으로 RAG 가 끊기지 않게).
        http_timeout = max(timeout, config.RAG_TIMEOUT) if allow_rag else timeout
        return HttpToolCaller(url=url, timeout=http_timeout)
    return StdioToolCaller(timeout=timeout)


def run_query(user_query: str, timeout: int = config.DEFAULT_TIMEOUT, tool_caller=None,
              allow_rag: bool | None = None, transport: str | None = None,
              http_url: str | None = None) -> dict:
    """질문 1건을 멀티 에이전트 그래프로 실행하고 최종 State 를 돌려준다.

    [입력]
        user_query : 사용자 질문.
        timeout    : Tool 호출 timeout(초).
        tool_caller: 주입할 ToolCaller(미지정 시 transport/allow_rag 로 생성). 테스트는 Fake 주입 가능.
        allow_rag  : RAG(search_manual) 실제 호출 허용. None 이면 config.ALLOW_RAG_DEFAULT(기본 True).
                     True 면 transport 가 http 로 전환되어 search_manual 을 실제 호출한다(서버 선기동 필요).
        transport  : 'stdio'|'http'|None. None 이고 allow_rag 면 http 로 전환.
        http_url   : http transport 일 때 접속 URL(미지정 시 config.MCP_HTTP_URL).
    [반환] 최종 State dict(route/tool_results/safety_status/rag_status/final_answer 등).
    """
    # allow_rag 미지정(None) → 프로젝트 기본값(config.ALLOW_RAG_DEFAULT)을 따른다.
    if allow_rag is None:
        allow_rag = config.ALLOW_RAG_DEFAULT
    caller = tool_caller if tool_caller is not None else _build_caller(
        timeout, allow_rag=allow_rag, transport=transport, http_url=http_url)
    graph = build_graph(caller)
    return graph.invoke(build_initial_state(user_query, allow_rag=allow_rag))


def run_list_tools(timeout: int = config.DEFAULT_TIMEOUT, tool_caller=None,
                   transport: str | None = None, http_url: str | None = None) -> list:
    """업무 Tool 목록을 조회해 돌려준다(이름 리스트). 기본 stdio, transport='http' 면 HTTP 서버 조회."""
    caller = tool_caller if tool_caller is not None else _build_caller(
        timeout, transport=transport, http_url=http_url)
    return caller.list_tools()


# 기본 데모에서 쓰는 대표 질문(가상 시나리오). 각 질문은 supervisor 라우팅을 보여 주도록 구성.
_DEMO_DB_QUERY = "EQP-EV-03 설비 개요를 보여줘"
_DEMO_SAFETY_QUERY = "users 테이블을 DROP 해줘"
_DEMO_RAG_QUERY = "ALM-TEMP-402 조치 방향 매뉴얼 근거를 알려줘"


def run_demo(timeout: int = config.DEFAULT_TIMEOUT, tool_caller=None) -> dict:
    """기본 데모 시나리오를 순차 실행하고 결과 묶음을 돌려준다(콘솔 출력은 __main__ 담당).

    [시나리오]
        1) MCP stdio transport 연결 확인 + 업무 Tool 목록 조회
        2) DB Tool 정상 호출(설비 개요) — db route
        3) 위험 SQL 요청 차단(DROP) — safety route(BLOCKED)
        4) RAG 질문 처리 — rag route(SKIPPED, search_manual 미호출)
    [반환] {"tools": [...], "db": state, "safety": state, "rag": state}
    [주의] demo 는 '오프라인 stdio 교육 시나리오'다. 기본 RAG(config.ALLOW_RAG_DEFAULT=True)와
           무관하게 항상 stdio + allow_rag=False 로 고정한다. (그래야 stdio 에서 search_manual 을
           실제 호출해 timeout 되지 않고, 4단계가 의도대로 SKIPPED 로 표시된다.)
    """
    caller = tool_caller if tool_caller is not None else StdioToolCaller(timeout=timeout)
    out = {}
    # 1) 연결 확인 겸 업무 Tool 목록(stdio).
    out["tools"] = caller.list_tools()
    # 2) DB Tool 정상 호출(설비 개요). allow_rag=False 고정(stdio 오프라인).
    out["db"] = run_query(_DEMO_DB_QUERY, timeout=timeout, tool_caller=caller, allow_rag=False)
    # 3) 위험 SQL 차단.
    out["safety"] = run_query(_DEMO_SAFETY_QUERY, timeout=timeout, tool_caller=caller, allow_rag=False)
    # 4) RAG 질문 → SKIPPED(search_manual 미호출, stdio timeout 회피).
    out["rag"] = run_query(_DEMO_RAG_QUERY, timeout=timeout, tool_caller=caller, allow_rag=False)
    return out


# ===========================================================================
# DB Tool 병렬 실행 데모 (병렬 비교 데모 실행 로직 — UI는 mcp_client05에서 이 함수를 호출)
# ===========================================================================
# [이 블록의 목적 — 전체 Agent 병렬화가 아니라 'DB 조회 Tool 만' 병렬 호출]
#   기본 흐름(supervisor → 선택된 agent → answer)은 '순차형'이다(graph.py 무수정, 그대로 유지).
#   여기서는 같은 설비/라인 ID 로 '안전한 DB 조회 Tool 여러 개'를 동시에 호출해, 순차 대비 병렬의
#   차이를 수업에서 비교하기 위한 별도 데모만 추가한다.
#   - 전체 LangGraph 병렬화 아님 : State 충돌/라우팅 복잡도를 키우지 않는다.
#   - DB Agent 다중 생성 아님    : Agent 를 늘리는 게 아니라, 안전한 DB '조회 Tool' 을 병렬 호출한다.
#   - DB 직접 접속 아님          : 모든 호출은 MCP transport(call_mcp_tool) 경유다.

# 병렬 데모 대상 — '안전한 조회(SELECT 계열)' DB Tool 화이트리스트(서버 contract 와 일치, 추측 금지).
#   execute_sql/데이터 변경/ RAG(search_manual) 계열은 의도적으로 제외한다(아래 2차 방어도 참고).
SAFE_PARALLEL_DB_TOOLS = (
    "get_equipment_overview",   # 설비 개요(required: equipment_id)
    "get_recent_alarm_events",  # 최근 알람 이력(required: equipment_id / optional: alarm_code, limit)
    "get_quality_metrics",      # 품질 지표(any_of: metric_name/equipment_id/line_id / optional: date_range, limit)
    "get_maintenance_history",  # 정비 이력(required: equipment_id / optional: date_range, part_replaced)
)

# 병렬 데모에서 절대 호출하지 않을 위험/비대상 이름·패턴(방어적 2차 차단).
#   화이트리스트만 순회하므로 정상 환경에선 매칭되지 않지만, 서버가 예상 밖 Tool 을 노출하거나
#   화이트리스트에 위험 Tool 이 잘못 섞여도 execute_sql / 데이터 변경 SQL 계열이 병렬 호출에 끼지 않게 막는다.
_FORBIDDEN_PARALLEL_PATTERNS = (
    "execute_sql", "run_sql", "sql", "drop", "delete", "update",
    "insert", "alter", "truncate", "grant", "revoke", "merge",
)
# RAG 계열은 병렬 DB 데모 대상이 아니다(stdio timeout 가능성 + '조회 Tool 병렬'이라는 데모 취지와 분리).
_EXCLUDED_PARALLEL_TOOLS = ("search_manual",)

# 병렬 데모가 schema 기준으로 채울 수 있는 입력 인자(이 외 인자는 임의로 만들어 넣지 않는다).
#   날짜 범위(date_range)/부품명(part_replaced)/metric_name 등은 안전한 기본값을 단정하기 어려워
#   이번 데모에서는 채우지 않는다(필수가 아니므로 미전달, 필수면 skipped 처리).
_FILLABLE_PARALLEL_ARGS = ("equipment_id", "line_id", "limit")


def _is_forbidden_parallel_tool(tool_name) -> bool:
    """병렬 데모 대상에서 무조건 제외할 위험/비대상 Tool 인지 판정한다(방어적 2차 차단)."""
    low = str(tool_name or "").lower()
    if low in _EXCLUDED_PARALLEL_TOOLS:
        return True
    return any(pat in low for pat in _FORBIDDEN_PARALLEL_PATTERNS)


def get_safe_parallel_db_tool_specs(tool_schemas, equipment_id=None, line_id=None, limit=5) -> dict:
    """병렬 호출할 '안전한 DB 조회 Tool' 과 Tool별 인자를 schema 기준으로 구성한다.

    [왜 Tool 마다 인자를 다르게 구성하나]
        Tool 마다 받는 입력이 다르다(설비 개요는 equipment_id 만, 품질 지표는 line_id 도 받음 등).
        모든 Tool 에 equipment_id/line_id 를 무조건 넣으면 schema 에 없는 인자가 들어가
        contract mismatch 가 난다. 따라서 각 Tool 의 inputSchema 를 보고 '그 Tool 이 받는 인자만' 채운다.

    [입력]
        tool_schemas: list_mcp_tools 결과(각 {"name","inputSchema"} dict). 실제 서버 schema 기준.
        equipment_id / line_id : 조회 대상 식별자(가상). 빈 문자열은 미지정(None)으로 본다.
        limit       : 목록형 Tool 의 최대 건수(schema 에 limit 가 있는 Tool 에만 전달).
    [동작]
        1) SAFE_PARALLEL_DB_TOOLS 화이트리스트에 있는 Tool 만 후보로 본다(execute_sql/RAG 등은 비대상).
        2) _is_forbidden_parallel_tool 로 위험 이름 패턴을 한 번 더 막는다(방어).
        3) inputSchema.properties 에 '존재하는' 인자만, 값이 있을 때만 채운다(없는 인자 임의 추가 금지).
        4) inputSchema.required 를 모두 채울 수 없으면 호출하지 않고 skipped_tools 에 사유를 기록한다.
    [반환] {"specs": [{"tool_name","arguments"}...], "skipped_tools": [{"tool_name","reason"}...]}
    """
    # 빈 문자열/공백은 미지정(None)으로 정규화한다 → 필수 인자면 4)에서 skipped 로 유도된다.
    def _norm(value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    available = {
        "equipment_id": _norm(equipment_id),
        "line_id": _norm(line_id),
        "limit": limit,  # 정수 스칼라. schema 에 limit 가 있을 때만 전달한다.
    }

    specs = []
    skipped = []
    for schema in (tool_schemas or []):
        if not isinstance(schema, dict):
            continue
        name = schema.get("name")
        if name not in SAFE_PARALLEL_DB_TOOLS:
            # 병렬 DB 데모 대상이 아닌 Tool(RAG/SQL/상태조회 등)은 조용히 제외한다(스킵 사유 기록 대상 아님).
            continue
        if _is_forbidden_parallel_tool(name):
            # 정상 환경에선 도달하지 않지만, 위험 Tool 이 섞여도 절대 병렬 호출 대상에 넣지 않는다.
            skipped.append({"tool_name": name, "reason": "위험/비대상 Tool 패턴으로 병렬 호출에서 제외"})
            continue
        input_schema = schema.get("inputSchema") or {}
        props = input_schema.get("properties") or {}
        required = input_schema.get("required") or []
        # 3) schema 의 properties 에 있는 인자만, 값이 있을 때만 채운다(추측 인자 금지).
        args = {}
        for arg_name in _FILLABLE_PARALLEL_ARGS:
            if arg_name in props and available.get(arg_name) is not None:
                args[arg_name] = available[arg_name]
        # 4) 필수 인자를 모두 구성할 수 있는지 확인 — 못 채우면 호출하지 않고 skipped 에 사유 기록.
        missing = [req for req in required if req not in args]
        if missing:
            skipped.append({
                "tool_name": name,
                "reason": ("필수 입력 schema를 구성할 수 없어 병렬 데모 대상에서 제외"
                           f"(누락: {', '.join(missing)})"),
            })
            continue
        specs.append({"tool_name": name, "arguments": args})

    return {"specs": specs, "skipped_tools": skipped}


def _call_one_db_tool(spec, tool_caller_factory):
    """병렬 작업 1건 — '워커 스레드 안에서' 독립 caller 를 만들어 DB Tool 하나를 호출한다.

    [왜 caller 를 작업마다 새로 만드나 — 공유 금지]
        ToolCaller / fastmcp.Client 가 thread-safe 인지 보장되지 않는다. 하나의 caller 를 여러
        스레드가 공유하면 내부 MCP 세션/asyncio 상태가 경합할 수 있다. 그래서 각 스레드가 자기
        caller 를 새로 만들어 쓰고(호출 종료 시 transport 가 세션을 닫음) 절대 공유하지 않는다.
    [반환] (tool_name, envelope). 예외는 호출자가 잡아 'Tool별 오류'로 기록한다(전체 실패로 키우지 않음).
    """
    caller = tool_caller_factory()
    envelope = caller.call_tool(spec["tool_name"], spec["arguments"])
    return spec["tool_name"], envelope


def run_parallel_db_tools_demo(equipment_id: str = "EQP-EV-03", line_id: str = "EDU-LINE-01",
                               limit: int = 5, timeout: int = config.DEFAULT_TIMEOUT,
                               transport: str = "http", http_url: str | None = None,
                               max_workers: int = 4, tool_caller_factory=None) -> dict:
    """안전한 DB 조회 Tool 여러 개를 '병렬'로 호출하는 교육용 데모(전체 Agent 병렬화 아님).

    [수업 비교 포인트]
        기본 흐름(supervisor → 단일 agent → answer)은 순차형이다. 이 함수는 같은 설비/라인 ID 로
        여러 DB 조회 Tool 을 동시에 호출해 순차 대비 병렬 차이를 보여 준다. 결과는 Tool 별로 분리해
        담고, 하나의 최종 답변으로 억지 병합하지 않는다(비교가 목적).

    [HTTP transport 권장]
        stdio 는 Tool 호출마다 서버 subprocess 를 새로 spawn 하므로 병렬에는 무겁다. long-lived
        HTTP 서버 하나에 여러 요청을 보내는 편이 병렬 Tool 호출 데모에 적합하다(기본 transport='http').

    [병렬 처리 — ThreadPoolExecutor]
        call_tool 은 동기 함수(내부에서 asyncio.run)다. 따라서 스레드 풀로 동시에 실행한다.
        max_workers 는 호출 대상 수 이하로 제한한다(불필요한 스레드 방지). 한 Tool 이 실패해도
        나머지 결과는 유지하고, 실패는 type(error).__name__ 중심으로 Tool별 오류에 기록한다.

    [thread-safety] caller 를 스레드 간 공유하지 않는다 — 각 작업이 tool_caller_factory() 로 자기
        caller 를 새로 만든다(_call_one_db_tool). UI(mcp_client05)는 결과 dict 만 저장한다(client 객체 저장 금지).

    [입력]
        equipment_id / line_id / limit: 조회 입력. Tool 별 schema 에 맞는 인자만 전달된다(추측 금지).
        transport : 'http'(권장) | 'stdio'.
        http_url  : http transport 접속 URL(미지정 시 config.MCP_HTTP_URL).
        max_workers       : 동시 실행 상한(기본 4 이하 권장).
        tool_caller_factory: () -> ToolCaller 팩토리(테스트는 Fake 팩토리 주입). None 이면 transport 기준 생성.
    [반환] status/mode/transport/tool_count/called_count/success_count/error_count/skipped_count/
           elapsed_sec/inputs/called_tools/skipped_tools/results/errors 를 담은 dict.
    """
    # 1) caller 팩토리 결정 — '호출마다 새 caller'를 만들도록 강제(스레드 간 공유 금지).
    if tool_caller_factory is None:
        def tool_caller_factory():
            # 이 데모는 RAG 비대상이므로 allow_rag=False. transport 는 기본 http(권장).
            return _build_caller(timeout, allow_rag=False, transport=transport, http_url=http_url)

    inputs = {"equipment_id": equipment_id, "line_id": line_id, "limit": limit}
    base = {"mode": "parallel_db_tools", "transport": transport, "inputs": inputs}

    # 2) Tool schema 조회(병렬 이전, 1회). 서버가 노출하는 실제 schema 기준으로 인자를 구성한다.
    #    schema 가 비면 서버 미기동/연결 실패로 보고 병렬 호출을 시도하지 않는다(성공처럼 숨기지 않음).
    list_error = None
    try:
        tool_schemas = tool_caller_factory().list_tool_schemas()
    except Exception as error:  # noqa: BLE001 - 연결 단계 오류를 안전 dict 로 변환(원문 trace 미노출)
        tool_schemas = []
        list_error = type(error).__name__

    if not tool_schemas:
        # HTTP 서버 미기동/연결 실패 → 화면에서 서버 실행 명령을 안내하도록 connection_error 로 표기.
        return {**base, "status": "connection_error",
                "tool_count": 0, "called_count": 0, "success_count": 0,
                "error_count": 0, "skipped_count": 0, "elapsed_sec": 0.0,
                "called_tools": [], "skipped_tools": [], "results": {},
                "errors": [{"tool_name": None,
                            "error_type": list_error or "ConnectionError",
                            "message": "MCP Tool 목록(schema) 조회 실패 — HTTP 서버 기동 여부를 확인하세요."}]}

    # 3) 안전한 DB 조회 Tool 과 Tool별 인자를 schema 기준으로 구성한다.
    spec_result = get_safe_parallel_db_tool_specs(
        tool_schemas, equipment_id=equipment_id, line_id=line_id, limit=limit)
    specs = spec_result["specs"]
    skipped = spec_result["skipped_tools"]

    # 4) 병렬 호출 — ThreadPoolExecutor 로 동시에 실행(동기 call_tool 을 스레드로 병렬화).
    results = {}
    errors = []
    success_count = 0
    error_count = 0
    elapsed = 0.0
    if specs:
        workers = max(1, min(max_workers, len(specs)))
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pdb") as executor:
            future_to_name = {
                executor.submit(_call_one_db_tool, spec, tool_caller_factory): spec["tool_name"]
                for spec in specs
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    tool_name, envelope = future.result()
                except Exception as error:  # noqa: BLE001 - 한 Tool 실패가 전체를 깨지 않게 격리
                    error_count += 1
                    errors.append({"tool_name": name, "error_type": type(error).__name__})
                    results[name] = {"tool": name, "status": "error", "error": type(error).__name__}
                    continue
                # 결과는 비민감 요약만(agents._summarize_envelope 가 민감 key 마스킹/리스트는 개수만).
                summary = agents._summarize_envelope(tool_name, envelope)
                results[tool_name] = summary
                status = summary.get("status")
                if summary.get("error") or status in ("timeout", "error", "rejected", "needs_review"):
                    error_count += 1
                    errors.append({"tool_name": tool_name,
                                   "error_type": str(summary.get("error") or status or "unknown")})
                else:
                    success_count += 1
        elapsed = time.perf_counter() - start

    return {
        **base,
        "status": "executed",
        "tool_count": len(specs) + len(skipped),
        "called_count": len(specs),
        "success_count": success_count,
        "error_count": error_count,
        "skipped_count": len(skipped),
        "elapsed_sec": round(elapsed, 3),
        "called_tools": [spec["tool_name"] for spec in specs],
        "skipped_tools": skipped,
        "results": results,
        "errors": errors,
    }
