# -*- coding: utf-8 -*-
"""
Day5 mcp_client03 - Result Formatting (결과 요약 / 민감정보 차단)

[이 파일의 역할]
실제 stdio MCP 호출 결과(서버 envelope dict 또는 timeout/error 표시 dict)를 화면에 보여줄 때,
전체를 그대로 쏟지 않고 '민감정보 없는 요약'으로 정리합니다.

[mcp_client01/02 와의 관계]
요약 아이디어는 동일하지만, 단계별 독립성을 위해 mcp_client03 내부에 별도 파일로 둡니다.
mcp_client01/02 파일은 수정하지 않습니다.

[보안 원칙]
- 민감 key(_SENSITIVE_MARKERS)는 출력하지 않는다.
- 문서 전문/내부 경로/접속 비밀값/민감 컬럼은 요약 대상에서 제외한다.
- 긴 list(documents/events/history)는 상위 3개만.
- 예상치 못한 구조(또는 timeout/error 표시)도 오류 없이 요약한다.
"""
from __future__ import annotations


_SENSITIVE_MARKERS = (
    "password", "token", "secret", "connection", "dsn",
    "source_path", "file_path", "internal_url",
    "full_text", "chroma:document", "raw_metadata",
    "message", "operator_note", "technician_note", "lot_id",
    "owner_team", "location",
)


def _is_sensitive_key(key) -> bool:
    name = str(key).lower()
    return any(marker in name for marker in _SENSITIVE_MARKERS)


def safe_preview(value, max_chars: int = 120) -> str:
    """문자열을 공백 정리 후 max_chars 로 잘라 미리보기로 만든다(긴 본문 노출 방지)."""
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:max_chars] + "..." if len(text) > max_chars else text


def summarize_items(items, max_items: int = 3) -> list:
    """list[dict](events/history)을 상위 max_items 개만 'k=v' 로 요약한다."""
    if not isinstance(items, list):
        return []
    out = []
    for item in items[:max_items]:
        if isinstance(item, dict):
            parts = [f"{k}={safe_preview(v, 40)}" for k, v in item.items()
                     if not _is_sensitive_key(k) and not isinstance(v, (list, dict))]
            out.append(", ".join(parts))
        else:
            out.append(safe_preview(item))
    if len(items) > max_items:
        out.append(f"...외 {len(items) - max_items}건")
    return out


def summarize_documents(documents, max_items: int = 3) -> list:
    """search_manual documents 를 상위 max_items 개만 'title / snippet' 로 요약한다."""
    if not isinstance(documents, list):
        return []
    out = []
    for doc in documents[:max_items]:
        if not isinstance(doc, dict):
            out.append(safe_preview(doc))
            continue
        out.append(f"title: {safe_preview(doc.get('title'), 60)} / snippet: {safe_preview(doc.get('snippet'), 90)}")
    if len(documents) > max_items:
        out.append(f"...외 {len(documents) - max_items}건")
    return out


def _extract_payload(envelope: dict) -> dict:
    """서버 envelope 에서 sanitize 된 단일 Tool result payload 를 꺼낸다."""
    if not isinstance(envelope, dict):
        return {}
    # envelope 구조: {status, ..., results: [{tool_name, status, result: {...}}, ...]}
    # 이 단계는 한 번에 Tool 하나만 호출하므로 results[0].result(단일 payload)만 꺼낸다.
    results = envelope.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        inner = results[0].get("result")
        return inner if isinstance(inner, dict) else {}
    return {}


def summarize_tool_result(tool_name: str, envelope: dict) -> str:
    """실제 stdio 호출 결과(envelope)를 교육용으로 간결히 요약한 문자열로 만든다.

    timeout/error/rejected 와 정상 실행을 구분해 보여주며, 민감 필드는 포함하지 않는다.
    """
    if not isinstance(envelope, dict):
        return "status: unknown\n(요약할 수 없는 결과 형식)"

    status = envelope.get("status")

    # [분기 1] 클라이언트 측 timeout/error 표시(transport_stdio 가 만든 안전 dict)는 한 줄로 끝낸다.
    if status == "timeout":
        return f"status: timeout\nnote: {safe_preview(envelope.get('_note'), 80)}"
    if envelope.get("_client_error"):
        return f"status: error\nnote: client_error: {envelope.get('_client_error')}"

    lines = [f"status: {status}"]
    # [분기 2] 서버가 거부(rejected)한 경우(예: execute_sql 같은 금지 Tool)도 이유만 적고 끝낸다.
    if status == "rejected":
        lines.append("reason: forbidden tool" if "금지" in str(envelope.get("message", "")) else "reason: rejected")
        return "\n".join(lines)

    # [분기 3] 정상 실행: envelope 에서 payload 를 꺼내, 출처 표시 → 리스트 요약 → 비민감 스칼라 순으로 정리한다.
    payload = _extract_payload(envelope)
    for key in ("validation_status", "retrieval_source", "data_source", "fallback_used"):
        if key in payload:
            lines.append(f"{key}: {payload.get(key)}")
        elif key == "validation_status" and key in envelope:
            lines.append(f"{key}: {envelope.get(key)}")

    if "documents" in payload:
        docs = payload.get("documents") or []
        lines.append(f"documents: {len(docs)}")
        for d in summarize_documents(docs):
            lines.append(f"  - {d}")
    if "recent_events" in payload:
        ev = payload.get("recent_events") or []
        lines.append(f"events: {len(ev)}")
        for e in summarize_items(ev):
            lines.append(f"  - {e}")
    if "history" in payload:
        hist = payload.get("history") or []
        lines.append(f"history: {len(hist)}")
        for h in summarize_items(hist):
            lines.append(f"  - {h}")

    shown = ("validation_status", "retrieval_source", "data_source", "fallback_used",
             "documents", "recent_events", "history")
    for key, value in payload.items():
        if key in shown or _is_sensitive_key(key) or isinstance(value, (list, dict)):
            continue
        lines.append(f"{key}: {safe_preview(value)}")
    return "\n".join(lines)
