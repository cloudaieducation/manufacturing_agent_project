# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 패키지 실행 진입점 (CLI).

[실행]
    python -m day5.mcp_client04 --demo
    python -m day5.mcp_client04 --list-tools
    python -m day5.mcp_client04 --query "EDU-LINE-01 설비 상태를 보여줘"
    (PYTHONPATH=src 또는 src 를 cwd. python -m src.day5.mcp_client04 형태도 동작하도록 sys.path 를 보강한다.)

[옵션]
- --demo       : 기본 데모 시나리오(연결→목록→DB→위험SQL차단→RAG SKIPPED).
- --list-tools : 업무 Tool 목록만 조회.
- --query Q    : 질문 1건을 멀티 에이전트 그래프로 실행.
- --timeout N  : Tool 호출 timeout(초). 무한 대기 방지.
- --allow-rag  : RAG(search_manual) 실제 호출 강제 활성(기본이 이미 활성이면 동일).
- --no-rag     : RAG 비활성(오프라인 stdio). search_manual 은 SKIPPED.
- --transport  : stdio | http. 미지정 시 RAG 활성이면 http, 아니면 stdio.
- --http-url   : http transport 접속 URL(기본 config.MCP_HTTP_URL).

[기본 동작 — 중요]
  RAG 가 '기본 활성'(config.ALLOW_RAG_DEFAULT=True)이라, 그냥 --query 만 줘도 http 로 전환되어
  search_manual 을 실제 호출한다. 따라서 먼저 별도 터미널에서 streamable-http 서버를 띄워야 한다
  (README 11절). 서버 없이 오프라인으로 쓰려면 --no-rag(또는 --transport stdio).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# [import 경로 보강] 이 파일 <root>/src/day5/mcp_client04/__main__.py → parents[3] = <root>
# <root>/src 를 sys.path 에 넣어 'day5.mcp_client04.*' 가 어떤 -m 형태에서도 import 되게 한다.
_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from day5.mcp_client04 import config, runner


def _print_state(state: dict) -> None:
    """그래프 최종 State 에서 final_answer 를 출력한다(요약본만)."""
    print(state.get("final_answer", "(최종 응답 생성 실패)"))


def main() -> None:
    """CLI 진입점: --demo / --list-tools / --query 중 하나를 처리한다."""
    parser = argparse.ArgumentParser(
        description="mcp_client04 - standalone stdio transport + LangGraph 멀티 에이전트(최소)"
    )
    parser.add_argument("--demo", action="store_true", help="기본 데모 시나리오 실행")
    parser.add_argument("--list-tools", dest="list_tools", action="store_true", help="업무 Tool 목록 조회")
    parser.add_argument("--query", default=None, help="질문 1건을 멀티 에이전트 그래프로 실행")
    parser.add_argument("--timeout", type=int, default=config.DEFAULT_TIMEOUT,
                        help="Tool 호출 timeout(초). 무한 대기 방지(특히 RAG over stdio)")
    # RAG 기본 활성(config.ALLOW_RAG_DEFAULT). --allow-rag 로 강제 켜고, --no-rag 로 끈다.
    #   (allow_rag=True → transport 가 http 로 전환되므로 HTTP 서버를 먼저 띄워야 한다.)
    parser.add_argument("--allow-rag", dest="allow_rag", action="store_true",
                        help="RAG(search_manual) 실제 호출 강제 활성. 미지정 transport 면 http 로 전환(서버 선기동 필요)")
    parser.add_argument("--no-rag", dest="allow_rag", action="store_false",
                        help="RAG 비활성(오프라인 stdio). search_manual 은 SKIPPED")
    parser.set_defaults(allow_rag=config.ALLOW_RAG_DEFAULT)
    parser.add_argument("--transport", default=None, choices=["stdio", "http"],
                        help="transport 선택. 미지정 시 allow_rag 면 http, 아니면 stdio. http 는 외부 long-lived 서버 접속")
    parser.add_argument("--http-url", dest="http_url", default=config.MCP_HTTP_URL,
                        help=f"http transport 접속 URL(기본 {config.MCP_HTTP_URL})")
    args = parser.parse_args()

    if args.list_tools:
        names = runner.run_list_tools(timeout=args.timeout,
                                      transport=args.transport, http_url=args.http_url)
        transport_label = "http" if args.transport == "http" else "stdio"
        print(f"[업무 Tool 목록] ({transport_label} transport)")
        for name in names:
            print(f"- {name}")
        return

    if args.query:
        _print_state(runner.run_query(args.query, timeout=args.timeout,
                                      allow_rag=args.allow_rag,
                                      transport=args.transport, http_url=args.http_url))
        return

    if args.demo:
        result = runner.run_demo(timeout=args.timeout)
        print("[1] MCP stdio transport 연결 + 업무 Tool 목록")
        for name in result.get("tools", []):
            print(f"- {name}")
        print("\n[2] DB Tool 정상 호출(db route)")
        _print_state(result["db"])
        print("\n[3] 위험 SQL 요청 차단(safety route)")
        _print_state(result["safety"])
        print("\n[4] RAG 질문 처리(rag route, SKIPPED)")
        _print_state(result["rag"])
        print("\n[참고] LangGraph 단일 경로(supervisor→1 agent→answer). "
              "RAG는 기본 SKIPPED, 실제 호출은 --allow-rag(+HTTP 서버).")
        return

    # 옵션 미지정 시 데모 안내.
    parser.print_help()


if __name__ == "__main__":
    main()
