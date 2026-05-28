# Day2 Markdown 문서 로드 결과

## 1. 로드 요약

- 읽은 문서 수: 3
- 전체 문단 수: 290
- 전체 글자 수: 23827

## 2. 문서별 요약

### alarm_manual.md

- 파일명: alarm_manual.md
- 글자 수: 8156
- 문단 수: 137

### quality_standard.md

- 파일명: quality_standard.md
- 글자 수: 7520
- 문단 수: 75

### troubleshooting_guide.md

- 파일명: troubleshooting_guide.md
- 글자 수: 8151
- 문단 수: 78

## 3. 다음 단계 안내

다음 단계에서는 `chunk_builder.py`를 실행해 문단을 chunk로 나누고 metadata를 생성합니다.

문서 로더가 Markdown 파일을 읽어 문단 단위로 정리하면, chunk_builder.py는 이 문단을 검색하기 좋은 작은 단위로 나눕니다.

이후 RAG 검색 단계에서는 사용자의 질문과 관련이 높은 chunk를 찾아 AI Agent 답변의 근거로 사용합니다.
