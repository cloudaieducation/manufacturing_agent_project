# -*- coding: utf-8 -*-
"""
Day4 Tool Selection Prompt Builder

[이 모듈의 역할]
사용자 질문을 LLM에 넘기기 전에, LLM이 올바른 Tool Plan을 출력할 수 있도록
prompt 문자열을 조립(build)하는 단일 책임 모듈입니다.

이 모듈이 담당하는 것:
  - 초기 Tool Plan 생성을 위한 prompt 구성 (build_generation_prompt)
  - LLM 출력이 validation을 통과하지 못했을 때의 재시도(Repair) prompt 구성
    (build_repair_prompt)
  - 템플릿 파일이 없을 때 사용할 코드 내장 fallback prompt 상수 보유

이 모듈이 담당하지 않는 것:
  - LLM 호출 자체 (runner.generate_tool_plan 이 담당)
  - LLM 응답 파싱·정규화 (normalizer 담당)
  - Tool Plan 검증 (validation 담당)
  - 검증 결과 후처리·최종 확정 (finalize, results 담당)
  - 출력 파일 저장 (output_writer 담당)
  - 리포트 렌더링 (report 담당)

[파이프라인 내 위치]
사용자 질문
  → prompt_builder.build_generation_prompt (이 모듈)
  → runner.generate_tool_plan (LLM 호출)
  → normalizer (JSON 파싱)
  → validation (Tool Plan 검증)
  → (실패 시) prompt_builder.build_repair_prompt (이 모듈, 재진입)
  → runner.generate_tool_plan (재시도)
  → normalizer → finalize → results → report → output_writer

[runner와의 관계]
이 모듈은 runner를 import하지 않습니다. runner가 이 모듈을 import합니다.
순환 import(circular import)를 방지하기 위한 단방향 의존 구조입니다.

의존: contracts(ALLOWED_TOOLS, TOOL_CONTRACTS), utils(render_template).
runner를 import하지 않습니다(순환 import 방지).
"""
import json

from day4.tool_selection.contracts import ALLOWED_TOOLS, TOOL_CONTRACTS
from day4.tool_selection.utils import render_template


# ---------------------------------------------------------------------------
# fallback prompt 상수 (코드 내장)
# ---------------------------------------------------------------------------
# [fallback prompt가 필요한 이유]
# Mustache 템플릿 파일(templates/day4/*.mustache)이 배포 환경에 없거나
# 파일 경로가 잘못 설정된 경우에도 LLM 호출이 완전히 실패하지 않도록,
# 동일한 내용을 Python 소스 코드 안에 상수로 내장해 두는 안전장치입니다.
# 템플릿 파일이 있으면 해당 파일이 우선 사용됩니다.
#
# [system prompt vs user prompt의 역할 차이]
# - FALLBACK_SYSTEM_PROMPT: LLM의 전반적인 역할·제약을 선언합니다.
#   "당신은 MCP Tool 선택 에이전트입니다. 허용된 Tool만 사용하세요." 처럼
#   모든 질문에 걸쳐 공통으로 적용되는 행동 규칙을 담습니다.
# - FALLBACK_PROMPT_TEMPLATE (user prompt 부분): 개별 사용자 질문과 그 질문에
#   필요한 context(Tool 목록, Tool Contract, 사용자 질문 원문, 출력 형식)를
#   주입합니다. 질문마다 달라지는 동적 데이터를 {placeholder} 형태로 포함합니다.

# system prompt: LLM의 역할과 공통 제약 규칙을 정의하는 정적 지시문
FALLBACK_SYSTEM_PROMPT = (
    "당신은 제조 설비 운영을 지원하는 MCP Tool 선택 에이전트입니다.\n"
    "사용자 질문을 분석해 사용 가능한 MCP Tool 중 필요한 Tool을 순서대로 선택하고,\n"
    "실행 계획(Tool Plan)을 JSON으로 만드세요.\n"
    "- 제공된 MCP Tool 목록에 있는 Tool만 사용하세요.\n"
    "- 목록에 없는 Tool 이름을 만들지 마세요.\n"
    "- arguments key는 Tool Contract에 정의된 이름만 사용하세요.\n"
    "- 필요한 정보가 질문에 없으면 비우거나 null로 두고 추측하지 마세요.\n"
    "- Text-to-SQL, SQL 생성/실행 관련 Tool은 절대 선택하지 마세요.\n"
    "- 개인정보나 과도한 전체 조회 요청에는 빈 plan을 출력하세요.\n"
)

