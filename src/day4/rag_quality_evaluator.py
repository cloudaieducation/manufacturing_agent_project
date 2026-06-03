# -*- coding: utf-8 -*-
"""
Day4 RAG 검색 품질 평가기 - 호환용 실행 진입점(entry point)

[이 파일의 역할 — 교육용 설명]
- 이 파일에는 평가 로직이 들어 있지 않습니다. "기존 실행 명령을 그대로 쓰기 위한 얇은 진입점"입니다.
- 실제 실행 흐름(설정 읽기 → 검색 → 재정렬 → 채점 → 판정 → 보고서 저장)은
  src/day4/rag_quality/runner.py 의 main() 이 담당합니다.
- 코드를 처음 읽는 수강생은 이 파일에서 "어디서 실제 코드가 시작되는지(runner.main)"만 확인하고,
  세부 흐름은 runner.py 로 넘어가면 됩니다.

실행(프로젝트 루트에서):
    uv run python src/day4/rag_quality_evaluator.py
"""

# [왜 sys.path 에 프로젝트 루트를 넣는가 — 코드 해석을 돕기 위한 설명]
#   - 이 파일을 직접 실행하면 파이썬은 sys.path[0] 을 이 파일이 있는 src/day4 로 잡습니다.
#     그러면 "src" 라는 패키지를 찾지 못해 "from src.day4..." import 가 실패합니다.
#   - 그래서 day3 관례와 동일하게 프로젝트 루트(parents[2])를 sys.path 에 넣어,
#     어디서 실행하든 "from src.day4.rag_quality..." import 가 되도록 보정합니다.
#   - parents[2] = (이 파일=src/day4/...) 기준 두 단계 위 = 프로젝트 루트.
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.day4.rag_quality.runner import main


# 다른 파일에서 import 할 때는 실행되지 않고, 직접 실행할 때만 main()이 동작합니다.
if __name__ == "__main__":
    main()
