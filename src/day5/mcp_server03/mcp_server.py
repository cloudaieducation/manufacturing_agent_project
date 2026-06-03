# -*- coding: utf-8 -*-
"""
Day5 mcp_server03 - MCP Server 진입점 (순수 Python 함수형 골격)

[이 모듈의 역할]
MCP Tool 등록/호출의 진입점입니다. MCP SDK 가 없어도 import 가 깨지지 않으며,
1차에서는 순수 Python 함수 호출 형태로 MCP Server 구조를 보여줍니다.

[제공하는 진입 함수]
- list_mcp_tools()                              : 노출 Tool schema 목록(contracts 기준)
- call_mcp_tool(tool_name, arguments)           : 개별 Tool 직접 호출(검증 후 실행)
- call_select_tools_for_manufacturing_query(..) : LLM 으로 Tool Plan 생성(실행 안 함)
- call_validate_tool_plan(tool_plan, ..)        : normalizer → validation 결과 반환
- call_execute_selected_tools(tool_plan, ..)    : 주어진 Tool Plan 실행
- call_execute_query(user_query, ..)            : LLM 생성 → 검증 → PASS 면 실행

[책임 분리]
- Selection(생성)        : tool_selector
- Validation(정규화/검증) : normalizer + validation (tool_executor 안에서 호출)
- Execution(실행)        : tool_executor
- Schema 노출            : mcp_schemas (contracts 기준)
- 호출 이력 로깅          : mcp_logging (JSONL, sanitize 후 저장)
이 파일은 위 계층을 '엮는' 얇은 진입점입니다. runner.py 를 import 하지 않습니다.

[FastMCP 서버]
- create_fastmcp_server() 로 FastMCP server 를 만들고 Tool wrapper 를 등록한다.
- FastMCP wrapper(_fastmcp_*)는 위 함수형 API 를 호출하는 '얇은 계층'이며 기능 로직을
  새로 만들지 않는다. 내부 디버깅 함수는 Tool 로 노출하지 않는다.

[로깅 정책]
- 핵심 이벤트는 '진입 함수'에서 mcp_logging.log_event 로 1회만 남긴다.
  → FastMCP 경유든 함수형 직접 호출이든 중복 기록되지 않는다.
- 로그에는 sanitize 된 안전 필드만 남는다(raw user_query/result/prompt/response 미기록).
- 로그 저장 실패(log_event=False)는 Tool 실행 결과에 영향을 주지 않는다.

[보안]
- FORBIDDEN_SQL_TOOLS 는 list_mcp_tools() 에 노출하지 않습니다(mcp_schemas 가 제외).
- API Key / token / password / endpoint / 환경변수 값은 반환/로깅하지 않습니다.
"""
# [import 구성 = MCP 서버의 계층 지도]
# 아래 import 들은 이 진입점이 '엮어 주는' 각 계층을 그대로 보여 준다.
# MCP 서버 흐름을 이해하려면 각 모듈이 흐름의 어느 단계를 맡는지 짚어 두는 것이 좋다.
#   - contracts     : 허용/금지 Tool 목록(기준표). 노출/차단 판단의 single source.
#   - mcp_schemas   : contracts → MCP Client 가 보는 Tool input schema 로 '변환'하는 계층.
#   - tool_selector : 사용자 질문 → LLM Tool Plan '생성'(Selection) 계층.
#   - tool_executor : 정규화 → 검증 → PASS 면 '실행'(Execution) 계층(DB 조회는 그 아래).
#   - mcp_logging   : 호출 이력을 sanitize 후 JSONL 로 남기는 로깅 계층.
from day5.mcp_server03.contracts import ALLOWED_TOOLS, FORBIDDEN_SQL_TOOLS
from day5.mcp_server03 import mcp_schemas
from day5.mcp_server03 import tool_selector
from day5.mcp_server03 import tool_executor
from day5.mcp_server03 import mcp_logging


# ---------------------------------------------------------------------------
# FastMCP (MCP Server 구현에 사용 — 교육 환경에 설치돼 있다고 가정)
# ---------------------------------------------------------------------------
# [import 경로] 현재 venv 에서 'from fastmcp import FastMCP' 가 동작한다.
#   (대안: 'from mcp.server.fastmcp import FastMCP' — 사용하지 않는다.)
from fastmcp import FastMCP


