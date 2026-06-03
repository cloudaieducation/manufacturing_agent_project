# -*- coding: utf-8 -*-
"""
Day4 RAG 검색 품질 평가기 패키지 (rag_quality)

[이 패키지가 무엇인가 — 교육용 설명]
원래 이 평가기는 하나의 긴 파일(rag_quality_evaluator.py)에 모든 코드가 들어 있었습니다.
코드를 처음 읽는 수강생이 "검색 → 재정렬 → 채점 → 판정 → 보고서" 흐름을 따라가기 쉽도록,
역할별로 모듈을 나눈 구조가 이 패키지입니다.
(즉, "하나의 긴 평가기 파일을 역할별 모듈로 나눈 구조"입니다.)

[모듈별 역할 — 학습 흐름을 따라가기 위한 안내]
- config.py    : 경로/환경 변수/Chroma·Ollama 기본값 같은 "실행 설정"과,
                 여러 모듈이 함께 쓰는 작은 공용 유틸(normalize_value / safe_float / load_json_file 등).
                 import 그래프의 가장 아래 계층이라 다른 내부 모듈을 import 하지 않습니다.
- retrieval.py : 질문을 받아 관련 문서 chunk를 찾아오는 "검색" 단계.
                 실제 Chroma 검색, Ollama 임베딩, 환경이 없을 때의 교육용 mock 검색을 담당합니다.
- reranking.py : 검색 결과를 질문 의도/메타데이터 기준으로 다시 정렬하고,
                 케이스 유형에 맞는 최종 근거 개수를 정하는 "재정렬(rerank)" 단계.
                 (운영용이 아니라 평가용 진단 reranker라는 점이 핵심입니다.)
- scoring.py   : 검색된 근거가 질문에 맞는지 채점하고 PASS/WARN/FAIL을 판정하는 "채점/판정" 단계.
- reporting.py : 결과를 JSON으로 저장하고 Markdown 보고서를 만들며 콘솔 요약을 출력하는 "보고서" 단계.
- runner.py    : 위 단계들을 순서대로 이어 붙이는 "실행 흐름". 한 케이스를 평가하는 evaluate_case(),
                 전체 통계를 만드는 build_summary(), 진입점 main()이 여기에 있습니다.

[실행 진입점]
- 전체 실행 흐름은 runner.py의 main()이 담당합니다.
- 기존 실행 명령(uv run python src/day4/rag_quality_evaluator.py)을 유지하기 위해,
  루트의 rag_quality_evaluator.py가 호환용 진입점으로 이 main()을 호출합니다.
"""
