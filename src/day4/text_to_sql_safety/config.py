# -*- coding: utf-8 -*-
"""
Day4 Text-to-SQL Safety 설정 모듈 - 교육용

이 파일은 Safety Checker가 사용하는 "경로/출력 설정"과 "LLM timeout 설정"만 모아 둔 모듈입니다.
text_to_sql_safety_checker.py가 import 해서 사용하며, 값/순서/주석을 그대로 옮겨
"입력/출력 파일이 어디인지, LLM timeout이 몇 초인지"를 한곳에서 볼 수 있게 합니다.

(설계 원칙)
- 이 모듈은 표준 라이브러리만 사용하고, 프로젝트 내부 모듈(policies/checker/safety/
  generators/reporting/runners 등)을 import 하지 않습니다. 순환 import를 피하기 위해
  '설정 값/경로/timeout'만 담는 모듈로 유지합니다.
"""

import os
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────
# 경로 상수 — day4 다른 파일과 동일하게 "프로젝트 루트" 기준으로 계산합니다.
#   parents[0]=day4, parents[1]=src, parents[2]=프로젝트 루트
#   (config.py는 src/day4/text_to_sql_safety/ 안에 있으므로 parents[3]이 프로젝트 루트)
# ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PATH = PROJECT_ROOT / "data" / "day4_text_to_sql_cases.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "day4"
RESULT_JSON_PATH = OUTPUT_DIR / "text_to_sql_safety_result.json"
REPORT_MD_PATH = OUTPUT_DIR / "text_to_sql_safety_report.md"
TRACE_LOG_PATH = OUTPUT_DIR / "text_to_sql_safety_trace.jsonl"
# LLM Batch 전용 출력 (기본 Batch 결과 파일을 덮어쓰지 않도록 별도 경로 사용)
LLM_BATCH_RESULT_JSON_PATH = OUTPUT_DIR / "text_to_sql_llm_batch_result.json"
LLM_BATCH_REPORT_MD_PATH = OUTPUT_DIR / "text_to_sql_llm_batch_report.md"


def _resolve_llm_timeout() -> int:
    """
    LLM(OpenAI 호환) 호출 타임아웃(초)을 결정합니다.

    - 환경변수 TEXT_TO_SQL_LLM_TIMEOUT로 조정할 수 있고, 기본값은 120초입니다.
    - NVIDIA 등 일부 엔드포인트는 응답이 느려 30초로는 타임아웃→mock fallback이 잦았기에
      기본 타임아웃을 넉넉히(120초) 두었습니다.
    - 숫자가 아니거나 0 이하이면 안전하게 120초로 처리합니다.
    """
    raw = (os.environ.get("TEXT_TO_SQL_LLM_TIMEOUT", "120") or "120").strip()
    try:
        value = int(raw)
        return value if value > 0 else 120
    except (TypeError, ValueError):
        return 120
