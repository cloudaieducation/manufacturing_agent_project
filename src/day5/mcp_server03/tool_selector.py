# -*- coding: utf-8 -*-
"""
Day5 mcp_server03 - Tool Selector (LLM 기반 Tool Selection)

[이 모듈의 역할]
사용자 자연어 질문을 받아 LLM 으로 Tool Plan 을 '생성'합니다.
이 모듈은 Tool 을 '실행'하지 않습니다. 생성한 Tool Plan 은 반드시
tool_executor 의 normalizer → validation 을 통과한 뒤 PASS 일 때만 실행됩니다.

[Day5 의 기본 Tool Selection 모드 = LLM]
- 기본 흐름: 사용자 질문 → build_selection_prompt → LLM → {"plan": [...]}
- LLM 호출은 프로젝트 공통 seam(src/llm_client.generate_json_response)을 재사용합니다.
- llm_client 를 함수 내부에서 '지연 import' 하여, llm_client import 가 실패해도
  MCP Server 전체 import 가 깨지지 않게 합니다(generation_source="unavailable").

[runner.py 미사용]
Day4 langgraph_tool_selector_v2_runner.py 를 import 하지 않습니다.
평가/회귀용 runner 와 실행용 MCP Server 의 책임을 분리합니다.

[LLM 전용 정책 — rule fallback 없음]
- 교육용 LLM 기본 흐름에서는 rule 기반 fallback Tool Plan 을 만들지 않습니다.
- LLM 실패/사용 불가 시에는 build_llm_error_plan(빈 plan) 으로 구조화된 실패 응답만 반환합니다.
- Text-to-SQL / SQL 관련 Tool 은 어떤 경우에도 생성하지 않습니다.

[보안]
- API Key / endpoint / 환경변수 값은 절대 출력하지 않습니다.
- LLM 응답이 JSON dict 가 아니면 실행 가능한 plan 으로 취급하지 않습니다.

[전체 흐름에서의 위치]
    mcp_server.call_select_tools_for_manufacturing_query / call_execute_query
        ↓
    [tool_selector.select_tool_plan_with_llm]  ← Tool Plan 생성(여기까지가 Selection)
        ↓
    tool_executor.execute_tool_plan            ← 검증 후 PASS 일 때만 Execution
"""
# inspect: llm_client.generate_json_response 의 시그니처를 런타임에 확인해
#          allow_fallback 파라미터 지원 여부를 판별하기 위해 사용한다(구버전 호환).
import inspect

# contracts: 프롬프트에 넣을 허용 Tool 목록/계약과 Tool 선택 기준.
#            tool_selector 는 이 범위 '밖'의 Tool 을 절대 생성하지 않는다.
from day5.mcp_server03.contracts import ALLOWED_TOOLS, TOOL_CONTRACTS