# ---------------------------------------------------------------------------
# 로그 이벤트 매핑/헬퍼 (진입 함수 공통 로깅에 사용)
# ---------------------------------------------------------------------------
# [용도] execute_tool_plan 결과의 status 를 로그 event_type 으로 변환한다.
#        실행/거부/검토필요/오류를 구분해 기록하기 위함이다.
_STATUS_EVENT = {
    "executed": "tool_executed",
    "dry_run": "tool_executed",
    "rejected": "tool_rejected",
    "needs_review": "tool_needs_review",
    "error": "tool_error",
}


def _event_for_status(status):
    """실행 결과 status 문자열을 로그 event_type 으로 변환한다(기본 tool_executed)."""
    return _STATUS_EVENT.get(status, "tool_executed")


def _issue_types(issues):
    """validation issues(list[dict]) 에서 'type' 값만 추려 list[str] 로 돌려준다.

    [왜 type 만 남기는가]
        issue 에는 message 등 부가 텍스트가 있을 수 있다. 로그에는 분류용 type 만
        남겨, 원문 메시지에 섞일 수 있는 민감정보 노출을 피한다.
    """
    if not isinstance(issues, list):
        return []
    types = []
    for issue in issues:
        if isinstance(issue, dict) and issue.get("type"):
            types.append(issue.get("type"))
    return types


def _log_execution_result(tool_name, result):
    """실행 결과 dict 를 보고 상태별 로그 이벤트를 1건 남긴다(진입 함수 공통).

    [기록 필드] tool_name / status / validation_status / executed_count / issue_types
    [기록 안 함] results(raw) / message 원문 / issues 원문 — sanitize 화이트리스트로 차단.
    [안정성] log_event 가 실패해도(False) 결과에는 영향이 없다.
    """
    if not isinstance(result, dict):
        return
    status = result.get("status")
    mcp_logging.log_event(_event_for_status(status), {
        "tool_name": tool_name,
        "status": status,
        "validation_status": result.get("validation_status"),
        "executed_count": result.get("executed_count"),
        "issue_types": _issue_types(result.get("issues")),
    })


def list_mcp_tools():
    """노출할 MCP Tool schema 목록을 반환한다(contracts 기준).

    [반환]
        list[dict] — mcp_schemas.build_mcp_tool_schemas() 결과.
                     FORBIDDEN_SQL_TOOLS 는 포함되지 않는다.

    [용도]
        MCP Client 가 사용 가능한 Tool 과 input schema 를 확인할 때 사용한다.
    """
    return mcp_schemas.build_mcp_tool_schemas()


def call_mcp_tool(tool_name, arguments):
    """개별 MCP Tool 을 직접 호출한다(검증 후 PASS 일 때만 실행).

    [입력]
        tool_name: 호출할 Tool 이름.
        arguments: 호출 인자 dict.
    [반환]
        tool_executor.execute_tool_plan() 의 결과 dict
        (status / validation_status / executed_count / results / issues / message).
        금지/미허용 Tool 은 즉시 rejected 로 반환한다.

    [동작]
        1) 금지/미허용 Tool 이면 rejected (schema 에 없는 Tool 차단).
        2) build_single_tool_plan 으로 단일 Tool Plan 생성.
        3) execute_tool_plan 으로 정규화 → 검증 → PASS 면 실행.

    [보안]
        execute_sql 등 금지 Tool 은 1단계에서 차단되고, 설령 통과해도
        normalizer/validation 단계에서 다시 FAIL 처리되어 실행되지 않는다.
    """
    # 시작 로그: 어떤 Tool 이 어떤 인자로 호출됐는지(인자는 sanitize 되어 기록됨).
    mcp_logging.log_event("tool_called", {
        "tool_name": tool_name,
        "arguments": arguments,
    })

    # 1) 금지/미허용 Tool 즉시 차단 (방어적 1차 게이트)
    if tool_name in FORBIDDEN_SQL_TOOLS:
        result = {
            "status": "rejected",
            "validation_status": "FAIL",
            "executed_count": 0,
            "results": [],
            "issues": [],
            "message": "금지된 Text-to-SQL/SQL 관련 Tool 이므로 실행하지 않습니다.",
        }
        _log_execution_result(tool_name, result)
        return result
    if tool_name not in ALLOWED_TOOLS:
        result = {
            "status": "rejected",
            "validation_status": "FAIL",
            "executed_count": 0,
            "results": [],
            "issues": [],
            "message": "허용 목록에 없는 Tool 이므로 실행하지 않습니다.",
        }
        _log_execution_result(tool_name, result)
        return result

    # 2) 단일 Tool Plan 으로 감싼 뒤 3) 검증 후 실행
    plan = tool_executor.build_single_tool_plan(tool_name, arguments)
    # user_query 가 없으므로 normalization 은 빈 query 기준으로 동작(인자 기본값 보정 위주).
    result = tool_executor.execute_tool_plan(plan, user_query="")
    # 결과 status 별로 tool_executed/tool_rejected/tool_needs_review/tool_error 기록.
    _log_execution_result(tool_name, result)
    return result


