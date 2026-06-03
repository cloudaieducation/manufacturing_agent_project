# -*- coding: utf-8 -*-
"""
Day4 RAG 검색 품질 평가기 (RAG Quality Evaluator) - 교육 버전

이 파일은 제조 AI Agent 교육용 예제입니다.

[이 프로그램이 하는 일 — 한눈에 보기]
- data/day4_rag_evaluation_cases.json 에 적힌 "평가용 질문 목록"을 읽습니다.
- 각 질문을 실제 Chroma Vector DB(2일차에서 만든 검색 DB)에 던져 관련 문서를 검색합니다.
- 검색된 문서가 그 질문에 정말 맞는지 expected_keywords / expected_metadata 기준으로 채점합니다.
- 채점 결과를 PASS / WARN / FAIL 로 판정하고, JSON 결과와 Markdown 보고서로 저장합니다.

[왜 이런 프로그램이 필요한가? — 수업 핵심]
- 4일차에서는 "Agent가 search_manual Tool을 골랐는가?"만 보는 것을 넘어,
  "실제 검색된 근거(Chunk)가 질문에 맞는가?"까지 평가합니다.
- RAG(검색 증강 생성)는 좋은 답을 내려면 "검색 단계의 품질"이 먼저 좋아야 하므로,
  검색 결과 자체를 점검하는 평가 도구가 운영 설계의 한 부분이 됩니다.

[교육 안정성 — fallback 설계]
- 수강생 환경마다 Chroma/Ollama 설치 상태가 다를 수 있습니다.
- 그래서 Chroma 검색이 "기술적으로" 실패하면(설치 안 됨/DB 없음/collection 없음/쿼리 오류 등),
  프로그램을 멈추지 않고 교육용 mock 검색으로 자동 전환(fallback)합니다.
- 단, "Chroma 검색은 성공했는데 결과가 0건"인 경우는 기술적 실패가 아니라 "검색 결과 없음"이므로
  mock fallback 하지 않고, 빈 결과 그대로 평가합니다. (이 구분이 평가의 핵심 포인트입니다.)

주의:
- 실제 사내 데이터나 민감정보를 사용하지 않는 교육용 가상 제조 시나리오입니다.
- API Key, DB 비밀번호, 전체 환경변수 값은 출력하지 않습니다.
- requirements.txt 등 의존성 파일은 수정하지 않습니다. (chromadb 없으면 mock fallback)
- 외부 인터넷 호출은 하지 않습니다.

실행 명령(프로젝트 루트에서):
    uv run python src/day4/rag_quality_evaluator.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# 공통 설정값(경로/Chroma·Ollama 기본값/상수)과 공용 유틸 함수는 config.py로 분리했습니다.
#   - 교육용 리팩토링 2단계: "어떤 값이 어디서 오는지"를 수강생이 볼 수 있도록
#     별표(*) import 대신 사용하는 이름을 명시적으로 가져옵니다.
from src.day4.rag_quality.config import (
    DATA_PATH,
    OUTPUT_DIR,
    RESULT_JSON_PATH,
    REPORT_MD_PATH,
    load_json_file,
    get_rag_eval_config,
    safe_float,
)

# 검색(retrieval) 계층은 retrieval.py로 분리했습니다(교육용 리팩토링 3단계).
#   - 실제 검색이 필요한 곳(evaluate_case)에서 retrieve_chunks()만 가져다 씁니다.
#   - _embed_query_with_ollama / chroma_retrieve_chunks / mock_retrieve_chunks 는
#     retrieval.py 내부 구현이므로 여기서 직접 import 하지 않습니다.
from src.day4.rag_quality.retrieval import retrieve_chunks

# 채점/판정(scoring) 계층은 scoring.py로 분리했습니다(교육용 리팩토링 4단계).
#   - evaluate_case()에서 키워드/메타데이터 채점, PASS/WARN/FAIL 판정, 원인 메모 생성을
#     scoring.py의 함수로 호출합니다.
#   - NONE_EVIDENCE_TYPES / is_out_of_scope_case 는 이제 scoring.py 내부에서만 쓰이므로
#     runner.py에서는 더 이상 import 하지 않습니다.
from src.day4.rag_quality.scoring import (
    score_keywords,
    score_metadata,
    judge_evidence_quality,
    build_missing_reason,
)

# 보고서/출력(reporting) 계층은 reporting.py로 분리했습니다(교육용 리팩토링 6단계).
#   - main()에서 평가가 끝난 payload를 JSON/Markdown으로 저장하고 콘솔 요약을 출력할 때 사용합니다.
from src.day4.rag_quality.reporting import (
    write_json_result,
    write_markdown_report,
    print_summary,
)

# 재정렬(reranking) 계층은 reranking.py로 분리했습니다(교육용 리팩토링 7단계).
#   - evaluate_case()에서 검색 결과를 재정렬하고(top 3 또는 top 5) 최종 근거를 고를 때 사용합니다.
#   - infer_preferred_doc_types 는 reranking.py 내부에서 rerank_chunks 가 호출하는 helper이므로
#     runner.py에서는 직접 import 하지 않습니다.
from src.day4.rag_quality.reranking import (
    get_final_evidence_limit,
    rerank_chunks,
)


# ──────────────────────────────────────────────────────────────────────
# 13. 검색 Chunk preview 생성 함수
# ──────────────────────────────────────────────────────────────────────
def build_chunk_preview(retrieved_chunks: list[dict], max_chars: int = 200) -> list[dict]:
    """
    보고서에 넣을 "검색 결과 미리보기"를 만듭니다.

    [왜 text를 일부만 자르나 — 코드 해석을 돕기 위한 설명]
        - chunk 본문 전체를 보고서에 넣으면 표가 지나치게 길어져 읽기 어렵습니다.
        - 앞부분 일부(max_chars)만 보여 주고, 잘렸으면 "..."으로 더 있다는 것을 표시합니다.
          (원본 데이터를 바꾸는 게 아니라 "보여 주기용 요약"만 만드는 함수입니다.)

    규칙:
        - text는 앞부분 max_chars(기본 200)자만 보여 줍니다(보고서가 길어지지 않게).
        - 입력으로 받은 chunk(=최종 evidence)를 그대로 미리보기로 남깁니다.
          (개수 제한은 호출부에서 final_evidence_limit로 이미 정합니다.
           direct/out_of_scope/low_confidence는 최대 3개, multi_document_evidence는 최대 5개)
        - distance는 safe_float()로 안전하게 변환합니다.
        - reranker가 추가한 original_rank / rerank_score / rerank_reasons도 함께 보여 줍니다.
    """
    preview: list[dict] = []

    # 최종 evidence chunk를 순서대로(rerank된 순서) 미리보기로 만듭니다.
    for chunk in retrieved_chunks:
        text = str(chunk.get("text", "") or "")
        # 앞부분만 자르고, 잘렸으면 "..."을 붙여 더 있다는 걸 표시합니다.
        text_preview = text[:max_chars] + ("..." if len(text) > max_chars else "")

        metadata = chunk.get("metadata", {})
        preview.append(
            {
                "chunk_id": str(chunk.get("chunk_id", "") or ""),
                "text_preview": text_preview,
                "metadata": metadata if isinstance(metadata, dict) else {},
                "distance": safe_float(chunk.get("distance")),
                "source": str(chunk.get("source", "") or ""),
                # reranker 진단 정보(없으면 None / 빈 리스트)
                "original_rank": chunk.get("original_rank"),
                "rerank_score": chunk.get("rerank_score"),
                "rerank_reasons": chunk.get("rerank_reasons", []),
            }
        )

    return preview


# ──────────────────────────────────────────────────────────────────────
# 14. 단일 케이스 평가 함수
# ──────────────────────────────────────────────────────────────────────
def evaluate_case(case: dict, config: dict) -> dict:
    """
    한 개의 평가 케이스(case)에 대해 검색 → 채점 → 판정까지 모두 수행합니다.

    흐름:
        retrieve_chunks(top_k) → rerank_chunks → final_evidence(top 3 또는 5)
        → score_keywords → score_metadata → judge_evidence_quality
        → build_missing_reason → build_chunk_preview → 결과 dict 반환

    개선 포인트(이번 버전):
        - 기존에는 Chroma top_k 결과를 "그대로" 채점했습니다.
        - 이제는 top_k 결과를 rule-based reranker로 재정렬한 뒤,
          케이스 유형에 맞는 최종 evidence 개수(top 3 또는 top 5)만 골라 채점합니다.
        - 이는 정답을 끼워 맞추는 것이 아니라, 질문 의도에 맞는 문서 유형을 우선하고
          검색 결과를 재정렬하는 일반적인 RAG 개선 방식입니다.
    """
    user_query = str(case.get("user_query", "") or "")
    expected_keywords = case.get("expected_keywords", []) or []
    expected_metadata = case.get("expected_metadata", {}) or {}

    # (1) 검색 수행 (Chroma 또는 mock) + 어떤 경로를 썼는지 정보 받기
    #     RAG_TOP_K(예: 10)로 넉넉히 가져온 뒤, 아래에서 재정렬·축소합니다.
    retrieved_chunks, retrieval_info = retrieve_chunks(user_query, config)

    # (2) rule-based reranker로 검색 결과를 질문 의도/메타데이터 기준 재정렬
    reranked_chunks = rerank_chunks(case, retrieved_chunks)

    # (3) 케이스 유형에 맞는 최종 evidence 개수 결정 후, 상위 N개만 최종 근거로 사용
    #     - direct_evidence / out_of_scope / low_confidence : top 3
    #     - multi_document_evidence                         : top 5
    final_evidence_limit = get_final_evidence_limit(case)
    final_evidence_chunks = reranked_chunks[:final_evidence_limit]

    # (4) 최종 evidence 기준으로 키워드/메타데이터 채점
    keyword_score = score_keywords(expected_keywords, final_evidence_chunks)
    metadata_score = score_metadata(expected_metadata, final_evidence_chunks)

    # (5) 종합 판정 (PASS/WARN/FAIL) — 최종 evidence 기준
    evidence_quality = judge_evidence_quality(case, keyword_score, metadata_score, final_evidence_chunks)

    # (6) 원인 메모 + 검색 결과 미리보기 (둘 다 최종 evidence 기준)
    missing_reason = build_missing_reason(
        case, keyword_score, metadata_score, final_evidence_chunks, retrieval_info
    )
    chunks_preview = build_chunk_preview(final_evidence_chunks)

    # (7) 최종 결과 dict 구성 (JSON/보고서에서 그대로 사용)
    return {
        "case_id": str(case.get("case_id", "") or ""),
        "user_query": user_query,
        "difficulty": str(case.get("difficulty", "") or ""),
        "expected_evidence_type": str(case.get("expected_evidence_type", "") or ""),
        # retrieved_chunk_count: 전체 Chroma(또는 mock) 검색 결과 수(기존 의미 유지)
        "retrieved_chunk_count": len(retrieved_chunks),
        # rerank 관련 진단 정보
        "rerank_applied": True,
        "reranked_chunk_count": len(reranked_chunks),
        "final_evidence_count": len(final_evidence_chunks),
        "final_evidence_limit": final_evidence_limit,
        "retrieval_info": retrieval_info,
        "keyword_match": keyword_score,
        "metadata_match": metadata_score,
        "evidence_quality": evidence_quality,
        "missing_reason": missing_reason,
        # 데이터에 있는 개선 힌트를 그대로 전달(수업에서 "이렇게 고치면 된다"를 보여 주기 위함)
        "improvement_hint": str(case.get("expected_improvement_hint", "") or ""),
        # preview는 최종 evidence 기준(멀티 문서 케이스는 최대 5개까지 나올 수 있음)
        "retrieved_chunks_preview": chunks_preview,
    }


# ──────────────────────────────────────────────────────────────────────
# 15. Summary 생성 함수
# ──────────────────────────────────────────────────────────────────────
def build_summary(results: list[dict]) -> dict:
    """
    케이스별 결과(results)를 모아 전체 요약 통계를 만듭니다.

    [왜 집계가 필요한가 — 강의 맥락에서 확인할 포인트]
        - 케이스 하나하나의 판정만 보면 "전체적으로 검색 품질이 좋은가"를 알기 어렵습니다.
        - PASS/WARN/FAIL 분포로 전반적인 품질을, chroma/mock 사용 수와 fallback 수로
          "이번 실행이 실제 Chroma 기준인지, mock에 얼마나 기댔는지"를 한눈에 봅니다.
          (mock 사용/ fallback이 많으면 점수를 실제 검색 품질로 해석하면 안 됩니다.)

    포함:
        총 건수, PASS/WARN/FAIL 수, fallback 수, chroma/mock 사용 수,
        난이도별 건수, fallback 사유 목록
    """
    summary = {
        "total_cases": len(results),
        "pass_count": 0,
        "warn_count": 0,
        "fail_count": 0,
        "fallback_count": 0,
        "chroma_used_count": 0,
        "mock_used_count": 0,
        "difficulty_counts": {},
        "fallback_reasons": [],
    }

    for result in results:
        # 판정 집계
        quality = result.get("evidence_quality")
        if quality == "PASS":
            summary["pass_count"] += 1
        elif quality == "WARN":
            summary["warn_count"] += 1
        elif quality == "FAIL":
            summary["fail_count"] += 1

        # 검색 경로/ fallback 집계
        retrieval_info = result.get("retrieval_info", {})
        used_source = retrieval_info.get("used_source")
        if used_source == "chroma":
            summary["chroma_used_count"] += 1
        elif used_source == "mock":
            summary["mock_used_count"] += 1

        if retrieval_info.get("fallback_used"):
            summary["fallback_count"] += 1
            reason = retrieval_info.get("fallback_reason")
            if reason:
                # 보고서에서 "어떤 케이스가 왜 fallback 됐는지" 볼 수 있게 case_id와 함께 기록
                summary["fallback_reasons"].append(
                    {"case_id": result.get("case_id", ""), "reason": reason}
                )

        # 난이도별 건수 집계
        difficulty = result.get("difficulty", "") or "unknown"
        summary["difficulty_counts"][difficulty] = summary["difficulty_counts"].get(difficulty, 0) + 1

    return summary


# ──────────────────────────────────────────────────────────────────────
# 19. main 함수
# ──────────────────────────────────────────────────────────────────────
def main() -> None:
    """
    전체 실행 진입점입니다. 이 함수가 "실행 흐름"을 한눈에 보여 주는 자리이며,
    세부 단계(검색/재정렬/채점/판정/저장)는 각 모듈 함수에 위임되어 있습니다.

    순서:
        설정 읽기 → 케이스 읽기 → 케이스별 평가 → 요약 → JSON/MD 저장 → 콘솔 요약 출력
    """
    # (1) 환경 변수 기반 실행 설정(mode/top_k/Chroma 경로 등)을 읽습니다.
    config = get_rag_eval_config()
    # (2) 평가할 케이스 목록을 읽습니다. 파일이 없거나 비어 있으면 안내 후 안전하게 종료합니다.
    cases = load_json_file(DATA_PATH)
    if not cases:
        print("평가할 RAG 케이스가 없습니다.")
        return

    # (3) 모든 케이스를 평가합니다(각 케이스는 독립적으로 검색·재정렬·채점·판정).
    results = [evaluate_case(case, config) for case in cases]
    # (4) 케이스별 결과를 모아 전체 요약 통계를 만듭니다.
    summary = build_summary(results)

    # (5) 저장/보고에 사용할 전체 결과 묶음입니다.
    #     config(이번 실행 설정) + summary(전체 요약) + results(케이스별 상세)를 한 dict로 모읍니다.
    payload = {
        "config": config,
        "summary": summary,
        "results": results,
    }

    # (6) 같은 결과를 JSON(기계용)과 Markdown(사람용)으로 저장하고, 콘솔에 요약을 출력합니다.
    write_json_result(payload)
    write_markdown_report(payload)
    print_summary(config, summary)


# 이 파일을 직접 실행했을 때만 main()이 동작합니다(다른 파일에서 import 시에는 실행 안 됨).
if __name__ == "__main__":
    main()
