# -*- coding: utf-8 -*-
"""
2일차 RAG 실습 - Chroma Vector DB 기반 RAG 검색기

이 파일은 Chroma Vector DB에서 질문과 관련 있는 Top-3 문서 chunk를 검색합니다.
검색에는 Ollama의 nomic-embed-text:latest embedding 모델을 사용합니다.

실행 흐름:
sample_rag_queries.json 읽기
→ 질문 embedding 생성
→ Chroma Vector DB Top-K 검색
→ Mustache 템플릿으로 outputs/day2/rag_test_results.md 저장

필요 패키지:
pip install chromadb
pip install pystache

Ollama 사전 준비 명령어:
ollama list
ollama pull nomic-embed-text
ollama serve

실행 명령어:
python src/day2/rag_search_20260524_034616.py
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import pystache


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


DEFAULT_COLLECTION_NAME = "manufacturing_rag_docs"
DEFAULT_TOP_K = 3

# 저장할 때 사용한 embedding 모델과 검색할 때 사용하는 embedding 모델은 같아야 합니다.
OLLAMA_EMBEDDING_MODEL = "nomic-embed-text:latest"
OLLAMA_EMBEDDING_URL = "http://localhost:11434/api/embeddings"


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 폴더를 찾습니다.

    src 폴더가 있고, docs 또는 outputs 폴더가 있는 위치를 프로젝트 루트로 봅니다.
    프로젝트 폴더 위치가 바뀌어도 동작하도록 특정 경로를 하드코딩하지 않습니다.
    """
    current_file = Path(__file__).resolve()

    for parent in [current_file.parent, *current_file.parents]:
        has_src = (parent / "src").exists()
        has_docs_or_outputs = (parent / "docs").exists() or (parent / "outputs").exists()
        if has_src and has_docs_or_outputs:
            return parent

    return Path.cwd().resolve()


def load_sample_queries(query_path: Path) -> List[Dict[str, Any]]:
    """
    data/sample_rag_queries.json 파일에서 샘플 질의 목록을 읽습니다.
    """
    if not query_path.exists():
        logger.warning("샘플 질의 파일을 찾지 못했습니다: %s", query_path)
        return []

    query_data = json.loads(query_path.read_text(encoding="utf-8-sig"))

    if isinstance(query_data, dict):
        queries = query_data.get("queries", [])
    elif isinstance(query_data, list):
        queries = query_data
    else:
        queries = []

    if not isinstance(queries, list):
        logger.warning("sample_rag_queries.json의 queries 값이 리스트가 아닙니다.")
        return []

    return queries