def call_select_tools_for_manufacturing_query(user_query):
    """사용자 질문으로 LLM Tool Plan 을 '생성'만 한다(실행하지 않음).

    [입력]
        user_query   : 사용자 자연어 질문.
    [반환]
        tool_selector.select_tool_plan_with_llm() 결과
        (tool_plan / generation_source / fallback_used / error_message).

    [주의]
        기본 실행은 LLM 기반 strict 모드다. LLM 이 Tool Plan 을 생성하지 못하면
        rule 기반 대체 실행을 하지 않고 구조화된 실패 응답을 반환한다.
        API Key 가 없는 환경에서는 generation_source 가 "unavailable" 또는
        "llm_error" 인 실패 응답이 정상이다. 이 함수는 실행을 하지 않는다.
    """
    selection = tool_selector.select_tool_plan_with_llm(user_query)
    # Selection 완료 로그: 출처/ fallback 여부 + 질의 preview(원문 전체는 미기록).
    mcp_logging.log_event("tool_selected", {
        "user_query": user_query,
        "generation_source": selection.get("generation_source"),
        "fallback_used": selection.get("fallback_used"),
    })
    return selection


def call_validate_tool_plan(tool_plan, user_query=""):
    """주어진 Tool Plan 을 normalizer → validation 으로 검증한 결과를 반환한다(실행 안 함).

    [입력]
        tool_plan : {"plan": [...]} 형태.
        user_query: 정규화 entity 추출용(선택).
    [반환]
        {
          "validation_status": "PASS"|"WARNING"|"FAIL"|"NEEDS_REVIEW",
          "issues": [...],
          "executable": bool   # PASS 면 True (기본 정책상 실행 가능 여부)
        }

    [동작]
        tool_executor.execute_tool_plan 을 dry_run=True 로 호출해 실행 없이 검증만 수행하고,
        검증 핵심 정보만 추려서 반환한다.

    [주의]
        WARNING/FAIL/NEEDS_REVIEW 는 executable=False (기본 정책상 실행하지 않음).
    """
    # dry_run=True 로 실행 없이 정규화/검증만 수행
    exec_result = tool_executor.execute_tool_plan(
        tool_plan, user_query=user_query, dry_run=True
    )
    validation_status = exec_result.get("validation_status", "FAIL")
    issues = exec_result.get("issues", [])
    # 검증 완료 로그: 검증 상태 + 이슈 타입만(이슈 원문 메시지는 미기록).
    mcp_logging.log_event("tool_validated", {
        "validation_status": validation_status,
        "issue_types": _issue_types(issues),
    })
    return {
        "validation_status": validation_status,
        "issues": issues,
        # 기본 정책: PASS 만 실행 가능으로 본다(WARNING 은 검토 필요).
        "executable": validation_status == "PASS",
    }


def call_execute_selected_tools(tool_plan, user_query="", dry_run=False):
    """이미 만들어진 Tool Plan 을 실행한다(검증 후 PASS 면 실행).

    [입력]
        tool_plan : {"plan": [...]} 형태.
        user_query: 정규화 entity 추출용(선택).
        dry_run   : True 면 실제 조회 없이 실행 계획만 확인.
    [반환]
        tool_executor.execute_tool_plan() 결과 dict.

    [용도]
        Selection 과 Execution 을 분리해 호출하고 싶을 때 사용한다.
        (먼저 call_select_... 로 plan 을 만들고, 검토 후 이 함수로 실행)
    """
    result = tool_executor.execute_tool_plan(
        tool_plan, user_query=user_query, dry_run=dry_run
    )
    # 실행 결과 로그(이미 만들어진 plan 실행). tool_name 은 단일이 아니므로 "(tool_plan)".
    _log_execution_result("(tool_plan)", result)
    return result


