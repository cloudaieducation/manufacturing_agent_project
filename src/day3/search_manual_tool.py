"""
Day3 search_manual Tool - beginner friendly simplified version

This file is a simplified educational Tool for the manufacturing AI Agent project.

[이 파일이 Day3 아키텍처에서 맡는 역할]
- 이 파일은 2일차에서 만든 RAG 검색 기능을, Agent가 호출할 수 있는 단일 Tool
  (search_manual)로 감싸 주는 계층입니다.
- 즉 ManualRAGAgent가 "기술 문서/조치 절차의 근거"를 찾을 때 호출하는 Tool입니다.

[DB Tool과 RAG Tool은 "근거의 성격"이 다릅니다 — 핵심 개념]
- DB Tool(postgres_db_tool.py): 실제 설비 상태, 알람 이력, 수치 데이터 등
  "지금 현장이 어떤 상태인가"라는 사실(fact)을 확인합니다.
- RAG Tool(이 파일): 기술 문서, 장애 대응 가이드, 조치 절차 등
  "이럴 때는 어떻게 대응해야 하는가"라는 지식/절차의 근거를 검색합니다.
- 장애 대응 요약은 이 둘(사실 + 절차)을 함께 봐야 신뢰할 수 있습니다.

Main idea:
- Try Day2 RAG search first.       (먼저 Day2 RAG 벡터 검색을 시도)
- If RAG search fails or returns no results, use simple CSV keyword search.
  (RAG가 준비 안 됐거나 결과가 없으면 CSV 키워드 검색으로 fallback)
- Keep the code small so beginners can read it.
- Do not write log files.
- Do not use real company data or internal system names.

[fallback에 대한 중요한 오해 방지]
- 여기서의 CSV 키워드 검색 fallback은 "운영 수준의 검색 품질을 보장"하는 구조가
  아니라, RAG 인덱스가 아직 없어도 수업이 멈추지 않게 하는 교육용 안정화 장치입니다.

[현업 적용 시 검토 포인트]
- 사내 문서 저장소, chunk 분할 전략, metadata 설계, vector DB 선택,
  문서 접근 권한과 보안 등급을 함께 검토해야 합니다.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Any, Callable


def get_project_root() -> Path:
    """
    이 파일 위치를 기준으로 프로젝트 루트를 계산합니다.

    parents[2] = 프로젝트 루트 (src/day3/이 파일 → src → 프로젝트 루트)
    CSV/RAG 모듈 경로를 루트 기준으로 찾기 위해 사용합니다.

    Expected file location:
    project_root/src/day3/search_manual_tool.py
    """
    return Path(__file__).resolve().parents[2]


def build_search_query(
    alarm_code: str | None = None,
    symptom: str | None = None,
    user_query: str | None = None,
) -> str:
    """
    alarm_code, symptom, user_query 세 입력을 하나의 검색 문자열로 합칩니다.

    설계 의미:
        - 검색 엔진(RAG/CSV)에는 결국 "하나의 질의 문자열"이 들어가므로,
          여러 입력 신호를 합쳐 검색 품질을 높이는 전처리 단계입니다.
        - 입력값이 풍부할수록(알람 코드 + 증상 + 사용자 질문) 검색이 더 정확해집니다.

    입력: alarm_code/symptom/user_query (각각 None이거나 빈 값일 수 있음)
    출력: 공백으로 이어 붙인 단일 검색 문자열 (모두 비면 빈 문자열)
    """
    query_parts: list[str] = []

    # None 또는 공백뿐인 값은 검색어에 넣지 않습니다.
    # (빈 값이 섞이면 검색 품질이 떨어지므로 의미 있는 신호만 모읍니다.)
    for value in [alarm_code, symptom, user_query]:
        if value is not None and str(value).strip() != "":
            query_parts.append(str(value).strip())

    return " ".join(query_parts)


def load_rag_search_function() -> Callable[..., Any] | None:
    """
    Day2 RAG 모듈(src.day2.rag_search)에서 search_top_k 함수를 동적으로 불러옵니다.

    설계 의미:
        - Day3 코드가 Day2 RAG를 "있으면 쓰고, 없으면 fallback"하도록 느슨하게 연결합니다.
        - import를 파일 상단이 아니라 함수 안에서 try로 감싸는 이유는,
          Day2 RAG가 아직 준비되지 않은 환경에서도 이 파일이 깨지지 않게 하기 위함입니다.

    출력:
        - 준비됐으면 search_top_k 함수 객체
        - 준비 안 됐으면 None → search_manual()이 fallback_keyword_search()를 사용
    """
    project_root = get_project_root()

    # Day2 패키지를 import하려면 프로젝트 루트가 sys.path에 있어야 합니다.
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Day2 RAG가 없거나 import 중 오류가 나도 수업이 멈추지 않도록 광범위하게 잡고 None 반환.
    try:
        from src.day2.rag_search import search_top_k
    except Exception:
        return None

    return search_top_k


def fallback_keyword_search(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """
    Day2 RAG를 쓸 수 없을 때 동작하는, chunk_metadata.csv 기반 단순 키워드 검색입니다.

    위치/역할:
        - 이것은 RAG 실패 시 수업이 멈추지 않게 해 주는 "교육용 fallback"이며,
          벡터 유사도 검색이 아니라 단순 단어 포함 횟수(score) 매칭입니다.
        - 따라서 검색 품질은 RAG보다 낮을 수 있고, 운영용 검색 대체재가 아닙니다.

    Search file priority (먼저 발견되는 파일을 사용):
    1. outputs/day2/chunk_metadata.csv
    2. outputs/chunk_metadata.csv
    3. data/chunk_metadata.csv

    Score rule:
    - 질의를 단어들로 쪼갭니다.
    - 각 CSV 행에 질의 단어가 몇 개 포함됐는지 세어 점수로 사용합니다.
    - 점수 상위 top_k개 행을 반환합니다.
    """
    project_root = get_project_root()

    # CSV 후보 경로를 우선순위대로 둡니다.
    # 환경(2일차 산출물 위치)에 따라 파일 위치가 다를 수 있어 여러 곳을 순서대로 확인합니다.
    candidate_paths = [
        project_root / "outputs" / "day2" / "chunk_metadata.csv",
        project_root / "outputs" / "chunk_metadata.csv",
        project_root / "data" / "chunk_metadata.csv",
    ]

    # 우선순위대로 실제 존재하는 첫 번째 파일을 선택합니다.
    metadata_file: Path | None = None
    for path in candidate_paths:
        if path.exists() and path.is_file():
            metadata_file = path
            break

    # CSV 자체가 없으면 "오류"가 아니라 "검색 결과 없음(빈 list)"으로 처리합니다.
    # 즉 결과가 비는 것은 코드 버그가 아니라, RAG 인덱스/CSV metadata 준비 상태 문제일 수 있습니다.
    if metadata_file is None:
        return []

    # 질의를 소문자로 정규화하고, 한글/영문/숫자/_/- 단위로 토큰을 추출합니다.
    normalized_query = str(query or "").strip().lower()
    query_words = re.findall(r"[0-9a-zA-Z가-힣_-]+", normalized_query)
    # 1글자 토큰은 노이즈가 많아 검색 정확도를 떨어뜨리므로 2글자 이상만 사용합니다.
    query_words = [word for word in query_words if len(word) >= 2]

    # 쓸 만한 검색 단어가 하나도 없으면 빈 결과를 돌려줍니다.
    if len(query_words) == 0:
        return []

    scored_rows: list[dict[str, Any]] = []

    # CSV는 Windows 메모장 등에서 BOM이 붙어 저장되는 경우가 많아 utf-8-sig로 엽니다.
    # (프로젝트 공통 규칙: 파일 입출력은 utf-8-sig 사용)
    with metadata_file.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        # 각 행의 모든 컬럼 값을 한 덩어리 텍스트로 합쳐, 질의 단어가 몇 개 들어있는지 셉니다.
        # 어떤 컬럼에 정보가 있을지 미리 알 수 없으므로 행 전체를 검색 대상으로 삼습니다.
        for row in reader:
            row_text = " ".join(str(value) for value in row.values() if value is not None)
            searchable_text = row_text.lower()

            score = 0
            for word in query_words:
                if word in searchable_text:
                    score += 1

            # 한 단어라도 맞은 행만 후보로 남깁니다.
            if score > 0:
                scored_rows.append({
                    "score": score,
                    "row": row,
                })

    # 점수가 높은 행이 앞에 오도록 내림차순 정렬합니다.
    scored_rows.sort(key=lambda item: item["score"], reverse=True)

    results: list[dict[str, Any]] = []

    # 상위 top_k개 행만 표준 결과 형태로 변환합니다.
    # CSV마다 컬럼 이름이 제각각일 수 있으므로(doc_name vs source vs file_name 등),
    # 아래에서 "여러 후보 컬럼명 중 먼저 값이 있는 것"을 골라 표준 필드로 정규화합니다.
    # 이렇게 하면 CSV 스키마가 조금 달라도 Agent는 항상 같은 형태의 결과를 받습니다.
    for index, item in enumerate(scored_rows[:top_k], start=1):
        row = item["row"]

        # next(..., "")는 "후보 컬럼명들을 순서대로 보다가 값이 있는 첫 컬럼을 사용,
        # 하나도 없으면 빈 문자열"이라는 뜻입니다.
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

        # 본문 텍스트 컬럼을 못 찾았으면, 행 전체를 합쳐 최대 1000자까지 본문으로 대체합니다.
        # (결과 텍스트가 완전히 비어 보이는 것을 막는 최소 보완 장치입니다.)
        if text == "":
            text = " ".join(str(value) for value in row.values() if value is not None)[:1000]

        # Agent/MCP가 다루기 좋은 표준 결과 한 건을 만듭니다.
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
    Agent/MCP Tool로 쓰이는 매뉴얼 검색의 "공개 진입점"입니다.

    Agent 관점:
        - ManualRAGAgent와 MCP search_manual Tool이 최종적으로 호출하는 함수입니다.
        - alarm_code/symptom/user_query가 풍부할수록 더 정확한 근거를 찾을 가능성이 높습니다.
          (top_k는 몇 건을 가져올지 결정 — 너무 크면 노이즈, 너무 작으면 근거 부족)

    Processing flow:
    1. 세 입력을 하나의 검색 질의로 합칩니다.
    2. Day2 RAG search_top_k()를 먼저 시도합니다.
    3. RAG가 실패하거나 결과가 0건이면 CSV 키워드 검색으로 fallback합니다.
    4. search_mode를 포함한 표준 dict를 반환합니다.

    출력 dict의 search_mode 값으로 "어느 경로로 검색했는지"를 알 수 있습니다:
        - "rag": Day2 RAG 검색 성공
        - "fallback_csv": RAG 불가/0건이라 CSV 키워드 검색 사용
        - "empty_query": 검색어가 비어 아예 검색하지 않음
    """
    top_k = int(top_k)

    # 1) 세 입력을 하나의 검색 문자열로 합칩니다.
    query = build_search_query(
        alarm_code=alarm_code,
        symptom=symptom,
        user_query=user_query,
    )

    # 검색어가 완전히 비면 검색을 시도하지 않고, 그 사실을 search_mode로 명시해 돌려줍니다.
    # (호출 측이 "검색 실패"가 아니라 "입력이 비었음"을 구분할 수 있게 합니다.)
    if query.strip() == "":
        return {
            "query": query,
            "search_mode": "empty_query",
            "top_k": top_k,
            "result_count": 0,
            "results": [],
        }

    # 2) RAG 함수 로딩을 시도합니다. None이면 RAG 미준비 상태입니다.
    search_function = load_rag_search_function()
    results: list[dict[str, Any]] = []
    search_mode = "rag"

    if search_function is not None:
        try:
            raw_results = search_function(query, top_k)

            # RAG 구현마다 반환 형태가 다를 수 있어, 여러 형태를 표준 list로 정규화합니다.
            #  - None: 결과 없음
            #  - dict이면서 "results" 리스트를 품은 경우 / "data.results" 형태
            #  - 그 외 dict: 통째로 한 건으로 취급
            #  - list: 그대로 사용
            #  - 기타 타입: 문자열화해서 한 건으로 감쌈
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
            # RAG 호출 중 예외가 나도 멈추지 않고 빈 결과로 둔 뒤 아래 fallback으로 넘어갑니다.
            results = []

    # 3) RAG 결과가 0건이면(미준비/실패/매칭 없음) CSV 키워드 검색으로 fallback합니다.
    #    fallback은 교육용 안정화 장치이며, search_mode를 바꿔 어느 경로였는지 기록합니다.
    if len(results) == 0:
        search_mode = "fallback_csv"
        results = fallback_keyword_search(query, top_k)

    # 4) 검색 경로(search_mode)와 건수를 포함한 표준 결과를 돌려줍니다.
    return {
        "query": query,
        "search_mode": search_mode,
        "top_k": top_k,
        "result_count": len(results),
        "results": results,
    }


if __name__ == "__main__":
    # 직접 실행 시: 교육용 가상 알람 코드로 search_manual을 한 번 호출해 결과 형태를 확인합니다.
    # 출력의 search_mode를 보면 RAG로 찾았는지 CSV fallback으로 찾았는지 알 수 있습니다.
    result = search_manual(
        alarm_code="ALM-TEMP-402",
        symptom="temperature abnormal",
        top_k=3,
    )
    print(result)
