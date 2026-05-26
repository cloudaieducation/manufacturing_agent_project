# -*- coding: utf-8 -*-
"""
2일차 RAG 실습 - LangGraph StateGraph 기반 RAG 실행기 단순화 버전

이 파일은 교육용 제조 AI Agent 실습에서 LangGraph 흐름만 담당합니다.
최종 Markdown 리포트 저장은 day2_rag_agent_v1.py가 담당합니다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent

for path in [CURRENT_DIR, SRC_DIR]:
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from langgraph.graph import StateGraph, END
import pystache

from graph_state import (
    ManufacturingRAGState,
    create_initial_state,
    add_trace,
    summarize_retrieved_docs,
)
from rag_search import search_top_k
from llm_client import generate_response


MAX_RETRY_COUNT = 1


def get_project_root() -> Path:
    """현재 파일 위치를 기준으로 프로젝트 루트 폴더를 찾습니다."""
    current_path = Path(__file__).resolve()

    for parent in [current_path.parent, *current_path.parents]:
        if (parent / "src").exists() and ((parent / "docs").exists() or (parent / "outputs").exists()):
            return parent

    return Path.cwd().resolve()


def extract_alarm_code(text: str) -> str:
    """ALM-TEMP-402 같은 알람 코드를 추출합니다."""
    if not text:
        return ""
    match = re.search(r"ALM-[A-Z]+-[0-9]+", text)
    return match.group(0) if match else ""


def extract_equipment_id(text: str) -> str:
    """EQP-EV-03 같은 설비 ID를 추출합니다."""
    if not text:
        return ""
    match = re.search(r"EQP-[A-Z]+-[0-9]+", text)
    return match.group(0) if match else ""


def render_prompt_template(template_name: str, data: dict[str, Any]) -> str:
    """templates/day2 폴더의 Mustache 템플릿을 렌더링합니다."""
    template_path = get_project_root() / "templates" / "day2" / template_name
    template_text = template_path.read_text(encoding="utf-8-sig")
    return pystache.render(template_text, data)


def build_llm_prompt(state: ManufacturingRAGState) -> str:
    """LLM에 전달할 프롬프트를 Mustache 템플릿으로 생성합니다."""
    retrieved_docs = state.get("retrieved_docs", [])

    data = {
        "user_query": state.get("user_query", ""),
        "equipment_id": state.get("equipment_id", ""),
        "alarm_code": state.get("alarm_code", ""),
        "equipment_id_display": state.get("equipment_id", "") or "질문에서 명확히 확인되지 않음",
        "alarm_code_display": state.get("alarm_code", "") or "질문에서 명확히 확인되지 않음",
        "retrieved_docs": retrieved_docs,
    }

    return render_prompt_template("rag_answer_prompt.mustache", data)


def build_mock_answer(state: ManufacturingRAGState) -> str:
    """LLM 호출 실패 또는 검색 근거 부족 시 사용할 짧은 교육용 mock 답변을 만듭니다.

    실제 LLM 호출이 실패했을 때 수업 흐름을 유지하기 위한 교육용 대체 답변입니다.
    """
    user_query = state.get("user_query", "")
    equipment_id = state.get("equipment_id", "") or "질문에서 명확히 확인되지 않음"
    alarm_code = state.get("alarm_code", "") or "질문에서 명확히 확인되지 않음"
    retrieved_docs = state.get("retrieved_docs", [])

    if retrieved_docs:
        doc_lines = []
        for doc in retrieved_docs:
            doc_lines.append(
                f"- Rank {doc.get('rank', '')} / "
                f"{doc.get('doc_name', '')} / "
                f"{doc.get('section_title', '')} / "
                f"score={doc.get('score', '')} / "
                f"{doc.get('preview', '')}"
            )
        doc_summary = "\n".join(doc_lines)
    else:
        doc_summary = "- 검색된 근거 문서가 없습니다."

    return f"""
## 1. 질의 요약
- 사용자 질문: {user_query}

## 2. 확인된 설비 ID와 알람 코드
- 설비 ID: {equipment_id}
- 알람 코드: {alarm_code}

## 3. 검색 근거 요약
{doc_summary}

## 4. 원인 후보
- 온도 상승 추세가 있었는지 확인이 필요합니다.
- 냉각 상태 또는 센서 값 변동 가능성을 검토할 수 있습니다.
- 최근 정비 이력 또는 설정 변경 여부를 함께 확인할 수 있습니다.

