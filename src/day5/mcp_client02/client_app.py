# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 - LangGraph 멀티 에이전트 direct client (CLI 진입점)

[이 패키지가 무엇인가]
mcp_client01(단일 Tool 호출)의 다음 단계로, LangGraph 로 여러 Agent Node 를 'fan-out' 하여
mcp_server03 의 Tool 을 호출하고, Evidence Check + Synthesis 로 결과를 종합하는 실습 client 입니다.

[direct mode]
실제 stdio/HTTP MCP 연결이 아니라, 서버의 Tool entrypoint(call_mcp_tool/list_mcp_tools)를 직접
호출하는 direct mode 입니다. 실제 transport 연결은 후속 단계(mcp_client03) TODO 입니다.

[병렬에 대한 정확한 설명]
이번 단계의 '병렬'은 LangGraph 구조상 fan-out 을 표현하는 '논리적 병렬'이며, call_mcp_tool 이
동기 함수이므로 실제 '벽시계 동시성'은 보장하지 않습니다(그래프 모양만 병렬).
진짜 동시 실행은 후속 단계에서 asyncio.to_thread 또는 ThreadPoolExecutor 로 검토합니다.

[경계]
- 서버 Tool entrypoint 만 사용(tool_calling 경유). repositories/db_access/rag adapter 직접 호출 금지.
- 결과 전체 dict/민감정보는 출력하지 않고 요약만 출력.

[실행]
    uv run python -m day5.mcp_client02
    uv run python -m day5.mcp_client02.client_app
    uv run python -m day5.mcp_client02 --query "..."
    (import 경로상 <root>/src 가 sys.path 에 있어야 한다 — PYTHONPATH=src 또는 src 를 cwd)
"""
from __future__ import annotations

import argparse  # CLI 인자(--query) 파싱
import sys
from pathlib import Path

# [import 경로 보강] 이 파일 위치: <root>/src/day5/mcp_client02/client_app.py → parents[3] = <root>
# day3+ 규칙에 맞춰 <root>/src 를 sys.path 에 넣어, 'day5.mcp_client02.*' 패키지 경로 import 가
# 어디서 실행하든 동작하도록 보강한다(아래 graph_builder import 가 이 줄에 의존한다).
_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# 그래프 조립(build_graph)과 초기 State 생성(build_initial_state)을 가져온다.
# 실행의 핵심 두 함수이며, run_query 가 이 둘을 이어 그래프를 invoke 한다.
from day5.mcp_client02.graph_builder import build_graph, build_initial_state


# 기본 데모 질문(가상 시나리오). RAG + 품질 + 설비 + 알람 의도를 함께 담은 예시.
_DEFAULT_QUERY = "EQP-EV-03에서 ALM-TEMP-402 반복 발생 시 조치 방향과 품질 영향을 알려줘"

# 화면 출력에 쓰는 Agent 결과 key ↔ 라벨.
_AGENT_KEYS = [
    ("rag_result", "RAG"),
    ("equipment_result", "Equipment"),
    ("alarm_result", "Alarm"),
    ("quality_result", "Quality"),
    ("maintenance_result", "Maintenance"),
]


def _print_planner(state: dict) -> None:
    """Planner 가 추출한 식별자/need_* flag 를 요약 출력한다."""
    print("[Planner] (규칙 기반)")
    print(f"  equipment_id={state.get('equipment_id')} alarm_code={state.get('alarm_code')} "
          f"metric_name={state.get('metric_name')}")
    print(f"  need: rag={state.get('need_rag')} equipment={state.get('need_equipment')} "
          f"alarm={state.get('need_alarm')} quality={state.get('need_quality')} "
          f"maintenance={state.get('need_maintenance')}")


def _print_agents(state: dict) -> None:
    """각 Agent 의 실행/skip/error 상태를 요약 출력한다."""
    print("\n[Agents] (논리적 병렬 fan-out / 실제 동시성은 후속 TODO)")
    for key, label in _AGENT_KEYS:
        res = state.get(key) or {}
        status = res.get("status", "none")
        extra = ""
        if status == "error" and res.get("error_summary"):
            extra = f" ({res['error_summary']})"
        elif status == "executed":
            ds = (res.get("result_summary") or {}).get("data_source")
            rs = (res.get("result_summary") or {}).get("retrieval_source")
            tag = ds or rs
            extra = f" (source={tag})" if tag else ""
        print(f"  - {label} agent: {status}{extra}")


def _print_evidence(state: dict) -> None:
    """Evidence Check 결과(직접 근거/oos/mock fallback)를 요약 출력한다."""
    flags = state.get("evidence_flags") or {}
    print("\n[Evidence Check] (표시용 — Guardrail 전체 아님)")
    print(f"  direct_evidence_found={flags.get('direct_evidence_found')} "
          f"out_of_scope_warning={flags.get('out_of_scope_warning')} "
          f"used_mock_fallback={flags.get('used_mock_fallback')}")
    if flags.get("missing_identifiers"):
        print(f"  missing_identifiers={flags.get('missing_identifiers')}")
    for note in flags.get("safety_notes", []):
        print(f"  note: {note}")


def run_query(user_query: str) -> dict:
    """그래프를 실행하고 최종 State 를 돌려준다(콘솔 출력 없이 호출 가능 — 테스트용).

    [실행 흐름 — mcp_client02 의 중심 연결점]
    1) build_graph()      : Planner→5 Agent→Evidence Check→Synthesis 그래프를 compile.
    2) build_initial_state(user_query): user_query 와 빈 errors 채널만 담은 초기 State 생성.
    3) graph.invoke(...)  : 초기 State 를 그래프에 흘려보내 모든 Node 를 거친 '최종 State'를 받는다.
    [입력] user_query: 사용자 질문 문자열.
    [반환] 모든 Node 가 채운 최종 State dict(final_answer / 각 *_result / evidence_flags 포함).
    """
    graph = build_graph()
    return graph.invoke(build_initial_state(user_query))


def main() -> None:
    """CLI 진입점: 질문을 받아 멀티 에이전트 그래프를 실행하고 결과를 요약 출력한다.

    client02는 교육용 direct mode 예제이며, stdio/http transport는 이후 client03 단계에서 다룬다.
    """
    parser = argparse.ArgumentParser(
        description="mcp_client02 - LangGraph 멀티 에이전트 direct client(mcp_server03 Tool 호출)"
    )
    parser.add_argument("--query", default=_DEFAULT_QUERY, help="사용자 질문(미지정 시 기본 데모 질문)")
    args = parser.parse_args()

    # 그래프를 한 번 실행해 최종 State 를 받는다(여기서 모든 Node 가 순서대로 거쳐진다).
    state = run_query(args.query)

    # 최종 State 를 단계별로 사람이 읽기 쉽게 요약 출력한다(Planner → Agent → Evidence → 종합 답변).
    _print_planner(state)
    _print_agents(state)
    _print_evidence(state)
    print()
    print(state.get("final_answer", "(최종 답변 생성 실패)"))
    print("\n[참고] 이번 단계의 병렬은 LangGraph fan-out 의 '논리적 병렬' 구조이며, "
          "실제 벽시계 동시성은 보장하지 않습니다(후속 TODO: asyncio.to_thread / ThreadPoolExecutor).")


if __name__ == "__main__":
    main()
