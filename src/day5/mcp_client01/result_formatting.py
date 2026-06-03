# -*- coding: utf-8 -*-
"""
Day5 mcp_client01 - Result Formatting (Tool 결과 요약/안전 출력)

[이 모듈의 역할]
MCP Client(mcp_client01)가 서버 Tool 호출 결과(dict)를 화면에 '요약'해서 보여줄 때
사용하는 보조 함수 모음입니다. 전체 dict 를 그대로 출력하지 않고, 교육용으로 핵심만 추립니다.

[보안 원칙 — 매우 중요]
- 민감 key(아래 _SENSITIVE_MARKERS)는 어떤 경우에도 출력하지 않는다.
- 문서 전문(full_text/chroma:document), 내부 경로(source_path/file_path/internal_url),
  접속 비밀값(password/token/secret/connection/dsn), 민감 컬럼(message/operator_note/
  technician_note/lot_id/owner_team/location)은 요약 대상에서 제외한다.
- 긴 문자열은 safe_preview 로 잘라 보여준다.
- 예상치 못한 구조가 들어와도 오류 없이 요약한다(클라이언트가 멈추지 않도록).

[주의]
이 모듈은 서버 결과를 '표시'만 한다. DB/RAG/repository 에 직접 접근하지 않는다.
"""
from __future__ import annotations


# 출력에서 제외할 민감 key 마커(부분 일치, 소문자 비교).
# key 이름에 아래 단어가 포함되면 그 필드는 요약/출력하지 않는다.
_SENSITIVE_MARKERS = (
    "password",
    "token",
    "secret",
    "connection",
    "dsn",
    "source_path",
    "file_path",
    "internal_url",
    "full_text",
    "chroma:document",
    "raw_metadata",
    "message",
    "operator_note",
    "technician_note",
    "lot_id",
    "owner_team",
    "location",
)


def _is_sensitive_key(key) -> bool:
    """key 이름에 민감 마커가 포함되면 True(출력 제외 대상)."""
    name = str(key).lower()
    return any(marker in name for marker in _SENSITIVE_MARKERS)


def safe_preview(value, max_chars: int = 120) -> str:
    """문자열 값을 max_chars 길이로 잘라 미리보기 문자열로 만든다.

    [목적]
        snippet/title 등 긴 문자열을 화면에 통째로 쏟지 않기 위함이다.
        문서 전문이 들어와도 길이를 제한해 보여준다(전문 노출 방지의 보조 장치).
    [동작]
        - 값이 없으면 빈 문자열.
        - 줄바꿈/연속 공백을 한 칸으로 정리하고, 길면 끝에 '...' 을 붙인다.
    """
    if value is None:
        return ""
    text = " ".join(str(value).split())
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def _safe_scalar_fields(payload: dict, skip_keys=()) -> list[str]:
    """payload 에서 '민감하지 않은 스칼라 필드'만 'key=value' 문자열 리스트로 만든다.

    list/dict 값은 여기서 다루지 않고(별도 요약), 민감 key/이미 출력한 key 는 건너뛴다.
    [skip_keys] 상위에서 이미 표시한 메타 필드(data_source/fallback_used 등)를 중복 출력하지 않기 위함.
    """
    lines = []
    if not isinstance(payload, dict):
        return lines
    skip = set(skip_keys)
    for key, value in payload.items():
        if key in skip or _is_sensitive_key(key):
            continue
        # 중첩 구조(documents/recent_events/history 등)는 전용 요약 함수에서 처리한다.
        if isinstance(value, (list, dict)):
            continue
        lines.append(f"{key}: {safe_preview(value)}")
    return lines


def summarize_items(items, max_items: int = 3) -> list[str]:
    """list[dict] 항목(알람 events / 정비 history 등)을 상위 max_items 개만 요약한다.

    [동작]
        - 각 항목 dict 에서 민감 key 를 제외한 스칼라만 'k=v' 로 이어 붙인다.
        - 항목이 max_items 보다 많으면 '...외 N건' 표시를 덧붙인다.
        - 예상치 못한 형태(비 dict)는 safe_preview 로 처리한다.
    """
    if not isinstance(items, list):
        return []
    summary = []
    for item in items[:max_items]:
        if isinstance(item, dict):
            parts = [f"{k}={safe_preview(v, 40)}" for k, v in item.items()
                     if not _is_sensitive_key(k) and not isinstance(v, (list, dict))]
            summary.append(", ".join(parts))
        else:
            summary.append(safe_preview(item))
    if len(items) > max_items:
        summary.append(f"...외 {len(items) - max_items}건")
    return summary