# user prompt 템플릿: 동적 context(tool 목록, contract, 사용자 질문)를
# {placeholder}로 받아 완성된 LLM 요청 문자열을 만듭니다.
# .format()으로 치환되므로 중괄호는 {{ }} 로 이스케이프되어 있습니다.
FALLBACK_PROMPT_TEMPLATE = (
    "{system_prompt}\n\n"
    "=== 사용 가능한 MCP Tool 목록 ===\n{available_tools}\n\n"
    "=== Tool Contract (요약) ===\n{tool_contracts}\n\n"
    "=== 사용자 질문 ===\n{user_query}\n\n"
    "=== 출력 형식 ===\n"
    "아래 JSON 형식 하나만 출력하세요. markdown, 코드펜스, 주석은 출력하지 마세요.\n"
    '{{"plan": [{{"step": 1, "tool_name": "", "arguments": {{}}, '
    '"condition": "always", "reason": ""}}]}}\n'
    '처리 가능한 MCP Tool이 없으면 {{"plan": []}} 를 출력하세요.\n'
)


def build_available_tools_text():
    """ALLOWED_TOOLS 목록을 사람이 읽을 수 있는 텍스트로 변환합니다.

    역할:
        LLM prompt에 삽입할 '사용 가능한 MCP Tool 목록' 섹션을 생성합니다.
        각 Tool의 이름과 purpose(용도 한 줄 요약)만 포함합니다.

    반환:
        str: "- <tool_name>: <purpose>" 형태의 줄 목록 문자열.
             줄바꿈으로 구분된 단일 문자열.

    호출 시점:
        build_generation_prompt 및 build_repair_prompt 내부에서 호출됩니다.

    [available_tools 텍스트를 prompt에 넣는 이유]
        LLM은 기본적으로 어떤 Tool이 시스템에 존재하는지 알지 못합니다.
        ALLOWED_TOOLS 목록과 각 Tool의 용도를 명시해 주어야 LLM이
        사용자 질문에 맞는 Tool을 올바르게 선택할 수 있습니다.
        또한 목록에 없는 Tool 이름을 LLM이 임의로 생성(hallucination)하는
        것을 막는 앵커(anchor) 역할도 합니다.
    """
    lines = []
    for name in ALLOWED_TOOLS:
        # TOOL_CONTRACTS에서 해당 Tool의 계약 정보를 가져옵니다.
        # 계약 정보가 없는 Tool은 빈 dict로 처리합니다.
        contract = TOOL_CONTRACTS.get(name, {})
        # purpose: Tool이 어떤 상황에서 왜 쓰이는지를 한 줄로 요약한 문자열
        lines.append(f"- {name}: {contract.get('purpose', '')}")
    return "\n".join(lines)


def build_tool_contracts_text():
    """TOOL_CONTRACTS를 LLM이 이해할 수 있는 요약 텍스트로 변환합니다.

    역할:
        각 Tool의 사용 조건(when_to_use), 필수 인자(required_arguments),
        선택적 필수 인자(any_of_required_arguments), 선택 인자(optional_arguments)를
        구조화된 텍스트로 조합하여 LLM prompt의 'Tool Contract' 섹션을 생성합니다.

    반환:
        str: Tool별 계약 요약이 줄바꿈으로 이어진 단일 문자열.

    호출 시점:
        build_generation_prompt 및 build_repair_prompt 내부에서 호출됩니다.

    [Tool Contract 요약을 prompt에 넣는 이유]
        Tool 이름과 용도만 알려 주면 LLM이 argument 이름을 임의로 추측합니다.
        required_arguments, any_of_required_arguments, optional_arguments를
        명시함으로써:
          1. LLM이 반드시 채워야 할 인자를 빠뜨리지 않게 합니다.
          2. 계약에 없는 인자 이름을 만들어 내는 hallucination을 억제합니다.
          3. when_to_use 조건을 통해 LLM이 질문 맥락과 Tool을 올바르게 매핑하도록 안내합니다.
        이 정보를 prompt에 포함시키는 것이 validation 통과율을 높이는 핵심 장치입니다.
    """
    lines = []
    for name in ALLOWED_TOOLS:
        contract = TOOL_CONTRACTS.get(name, {})
        # 각 인자 카테고리를 안전하게 추출합니다. None이면 빈 리스트로 대체합니다.
        required = contract.get("required_arguments", []) or []
        any_of = contract.get("any_of_required_arguments", []) or []
        optional = contract.get("optional_arguments", []) or []
        # Tool 이름을 첫 줄로, 세부 조건을 들여쓰기 항목으로 구성합니다.
        parts = [f"{name}"]
        parts.append(f"  - when_to_use: {contract.get('when_to_use', '')}")
        if required:
            parts.append(f"  - required: {', '.join(required)}")
        if any_of:
            # any_of_required: 나열된 인자 중 하나 이상은 반드시 제공해야 함을 의미합니다.
            parts.append(f"  - any_of_required (하나 이상): {', '.join(any_of)}")
        if optional:
            parts.append(f"  - optional: {', '.join(optional)}")
        lines.append("\n".join(parts))
    return "\n".join(lines)


