# -*- coding: utf-8 -*-
"""
Day5 mcp_client_final - Streamlit 화면 (Agent 판단 흐름 시각화)

[이 파일의 목적]
agent_flow.run_agent_flow 가 만든 '판단 단계 dict'를 위에서 아래로 읽히는 '세로 단계형' 화면으로
보여 줍니다. 화면의 주인공은 결과 dict 가 아니라 'Agent 가 어떻게 판단했는가'(의도→Tool 선택→
호출 trace→비교/검증→교육용 점검 등급→다음 확인 항목)입니다.

[경계]
- 이 파일은 day5.mcp_client_final 의 agent_flow / scenarios 만 import 한다.
- 서버(mcp_server03) 내부 모듈은 직접 import 하지 않는다(Tool 호출은 agent_flow 가 ToolCaller 로 수행).
- 결과는 성공처럼 포장하지 않는다. OK/EMPTY/SKIPPED/ERROR 와 mock_fallback/fallback_used/
  data_source/retrieval_source 를 정직하게 표시한다.

[transport 정책 — standalone HTTP 전용]
- mcp_client_final 은 stdio/subprocess 로 서버를 실행하지 않는다. 별도로 떠 있는
  mcp_server_final standalone HTTP 서버(http://127.0.0.1:8003/mcp)에만 연결한다.
- 화면에서 transport 를 선택하지 않으며, 내부적으로 항상 "http" + 8003 endpoint 를 사용한다.

[실행]
    # 1) 먼저 mcp_server_final standalone HTTP 서버를 8003 포트로 실행
    #    (PowerShell) $env:PYTHONPATH = "src"
    #    uv run python -m day5.mcp_server_final.mcp_server --transport streamable-http --host 127.0.0.1 --port 8003 --path /mcp
    # 2) Client(Streamlit) 실행
    uv run streamlit run src/day5/mcp_client_final/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# [import 경로 보강] 이 파일 <root>/src/day5/mcp_client_final/streamlit_app.py → parents[3] = <root>.
_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import streamlit as st

# mcp_client_final 의 판단 흐름 + 시연 시나리오만 import(서버 내부 import 금지).
from day5.mcp_client_final import agent_flow, scenarios
# 다중 DB Tool 병렬 호출 데모(별도 탭) — Agent 판단 흐름과 분리된 독립 모듈.
from day5.mcp_client_final import parallel_runner


# [standalone HTTP 전용] 교육용 최종 실습 MCP endpoint 를 8003 으로 통일한다.
#   mcp_client04.config.MCP_HTTP_URL 은 8000 을 가리키므로 여기서는 사용하지 않고,
#   이 로컬 상수만 화면 표시/실행 호출에 사용한다(client04 는 참조 대상이라 수정하지 않음).
DEFAULT_MCP_HTTP_URL = "http://127.0.0.1:8003/mcp"
# standalone HTTP 전용 정책상 transport 는 항상 http 로 고정한다(stdio/subprocess 미사용).
_TRANSPORT = "http"
# 서버 실행 안내 명령(mcp_server_final standalone HTTP 서버, 8003).
_HTTP_SERVER_RUN_COMMAND = (
    'uv run python -m day5.mcp_server_final.mcp_server '
    '--transport streamable-http --host 127.0.0.1 --port 8003 --path /mcp'
)


# 단계별 상태 → 색 매핑(정직 표기: 성공/생략/0건/오류 구분).
def _status_box(status: str, ok_msg: str, other_msg: str = "") -> None:
    if status == "OK":
        st.success(ok_msg)
    elif status == "ERROR":
        st.error(other_msg or "ERROR — 호출 실패(성공으로 표시하지 않음).")
    elif status in ("EMPTY",):
        st.warning(other_msg or "EMPTY — 결과 0건.")
    elif status in ("SKIPPED",):
        st.info(other_msg or "SKIPPED — 이번 의도에서는 호출하지 않음.")
    else:
        st.write(f"status: {status}")


def _init_session() -> None:
    ss = st.session_state
    ss.setdefault("final_question", "")
    ss.setdefault("final_result", None)
    # 병렬 DB Tool 호출 데모 전용 키(기존 Agent 결과와 섞이지 않도록 분리).
    ss.setdefault("parallel_result", None)
    ss.setdefault("pdb_equipment_id", "EQP-EV-03")
    ss.setdefault("pdb_line_id", "")
    ss.setdefault("pdb_limit", 5)
    ss.setdefault("pdb_max_workers", 4)


def render_input() -> tuple:
    """질문 입력 + 예시 selectbox + 실행 버튼(standalone HTTP 전용). (transport, http_url) 반환."""
    st.subheader("1) 질문 입력")
    examples = scenarios.get_scenarios()
    labels = [f"{s['name']} — {s['question']}" for s in examples]
    pick = st.selectbox("예시 질문(수업 시연용)", ["(직접 입력)"] + labels)
    if pick != "(직접 입력)":
        chosen = examples[labels.index(pick)]
        st.caption(f"💡 {chosen['explanation']}  · 핵심: {chosen['key_concept']}")
        default_q = chosen["question"]
    else:
        default_q = st.session_state.get("final_question", "")

    question = st.text_area("질문", value=default_q, height=80,
                            placeholder="예) EQP-EV-03에서 ALM-TEMP-402가 반복되는데 품질 영향과 추가 확인 방향?")

    # [standalone HTTP 전용] transport 선택 UI 없음 — 항상 http + 8003 endpoint 로 고정한다.
    transport = _TRANSPORT
    http_url = DEFAULT_MCP_HTTP_URL
    st.info(
        "mcp_client_final은 standalone HTTP 서버 연결만 사용합니다. "
        "먼저 mcp_server_final을 8003 포트로 실행한 뒤 Client를 실행해 주세요."
    )
    # endpoint 는 읽기 전용으로 표시만 한다(사용자가 포트를 바꾸지 못하게 함). 실제 호출은 상수를 사용.
    st.caption(f"연결 대상 MCP HTTP endpoint(고정): {DEFAULT_MCP_HTTP_URL}")
    st.code(_HTTP_SERVER_RUN_COMMAND, language="bash")

    if st.button("Agent 판단 흐름 실행", type="primary"):
        q = str(question or "").strip()
        if not q:
            st.warning("질문을 입력하세요.")
        else:
            st.session_state["final_question"] = q
            with st.spinner("Agent 판단 흐름 실행 중... (분석→의도→Tool선택→호출→비교/검증→점검등급→다음확인)"):
                st.session_state["final_result"] = agent_flow.run_agent_flow(
                    q, transport=transport, http_url=DEFAULT_MCP_HTTP_URL)
    return transport, http_url


def render_result(result: dict) -> None:
    """판단 단계 dict 를 '세로 단계형'으로 표시한다(결과보다 판단 흐름이 먼저 보이게)."""
    if not isinstance(result, dict):
        st.error("결과 형식이 올바르지 않습니다.")
        return

    analysis = result.get("analysis", {})
    intent = result.get("intent", {})

    # --- 1단계: 질문 분석 ---
    st.markdown("### 1단계 · 질문 분석")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("equipment_id", analysis.get("equipment_id") or "-")
    c2.metric("alarm_code", analysis.get("alarm_code") or "-")
    c3.metric("line_id", analysis.get("line_id") or "-")
    c4.metric("metric_name", analysis.get("metric_name") or "-")
    if analysis.get("keywords"):
        st.caption("추출 키워드: " + " · ".join(
            f"{k['category']}({', '.join(k['matched'])})" for k in analysis["keywords"]))

    # --- 2단계: 의도 분류 ---
    st.markdown("### 2단계 · 의도 분류")
    st.info(f"intent → **{intent.get('intent')}**  (needs_db={intent.get('needs_db')}, "
            f"needs_rag={intent.get('needs_rag')})")
    st.caption(f"이유: {intent.get('reason')}")

    # --- 3단계: 선택된 MCP Tool ---
    st.markdown("### 3단계 · 선택된 MCP Tool / 이유 / 순서")
    selected = result.get("selected_tools", [])
    if selected:
        st.table([{"순서": s["call_order"], "tool": s["tool_name"],
                   "목적": s["purpose"], "선택 이유": s["reason"]} for s in selected])
    else:
        st.caption("선택된 Tool 이 없습니다(의도가 모호하거나 식별자 부족).")

    # --- 4단계: Tool 호출 trace (메타데이터 정직 표시) ---
    st.markdown("### 4단계 · MCP Tool 호출 trace")
    trace = result.get("tool_trace", [])
    if trace:
        st.table([{"tool": t["tool_name"], "status": t["status"],
                   "data_source": t.get("data_source"), "retrieval_source": t.get("retrieval_source"),
                   "fallback_used": t.get("fallback_used"), "mock_fallback": t.get("mock_fallback"),
                   "error": t.get("error")} for t in trace])
        if any(t.get("status") == "ERROR" for t in trace):
            st.warning("일부 Tool 호출이 ERROR 입니다(서버 미기동/연결 실패 가능) — 성공으로 표시하지 않습니다.")
    else:
        st.caption("호출한 Tool 이 없습니다.")

    # --- 5/6단계: DB / RAG 결과 요약 ---
    col_db, col_rag = st.columns(2)
    with col_db:
        st.markdown("### 5단계 · DB 결과 요약")
        db = result.get("db_summary", {})
        _status_box(db.get("status"), db.get("reason", "DB OK"), db.get("reason", ""))
        st.caption(f"data_source={db.get('data_source')} · mock_fallback={db.get('has_mock_fallback')}")
    with col_rag:
        st.markdown("### 6단계 · RAG 결과 요약")
        rag = result.get("rag_summary", {})
        _status_box(rag.get("status"), rag.get("reason", "RAG OK"), rag.get("reason", ""))
        st.caption(f"retrieval_source={rag.get('retrieval_source')} · "
                   f"fallback_used={rag.get('fallback_used')} · documents={rag.get('documents_count')}")

    # --- 7단계: 비교 + Evidence Check ---
    st.markdown("### 7단계 · DB↔RAG 비교 + Evidence Check")
    ev = result.get("evidence_check", {})
    lvl = ev.get("evidence_level")
    if lvl == "DIRECT":
        st.success(f"evidence_level: {lvl} — {ev.get('evidence_reason')}")
    elif lvl == "PARTIAL":
        st.warning(f"evidence_level: {lvl} — {ev.get('evidence_reason')}")
    else:
        st.error(f"evidence_level: {lvl} — {ev.get('evidence_reason')}")
    st.caption(f"db_supported={ev.get('db_supported')} · rag_supported={ev.get('rag_supported')} · "
               f"mock_fallback={ev.get('has_mock_fallback')}")
    for note in ev.get("mismatch_notes", []):
        st.write(f"- ⚠️ {note}")

    # --- 8단계: 교육용 점검 등급 ---
    st.markdown("### 8단계 · 교육용 점검 등급 (점검 우선순위)")
    chk = result.get("educational_check_level", {})
    level = chk.get("check_level")
    if level == "높음":
        st.error(f"점검 우선순위: **{level}**")
    elif level == "보통":
        st.warning(f"점검 우선순위: **{level}**")
    elif level == "낮음":
        st.success(f"점검 우선순위: **{level}**")
    else:
        st.info(f"점검 우선순위: **{level}**")
    st.caption(chk.get("reason"))
    if chk.get("uncertainty"):
        st.caption("불확실성: " + " · ".join(chk["uncertainty"]))
    st.warning("※ 교육용 예제 기준이며 실제 운영 판단이 아닙니다.")

    # --- 9단계: 다음 확인 항목 ---
    st.markdown("### 9단계 · 다음 확인 항목 / 후속 질문")
    st.write("**다음 확인 항목(추가 확인 방향 — 조치 명령 아님):**")
    for c in result.get("next_checks", []):
        st.write(f"- {c}")
    st.write("**후속 질문 후보:**")
    for q in result.get("follow_up_questions", []):
        st.write(f"- {q}")

    st.divider()
    st.caption(result.get("final_message", ""))

    # --- 원본 결과(맨 아래 expander) ---
    with st.expander("원본 결과 dict 보기 (raw)"):
        st.json(result)


# ---------------------------------------------------------------------------
# 탭 2: 다중 DB Tool 병렬 호출 데모 (Agent 판단 흐름과 분리된 별도 데모)
# ---------------------------------------------------------------------------
# [이 탭의 성격 — 매우 중요]
#   Client 가 여러 DB 조회 Tool 호출을 '동시에 시작'하는 구조를 보여 주는 교육용 데모입니다.
#   Server 는 Tool 요청을 받아 처리하는 역할이며, 병렬 호출을 시작하는 쪽은 Client 입니다.
#   Agent 가 여러 개인 구조가 아니라(멀티에이전트 아님), DB Tool '호출'만 병렬화하는 구조입니다.
#   실행은 parallel_runner.run_parallel_db_tools_demo 가 담당하고, 이 UI 는 입력 수집/결과 표시만 합니다.
#   (서버 실행 명령은 모듈 상단의 _HTTP_SERVER_RUN_COMMAND(8003)를 공유한다.)


def render_parallel_result(result: dict) -> None:
    """병렬 DB Tool 호출 결과 dict 를 요약/Tool별 표/스킵으로 표시한다(정직 표기).

    [표시 원칙] 성공(OK)/결과없음(EMPTY)/실패(ERROR)/스킵을 섞지 않고 구분한다.
               결과는 parallel_runner 단계에서 이미 비민감 요약(개수/스칼라)으로 변환돼 있다.
    """
    if not isinstance(result, dict):
        st.error("병렬 실행 결과 형식이 올바르지 않습니다.")
        return

    status = result.get("status")
    note = result.get("note")

    # 연결 실패/서버 미기동 등: 숨기지 않고 안내 + 서버 실행 명령을 함께 보여 준다.
    if status == "ERROR" and not result.get("called_tools"):
        st.error(note or "병렬 호출을 실행하지 못했습니다(서버 연결/Tool schema 확인 필요).")
        st.caption("HTTP transport 사용 시, 먼저 별도 터미널에서 streamable-http 서버를 띄우세요:")
        st.code(_HTTP_SERVER_RUN_COMMAND, language="bash")
        with st.expander("전체 병렬 실행 결과 JSON"):
            st.json(result)
        return

    # 실행 요약(전체 성공/일부/전체 실패).
    success = result.get("success_count", 0)
    error = result.get("error_count", 0)
    skipped = result.get("skipped_tools") or []
    if status == "OK":
        st.success(f"전체 성공: {success}개 DB 조회 Tool 을 Client 측에서 병렬 호출했습니다.")
    elif status == "PARTIAL":
        st.warning(f"일부 성공: 성공 {success} · 실패 {error} · 스킵 {len(skipped)}.")
    else:
        st.error(f"실패: 호출한 Tool 이 모두 실패했습니다(성공 {success} · 실패 {error}).")

    # 핵심 지표 — 전체 실행 시간 / 호출·성공·실패 수.
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("total_elapsed_ms", result.get("total_elapsed_ms", 0))
    col2.metric("called", len(result.get("called_tools") or []))
    col3.metric("success", success)
    col4.metric("error", error)
    st.caption(f"transport={result.get('transport')} · equipment_id={result.get('equipment_id')} · "
               f"line_id={result.get('line_id') or '-'} · limit={result.get('limit')} · "
               f"max_workers={result.get('max_workers')}")

    # 호출된 Tool 목록.
    called = result.get("called_tools") or []
    if called:
        st.markdown("#### 호출된 Tool")
        st.write(" · ".join(called))

    # Tool별 결과 표 — tool_name/status/elapsed_ms/data_source/fallback_used/error/result_summary.
    st.markdown("#### Tool별 결과")
    rows = result.get("results") or []
    if rows:
        table = [{
            "tool_name": r.get("tool_name"),
            "status": r.get("status"),
            "elapsed_ms": r.get("elapsed_ms"),
            "data_source": r.get("data_source"),
            "fallback_used": r.get("fallback_used"),
            "error": r.get("error"),
            "result_summary": ", ".join(f"{k}={v}" for k, v in (r.get("result_summary") or {}).items()),
        } for r in rows]
        st.table(table)
    else:
        st.caption("호출된 Tool 결과가 없습니다.")

    # 스킵된 Tool — required 인자를 구성할 수 없어 호출하지 않은 Tool 과 사유.
    if skipped:
        with st.expander(f"스킵된 Tool 목록 ({len(skipped)})"):
            for item in skipped:
                st.write(f"- **{item.get('tool_name')}**: {item.get('reason')}")

    # 전체 결과 JSON(이미 비민감 요약만 포함).
    with st.expander("전체 병렬 실행 결과 JSON"):
        st.json(result)


def render_parallel_demo() -> None:
    """탭 2 본문 — 다중 DB Tool 병렬 호출 데모(입력 + 실행 버튼 + 결과 표시).

    [transport/http_url] standalone HTTP 전용 정책상 항상 http + 8003 endpoint 를 사용한다.
    """
    st.subheader("다중 DB Tool 병렬 호출 데모")
    st.info(
        "이 데모는 **Client가 여러 DB Tool 호출을 동시에 시작**하는 구조를 보여 줍니다. "
        "Server는 Tool 요청을 받아 처리하는 역할이며, 병렬 호출을 시작하는 쪽은 Client입니다. "
        "Agent가 여러 개인 구조가 아니라 DB Tool 호출만 병렬화하는, 기존 Agent 판단 흐름과 분리된 교육용 데모입니다."
    )
    st.caption(
        "예시 질문: 'EQP-EV-03 설비 개요, 최근 알람 이력, 품질 지표, 정비 이력을 병렬로 조회해줘' "
        "(이 데모는 위 4개 안전 조회 Tool 만 병렬 호출하며, search_manual/SQL 계열은 호출하지 않습니다.)"
    )
    st.caption(
        f"mcp_client_final은 standalone HTTP 서버 연결만 사용합니다 → 연결 대상(고정): {DEFAULT_MCP_HTTP_URL}. "
        "먼저 mcp_server_final을 8003 포트로 실행한 뒤 Client를 실행해 주세요(미기동 시 결과는 ERROR로 정직 표기)."
    )
    st.code(_HTTP_SERVER_RUN_COMMAND, language="bash")

    # 입력값 — SQL 이 아니라 식별자/limit/동시 실행 수만 받는다.
    col_eq, col_ln = st.columns(2)
    with col_eq:
        st.text_input("equipment_id", key="pdb_equipment_id",
                      help="조회할 설비 ID(가상). 기본값 EQP-EV-03")
    with col_ln:
        st.text_input("line_id (선택)", key="pdb_line_id",
                      help="조회할 라인 ID(가상, 선택). 비워 두면 미전달. 예: LINE-07")
    col_lim, col_wk = st.columns(2)
    with col_lim:
        st.number_input("limit", min_value=1, max_value=50, step=1, key="pdb_limit",
                        help="목록형 Tool 의 최대 건수(schema 에 limit 가 있는 Tool 에만 전달)")
    with col_wk:
        st.number_input("max_workers", min_value=1, max_value=8, step=1, key="pdb_max_workers",
                        help="동시 실행 상한(병렬 호출 워커 수)")

    if st.button("다중 DB Tool 병렬 호출 실행", type="primary", key="pdb_run"):
        with st.spinner("다중 DB Tool 병렬 호출 실행 중..."):
            st.session_state["parallel_result"] = parallel_runner.run_parallel_db_tools_demo(
                equipment_id=str(st.session_state.get("pdb_equipment_id") or "").strip() or "EQP-EV-03",
                line_id=(str(st.session_state.get("pdb_line_id") or "").strip() or None),
                limit=int(st.session_state.get("pdb_limit") or 5),
                transport=_TRANSPORT,
                http_url=DEFAULT_MCP_HTTP_URL,
                max_workers=int(st.session_state.get("pdb_max_workers") or 4),
            )

    parallel_result = st.session_state.get("parallel_result")
    if parallel_result is not None:
        st.divider()
        render_parallel_result(parallel_result)


def main() -> None:
    st.set_page_config(page_title="mcp_client_final — Agent 판단 흐름", layout="wide")
    _init_session()
    st.title("mcp_client_final — Agent 판단 흐름 시각화")
    st.caption(
        "단순 조회/보고 UI가 아니라, Agent가 '의도 판단 → Tool 선택 → 호출 → 비교·검증 → "
        "교육용 점검 등급 → 다음 확인 항목'을 어떻게 수행하는지 단계별로 보여 주는 교육용 예제입니다. "
        "(실행 호출은 mcp_client04의 ToolCaller/config를 재사용)"
    )

    # 탭 분리: 탭 1은 기존 Agent 실행 흐름(무변경), 탭 2는 다중 DB Tool 병렬 호출 데모.
    tab_agent, tab_parallel = st.tabs(["Agent 실행", "다중 DB Tool 병렬 호출"])

    with tab_agent:
        # 기존 흐름 유지 — render_input()/render_result()/run_agent_flow() 변경 없음.
        render_input()
        result = st.session_state.get("final_result")
        if result is not None:
            st.divider()
            render_result(result)

    with tab_parallel:
        # standalone HTTP 전용 — http + 8003 endpoint 고정(render_parallel_demo 내부에서 사용).
        render_parallel_demo()


# streamlit 은 이 스크립트를 top-level 로 실행하므로 main() 을 바로 호출한다.
main()
