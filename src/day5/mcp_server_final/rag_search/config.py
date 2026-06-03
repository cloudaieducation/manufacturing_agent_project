# -*- coding: utf-8 -*-
"""
Day5 mcp_server_final - rag_search 공통 설정/유틸 모듈 (config)

[출처/유래]
이 파일은 Day4 `rag_quality/config.py`의 '검색에 필요한 부분'을 Day5 `rag_search`로
복사해 온 것입니다. Day4 원본은 수정하지 않으며, 이 복사본만 Day5 기준으로 조정합니다.
평가(scoring/reporting/runner) 관련 일부 보조 함수는 검색에는 쓰이지 않지만,
복사 충실도를 위해 그대로 남겨 둡니다(검색 흐름은 이들을 import 하지 않습니다).

이 파일은 rag_search에서 사용하는
- 실행 설정(mode, top_k 등)
- Chroma / Ollama 기본값
을 한곳에 모아 둔 "가장 아래 계층" 파일입니다.

[Day5 차이 — 매우 중요]
- Day4 get_rag_eval_config() 의 top_k 기본값은 3 이지만, Day5 운영 검색은 top_k=10 을 기준으로 합니다.
  (top_k=10 은 Day4 검색 성능 측정이 완료된 값입니다.)
- 그래서 Day5 전용 DEFAULT_TOP_K=10 상수와 get_rag_search_config(top_k=10) 함수를 추가했습니다.
  rag_quality_adapter 는 Day4 기본값(3)에 의존하지 않고 이 Day5 설정을 사용합니다.
- vector_db/chroma_db 경로/collection 이름은 Day4 와 동일하게 유지하되, read-only 로만 사용합니다.

또한 여러 모듈에서 공통으로 쓰는 작은 보조 함수도 함께 둡니다.
(normalize_value / safe_float / is_out_of_scope_case 등)

교육용 리팩토링 2단계에서는 파일 수를 불필요하게 늘리지 않기 위해,
load_json_file() 같은 IO 유틸도 일단 이 파일에 함께 둡니다.
- 엄밀히는 IO 유틸이지만, 지금은 "공통 기반 한 곳"으로 모아 두는 것이 설명하기 쉽습니다.
- 이후 필요하면 io_utils.py 등으로 더 세분화할 수 있습니다.

import 계층 규칙(중요):
- 이 파일(config.py)은 내부 다른 모듈(runner.py 등)을 절대 import 하지 않습니다.
  → 항상 import 그래프의 가장 아래에 있어야 순환 import가 생기지 않습니다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


# Ollama 임베딩 설정 (실제 Chroma 검색용)
#   - day2에서 collection을 Ollama nomic-embed-text(768차원)로 인덱싱했으므로,
#     질문도 같은 모델로 임베딩해 query_embeddings로 검색해야 차원이 맞습니다.
#   - localhost Ollama 호출이며 외부 인터넷 호출이 아닙니다. Ollama 미실행 시 mock fallback 됩니다.
OLLAMA_EMBED_URL = os.environ.get("OLLAMA_EMBED_URL", "http://localhost:11434/api/embeddings")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")


# ──────────────────────────────────────────────────────────────────────
# 1. 기본 상수 정의
#    - 입력/출력 파일 경로와 Chroma 기본값을 한곳에 모아 둡니다.
#    - 경로는 "프로젝트 루트에서 실행"하는 것을 전제로 한 상대경로입니다.
#      (이 프로젝트의 다른 스크립트들과 동일하게 항상 루트에서 실행하세요.)
#    - 경로/설정을 코드 곳곳에 흩뿌리지 않고 config 한곳에 모으면, 수업 중
#      "어떤 파일을 읽고 어디에 결과가 쌓이는지"를 한눈에 짚어 줄 수 있습니다.
# ──────────────────────────────────────────────────────────────────────
DATA_PATH = Path("data/day4_rag_evaluation_cases.json")
OUTPUT_DIR = Path("outputs/day4")
# 결과는 두 가지 형태로 남깁니다: 기계가 다루기 좋은 JSON과 사람이 읽기 좋은 Markdown 보고서.
RESULT_JSON_PATH = OUTPUT_DIR / "rag_quality_evaluation_result.json"
REPORT_MD_PATH = OUTPUT_DIR / "rag_quality_evaluation_report.md"

DEFAULT_CHROMA_PERSIST_DIR = Path("vector_db/chroma_db")
DEFAULT_CHROMA_COLLECTION_NAME = "manufacturing_rag_docs"

# expected_evidence_type 중 "근거가 없거나 약한 것이 정상"인 케이스 유형입니다.
#   - 예: 없는 알람 코드 검색, 검색 근거가 부족할 때 추가 확인을 요구하는 케이스
#   - 이런 케이스는 "검색 결과 없음"이 오히려 바람직하므로 판정 규칙이 다릅니다.
#   - out_of_scope: 현재 3개 문서 범위 밖 질문(없는 설비/알람 등)도 같은 계열로 다룹니다.
#     단, out_of_scope는 judge_evidence_quality()에서 "가장 먼저" 따로 처리합니다.
NONE_EVIDENCE_TYPES = {"none", "none_or_low_confidence", "out_of_scope"}


def is_out_of_scope_case(case: dict) -> bool:
    """현재 3개 문서 범위 밖 질문인지 평가 케이스 기준으로 판단합니다.

    설명:
        - 평가 케이스의 expected_evidence_type 값이 "out_of_scope"이면
          현재 지식베이스(3개 문서)로는 직접 근거를 만들 수 없는 질문이라는 뜻입니다.
        - 이런 케이스는 "유사 문서가 검색되었는지"가 아니라
          "직접 근거가 없음을 올바르게 판단하는지"가 평가 목적입니다.
    """
    return str(case.get("expected_evidence_type", "") or "").strip().lower() == "out_of_scope"


# ──────────────────────────────────────────────────────────────────────
# 2. JSON 읽기 함수
# ──────────────────────────────────────────────────────────────────────
def load_json_file(path: Path) -> list[dict]:
    """
    JSON 파일을 읽어 list[dict] 형태로 돌려줍니다. (평가 케이스 목록 읽기용)

    설명:
        - Windows 메모장 등에서 저장한 파일은 맨 앞에 보이지 않는 BOM 표시가 붙을 수 있습니다.
          그래서 utf-8-sig(=BOM 허용)로 먼저 읽고, 안 되면 utf-8로 다시 시도합니다.
        - 파일이 없거나 JSON 문법이 틀려도 프로그램을 멈추지 않고, 친절한 안내를 출력한 뒤
          빈 리스트([])를 돌려줍니다. (수업이 중간에 끊기지 않도록 하는 안전장치)

    반환: 정상이면 list[dict], 문제가 있으면 빈 리스트([])
    """
    # 파일이 아예 없는 경우: 어디를 봐야 하는지 경로까지 알려 줍니다.
    if not path.exists():
        print(f"[오류] 입력 파일을 찾을 수 없습니다: {path}")
        print("       프로젝트 루트에서 실행했는지, 파일 경로가 맞는지 확인해 주세요.")
        return []

    # 1차 시도는 utf-8-sig(BOM 허용), 실패하면 2차로 일반 utf-8 로 읽습니다.
    raw_text = None
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            raw_text = path.read_text(encoding=encoding)
            break  # 성공하면 더 시도하지 않고 빠져나옵니다.
        except UnicodeDecodeError:
            continue  # 이 인코딩으로는 못 읽었으니 다음 인코딩으로 재시도

    if raw_text is None:
        print(f"[오류] 파일 인코딩을 해석하지 못했습니다(UTF-8 계열 아님): {path}")
        return []

    # 문자열을 실제 JSON 데이터로 변환합니다. 문법 오류면 위치까지 알려 줍니다.
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as error:
        # error.lineno / error.colno / error.msg 로 "어디가 왜 틀렸는지" 안내합니다.
        print(f"[오류] JSON 문법 오류: {path}")
        print(f"       line {error.lineno}, column {error.colno} - {error.msg}")
        return []

    # 이 프로그램은 "케이스 목록(list)"을 기대합니다. dict 등 다른 형태면 경고 후 빈 리스트.
    if not isinstance(data, list):
        print(f"[경고] JSON 최상위가 list가 아닙니다(현재 형태: {type(data).__name__}): {path}")
        return []

    # list 안의 항목 중 dict가 아닌 것은 평가할 수 없으므로 걸러 냅니다(안전 처리).
    return [item for item in data if isinstance(item, dict)]


# ──────────────────────────────────────────────────────────────────────
# 3. 실행 설정 함수
# ──────────────────────────────────────────────────────────────────────
def get_rag_eval_config() -> dict:
    """
    환경 변수를 읽어 이번 실행에 사용할 설정(dict)을 만듭니다.

    환경 변수와 기본값:
        - RAG_EVAL_MODE          : "chroma"(기본) 또는 "mock"
        - CHROMA_PERSIST_DIR     : "vector_db/chroma_db"(기본)
        - CHROMA_COLLECTION_NAME : "manufacturing_rag_docs"(기본)
        - RAG_TOP_K              : 3(기본). 숫자가 아니면 3으로 처리.

    설명:
        - 환경 변수는 "실행할 때 바깥에서 넘겨 주는 설정 값"입니다.
          코드를 고치지 않고도 모드나 Top-K를 바꿔 가며 실습할 수 있게 해 줍니다.
    """
    # mode: 소문자로 통일하고, 허용된 값이 아니면 안전하게 "chroma"로 되돌립니다.
    mode = os.environ.get("RAG_EVAL_MODE", "chroma").strip().lower()
    if mode not in ("chroma", "mock"):
        mode = "chroma"

    # 경로/이름: 비어 있으면 기본값을 사용합니다.
    persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "").strip() or str(DEFAULT_CHROMA_PERSIST_DIR)
    collection_name = os.environ.get("CHROMA_COLLECTION_NAME", "").strip() or DEFAULT_CHROMA_COLLECTION_NAME

    # top_k: 문자열을 정수로 바꿉니다. 숫자가 아니거나 0 이하이면 기본값 3으로 처리합니다.
    top_k_raw = os.environ.get("RAG_TOP_K", "3").strip()
    try:
        top_k = int(top_k_raw)
        if top_k <= 0:
            top_k = 3
    except (TypeError, ValueError):
        top_k = 3

    return {
        "mode": mode,
        "chroma_persist_dir": persist_dir,
        "collection_name": collection_name,
        "top_k": top_k,
    }


# ──────────────────────────────────────────────────────────────────────
# 3-A. Day5 운영 검색 설정 (top_k=10 명시)
# ──────────────────────────────────────────────────────────────────────
# Day5 mcp_server_final 의 search_manual 운영 검색 기준 top_k.
# [중요] Day4 get_rag_eval_config() 기본값(3)에 의존하지 않는다. 운영 검색은 10 으로 고정한다.
#        문서가 3건뿐이어도 top_k=10 을 유지하고, 실제 반환 가능한 결과만 돌려준다.
DEFAULT_TOP_K = 10


def get_rag_search_config(top_k: int = DEFAULT_TOP_K) -> dict:
    """Day5 운영 검색용 설정(dict)을 만든다. top_k 는 기본 10 으로 명시한다.

    [Day4 get_rag_eval_config() 와의 차이]
        - top_k 기본값을 3 이 아니라 DEFAULT_TOP_K(=10) 로 둔다.
        - 그 외(mode/chroma_persist_dir/collection_name)는 Day4 설정을 그대로 재사용한다.
          (vector_db/chroma_db 경로·collection 이름을 Day4 와 일치시켜 검색 성능을 유지한다.)

    [입력]
        top_k: 검색해 올 chunk 수. 기본 10. 0 이하면 DEFAULT_TOP_K 로 되돌린다.
    [반환]
        retrieval.retrieve_chunks(user_query, config) 가 그대로 쓰는 config dict.

    [주의]
        ChromaDB / metadata DB 는 read-only 로만 사용한다(이 함수는 경로/이름만 구성).
    """
    base = get_rag_eval_config()
    try:
        resolved_top_k = int(top_k)
        if resolved_top_k <= 0:
            resolved_top_k = DEFAULT_TOP_K
    except (TypeError, ValueError):
        resolved_top_k = DEFAULT_TOP_K
    base["top_k"] = resolved_top_k
    return base


# ──────────────────────────────────────────────────────────────────────
# 4. 값 정규화 함수 (metadata 비교를 안정적으로 하기 위함)
# ──────────────────────────────────────────────────────────────────────
def normalize_value(value) -> str:
    """
    metadata 비교를 위해 값을 "비교하기 쉬운 문자열"로 통일합니다.

    규칙:
        - None         → "" (빈 문자열)
        - bool         → "true" 또는 "false"
        - 문자열       → 앞뒤 공백 제거 + 소문자
        - 숫자/기타    → 문자열로 변환 후 소문자

    왜 필요한가:
        - 같은 의미라도 True / "true" / "True" 처럼 표기가 제각각일 수 있습니다.
          이를 한 형태로 맞춰야 "같다/다르다"를 올바르게 비교할 수 있습니다.

    주의:
        - 파이썬에서 bool은 int의 하위 타입이라, 반드시 bool을 int보다 "먼저" 검사해야
          True가 숫자 1로 잘못 처리되지 않습니다.
    """
    if value is None:
        return ""

    # bool 먼저 검사 (True/False → "true"/"false")
    if isinstance(value, bool):
        return "true" if value else "false"

    # 문자열은 공백 제거 후 소문자로
    if isinstance(value, str):
        return value.strip().lower()

    # 그 외(숫자 등)는 문자열로 바꾼 뒤 소문자로 통일
    #   - 추가로 "true"/"false"로 쓰인 문자열 숫자도 그대로 비교되도록 합니다.
    return str(value).strip().lower()


# ──────────────────────────────────────────────────────────────────────
# 5. Distance 안전 변환 함수
# ──────────────────────────────────────────────────────────────────────
def safe_float(value) -> float | None:
    """
    Chroma의 distance 값처럼 형태가 들쭉날쭉한 값을 안전하게 float로 바꿉니다.

    규칙:
        - None 이면 None 반환
        - int / float / 숫자처럼 생긴 문자열이면 float로 변환
        - 변환할 수 없으면 None 반환 (프로그램을 멈추지 않기 위함)

    왜 필요한가:
        - distance는 검색 경로/버전에 따라 None, 정수, 실수, 문자열 등으로 올 수 있어
          그대로 계산/표시하면 오류가 날 수 있습니다. 여기서 한 번 안전하게 거릅니다.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
