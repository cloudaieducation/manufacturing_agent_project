# -*- coding: utf-8 -*-
"""
2일차 RAG 실습 - LangGraph State 구조 정의

State는 Agent가 작업하면서 들고 다니는 작업 파일입니다.
LangGraph에서는 각 Node가 State를 읽고, 필요한 값을 추가하거나 수정합니다.

이번 파일은 실제 LangGraph 그래프를 실행하지 않습니다.
또한 Chroma Vector DB를 직접 검색하지 않습니다.

이 파일의 목적은 다음 단계 langgraph_rag_graph_runner.py에서 사용할
State의 모양을 미리 정의하는 것입니다.

중요한 흐름은 다음과 같습니다.

1. 사용자 질문이 user_query에 저장됩니다.
2. parse_query_node가 설비 ID와 알람 코드를 추출합니다.
3. retrieve_docs_node가 rag_search.py의 search_top_k()를 호출합니다.
4. Chroma Vector DB에서 검색된 Top-3 문서 조각이 retrieved_docs에 저장됩니다.
5. generate_answer_node가 retrieved_docs를 근거로 답변 초안을 만듭니다.
6. verify_grounding_node가 검색 근거가 있는지 확인합니다.
7. trace에는 각 Node가 어떤 일을 했는지 실행 이력이 저장됩니다.

CSV 검색 결과가 아니라 Chroma Vector DB 검색 결과가 retrieved_docs에 들어간다는 점이 중요합니다.

필요 패키지:
pip install pystache

실행 명령어:
python src/day2/graph_state_20260524_040615.py
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pystache

try:
    from typing_extensions import TypedDict
except ImportError:
    from typing import TypedDict


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class RetrievedDoc(TypedDict):
    """
    Chroma Vector DB 검색 결과 1개를 표현합니다.

    TypedDict는 딕셔너리의 '필드 이름과 값의 타입'을 미리 정해두는 방법입니다.
    초보자 관점에서는 '정해진 양식이 있는 dict'라고 이해하면 됩니다.
    """

    rank: int
    score: float
    distance: float
    chunk_id: str
    doc_name: str
    section_title: str
    alarm_code: str
    equipment_id: str
    keywords: str
    text: str
    preview: str


class NodeTrace(TypedDict):
    """
    LangGraph Node 실행 기록 1개를 표현합니다.

    trace는 Agent가 어떤 순서로 어떤 일을 했는지 확인하는 실행 이력입니다.
    나중에 오류 분석이나 수강생 실습 결과 확인에 도움이 됩니다.
    """

    node_name: str
    status: str
    message: str
    input_summary: str
    output_summary: str


class ManufacturingRAGState(TypedDict):
    """
    LangGraph StateGraph 전체에서 공유되는 State를 표현합니다.

    State는 각 Node 사이를 이동하는 작업 상태입니다.
    Node는 State를 읽고 필요한 값을 채운 뒤 다음 Node로 넘깁니다.
    """

    user_query: str
    rewritten_query: str
    equipment_id: str
    alarm_code: str
    retrieved_docs: List[RetrievedDoc]
    draft_answer: str
    final_answer: str
    grounding_status: str
    needs_rewrite: bool
    retry_count: int
    errors: List[str]
    trace: List[NodeTrace]


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 경로를 찾습니다.

    보통 이 파일은 src/day2/graph_state_날짜_시간.py 위치에 있습니다.
    부모 폴더를 올라가며 src 폴더와 docs 또는 outputs 폴더가 있는 위치를 찾습니다.
    """
    current_path = Path(__file__).resolve()

    for parent in [current_path.parent, *current_path.parents]:
        has_src = (parent / "src").exists()
        has_docs_or_outputs = (parent / "docs").exists() or (parent / "outputs").exists()
        if has_src and has_docs_or_outputs:
            return parent

    return Path.cwd().resolve()


def create_initial_state(user_query: str) -> ManufacturingRAGState:
    """
    사용자 질문으로 초기 State를 생성합니다.

    처음에는 사용자 질문만 있고,
    설비 ID, 알람 코드, 검색 결과, 답변, trace는 아직 비어 있습니다.
    """
    return {
        "user_query": user_query,
        "rewritten_query": "",
        "equipment_id": "",
        "alarm_code": "",
        "retrieved_docs": [],
        "draft_answer": "",
        "final_answer": "",
        "grounding_status": "not_checked",
        "needs_rewrite": False,
        "retry_count": 0,
        "errors": [],
        "trace": [],
    }