class SimpleOllamaEmbeddingFunction:
    """
    질문 text를 Ollama embedding API로 보내 숫자 벡터로 바꾸는 도구입니다.

    Chroma는 이 숫자 벡터를 사용해 질문과 의미가 가까운 문서 chunk를 찾습니다.
    """

    def __init__(self, model_name: str, url: str, timeout_seconds: int = 60) -> None:
        self.model_name = model_name
        self.url = url
        self.timeout_seconds = timeout_seconds

    def name(self) -> str:
        """Chroma가 embedding function을 구분할 때 사용하는 이름입니다."""
        return "simple_ollama_nomic_embed_text"

    def __call__(self, input: List[str]) -> List[List[float]]:
        """여러 문장을 embedding 리스트로 변환합니다."""
        return self.embed_documents(input)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """문서 또는 질문 목록을 embedding 리스트로 변환합니다."""
        return [self._request_embedding(str(text or "")) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        """검색 질문 하나를 embedding으로 변환합니다."""
        return self._request_embedding(str(text or ""))

    def _request_embedding(self, text: str) -> List[float]:
        """Ollama embedding API를 호출해 embedding 숫자 리스트를 받습니다."""
        payload = {
            "model": self.model_name,
            "prompt": text,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_text = response.read().decode("utf-8")
        except urllib.error.URLError as error:
            logger.error("Ollama 서버에 연결하지 못했습니다.")
            logger.error("확인 명령어: ollama serve")
            logger.error("모델 설치 명령어: ollama pull nomic-embed-text")
            raise RuntimeError(f"Ollama embedding API 연결 오류: {error}") from error

        response_json = json.loads(response_text)
        embedding = response_json.get("embedding")

        if not isinstance(embedding, list) or not embedding:
            raise RuntimeError(
                "Ollama 응답에서 embedding 필드를 찾지 못했습니다. "
                "모델명과 Ollama API 상태를 확인해 주세요."
            )

        return [float(value) for value in embedding]


def get_chroma_collection(chroma_dir: Path, collection_name: str):
    """
    Chroma PersistentClient를 만들고 collection을 반환합니다.
    """
    try:
        import chromadb
    except ImportError:
        logger.error("chromadb 패키지가 설치되어 있지 않습니다.")
        logger.error("설치 명령: pip install chromadb")
        return None

    if not chroma_dir.exists():
        logger.warning("Chroma Vector DB 폴더를 찾지 못했습니다: %s", chroma_dir)
        logger.warning("먼저 chroma_index_builder_날짜_시간.py를 실행해 Chroma DB를 생성해 주세요.")
        logger.warning("Ollama 준비 명령어: ollama list, ollama pull nomic-embed-text, ollama serve")
        return None

    client = chromadb.PersistentClient(path=str(chroma_dir))

    try:
        return client.get_collection(name=collection_name)
    except Exception as error:
        logger.warning("Chroma collection을 열지 못했습니다: %s", collection_name)
        logger.warning("먼저 chroma_index_builder_날짜_시간.py를 실행해 Chroma DB를 생성해 주세요.")
        logger.warning("chromadb 설치 여부를 확인해 주세요: pip install chromadb")
        logger.warning("Ollama 준비 명령어: ollama list, ollama pull nomic-embed-text, ollama serve")
        logger.warning("참고 오류: %s", str(error)[:500])
        return None


def distance_to_score(distance: Any) -> float:
    """
    Chroma distance를 수강생이 보기 쉬운 score로 변환합니다.

    distance는 작을수록 더 가까운 결과이고, score는 클수록 더 좋은 결과입니다.
    """
    try:
        distance_value = float(distance)
    except (TypeError, ValueError):
        return 0.0

    if distance_value < 0:
        distance_value = 0.0

    return round(1 / (1 + distance_value), 4)


def search_top_k(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    chroma_dir: Optional[Path] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> List[Dict[str, Any]]:
    """
    사용자 질문을 받아 Chroma Vector DB에서 Top-K 관련 chunk를 검색합니다.
    """

    def preview_text(text: str, max_length: int = 180) -> str:
        one_line_text = " ".join(str(text or "").split())
        if len(one_line_text) <= max_length:
            return one_line_text
        return one_line_text[:max_length] + "..."

    if not query or not query.strip():
        return []

    project_root = get_project_root()
    chroma_dir = chroma_dir or (project_root / "vector_db" / "chroma_db")

    collection = get_chroma_collection(chroma_dir, collection_name)
    if collection is None:
        return []

    embedding_function = SimpleOllamaEmbeddingFunction(
        model_name=OLLAMA_EMBEDDING_MODEL,
        url=OLLAMA_EMBEDDING_URL,
    )
    query_embedding = embedding_function.embed_query(query)

    query_result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    ids = (query_result.get("ids") or [[]])[0]
    documents = (query_result.get("documents") or [[]])[0]
    metadatas = (query_result.get("metadatas") or [[]])[0]
    distances = (query_result.get("distances") or [[]])[0]

    results: List[Dict[str, Any]] = []

    for index, chunk_id in enumerate(ids):
        text = documents[index] if index < len(documents) else ""
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        distance = distances[index] if index < len(distances) else None

        try:
            distance_value = round(float(distance), 4) if distance is not None else 0.0
        except (TypeError, ValueError):
            distance_value = 0.0

        results.append(
            {
                "rank": index + 1,
                "score": distance_to_score(distance),
                "distance": distance_value,
                "chunk_id": str(chunk_id),
                "doc_name": str(metadata.get("doc_name", "") or ""),
                "section_title": str(metadata.get("section_title", "") or ""),
                "alarm_code": str(metadata.get("alarm_code", "") or ""),
                "equipment_id": str(metadata.get("equipment_id", "") or ""),
                "keywords": str(metadata.get("keywords", "") or ""),
                "text": str(text or ""),
                "preview": preview_text(str(text or "")),
            }
        )

    return results


def run_sample_queries() -> List[Dict[str, Any]]:
    """
    data/sample_rag_queries.json의 샘플 질의를 실행합니다.
    """
    project_root = get_project_root()
    query_path = project_root / "data" / "sample_rag_queries.json"
    queries = load_sample_queries(query_path)

    if not queries:
        return []

    all_results: List[Dict[str, Any]] = []

    for query_item in queries:
        user_query = str(query_item.get("user_query", "") or "")
        search_results = search_top_k(user_query, top_k=DEFAULT_TOP_K)

        all_results.append(
            {
                "query_id": str(query_item.get("id", "") or ""),
                "user_query": user_query,
                "intent": str(query_item.get("intent", "") or ""),
                "difficulty": str(query_item.get("difficulty", "") or ""),
                "expected_keywords": query_item.get("expected_keywords", []),
                "expected_docs": query_item.get("expected_docs", []),
                "search_results": search_results,
            }
        )

    return all_results


def save_results(
    results: List[Dict[str, Any]],
    output_md_path: Path,
    template_path: Path,
) -> None:
    """
    Mustache 템플릿을 사용해 outputs/day2/rag_test_results.md 파일을 저장합니다.
    """

    def format_list(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value or "")

    def escape_table_text(value: Any) -> str:
        return str(value or "").replace("\n", " ").replace("|", "/")

    if not template_path.exists():
        logger.warning("Mustache 템플릿 파일을 찾지 못했습니다: %s", template_path)
        logger.warning("templates/day2/rag_test_results.mustache 파일을 먼저 생성해 주세요.")
        return

    project_root = get_project_root()
    chroma_dir = project_root / "vector_db" / "chroma_db"

    rendered_results: List[Dict[str, Any]] = []
    for item in results:
        search_results = item.get("search_results", [])
        rendered_search_results = []

        for result in search_results:
            rendered_search_results.append(
                {
                    "rank": result.get("rank", ""),
                    "score": result.get("score", ""),
                    "distance": result.get("distance", ""),
                    "doc_name": escape_table_text(result.get("doc_name", "")),
                    "section_title": escape_table_text(result.get("section_title", "")),
                    "chunk_id": escape_table_text(result.get("chunk_id", "")),
                    "keywords": escape_table_text(result.get("keywords", "")),
                    "preview": escape_table_text(result.get("preview", "")),
                }
            )

        rendered_results.append(
            {
                "query_id": str(item.get("query_id", "") or ""),
                "user_query": str(item.get("user_query", "") or ""),
                "intent": str(item.get("intent", "") or ""),
                "difficulty": str(item.get("difficulty", "") or ""),
                "expected_keywords_text": format_list(item.get("expected_keywords", [])),
                "expected_docs_text": format_list(item.get("expected_docs", [])),
                "has_search_results": bool(rendered_search_results),
                "search_results": rendered_search_results,
            }
        )

    template_data = {
        "chroma_dir": str(chroma_dir),
        "collection_name": DEFAULT_COLLECTION_NAME,
        "embedding_provider": "Ollama",
        "embedding_model": OLLAMA_EMBEDDING_MODEL,
        "embedding_api_url": OLLAMA_EMBEDDING_URL,
        "result_count": len(results),
        "results": rendered_results,
        "has_results": bool(rendered_results),
    }

    template_text = template_path.read_text(encoding="utf-8-sig")
    rendered_text = pystache.render(template_text, template_data)

    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text(rendered_text, encoding="utf-8-sig")


def main() -> None:
    """
    단독 실행 시 sample_rag_queries.json을 읽고 RAG 검색 테스트를 수행합니다.
    """
    project_root = get_project_root()
    query_path = project_root / "data" / "sample_rag_queries.json"
    output_md_path = project_root / "outputs" / "day2" / "rag_test_results.md"
    template_path = project_root / "templates" / "day2" / "rag_test_results.mustache"

    logger.info("Day2 Chroma RAG 검색을 시작합니다.")
    logger.info("프로젝트 루트: %s", project_root)
    logger.info("샘플 질의 파일: %s", query_path)
    logger.info("검색 결과 파일: %s", output_md_path)

    results = run_sample_queries()
    save_results(results, output_md_path, template_path)

    logger.info("검색 완료. 질의 수: %s", len(results))
    logger.info("검색 결과 파일: %s", output_md_path)

    if not results:
        logger.warning("실행된 검색 결과가 없습니다. sample_rag_queries.json과 Chroma DB 생성 여부를 확인해 주세요.")


if __name__ == "__main__":
    main()
