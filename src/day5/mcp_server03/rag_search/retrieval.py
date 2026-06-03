# -*- coding: utf-8 -*-
"""
Day5 mcp_server03 - rag_search 검색 계층 모듈 (retrieval)

[출처/유래]
이 파일은 Day4 `rag_quality/retrieval.py`를 Day5 `rag_search`로 복사한 것입니다.
검색 로직(함수 내부)은 Day4 와 동일하게 유지해 검색 성능을 보존하며, import 경로만
Day5 `rag_search` 기준으로 바꿨습니다. Day4 원본은 수정하지 않습니다.

이 파일은 "질문을 받아 관련 문서 chunk를 찾아오는" 검색 단계만 모아 둡니다.
- Ollama 임베딩 호출(_embed_query_with_ollama)
- 실제 Chroma Vector DB 검색(chroma_retrieve_chunks)  ← vector_db/chroma_db 는 read-only 로만 사용
- 교육용 가짜 검색(mock_retrieve_chunks)
- Chroma 우선, 실패 시 mock으로 자동 전환하는 통합 검색(retrieve_chunks)

[운영형 입력 — 매우 중요]
- 운영 진입점은 retrieve_chunks(user_query, config) 입니다.
  평가 케이스(case / case_id / expected_keywords / expected_metadata / expected_tools)에
  의존하지 않고, 'user_query 와 config' 만으로 동작합니다.
- top_k 는 config["top_k"] 를 따릅니다. Day5 는 rag_search.config.get_rag_search_config()
  로 top_k=10 을 명시해 전달합니다(Day4 기본값 3 에 의존하지 않음).
- rerank / scoring / report 로직은 이 파일에 들어오지 않습니다.

import 계층 규칙(중요):
- retrieval.py는 config.py만 import 합니다(reranking / adapter 등을 import 하지 않습니다).
  → 항상 config 아래 계층을 바라보는 단방향 구조라 순환 import가 생기지 않습니다.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

# 검색에 필요한 설정값/유틸은 config.py에서 명시적으로 가져옵니다(별표 import 금지).
from day5.mcp_server03.rag_search.config import (
    OLLAMA_EMBED_URL,
    OLLAMA_EMBED_MODEL,
    DEFAULT_CHROMA_PERSIST_DIR,
    DEFAULT_CHROMA_COLLECTION_NAME,
    safe_float,
)


# ──────────────────────────────────────────────────────────────────────
# 1. Ollama 임베딩 함수 (실제 Chroma 검색용)
# ──────────────────────────────────────────────────────────────────────
def _embed_query_with_ollama(text: str) -> list:
    """질문 문자열을 Ollama 임베딩 API로 보내 768차원 벡터로 변환합니다.

    [왜 Ollama 임베딩인가 — 학습 흐름을 따라가기 위한 설명]
        - Vector DB 검색은 "질문 벡터"와 "문서 벡터"의 거리(distance)를 재는 방식입니다.
          두 벡터를 같은 임베딩 모델로 만들어야 거리 계산이 의미를 갖습니다.
        - day2에서 문서를 Ollama nomic-embed-text(768차원)로 인덱싱했으므로,
          질문도 반드시 같은 모델로 임베딩해야 차원과 의미 공간이 맞습니다.
        - 함수 이름 앞의 '_'는 "이 모듈 내부용 helper"라는 관례 표시입니다.

    실패 시: 응답에 embedding 필드가 없으면 RuntimeError를 던집니다.
        이 예외는 호출부(chroma_retrieve_chunks)에서 잡아 mock fallback 사유로 바꿉니다.
    """
    payload = json.dumps({"model": OLLAMA_EMBED_MODEL, "prompt": str(text or "")}).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    embedding = data.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError("Ollama 응답에 embedding 필드가 없습니다.")
    return [float(value) for value in embedding]


# ──────────────────────────────────────────────────────────────────────
# 2. Chroma 검색 함수
# ──────────────────────────────────────────────────────────────────────
def chroma_retrieve_chunks(
    user_query: str,
    top_k: int,
    persist_dir: Path,
    collection_name: str,
) -> tuple[list[dict], str | None]:
    """
    실제 Chroma Vector DB에서 user_query와 관련된 문서 chunk를 검색합니다.

    반환 형태: (chunks, error_reason)
        - 검색 성공(결과 있음/없음 모두) → (chunks, None)
        - 기술적 실패                     → ([], "실패 사유 메시지")

    핵심 구분(매우 중요):
        - "검색은 됐는데 결과가 0건" 은 기술적 실패가 아니므로 ([], None) 으로 돌려줍니다.
          → 이 경우는 mock fallback 대상이 아니라, "검색 결과 없음" 그대로 평가합니다.
        - import 실패 / 경로 없음 / collection 없음 / query 오류 / embedding function 오류는
          모두 기술적 실패이므로 ([], "사유") 로 돌려줍니다. → mock fallback 대상.

    설명:
        - chromadb는 함수 "안에서" import 합니다. 설치가 안 되어 있어도 이 함수에 들어오기
          전까지는 오류가 나지 않게 하고, 들어와서 ImportError를 잡아 fallback 하기 위함입니다.
    """
    # persist_dir 가 문자열로 들어올 수도 있으니 Path로 통일합니다.
    persist_dir = Path(persist_dir)

    # (1) chromadb 설치 여부 확인 — 미설치면 기술적 실패로 처리(설치 파일은 건드리지 않음)
    try:
        import chromadb
    except Exception as error:  # noqa: BLE001  (import 단계의 모든 문제를 포괄)
        return [], f"chromadb import 실패: {str(error)[:200]}"

    # (2) DB 폴더 존재 확인 — 없으면 아직 인덱스를 안 만든 상태이므로 기술적 실패
    if not persist_dir.exists():
        return [], f"Chroma persist_dir 경로가 없습니다: {persist_dir}"

    # (3) PersistentClient 생성 — 손상된 DB 등으로 실패할 수 있어 try로 감쌉니다.
    try:
        client = chromadb.PersistentClient(path=str(persist_dir))
    except Exception as error:  # noqa: BLE001
        return [], f"Chroma PersistentClient 생성 실패: {str(error)[:200]}"

    # (4) collection 가져오기 — 이름이 없거나 아직 안 만들었으면 실패
    try:
        collection = client.get_collection(name=collection_name)
    except Exception as error:  # noqa: BLE001
        return [], f"Chroma collection을 열 수 없습니다({collection_name}): {str(error)[:200]}"

    # (5) 질문 임베딩 — collection이 Ollama 768차원으로 인덱싱되어 있으므로,
    #     같은 모델로 질문을 임베딩한 뒤 query_embeddings로 검색해야 차원이 맞습니다.
    #     (Ollama 미실행/오류 시 mock fallback 사유로 돌려줍니다.)
    try:
        query_embedding = _embed_query_with_ollama(user_query)
    except Exception as error:  # noqa: BLE001
        return [], f"질의 임베딩(Ollama) 실패: {str(error)[:200]}"

    # (6) 실제 검색(query) 실행 — Ollama 임베딩 벡터로 query_embeddings 검색
    try:
        query_result = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as error:  # noqa: BLE001  (embedding function 오류 포함 모든 query 오류)
        return [], f"Chroma query 실행 실패(embedding function 등): {str(error)[:200]}"

    # (6) query 결과 파싱
    #     query_texts를 1개 넣었으므로 결과의 첫 번째 묶음([0])만 사용합니다.
    #     결과가 비어 있으면 documents 등이 [[]] 형태일 수 있어 안전하게 꺼냅니다.
    documents = (query_result.get("documents") or [[]])[0]
    metadatas = (query_result.get("metadatas") or [[]])[0]
    distances = (query_result.get("distances") or [[]])[0]

    chunks: list[dict] = []
    for index, text in enumerate(documents):
        # 같은 index 위치의 metadata/distance를 안전하게 꺼냅니다(길이가 다를 경우 대비).
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        distance = distances[index] if index < len(distances) else None

        chunks.append(
            {
                "chunk_id": f"chroma-{index}",
                "text": str(text or ""),
                "metadata": metadata if isinstance(metadata, dict) else {},
                "distance": safe_float(distance),  # None/숫자/문자 → float 또는 None
                "source": "chroma",
            }
        )

    # 결과가 0건이어도 "검색은 성공"이므로 ([], None) 으로 돌려줍니다(중요!).
    return chunks, None


# ──────────────────────────────────────────────────────────────────────
# 3. Mock 검색 함수
# ──────────────────────────────────────────────────────────────────────
def mock_retrieve_chunks(user_query: str) -> list[dict]:
    """
    Chroma가 기술적으로 실패했을 때 사용하는 "교육용 가짜 검색"입니다.

    설계 의미:
        - 실제 DB 없이도 수업 흐름이 끊기지 않도록, 질문에 들어 있는 키워드를 보고
          미리 만들어 둔 교육용 Chunk를 돌려줍니다.
        - 반환되는 Chunk에는 항상 source="mock" 을 넣어, 결과만 봐도 "이건 mock이었다"를
          구분할 수 있게 합니다.
        - 매칭되는 키워드가 없으면 "근거 부족" Chunk(또는 빈 리스트)를 돌려주어,
          없는 알람/근거 부족 케이스도 자연스럽게 평가되도록 합니다.

    주의:
        - 여기 등장하는 알람 코드/설비는 모두 강의용 가짜 값입니다.
    """
    # query를 소문자로 만들어 키워드 포함 여부를 대소문자 구분 없이 검사합니다.
    query = (user_query or "").lower()

    # [mock_library 의 목적과 구조 — 코드 해석을 돕기 위한 설명]
    #   - 이 목록은 "(검색을 트리거하는 키워드들) → (돌려줄 교육용 Chunk)" 쌍의 모음입니다.
    #   - 실제 Vector DB를 흉내 내되, 의미 검색이 아니라 단순 키워드 포함 검사로 동작합니다.
    #     (환경이 없어도 수업 흐름이 끊기지 않게 하려는 의도적 단순화입니다.)
    #   - 각 Chunk는 실제 Chroma 결과와 같은 형태(chunk_id/text/metadata/distance/source)를
    #     갖도록 만들어, 이후 rerank·채점 단계가 mock/chroma를 구분 없이 처리할 수 있습니다.
    #   - 여기 등장하는 알람 코드/설비/공정명은 모두 강의용 가짜 값입니다(개별 text 의미는
    #     수업에서 자연어로 읽으면 되므로, 줄마다 따로 주석을 달지 않습니다).
    mock_library: list[tuple[list[str], dict]] = [
        (
            ["alm-temp-402", "온도"],
            {
                "chunk_id": "mock-temp-001",
                "text": (
                    "ALM-TEMP-402는 증착 설비에서 온도 상승이 반복 감지될 때 발생하는 알람입니다. "
                    "온도 알람이 반복되면 냉각 계통과 온도 센서 상태를 먼저 확인하고, "
                    "반복 발생 시간대와 공정 상태 변화를 비교해 조치 절차를 적용해야 합니다."
                ),
                "metadata": {
                    "alarm_code": "ALM-TEMP-402",
                    "equipment_type": "증착 설비",
                    "symptom": "온도 상승",
                },
                "distance": None,
                "source": "mock",
            },
        ),
        (
            ["eqp-vd-03"],
            {
                "chunk_id": "mock-eqp-vd-03",
                "text": (
                    "EQP-VD-03에서 온도 상승 알람이 계속 발생하면 냉각수 흐름, 온도 센서 보정 상태, "
                    "히터 출력 이상 여부를 우선 확인해야 합니다. 증상은 온도 상승으로 분류합니다."
                ),
                "metadata": {
                    "equipment_id": "EQP-VD-03",
                    "symptom": "온도 상승",
                    "equipment_type": "증착 설비",
                },
                "distance": None,
                "source": "mock",
            },
        ),
        (
            ["압력", "alm-press-105"],
            {
                "chunk_id": "mock-press-105",
                "text": (
                    "ALM-PRESS-105 및 압력 불안정 알람은 챔버 압력 편차, 진공도 이상과 함께 나타날 수 있습니다. "
                    "압력 계통에서 밸브, 펌프, 배관 누설을 점검하고 관련 조치 기준 문서를 함께 확인합니다."
                ),
                "metadata": {
                    "alarm_code": "ALM-PRESS-105",
                    "equipment_id": "EQP-CVD-02",
                    "symptom": "압력 불안정",
                },
                "distance": None,
                "source": "mock",
            },
        ),
        (
            ["alm-3091"],
            {
                "chunk_id": "mock-3091",
                "text": (
                    "ALM-3091은 품질 지표 저하와 연관될 수 있는 알람으로, 품질 기준 문서와 함께 검토해야 합니다. "
                    "알람 발생 시점의 수율, 검사 결과 변화 등 품질 지표 저하 근거를 확인합니다."
                ),
                "metadata": {
                    "alarm_code": "ALM-3091",
                    "quality_related": True,
                },
                "distance": None,
                "source": "mock",
            },
        ),
        (
            ["세정"],
            {
                "chunk_id": "mock-clean-001",
                "text": (
                    "세정 설비에서 반복 알람이 발생하면 정비 이력과 함께 조치 기준 문서를 참고해야 합니다. "
                    "반복 알람은 최근 정비 내역, 부품 교체 이력과 연결해 원인을 좁혀 갑니다."
                ),
                "metadata": {
                    "equipment_type": "세정 설비",
                    "requires_maintenance_context": True,
                },
                "distance": None,
                "source": "mock",
            },
        ),
        (
            ["etch"],
            {
                "chunk_id": "mock-etch-001",
                "text": (
                    "ETCH 공정에서 불량률이 상승하면 품질 기준 문서를 확인해 수율 저하 및 검사 결과 변화와 "
                    "연결해 분석해야 합니다. 공정명과 품질 관련 metadata를 함께 사용합니다."
                ),
                "metadata": {
                    "process_name": "ETCH",
                    "quality_related": True,
                },
                "distance": None,
                "source": "mock",
            },
        ),
        (
            ["alm-1052"],
            {
                "chunk_id": "mock-1052",
                "text": (
                    "ALM-1052 압력 알람은 단발 발생과 반복 발생의 적용 절차가 다릅니다. "
                    "한 번만 발생한 경우와 반복 발생한 경우의 절차 적용 기준을 구분해 확인해야 합니다."
                ),
                "metadata": {
                    "alarm_code": "ALM-1052",
                    "symptom": "압력 불안정",
                },
                "distance": None,
                "source": "mock",
            },
        ),
        (
            ["검색 결과가 부족", "부족", "추가 확인"],
            {
                "chunk_id": "mock-lowconf-001",
                "text": (
                    "검색 결과가 부족할 때는 원인을 단정하지 말고 추가 확인이 필요하다고 표시해야 합니다. "
                    "근거가 충분하지 않으면 low confidence 상태로 다루어야 합니다."
                ),
                "metadata": {
                    "requires_uncertainty_handling": True,
                },
                "distance": None,
                "source": "mock",
            },
        ),
    ]

    # 질문에 포함된 키워드에 해당하는 Chunk들을 모읍니다(중복 chunk_id는 한 번만).
    matched_chunks: list[dict] = []
    seen_ids: set[str] = set()
    for keywords, chunk in mock_library:
        if any(keyword in query for keyword in keywords):
            if chunk["chunk_id"] not in seen_ids:
                matched_chunks.append(chunk)
                seen_ids.add(chunk["chunk_id"])

    # 없는 알람 코드(ALM-9999)처럼 명시적으로 "근거 없음"을 보여 줘야 하는 경우:
    #   - 매칭된 게 없으면 빈 리스트를 돌려줘 "검색 결과 없음"으로 평가되게 합니다.
    if not matched_chunks:
        return []

    return matched_chunks


# ──────────────────────────────────────────────────────────────────────
# 4. 통합 검색 함수 (Chroma 우선, 실패 시 mock fallback)
# ──────────────────────────────────────────────────────────────────────
def retrieve_chunks(user_query: str, config: dict) -> tuple[list[dict], dict]:
    """
    설정(config)에 따라 Chroma 또는 mock 검색을 수행하고, 사용된 경로 정보까지 돌려줍니다.

    반환: (chunks, retrieval_info)
        retrieval_info 에는 어떤 경로(used_source)를 썼는지, fallback이 일어났는지,
        그 사유는 무엇인지 등을 담아 결과/보고서에서 추적할 수 있게 합니다.

    분기 규칙:
        - mode == "mock"   → 처음부터 mock만 사용
        - mode == "chroma" → Chroma 먼저 시도
            · Chroma 기술적 실패(사유 있음) → mock fallback (사유 기록)
            · Chroma 성공(결과 0건 포함)     → 그 결과를 그대로 사용 (fallback 안 함)

    [왜 used_source / fallback_used 를 따로 기록하나 — 강의 맥락에서 확인할 포인트]
        - 결과만 보면 "이 점수가 실제 Chroma 검색에서 나온 것인지, mock fallback에서 나온
          것인지" 구분할 수 없습니다. 그래서 어떤 경로를 썼는지를 retrieval_info에 남겨
          보고서에서 추적할 수 있게 합니다. (mock 결과를 실제 검색 품질로 오해하지 않도록)
    """
    top_k = config.get("top_k", 3)
    collection_name = config.get("collection_name", DEFAULT_CHROMA_COLLECTION_NAME)
    persist_dir = config.get("chroma_persist_dir", str(DEFAULT_CHROMA_PERSIST_DIR))
    mode = config.get("mode", "chroma")

    # retrieval_info의 공통 뼈대를 먼저 만들어 둡니다(아래에서 값만 채움).
    retrieval_info = {
        "mode": mode,
        "used_source": None,
        "fallback_used": False,
        "fallback_reason": None,
        "top_k": top_k,
        "collection_name": collection_name,
        "persist_dir": str(persist_dir),
    }

    # (A) mock 모드: Chroma를 아예 시도하지 않고 mock만 사용합니다.
    if mode == "mock":
        chunks = mock_retrieve_chunks(user_query)
        retrieval_info["used_source"] = "mock"
        return chunks, retrieval_info

    # (B) chroma 모드: 먼저 Chroma를 시도합니다.
    chunks, error_reason = chroma_retrieve_chunks(
        user_query=user_query,
        top_k=top_k,
        persist_dir=Path(persist_dir),
        collection_name=collection_name,
    )

    # (B-1) 기술적 실패(error_reason이 있음) → mock fallback
    if error_reason is not None:
        mock_chunks = mock_retrieve_chunks(user_query)
        retrieval_info["used_source"] = "mock"
        retrieval_info["fallback_used"] = True
        retrieval_info["fallback_reason"] = error_reason
        return mock_chunks, retrieval_info

    # (B-2) Chroma 성공(결과가 0건이어도 여기로 옴) → 그대로 사용, fallback 하지 않음
    retrieval_info["used_source"] = "chroma"
    return chunks, retrieval_info
