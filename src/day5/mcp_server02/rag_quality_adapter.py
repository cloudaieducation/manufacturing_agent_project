# -*- coding: utf-8 -*-
"""
Day5 mcp_server02 - RAG Quality Adapter (search_manual ↔ rag_search 연결 계층)

[이 모듈의 역할]
`manual_search.py`(search_manual interface)와 Day5 `rag_search`(검색/재정렬)를 잇는 adapter 입니다.
Day4 `rag_quality` 를 '직접' import 하지 않고, Day5 로 복사·정리한 `rag_search` 만 사용합니다.

[전체 흐름에서의 위치]
    tool_executor → manual_search.search_manual()
        ↓ (RAG 검색 위임)
    [rag_quality_adapter.search_manual_documents]
        ↓
    rag_search.retrieval.retrieve_chunks(query, config)   ← vector_db/chroma_db (read-only)
        ↓
    rag_search.reranking.rerank_chunks_for_manual_search   ← 운영형(정답 라벨 미사용)
        ↓
    MCP search_manual 응답용으로 변환(snippet/ metadata whitelist) → security 가 2차 제한

[핵심 원칙]
1. top_k 는 10 으로 명시한다(Day4 기본값 3 에 의존하지 않음).
2. ChromaDB / metadata DB 는 read-only. 수정/마이그레이션하지 않는다.
3. 다음 필드는 절대 MCP 응답에 넣지 않는다:
   chroma:document(=문서 전문), full_text, raw_text, source_path, file_path, path,
   internal_url, author, owner, created_by, updated_by, distance 원문.
4. score 는 선택 필드다. 명확한 기준(similarity/operational rerank)이 없으면 생략한다.
   (현재는 문서가 적어 title/doc_type/snippet 이 더 유용하므로 기본 미반환.)

[Day4 rerank_chunks(case, chunks) 미사용]
평가용 reranker 는 정답 라벨(expected_*)에 의존하므로 쓰지 않는다.
운영형 rag_search.reranking.rerank_chunks_for_manual_search 만 사용한다.
"""
from day5.mcp_server02.rag_search.config import get_rag_search_config, DEFAULT_TOP_K
from day5.mcp_server02.rag_search.retrieval import retrieve_chunks
from day5.mcp_server02.rag_search.reranking import rerank_chunks_for_manual_search


# MCP 응답 metadata 에 남겨도 되는 key 화이트리스트(읽기 전용 mapping).
# [주의] 실제 ChromaDB metadata 에서 이 key 들만 통과시키고 나머지는 버린다.
_ALLOWED_METADATA_KEYS = (
    "doc_name",
    "section_title",
    "alarm_code",
    "equipment_type",
    "process_name",
    "equipment_id",
    "keywords",
    "symptom",
    "quality_metric",
    "action",
    "chunk_id",
)

# snippet 최대 길이(문서 전문 대신 짧은 발췌만 노출).
_SNIPPET_MAX = 300


def build_safe_snippet(text, max_chars=_SNIPPET_MAX):
    """문서 본문(text)을 안전한 snippet 으로 축약한다(전문 미반환).

    [동작]
        - 공백/줄바꿈을 한 칸으로 정리한다.
        - max_chars(기본 300)자까지만 남기고, 잘렸으면 "..." 을 붙인다.
        - text 가 없거나 문자열이 아니면 빈 문자열을 돌려준다.

    [왜 필요한가]
        full_text / chroma:document 를 그대로 노출하면 안 되므로, 항상 짧은 발췌만 만든다.
    """
    if not isinstance(text, str) or not text:
        return ""
    # 연속 공백/줄바꿈을 한 칸으로 정리(보기 좋고 길이 예측 가능)
    collapsed = " ".join(text.split())
    if len(collapsed) > max_chars:
        return collapsed[:max_chars] + "..."
    return collapsed


def sanitize_rag_metadata(metadata):
    """chunk metadata 에서 허용 key 만 남긴다(read-only whitelist mapping).

    [입력] metadata: chunk 의 metadata dict(아니면 빈 dict 취급).
    [반환] _ALLOWED_METADATA_KEYS 에 있는 key 만 담은 dict.

    [차단 대상(자동 제거)]
        chroma:document(문서 전문), full_text, raw_text, source_path, file_path, path,
        internal_url, author, owner, created_by, updated_by 등 — 화이트리스트에 없으므로 제거됨.

    [주의] metadata DB 자체는 수정하지 않는다. 읽어 온 값을 통과/제거만 한다.
    """
    if not isinstance(metadata, dict):
        return {}
    safe = {}
    for key in _ALLOWED_METADATA_KEYS:
        if key in metadata and metadata[key] is not None:
            safe[key] = metadata[key]
    return safe


