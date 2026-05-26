# -*- coding: utf-8 -*-
"""
2일차 RAG 실습 - Markdown 문서 로더

이 파일은 Day2 RAG 실습의 첫 번째 단계인 "Markdown 문서 로드"만 담당합니다.

RAG는 Retrieval-Augmented Generation의 줄임말입니다.
쉽게 말하면, AI Agent가 답변하기 전에 관련 문서를 먼저 찾아보고
그 문서를 근거로 답변하도록 만드는 방식입니다.

이 문서 로더는 docs 폴더에 있는 Markdown(.md) 파일을 읽고,
파일명, 글자 수, 문단 수를 정리한 뒤 결과 Markdown 파일로 저장합니다.

실행 명령어:
python src/day2/rag_document_loader_YYYYMMDD_HHMMSS.py
"""

import logging
from pathlib import Path


# logging은 Java의 log.info()와 비슷하게 실행 과정을 남기는 기능입니다.
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)


def get_project_root():
    """
    현재 파일 위치를 기준으로 프로젝트 루트 경로를 찾습니다.

    pathlib.Path는 파일과 폴더 경로를 다루기 쉽게 해 주는 Python 도구입니다.
    프로젝트 폴더가 C 드라이브, F 드라이브 등 어디로 이동해도 동작하도록
    특정 경로를 코드에 직접 쓰지 않습니다.
    """
    current_file = Path(__file__).resolve()

    for parent in [current_file.parent] + list(current_file.parents):
        src_dir = parent / "src"
        docs_dir = parent / "docs"
        outputs_dir = parent / "outputs"

        if src_dir.exists() and (docs_dir.exists() or outputs_dir.exists()):
            return parent

    # 프로젝트 루트를 찾지 못하면 현재 파일 기준 두 단계 위를 기본값으로 사용합니다.
    return current_file.parents[2]


def load_documents(project_root):
    """
    docs 폴더의 Markdown(.md) 파일을 읽고 문서 정보를 리스트로 반환합니다.

    문단은 빈 줄 기준으로 나눕니다.
    여기서는 "문서 로드"만 다루므로 키워드 분석이나 제목 수 계산은 하지 않습니다.
    """
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        logger.warning("docs 폴더를 찾을 수 없습니다.")
        logger.warning("프로젝트 루트 아래에 docs 폴더를 만들고 Markdown 문서를 넣어 주세요.")
        return []

    markdown_files = sorted(docs_dir.glob("*.md"))

    if not markdown_files:
        logger.warning("docs 폴더에 Markdown(.md) 문서가 없습니다.")
        logger.warning("docs 폴더에 실습용 Markdown 문서를 추가한 뒤 다시 실행해 주세요.")
        return []

    results = []

    for file_path in markdown_files:
        logger.info("Markdown 문서를 읽는 중입니다: %s", file_path.name)

        text = file_path.read_text(encoding="utf-8-sig")

        paragraphs = []
        for block in text.split("\n\n"):
            paragraph = block.strip()
            if paragraph:
                paragraphs.append(paragraph)

        results.append(
            {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "char_count": len(text),
                "paragraph_count": len(paragraphs),
                "paragraphs": paragraphs,
            }
        )

    return results


def save_result_markdown(results, output_path):
    """
    문서 로드 결과를 outputs/day2/document_load_result.md 파일로 저장합니다.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_paragraphs = sum(item["paragraph_count"] for item in results)
    total_chars = sum(item["char_count"] for item in results)

    lines = []
    lines.append("# Day2 Markdown 문서 로드 결과")
    lines.append("")
    lines.append("## 1. 로드 요약")
    lines.append("")
    lines.append(f"- 읽은 문서 수: {len(results)}")
    lines.append(f"- 전체 문단 수: {total_paragraphs}")
    lines.append(f"- 전체 글자 수: {total_chars}")
    lines.append("")
    lines.append("## 2. 문서별 요약")
    lines.append("")

    if not results:
        lines.append("- 분석할 Markdown 문서가 없습니다.")
        lines.append("- docs 폴더에 Markdown 문서를 추가한 뒤 다시 실행해 주세요.")
        lines.append("")
    else:
        for item in results:
            lines.append(f"### {item['file_name']}")
            lines.append("")
            lines.append(f"- 파일명: {item['file_name']}")
            lines.append(f"- 글자 수: {item['char_count']}")
            lines.append(f"- 문단 수: {item['paragraph_count']}")
            lines.append("")

    lines.append("## 3. 다음 단계 안내")
    lines.append("")
    lines.append("다음 단계에서는 `chunk_builder.py`를 실행해 문단을 chunk로 나누고 metadata를 생성합니다.")
    lines.append("")
    lines.append("문서 로더가 Markdown 파일을 읽어 문단 단위로 정리하면, chunk_builder.py는 이 문단을 검색하기 좋은 작은 단위로 나눕니다.")
    lines.append("")
    lines.append("이후 RAG 검색 단계에서는 사용자의 질문과 관련이 높은 chunk를 찾아 AI Agent 답변의 근거로 사용합니다.")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8-sig")


def main():
    """
    전체 실행 흐름을 담당합니다.

    1. 프로젝트 루트를 찾습니다.
    2. docs 폴더의 Markdown 문서를 읽습니다.
    3. 결과를 outputs/day2/document_load_result.md 파일로 저장합니다.
    4. 다음 단계인 chunk_builder.py 실행을 안내합니다.
    """
    project_root = get_project_root()
    output_path = project_root / "outputs" / "day2" / "document_load_result.md"

    logger.info("Day2 RAG Markdown 문서 로드를 시작합니다.")
    logger.info("프로젝트 루트: %s", project_root)

    results = load_documents(project_root)
    save_result_markdown(results, output_path)

    logger.info("문서 로드 결과를 저장했습니다: %s", output_path)
    logger.info("다음 단계에서는 chunk_builder.py를 실행해 문단을 chunk로 나누고 metadata를 생성합니다.")


if __name__ == "__main__":
    main()