def summarize_documents(documents, max_items: int = 3) -> list[str]:
    """search_manual 의 documents 를 상위 max_items 개만 'title / snippet' 로 요약한다.

    [보안]
        full_text/chroma:document/source_path 등은 애초에 서버가 반환하지 않지만,
        여기서도 민감 key 는 제외하고 title/snippet 중심으로만 보여준다.
    """
    if not isinstance(documents, list):
        return []
    summary = []
    for doc in documents[:max_items]:
        if not isinstance(doc, dict):
            summary.append(safe_preview(doc))
            continue
        title = safe_preview(doc.get("title"), 60)
        snippet = safe_preview(doc.get("snippet"), 90)
        summary.append(f"title: {title} / snippet: {snippet}")
    if len(documents) > max_items:
        summary.append(f"...외 {len(documents) - max_items}건")
    return summary


def _extract_payload(result: dict) -> dict:
    """call_mcp_tool 반환(envelope)에서 sanitize 된 단일 Tool result payload 를 꺼낸다.

    envelope 구조: {status, validation_status, results:[{tool_name, status, result, ...}], ...}
    """
    if not isinstance(result, dict):
        return {}
    results = result.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        inner = results[0].get("result")
        return inner if isinstance(inner, dict) else {}
    return {}


def summarize_tool_result(tool_name: str, result: dict) -> str:
    """Tool 호출 결과(envelope)를 교육용으로 간결하게 요약한 문자열로 만든다.

    [입력]
        tool_name: 호출한 Tool 이름.
        result   : call_mcp_tool 의 반환 dict(envelope).
    [반환]
        여러 줄 요약 문자열. 민감 필드는 포함하지 않는다.

    [동작]
        - 거부(rejected)면 상태와 사유 요약만 보여준다(금지 Tool 확인용).
        - 정상이면 status + data_source/retrieval_source/fallback_used + Tool별 핵심 요약.
        - documents/recent_events/history 같은 중첩 리스트는 상위 3개만.
    """
    if not isinstance(result, dict):
        return f"status: unknown\n(요약할 수 없는 결과 형식)"

    status = result.get("status")
    lines = [f"status: {status}"]

    # 거부된 경우(금지 Tool 등): 사유만 짧게(민감정보 없는 안내 문구).
    if status == "rejected":
        reason = safe_preview(result.get("message"), 120)
        lines.append("reason: forbidden tool" if "금지" in str(result.get("message", "")) else "reason: rejected")
        if reason:
            lines.append(f"note: {reason}")
        return "\n".join(lines)

    payload = _extract_payload(result)

    # 데이터 출처 표시(DB/RAG/mock fallback 구분 — 실습 확인 포인트).
    for key in ("validation_status", "retrieval_source", "data_source", "fallback_used"):
        if key in payload:
            lines.append(f"{key}: {payload.get(key)}")
        elif key == "validation_status" and key in result:
            lines.append(f"{key}: {result.get(key)}")

    # Tool별 중첩 구조 요약(상위 3개).
    if "documents" in payload:
        docs = payload.get("documents") or []
        lines.append(f"documents: {len(docs)}")
        for line in summarize_documents(docs):
            lines.append(f"  - {line}")
    if "recent_events" in payload:
        events = payload.get("recent_events") or []
        lines.append(f"events: {len(events)}")
        for line in summarize_items(events):
            lines.append(f"  - {line}")
    if "history" in payload:
        history = payload.get("history") or []
        lines.append(f"history: {len(history)}")
        for line in summarize_items(history):
            lines.append(f"  - {line}")

    # 그 외 비민감 스칼라 필드(equipment_id/equipment_type/value 등).
    # 위에서 이미 보여준 메타 필드는 skip 하여 중복 출력을 피한다.
    already_shown = ("validation_status", "retrieval_source", "data_source", "fallback_used")
    for line in _safe_scalar_fields(payload, skip_keys=already_shown):
        lines.append(line)

    return "\n".join(lines)
