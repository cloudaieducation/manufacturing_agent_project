# -*- coding: utf-8 -*-
"""
Day5 mcp_client_final - 다중 DB Tool 병렬 호출 데모 (parallel_runner)

[이 모듈이 무엇인가 — 교육용 설명]
이 모듈은 'Client 측에서 여러 DB 조회 Tool 호출을 동시에 시작'하는 교육용 데모입니다.
기존 agent_flow.run_agent_flow 의 '의도 판단 → Tool 순차 호출' 흐름과는 별개이며, 같은 설비/라인
식별자로 안전한 DB 조회 Tool 여러 개를 ThreadPoolExecutor 로 동시에 호출해 봅니다.

[병렬의 정확한 의미 — 매우 중요]
- 이것은 'Client 측 다중 DB Tool 병렬 호출'입니다. 병렬 호출을 '시작'하는 쪽은 Client 입니다.
- Server(mcp_server03/mcp_server_final)는 동시에 들어온 Tool 요청을 '처리'하는 역할일 뿐입니다.
- Agent 가 여러 개인 구조가 아니라(멀티에이전트 아님), 'Tool 호출'만 병렬화하는 구조입니다.

[경계 — 기존 재사용 범위 유지]
- mcp_client04 에서 'config' 와 'mcp_tools'(ToolCaller / extract_payload)만 재사용합니다.
- mcp_client04 의 runner / agents / graph 는 import 하지 않습니다(Agent 스택 비의존).
- mcp_server_final / mcp_server03 의 내부 모듈은 직접 import 하지 않습니다(MCP Tool 호출 경로 유지).
- 데이터 접근은 ToolCaller(call_mcp_tool 경유)만 사용합니다(DB/Chroma 직접 접속 금지).

[안전/정직 표기]
- 호출 대상은 '안전한 조회(SELECT 계열) DB Tool' 화이트리스트뿐입니다(아래 SAFE_PARALLEL_DB_TOOLS).
- search_manual(RAG) / execute_sql / SQL 변경 계열 Tool 은 병렬 데모 대상에서 제외합니다.
- 한 Tool 의 실패는 예외로 전체를 멈추지 않고 Tool별 status="ERROR" 로 정직하게 기록합니다.
- 결과는 payload 전체가 아니라 '비민감 요약'(리스트는 _count)만 담습니다.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# [import 경로 보강] 이 파일 <root>/src/day5/mcp_client_final/parallel_runner.py → parents[3] = <root>.
# streamlit 직접 실행 등 어디서 실행하든 'day5.*' 를 찾도록 <root>/src 를 sys.path 에 넣는다.
_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# [재사용 — 기존 범위 유지] mcp_client04 의 'config' 와 'mcp_tools' 만 가져온다.
#   - config         : 타임아웃 등 설정 상수(MCP_HTTP_URL=8000 은 사용하지 않고 로컬 8003 상수 사용).
#   - HttpToolCaller : standalone HTTP(streamable-http) 서버 접속용 ToolCaller(이 데모는 http 전용).
#   - extract_payload: call_mcp_tool envelope 에서 단일 Tool result payload 를 꺼내는 헬퍼.
# runner / agents / graph 는 import 하지 않는다(Agent 스택 비의존).
from day5.mcp_client04 import config
from day5.mcp_client04.mcp_tools import HttpToolCaller, extract_payload


# [standalone HTTP 전용] 교육용 최종 실습 MCP endpoint 를 8003 으로 통일한다.
#   mcp_client04.config.MCP_HTTP_URL 은 8000 을 가리키므로 사용하지 않고, 이 로컬 상수만 사용한다
#   (mcp_client04 는 참조 대상이라 수정하지 않는다).
DEFAULT_MCP_HTTP_URL = "http://127.0.0.1:8003/mcp"


# ===========================================================================
# 병렬 데모 대상 — '안전한 조회(SELECT 계열) DB Tool' 화이트리스트(서버 contract 와 일치).
#   execute_sql / 데이터 변경 SQL 계열 / search_manual(RAG) 은 의도적으로 제외한다.
# ===========================================================================
SAFE_PARALLEL_DB_TOOLS = (
    "get_equipment_overview",   # required: equipment_id
    "get_recent_alarm_events",  # required: equipment_id / optional: alarm_code, limit
    "get_quality_metrics",      # any_of: metric_name/equipment_id/line_id / optional: date_range, limit
    "get_maintenance_history",  # required: equipment_id / optional: date_range, part_replaced
)

# 병렬 데모에서 schema 기준으로 채울 수 있는 입력 인자(이 외 인자는 임의로 만들어 넣지 않는다).
_FILLABLE_PARALLEL_ARGS = ("equipment_id", "line_id", "limit")

# 방어적 2차 차단 — 위험/비대상 Tool 이름 패턴(화이트리스트만 순회하므로 정상 환경에선 매칭 안 됨).
_FORBIDDEN_PARALLEL_PATTERNS = (
    "execute_sql", "run_sql", "sql", "drop", "delete", "update",
    "insert", "alter", "truncate", "grant", "revoke", "merge",
)
# RAG 계열은 병렬 DB 데모 대상이 아니다('조회 Tool 병렬'이라는 데모 취지와 분리 + stdio timeout 가능).
_EXCLUDED_PARALLEL_TOOLS = ("search_manual",)

# 결과 요약에서 제외할 민감 key 마커(부분 일치, 소문자 비교). 서버가 이미 sanitize 하지만 2차 방어.
_SENSITIVE_MARKERS = (
    "password", "token", "secret", "connection", "dsn",
    "source_path", "file_path", "internal_url",
    "full_text", "chroma:document", "raw_metadata",
    "message", "operator_note", "technician_note", "lot_id", "owner_team", "location",
)


def _is_sensitive_key(key) -> bool:
    """key 이름에 민감 마커가 포함되면 True(요약 제외 대상)."""
    name = str(key).lower()
    return any(marker in name for marker in _SENSITIVE_MARKERS)


def _is_forbidden_parallel_tool(tool_name) -> bool:
    """병렬 데모 대상에서 무조건 제외할 위험/비대상 Tool 인지 판정한다(방어적 2차 차단)."""
    low = str(tool_name or "").lower()
    if low in _EXCLUDED_PARALLEL_TOOLS:
        return True
    return any(pat in low for pat in _FORBIDDEN_PARALLEL_PATTERNS)


def _sanitize_payload(payload: dict) -> dict:
    """payload 에서 '민감 key 제외 + 리스트는 개수만' 으로 작은 요약 dict 를 만든다.

    [목적] payload 전체/민감 필드/문서 전문을 화면에 노출하지 않는다(비민감 요약만).
    """
    safe = {}
    if not isinstance(payload, dict):
        return safe
    for key, value in payload.items():
        if _is_sensitive_key(key):
            continue
        if isinstance(value, list):
            safe[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            continue
        else:
            safe[key] = value
    return safe


def _build_caller(transport: str, http_url, timeout: int):
    """standalone HTTP 서버에 연결하는 ToolCaller 를 새로 만든다(워커마다 호출 → 공유 금지, http 전용).

    - http  : 외부 long-lived streamable-http 서버(http://127.0.0.1:8003/mcp)에 접속(서버 선기동 필요).
    [경계] client 가 http 서버를 spawn 하지 않는다. 사용자가 미리 띄운 URL 에 접속만 한다.
    [정책] standalone HTTP 전용. transport 가 http 가 아니면 조용히 바꾸지 않고 명확한 오류를 발생시킨다.
    """
    if transport != "http":
        raise ValueError(
            "mcp_client_final은 standalone HTTP 서버 연결만 지원합니다. "
            "mcp_server_final을 8003 포트로 먼저 실행해 주세요."
        )
    return HttpToolCaller(url=http_url or DEFAULT_MCP_HTTP_URL,
                          timeout=max(timeout, config.RAG_TIMEOUT))


def _build_specs(tool_schemas, equipment_id, line_id, limit) -> dict:
    """병렬 호출할 '안전한 DB 조회 Tool' 과 Tool별 인자를 schema 기준으로 구성한다.

    [왜 Tool 마다 인자를 다르게 구성하나]
        Tool 마다 받는 입력이 다르다. schema(inputSchema)에 '존재하는' 인자만, 값이 있을 때만 채운다.
        required 를 모두 채울 수 없으면 호출하지 않고 skipped 에 사유를 기록한다(추측 인자 금지).
    [반환] {"specs": [{tool_name, arguments}...], "skipped_tools": [{tool_name, reason}...]}
    """
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

    # schema 를 이름으로 찾기 쉽게 매핑.
    schema_by_name = {}
    for schema in (tool_schemas or []):
        if isinstance(schema, dict) and schema.get("name"):
            schema_by_name[schema["name"]] = schema

    specs = []
    skipped = []
    for name in SAFE_PARALLEL_DB_TOOLS:
        if _is_forbidden_parallel_tool(name):
            # 정상 환경에선 도달하지 않지만, 위험 Tool 이 섞여도 절대 병렬 호출 대상에 넣지 않는다.
            skipped.append({"tool_name": name, "reason": "위험/비대상 Tool 패턴으로 병렬 호출에서 제외"})
            continue
        schema = schema_by_name.get(name)
        if not schema:
            skipped.append({"tool_name": name, "reason": "서버 schema 에 노출되지 않은 Tool 이라 제외"})
            continue
        input_schema = schema.get("inputSchema") or {}
        props = input_schema.get("properties") or {}
        required = input_schema.get("required") or []
        # schema 의 properties 에 있는 인자만, 값이 있을 때만 채운다(추측 인자 금지).
        args = {}
        for arg_name in _FILLABLE_PARALLEL_ARGS:
            if arg_name in props and available.get(arg_name) is not None:
                args[arg_name] = available[arg_name]
        # required 인자를 모두 구성할 수 있는지 확인 — 못 채우면 호출하지 않고 skipped 에 사유 기록.
        missing = [req for req in required if req not in args]
        if missing:
            skipped.append({
                "tool_name": name,
                "reason": f"required argument missing: {', '.join(missing)}",
            })
            continue
        specs.append({"tool_name": name, "arguments": args})

    return {"specs": specs, "skipped_tools": skipped}


def _summarize_envelope(tool_name: str, envelope) -> dict:
    """서버 envelope 를 Tool별 결과 항목(비민감 요약)으로 변환한다.

    [반환] {tool_name, status, data_source, fallback_used, error, result_summary}
        status ∈ "OK" | "EMPTY" | "ERROR"
        - _client_error / server status(timeout/error/rejected) → ERROR(정직 표기, 원문 trace 미노출).
        - 정상 envelope → payload 의 data_source/fallback_used + 비민감 요약. 리스트가 모두 0건이면 EMPTY.
    """
    entry = {"tool_name": tool_name, "status": None, "data_source": None,
             "fallback_used": None, "error": None, "result_summary": {}}

    if not isinstance(envelope, dict):
        entry["status"] = "ERROR"
        entry["error"] = "invalid_envelope"
        return entry

    # transport 가 만든 안전 표시(timeout/연결 오류) 또는 서버 status 를 ERROR 로 정직 변환.
    if envelope.get("_client_error"):
        entry["status"] = "ERROR"
        entry["error"] = f"client_error:{envelope.get('_client_error')}"
        return entry
    server_status = envelope.get("status")
    if server_status in ("timeout", "error"):
        entry["status"] = "ERROR"
        entry["error"] = str(server_status)
        return entry
    if server_status == "rejected":
        entry["status"] = "ERROR"
        entry["error"] = "rejected(금지 Tool)"
        return entry

    # 정상 envelope → 단일 Tool payload 추출 후 비민감 요약.
    payload = extract_payload(envelope) or {}
    summary = _sanitize_payload(payload)
    entry["data_source"] = payload.get("data_source")
    entry["fallback_used"] = payload.get("fallback_used")
    entry["result_summary"] = summary

    # 리스트형 결과(recent_events/history 등)가 모두 0건이면 EMPTY(결과 없음)로 정직 표기.
    list_counts = [v for k, v in summary.items() if k.endswith("_count")]
    if list_counts and all((c or 0) == 0 for c in list_counts):
        entry["status"] = "EMPTY"
    else:
        entry["status"] = "OK"
    return entry


def _call_one(spec, caller_factory) -> dict:
    """병렬 작업 1건 — '워커 스레드 안에서' 독립 caller 를 만들어 DB Tool 하나를 호출한다.

    [왜 caller 를 작업마다 새로 만드나 — 공유 금지]
        ToolCaller / fastmcp.Client 의 thread-safety 가 보장되지 않으므로, 각 워커가 자기 caller 를
        새로 만들어 쓴다(MCP 세션/asyncio 상태 경합 방지).
    [시간 측정] 이 호출의 소요 시간(elapsed_ms)을 워커 안에서 측정해 결과에 담는다.
    [반환] _summarize_envelope 결과 + elapsed_ms. 예외도 ERROR 항목으로 변환한다(전체 중단 방지).
    """
    tool_name = spec["tool_name"]
    start = time.perf_counter()
    try:
        caller = caller_factory()
        envelope = caller.call_tool(tool_name, dict(spec.get("arguments") or {}))
        entry = _summarize_envelope(tool_name, envelope)
    except Exception as error:  # noqa: BLE001 - 한 Tool 실패가 전체를 깨지 않게 격리(원문 trace 미노출)
        entry = {"tool_name": tool_name, "status": "ERROR", "data_source": None,
                 "fallback_used": None, "error": f"call_failed:{type(error).__name__}",
                 "result_summary": {}}
    entry["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
    return entry


def run_parallel_db_tools_demo(
    *,
    equipment_id: str = "EQP-EV-03",
    line_id: str | None = None,
    limit: int = 5,
    transport: str = "http",
    http_url: str | None = None,
    max_workers: int = 4,
    timeout: int = config.DEFAULT_TIMEOUT,
) -> dict:
    """안전한 DB 조회 Tool 여러 개를 'Client 측에서 동시에' 호출하는 교육용 데모.

    [흐름]
        1) transport 별 caller 팩토리 준비(워커마다 새 caller — 공유 금지).
        2) list_tool_schemas() 로 서버가 노출한 Tool schema 를 1회 조회한다(인자 구성 근거).
           schema 를 못 받으면(서버 미기동/연결 실패) status="ERROR" 로 정직하게 표기한다.
        3) SAFE_PARALLEL_DB_TOOLS 중 schema·required 를 만족하는 Tool 만 호출 대상으로 구성한다.
        4) ThreadPoolExecutor 로 동시에 호출하고, Tool별 elapsed_ms 와 전체 total_elapsed_ms 를 측정한다.

    [입력]
        equipment_id : 조회 대상 설비(가상). 기본 "EQP-EV-03".
        line_id      : 조회 대상 라인(선택). 빈 값이면 미전달.
        limit        : 목록형 Tool 의 최대 건수(schema 에 limit 가 있는 Tool 에만 전달).
        transport    : "http" 전용(standalone HTTP 서버 접속). http 가 아니면 status="ERROR" 로 반환한다.
        http_url     : http 접속 URL(미지정 시 DEFAULT_MCP_HTTP_URL = http://127.0.0.1:8003/mcp).
        max_workers  : 동시 실행 상한(기본 4).
    [반환] status/transport/equipment_id/line_id/total_elapsed_ms/called_tools/skipped_tools/
           success_count/error_count/results(list) 를 담은 dict.
    """
    base = {
        "transport": transport,
        "equipment_id": equipment_id,
        "line_id": line_id,
        "limit": limit,
        "max_workers": max_workers,
    }

    # [standalone HTTP 전용] transport 가 http 가 아니면 조용히 바꾸지 않고 명확한 상태로 반환한다.
    if transport != "http":
        return {
            **base, "status": "ERROR", "total_elapsed_ms": 0,
            "called_tools": [], "skipped_tools": [], "success_count": 0, "error_count": 0,
            "results": [],
            "note": ("mcp_client_final은 standalone HTTP 서버 연결만 지원합니다. "
                     "mcp_server_final을 8003 포트로 먼저 실행해 주세요."),
        }

    def caller_factory():
        # 워커마다 새 caller 를 만든다(스레드 간 공유 금지). RAG 비대상이라 DB Tool 만 호출한다.
        return _build_caller(transport, http_url, timeout)

    # 2) Tool schema 조회(병렬 이전, 1회). 서버 미기동/연결 실패면 schema 가 비어 온다.
    try:
        tool_schemas = caller_factory().list_tool_schemas()
    except Exception as error:  # noqa: BLE001 - 연결 단계 오류를 안전 dict 로 변환(원문 trace 미노출)
        tool_schemas = []
        return {
            **base, "status": "ERROR", "total_elapsed_ms": 0,
            "called_tools": [], "skipped_tools": [], "success_count": 0, "error_count": 0,
            "results": [],
            "note": f"MCP 서버 schema 조회 실패({type(error).__name__}) — HTTP 서버 기동 여부를 확인하세요.",
        }
    if not tool_schemas:
        return {
            **base, "status": "ERROR", "total_elapsed_ms": 0,
            "called_tools": [], "skipped_tools": [], "success_count": 0, "error_count": 0,
            "results": [],
            "note": "MCP 서버 Tool schema 를 받지 못했습니다 — HTTP 서버 기동 여부/URL 을 확인하세요.",
        }

    # 3) 안전한 DB 조회 Tool 과 Tool별 인자를 schema 기준으로 구성한다.
    spec_result = _build_specs(tool_schemas, equipment_id, line_id, limit)
    specs = spec_result["specs"]
    skipped = spec_result["skipped_tools"]

    # 4) 병렬 호출 — ThreadPoolExecutor 로 동시에 실행(동기 call_tool 을 스레드로 병렬화).
    results = []
    success_count = 0
    error_count = 0
    total_elapsed_ms = 0
    if specs:
        workers = max(1, min(max_workers, len(specs)))
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pdb_final") as executor:
            future_to_name = {
                executor.submit(_call_one, spec, caller_factory): spec["tool_name"]
                for spec in specs
            }
            for future in as_completed(future_to_name):
                entry = future.result()  # _call_one 이 예외를 이미 ERROR 항목으로 흡수한다.
                results.append(entry)
                if entry.get("status") == "ERROR":
                    error_count += 1
                else:
                    success_count += 1
        total_elapsed_ms = int((time.perf_counter() - start) * 1000)

    # 호출 순서가 보이도록 tool_name 기준 정렬(병렬이라 완료 순서는 비결정적).
    results.sort(key=lambda e: e.get("tool_name", ""))
    called_tools = [spec["tool_name"] for spec in specs]

    # 전체 status 판정 — 전부 성공 OK / 일부만 성공·스킵 PARTIAL / 호출 0 또는 전부 실패 ERROR.
    if not called_tools:
        status = "ERROR"
    elif error_count == 0 and not skipped:
        status = "OK"
    elif success_count == 0:
        status = "ERROR"
    else:
        status = "PARTIAL"

    return {
        **base,
        "status": status,
        "total_elapsed_ms": total_elapsed_ms,
        "called_tools": called_tools,
        "skipped_tools": skipped,
        "success_count": success_count,
        "error_count": error_count,
        "results": results,
    }