def call_execute_query(user_query, dry_run=False):
    """사용자 질문 → LLM Tool Plan 생성 → 검증 → PASS 면 실행하는 end-to-end 진입점.

    [입력]
        user_query   : 사용자 자연어 질문.
        dry_run      : True 면 실제 조회 없이 실행 계획만 확인.
    [반환]
        execute_tool_plan 결과 dict 에 generation_source/fallback_used 를 덧붙인 dict.

    [동작]
        1) tool_selector 로 LLM Tool Plan 생성(실패 시 구조화된 strict 실패 응답).
        2) tool_executor 로 정규화 → 검증 → PASS 면 실행(WARNING/FAIL 은 미실행).
        3) Selection 출처(generation_source/fallback_used)를 결과에 함께 담는다.

    [주의]
        기본 실행은 LLM 기반 strict 모드다. LLM 실패 시 rule 기반 대체 실행을 하지 않고,
        generation_source 가 "unavailable"/"llm_error" 인 실패 응답을 반환한다(fallback_used=False).
        WARNING/FAIL 인 경우 needs_review/rejected 로 반환되며 실제 조회는 하지 않는다.
    """
    # 시작 로그: 어떤 질의가 들어왔는지(원문 전체가 아니라 preview 로만 기록).
    mcp_logging.log_event("tool_called", {"user_query": user_query})

    # 1) Selection: LLM 으로 Tool Plan 생성
    selection = tool_selector.select_tool_plan_with_llm(user_query)
    # Selection 완료 로그(출처/fallback 여부).
    mcp_logging.log_event("tool_selected", {
        "generation_source": selection.get("generation_source"),
        "fallback_used": selection.get("fallback_used"),
    })

    # 2) Execution: 생성된 plan 을 정규화 → 검증 → PASS 면 실행
    exec_result = tool_executor.execute_tool_plan(
        selection.get("tool_plan", {"plan": []}),
        user_query=user_query,
        dry_run=dry_run,
    )

    # 3) Selection 출처 정보를 실행 결과에 함께 담아 반환(해석에 도움)
    exec_result["generation_source"] = selection.get("generation_source")
    exec_result["fallback_used"] = selection.get("fallback_used")
    exec_result["selection_error_message"] = selection.get("error_message")

    # 실행 결과 로그: status 별 이벤트 + 생성 출처도 함께 남긴다.
    _log_execution_result("(query)", exec_result)
    return exec_result


# ===========================================================================
# FastMCP wrapper 계층 (MCP Tool 진입점)
# ===========================================================================
# [설계 원칙]
# - 아래 _fastmcp_* 함수는 위의 기존 함수형 API 를 '그대로 호출'하는 얇은 계층이다.
#   기능 로직은 기존 함수에 있고, wrapper 는 MCP Tool 진입점 역할만 한다.
# - 로그는 기존 진입 함수에서 이미 남기므로, wrapper 는 핵심 이벤트를 '중복 기록하지
#   않는다'. (FastMCP 경유든 함수형 직접 호출이든 동일하게 1회만 기록된다.)
# - 타입 힌트는 FastMCP 가 input schema 를 자동 생성하는 데 사용된다.


def _fastmcp_execute_query(user_query: str, dry_run: bool = False) -> dict:
    """[MCP Tool: execute_query] 질문 → 생성 → 검증 → PASS 면 실행(end-to-end 핵심)."""
    return call_execute_query(user_query, dry_run=dry_run)


def _fastmcp_select_tools_for_manufacturing_query(user_query: str) -> dict:
    """[MCP Tool: select_tools_for_manufacturing_query] LLM Tool Selection 만 수행(실행 안 함)."""
    return call_select_tools_for_manufacturing_query(user_query)


def _fastmcp_validate_tool_plan(tool_plan: dict, user_query: str = "") -> dict:
    """[MCP Tool: validate_tool_plan] 주어진 Tool Plan 의 정규화/검증 결과만 반환."""
    return call_validate_tool_plan(tool_plan, user_query=user_query)


def _fastmcp_execute_selected_tools(tool_plan: dict, user_query: str = "",
                                    dry_run: bool = False) -> dict:
    """[MCP Tool: execute_selected_tools] 이미 만들어진 Tool Plan 을 검증 후 실행."""
    return call_execute_selected_tools(tool_plan, user_query=user_query, dry_run=dry_run)


def _fastmcp_call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """[MCP Tool: call_mcp_tool] 개별 Tool 직접 호출(검증 후 PASS 면 실행)."""
    return call_mcp_tool(tool_name, arguments)


