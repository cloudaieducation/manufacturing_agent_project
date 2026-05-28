# Day2 Chroma Vector DB 생성 결과 (선택/확장 실습)

Chroma 인덱스 생성은 선택/확장 실습입니다. 2일차의 기본 목표는 Vector DB 구축 자체가
아니라, 검색 결과가 State(retrieved_docs)와 Trace로 어떻게 연결되는지 이해하는 것입니다.
Chroma/Ollama 실행 오류가 나면 강사 데모 또는 미리 저장된 검색 결과로 진행하는
Saved Result Review로 대체할 수 있습니다.

## 1. 생성 요약

- 읽은 chunk 수: 201
- Chroma DB 저장 경로: `C:\work\manufacturing_agent_project\vector_db\chroma_db`
- Chroma collection 이름: `manufacturing_rag_docs`
- Chroma collection 저장 개수: 201
- Embedding provider: Ollama
- Embedding model: `nomic-embed-text:latest`
- Embedding API URL: `http://localhost:11434/api/embeddings`

## 2. 문서별 chunk 수

| 문서명 | chunk 수 |
|---|---:|
| alarm_manual.md | 78 |
| quality_standard.md | 60 |
| troubleshooting_guide.md | 63 |

## 3. Chroma 저장 구조 설명

- `documents`에는 chunk text가 저장됩니다.
- `ids`에는 `chunk_id`가 저장됩니다.
- `metadatas`에는 문서명, 섹션명, 알람 코드, 설비 ID, 키워드 등이 저장됩니다.
- CSV를 검색하는 것이 아니라 Chroma Vector DB에서 의미 기반 검색을 수행합니다.
- 저장할 때와 검색할 때 같은 embedding 모델을 사용해야 합니다.

## 4. Ollama 사전 준비 명령어

```bash
ollama list
ollama pull nomic-embed-text
ollama serve
```

## 5. 다음 단계 안내

다음 단계에서는 `rag_search.py`에서도 같은 embedding 모델과 URL을 사용해 Chroma Vector DB를 검색합니다.