def add_trace(
    state: ManufacturingRAGState,
    node_name: str,
    status: str,
    message: str,
    input_summary: str = "",
    output_summary: str = "",
) -> ManufacturingRAGState:
    """
    Node 실행 기록을 State의 trace 목록에 추가합니다.

    여기서는 초보자가 이해하기 쉽도록 원본 State를 직접 수정합니다.
    LangGraph Node 안에서 이 함수를 호출하면,
    어떤 Node가 어떤 입력을 받고 어떤 결과를 만들었는지 기록할 수 있습니다.
    """
    trace_item: NodeTrace = {
        "node_name": node_name,
        "status": status,
        "message": message,
        "input_summary": input_summary,
        "output_summary": output_summary,
    }

    state["trace"].append(trace_item)
    return state


def summarize_retrieved_docs(retrieved_docs: List[RetrievedDoc]) -> str:
    """
    retrieved_docs 목록을 사람이 보기 쉬운 짧은 문자열로 요약합니다.

    retrieved_docs에는 Chroma Vector DB에서 검색한 Top-3 문서 조각이 들어갑니다.
    text 전체는 길 수 있으므로 doc_name, section_title, score, preview 중심으로 요약합니다.
    """
    if not retrieved_docs:
        return "검색된 문서 조각이 없습니다."

    lines: List[str] = []

    for doc in retrieved_docs:
        lines.append(
            f"{doc.get('rank', '')}. "
            f"{doc.get('doc_name', '')} / "
            f"{doc.get('section_title', '')} / "
            f"score={doc.get('score', 0)} / "
            f"{doc.get('preview', '')}"
        )

    return "\n".join(lines)


def save_results(
    state: ManufacturingRAGState,
    output_path: Path,
    template_path: Path,
) -> None:
    """
    Mustache 템플릿을 사용해 State 데모 결과 Markdown 파일을 저장합니다.
    """
    if not template_path.exists():
        logger.warning("Mustache 템플릿 파일을 찾지 못했습니다: %s", template_path)
        logger.warning("templates/day2/state_demo_result.mustache 파일을 먼저 생성해 주세요.")
        return

    retrieved_docs = [
        {
            "rank": doc.get("rank", ""),
            "score": doc.get("score", ""),
            "doc_name": doc.get("doc_name", ""),
            "section_title": doc.get("section_title", ""),
            "chunk_id": doc.get("chunk_id", ""),
            "keywords": doc.get("keywords", ""),
            "preview": doc.get("preview", ""),
        }
        for doc in state.get("retrieved_docs", [])
    ]

    trace_items = [
        {
            "node_name": item.get("node_name", ""),
            "status": item.get("status", ""),
            "message": item.get("message", ""),
            "input_summary": item.get("input_summary", ""),
            "output_summary": item.get("output_summary", ""),
        }
        for item in state.get("trace", [])
    ]

    template_data = {
        "user_query": state.get("user_query", ""),
        "rewritten_query": state.get("rewritten_query", ""),
        "equipment_id": state.get("equipment_id", ""),
        "alarm_code": state.get("alarm_code", ""),
        "grounding_status": state.get("grounding_status", ""),
        "needs_rewrite": state.get("needs_rewrite", False),
        "retry_count": state.get("retry_count", 0),
        "errors_text": ", ".join(state.get("errors", [])) if state.get("errors", []) else "없음",
        "retrieved_docs": retrieved_docs,
        "trace_items": trace_items,
        "has_retrieved_docs": bool(retrieved_docs),
        "has_trace_items": bool(trace_items),
    }

    template_text = template_path.read_text(encoding="utf-8-sig")
    rendered_text = pystache.render(template_text, template_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered_text, encoding="utf-8-sig")