def build_selection_prompt(user_query):
    """LLM 에게 Tool Plan 생성을 요청하는 prompt 문자열을 만든다.

    [입력]
        user_query: 사용자 자연어 질문.
    [반환]
        LLM 에 전달할 prompt 문자열.

    [구성]
        1) 역할/제약 선언(허용 Tool 만, 이름/인자 임의 생성 금지, SQL 금지, 과도조회 금지)
        2) 사용 가능한 Tool 목록(이름 + purpose) — contracts 기준
        3) Tool Contract 요약(required/any_of/optional) — contracts 기준
        4) 사용자 질문
        5) 출력 형식(JSON 하나만, markdown/코드펜스 금지)

    [설계 의도]
        Day4 prompt_builder.py 를 import 하지 않고, contracts 만으로 최소 prompt 를
        구성한다(Day5 자립). Tool 목록/계약을 prompt 에 넣어야 LLM 이 허용 범위 안에서
        올바른 Tool 을 선택하고, 없는 Tool/인자를 만들어내는 환각을 줄일 수 있다.
    """
    # 사용 가능한 Tool 목록(이름 + 한 줄 purpose)
    tool_lines = []
    for name in ALLOWED_TOOLS:
        contract = TOOL_CONTRACTS.get(name, {})
        tool_lines.append(f"- {name}: {contract.get('purpose', '')}")
    available_tools = "\n".join(tool_lines)

    # Tool Contract 요약(required/any_of/optional)
    contract_lines = []
    for name in ALLOWED_TOOLS:
        contract = TOOL_CONTRACTS.get(name, {})
        required = contract.get("required_arguments", []) or []
        any_of = contract.get("any_of_required_arguments", []) or []
        optional = contract.get("optional_arguments", []) or []
        parts = [f"{name}"]
        parts.append(f"  - when_to_use: {contract.get('when_to_use', '')}")
        if required:
            parts.append(f"  - required: {', '.join(required)}")
        if any_of:
            parts.append(f"  - any_of_required (하나 이상): {', '.join(any_of)}")
        if optional:
            parts.append(f"  - optional: {', '.join(optional)}")
        contract_lines.append("\n".join(parts))
    tool_contracts = "\n".join(contract_lines)

    # 역할/제약 + 본문 + 출력 형식
    return (
        "당신은 제조 설비 운영을 지원하는 MCP Tool 선택 에이전트입니다.\n"
        "사용자 질문을 분석해 사용 가능한 MCP Tool 중 필요한 Tool을 순서대로 선택하고,\n"
        "실행 계획(Tool Plan)을 JSON으로 만드세요.\n"
        "- 제공된 MCP Tool 목록에 있는 Tool만 사용하세요.\n"
        "- 목록에 없는 Tool 이름을 만들지 마세요.\n"
        "- arguments key는 Tool Contract에 정의된 이름만 사용하세요.\n"
        "- 필요한 정보가 질문에 없으면 비우거나 null로 두고 추측하지 마세요.\n"
        "- Text-to-SQL, SQL 생성/실행 관련 Tool은 절대 선택하지 마세요.\n"
        "- 개인정보나 과도한 전체 조회 요청에는 빈 plan을 출력하세요.\n\n"
        f"=== 사용 가능한 MCP Tool 목록 ===\n{available_tools}\n\n"
        f"=== Tool Contract (요약) ===\n{tool_contracts}\n\n"
        f"=== 사용자 질문 ===\n{user_query}\n\n"
        "=== 출력 형식 ===\n"
        "아래 JSON 형식 하나만 출력하세요. markdown, 코드펜스, 주석은 출력하지 마세요.\n"
        '{"plan": [{"step": 1, "tool_name": "", "arguments": {}, '
        '"condition": "always", "reason": ""}]}\n'
        '처리 가능한 MCP Tool이 없으면 {"plan": []} 를 출력하세요.\n'
    )


def call_llm_json(prompt):
    """프로젝트 공통 llm_client.generate_json_response 를 재사용해 JSON dict 를 받는다.

    [반환] (result_dict_or_None, source)
        source:
          "llm"         : LLM 이 JSON dict 를 정상 반환
          "llm_error"   : 호출은 됐으나 파싱 실패 / llm_error_code 포함 / 비정상 반환
          "unavailable" : llm_client 자체를 import 할 수 없는 환경

    [지연 import 이유]
        llm_client import 를 모듈 상단이 아니라 함수 내부에서 시도한다.
        → API Key 미설정/모듈 부재 환경에서도 tool_selector import 자체는 성공하고,
          호출 시점에만 "unavailable" 로 안전하게 분기한다.

    [allow_fallback=False 사용 이유]
        순수 LLM 결과를 구분하기 위해, generate_json_response 에 allow_fallback
        파라미터가 있으면 False 로 호출한다(구버전 호환을 위해 inspect 로 확인).
        실패 시 mock 으로 자동 대체되지 않아, 우리가 직접 fallback/strict 를 결정할 수 있다.

    [보안]
        예외 메시지, API Key, endpoint 등을 출력하지 않는다(조용히 source 만 반환).
    """
    try:
        from llm_client import generate_json_response
    except Exception:
        # llm_client 를 못 불러와도 import 가 깨지지 않도록 안전하게 처리
        return None, "unavailable"

    try:
        signature = inspect.signature(generate_json_response)
        if "allow_fallback" in signature.parameters:
            result = generate_json_response(prompt, allow_fallback=False)
        else:
            result = generate_json_response(prompt)
    except Exception:
        # 호출 중 예외도 조용히 처리(민감정보 노출 방지)
        return None, "llm_error"

    if not isinstance(result, dict):
        return None, "llm_error"
    if result.get("llm_error_code"):
        # llm_client 가 파싱/호출 실패를 dict 로 알려준 경우
        return result, "llm_error"
    return result, "llm"