def _fastmcp_list_mcp_tools() -> list:
    """[MCP Tool: list_mcp_tools] 노출 Tool schema 목록(교육/디버깅용)."""
    return list_mcp_tools()


def create_fastmcp_server():
    """FastMCP server 객체를 생성하고 Tool wrapper 를 등록해 돌려준다.

    [반환]
        - 생성에 성공하면 FastMCP server 객체.
        - 생성/등록 중 오류가 나면 None.
          (안내 dict 가 아니라 명시적으로 Python None 을 반환한다.)

    [등록 Tool]
        execute_query / select_tools_for_manufacturing_query / validate_tool_plan /
        execute_selected_tools / call_mcp_tool / list_mcp_tools

    [노출 금지]
        raw 로그 조회, 환경변수 조회, SQL/Text-to-SQL Tool 은
        등록하지 않는다.

    [안정성]
        등록 실패를 외부로 던지지 않고 None 으로 흡수한다.
    """
    try:
        server = FastMCP("mcp_server03")
        # MCP Tool 이름은 함수형 API 보다 짧고 명확하게 부여한다(기존 함수명과 1:1 추적 가능).
        server.tool(name="execute_query")(_fastmcp_execute_query)
        server.tool(name="select_tools_for_manufacturing_query")(
            _fastmcp_select_tools_for_manufacturing_query
        )
        server.tool(name="validate_tool_plan")(_fastmcp_validate_tool_plan)
        server.tool(name="execute_selected_tools")(_fastmcp_execute_selected_tools)
        server.tool(name="call_mcp_tool")(_fastmcp_call_mcp_tool)
        server.tool(name="list_mcp_tools")(_fastmcp_list_mcp_tools)
        return server
    except Exception:
        # 등록 실패도 메인 흐름을 깨뜨리지 않는다.
        return None


def warm_up_rag_dependencies():
    """RAG(search_manual) 무거운 의존성을 '메인 스레드에서 미리' 한 번 적재한다(best-effort).

    [왜 필요한가 — stdio worker-thread import deadlock 회피]
        FastMCP 는 동기 Tool 함수를 worker thread(anyio.to_thread)에서 실행한다. stdio transport
        에서는 메인 스레드가 stdin 블로킹 읽기에 들어가 있는데, 이 상태에서 worker thread 가
        chromadb(onnxruntime 등 무거운 native 확장)를 '처음' import 하면 import 가 멈춰(hang)
        search_manual 이 무응답/timeout 된다(DB Tool 은 영향 없음).
        → 서버 기동 시(=메인 스레드, server.run() 이전) chromadb/PersistentClient/collection 을
          미리 적재해 두면, 이후 worker thread 의 import 는 캐시된 no-op 이 되어 hang 이 사라진다.
          (chromadb 는 같은 경로의 PersistentClient/onnx 모델을 내부 캐시로 재사용한다.)

    [경계/안정성]
        - best-effort: 어떤 예외도 서버 기동을 막지 않는다(chromadb 미설치/DB 미생성도 정상).
        - 로그/진단은 stderr 로만 남긴다(stdio 의 stdout=프로토콜 채널을 오염시키지 않음).
        - Ollama 미실행이어도 chromadb import/client/collection 적재라는 목적은 달성된다
          (임베딩 단계 실패는 mock fallback 으로 흡수되며, 적재 자체는 이미 끝난 뒤다).
    """
    import sys
    try:
        # manual_search → adapter → rag_search 로 내려가며 chromadb import / PersistentClient /
        # get_collection(onnx 모델 적재)까지 메인 스레드에서 1회 수행한다(결과는 버린다).
        from day5.mcp_server03 import manual_search
        manual_search.search_manual("warm up", alarm_code=None)
        print("[mcp_server03] RAG 의존성 warm-up 완료(메인 스레드 사전 적재)", file=sys.stderr, flush=True)
    except Exception as error:  # noqa: BLE001 - warm-up 실패는 서버 기동을 막지 않는다
        # 사유 원문/스택은 남기지 않고 타입만 짧게(민감정보 방지).
        print(f"[mcp_server03] RAG 의존성 warm-up 생략({type(error).__name__})", file=sys.stderr, flush=True)


