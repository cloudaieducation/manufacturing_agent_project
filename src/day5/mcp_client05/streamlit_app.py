# -*- coding: utf-8 -*-
"""
Day5 mcp_client05 - Streamlit 교육용 웹 UI (화면 단계)

[이 파일의 목적]
mcp_client04 의 실행 흐름(standalone MCP stdio transport + LangGraph 멀티 에이전트)을
'그대로 재사용'하면서, 그 실행 결과를 웹 화면에서 확인할 수 있게 하는 '얇은 UI' 입니다.
핵심 로직(MCP 연결 · Tool 호출 · LangGraph 라우팅)은 이 파일에 새로 구현하지 않고,
mcp_client04 의 ``runner`` 계층(run_query / run_list_tools / run_demo)만 호출합니다.

[왜 '얇은 UI' 인가 — 경계]
- 이 파일은 ``day5.mcp_client04.runner`` 와 ``config`` 만 import 합니다.
- mcp_server03 의 내부 함수/모듈(repositories/db_access/rag_*/Tool 함수)은 직접 import 하지
  않습니다. 서버는 별도 프로세스로 실행되고, client 는 transport(stdio)로만 접속합니다.
  → 서버 내부를 직접 import 하면 transport 경계를 깨고(=프로토콜이 아니라 함수 호출),
    교육용으로 가르치려는 '서버/클라이언트 분리' 모델이 무너지기 때문입니다.
- DB 직접 접속, RAG 내부 함수 직접 호출도 하지 않습니다. 모든 데이터 접근은 ToolCaller(=runner)뿐.

[search_manual 을 기본 SKIPPED 처리하는 이유 + HTTP 활성 경로(2차 확장)]
mcp_client03 검증에서, search_manual(Chroma+Ollama)을 stdio 서버 서브프로세스로 호출하면
worker thread 안에서 hang/timeout 가능성이 확인되었습니다. 따라서 '기본'은 RAG 질문을
실제로 호출하지 않고 rag_agent 가 ``rag_status="SKIPPED"`` 로 정직하게 표기합니다.
(timeout 을 성공처럼 위장하지 않음.)
2차 확장: 사이드바 toggle 을 켜면 allow_rag=True + http transport 로 전환되어, 외부에서 미리
띄운 long-lived streamable-http 서버에 접속해 search_manual 을 실제 호출합니다(rag_status:
OK/EMPTY/ERROR). HTTP 서버는 이 앱이 spawn 하지 않으며, 사용자가 별도 터미널에서 먼저 띄워야 합니다.

[MCP client 를 st.session_state 에 저장하지 않는 이유 — 매우 중요]
Streamlit 은 버튼 클릭/입력 변경마다 스크립트를 '재실행(rerun)' 합니다.
fastmcp.Client / StdioTransport 는 async context manager 로 수명이 관리되고, 그 뒤에는
서버 subprocess 와 event loop 가 붙어 있습니다. 이런 객체를 session_state 에 오래 보관하면
rerun 사이에 event loop/서브프로세스 정리가 꼬여(좀비 프로세스, 닫힌 loop 재사용 등) 불안정해집니다.
→ 그래서 MCP 연결은 '요청(버튼 클릭) 단위로 열고 닫습니다'. 실제로 transport.acall_mcp_tool 은
   호출마다 ``async with Client(...)`` 로 새 세션을 열고 종료합니다(기존 구조 그대로).

[session_state 에 저장하는 것 / 저장하지 않는 것]
저장함(모두 'plain 데이터'):
  - last_query     : 마지막 사용자 질문(str)
  - last_state     : 마지막 LangGraph 실행 결과 State(dict)
  - tools_list     : Tool 목록 조회 결과(list[str])
  - demo_result    : 데모 실행 결과(dict of State)
  - error_messages : 오류 메시지 요약 목록(list[str])
저장 안 함(금지):
  - fastmcp.Client / StdioTransport / 서버 subprocess / 열린 async context manager / DB 연결

[async 실행 helper]
기존 runner(run_query/run_list_tools/run_demo)는 '동기' 함수입니다.
내부에서 StdioToolCaller 가 ``asyncio.run()`` 으로 stdio transport 를 호출합니다(async 캡슐화).
즉 이 Streamlit 앱은 직접 ``asyncio.run()`` 을 호출하지 않습니다. 다만 Streamlit 의 스크립트
스레드에 이미 실행 중인 event loop 가 있으면 내부 ``asyncio.run()`` 이 충돌할 수 있으므로,
runner 호출을 '깨끗한 워커 스레드'에서 실행하는 단일 helper(``run_in_worker``)로 격리합니다.
(이 격리는 Windows 에서 subprocess 에 필요한 ProactorEventLoop 도 워커 스레드에서 새로 만들어 줍니다.)

[실행 방법]
    streamlit run src/day5/mcp_client05/streamlit_app.py
  uv 사용 환경:
    uv run streamlit run src/day5/mcp_client05/streamlit_app.py
  (항상 프로젝트 루트에서 실행)

[참고] Streamlit 미설치 시에는 이 파일을 'streamlit run' 으로 띄울 수 없습니다.
       설치: ``pip install streamlit`` 또는 ``uv add streamlit``
       (이번 작업에서는 requirements.txt/pyproject.toml/uv.lock/.env 를 수정하지 않습니다.)
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# [import 경로 보강]
# streamlit 은 이 파일을 '스크립트'로 직접 실행하므로(패키지 -m 실행 아님),
# <root>/src 를 sys.path 에 넣어 'day5.mcp_client04.*' 를 import 할 수 있게 한다.
# 이 파일 <root>/src/day5/mcp_client05/streamlit_app.py → parents[3] = <root>.
_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import streamlit as st

# 기존 mcp_client04 의 public 계층만 import (서버 내부 import 금지).
from day5.mcp_client04 import config, runner


# ---------------------------------------------------------------------------
# 예시 질문 — 라우팅 유형별 대표 질문(가상 시나리오)
# ---------------------------------------------------------------------------
# 각 질문은 supervisor 라우팅이 어디로 가는지 수업에서 보여 주기 위한 것이다.
EXAMPLE_QUESTIONS = [
    "EDU-LINE-01 설비 상태를 보여줘",            # → db
    "사용 가능한 MCP Tool 목록을 보여줘",         # → tools
    "DROP TABLE equipment_status 실행해줘",      # → safety (BLOCKED)
    "매뉴얼에서 알람 대응 방법을 찾아줘",          # → rag (SKIPPED)
]


# ---------------------------------------------------------------------------
# async 실행 helper — runner(동기) 호출을 깨끗한 워커 스레드에서 실행
# ---------------------------------------------------------------------------
def run_in_worker(thunk):
    """기존 runner(동기) 호출을 Streamlit 스크립트 스레드와 분리된 워커 스레드에서 실행한다.

    [왜 워커 스레드인가]
        runner.run_query/run_list_tools/run_demo 는 동기 함수지만, 내부 StdioToolCaller 가
        ``asyncio.run()`` 으로 stdio transport 를 호출한다. Streamlit 스크립트 스레드에 이미
        실행 중인 event loop 가 있으면 ``asyncio.run()`` 이 'cannot be called from a running
        event loop' 로 실패할 수 있다. 깨끗한 워커 스레드에서 실행하면 그 스레드에는 실행 중인
        loop 가 없으므로 안전하고, Windows 에서 subprocess 에 필요한 새 event loop 도 워커
        스레드에서 만들어진다.
    [요청 단위 정리]
        ThreadPoolExecutor 를 with 로 만들어 호출이 끝나면 스레드를 정리한다(자원을 남기지 않음).
        MCP 연결 자체는 transport 가 호출마다 열고 닫으므로, 여기서 client/subprocess 를 보관하지 않는다.
    [입력] thunk: 인자 없는 호출 가능 객체(예: ``lambda: runner.run_query(q, timeout=t)``).
    [반환] thunk 의 반환값(그대로). 예외는 호출자에게 그대로 전달된다.
    """
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="mcp_client05_ui") as executor:
        return executor.submit(thunk).result()


def _safe_execute(thunk):
    """thunk 를 워커 스레드에서 실행하고 ``(result, error_text)`` 로 돌려준다.

    [오류 처리 기준]
        - 전체 traceback 을 그대로 노출하지 않는다. 짧은 요약(예외 타입/메시지)만 만든다.
        - 민감정보는 출력하지 않는다(runner/transport 가 이미 비민감 dict 로 변환하지만, 추가로
          예외 메시지는 타입 중심으로 짧게 자른다).
        - event loop 충돌(RuntimeError)은 따로 안내 문구를 붙인다.
    [반환] 정상: (result, None) / 오류: (None, error_text)
    """
    try:
        return run_in_worker(thunk), None
    except RuntimeError as error:
        # asyncio event loop 충돌 등 — 무리하게 숨기지 않고 해결 방향을 함께 안내한다.
        return None, (f"asyncio 실행 충돌 가능성({type(error).__name__}): {str(error)[:200]}\n"
                      "→ Streamlit 을 재시작하거나, 'streamlit run' 으로 단독 실행했는지 확인하세요.")
    except Exception as error:  # noqa: BLE001 - UI 경계에서 안전 요약으로 변환
        return None, f"{type(error).__name__}: {str(error)[:200]}"


# ---------------------------------------------------------------------------
# session_state 초기화 / 리셋
# ---------------------------------------------------------------------------
def init_session() -> None:
    """session_state 에 '저장 가능한 plain 데이터' 키만 초기화한다(client 객체는 절대 저장 안 함)."""
    ss = st.session_state
    ss.setdefault("query_input", "")       # 사용자 질문 입력(text_area 위젯 바인딩)
    ss.setdefault("last_query", "")        # 마지막으로 실행한 질문
    ss.setdefault("last_state", None)      # 마지막 LangGraph 실행 결과 State(dict)
    ss.setdefault("tools_list", None)      # Tool 목록 조회 결과(list[str])
    ss.setdefault("demo_result", None)     # 데모 실행 결과(dict of State)
    ss.setdefault("error_messages", [])    # 오류 메시지 요약 목록(list[str])
    # 'DB Tool 병렬 실행' 탭 — plain 데이터만 저장한다(client/transport 객체는 절대 저장 안 함).
    ss.setdefault("pdb_equipment_id", "EQP-EV-03")  # 마지막 입력 equipment_id
    ss.setdefault("pdb_line_id", "EDU-LINE-01")     # 마지막 입력 line_id
    ss.setdefault("pdb_limit", 5)                   # 마지막 입력 limit
    ss.setdefault("pdb_result", None)               # 마지막 병렬 실행 결과 dict


def reset_session() -> None:
    """세션 상태 초기화 버튼 처리 — 저장한 plain 데이터만 비운다."""
    ss = st.session_state
    ss["query_input"] = ""
    ss["last_query"] = ""
    ss["last_state"] = None
    ss["tools_list"] = None
    ss["demo_result"] = None
    ss["error_messages"] = []
    ss["pdb_result"] = None  # 병렬 실행 결과만 비운다(입력 기본값은 유지).


def _use_example() -> None:
    """예시 질문 selectbox 선택값을 질문 입력창으로 채운다(on_click 콜백).

    위젯 생성 '이전'에 동작하는 on_click 콜백에서 session_state 를 바꿔야 안전하다
    (위젯 생성 이후 같은 run 에서 위젯 키를 바꾸면 Streamlit 이 예외를 던진다).
    """
    st.session_state["query_input"] = st.session_state.get("example_select", "")


# ---------------------------------------------------------------------------
# 렌더링 — LangGraph State / 화면 출력의 연결
# ---------------------------------------------------------------------------
def render_state(state: dict) -> None:
    """LangGraph 최종 State(dict)를 교육용으로 항목별 분해해 화면에 표시한다.

    [State ↔ 화면 매핑]
        route          → 처리 경로(st.info)
        final_answer   → 최종 답변(요약 텍스트)
        safety_status  → 안전성 판정(OK / BLOCKED)
        rag_status     → RAG 처리(SKIPPED 등)
        tool_results   → 호출한 Tool / 결과 요약(비민감 dict)
        available_tools→ 조회된 업무 Tool 목록
        errors         → 오류 누적
        messages       → 중간 처리 메시지(누적 로그)
        (state 전체)    → st.json 으로 펼쳐 확인
    """
    if not isinstance(state, dict):
        st.error("실행 결과 State 가 올바른 형식이 아닙니다.")
        return

    route = state.get("route")
    safety = state.get("safety_status")
    rag = state.get("rag_status")
    errors = state.get("errors") or []
    tool_results = state.get("tool_results") or {}
    messages = state.get("messages") or []

    # 처리 경로 설명(어떤 agent 로 분기됐는지).
    st.info(f"supervisor route → **{route}** "
            "(규칙 기반 supervisor 가 질문을 분석해 단일 경로로 분기합니다)")

    # 상태 배지 3종.
    col_route, col_safety, col_rag = st.columns(3)
    col_route.metric("route", route or "-")
    col_safety.metric("safety_status", safety or "-")
    col_rag.metric("rag_status", rag or "-")

    # 최종 답변(answer_agent 가 만든 비민감 요약 텍스트).
    st.markdown("#### 최종 답변")
    if errors or rag == "ERROR":
        # 오류가 기록됐으면(또는 RAG ERROR) 성공처럼 표시하지 않는다.
        st.error("처리 중 오류가 기록되었습니다(아래 '오류 메시지'/RAG 상태 확인).")
    elif safety == "BLOCKED" or rag in ("SKIPPED", "EMPTY"):
        st.warning("정상 흐름이지만 일부 단계가 차단/생략/0건 처리되었습니다(아래 설명 참고).")
    else:
        st.success("정상 처리되었습니다.")
    st.code(state.get("final_answer") or "(최종 응답 생성 실패)", language="text")

    # safety 판정 설명.
    if safety == "BLOCKED":
        st.warning("safety_agent: 위험 SQL/데이터 변경 요청을 차단했습니다(BLOCKED). "
                   "client 는 SQL 을 실제로 실행하지 않습니다.")
    elif safety == "OK":
        st.caption("safety_agent: 위험 SQL 키워드 없음(OK).")

    # rag 판정 설명 — 상태별로 다르게 표시(성공/생략/0건/오류를 명확히 구분).
    if rag == "SKIPPED":
        st.warning("rag_agent: search_manual 은 stdio transport 환경의 timeout 가능성으로 "
                   "기본 호출하지 않고 SKIPPED 처리되었습니다(사이드바 toggle 로 HTTP 호출 활성화 가능).")
    elif rag == "OK":
        st.success("rag_agent: search_manual 을 HTTP transport 로 실제 호출해 매뉴얼 문서를 검색했습니다(OK).")
    elif rag == "EMPTY":
        st.warning("rag_agent: search_manual 을 호출했으나 관련 문서가 0건입니다(EMPTY).")
    elif rag == "ERROR":
        st.error("rag_agent: search_manual 호출이 timeout/실패했습니다(ERROR). "
                 "HTTP 서버 기동 여부와 Ollama 상태를 확인하세요(성공으로 위장하지 않음).")

    # 호출한 Tool / 결과 요약.
    st.markdown("#### 호출한 Tool / 결과 요약")
    if tool_results:
        st.write("호출한 Tool: " + ", ".join(map(str, tool_results.keys())))
        st.json(tool_results)  # 요약 dict(비민감 스칼라/개수만 — agents._summarize_envelope 가 마스킹)
    else:
        st.caption("이번 경로에서는 업무 Tool 호출이 없었습니다.")

    # 조회된 업무 Tool 목록(tools route 일 때).
    if state.get("available_tools"):
        st.markdown("#### 사용 가능한 업무 Tool")
        st.write(state["available_tools"])

    # 오류 메시지(짧은 요약만 — 전체 traceback 미노출).
    if errors:
        with st.expander("오류 메시지", expanded=True):
            for item in errors:
                st.write(f"- {item}")

    # 중간 처리 메시지(누적 로그) — 상세는 expander 로.
    with st.expander("중간 처리 메시지 (messages)"):
        if messages:
            for item in messages:
                st.write(f"- {item}")
        else:
            st.caption("기록된 중간 메시지가 없습니다.")

    # 전체 State 확인.
    with st.expander("전체 state 확인 (st.json)"):
        st.json(state)


def render_tools(tools) -> None:
    """Tool 목록 조회 결과를 표/리스트로 표시한다."""
    st.markdown("#### MCP 업무 Tool 목록")
    if not tools:
        st.warning("조회된 Tool 이 없습니다(서버 연결 실패 가능). 아래 '오류 메시지' 와 서버 로그를 확인하세요.")
        return
    st.success(f"{len(tools)}개의 업무 Tool 을 조회했습니다(standalone stdio transport).")
    # 표 형태로 보기 좋게(번호 + 이름).
    st.table([{"no": i + 1, "tool": name} for i, name in enumerate(tools)])
    with st.expander("원본(JSON) 보기"):
        st.json(list(tools))


def render_demo(demo: dict) -> None:
    """기본 데모 결과(4단계)를 expander 로 나누어 표시한다.

    demo = {"tools": [...], "db": State, "safety": State, "rag": State}
    """
    if not isinstance(demo, dict):
        st.error("데모 결과 형식이 올바르지 않습니다.")
        return

    st.markdown("#### 기본 데모 실행 결과 (4단계)")
    st.caption("각 단계는 요청 단위로 MCP 연결을 열고 닫습니다(server subprocess 누수 방지).")

    with st.expander("1) MCP stdio transport 연결 + 업무 Tool 목록", expanded=True):
        render_tools(demo.get("tools"))

    with st.expander("2) DB Tool 정상 호출 (db route)"):
        render_state(demo.get("db") or {})

    with st.expander("3) 위험 SQL 요청 차단 (safety route, BLOCKED)"):
        render_state(demo.get("safety") or {})

    with st.expander("4) RAG 질문 처리 (rag route, SKIPPED)"):
        render_state(demo.get("rag") or {})


# ---------------------------------------------------------------------------
# 사이드바 — 현재 동작 방식 안내 + 동작 버튼
# ---------------------------------------------------------------------------
def render_sidebar(timeout_default: int):
    """사이드바를 그리고, (timeout, rag_options) 를 돌려준다.

    [버튼 → 호출 매핑]
        - Tool 목록 조회   → runner.run_list_tools (mcp_tools/transport 계층 경유)
        - 기본 데모 실행   → runner.run_demo       (연결→목록→DB→위험SQL차단→RAG SKIPPED)
        - 세션 상태 초기화 → reset_session
    [RAG over HTTP — 2차 확장]
        toggle 을 켜면 사용자 질문 실행 시 allow_rag=True + http transport 로 search_manual 을 실제
        호출한다. HTTP 서버는 client 가 spawn 하지 않으므로, 사용자가 별도 터미널에서 미리 띄워야 한다.
    [반환] (timeout:int, rag_options:dict) — rag_options={"allow_rag", "http_url"}.
    """
    with st.sidebar:
        st.header("실행 환경 / 경계")
        # 현재 동작 방식(읽기 전용 안내) — 민감정보(키/비밀번호/환경변수)는 표시하지 않는다.
        st.markdown(
            "- transport 방식: **stdio**(기본) / **http**(RAG 활성 시)\n"
            "- MCP 서버 실행: **standalone subprocess** (`-m day5.mcp_server03.mcp_server`)\n"
            "- MCP client 보관: **요청 단위 생성/정리** (session_state 미저장)\n"
            "- RAG 실행 상태: **기본 비활성화** (toggle 로 활성)\n"
            "- search_manual: **SKIPPED**(기본) / **HTTP 호출**(활성)\n"
            "- 민감정보 출력: **출력하지 않음**"
        )

        st.divider()
        st.subheader("Tool 호출 timeout")
        timeout = st.number_input(
            "timeout(초) — 무한 대기 방지",
            min_value=5, max_value=120, value=int(timeout_default), step=5,
            help="stdio Tool 호출 단위 timeout. RAG-over-stdio 지연 대비.",
        )

        st.divider()
        st.subheader("RAG (search_manual) — 2차 확장")
        # toggle: 켜면 사용자 질문 실행 시 http transport 로 search_manual 을 실제 호출한다.
        # 기본값은 프로젝트 기본(config.ALLOW_RAG_DEFAULT) — RAG 가 기본 활성이면 toggle 도 기본 ON.
        # OFF 로 내리면 stdio 오프라인(서버 불필요, search_manual SKIPPED)으로 동작한다.
        allow_rag = st.toggle(
            "search_manual 실제 호출 (HTTP)",
            value=config.ALLOW_RAG_DEFAULT,
            help="켜면 RAG 질문에서 search_manual 을 실제 호출합니다(HTTP 서버 선기동 필요). "
                 "끄면 오프라인 stdio(SKIPPED).",
        )
        http_url = config.MCP_HTTP_URL
        if allow_rag:
            # 활성일 때만 URL 입력 노출. 서버 선기동 안내(client 는 서버를 spawn 하지 않음).
            http_url = st.text_input("MCP HTTP URL", value=config.MCP_HTTP_URL,
                                     help="외부에서 실행 중인 streamable-http 서버 endpoint")
            st.info(
                "RAG 활성 모드: 먼저 별도 터미널에서 HTTP 서버를 띄우세요(없으면 rag_status=ERROR 정직 표기).\n\n"
                "```\n"
                "$env:PYTHONPATH=\"src\"\n"
                "python -m day5.mcp_server03.mcp_server --transport streamable-http "
                "--host 127.0.0.1 --port 8000 --path /mcp\n"
                "```"
            )

        st.divider()
        st.subheader("동작")
        # 각 버튼은 누른 즉시(같은 run 안에서) 처리한다 — 결과는 session_state 에 저장하고
        # 메인 영역에서 렌더한다. MCP client 객체는 저장하지 않는다.
        # (Tool 목록/데모 버튼은 RAG 와 무관한 stdio 동작 그대로 유지한다.)
        if st.button("Tool 목록 조회", use_container_width=True):
            with st.spinner("MCP Tool 목록 조회 중... (요청 단위 연결/정리)"):
                tools, err = _safe_execute(lambda: runner.run_list_tools(timeout=int(timeout)))
            if err:
                st.session_state["error_messages"].append(f"[list-tools] {err}")
            st.session_state["tools_list"] = tools  # None 이면 렌더에서 실패 안내

        if st.button("기본 데모 실행", use_container_width=True):
            with st.spinner("기본 데모 실행 중... (연결→목록→DB→위험SQL차단→RAG SKIPPED)"):
                demo, err = _safe_execute(lambda: runner.run_demo(timeout=int(timeout)))
            if err:
                st.session_state["error_messages"].append(f"[demo] {err}")
            st.session_state["demo_result"] = demo

        if st.button("세션 상태 초기화", use_container_width=True):
            reset_session()
            st.success("세션 상태를 초기화했습니다.")

    return int(timeout), {"allow_rag": bool(allow_rag), "http_url": http_url}


# ---------------------------------------------------------------------------
# 메인 화면
# ---------------------------------------------------------------------------
def render_query_section(timeout: int, rag_options: dict) -> None:
    """사용자 질문 입력 + LangGraph 실행 영역.

    [rag_options] 사이드바 toggle 결과({"allow_rag", "http_url"}). allow_rag 면 http transport 로
    search_manual 을 실제 호출한다(아니면 기존 stdio + RAG SKIPPED).
    """
    st.subheader("사용자 질문 실행")
    if rag_options.get("allow_rag"):
        st.caption(f"RAG 활성 모드: http transport → {rag_options.get('http_url')} "
                   "(search_manual 실제 호출)")

    # 예시 질문(selectbox) → '예시 질문 사용' 버튼으로 입력창 채우기.
    col_sel, col_btn = st.columns([4, 1])
    with col_sel:
        st.selectbox("예시 질문", EXAMPLE_QUESTIONS, key="example_select")
    with col_btn:
        st.write("")  # 버튼 높이 맞추기용 여백
        st.button("예시 질문 사용", on_click=_use_example, use_container_width=True)

    # 질문 입력창(session_state['query_input'] 에 바인딩).
    st.text_area("질문을 입력하세요", key="query_input", height=90,
                 placeholder="예) EDU-LINE-01 설비 상태를 보여줘")

    # LangGraph 실행 버튼 → runner.run_query (기존 graph/agent 흐름 그대로 사용).
    if st.button("LangGraph 실행", type="primary"):
        query = str(st.session_state.get("query_input", "")).strip()
        if not query:
            st.warning("질문을 입력하세요.")
        else:
            st.session_state["last_query"] = query
            # allow_rag 면 http transport 로 search_manual 실제 호출, 아니면 기존 stdio(RAG SKIPPED).
            allow_rag = bool(rag_options.get("allow_rag"))
            transport = "http" if allow_rag else None
            http_url = rag_options.get("http_url")
            with st.spinner("LangGraph 실행 중... (supervisor → agent → answer, 요청 단위 MCP 연결)"):
                state, err = _safe_execute(lambda: runner.run_query(
                    query, timeout=timeout, allow_rag=allow_rag,
                    transport=transport, http_url=http_url))
            if err:
                st.session_state["error_messages"].append(f"[query] {err}")
                st.session_state["last_state"] = None
            else:
                st.session_state["last_state"] = state


# ---------------------------------------------------------------------------
# 'DB Tool 병렬 실행' 탭 — 안전한 DB 조회 Tool 여러 개를 동시에 호출하는 교육용 비교 데모
# ---------------------------------------------------------------------------
# [이 탭의 목적 — 전체 Agent 병렬화가 아니라 'DB 조회 Tool 만' 병렬]
#   기본 탭(supervisor → 단일 agent → answer)은 순차형이다(LangGraph 구조 무수정 유지).
#   이 탭은 같은 설비/라인 ID 로 '안전한 DB 조회 Tool' 여러 개를 동시에 호출해, 순차 대비 병렬의
#   차이를 수업에서 비교하기 위한 데모다. 운영용 자동 의사결정이 아니라 비교 화면이다.
#   - SQL 입력을 받지 않는다(equipment_id/line_id/limit 만). execute_sql/RAG 는 호출 대상이 아니다.
#   - 실행은 runner.run_parallel_db_tools_demo 가 담당한다(이 UI 는 입력 수집/결과 표시만).
HTTP_SERVER_RUN_COMMAND = (
    "uv run python -m src.day5.mcp_server03.mcp_server "
    "--transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp"
)


def render_parallel_db_result(result: dict) -> None:
    """병렬 DB Tool 실행 결과 dict 를 요약/Tool별/스킵/전체 JSON 으로 표시한다.

    [표시 원칙] 성공/실패/스킵을 정직하게 구분한다(timeout/연결 실패를 성공처럼 보이지 않게).
               결과는 runner 단계에서 이미 비민감 요약(개수/스칼라)으로 변환돼 있다.
    """
    if not isinstance(result, dict):
        st.error("병렬 실행 결과 형식이 올바르지 않습니다.")
        return

    # 연결 실패: HTTP 서버 미기동을 숨기지 않고, 실행 명령을 함께 안내한다.
    if result.get("status") == "connection_error":
        st.error(
            "HTTP MCP 서버에 연결할 수 없습니다.\n\n"
            "streamable-http 서버가 실행 중인지 확인해 주세요.\n\n"
            "실행 명령:"
        )
        st.code(HTTP_SERVER_RUN_COMMAND, language="bash")
        with st.expander("전체 병렬 실행 결과 JSON"):
            st.json(result)
        return

    called = result.get("called_count", 0)
    success = result.get("success_count", 0)
    error = result.get("error_count", 0)
    skipped = result.get("skipped_count", 0)

    # 요약 — 전체 성공/일부 실패·스킵/전체 실패를 색으로 구분.
    st.markdown("#### 실행 요약")
    if called == 0:
        st.info("호출 대상 Tool 이 없습니다. 입력값으로 필수 인자를 구성할 수 있는 안전 조회 Tool 이 없습니다.")
    elif error == 0 and skipped == 0:
        st.success(f"전체 성공: {success}개 DB 조회 Tool 을 병렬 호출했습니다.")
    elif error >= called:
        st.error(f"전체 실패: 호출한 {called}개 Tool 이 모두 실패했습니다.")
    else:
        st.warning(f"일부 실패/스킵: 성공 {success} · 실패 {error} · 스킵 {skipped}.")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("transport", result.get("transport", "-"))
    col2.metric("tool_count", result.get("tool_count", 0))
    col3.metric("called", called)
    col4.metric("elapsed(s)", result.get("elapsed_sec", 0.0))
    col5, col6, col7, _ = st.columns(4)
    col5.metric("success", success)
    col6.metric("error", error)
    col7.metric("skipped", skipped)

    inputs = result.get("inputs") or {}
    st.caption(f"입력 — equipment_id={inputs.get('equipment_id')} · "
               f"line_id={inputs.get('line_id')} · limit={inputs.get('limit')}")

    # Tool별 결과 — expander 로 분리(최종 답변 1개로 병합하지 않고 Tool별 비교).
    st.markdown("#### Tool별 결과")
    results = result.get("results") or {}
    if not results:
        st.caption("호출된 Tool 결과가 없습니다.")
    for tool_name, summary in results.items():
        summary = summary or {}
        tstatus = summary.get("status")
        is_err = bool(summary.get("error")) or tstatus in ("timeout", "error", "rejected", "needs_review")
        label = f"{tool_name} 결과 (status={tstatus})" + ("  ⚠️ 오류" if is_err else "")
        with st.expander(label, expanded=not is_err):
            st.write(f"- status: {tstatus}")
            if summary.get("data_source") is not None:
                st.write(f"- data_source: {summary.get('data_source')}")
            if is_err:
                st.warning(f"오류 발생: {summary.get('error') or tstatus}")
            # 비민감 요약(개수/스칼라)만 JSON 으로 표시(원문/민감 필드는 runner 가 이미 제거).
            st.json(summary)

    # 스킵된 Tool — 필수 인자를 구성할 수 없어 호출하지 않은 Tool 과 사유.
    skipped_tools = result.get("skipped_tools") or []
    if skipped_tools:
        with st.expander(f"스킵된 Tool 목록 ({len(skipped_tools)})"):
            for item in skipped_tools:
                st.write(f"- **{item.get('tool_name')}**: {item.get('reason')}")

    # 전체 결과 JSON(이미 비민감 요약만 포함).
    with st.expander("전체 병렬 실행 결과 JSON"):
        st.json(result)


def render_parallel_db_section(timeout: int) -> None:
    """'DB Tool 병렬 실행' 탭 본문 — 입력 UI + 병렬 실행 버튼 + 결과 표시.

    [기본 탭과의 차이]
        기본 탭은 supervisor 가 질문을 분석해 단일 경로로 분기하는 순차형이다. 이 탭은 같은 설비/라인
        ID 로 여러 DB 조회 Tool 을 동시에 호출하는 병렬 데모다(전체 Agent 병렬화 아님).
    [SQL 미입력 이유] DB 직접 접속/SQL 실행은 안전성 검토가 별도로 필요하므로 이 탭에서는 받지 않는다.
        식별자(equipment_id/line_id)와 limit 만 받아 안전한 조회 Tool 만 호출한다.
    """
    st.subheader("DB Tool 병렬 실행 (교육용 비교 데모)")
    st.caption(
        "같은 설비/라인 ID로 설비 개요·최근 알람·품질 지표·정비 이력 같은 안전한 조회 Tool을 동시에 "
        "호출합니다. 전체 Agent 병렬화가 아니라 안전한 DB 조회 Tool만 병렬 호출하는 데모입니다."
    )

    # HTTP transport 권장 안내 + 서버 실행 명령(서버는 이 앱이 띄우지 않으므로 사용자가 먼저 기동).
    st.info(
        "**HTTP transport 권장**(stdio 는 호출마다 서버 subprocess 를 새로 spawn 해 병렬에 무거움). "
        "먼저 별도 터미널에서 streamable-http 서버를 띄우세요:"
    )
    st.code(HTTP_SERVER_RUN_COMMAND, language="bash")

    # 입력값 — SQL 이 아니라 식별자/limit 만 받는다.
    col_eq, col_ln, col_lim = st.columns(3)
    with col_eq:
        st.text_input("equipment_id", key="pdb_equipment_id", help="조회할 설비 ID(가상). 예: EQP-EV-03")
    with col_ln:
        st.text_input("line_id", key="pdb_line_id", help="조회할 라인 ID(가상). 예: EDU-LINE-01")
    with col_lim:
        st.number_input("limit", min_value=1, max_value=50, step=1, key="pdb_limit",
                        help="목록형 Tool 의 최대 건수(schema 에 limit 가 있는 Tool 에만 전달)")

    # transport 선택 — 기본 http 권장. stdio 는 병렬 데모에 권장하지 않는다고 안내.
    transport = st.selectbox(
        "transport", ["http", "stdio"], index=0,
        help="병렬 데모는 http 권장. stdio 는 호출마다 서버 subprocess 를 생성해 무겁습니다.")
    if transport == "stdio":
        st.warning("stdio 는 병렬 호출 데모에 권장하지 않습니다(호출마다 서버 subprocess spawn). "
                   "long-lived HTTP 서버 사용을 권장합니다.")
    http_url = st.text_input("MCP HTTP URL", value=config.MCP_HTTP_URL,
                             help="외부에서 실행 중인 streamable-http 서버 endpoint",
                             disabled=(transport != "http"))

    # 병렬 실행 — runner.run_parallel_db_tools_demo 를 워커 스레드에서 호출(client 객체는 저장 안 함).
    if st.button("DB Tool 병렬 실행", type="primary", key="pdb_run"):
        equipment_id = str(st.session_state.get("pdb_equipment_id", "")).strip()
        line_id = str(st.session_state.get("pdb_line_id", "")).strip()
        limit = int(st.session_state.get("pdb_limit", 5))
        with st.spinner("DB 조회 Tool 병렬 호출 중... (작업마다 독립 caller 생성, 요청 단위 연결/정리)"):
            result, err = _safe_execute(lambda: runner.run_parallel_db_tools_demo(
                equipment_id=equipment_id, line_id=line_id, limit=limit,
                timeout=timeout, transport=transport, http_url=http_url))
        if err:
            st.session_state["error_messages"].append(f"[parallel-db] {err}")
            st.session_state["pdb_result"] = None
        else:
            st.session_state["pdb_result"] = result

    # 결과 표시(있으면).
    if st.session_state.get("pdb_result") is not None:
        st.divider()
        render_parallel_db_result(st.session_state["pdb_result"])


def render_flow_explanation() -> None:
    """교육용 흐름 설명 영역(화면 하단 expander)."""
    with st.expander("교육용 흐름 설명 (LangGraph 멀티 에이전트)"):
        st.markdown(
            "```\n"
            "사용자 질문\n"
            "  → supervisor_agent 라우팅 (규칙 기반: safety > tools > rag > db > answer)\n"
            "  → tool_discovery_agent / db_agent / safety_agent / rag_agent\n"
            "  → answer_agent\n"
            "  → 최종 응답\n"
            "```"
        )
        st.markdown(
            "**질문 유형별 기대 동작**\n"
            "- DB 조회 질문 → `db_agent` (안전한 SELECT 계열 업무 Tool 1건 호출)\n"
            "- Tool 목록 질문 → `tool_discovery_agent`\n"
            "- 위험 SQL 요청 → `safety_agent` (BLOCKED, client 는 실행하지 않음)\n"
            "- 매뉴얼/RAG 질문 → `rag_agent` 기본 **SKIPPED** / RAG toggle ON 시 **HTTP 실제 호출**\n"
            "- 기타 질문 → `answer_agent` 안내 응답"
        )
        st.info(
            "`search_manual` 은 **기본 SKIPPED** 입니다(stdio transport 환경의 timeout 가능성, "
            "mcp_client03 검증).\n\n"
            "**2차 확장:** 사이드바의 'search_manual 실제 호출 (HTTP)' toggle 을 켜면 "
            "streamable-http transport 로 전환되어 실제로 호출합니다(rag_status: OK/EMPTY/ERROR). "
            "이때는 먼저 별도 터미널에서 HTTP 서버를 띄워야 합니다."
        )


def render_error_panel() -> None:
    """누적 오류 메시지를 화면 하단에 제한적으로 표시한다(전체 traceback 미노출)."""
    errors = st.session_state.get("error_messages") or []
    if not errors:
        return
    st.divider()
    st.error(f"이번 세션에서 {len(errors)}건의 오류가 기록되었습니다.")
    with st.expander("오류 메시지 상세 (요약만)"):
        for item in errors:
            st.write(f"- {item}")
        st.caption("다음 확인 사항: 서버 로그(outputs/day5/mcp_client04_server.log), "
                   "CLI 재현(`python -m src.day5.mcp_client04 --list-tools`).")


def main() -> None:
    """Streamlit 앱 진입점 — 제목 → 사이드바 → 결과 영역 → 질문 실행 → 흐름 설명 순으로 그린다."""
    st.set_page_config(page_title="MCP Client05 UI (Client04 LangGraph Demo)", layout="wide")
    init_session()

    # 1) 제목 영역.
    st.title("MCP Client05 UI — Client04 LangGraph Demo")
    st.caption(
        "standalone MCP stdio transport 기반 client · LangGraph 멀티에이전트 흐름 · "
        "DB Tool 중심 실행 · search_manual RAG 는 기본 SKIPPED · "
        "client05 는 화면 계층(실행은 mcp_client04 runner/config 재사용)"
    )

    # 2) 사이드바(안내 + 동작 버튼) — 버튼 결과는 session_state 에 저장됨.
    #    rag_options = {"allow_rag", "http_url"} (RAG over HTTP toggle 결과). 사이드바는 탭 공통이다.
    timeout, rag_options = render_sidebar(config.DEFAULT_TIMEOUT)

    # 3) 탭 구성 — 기본 흐름은 '기본 LangGraph 실행' 탭에 그대로 유지하고(순차형),
    #    '안전한 DB 조회 Tool 병렬 호출' 비교 데모는 새 탭에 둔다(기존 LangGraph 구조 무수정).
    tab_basic, tab_parallel_db = st.tabs(["기본 LangGraph 실행", "DB Tool 병렬 실행"])

    # --- 기본 LangGraph 실행 탭(기존 화면 그대로) ---------------------------------
    with tab_basic:
        # Tool 목록 조회 결과(있으면).
        if st.session_state.get("tools_list") is not None:
            st.divider()
            render_tools(st.session_state["tools_list"])
        # 기본 데모 결과(있으면).
        if st.session_state.get("demo_result") is not None:
            st.divider()
            render_demo(st.session_state["demo_result"])
        # 사용자 질문 실행 영역(supervisor → 단일 agent → answer, 순차형).
        st.divider()
        render_query_section(timeout, rag_options)
        # 마지막 질문 실행 결과(있으면).
        if st.session_state.get("last_state") is not None:
            st.markdown("### 실행 결과")
            st.caption(f"질문: {st.session_state.get('last_query', '')}")
            render_state(st.session_state["last_state"])
        # 교육용 흐름 설명.
        st.divider()
        render_flow_explanation()

    # --- DB Tool 병렬 실행 탭(신규 교육용 비교 데모) -------------------------------
    with tab_parallel_db:
        render_parallel_db_section(timeout)

    # 4) 누적 오류 패널(탭 공통, 화면 하단).
    render_error_panel()


# streamlit 은 이 스크립트를 top-level 로 실행하므로 main() 을 바로 호출한다.
main()