def build_generation_prompt(templates, user_query):
    """초기 Tool Plan 생성을 위한 LLM prompt를 구성합니다.

    역할:
        사용자 질문을 처음 LLM에 보낼 때 사용하는 prompt를 만듭니다.
        Mustache 템플릿 파일이 있으면 해당 파일을 우선 사용하고,
        파일이 없으면 코드 내장 FALLBACK_PROMPT_TEMPLATE을 사용합니다.

    입력:
        templates (dict): runner가 미리 로드한 템플릿 문자열 딕셔너리.
            "system_prompt" 키: 시스템 지시 텍스트 (없으면 FALLBACK_SYSTEM_PROMPT 사용).
            "improved_prompt" 키: {{}} 치환 가능한 Mustache 스타일 user prompt 템플릿
                                   (없으면 FALLBACK_PROMPT_TEMPLATE 사용).
        user_query (str): 사용자가 입력한 원본 질문 문자열.

    반환:
        str: LLM에 전달할 완성된 prompt 문자열.

    호출 시점:
        runner.generate_tool_plan 내에서 최초 LLM 호출 직전에 호출됩니다.
        repair 경로(재시도)에서는 build_repair_prompt가 대신 사용됩니다.

    주의:
        이 함수는 LLM을 호출하지 않습니다. prompt 문자열만 반환합니다.
        실제 LLM 호출 및 응답 처리는 runner가 담당합니다.
    """
    # system_prompt: 모든 요청에 공통 적용되는 역할·제약 지시문.
    # templates에 명시적으로 설정된 값이 없으면 코드 내장 fallback을 사용합니다.
    system_prompt = templates.get("system_prompt") or FALLBACK_SYSTEM_PROMPT

    # available_tools: LLM이 선택 가능한 Tool 이름 + 용도 목록
    available_tools = build_available_tools_text()

    # tool_contracts: 각 Tool의 사용 조건과 인자 계약 요약
    tool_contracts = build_tool_contracts_text()

    # Mustache 템플릿 파일이 있으면 render_template으로 {{key}} 치환하여 반환합니다.
    improved_template = templates.get("improved_prompt")
    if improved_template:
        # render_template은 {{system_prompt}}, {{available_tools}} 등의 placeholder를
        # 실제 값으로 치환합니다. 외부 라이브러리에 의존하지 않는 단순 문자열 치환입니다.
        return render_template(
            improved_template,
            {
                "system_prompt": system_prompt,
                "available_tools": available_tools,
                "tool_contracts": tool_contracts,
                "user_query": user_query,
            },
        )

    # 템플릿 파일이 없으면 코드 내부 fallback prompt 사용
    # FALLBACK_PROMPT_TEMPLATE은 Python str.format()으로 치환합니다.
    # (render_template은 {{key}} 기반이지만, fallback은 {key} 기반 .format()을 사용합니다.)
    return FALLBACK_PROMPT_TEMPLATE.format(
        system_prompt=system_prompt,
        available_tools=available_tools,
        tool_contracts=tool_contracts,
        user_query=user_query,
    )