def run_fastmcp_server():
    """FastMCP server 를 실행한다(설치돼 있을 때만).

    [반환]
        - 생성 실패: 안전 안내 dict(예외 없음).
        - 정상 실행 후 종료: 종료 안내 dict.

    [보안]
        API Key / endpoint / 환경변수 값 등은 출력/반환하지 않는다.

    [주의]
        server.run() 은 (stdio 등) 블로킹 실행이다.
    """
    server = create_fastmcp_server()
    if server is None:
        return {
            "status": "unavailable",
            "message": "FastMCP server 생성에 실패했습니다.",
        }

    # stdio worker-thread 의 chromadb import deadlock 을 피하려고, 메인 스레드에서 RAG 의존성을
    # 미리 적재한다(best-effort, 실패해도 서버 기동에는 영향 없음).
    warm_up_rag_dependencies()
    mcp_logging.log_event("server_started", {"has_fastmcp": True})
    try:
        server.run()
    except Exception as error:
        # 실행 중 오류는 안전 메시지로만(스택트레이스/민감정보 미노출).
        return {"status": "error", "message": type(error).__name__}
    return {"status": "stopped"}


def run_fastmcp_http_server(host: str = "127.0.0.1", port: int = 8003,
                            path: str = "/mcp"):
    """FastMCP server 를 streamable-http transport 로 실행한다(long-lived HTTP 서버).

    [왜 HTTP 옵션을 두는가]
        stdio transport 는 client 가 Tool 호출마다 서버 프로세스를 새로 spawn 한다. 이 환경에서
        search_manual(RAG: chroma+onnx+Ollama)을 stdio 서브프로세스로 호출하면 무응답/timeout 된다
        (DB Tool 은 정상). long-lived HTTP 서버로 띄우면 RAG 초기화 비용을 1회만 치르고 프로세스가
        살아 있는 상태로 재사용되어, search_manual 이 in-process 와 같은 수초 내에 정상 응답한다.

    [기존 stdio 와의 관계]
        run_fastmcp_server()(기본 stdio)는 그대로 둔다. 이 함수는 '추가' 실행 옵션이며,
        둘 중 어느 쪽도 서로의 동작을 바꾸지 않는다.

    [입력]
        host: 바인드 주소(기본 127.0.0.1 — 로컬 전용).
        port: 포트(기본 8003).
        path: MCP endpoint 경로(기본 /mcp). client 는 http://host:port/path 로 접속.

    [반환]
        - 생성 실패: 안전 안내 dict(예외 없음).
        - server.run() 은 블로킹이라 정상 종료(Ctrl+C 등) 시 종료 안내 dict.

    [보안]
        host 기본값은 127.0.0.1(외부 노출 안 함). API Key/endpoint/환경변수 값은 출력/반환하지 않는다.
        배너는 끄고(show_banner=False), 일반 로그는 uvicorn 이 stderr 로 보낸다(stdout protocol 혼선 없음).
    """
    server = create_fastmcp_server()
    if server is None:
        return {
            "status": "unavailable",
            "message": "FastMCP server 생성에 실패했습니다.",
        }

    # transport/host/port 만 로깅한다(민감정보 없음).
    mcp_logging.log_event("server_started", {
        "has_fastmcp": True, "transport": "streamable-http", "port": port,
    })
    try:
        server.run(transport="streamable-http", host=host, port=port,
                   path=path, show_banner=False)
    except Exception as error:
        return {"status": "error", "message": type(error).__name__}
    return {"status": "stopped"}


def _parse_cli_args(argv=None):
    """__main__ 용 최소 CLI 파서. 기본은 stdio(기존 동작 유지), --transport http 면 HTTP 실행."""
    import argparse
    parser = argparse.ArgumentParser(
        description="mcp_server03 - FastMCP server (stdio 기본, streamable-http 옵션)"
    )
    parser.add_argument("--transport", default="stdio",
                        choices=["stdio", "http", "streamable-http"],
                        help="실행 transport. 기본 stdio(기존 동작). http/streamable-http 는 long-lived HTTP")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host(기본 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8003, help="HTTP port(기본 8003)")
    parser.add_argument("--path", default="/mcp", help="HTTP MCP endpoint 경로(기본 /mcp)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    # 직접 실행 시: 기본은 stdio(기존 동작 유지). --transport http 면 long-lived HTTP 로 실행.
    _args = _parse_cli_args()
    if _args.transport in ("http", "streamable-http"):
        run_fastmcp_http_server(host=_args.host, port=_args.port, path=_args.path)
    else:
        run_fastmcp_server()
