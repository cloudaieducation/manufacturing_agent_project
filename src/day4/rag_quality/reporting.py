# -*- coding: utf-8 -*-
"""
Day4 RAG 검색 품질 평가기 - 보고서/출력 계층 모듈 (reporting)

이 파일은 평가 결과를 "저장하고 사람에게 보여주는" 단계만 모아 둡니다.
- JSON 결과 저장(write_json_result)
- Markdown 보고서 저장(write_markdown_report)
- 콘솔 요약 출력(print_summary)

[왜 JSON과 Markdown을 둘 다 저장하나 — 교육용 설명]
- JSON: 다른 프로그램/스크립트가 다시 읽어 비교·집계하기 좋은 "기계가 다루는" 형식입니다.
        (회귀 검증 때 결과를 그대로 비교하는 데도 씁니다.)
- Markdown: 사람이 표와 문장으로 한눈에 읽기 좋은 형식입니다. 수업 중 결과를 함께
        리뷰하는 자료로 사용합니다. 같은 결과를 용도에 따라 두 형태로 남기는 셈입니다.

교육용 리팩토링 6단계에서 runner.py로부터 분리했습니다.
- 함수 내부 로직은 분리 전과 한 글자도 다르지 않습니다(안전한 위치 이동).
- 검색(retrieval) / 재정렬(rerank) / 채점(scoring) / 평가 흐름(evaluate_case)은
  이 파일에 들어오지 않습니다. 여기서는 "이미 만들어진 결과"를 저장/출력만 합니다.

import 계층 규칙(중요):
- reporting.py는 config.py만 import 합니다(runner / retrieval / scoring 을 import 하지 않습니다).
  → config 아래 계층을 바라보는 단방향 구조라 순환 import가 생기지 않습니다.
"""

from __future__ import annotations

import json

# 저장 경로/출력 경로 상수는 config.py에서 명시적으로 가져옵니다(별표 import 금지).
from src.day4.rag_quality.config import (
    DATA_PATH,
    OUTPUT_DIR,
    RESULT_JSON_PATH,
    REPORT_MD_PATH,
)