def build_repair_prompt(templates, user_query, original_plan, issues):
    """검증 실패한 Tool Plan을 LLM이 재생성(Repair)하도록 유도하는 prompt를 구성합니다.

    역할:
        1차 LLM 출력이 validation을 통과하지 못한 경우, LLM에게 실패한 Tool Plan과
        구체적인 validation 오류 목록을 제공하여 올바른 Tool Plan을 재생성하게 합니다.
        이 함수는 코드 내장 템플릿만 사용합니다(별도 Mustache 파일 없음).

    입력:
        templates (dict): runner가 로드한 템플릿 딕셔너리.
            "system_prompt" 키: 시스템 지시 텍스트 (없으면 FALLBACK_SYSTEM_PROMPT 사용).
        user_query (str): 사용자가 입력한 원본 질문 문자열 (수정 없이 그대로 전달).
        original_plan (dict): 검증 실패한 LLM의 첫 번째 Tool Plan JSON.
        issues (list[dict]): validator가 발견한 validation 오류 목록.
            각 항목은 issue_type, tool_name, detail 등의 필드를 포함합니다.

    반환:
        str: LLM에 전달할 완성된 Repair prompt 문자열.

    호출 시점:
        runner에서 1차 generate_tool_plan이 validation을 통과하지 못했을 때,
        2차(재시도) LLM 호출 직전에 호출됩니다.

    [repair prompt에 validation issues를 넣는 이유]
        LLM은 자신이 생성한 응답의 오류를 자동으로 알지 못합니다.
        validation 단계에서 발견된 오류(예: 허용되지 않은 tool_name, 누락된 required argument)를
        JSON 형태로 직접 prompt에 포함시켜 LLM에게 명시적으로 알려야 합니다.
        이 방식은 ReAct(Reason + Act) 패턴에서 'Observation' 역할에 해당하며,
        LLM이 오류 원인을 인식하고 수정된 Plan을 생성할 확률을 높입니다.

    주의:
        이 함수는 LLM을 호출하지 않습니다. prompt 문자열만 반환합니다.
        실제 LLM 호출 및 응답 처리는 runner가 담당합니다.
    """
    # 공통 제약 규칙은 generation prompt와 동일한 system_prompt를 사용합니다.
    system_prompt = templates.get("system_prompt") or FALLBACK_SYSTEM_PROMPT

    # repair에도 Tool 목록과 Contract를 포함합니다.
    # LLM이 이전 오류를 수정할 때 허용된 Tool과 인자 정의를 다시 참조할 수 있도록 합니다.
    available_tools = build_available_tools_text()
    tool_contracts = build_tool_contracts_text()

    # validation issues를 JSON 문자열로 직렬화합니다.
    # LLM이 구조화된 오류 목록을 정확히 파악할 수 있도록 JSON 형식을 유지합니다.
    issues_text = json.dumps(issues, ensure_ascii=False, indent=2)

    # 실패한 이전 Tool Plan도 JSON 형식으로 포함합니다.
    # LLM이 어떤 Plan을 어떻게 수정해야 하는지 구체적으로 이해할 수 있게 합니다.
    plan_text = json.dumps(original_plan, ensure_ascii=False, indent=2)

    # repair prompt는 f-string으로 조립합니다.
    # 각 섹션(역할, 규칙, tool 목록, contract, 질문, 이전 plan, 오류 목록, 출력 형식)을
    # 순서대로 배치하여 LLM이 문맥을 단계적으로 이해하도록 설계되어 있습니다.
    #
    # [출력을 JSON 하나로 제한하는 이유]
    #   LLM은 응답에 설명 문장, markdown, 코드 펜스(```json ... ```) 등을 자유롭게 추가할 수 있습니다.
    #   normalizer가 JSON만을 파싱해야 하므로, 여분의 텍스트가 섞이면 파싱이 실패합니다.
    #   "JSON 형식 하나만 출력하세요. markdown, 코드펜스, 주석은 출력하지 마세요."라는
    #   명시적 지시를 통해 파싱 오류 가능성을 최소화합니다.
    #
    # [markdown/code fence를 출력하지 말라고 지시하는 이유]
    #   LLM이 ```json\n{...}\n``` 형태로 응답하면 normalizer가 중괄호 외의 문자를
    #   처리해야 하는 부담이 생깁니다. 순수 JSON 문자열만 오면 json.loads()로 바로
    #   파싱할 수 있으며, 이는 normalizer의 구현을 단순하게 유지하는 데 기여합니다.
    return (
        f"{system_prompt}\n\n"
        "The previous MCP Tool Plan failed validation.\n\n"
        "Use the validation issues as Observation.\n"
        "Repair the Tool Plan.\n\n"
        "Rules:\n"
        "- Use only allowed MCP tools.\n"
        "- Do not invent tools.\n"
        "- Do not invent argument names.\n"
        "- Remove extra tools.\n"
        "- Add missing required tools.\n"
        "- Fill required arguments only when present or clearly implied.\n"
        "- If required information is missing or ambiguous, set it to null and "
        "explain it in condition and reason.\n"
        "- Do not select Text-to-SQL or SQL safety tools.\n"
        "- Return only valid JSON.\n\n"
        f"=== 사용 가능한 MCP Tool 목록 ===\n{available_tools}\n\n"
        f"=== Tool Contract (요약) ===\n{tool_contracts}\n\n"
        f"=== 사용자 질문 ===\n{user_query}\n\n"
        f"=== 이전 Tool Plan ===\n{plan_text}\n\n"
        f"=== Validation Issues (Observation) ===\n{issues_text}\n\n"
        "=== 출력 형식 ===\n"
        "아래 JSON 형식 하나만 출력하세요. markdown, 코드펜스, 주석은 출력하지 마세요.\n"
        '{"plan": [{"step": 1, "tool_name": "", "arguments": {}, '
        '"condition": "always", "reason": ""}]}\n'
        '처리 가능한 MCP Tool이 없으면 {"plan": []} 를 출력하세요.\n'
    )
