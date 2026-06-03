# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 - Result Synthesis (템플릿 기반 최종 답변 생성)

[이 파일의 역할]
병렬 Agent 결과 + Evidence Check 결과를 모아 '최종 답변(final_answer)'을 만드는
Synthesis Node 입니다. 이번 단계는 LLM 없이 '템플릿 기반'으로 구성합니다.

[안전 원칙 — 매우 중요]
- 원인 확정 금지: "검색됨/조회됨"을 "원인이다"로 단정하지 않는다.
- 실제 장비 제어 지시 금지(교육용 가상 시나리오).
- 직접 근거 부족 시 "직접 근거 부족"을 명시한다.
- 민감정보/문서 전문/전체 dict 출력 금지(요약만).
- skipped Agent → "이번 질문에서는 해당 조회를 생략", error Agent → "해당 정보 확인 실패".
"""
from __future__ import annotations

from day5.mcp_client02.result_formatting import safe_preview, summarize_documents, summarize_items


_AGENT_LABELS = {
    "rag_result": "매뉴얼/RAG 근거",
    "equipment_result": "설비 개요",
    "alarm_result": "알람 이력",
    "quality_result": "품질 지표",
    "maintenance_result": "정비 이력",
}


def _status_line(label: str, result: dict) -> str:
    """한 Agent 결과의 상태 한 줄 요약(executed/skipped/error)."""
    if not isinstance(result, dict):
        return f"- {label}: 결과 없음"
    status = result.get("status")
    if status == "skipped":
        note = result.get("error_summary")
        tail = f"({safe_preview(note, 40)})" if note else ""
        return f"- {label}: 이번 질문에서는 해당 조회를 생략 {tail}".rstrip()
    if status == "error":
        return f"- {label}: 해당 정보 확인 실패({safe_preview(result.get('error_summary'), 40)})"
    return f"- {label}: 확인됨"


def _summary_detail_lines(result: dict) -> list:
    """executed Agent 의 result_summary 를 안전하게 한두 줄로 풀어 쓴다(민감정보 제외)."""
    lines = []
    if not isinstance(result, dict) or result.get("status") != "executed":
        return lines
    summary = result.get("result_summary") or {}
    # data_source/fallback_used 같은 출처 표시.
    for key in ("data_source", "fallback_used", "retrieval_source"):
        if key in summary:
            lines.append(f"    {key}: {summary.get(key)}")
    # 중첩 리스트(documents/recent_events/history)는 상위 3개만.
    if "documents" in summary:
        for doc in summarize_documents(summary.get("documents")):
            lines.append(f"    - {doc}")
    if "recent_events" in summary:
        for ev in summarize_items(summary.get("recent_events")):
            lines.append(f"    - {ev}")
    if "history" in summary:
        for hist in summarize_items(summary.get("history")):
            lines.append(f"    - {hist}")
    # 그 외 비민감 스칼라(equipment_type/value/metric_name 등).
    for key, value in summary.items():
        if key in ("data_source", "fallback_used", "retrieval_source",
                   "documents", "recent_events", "history") or key.endswith("_truncated"):
            continue
        if isinstance(value, (list, dict)):
            continue
        lines.append(f"    {key}: {safe_preview(value, 60)}")
    return lines


def build_final_answer(state: dict) -> str:
    """State 의 Agent 결과 + evidence_flags 로 템플릿 기반 최종 답변 문자열을 만든다.

    [종합 방식]
    아래 1~7번 섹션 순서대로 정해진 틀에 State 값을 끼워 넣는다(LLM 미사용). 즉 '어떤 정보를 어떤 순서로
    보여줄지'가 고정 템플릿으로 정해져 있다: 질문 요약 → 직접 근거 → RAG → 설비 DB → 알람/품질/정비 →
    주의사항 → 다음 확인 방향. 각 Agent 결과는 _status_line 이 executed/skipped/error 를 구분해 안전하게
    한 줄로 요약하고, executed 인 경우에만 _summary_detail_lines 로 비민감 요약을 덧붙인다.
    """
    query = safe_preview(state.get("user_query"), 200)
    # evidence_check 가 채운 flag 를 읽어 '직접 근거 유무/주의 문구'를 결정한다(없으면 빈 dict).
    flags = state.get("evidence_flags") or {}

    out = []
    out.append("=" * 60)
    out.append("[최종 종합 답변] (템플릿 기반, LLM 미사용 / 교육용 가상 시나리오)")
    out.append("=" * 60)

    # 1. 질문 요약
    out.append("\n1. 질문 요약")
    out.append(f"   - {query}")

    # 2. 직접 확인된 근거
    out.append("\n2. 직접 확인된 근거")
    if flags.get("direct_evidence_found"):
        out.append("   - 질문의 식별자(설비/알람)가 조회 결과에 직접 확인되었습니다.")
    else:
        out.append("   - 직접 근거 부족: 질문의 식별자가 조회 결과에 직접 나타나지 않았습니다.")
    if flags.get("missing_identifiers"):
        out.append(f"   - 직접 매칭되지 않은 식별자: {', '.join(map(str, flags['missing_identifiers']))}")

    # 3. 매뉴얼/RAG 근거
    out.append("\n3. 매뉴얼/RAG 근거")
    out.append(_status_line("매뉴얼/RAG 근거", state.get("rag_result")))
    out.extend(_summary_detail_lines(state.get("rag_result")))

    # 4. DB 조회 결과 (설비 개요)
    out.append("\n4. DB 조회 결과")
    out.append(_status_line("설비 개요", state.get("equipment_result")))
    out.extend(_summary_detail_lines(state.get("equipment_result")))

    # 5. 품질/알람/정비 관점
    out.append("\n5. 품질/알람/정비 관점")
    for key in ("alarm_result", "quality_result", "maintenance_result"):
        out.append(_status_line(_AGENT_LABELS[key], state.get(key)))
        out.extend(_summary_detail_lines(state.get(key)))

    # 6. 주의사항
    out.append("\n6. 주의사항")
    out.append("   - 조회/검색 결과를 곧바로 '원인'으로 단정하지 않습니다(확인·검토 중심).")
    out.append("   - 실제 장비 제어 지시는 제공하지 않습니다(교육용).")
    for note in flags.get("safety_notes", []):
        out.append(f"   - {safe_preview(note, 100)}")

    # 7. 다음 확인 방향
    out.append("\n7. 다음 확인 방향")
    if flags.get("out_of_scope_warning"):
        out.append("   - 직접 근거가 부족하므로, 설비/알람 식별자를 더 명확히 하여 재조회를 권장합니다.")
    if flags.get("used_mock_fallback"):
        out.append("   - 일부 결과가 mock_fallback 입니다. 실제 DB(PostgreSQL) 연결 후 재확인을 권장합니다.")
    out.append("   - 매뉴얼 근거와 DB 사실 데이터를 함께 비교해 원인 후보를 좁히는 절차를 따릅니다.")

    return "\n".join(out)


def synthesis_node(state: dict) -> dict:
    """Synthesis Node: 템플릿 기반 최종 답변을 만들어 final_answer 에 담는다."""
    return {"final_answer": build_final_answer(state)}
