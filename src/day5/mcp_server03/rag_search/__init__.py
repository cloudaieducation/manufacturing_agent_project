# -*- coding: utf-8 -*-
"""
Day5 mcp_server03 - rag_search 패키지

[이 패키지가 무엇인가]
Day5 `search_manual` 운영 검색을 위해, Day4 `rag_quality` 패키지에서 '검색에 필요한 부분만'
복사해 정리한 패키지입니다. Day4 원본은 수정하지 않으며, 평가용(scoring/reporting/runner)은
복사하지 않았습니다.

[구성]
- config.py    : Chroma/Ollama 기본값 + Day5 운영 검색 설정(top_k=10, get_rag_search_config).
- retrieval.py : 질문 → 관련 chunk 검색(Chroma 우선, 실패 시 mock fallback).
                 운영형 진입점 retrieve_chunks(user_query, config) 를 그대로 사용합니다.
- reranking.py : 운영형 재정렬(정답 라벨 미사용). rerank_chunks_for_manual_search 만 제공합니다.

[중요 원칙]
- ChromaDB / metadata DB(vector_db/chroma_db)는 read-only 로만 사용합니다.
- 평가 정답 라벨(expected_keywords/expected_metadata/expected_tools)에 의존하지 않습니다.
- 실제 MCP 응답 변환/민감 필드 제거는 상위 계층(rag_quality_adapter.py / security.py)이 담당합니다.
"""
