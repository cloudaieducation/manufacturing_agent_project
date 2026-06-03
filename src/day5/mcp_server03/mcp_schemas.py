# -*- coding: utf-8 -*-
"""
Day5 mcp_server03 - MCP Schemas (contracts → MCP Tool schema 변환)

[이 모듈의 역할]
contracts.py 의 Tool 정의(ALLOWED_TOOLS, TOOL_CONTRACTS)를 읽어,
MCP Tool 의 input schema(JSON Schema 형태 dict)로 '변환만' 합니다.

[가장 중요한 원칙 — schema 중복 정의 금지]
이 파일은 Tool 이름이나 argument 목록을 새로 정의하지 않습니다.
모든 기준은 contracts.py 한 곳(single source of truth)에서만 옵니다.
→ contracts 와 mcp_schemas 가 서로 다른 schema 를 갖는 '불일치' 사고를 원천 차단합니다.
   (검증: get_exposed_mcp_tool_names() 결과 == ALLOWED_TOOLS 여야 합니다.)

[FORBIDDEN_SQL_TOOLS 제외]
Text-to-SQL / SQL 실행 계열 Tool 은 MCP Tool 목록에 절대 노출하지 않습니다.
ALLOWED_TOOLS 와 FORBIDDEN_SQL_TOOLS 는 교집합이 없지만, 방어적으로 한 번 더 거릅니다.

[MCP SDK 비의존]
MCP SDK 가 없어도 이 모듈은 순수 dict 를 만들어 반환합니다.
실제 MCP 서버 등록은 mcp_server.py 가 담당하며, SDK 가 있으면 이 dict 를 그대로 사용합니다.

[전체 흐름에서의 위치]
    contracts.py (기준)
        ↓ 변환
    [mcp_schemas]  → list_mcp_tools() 가 노출할 Tool schema 생성
        ↓
    mcp_server.list_mcp_tools()
"""
# contracts 가 schema 의 single source of truth 다. 이 모듈은 Tool 이름/argument 를
# 새로 정의하지 않고, 아래 세 기준만 읽어 MCP Tool input schema(dict)로 '변환'만 한다.
#   - ALLOWED_TOOLS       : 노출 대상 Tool 이름(허용 목록).
#   - FORBIDDEN_SQL_TOOLS : 노출에서 제외할 SQL 계열 Tool(방어적 재확인용).
#   - TOOL_CONTRACTS      : 각 Tool 의 purpose/required/any_of/optional 정의.
from day5.mcp_server03.contracts import (
    ALLOWED_TOOLS,
    FORBIDDEN_SQL_TOOLS,
    TOOL_CONTRACTS,
)


# ---------------------------------------------------------------------------
# argument 이름 → JSON Schema type 추정 규칙
# ---------------------------------------------------------------------------
# [용도] build_single_tool_schema() 에서 각 argument 의 JSON Schema "type" 을 정한다.
# [근거] 교육용 가상 시나리오의 argument 의미에 맞춘 단순 매핑이다.
#        limit 만 정수이고 나머지는 문자열로 취급한다(날짜 범위/코드/이름 등은 문자열).
# [주의] contracts 에 없는 새 argument 가 생기면 기본값 "string" 으로 처리된다.
_ARG_TYPE_HINTS = {
    "limit": "integer",
}


def _arg_type(arg_name):
    """argument 이름으로 JSON Schema type 문자열을 돌려준다(기본 string)."""
    return _ARG_TYPE_HINTS.get(arg_name, "string")


def get_exposed_mcp_tool_names():
    """MCP 로 노출할 Tool 이름 목록을 돌려준다.

    [반환]
        list[str] — ALLOWED_TOOLS 에서 FORBIDDEN_SQL_TOOLS 를 제외한 목록.
                    (둘은 교집합이 없으므로 정상 환경에서는 ALLOWED_TOOLS 와 동일하다.)

    [검증 포인트]
        set(get_exposed_mcp_tool_names()) == set(ALLOWED_TOOLS) 여야 한다.
        만약 다르면 contracts 에서 ALLOWED_TOOLS 와 FORBIDDEN_SQL_TOOLS 가
        잘못 겹친 것이므로 즉시 점검해야 한다.

    [호출 시점]
        mcp_server 가 노출 Tool 목록을 확인할 때, 그리고 검증 스크립트에서.
    """
    forbidden = set(FORBIDDEN_SQL_TOOLS)
    return [name for name in ALLOWED_TOOLS if name not in forbidden]