def build_llm_error_plan(error_code, message=""):
    """strict fallback mode 전용 LLM 실패 plan(빈 plan)을 만든다.

    [반환]
        {"llm_error_code": <코드>, "llm_error_message": <안전한 짧은 설명>, "plan": []}

    [용도]
        LLM 실패 시, rule fallback 을 쓰지 않고
        실패 상태를 plan 형태(plan=[])로 남긴다. 이후 validation 이 llm_error_code 를
        감지해 json_parse_error(FAIL)로 처리하므로 실행되지 않는다.

    [보안]
        message 에는 짧고 안전한 설명만 넣는다(예외 전문/키/endpoint 금지).
    """
    safe_code = error_code or "unknown_llm_error"
    safe_message = message or "LLM 실패, strict mode 로 rule fallback 미사용"
    return {
        "llm_error_code": safe_code,
        "llm_error_message": safe_message,
        "plan": [],
    }


def select_tool_plan_with_llm(user_query):
    """LLM 으로 Tool Plan 을 생성한다(Selection 단계의 진입점).

    교육용 LLM 전용 정책에서는 LLM 실패 시 rule fallback 을 쓰지 않고
    build_llm_error_plan(빈 plan) 으로 통일 처리한다.

    [입력]
        user_query   : 사용자 자연어 질문.
    [반환]
        {
          "tool_plan": {"plan": [...]},
          "generation_source": "llm" | "llm_error" | "unavailable",
          "fallback_used": bool,
          "error_message": str | None
        }

    [분기]
        1) LLM 성공 + {"plan": ...} → generation_source="llm", fallback_used=False
        2) LLM 호출 실패 / plan 키 없음 / 사용 불가 →
           build_llm_error_plan(빈 plan), generation_source=source(llm_error|unavailable),
           fallback_used=False (rule fallback 으로 대체 실행하지 않음)

    [주의]
        LLM 응답이 JSON dict 가 아니면(plan 키 없음 포함) '실행 가능한 plan' 으로 보지 않는다.
        API Key 미설정 환경에서는 unavailable 실패 응답이 정상 결과다.
    """
    prompt = build_selection_prompt(user_query)
    result, source = call_llm_json(prompt)

    # 1) 정상 LLM 응답 (plan 키 존재)
    if source == "llm" and isinstance(result, dict) and "plan" in result:
        return {
            "tool_plan": result,
            "generation_source": "llm",
            "fallback_used": False,
            "error_message": None,
        }

    # 2) LLM 실패 또는 plan 키 없음 → strict 실패 응답으로 통일한다.
    #    (rule fallback 으로 대체 실행하지 않는다.)
    safe_source = source if source in ("llm_error", "unavailable") else "llm_error"
    error_plan = build_llm_error_plan(
        safe_source, "LLM 실패 또는 비정상 응답(strict mode)"
    )
    return {
        "tool_plan": error_plan,
        "generation_source": safe_source,
        "fallback_used": False,
        "error_message": "LLM 실패 또는 비정상 응답으로 strict mode 처리",
    }
