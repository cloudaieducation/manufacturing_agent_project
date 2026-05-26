"""
Day3 search_manual Tool - beginner friendly simplified version

This file is a simplified educational Tool for the manufacturing AI Agent project.

Main idea:
- Try Day2 RAG search first.
- If RAG search fails or returns no results, use simple CSV keyword search.
- Keep the code small so beginners can read it.
- Do not write log files.
- Do not use real company data or internal system names.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Any, Callable


def get_project_root() -> Path:
    """
    Return the project root based on this file location.

    Expected file location:
    project_root/src/day3/search_manual_tool_YYYYMMDD_HHMMSS.py
    """
    return Path(__file__).resolve().parents[2]


def build_search_query(
    alarm_code: str | None = None,
    symptom: str | None = None,
    user_query: str | None = None,
) -> str:
    """
    Combine alarm_code, symptom, and user_query into one search query.
    Empty values are ignored.
    """
    query_parts: list[str] = []

    for value in [alarm_code, symptom, user_query]:
        if value is not None and str(value).strip() != "":
            query_parts.append(str(value).strip())

    return " ".join(query_parts)


def load_rag_search_function() -> Callable[..., Any] | None:
    """
    Load search_top_k from src.day2.rag_search.

    If the Day2 RAG file is not ready yet, return None.
    In that case search_manual() will use fallback_keyword_search().
    """
    project_root = get_project_root()

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from src.day2.rag_search import search_top_k
    except Exception:
        return None

    return search_top_k


def fallback_keyword_search(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """
    Search chunk_metadata.csv using simple keyword matching.

    Search file priority:
    1. outputs/day2/chunk_metadata.csv
    2. outputs/chunk_metadata.csv
    3. data/chunk_metadata.csv

    Score rule:
    - Split query into words.
    - Count how many query words are included in each CSV row.
    - Return top_k rows by score.
    """
    project_root = get_project_root()

    candidate_paths = [
        project_root / "outputs" / "day2" / "chunk_metadata.csv",
        project_root / "outputs" / "chunk_metadata.csv",
        project_root / "data" / "chunk_metadata.csv",
    ]

    metadata_file: Path | None = None
    for path in candidate_paths:
        if path.exists() and path.is_file():
            metadata_file = path
            break

    if metadata_file is None:
        return []

    normalized_query = str(query or "").strip().lower()
    query_words = re.findall(r"[0-9a-zA-Z가-힣_-]+", normalized_query)
    query_words = [word for word in query_words if len(word) >= 2]

    if len(query_words) == 0:
        return []

    scored_rows: list[dict[str, Any]] = []

    with metadata_file.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            row_text = " ".join(str(value) for value in row.values() if value is not None)
            searchable_text = row_text.lower()

            score = 0
            for word in query_words:
                if word in searchable_text:
                    score += 1

            if score > 0:
                scored_rows.append({
                    "score": score,
                    "row": row,
                })

    scored_rows.sort(key=lambda item: item["score"], reverse=True)

    results: list[dict[str, Any]] = []

    for index, item in enumerate(scored_rows[:top_k], start=1):
        row = item["row"]

        doc_name = next(
            (str(row[key]) for key in ["doc_name", "source", "source_file", "file_name", "document_name"]
             if key in row and row[key] not in [None, ""]),
            "",
        )
        chunk_id = next(
            (str(row[key]) for key in ["chunk_id", "id", "chunk_index"]
             if key in row and row[key] not in [None, ""]),
            "",
        )
        alarm_code = next(
            (str(row[key]) for key in ["alarm_code", "alarm", "code"]
             if key in row and row[key] not in [None, ""]),
            "",
        )
        equipment_type = next(
            (str(row[key]) for key in ["equipment_type", "equipment", "type"]
             if key in row and row[key] not in [None, ""]),
            "",
        )
        symptom = next(
            (str(row[key]) for key in ["symptom", "issue", "problem"]
             if key in row and row[key] not in [None, ""]),
            "",
        )
        action = next(
            (str(row[key]) for key in ["action", "recommended_action", "solution", "조치"]
             if key in row and row[key] not in [None, ""]),
            "",
        )
        text = next(
            (str(row[key]) for key in ["text", "chunk_text", "content", "page_content", "document"]
             if key in row and row[key] not in [None, ""]),
            "",
        )

        if text == "":
            text = " ".join(str(value) for value in row.values() if value is not None)[:1000]

        results.append({
            "rank": index,
            "score": item["score"],
            "doc_name": doc_name,
            "chunk_id": chunk_id,
            "alarm_code": alarm_code,
            "equipment_type": equipment_type,
            "symptom": symptom,
            "action": action,
            "text": text,
        })

    return results


def search_manual(
    alarm_code: str | None = None,
    symptom: str | None = None,
    user_query: str | None = None,
    top_k: int = 3,
) -> dict[str, Any]:
    """
    Search manufacturing manual documents for Agent/MCP Tool use.

    Processing flow:
    1. Build one search query.
    2. Try Day2 RAG search_top_k().
    3. If RAG fails or returns no results, use fallback CSV keyword search.
    4. Return a simple dict.
    """
    top_k = int(top_k)

    query = build_search_query(
        alarm_code=alarm_code,
        symptom=symptom,
        user_query=user_query,
    )

    if query.strip() == "":
        return {
            "query": query,
            "search_mode": "empty_query",
            "top_k": top_k,
            "result_count": 0,
            "results": [],
        }

    search_function = load_rag_search_function()
    results: list[dict[str, Any]] = []
    search_mode = "rag"

    if search_function is not None:
        try:
            raw_results = search_function(query, top_k)

            if raw_results is None:
                results = []
            elif isinstance(raw_results, dict):
                if isinstance(raw_results.get("results"), list):
                    results = raw_results["results"]
                elif isinstance(raw_results.get("data"), dict) and isinstance(raw_results["data"].get("results"), list):
                    results = raw_results["data"]["results"]
                else:
                    results = [raw_results]
            elif isinstance(raw_results, list):
                results = raw_results
            else:
                results = [{"rank": 1, "text": str(raw_results)}]

            results = results[:top_k]
        except Exception:
            results = []

    if len(results) == 0:
        search_mode = "fallback_csv"
        results = fallback_keyword_search(query, top_k)

    return {
        "query": query,
        "search_mode": search_mode,
        "top_k": top_k,
        "result_count": len(results),
        "results": results,
    }


if __name__ == "__main__":
    result = search_manual(
        alarm_code="ALM-TEMP-402",
        symptom="temperature abnormal",
        top_k=3,
    )
    print(result)