def build_single_tool_schema(tool_name):
    """tool_name 하나에 대한 MCP Tool schema dict 를 contracts 기준으로 만든다.

    [입력]
        tool_name: ALLOWED_TOOLS 에 속한 Tool 이름.
    [반환]
        {
          "name": <tool_name>,
          "description": <purpose + any_of 안내>,
          "inputSchema": {
            "type": "object",
            "properties": { <arg>: {"type": ..., "description": ...}, ... },
            "required": [ <required_arguments> ],
            "additionalProperties": False
          }
        }

    [동작]
        1) FORBIDDEN_SQL_TOOLS 또는 미등록 tool 이면 ValueError(노출 금지).
        2) TOOL_CONTRACTS[tool_name] 에서 required/any_of/optional 을 읽는다.
        3) 세 그룹의 argument 를 모두 properties 에 넣는다(중복 정의 없이 contracts 기준).
        4) required_arguments 만 JSON Schema "required" 로 변환한다.
           any_of_required_arguments 는 JSON Schema 로 강제하지 않고 description 에 명시한다.
           (JSON Schema 의 anyOf 로도 표현 가능하나, 교육용 가독성을 위해 설명으로 안내한다.)

    [왜 required 만 required 로 넣는가]
        any_of 는 "이 중 하나 이상"이라는 OR 조건이라 JSON Schema required(=AND) 와 다르다.
        validation.py 가 any_of 충족 여부를 별도로 검증하므로, schema 에서는 설명만 제공한다.
    """
    forbidden = set(FORBIDDEN_SQL_TOOLS)
    if tool_name in forbidden or tool_name not in TOOL_CONTRACTS:
        # 금지 Tool 또는 contracts 에 없는 Tool 은 schema 를 만들지 않는다.
        raise ValueError(f"노출할 수 없는 Tool 입니다: {tool_name}")

    contract = TOOL_CONTRACTS[tool_name]
    required = list(contract.get("required_arguments", []) or [])
    any_of = list(contract.get("any_of_required_arguments", []) or [])
    optional = list(contract.get("optional_arguments", []) or [])

    # properties: required + any_of + optional 의 모든 argument 를 포함한다.
    # 같은 이름이 중복될 수 있으므로 dict 로 모아 자연스럽게 1개로 합친다.
    properties = {}
    for arg in required + any_of + optional:
        properties[arg] = {
            "type": _arg_type(arg),
            "description": _arg_description(tool_name, arg, required, any_of),
        }

    # description: Tool 의 purpose 에 any_of 안내를 덧붙인다.
    description = contract.get("purpose", "")
    if any_of:
        description = (
            f"{description} "
            f"(다음 argument 중 하나 이상 필요: {', '.join(any_of)})"
        )

    return {
        "name": tool_name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
            # 계약에 정의되지 않은 argument 는 허용하지 않는다(contracts 가 기준).
            "additionalProperties": False,
        },
    }


def _arg_description(tool_name, arg_name, required, any_of):
    """argument 한 개의 description 문자열을 만든다(required/any_of 여부 표시).

    [동작]
        - required 면 "(필수)" 표시
        - any_of 면 "(다음 중 하나 이상)" 표시
        - 그 외는 "(선택)" 표시
        뒤에 contracts 의 when_to_use 일부를 덧붙여 LLM/사용자가 의미를 파악하게 한다.
    """
    if arg_name in required:
        role = "필수"
    elif arg_name in any_of:
        role = "다음 중 하나 이상"
    else:
        role = "선택"
    # Tool 의 사용 맥락을 짧게 덧붙인다(없으면 빈 문자열).
    when = TOOL_CONTRACTS.get(tool_name, {}).get("when_to_use", "")
    return f"{arg_name} ({role}). 사용 맥락: {when}"


def build_mcp_tool_schemas():
    """노출 대상 전체 Tool 의 MCP schema 리스트를 만든다.

    [반환]
        list[dict] — get_exposed_mcp_tool_names() 의 각 Tool 에 대한
                     build_single_tool_schema() 결과 목록.

    [보장]
        - FORBIDDEN_SQL_TOOLS 는 결과에 포함되지 않는다.
        - 결과의 name 목록은 ALLOWED_TOOLS 와 일치한다(정상 환경 기준).

    [호출 시점]
        mcp_server.list_mcp_tools() 가 그대로 반환한다.
    """
    return [build_single_tool_schema(name) for name in get_exposed_mcp_tool_names()]