def demo_state_flow() -> ManufacturingRAGState:
    """
    수강생이 State 변화를 이해할 수 있도록 샘플 State를 생성합니다.

    이 함수는 Chroma 검색을 실행하지 않습니다.
    retrieved_docs 예시를 직접 넣어 State 구조만 보여줍니다.
    """
    user_query = "EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘"
    state = create_initial_state(user_query)

    add_trace(
        state,
        node_name="create_initial_state",
        status="success",
        message="사용자 질문으로 초기 State를 생성했습니다.",
        input_summary=user_query,
        output_summary="user_query가 State에 저장되었습니다.",
    )

    state["equipment_id"] = "EQP-EV-03"
    state["alarm_code"] = "ALM-TEMP-402"

    add_trace(
        state,
        node_name="parse_query_node",
        status="success",
        message="질문에서 설비 ID와 알람 코드를 추출한 예시입니다.",
        input_summary=state["user_query"],
        output_summary="equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402",
    )

    state["retrieved_docs"] = [
        {
            "rank": 1,
            "score": 0.8123,
            "distance": 0.2311,
            "chunk_id": "CHUNK-0007",
            "doc_name": "troubleshooting_guide.md",
            "section_title": "ALM-TEMP-402 온도 상승 반복 알람 개요",
            "alarm_code": "ALM-TEMP-402",
            "equipment_id": "EQP-EV-03",
            "keywords": "ALM-TEMP-402, EQP-EV-03, 온도 상승, 반복 알람, 원인 후보",
            "text": "ALM-TEMP-402 반복 알람은 온도 상승, 냉각 상태, 공정 부하, 센서 값 변동 가능성을 함께 확인해야 한다는 교육용 문단입니다.",
            "preview": "ALM-TEMP-402 반복 알람은 온도 상승, 냉각 상태, 공정 부하, 센서 값 변동 가능성을 함께 확인해야 합니다.",
        },
        {
            "rank": 2,
            "score": 0.7642,
            "distance": 0.3085,
            "chunk_id": "CHUNK-0015",
            "doc_name": "quality_standard.md",
            "section_title": "품질 영향 확인 관점",
            "alarm_code": "ALM-TEMP-402",
            "equipment_id": "EQP-EV-03",
            "keywords": "품질 지표, 불량률, 수율, 검사 결과, 품질 영향",
            "text": "반복 알람 발생 전후의 품질 지표, 불량률, 수율, 검사 결과 변화를 함께 확인하되 직접 원인으로 단정하지 않아야 한다는 교육용 문단입니다.",
            "preview": "반복 알람 발생 전후의 품질 지표, 불량률, 수율, 검사 결과 변화를 함께 확인해야 합니다.",
        },
    ]

    add_trace(
        state,
        node_name="retrieve_docs_node",
        status="success",
        message="Chroma Vector DB 검색 결과가 retrieved_docs에 저장된 예시입니다.",
        input_summary="search_top_k(user_query, top_k=3)",
        output_summary=summarize_retrieved_docs(state["retrieved_docs"]),
    )

    state["draft_answer"] = (
        "검색된 문서 근거를 기준으로 볼 때, ALM-TEMP-402 반복 발생은 온도 상승, 냉각 상태, "
        "공정 부하, 센서 값 변동 가능성을 원인 후보로 검토할 수 있습니다. "
        "품질 영향은 불량률, 수율, 검사 결과 변화와 함께 추가 확인이 필요합니다."
    )

    add_trace(
        state,
        node_name="generate_answer_node",
        status="success",
        message="검색 근거를 바탕으로 답변 초안을 생성한 예시입니다.",
        input_summary="retrieved_docs 2건",
        output_summary="원인 후보와 품질 영향 확인 항목을 포함한 답변 초안 생성",
    )

    state["grounding_status"] = "grounded"
    state["needs_rewrite"] = False
    state["final_answer"] = state["draft_answer"]

    add_trace(
        state,
        node_name="verify_grounding_node",
        status="success",
        message="답변에 사용할 검색 근거가 존재한다고 판단한 예시입니다.",
        input_summary="draft_answer와 retrieved_docs",
        output_summary="grounding_status=grounded, needs_rewrite=False",
    )

    return state


def main() -> None:
    """
    단독 실행 시 State 구조 데모를 생성합니다.
    """
    logger.info("Day2 LangGraph State 구조 데모 생성을 시작합니다.")

    project_root = get_project_root()
    output_path = project_root / "outputs" / "day2" / "state_demo_result.md"
    template_path = project_root / "templates" / "day2" / "state_demo_result.mustache"

    state = demo_state_flow()
    save_results(state, output_path, template_path)

    logger.info("Day2 LangGraph State 구조 데모 파일을 생성했습니다.")
    logger.info("저장 위치: %s", output_path)


if __name__ == "__main__":
    main()