def convert_chunk_to_manual_document(chunk):
    """rag_search 검색 결과 chunk 한 개를 MCP search_manual documents 항목으로 변환한다.

    [매핑]
        chunk_id        → doc_id
        section_title   → title (없으면 doc_name, 그것도 없으면 기본 문구)
        text/문서 내용   → snippet (build_safe_snippet 으로 축약, 전문 미반환)
        metadata        → sanitize_rag_metadata (허용 key 만)

    [반환하지 않는 것]
        chroma:document(문서 전문), distance 원문, full_text/source_path 등.
        score 는 명확한 기준이 없으면 생략한다(현재 기본 미반환).

    [입력] chunk: {chunk_id, text, metadata, distance, source, (운영 rerank 진단 필드)}.
    [반환] {doc_id, title, snippet, metadata} dict.
    """
    if not isinstance(chunk, dict):
        return {"doc_id": "", "title": "관련 문서(형식 오류)", "snippet": "", "metadata": {}}

    metadata = chunk.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}

    doc_id = str(chunk.get("chunk_id", "") or "")
    title = str(metadata.get("section_title") or metadata.get("doc_name") or "관련 문서(제목 없음)")
    snippet = build_safe_snippet(chunk.get("text", ""))
    safe_metadata = sanitize_rag_metadata(metadata)

    return {
        "doc_id": doc_id,
        "title": title,
        "snippet": snippet,
        "metadata": safe_metadata,
        # score 는 의도적으로 생략한다(명확한 similarity/score 기준 부재 + 문서 수가 적음).
        # 추후 명확한 기준이 생기면 여기서 optional 로 추가한다.
    }


def retrieve_with_day5_rag_search(query, top_k=DEFAULT_TOP_K):
    """Day5 rag_search 검색 계층을 호출한다(top_k=10 명시).

    [입력]
        query: 검색 질의문.
        top_k: 검색해 올 chunk 수(기본 10). Day4 기본값 3 에 의존하지 않는다.
    [반환]
        (chunks, retrieval_info) — retrieve_chunks 의 반환을 그대로 전달.
        오류 시 ([], {"used_source": "error", "fallback_used": True}) 로 안전 처리.

    [주의]
        ChromaDB 미가용/Ollama 미실행 등은 retrieve_chunks 내부에서 mock 으로 자동 fallback 된다
        (예외가 아니라 retrieval_info 로 표시됨). 여기서의 except 는 예기치 못한 오류 대비용이다.
    """
    config = get_rag_search_config(top_k=top_k)  # top_k=10 명시
    try:
        chunks, info = retrieve_chunks(query, config)
        return chunks, (info if isinstance(info, dict) else {})
    except Exception:
        # 경로/사유 원문을 노출하지 않고 안전한 최소 정보만 돌려준다.
        return [], {"used_source": "error", "fallback_used": True}


def rerank_for_manual_search(query, chunks, alarm_code=None, equipment_type=None):
    """운영형 재정렬을 적용한다(평가용 rerank_chunks(case,…) 미사용).

    [동작]
        rag_search.reranking.rerank_chunks_for_manual_search 를 호출한다.
        실패하면 retrieve 결과(chunks) 순서를 그대로 유지한다(검색이 끊기지 않게).
    """
    try:
        return rerank_chunks_for_manual_search(
            query, chunks, alarm_code=alarm_code, equipment_type=equipment_type
        )
    except Exception:
        return chunks if isinstance(chunks, list) else []


def search_manual_documents(query, alarm_code=None, equipment_type=None, top_k=DEFAULT_TOP_K):
    """search_manual 운영 검색의 adapter 진입점.

    [입력]
        query         : 검색 질의문(필수).
        alarm_code    : 알람 코드(선택). 운영형 rerank 가점 + 응답 matched_alarm_code.
        equipment_type: 설비 유형(선택). 운영형 rerank 가점.
        top_k         : 검색 chunk 수(기본 10).
    [반환]
        {
          "query": query,
          "matched_alarm_code": alarm_code,
          "documents": [ {doc_id, title, snippet, metadata}, ... ],
          "retrieval_source": "chroma" | "mock" | "error",
          "fallback_used": bool
        }
        검색 결과가 10건보다 적으면 실제 반환 가능한 만큼만 documents 에 담는다.

    [보안]
        - 문서 전문/distance 원문/내부 경로는 담지 않는다(convert/sanitize 가 제거).
        - retrieval_info 의 persist_dir/fallback_reason(경로·사유 원문)은 응답에 넣지 않는다.
          (used_source/fallback_used 같은 비민감 요약만 노출.)
    """
    chunks, info = retrieve_with_day5_rag_search(query, top_k=top_k)
    reranked = rerank_for_manual_search(
        query, chunks, alarm_code=alarm_code, equipment_type=equipment_type
    )

    documents = []
    if isinstance(reranked, list):
        for chunk in reranked:
            documents.append(convert_chunk_to_manual_document(chunk))

    return {
        "query": query,
        "matched_alarm_code": alarm_code,
        "documents": documents,
        # 경로/사유 원문이 아닌 비민감 요약만 노출한다.
        "retrieval_source": info.get("used_source") if isinstance(info, dict) else None,
        "fallback_used": bool(info.get("fallback_used")) if isinstance(info, dict) else False,
    }