## 5. 품질 영향 확인 항목
- 알람 발생 전후의 불량률 변화를 확인합니다.
- 알람 발생 전후의 수율 변화를 확인합니다.
- 검사 결과와 반복 알람 시점이 겹치는지 확인합니다.

## 6. 추가 확인 필요 사항
- Chroma Vector DB 검색 결과와 실제 교육용 로그의 일치 여부를 확인합니다.
- 검색 근거가 부족하면 질문을 설비 ID, 알람 코드, 증상 중심으로 다시 작성합니다.
- 원인은 확정하지 않고 담당자 검토가 필요한 후보로만 정리합니다.

## 7. 주의 문구
본 답변은 교육용 문서 검색 기반 초안입니다. 실제 설비 판단이나 조치는 담당자 검토가 필요합니다.
""".strip()


def parse_query_node(state: ManufacturingRAGState) -> ManufacturingRAGState:
    """사용자 질문에서 설비 ID와 알람 코드를 추출합니다."""
    print("- parse_query_node 실행")

    query = state.get("rewritten_query") or state.get("user_query", "")
    equipment_id = extract_equipment_id(query)
    alarm_code = extract_alarm_code(query)

    state["equipment_id"] = equipment_id
    state["alarm_code"] = alarm_code

    add_trace(
        state,
        node_name="parse_query_node",
        status="success",
        message="질문에서 설비 ID와 알람 코드를 추출했습니다.",
        input_summary=query,
        output_summary=f"equipment_id={equipment_id or '없음'}, alarm_code={alarm_code or '없음'}",
    )
    return state


def retrieve_docs_node(state: ManufacturingRAGState) -> ManufacturingRAGState:
    """rag_search.search_top_k()를 호출해 관련 문서를 검색합니다."""
    print("- retrieve_docs_node 실행")

    query = state.get("rewritten_query") or state.get("user_query", "")

    try:
        retrieved_docs = search_top_k(query, top_k=3)
    except Exception as error:
        retrieved_docs = []
        state["errors"].append(f"RAG 검색 실패: {type(error).__name__}: {error}")

    state["retrieved_docs"] = retrieved_docs  # type: ignore[assignment]

    if retrieved_docs:
        status = "success"
        output_summary = summarize_retrieved_docs(retrieved_docs)  # type: ignore[arg-type]
    else:
        status = "warning"
        output_summary = "retrieved_docs=0건"
        state["errors"].append("검색 결과가 없습니다.")

    add_trace(
        state,
        node_name="retrieve_docs_node",
        status=status,
        message="RAG 검색을 수행했습니다.",
        input_summary=query,
        output_summary=output_summary,
    )
    return state


def generate_answer_node(state: ManufacturingRAGState) -> ManufacturingRAGState:
    """검색 결과를 바탕으로 LLM 답변을 생성합니다."""
    print("- generate_answer_node 실행")

    retrieved_docs = state.get("retrieved_docs", [])

    if not retrieved_docs:
        answer = build_mock_answer(state)
        state["draft_answer"] = answer
        state["final_answer"] = answer
        add_trace(
            state,
            node_name="generate_answer_node",
            status="warning",
            message="검색 근거가 없어 교육용 mock 답변을 생성했습니다.",
            input_summary="retrieved_docs=0건",
            output_summary="answer_source=mock",
        )
        return state

    try:
        prompt = build_llm_prompt(state)
        answer = generate_response(prompt)

        if not isinstance(answer, str) or not answer.strip():
            answer = build_mock_answer(state)
            answer_source = "mock"
            status = "warning"
            message = "LLM 응답이 비어 있어 교육용 mock 답변을 생성했습니다."
        else:
            answer_source = "llm_client"
            status = "success"
            message = "llm_client.py를 통해 답변을 생성했습니다."

    except Exception as error:
        answer = build_mock_answer(state)
        state["errors"].append(f"LLM 호출 실패: {type(error).__name__}: {error}")
        answer_source = "mock"
        status = "warning"
        message = "LLM 호출 실패로 교육용 mock 답변을 생성했습니다."

    state["draft_answer"] = answer
    state["final_answer"] = answer

    add_trace(
        state,
        node_name="generate_answer_node",
        status=status,
        message=message,
        input_summary=f"retrieved_docs={len(retrieved_docs)}건",
        output_summary=f"answer_source={answer_source}",
    )
    return state


def verify_grounding_node(state: ManufacturingRAGState) -> ManufacturingRAGState:
    """검색 근거가 있는지 확인합니다."""
    print("- verify_grounding_node 실행")

    retrieved_docs = state.get("retrieved_docs", [])

    if retrieved_docs:
        state["grounding_status"] = "PASS"
        state["needs_rewrite"] = False
        message = "검색 근거가 있어 grounding_status를 PASS로 설정했습니다."
    else:
        state["grounding_status"] = "NEEDS_REWRITE"
        if state.get("retry_count", 0) >= MAX_RETRY_COUNT:
            state["needs_rewrite"] = False
            message = "재시도 횟수 제한에 도달하여 재작성 없이 종료합니다."
        else:
            state["needs_rewrite"] = True
            message = "검색 근거가 없어 질의를 한 번 재작성합니다."

    add_trace(
        state,
        node_name="verify_grounding_node",
        status="success" if retrieved_docs else "warning",
        message=message,
        input_summary=f"retrieved_docs={len(retrieved_docs)}건, retry_count={state.get('retry_count', 0)}",
        output_summary=(
            f"grounding_status={state['grounding_status']}, "
            f"needs_rewrite={state['needs_rewrite']}, "
            f"retry_count={state['retry_count']}"
        ),
    )
    return state


def query_rewrite_node(state: ManufacturingRAGState) -> ManufacturingRAGState:
    """검색 실패 시 핵심 키워드 중심으로 질의를 재작성합니다."""
    print("- query_rewrite_node 실행")

    equipment_id = state.get("equipment_id", "")
    alarm_code = state.get("alarm_code", "")

    keyword_parts = [equipment_id, alarm_code, "온도 상승", "반복 알람", "품질 영향", "원인 후보"]
    rewritten_query = " ".join(part for part in keyword_parts if part).strip()

    if not rewritten_query:
        rewritten_query = "온도 상승 반복 알람 품질 영향 원인 후보 확인 항목"

    state["rewritten_query"] = rewritten_query
    state["retry_count"] = state.get("retry_count", 0) + 1
    state["needs_rewrite"] = False

    add_trace(
        state,
        node_name="query_rewrite_node",
        status="success",
        message="검색 실패 후 핵심 키워드 중심으로 질의를 재작성했습니다.",
        input_summary=state.get("user_query", ""),
        output_summary=rewritten_query,
    )
    return state


def should_rewrite_or_end(state: ManufacturingRAGState) -> str:
    """verify_grounding_node 이후 재작성 여부를 결정합니다."""
    if state.get("grounding_status") == "PASS":
        return "end"
    if state.get("retry_count", 0) >= MAX_RETRY_COUNT:
        return "end"
    if state.get("needs_rewrite") is True:
        return "rewrite"
    return "end"


def build_graph():
    """LangGraph StateGraph를 구성합니다."""
    graph_builder = StateGraph(ManufacturingRAGState)
    graph_builder.add_node("parse_query", parse_query_node)
    graph_builder.add_node("retrieve_docs", retrieve_docs_node)
    graph_builder.add_node("generate_answer", generate_answer_node)
    graph_builder.add_node("verify_grounding", verify_grounding_node)
    graph_builder.add_node("query_rewrite", query_rewrite_node)
    graph_builder.set_entry_point("parse_query")
    graph_builder.add_edge("parse_query", "retrieve_docs")
    graph_builder.add_edge("retrieve_docs", "generate_answer")
    graph_builder.add_edge("generate_answer", "verify_grounding")
    graph_builder.add_conditional_edges(
        "verify_grounding",
        should_rewrite_or_end,
        {"rewrite": "query_rewrite", "end": END},
    )
    graph_builder.add_edge("query_rewrite", "retrieve_docs")
    return graph_builder.compile()


def run_langgraph_rag(user_query: str) -> ManufacturingRAGState:
    """day2_rag_agent_v1.py가 호출하는 외부 인터페이스입니다."""
    initial_state = create_initial_state(user_query)
    graph = build_graph()
    final_state = graph.invoke(initial_state)
    return final_state


def main() -> None:
    """단독 실행 시 샘플 질문으로 LangGraph RAG 흐름을 실행합니다."""
    sample_query = "EQP-EV-03에서 ALM-TEMP-402가 반복 발생했는데 원인 후보와 품질 영향 확인 항목을 알려줘"
    final_state = run_langgraph_rag(sample_query)
    print("[완료] LangGraph RAG 실행")
    print(f"grounding_status: {final_state.get('grounding_status', '')}")
    print()
    print(final_state.get("final_answer", ""))


if __name__ == "__main__":
    main()
