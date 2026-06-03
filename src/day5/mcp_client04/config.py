# -*- coding: utf-8 -*-
"""
Day5 mcp_client04 - 설정 (config)

[이 파일의 역할]
mcp_client04 가 standalone MCP 서버(mcp_server03)를 stdio 로 실행/접속할 때 쓰는 설정값을 모읍니다.
mcp_client03 에서 검증된 실행 방식(command/args/cwd/env/log_file)을 그대로 재사용합니다.

[중요 — 경계]
여기서는 '서버를 어떻게 실행할지'만 정의합니다. mcp_server03 의 내부 함수/모듈을 직접 import 하지
않습니다. 서버는 별도 프로세스로 실행되고, client 는 transport(stdio)로만 접속합니다.

[보안]
- 접속 비밀값(.env 등)은 서브프로세스 환경에 '상속'만 하고, 코드/로그에 값을 출력하지 않습니다.
- 서버 배너/로그(stderr)는 client 출력과 섞이지 않도록 log_file 로 분리합니다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


# 경로: 이 파일 <root>/src/day5/mcp_client04/config.py → parents[3] = <root>
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"

# 서버 실행 명령(mcp_client03 과 동일): python -m day5.mcp_server03.mcp_server → stdio MCP 서버.
# [주의] 서버 함수를 import 하지 않고, '서브프로세스 실행'으로만 띄운다.
SERVER_COMMAND = sys.executable
SERVER_ARGS = ["-m", "day5.mcp_server03.mcp_server"]

# 서버 stderr/로그를 분리해 둘 파일(콘솔 출력 정돈). outputs 아래.
SERVER_LOG_PATH = PROJECT_ROOT / "outputs" / "day5" / "mcp_client04_server.log"

# 서버가 MCP 로 노출하는 'wrapper Tool' 이름(mcp_client03 에서 검증됨).
#   - LIST_TOOL : 업무 Tool 목록을 돌려주는 wrapper.
#   - CALL_TOOL : 업무 Tool 을 호출하는 wrapper(인자: {"tool_name", "arguments"}).
# 업무 Tool(get_equipment_overview 등)은 CALL_TOOL 을 통해 호출한다(직접 등록 Tool 아님).
MCP_LIST_TOOL = "list_mcp_tools"
MCP_CALL_TOOL = "call_mcp_tool"

# RAG 업무 Tool 이름(추측 금지 — 서버 contract 와 일치, mcp_client03/서버 schema 에서 검증됨).
# search_manual 도 직접 등록 Tool 이 아니라 CALL_TOOL 경유로 호출한다(arguments={"query", "alarm_code"?}).
MCP_SEARCH_TOOL = "search_manual"

# Tool 호출 기본 timeout(초). RAG(search_manual)는 stdio 환경에서 지연될 수 있어(아래) 호출 단위 timeout 으로 보호한다.
DEFAULT_TIMEOUT = 30

# RAG 전용 timeout(초). search_manual 은 chroma+임베딩 비용으로 DB Tool 보다 느리므로 더 넉넉히 둔다.
# (long-lived HTTP 서버에서는 초기화가 1회뿐이라 수초 내 응답하지만, 첫 호출/임베딩 로딩 지연을 흡수.)
RAG_TIMEOUT = 60

# --- transport 선택 ---------------------------------------------------------
# 기본 transport. 'stdio'(기존 동작) 가 기본이다.
#   - stdio : Tool 호출마다 서버 서브프로세스를 새로 spawn(기존 mcp_client03 검증 방식).
#   - http  : 외부에서 이미 실행 중인 long-lived streamable-http 서버 URL 에 접속(client 가 spawn 안 함).
# RAG(search_manual)는 stdio 에서 timeout 가능성이 있어, --allow-rag 시 http 로 전환해 쓴다(README 참조).
DEFAULT_TRANSPORT = "stdio"

# http transport 일 때 접속할 MCP endpoint URL.
#   이 수업에서는 서버를 8000 포트로 띄운다 → client 기본 URL 도 8000 으로 맞춘다.
#   [주의] mcp_server03 의 --port '기본값'은 8003 이므로, 서버를 띄울 때 반드시 --port 8000 을 명시해야
#          이 URL 과 일치한다. 포트를 바꾸려면 서버 --port 와 이 URL(또는 --http-url)을 함께 맞춘다.
#   fastmcp.Client 는 URL 문자열을 받으면 streamable-http transport 로 자동 추론한다.
MCP_HTTP_URL = "http://127.0.0.1:8000/mcp"

# RAG(search_manual) 기본 실행 여부.
#   기본을 True 로 둔다 → 사용자 질문(run_query/CLI)은 별도 플래그 없이도 RAG 를 실제 호출한다.
#   [전제] allow_rag=True 면 transport 가 http 로 전환되므로(_resolve_transport), 외부에서 long-lived
#          streamable-http 서버가 떠 있어야 한다. 서버가 없으면 rag_status=ERROR(정직 표기).
#   [오프라인/서버 없이 쓰려면] CLI 는 --no-rag(또는 --transport stdio)로 끈다.
#   (UI(mcp_client05)는 client04 runner/config 를 재사용하며, toggle 로 같은 allow_rag 를 끈다.)
#   [주의] stdio 서버 서브프로세스로 search_manual 을 호출하면 timeout/hang 가능성이 있어, RAG 는
#          stdio 가 아니라 http 로만 호출한다(DEFAULT_TRANSPORT 자체는 stdio 로 두고 allow_rag 가 http 로 끌어올린다).
ALLOW_RAG_DEFAULT = True

# 위험 SQL/데이터 변경 키워드(safety_agent 가 차단 판정에 사용). 대소문자 무시 비교.
DANGEROUS_SQL_KEYWORDS = (
    "drop", "delete", "update", "insert", "alter", "truncate",
    "grant", "revoke", "merge",
)


def get_server_env() -> dict:
    """서버 서브프로세스에 넘길 환경변수 dict 를 만든다.

    [동작]
        현재 환경을 상속하되, 서브프로세스가 day5.* 패키지를 찾도록 PYTHONPATH=src 를 주입한다.
    [보안]
        비밀값을 새로 만들거나 출력하지 않는다. 상속만 한다.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return env
