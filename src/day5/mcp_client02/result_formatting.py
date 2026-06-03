# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 - Result Formatting (결과 요약/민감정보 차단)

[이 파일의 역할]
서버 Tool 결과(dict)를 화면에 보여주거나 State 에 저장할 때, 전체를 그대로 쓰지 않고
'민감정보 없는 요약 구조'로 정리하는 보조 함수 모음입니다.

[mcp_client01 과의 관계]
mcp_client01 의 result_formatting 아이디어를 참고했지만, 단계별 독립성을 위해 mcp_client02
내부에 별도 파일로 둡니다(과도한 공용화 대신 명확성 우선). mcp_client01 파일은 수정하지 않습니다.

[보안 원칙]
- 민감 key(_SENSITIVE_MARKERS)는 어떤 경우에도 출력/저장하지 않는다.
- 문서 전문/내부 경로/접속 비밀값/민감 컬럼은 요약 대상에서 제외한다.
- 긴 list(documents/events/history)는 상위 max_items 개만 남긴다.
- 예상치 못한 구조가 들어와도 오류 없이 처리한다.
"""
from __future__ import annotations


# 출력/저장에서 제외할 민감 key 마커(부분 일치, 소문자 비교).
_SENSITIVE_MARKERS = (
    "password", "token", "secret", "connection", "dsn",
    "source_path", "file_path", "internal_url",
    "full_text", "chroma:document", "raw_metadata",
    "message", "operator_note", "technician_note", "lot_id",
    "owner_team", "location",
)


def _is_sensitive_key(key) -> bool:
    """key 이름에 민감 마커가 포함되면 True(출력/저장 제외 대상)."""
    name = str(key).lower()
    return any(marker in name for marker in _SENSITIVE_MARKERS)


def safe_preview(value, max_chars: int = 120) -> str:
    """문자열 값을 공백 정리 후 max_chars 로 잘라 미리보기로 만든다(긴 본문 노출 방지)."""
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:max_chars] + "..." if len(text) > max_chars else text


def summarize_items(items, max_items: int = 3) -> list:
    """list[dict](알람 events / 정비 history 등)을 상위 max_items 개만 'k=v' 로 요약한다."""
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


def summarize_documents(documents, max_items: int = 3) -> list:
    """search_manual documents 를 상위 max_items 개만 'title / snippet' 로 요약한다."""
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


def compact_payload(payload: dict, max_items: int = 3) -> dict:
    """Tool 결과 payload 를 '민감 key 제외 + 긴 list 상위 N개'로 압축한 dict 로 만든다.

    [목적]
        Agent 결과를 State 에 저장하거나 화면에 보여줄 때 전체 dict 를 그대로 쓰지 않도록,
        안전하고 작은 요약 구조를 만든다. 서버가 이미 sanitize 하지만 client 에서도 한 번 더 거른다.
    [동작]
        - 스칼라(비민감): 그대로 보존.
        - list: 항목이 dict 면 민감 key 제외, 상위 max_items 개만. 길면 '_truncated' 표시.
        - dict: 민감 key 제외 후 재귀 압축.
        - 민감 key: 제거.
    """
    if not isinstance(payload, dict):
        return {}
    safe = {}
    for key, value in payload.items():
        if _is_sensitive_key(key):
            continue
        if isinstance(value, list):
            items = []
            for item in value[:max_items]:
                if isinstance(item, dict):
                    items.append({k: v for k, v in item.items()
                                  if not _is_sensitive_key(k) and not isinstance(v, (list, dict))})
                elif not isinstance(item, (list, dict)):
                    items.append(item)
            safe[key] = items
            if len(value) > max_items:
                safe[key + "_truncated"] = len(value) - max_items
        elif isinstance(value, dict):
            safe[key] = compact_payload(value, max_items)
        else:
            safe[key] = value
    return safe


def extract_payload(envelope: dict) -> dict:
    """call_mcp_tool envelope 에서 sanitize 된 단일 Tool result payload 를 꺼낸다."""
    if not isinstance(envelope, dict):
        return {}
    # envelope 구조: {status, ..., results: [{tool_name, status, result: {...}}, ...]}
    # 이 단계는 Tool 을 한 번에 하나만 호출하므로 results[0].result(단일 payload)만 꺼낸다.
    results = envelope.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        inner = results[0].get("result")
        return inner if isinstance(inner, dict) else {}
    return {}