# ──────────────────────────────────────────────────────────────────────
# 16. JSON 결과 저장 함수
# ──────────────────────────────────────────────────────────────────────
def write_json_result(payload: dict) -> None:
    """
    평가 결과 전체(payload)를 JSON 파일로 저장합니다.

    저장 경로: outputs/day4/rag_quality_evaluation_result.json
    규칙:
        - ensure_ascii=False : 한글이 \\uXXXX로 깨지지 않고 그대로 저장되게 함
        - indent=2           : 사람이 읽기 좋게 들여쓰기
        - 폴더가 없으면 자동 생성
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ──────────────────────────────────────────────────────────────────────
# 17. Markdown 보고서 저장 함수
# ──────────────────────────────────────────────────────────────────────
def write_markdown_report(payload: dict) -> None:
    """
    평가 결과를 사람이 읽기 좋은 Markdown 보고서로 저장합니다.

    저장 경로: outputs/day4/rag_quality_evaluation_report.md

    구성: 1.요약 / 2.Fallback 사유 / 3.케이스별 결과(+검색 미리보기 표) / 4.수업 노트
    (이 프로그램은 새 템플릿 파일을 만들지 않기 위해, 보고서 문자열을 코드에서 직접 조립합니다.)
    """
    config = payload.get("config", {})
    summary = payload.get("summary", {})
    results = payload.get("results", [])

    def escape_cell(value) -> str:
        """표(table) 칸이 깨지지 않도록 줄바꿈과 | 문자를 안전하게 바꿉니다.

        Markdown 표는 '|'로 칸을 나누고 줄바꿈으로 행을 나눕니다. 따라서 셀 값 안에
        '|'나 줄바꿈이 들어가면 표 구조가 깨집니다. 여기서 '|'는 '/'로, 줄바꿈은 공백으로
        바꿔 표가 깨지지 않게 합니다. (값 자체를 바꾸는 게 아니라 표 표시용으로만 가공)
        """
        return str(value if value is not None else "").replace("\n", " ").replace("|", "/")

    # 보고서는 lines 리스트에 한 줄씩 쌓은 뒤 마지막에 "\n"으로 이어 붙여 저장합니다.
    # 아래는 섹션 단위(제목 → 1.요약 → 2.Fallback → 3.케이스별 결과 → 4.수업 노트)로 채워집니다.
    lines: list[str] = []

    # ── 제목 ─────────────────────────────────────────────
    lines.append("# Day4 RAG Quality Evaluation Report")
    lines.append("")

    # ── 1. Summary ───────────────────────────────────────
    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"- Mode: {config.get('mode', '')}")
    lines.append(f"- Chroma Persist Dir: {config.get('chroma_persist_dir', '')}")
    lines.append(f"- Collection: {config.get('collection_name', '')}")
    lines.append(f"- Top-K: {config.get('top_k', '')}")
    lines.append(f"- Total cases: {summary.get('total_cases', 0)}")
    lines.append(f"- PASS: {summary.get('pass_count', 0)}")
    lines.append(f"- WARN: {summary.get('warn_count', 0)}")
    lines.append(f"- FAIL: {summary.get('fail_count', 0)}")
    lines.append(f"- Chroma Used: {summary.get('chroma_used_count', 0)}")
    lines.append(f"- Mock Used: {summary.get('mock_used_count', 0)}")
    lines.append(f"- Fallback Count: {summary.get('fallback_count', 0)}")
    lines.append("")

    # ── 2. Fallback Reasons ──────────────────────────────
    #   - 어떤 케이스가 왜 mock fallback으로 넘어갔는지 모아 보여 줍니다.
    #   - fallback이 한 건도 없으면 "Fallback was not used." 한 줄만 남겨 표를 비우지 않습니다.
    #   - 이 정보가 있어야 "이 점수가 실제 Chroma 검색 결과인지"를 의심해 볼 수 있습니다.
    lines.append("## 2. Fallback Reasons")
    lines.append("")
    fallback_reasons = summary.get("fallback_reasons", [])
    if not fallback_reasons:
        lines.append("- Fallback was not used.")
    else:
        for item in fallback_reasons:
            lines.append(f"- [{item.get('case_id', '')}] {item.get('reason', '')}")
    lines.append("")

    # ── 3. Case Results ──────────────────────────────────
    lines.append("## 3. Case Results")
    lines.append("")
    for result in results:
        keyword_match = result.get("keyword_match", {})
        metadata_match = result.get("metadata_match", {})
        retrieval_info = result.get("retrieval_info", {})

        lines.append(f"### {result.get('case_id', '')}")
        lines.append("")
        lines.append(f"- Query: {result.get('user_query', '')}")
        lines.append(f"- Difficulty: {result.get('difficulty', '')}")
        lines.append(f"- Expected Evidence Type: {result.get('expected_evidence_type', '')}")
        lines.append(f"- Retrieval Source: {retrieval_info.get('used_source', '')}")
        lines.append(f"- Fallback Used: {retrieval_info.get('fallback_used', False)}")
        lines.append(f"- Fallback Reason: {retrieval_info.get('fallback_reason', '')}")
        lines.append(f"- Retrieved Chunk Count: {result.get('retrieved_chunk_count', 0)}")
        # rerank 관련 진단 정보(이번 버전에서 추가)
        lines.append(f"- Rerank Applied: {result.get('rerank_applied', False)}")
        lines.append(f"- Reranked Chunk Count: {result.get('reranked_chunk_count', 0)}")
        lines.append(f"- Final Evidence Count: {result.get('final_evidence_count', 0)}")
        lines.append(f"- Final Evidence Limit: {result.get('final_evidence_limit', 0)}")
        lines.append(f"- Evidence Quality: {result.get('evidence_quality', '')}")
        # 키워드/메타데이터 매칭은 "맞춘 수/전체 (비율)" 형태로 한눈에 보여 줍니다.
        lines.append(
            f"- Keyword Match: {keyword_match.get('score', 0)}/{keyword_match.get('total', 0)} "
            f"(ratio {keyword_match.get('ratio', 0.0)})"
        )
        lines.append(
            f"- Metadata Match: {metadata_match.get('score', 0)}/{metadata_match.get('total', 0)} "
            f"(ratio {metadata_match.get('ratio', 0.0)})"
        )
        # 원인 메모는 여러 개일 수 있어 " / "로 이어 붙입니다.
        missing_reason = result.get("missing_reason", [])
        lines.append(f"- Missing Reason: {' / '.join(missing_reason) if missing_reason else '없음'}")
        lines.append(f"- Improvement Hint: {result.get('improvement_hint', '')}")
        lines.append("")

        # 검색 결과 미리보기 표
        #   - 최종 evidence로 선택된 chunk를 표로 보여 줍니다.
        #   - original_rank(원래 순위) / rerank_score / rerank_reasons 를 함께 노출해,
        #     "왜 이 근거가 위로 올라왔는지"를 수업에서 눈으로 따라갈 수 있게 합니다.
        #   - distance·rank·score 가 없을 때는 "-"로 표시해 표 칸을 비우지 않습니다.
        lines.append("#### Retrieved Chunks Preview")
        lines.append("")
        lines.append(
            "| Chunk ID | Source | Original Rank | Distance | Rerank Score | "
            "Rerank Reasons | Metadata | Text Preview |"
        )
        lines.append("|---|---|---:|---:|---:|---|---|---|")
        previews = result.get("retrieved_chunks_preview", [])
        if not previews:
            # 검색 결과가 없을 때도 표 구조는 유지하고 안내 행을 한 줄 넣습니다.
            lines.append("| (없음) | - | - | - | - | - | - | 검색 결과가 없습니다. |")
        else:
            for preview in previews:
                distance = preview.get("distance")
                distance_text = "-" if distance is None else f"{distance:.4f}"
                metadata_text = escape_cell(json.dumps(preview.get("metadata", {}), ensure_ascii=False))
                # rerank 진단 정보(없으면 "-"로 표시)
                original_rank = preview.get("original_rank")
                original_rank_text = "-" if original_rank is None else str(original_rank)
                rerank_score = preview.get("rerank_score")
                rerank_score_text = "-" if rerank_score is None else str(rerank_score)
                rerank_reasons = preview.get("rerank_reasons", []) or []
                rerank_reasons_text = escape_cell(", ".join(str(r) for r in rerank_reasons)) or "-"
                lines.append(
                    f"| {escape_cell(preview.get('chunk_id', ''))} "
                    f"| {escape_cell(preview.get('source', ''))} "
                    f"| {original_rank_text} "
                    f"| {distance_text} "
                    f"| {rerank_score_text} "
                    f"| {rerank_reasons_text} "
                    f"| {metadata_text} "
                    f"| {escape_cell(preview.get('text_preview', ''))} |"
                )
        lines.append("")

    # ── 4. Teaching Notes ────────────────────────────────
    lines.append("## 4. Teaching Notes")
    lines.append("")
    lines.append("- RAG 평가는 search_manual Tool 선택 여부만 보는 것이 아니다.")
    lines.append("- 실제 검색된 Chunk가 질문에 맞는지 확인해야 한다.")
    lines.append("- Metadata가 부족하면 검색 품질이 흔들릴 수 있다.")
    lines.append("- Chroma 검색 실패 시 fallback 전략도 운영 설계의 일부다.")
    lines.append("- Chroma 검색 성공 후 검색 결과가 없는 경우는 실제 검색 실패로 평가해야 한다.")
    lines.append("- 검색 실패 원인을 Chunk, Metadata, Query Rewrite, Top-K, Reranker 관점으로 나누어 봐야 한다.")
    lines.append("- 이 평가기는 top_k를 넉넉히 검색한 뒤 rule-based reranker로 재정렬하고, "
                 "케이스 유형에 따라 final evidence(top 3 또는 top 5)만 채점한다.")
    lines.append("- 단, 이 reranker는 평가용 진단 도구이며, 운영 search_manual Tool은 "
                 "expected_keywords 같은 정답 라벨 대신 query analysis/entity/metadata filter를 사용해야 한다.")
    lines.append("- out_of_scope 케이스는 유사 문서가 검색되어도 직접 근거가 없으면 PASS로 보고, "
                 "유사 문서를 확정 근거로 쓰지 않는지를 평가한다.")
    lines.append("")

    # 폴더 생성 후 UTF-8로 저장합니다.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# 18. 콘솔 출력 함수
# ──────────────────────────────────────────────────────────────────────
def print_summary(config: dict, summary: dict) -> None:
    """
    실행이 끝난 뒤 핵심 결과를 콘솔에서 빠르게 확인할 수 있도록 요약만 출력합니다.

    (자세한 케이스별 결과는 Markdown 보고서에서 보고, 여기서는 실행 직후 한눈에 보는 용도입니다.)
    fallback이 한 건이라도 있었다면, 보고서를 확인하라는 경고도 함께 출력합니다.
    """
    # 아래 print 블록은 "설정 + 입출력 경로 + 판정 집계"를 콘솔에 한 번에 보여 주는 요약 출력입니다.
    print("[Day4 RAG Quality Evaluator]")
    print(f"Mode: {config.get('mode', '')}")
    print(f"Chroma DB: {config.get('chroma_persist_dir', '')}")
    print(f"Collection: {config.get('collection_name', '')}")
    print(f"Top-K: {config.get('top_k', '')}")
    print("")
    print(f"Input: {DATA_PATH}")
    print(f"Output JSON: {RESULT_JSON_PATH}")
    print(f"Output Report: {REPORT_MD_PATH}")
    print("")
    print(f"Total cases: {summary.get('total_cases', 0)}")
    print(f"PASS: {summary.get('pass_count', 0)}")
    print(f"WARN: {summary.get('warn_count', 0)}")
    print(f"FAIL: {summary.get('fail_count', 0)}")
    print(f"Fallback: {summary.get('fallback_count', 0)}")

    # mock fallback이 있었다면, 결과를 100% 신뢰하기 전에 보고서를 보라고 안내합니다.
    if summary.get("fallback_count", 0) > 0:
        print("")
        print("[WARNING] Some cases used mock fallback. Check report for details.")
