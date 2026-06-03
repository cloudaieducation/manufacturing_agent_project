"""
Day4 LangGraph Tool Selector v2 Runner - ReAct-style MCP Tool Select 최고 성능 확인용

이 파일은 제조 AI Agent 교육용 예제입니다.

목적:
- LLM이 생성한 v2 Tool Plan을 Rule 기반으로 검증하고, 문제가 있으면
  LLM에게 1회 Repair를 요청한 뒤 재검증하여 최종 Tool Plan 성능을 확인합니다.
- generate -> validate -> repair -> validate -> finalize 흐름을 실습합니다.
- ReAct 흐름과 연결됩니다.
    reason          = Thought
    tool_name       = Action
    arguments       = Action Input
    validation      = Observation
    repair_tool_plan= Observation 기반 수정

흐름:
    START
    -> generate_tool_plan
    -> validate_tool_plan
    -> route_by_validation
         valid   -> finalize
         invalid -> repair_tool_plan -> validate_repaired_plan -> finalize / needs_review
    END

실행:
    uv run python src/day4/langgraph_tool_selector_v2_runner.py
    uv run python src/day4/langgraph_tool_selector_v2_runner.py --limit 10
    uv run python src/day4/langgraph_tool_selector_v2_runner.py --case-id TS-001

주의:
- 실제 사내 데이터나 민감정보를 사용하지 않는 교육용 가상 제조 시나리오입니다.
- API Key, token, password, 전체 환경변수 값은 출력하거나 trace에 남기지 않습니다.
- 기존 파일(llm_tool_selector.py, llm_tool_plan_validator.py)과 기존 결과 파일은
  수정하거나 덮어쓰지 않습니다. 이 Runner는 langgraph_tool_selector_v2_* 산출물만 만듭니다.
- requirements.txt / pyproject.toml / uv.lock은 수정하지 않습니다.
- langgraph가 없으면 동일한 흐름을 일반 함수 pipeline으로 실행합니다.

==========================================================================
전체 Tool Selection 파이프라인에서 이 파일의 위치
==========================================================================
전체 흐름:
  사용자 질문
  → prompt_builder.py     : LLM 호출용 prompt 구성 (Mustache 템플릿 렌더링)
  → [이 파일] runner.py   : generate → validate → repair → finalize 오케스트레이션
  → fallback.py           : LLM 실패 시 rule 기반 plan 생성 (LLM fallback)
  → normalizer.py         : 검증 전 plan 정규화 (필드 보정)
  → validation.py         : Tool Contract 기준 plan 검증
  → results.py            : 케이스별 result record / trace record / summary 집계
  → report.py             : Markdown 보고서 렌더링
  → output_writer.py      : JSON / trace.jsonl / 보고서 파일 저장

이 파일(runner.py)이 담당하는 역할:
  - CLI 인자 해석, 환경 준비, 입력 JSON 읽기
  - LangGraph StateGraph 구성 또는 fallback function pipeline 선택
  - 케이스별 초기 state 생성 → 파이프라인 실행 → 경과 시간 기록
  - 모든 케이스 완료 후 summary 집계 및 산출물 저장 위임

이 파일이 담당하지 않는 역할(의존 방향):
  - prompt 문자열 구성          → prompt_builder.py
  - 정규화 세부 로직             → normalizer.py
  - 검증 규칙 판단               → validation.py
  - result/trace 레코드 포맷     → results.py
  - 보고서 렌더링                → report.py
  - 파일 저장                    → output_writer.py

순환 import 회피 의도:
  - results.py / report.py / output_writer.py 는 runner를 import하지 않습니다.
  - plan_tool_names 같은 leaf utility는 utils.py로 이동해 두 방향 모두에서 재사용합니다.
  - 각 하위 모듈이 runner를 직접 참조하면 순환 의존이 생기므로,
    의존 방향은 항상 runner → 하위 모듈 (단방향)로 유지합니다.
==========================================================================
"""

from pathlib import Path
from datetime import datetime
import argparse
import copy
import importlib.util
import inspect
import json
import re
import sys
import time


# ---------------------------------------------------------------------------
# LangGraph 사용 가능 여부 (없으면 fallback function pipeline)
# ---------------------------------------------------------------------------
# [주의] 여기서 말하는 "LangGraph fallback"은 LLM 실패 시 사용하는
# "LLM fallback(rule 기반 plan)"과 이름이 비슷하나 전혀 다른 개념입니다.
#   - LangGraph fallback  : langgraph 패키지 미설치 → 동일한 Node 함수들을
#                           일반 Python 함수 pipeline으로 순서대로 호출
#   - LLM fallback        : LLM 호출/파싱 실패 → rule 기반 plan으로 대체
# USE_LANGGRAPH 플래그로 실행 경로를 결정하며, 어느 경로든 동일한 함수 로직을 수행합니다.
# ---------------------------------------------------------------------------
try:
    from langgraph.graph import StateGraph, END
    USE_LANGGRAPH = True
except Exception:  # ImportError 외 다른 import 오류도 안전하게 fallback
    StateGraph = None
    END = None
    USE_LANGGRAPH = False

# tqdm은 선택 의존성입니다. 설치되어 있으면 진행률 bar를 쓰고,
# 없으면 일반 print 로그로 fallback합니다. (필수 의존성으로 추가하지 않습니다.)
try:
    from tqdm import tqdm
except Exception:
    tqdm = None


# ---------------------------------------------------------------------------
# Tool 정의 / Tool Contract / severity 등 공용 상수는 day4.tool_selection.contracts
# 모듈(실제 파일: src/day4/tool_selection/contracts.py)로 분리되어 있습니다.
# runner를 직접 실행할 때도(top-level import 시점) day4 패키지가
# 보이도록, import보다 먼저 <root>/src 를 sys.path에 추가합니다.
#   - 이 파일: <root>/src/day4/langgraph_tool_selector_v2_runner.py
#   - parents[1] == <root>/src 이므로 day4 패키지를 찾을 수 있습니다.
#   - runner의 모든 import가 day4.* / llm_client 형태(=src 기준)라 src만 추가합니다.
# ---------------------------------------------------------------------------
_SRC_DIR_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(_SRC_DIR_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR_FOR_IMPORT))

from day4.tool_selection.contracts import (
    ALLOWED_TOOLS,
    FORBIDDEN_SQL_TOOLS,
    ALLOWED_PLAN_ITEM_FIELDS,
    MIN_REASON_LENGTH,
    TOOL_CONTRACTS,
    SEVERITY_ORDER,
)
from day4.tool_selection.utils import (
    read_text_file,
    render_template,
    plan_tool_names,
)


# ===========================================================================
# Tool Plan Normalization
# ===========================================================================
# 정규화 세부 로직은 day4.tool_selection.normalizer 모듈
# (src/day4/tool_selection/normalizer.py)로 분리되어 있습니다.
# runner.py에서는 validate_tool_plan / validate_repaired_plan node에서
# normalize_plan_for_validation()을 호출해 흐름을 보여줍니다.
# ===========================================================================
from day4.tool_selection.normalizer import (
    normalize_plan_for_validation,
    _record_normalization,
)

from day4.tool_selection.prompt_builder import (
    FALLBACK_SYSTEM_PROMPT,
    FALLBACK_PROMPT_TEMPLATE,
    build_available_tools_text,
    build_tool_contracts_text,
    build_generation_prompt,
    build_repair_prompt,
)
from day4.tool_selection.validation import (
    _make_empty_issue_counts,
    validate_plan,
    _validate_arguments,
    _finalize_validation,
)


# FALLBACK_SYSTEM_PROMPT / FALLBACK_PROMPT_TEMPLATE 및 prompt 빌더는
# day4.tool_selection.prompt_builder 모듈로 분리되어 있습니다(상단에서 import).
# ===========================================================================
# 경로 / 환경 준비
# ===========================================================================
def find_project_root():
    """현재 파일 위치(src/day4)를 기준으로 프로젝트 루트를 계산합니다.

    파일 계층:
      <root>/src/day4/langgraph_tool_selector_v2_runner.py
        ↑ parents[0] = src/day4
        ↑ parents[1] = src
        ↑ parents[2] = <root>  ← 이 값을 반환합니다.

    이 경로는 이후 prepare_environment(), load_templates(),
    save_outputs() 등 모든 경로 계산의 기준점으로 사용됩니다.
    """
    return Path(__file__).resolve().parents[2]


def prepare_environment(project_root):
    """src import 경로를 추가하고 .env 파일을 읽습니다.

    수업 중 설명을 돕기 위해 두 가지 작업을 순서대로 수행합니다.

    1. sys.path에 <root>/src 추가:
       - 이미 추가된 경우 중복 삽입을 건너뜁니다.
       - 이를 통해 'from llm_client import ...' 형태의 import가 동작합니다.

    2. .env 로드:
       - .env 파일이 존재하고 python-dotenv가 설치된 경우에만 실행합니다.
       - override=True: 이미 설정된 환경변수도 .env 값으로 덮어씁니다.
       - encoding="utf-8-sig": Windows Notepad에서 저장된 BOM 있는 파일도 처리합니다.
       - LLM_PROVIDER, CLOUD_LLM_PROVIDER 등의 설정이 이 단계에서 적용됩니다.
    """
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    env_path = project_root / ".env"
    if env_path.exists() and importlib.util.find_spec("dotenv") is not None:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, encoding="utf-8-sig", override=True)


def read_json_file(path):
    """JSON 파일을 utf-8-sig / utf-8 순서로 읽습니다.

    Windows 환경에서 BOM이 포함된 파일을 안전하게 처리하기 위해
    utf-8-sig를 먼저 시도하고, 실패하면 utf-8로 재시도합니다.
    두 인코딩 모두 실패하면 ValueError를 발생시킵니다.

    인자:
      path: 읽을 JSON 파일의 절대 또는 상대 경로.

    반환:
      JSON 파싱된 Python 객체 (보통 list[dict] 형태의 케이스 목록).

    예외:
      ValueError: 두 인코딩 모두 실패한 경우.
    """
    last_error = None
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            text = Path(path).read_text(encoding=encoding)
            return json.loads(text)
        except (UnicodeError, json.JSONDecodeError) as error:
            last_error = error
            continue
    raise ValueError(f"JSON 읽기 실패: {path} ({last_error})")


# read_text_file / render_template / plan_tool_names 는 day4.tool_selection.utils 로 이동했습니다(상단에서 import).

# build_available_tools_text / build_tool_contracts_text /
# build_generation_prompt / build_repair_prompt 는
# day4.tool_selection.prompt_builder 모듈로 분리되어 있습니다(상단에서 import).
# ===========================================================================
# LLM 호출 wrapper
# ===========================================================================
def call_llm_json(prompt):
    """
    src/llm_client.generate_json_response()를 재사용해 JSON dict를 받습니다.

    반환: (result_dict, source)
      source: "llm" (실제 LLM/seam 호출 성공) 또는
              "llm_error" (호출은 했으나 파싱/호출 실패)
              "unavailable" (llm_client 자체를 쓸 수 없음)

    수업 중 설명을 돕기 위해 source 값의 의미를 정리합니다:
      - "llm"         : LLM이 JSON 형식 응답을 정상 반환한 경우.
                        이 값은 이후 generate_tool_plan / repair_tool_plan의
                        분기 결정에 사용됩니다.
      - "llm_error"   : llm_client 호출에는 성공했으나 JSON 파싱이 실패하거나
                        llm_error_code가 dict에 포함된 경우.
      - "unavailable" : llm_client 모듈 자체를 import할 수 없는 환경.

    allow_fallback=False 설정 이유:
      순수 LLM 성능(v2 ReAct 프롬프트 효과)을 측정하는 것이 목적이므로,
      mock fallback으로 자동 전환되면 측정 결과가 오염됩니다.
      generate_json_response 시그니처에 allow_fallback 파라미터가 없는
      구버전 llm_client와의 호환성을 위해 inspect로 확인 후 조건부로 전달합니다.
    """
    try:
        from llm_client import generate_json_response
    except Exception:
        return None, "unavailable"

    try:
        signature = inspect.signature(generate_json_response)
        # 순수 LLM 성능 확인이 목적이므로 가능하면 mock fallback을 끈다.
        if "allow_fallback" in signature.parameters:
            result = generate_json_response(prompt, allow_fallback=False)
        else:
            result = generate_json_response(prompt)
    except Exception:
        return None, "llm_error"

    if not isinstance(result, dict):
        return None, "llm_error"

    if result.get("llm_error_code"):
        # llm_client가 호출/파싱 실패를 dict로 알려준 경우
        return result, "llm_error"

    return result, "llm"


# ===========================================================================
# Node: generate_tool_plan
# ===========================================================================
def generate_tool_plan(state, templates):
    """LLM으로 초기 v2 Tool Plan을 생성합니다.

    파이프라인에서 이 node의 위치:
      START → [generate_tool_plan] → validate_tool_plan → ...

    처리 흐름:
      1. state에서 user_query, fallback_mode를 읽습니다.
      2. prompt_builder.build_generation_prompt()로 LLM 호출용 prompt를 구성합니다.
      3. call_llm_json()으로 LLM을 호출하고 (result, source)를 받습니다.
      4. source에 따라 세 가지 분기를 거칩니다:
         (a) source == "llm" and "plan" in result  → 정상 LLM 응답, state에 기록
         (b) source == "llm" but "plan" key 없음   → 비정상 응답, 그대로 기록(파싱 이슈로 판정)
         (c) source != "llm"                        → LLM 실패, fallback_mode에 따라 분기

    [LLM fallback 분기 설명]
    fallback_mode == "strict":
      LLM 실패 시 rule 기반 plan을 사용하지 않고 실패 상태를 plan 형태로 기록합니다.
      이 모드는 LLM 성능만 측정하고 싶을 때 사용합니다.
      → generation_source에 오류 원인(source)이 기록되어 이후 trace 분석에 활용됩니다.

    fallback_mode == "rule" (기본값):
      LLM 실패 시 rule 기반 fallback plan(build_fallback_plan)으로 대체합니다.
      수업 현장에서 API 키 없이도 전체 흐름을 실행할 수 있도록 하는 안전망입니다.
      → fallback_used = True로 기록되어 summary에서 fallback 사용 횟수를 집계합니다.

    주의:
      "LLM fallback(rule 기반 plan 대체)"은 "LangGraph fallback(함수 pipeline으로 대체)"과
      이름이 비슷하나 의미가 다릅니다. LLM fallback은 이 함수 내부에서 발생하는
      plan 생성 단계의 대체 처리이고, LangGraph fallback은 실행 엔진 수준의 대체입니다.

    state 변경:
      initial_tool_plan         : 생성된 plan (LLM 또는 fallback)
      generation_source         : "llm" | "fallback_rule" | 오류코드
      initial_generation_source : generation_source와 동일 (repair 후에도 initial 기록 보존)
      llm_used                  : LLM 호출 성공 여부
      fallback_used             : rule fallback 사용 여부
      initial_fallback_used     : initial 단계에서의 fallback 사용 여부
      error_message             : LLM 실패 시 이유 설명 문자열
    """
    from day4.tool_selection.fallback import build_fallback_plan, build_llm_error_plan

    user_query = state.get("user_query", "")
    fallback_mode = state.get("fallback_mode", "rule")
    prompt = build_generation_prompt(templates, user_query)

    result, source = call_llm_json(prompt)

    # ── 분기 (a): LLM 호출 성공 + plan 키 정상 존재 ──────────────────────────
    if source == "llm" and isinstance(result, dict) and "plan" in result:
        state["initial_tool_plan"] = result
        state["generation_source"] = "llm"
        state["initial_generation_source"] = "llm"
        state["llm_used"] = True
        state["fallback_used"] = False
        state["initial_fallback_used"] = False
        return state

    # ── 분기 (b): LLM 호출 성공이나 plan 키 없음(비정상 응답) ────────────────
    if source == "llm" and isinstance(result, dict):
        # 호출은 성공했지만 plan key가 없는 비정상 응답 → 파싱 이슈로 둔다
        state["initial_tool_plan"] = result
        state["generation_source"] = "llm"
        state["initial_generation_source"] = "llm"
        state["llm_used"] = True
        state["fallback_used"] = False
        state["initial_fallback_used"] = False
        return state

    # ── 분기 (c): LLM 호출/파싱 실패 또는 llm_client 사용 불가 ──────────────
    # LLM 호출/파싱 실패 또는 llm_client 사용 불가
    if fallback_mode == "strict":
        # strict: rule fallback을 사용하지 않고 실패 상태를 plan 형태로 남긴다.
        # strict fallback mode: LLM 성능만 측정하는 경우, rule 대체 없이 실패를 기록합니다.
        # 이 분기는 실행 결과를 구분하기 위한 처리입니다(성공/실패를 명확히 분리).
        safe_source = source or "unknown_llm_error"
        error_plan = build_llm_error_plan(
            safe_source,
            "LLM 실패, strict mode로 rule fallback 미사용",
        )
        state["initial_tool_plan"] = error_plan
        state["generation_source"] = safe_source
        state["initial_generation_source"] = safe_source
        state["llm_used"] = False
        state["fallback_used"] = False
        state["initial_fallback_used"] = False
        state["error_message"] = "LLM 실패, strict mode로 rule fallback 미사용"
        return state

    # rule: 기존 동작 - rule 기반 fallback 사용
    # rule fallback mode: LLM 실패 시 키워드 매칭 기반 rule plan으로 대체합니다.
    # 수업 현장에서 API 키 없이도 파이프라인 흐름 전체를 체험할 수 있도록 합니다.
    fallback_plan = build_fallback_plan(user_query)
    state["initial_tool_plan"] = fallback_plan
    state["generation_source"] = "fallback_rule"
    state["initial_generation_source"] = "fallback_rule"
    state["llm_used"] = False
    state["fallback_used"] = True
    state["initial_fallback_used"] = True
    state["error_message"] = "LLM 실패로 rule fallback 사용"
    return state


# ===========================================================================
# Validation 핵심 로직
# ===========================================================================
# _make_empty_issue_counts / validate_plan / _validate_arguments /
# _finalize_validation 은 day4.tool_selection.validation 모듈로 분리되어
# 있습니다. validate_tool_plan / validate_repaired_plan node에서 validate_plan()을
# 호출해 흐름을 보여줍니다.
# ===========================================================================
# Node: validate_tool_plan / validate_repaired_plan
# ===========================================================================
def validate_tool_plan(state):
    """초기 Tool Plan을 정규화한 뒤 검증합니다.

    파이프라인에서 이 node의 위치:
      generate_tool_plan → [validate_tool_plan] → route_by_validation

    처리 순서:
      1. raw plan을 deep copy하여 state["raw_initial_tool_plan"]에 보존합니다.
         (정규화 전/후를 비교할 수 있도록 원본을 별도 키에 저장)
      2. normalize_plan_for_validation()으로 plan을 정규화합니다.
         정규화 모드(normalization_mode)는 state에서 읽습니다:
           "none"          : LLM 원본 그대로 사용
           "argument-only" : Tool Contract 기준 argument만 보정
           "full"          : argument 보정 + action tool 정책 적용
      3. 정규화된 plan을 state["normalized_initial_tool_plan"]에 기록하고,
         state["initial_tool_plan"]도 정규화 결과로 갱신합니다.
         (이후 finalize/결과 기록이 정규화 결과를 사용하도록 하는 의도)
      4. _record_normalization()으로 적용된 정규화 규칙을 state에 기록합니다.
      5. validate_plan()으로 Tool Contract 기준 검증을 수행합니다.
         검증 결과는 state["initial_validation_result"]에 저장됩니다.
         이 값은 이후 route_by_validation에서 repair 여부 판단에 사용됩니다.
    """
    raw_plan = state.get("initial_tool_plan")
    state["raw_initial_tool_plan"] = copy.deepcopy(raw_plan)

    normalized, rules, applied = normalize_plan_for_validation(
        raw_plan, state.get("user_query", ""),
        normalization_mode=state.get("normalization_mode", "full"),
    )
    state["normalized_initial_tool_plan"] = normalized
    # 기존 필드도 정규화된 plan으로 갱신(finalize/결과 기록이 정규화 결과를 쓰도록).
    state["initial_tool_plan"] = normalized
    _record_normalization(state, rules, applied)

    result = validate_plan(
        normalized,
        state.get("expected_tools"),
        state.get("expected_arguments"),
        state.get("expected_guardrail"),
        state.get("evaluable", True),
    )
    state["initial_validation_result"] = result
    return state


def validate_repaired_plan(state):
    """Repair된 Tool Plan을 정규화한 뒤 재검증합니다.

    파이프라인에서 이 node의 위치:
      repair_tool_plan → [validate_repaired_plan] → finalize

    validate_tool_plan과 동일한 정규화→검증 흐름을 수행하되,
    대상이 state["repaired_tool_plan"]입니다.

    처리 순서:
      1. raw repaired plan을 deep copy하여 state["raw_repaired_tool_plan"]에 보존합니다.
      2. normalize_plan_for_validation()으로 정규화합니다.
      3. 정규화 결과를 state["normalized_repaired_tool_plan"]과
         state["repaired_tool_plan"]에 기록합니다.
      4. _record_normalization()으로 적용 규칙을 state에 추가 기록합니다.
      5. validate_plan()으로 재검증하고 결과를
         state["repaired_validation_result"]에 저장합니다.
         이 값은 이후 finalize에서 initial과 repaired 중 더 나은 쪽을
         선택하는 비교 기준으로 사용됩니다.
    """
    raw_plan = state.get("repaired_tool_plan")
    state["raw_repaired_tool_plan"] = copy.deepcopy(raw_plan)

    normalized, rules, applied = normalize_plan_for_validation(
        raw_plan, state.get("user_query", ""),
        normalization_mode=state.get("normalization_mode", "full"),
    )
    state["normalized_repaired_tool_plan"] = normalized
    state["repaired_tool_plan"] = normalized
    _record_normalization(state, rules, applied)

    result = validate_plan(
        normalized,
        state.get("expected_tools"),
        state.get("expected_arguments"),
        state.get("expected_guardrail"),
        state.get("evaluable", True),
    )
    state["repaired_validation_result"] = result
    return state


# ===========================================================================
# Node: repair_tool_plan
# ===========================================================================
def repair_tool_plan(state, templates):
    """validation issues를 LLM에 전달해 Tool Plan을 1회 수정합니다.

    파이프라인에서 이 node의 위치:
      route_by_validation(→repair) → [repair_tool_plan] → validate_repaired_plan

    이 node는 ReAct 흐름에서 "Observation 기반 수정" 단계에 해당합니다.
    초기 검증에서 발견된 issues를 LLM에게 피드백으로 주어 plan을 재생성합니다.

    처리 순서:
      1. repair_attempted = True로 설정합니다.
         (finalize에서 repair 시도 여부를 구분하는 플래그입니다)
      2. user_query, fallback_mode, original_plan, issues를 state에서 읽습니다.
         issues: initial_validation_result의 issues 목록 → prompt에 포함됩니다.
      3. build_repair_prompt()로 수정 요청 prompt를 구성합니다.
      4. call_llm_json()으로 LLM 호출 후 (result, source)를 받습니다.

    분기 설명:
      source == "llm" 성공:
        - state["repaired_tool_plan"]에 LLM 응답을 저장합니다.
        - repair_generation_source = "llm"
        - repair_fallback_used = False
        - 주의: fallback_used는 여기서 False로 덮어쓰지 않습니다.
          initial 단계에서 이미 True였을 수 있으므로 repair 성공으로 초기화하면
          fallback 사용 이력이 소실됩니다.

      LLM 실패 + strict mode:
        - rule fallback 없이 실패 plan을 state에 기록합니다.
        - fallback_used는 기존 값 유지 (initial 단계 결과를 덮어쓰지 않음).

      LLM 실패 + rule mode:
        - build_fallback_plan()으로 rule 기반 plan을 생성해 저장합니다.
        - fallback_used = True (repair 단계에서의 fallback 사용을 추가 기록).
    """
    from day4.tool_selection.fallback import build_fallback_plan, build_llm_error_plan

    state["repair_attempted"] = True

    user_query = state.get("user_query", "")
    fallback_mode = state.get("fallback_mode", "rule")
    original_plan = state.get("initial_tool_plan", {})
    issues = state.get("initial_validation_result", {}).get("issues", [])

    prompt = build_repair_prompt(templates, user_query, original_plan, issues)
    result, source = call_llm_json(prompt)

    # ── 분기: Repair LLM 호출 성공 ───────────────────────────────────────────
    if source == "llm" and isinstance(result, dict):
        state["repaired_tool_plan"] = result
        state["repair_generation_source"] = "llm"
        state["repair_fallback_used"] = False
        # fallback_used는 수정하지 않는다. initial 단계에서 이미 True였을 수 있으므로
        # repair 성공 경로에서 False로 덮어쓰지 않는다.
        return state

    # Repair LLM 호출 실패
    if fallback_mode == "strict":
        # strict: rule fallback 미사용, 실패 상태를 plan 형태로 남긴다.
        # 이 분기는 실행 결과를 구분하기 위한 처리입니다(LLM 재생성 실패를 명시적으로 기록).
        safe_source = source or "unknown_llm_error"
        error_plan = build_llm_error_plan(
            safe_source,
            "Repair LLM 실패, strict mode로 rule fallback 미사용",
        )
        state["repaired_tool_plan"] = error_plan
        state["repair_generation_source"] = safe_source
        state["repair_fallback_used"] = False
        state["error_message"] = "Repair LLM 실패, strict mode로 rule fallback 미사용"
        # fallback_used는 기존 값 유지 (initial 단계 결과를 덮어쓰지 않음)
        return state

    # rule: 기존 동작 - rule 기반 fallback으로 1회 시도
    # repair 단계에서도 rule fallback을 사용해 전체 흐름이 끊기지 않도록 합니다.
    state["repaired_tool_plan"] = build_fallback_plan(user_query)
    state["repair_generation_source"] = "fallback_rule"
    state["fallback_used"] = True
    state["repair_fallback_used"] = True
    return state


# ===========================================================================
# Node: finalize
# ===========================================================================
def needs_repair(validation_result):
    """validation_result가 FAIL 또는 WARNING이면 repair 대상.

    route_by_validation에서 호출되어 repair node로 분기할지 결정합니다.
    PASS 외의 상태(FAIL / WARNING)는 LLM에게 수정 기회를 1회 줍니다.

    인자:
      validation_result: validate_plan()이 반환한 dict.
                         "status" 키에 "PASS" / "WARNING" / "FAIL" 중 하나가 있습니다.

    반환:
      True  → repair 분기로 라우팅
      False → finalize 분기로 직행
    """
    status = validation_result.get("status")
    return status in ("FAIL", "WARNING")


def finalize(state):
    """최종 Tool Plan / status / issues를 확정합니다.

    파이프라인에서 이 node의 위치:
      route_by_validation(→finalize) → [finalize]  (repair 없는 경우)
      validate_repaired_plan        → [finalize]   (repair 있는 경우)
      → END

    이 node는 initial 검증과 repair 후 재검증 결과를 비교해
    더 나은 쪽을 최종 결과로 채택하는 역할을 합니다.

    처리 로직:
      repair가 시도되지 않은 경우(repair_attempted == False):
        - initial_tool_plan / initial_validation_result를 그대로 최종으로 사용합니다.

      repair가 시도된 경우(repair_attempted == True):
        - SEVERITY_ORDER로 initial과 repaired의 severity 숫자를 비교합니다.
          (낮은 숫자 = 더 좋은 상태 = 선택 대상)
        - repaired_sev <= initial_sev 이면 repaired plan을 최종으로 채택합니다.
        - 그렇지 않으면 initial plan을 유지합니다.
        - 채택된 status가 여전히 "FAIL"이면 "NEEDS_REVIEW"로 격상합니다.
          (repair 후에도 실패 → 사람이 검토해야 함을 명시)

    state 변경 (이 값은 이후 report/trace 생성에 사용됩니다):
      final_tool_plan : 최종 채택된 plan dict
      final_status    : "PASS" | "WARNING" | "NEEDS_REVIEW"
      final_issues    : 최종 채택된 검증 결과의 issues 목록
    """
    initial_result = state.get("initial_validation_result", {})
    repair_attempted = state.get("repair_attempted", False)

    # ── repair 없이 finalize로 직행한 경우 ───────────────────────────────────
    if not repair_attempted:
        state["final_tool_plan"] = state.get("initial_tool_plan", {})
        state["final_status"] = initial_result.get("status", "FAIL")
        state["final_issues"] = initial_result.get("issues", [])
        return state

    # repair 수행된 경우: 재검증 결과로 최종 결정
    repaired_result = state.get("repaired_validation_result", {})
    repaired_status = repaired_result.get("status", "FAIL")

    # SEVERITY_ORDER: {"PASS": 0, "WARNING": 1, "FAIL": 2} 형태의 dict
    # 숫자가 낮을수록 더 좋은(심각도가 낮은) 상태입니다.
    initial_sev = SEVERITY_ORDER.get(initial_result.get("status", "FAIL"), 2)
    repaired_sev = SEVERITY_ORDER.get(repaired_status, 2)

    # 더 나은(severity 낮은) 쪽을 최종으로 채택
    if repaired_sev <= initial_sev:
        # ── repaired plan이 더 낫거나 동등 → repaired를 최종으로 채택 ─────────
        state["final_tool_plan"] = state.get("repaired_tool_plan", {})
        chosen_status = repaired_status
        chosen_issues = repaired_result.get("issues", [])
    else:
        # ── initial plan이 더 나음 → repair 결과를 버리고 initial 유지 ─────────
        state["final_tool_plan"] = state.get("initial_tool_plan", {})
        chosen_status = initial_result.get("status", "FAIL")
        chosen_issues = initial_result.get("issues", [])

    # repair 후에도 FAIL이면 NEEDS_REVIEW
    # 이 분기는 실행 결과를 구분하기 위한 처리입니다: 자동 처리 한계를 표시합니다.
    if chosen_status == "FAIL":
        state["final_status"] = "NEEDS_REVIEW"
    else:
        state["final_status"] = chosen_status
    state["final_issues"] = chosen_issues
    return state


# ===========================================================================
# 흐름 실행: LangGraph 또는 fallback function pipeline
# ===========================================================================
def route_by_validation(state):
    """초기 검증 결과로 분기 라벨을 반환합니다.

    LangGraph의 add_conditional_edges에서 라우팅 함수로 사용됩니다.
    needs_repair()를 호출해 state["initial_validation_result"]의 status를 확인하고,
    "repair" 또는 "finalize" 문자열을 반환합니다.

    반환값은 build_langgraph_app()의 conditional_edges 매핑 dict 키와 일치해야 합니다:
      {"repair": "repair_tool_plan", "finalize": "finalize"}
    """
    if needs_repair(state.get("initial_validation_result", {})):
        return "repair"
    return "finalize"


def run_state_with_functions(state, templates):
    """LangGraph 없이 동일한 Node 순서를 함수 호출로 실행합니다.

    [LangGraph fallback 실행 경로]
    langgraph 패키지가 설치되지 않은 환경에서 USE_LANGGRAPH == False일 때
    run_state()가 이 함수를 호출합니다.

    LangGraph StateGraph와 동일한 node 실행 순서를 일반 Python 함수 호출로 재현합니다:
      generate_tool_plan → validate_tool_plan
      → (조건 분기) route_by_validation == "repair":
            repair_tool_plan → validate_repaired_plan
      → finalize

    주의: 여기서 "LangGraph fallback"은 "LLM fallback(rule plan 대체)"과 다릅니다.
      LangGraph fallback : 실행 엔진을 함수 pipeline으로 대체
      LLM fallback       : plan 생성 단계에서 rule 기반 plan으로 내용을 대체
    """
    state = generate_tool_plan(state, templates)
    state = validate_tool_plan(state)

    if route_by_validation(state) == "repair":
        state = repair_tool_plan(state, templates)
        state = validate_repaired_plan(state)

    state = finalize(state)
    return state


def build_langgraph_app(templates):
    """LangGraph StateGraph를 구성해 컴파일된 app을 반환합니다.

    Node 구성:
      - generate_tool_plan    : LLM 또는 fallback으로 초기 plan 생성
      - validate_tool_plan    : 초기 plan 정규화 + 검증
      - repair_tool_plan      : 검증 실패 시 LLM에게 plan 수정 요청
      - validate_repaired_plan: 수정된 plan 재정규화 + 재검증
      - finalize              : 최종 plan/status 확정

    Edge 구성:
      generate_tool_plan → validate_tool_plan  (고정 edge)
      validate_tool_plan → (조건부):
        "repair"   → repair_tool_plan
        "finalize" → finalize
      repair_tool_plan   → validate_repaired_plan  (고정 edge)
      validate_repaired_plan → finalize            (고정 edge)
      finalize           → END

    templates 인자는 lambda를 통해 generate_tool_plan / repair_tool_plan에
    클로저로 전달됩니다(LangGraph node는 state 단일 인자만 받으므로).

    반환:
      컴파일된 LangGraph CompiledGraph 객체. run_state()에서 invoke()로 실행합니다.
    """
    graph = StateGraph(dict)

    graph.add_node("generate_tool_plan", lambda s: generate_tool_plan(s, templates))
    graph.add_node("validate_tool_plan", validate_tool_plan)
    graph.add_node("repair_tool_plan", lambda s: repair_tool_plan(s, templates))
    graph.add_node("validate_repaired_plan", validate_repaired_plan)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("generate_tool_plan")
    graph.add_edge("generate_tool_plan", "validate_tool_plan")
    graph.add_conditional_edges(
        "validate_tool_plan",
        route_by_validation,
        {"repair": "repair_tool_plan", "finalize": "finalize"},
    )
    graph.add_edge("repair_tool_plan", "validate_repaired_plan")
    graph.add_edge("validate_repaired_plan", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def run_state(state, templates, langgraph_app):
    """단일 케이스 state를 흐름에 태워 실행합니다.

    langgraph_app이 있으면 LangGraph로, 없으면 run_state_with_functions()로 실행합니다.
    두 경로 모두 동일한 함수 로직을 수행하므로 결과는 같습니다.

    인자:
      state          : build_initial_state()로 구성한 케이스별 초기 state dict
      templates      : load_templates()로 읽은 Mustache 템플릿 dict
      langgraph_app  : build_langgraph_app()의 반환값 또는 None

    반환:
      최종 state dict (finalize 완료 후)
      - LangGraph 경로: langgraph_app.invoke()가 반환한 결과를 dict()로 변환
      - 함수 pipeline 경로: run_state_with_functions()의 반환값

    이 값은 이후 build_result_record() / build_trace_record()에 사용됩니다.
    """
    if langgraph_app is not None:
        result = langgraph_app.invoke(state)
        return dict(result)
    return run_state_with_functions(state, templates)


# ===========================================================================
# 케이스 처리
# ===========================================================================
def is_evaluable_case(case):
    """expected_tools/expected_guardrail 기준 정확도 평가가 가능한 케이스인지.

    수업 중 설명을 돕기 위해: 테스트 케이스 중 일부는 expected 값이 없어
    도구 선택 정확도를 수치로 평가하기 어렵습니다. 이 함수는 그 구분을
    build_initial_state()에서 state["evaluable"] 값으로 만드는 판단 기준입니다.

    평가 가능 조건 (OR):
      1. expected_tools가 list로 존재하는 경우 → 정확도 계산 대상
      2. expected_guardrail 값이 있는 경우    → guardrail 차단 여부 평가 대상

    반환:
      True  : 정확도/guardrail 평가 가능
      False : 평가 기준 없음 (출력 품질만 육안 확인)
    """
    has_expected_tools = "expected_tools" in case and isinstance(case.get("expected_tools"), list)
    has_guardrail = bool(case.get("expected_guardrail"))
    return has_expected_tools or has_guardrail


def build_initial_state(case, normalization_mode="full", fallback_mode="rule"):
    """case에서 ToolSelectorV2State 초기값을 만듭니다.

    학습자가 흐름을 따라가기 위해 각 키의 의미를 정리합니다.
    반환하는 dict의 키별 용도:

    입력 데이터 관련:
      case_id           : 케이스 식별자 (예: "TS-001"). 보고서/trace에 기록됩니다.
      user_query        : 사용자 질문 문자열. prompt 구성과 rule fallback에 사용됩니다.
      expected_tools    : 정답 tool 목록(list[str]). 평가 기준. 없으면 빈 list.
      expected_arguments: 정답 argument dict. 평가 기준.
      expected_guardrail: 이 쿼리가 차단되어야 하는지 여부(bool 또는 None).

    실행 환경 관련:
      available_tools   : 이번 실행에서 선택 가능한 tool 이름 목록.
                          ALLOWED_TOOLS 상수를 list로 변환해 사용합니다.
      tool_contracts    : Tool Contract dict. 각 tool의 필수/선택 argument 정의.
      evaluable         : is_evaluable_case()의 반환값. 평가 가능 여부 플래그.

    실행 추적 관련 (파이프라인 진행 중 변경됩니다):
      repair_attempted      : repair node가 실행되었는지 여부. 초기값 False.
      llm_used              : 최종적으로 LLM이 사용되었는지 여부. 초기값 False.
      fallback_used         : rule fallback이 사용되었는지 여부. 초기값 False.
      initial_fallback_used : initial 단계에서 fallback 사용 여부. repair와 구분합니다.
      repair_fallback_used  : repair 단계에서 fallback 사용 여부.
      fallback_mode         : CLI --fallback-mode 값. "rule" | "strict".
      initial_generation_source: 초기 plan 생성 출처("llm"/"fallback_rule"/오류코드).
      error_message         : LLM/fallback 실패 시 이유 문자열. 초기값 None.

    정규화 관련:
      normalization_mode    : CLI --normalization-mode 값. "none"|"argument-only"|"full".
      normalization_applied : 정규화가 실제로 적용되었는지 여부. 초기값 False.
      normalization_rules   : 적용된 정규화 규칙 목록. 초기값 빈 list.
    """
    expected_tools = case.get("expected_tools")
    if not isinstance(expected_tools, list):
        expected_tools = []

    return {
        # ── 입력 데이터 ──────────────────────────────────────────────────────
        "case_id": case.get("case_id", ""),            # 케이스 식별자
        "user_query": case.get("user_query", ""),      # 사용자 질문 원문
        "expected_tools": expected_tools,              # 정답 tool 목록 (평가 기준)
        "expected_arguments": case.get("expected_arguments", {}),  # 정답 argument
        "expected_guardrail": case.get("expected_guardrail"),      # guardrail 차단 기대값
        # ── 실행 환경 ──────────────────────────────────────────────────────
        "available_tools": list(ALLOWED_TOOLS),        # 선택 가능한 tool 이름 목록
        "tool_contracts": TOOL_CONTRACTS,              # tool별 argument 계약 정의
        "evaluable": is_evaluable_case(case),          # 정확도 평가 가능 여부
        # ── 실행 추적 (초기값) ─────────────────────────────────────────────
        "repair_attempted": False,                     # repair 시도 여부
        "llm_used": False,                             # LLM 호출 성공 여부
        "fallback_used": False,                        # rule fallback 사용 여부
        "initial_fallback_used": False,                # initial 단계 fallback 여부
        "repair_fallback_used": False,                 # repair 단계 fallback 여부
        "fallback_mode": fallback_mode,                # "rule" | "strict"
        "initial_generation_source": None,             # 초기 plan 생성 출처
        "error_message": None,                         # 실패 시 이유 설명
        # ── 정규화 설정 (초기값) ───────────────────────────────────────────
        "normalization_mode": normalization_mode,      # "none"|"argument-only"|"full"
        "normalization_applied": False,                # 정규화 적용 여부
        "normalization_rules": [],                     # 적용된 정규화 규칙 목록
    }



# ---------------------------------------------------------------------------
# 결과 record / trace record / summary 집계는 day4.tool_selection.results
# 모듈(실제 파일: src/day4/tool_selection/results.py)로 분리되어 있습니다.
# (compute_repair_success / build_result_record / build_trace_record /
# build_summary). save_outputs / main 에서 import 해 사용합니다.
# plan_tool_names 는 day4.tool_selection.utils의 leaf utility로 이동되어 있으며,
# runner와 report가 모두 utils.py에서 재사용합니다. (tool_selection 하위 모듈이
# runner를 import하지 않도록 의존 방향을 정리한 결과입니다.)
# ---------------------------------------------------------------------------
from day4.tool_selection.results import (
    build_result_record,
    build_trace_record,
    build_summary,
)
# ---------------------------------------------------------------------------
# Markdown 보고서 생성(build_report_markdown / build_summary_markdown / ...,
# render_report_markdown)은 day4.tool_selection.report
# 모듈(실제 파일: src/day4/tool_selection/report.py)로 분리되었습니다.
# render_report_markdown은 save_outputs 안에서 함수 내부 import로 호출합니다.
# ---------------------------------------------------------------------------
# 결과 4종(results.json / validation_result.json / report.md / trace.jsonl) 저장은
# day4.tool_selection.output_writer 모듈(실제 파일: src/day4/tool_selection/output_writer.py)로
# 분리되어 있습니다. main()에서 save_outputs()를 호출해 실행 흐름의 마지막 단계를 보여줍니다.
# ---------------------------------------------------------------------------
from day4.tool_selection.output_writer import save_outputs


def derive_output_tag(input_path):
    """입력 파일명에서 output tag를 자동 추출합니다.

    규칙:
      - tool_selection_test_cases.json            -> all
      - tool_selection_test_cases_core_10.json    -> core_10
      - tool_selection_test_cases_guardrail_10... -> guardrail_10
      - 그 외 파일명                               -> 안전한 slug(stem)

    처리 순서:
      1. Path(input_path).stem 으로 확장자를 제거합니다.
      2. 기본 파일명("tool_selection_test_cases")과 정확히 일치하면 "all"을 반환합니다.
      3. 기본 파일명 + "_" 로 시작하면 그 뒤 부분을 tag 후보로 사용합니다.
      4. 그 외는 stem 전체를 tag 후보로 사용합니다.
      5. 정규식으로 안전한 slug를 만듭니다:
         [^A-Za-z0-9_-]+ 패턴 → 영숫자/밑줄/하이픈 이외의 문자를 밑줄로 치환합니다.
         앞뒤 밑줄 strip 후 빈 문자열이면 "all"을 반환합니다.

    이 값은 출력 파일명에 포함되어 입력 케이스 집합을 구분합니다:
      예) outputs/day4/langgraph_tool_selector_v2_core_10_results.json
    """
    stem = Path(input_path).stem  # 확장자 제거
    base = "tool_selection_test_cases"
    if stem == base:
        return "all"
    prefix = base + "_"
    if stem.startswith(prefix):
        tag = stem[len(prefix):]
    else:
        tag = stem
    # 안전한 slug: 영숫자/밑줄/하이픈만 남기고 나머지는 밑줄로
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", tag).strip("_")
    return slug or "all"


# ===========================================================================
# 템플릿 로드
# ===========================================================================
def load_templates(project_root):
    """system prompt / v2 improved prompt 템플릿을 읽습니다 (없으면 None).

    읽는 파일:
      templates/day4/llm_tool_selection_system_prompt_react.mustache
        → LLM에게 전달할 system prompt 역할의 Mustache 템플릿
      templates/day4/llm_tool_selection_prompt_v2_react_improved.mustache
        → 케이스별 사용자 질문과 tool 목록을 결합한 generation prompt 템플릿

    반환 dict:
      "system_prompt"   : 위 system prompt 파일 내용(str 또는 None)
      "improved_prompt" : 위 generation prompt 파일 내용(str 또는 None)

    read_text_file()은 파일이 없으면 None을 반환합니다.
    None인 경우 prompt_builder.py의 FALLBACK_SYSTEM_PROMPT /
    FALLBACK_PROMPT_TEMPLATE 상수가 대신 사용됩니다.
    """
    templates_dir = project_root / "templates" / "day4"
    return {
        "system_prompt": read_text_file(
            templates_dir / "llm_tool_selection_system_prompt_react.mustache"
        ),
        "improved_prompt": read_text_file(
            templates_dir / "llm_tool_selection_prompt_v2_react_improved.mustache"
        ),
    }


# ===========================================================================
# CLI
# ===========================================================================
def parse_args():
    """CLI 인자를 정의하고 파싱합니다.

    주요 인자:
      --input            : 테스트 케이스 JSON 파일 경로. 상대 경로는 프로젝트 루트 기준.
      --output-tag       : 산출물 파일명에 포함할 태그. 미지정 시 입력 파일명에서 자동 추출.
      --limit            : 앞에서 N개 케이스만 실행. 수업 중 빠른 확인에 유용합니다.
      --case-id          : 특정 case_id만 단독 실행. --limit보다 우선 적용됩니다.
      --normalization-mode: plan 정규화 수준.
                           "none"          → LLM 원본 그대로 검증
                           "argument-only" → argument 필드만 보정
                           "full"          → argument + action tool 정책 모두 적용
      --fallback-mode    : LLM 실패 시 처리 방식.
                           "rule"   → rule 기반 plan으로 자동 대체 (기본값)
                           "strict" → rule 대체 없이 실패 상태 기록
    """
    parser = argparse.ArgumentParser(
        description="Day4 LangGraph Tool Selector v2 Runner"
    )
    parser.add_argument("--input", type=str,
                        default="data/tool_selection_test_cases.json",
                        help="입력 테스트 케이스 JSON 경로 (기본: data/tool_selection_test_cases.json)")
    parser.add_argument("--output-tag", type=str, default=None,
                        help="출력 파일명 tag (미지정 시 입력 파일명에서 자동 추출)")
    parser.add_argument("--limit", type=int, default=None,
                        help="앞에서 N개 케이스만 실행")
    parser.add_argument("--case-id", type=str, default=None,
                        help="특정 case_id만 실행")
    parser.add_argument(
        "--normalization-mode",
        choices=["none", "argument-only", "full"],
        default="full",
        help=(
            "Tool Plan normalization mode. "
            "none=LLM raw plan only, "
            "argument-only=Tool Contract argument normalization only, "
            "full=argument normalization + action tool policy."
        ),
    )
    parser.add_argument(
        "--fallback-mode",
        choices=["rule", "strict"],
        default="rule",
        help=(
            "LLM fallback mode. "
            "rule=use rule-based fallback plan when LLM fails, "
            "strict=do not use rule fallback and keep LLM error result."
        ),
    )
    return parser.parse_args()


def select_cases(cases, limit, case_id):
    """CLI 옵션에 따라 실행할 케이스를 고릅니다.

    선택 우선순위:
      1. case_id가 지정된 경우: 해당 case_id와 일치하는 케이스만 반환합니다.
         일치하는 케이스가 없으면 경고를 출력하고 빈 list를 반환합니다.
      2. limit가 지정된 경우: cases[:limit]로 앞에서 N개만 반환합니다.
      3. 둘 다 없는 경우: 전체 케이스를 반환합니다.

    주의: case_id와 limit가 동시에 지정된 경우 main()에서 경고를 출력하고
    case_id를 우선 적용하므로, 이 함수는 case_id 분기를 먼저 처리합니다.
    """
    if case_id:
        selected = [c for c in cases if c.get("case_id") == case_id]
        if not selected:
            print(f"[경고] case_id '{case_id}'에 해당하는 케이스가 없습니다.")
        return selected
    if limit is not None:
        return cases[:limit]
    return cases


def main():
    """전체 실행 흐름의 진입점입니다.

    코드의 실행 순서를 드러내기 위해 단계별로 정리합니다:

    1단계 - CLI 인자 읽기:
      parse_args()로 --input, --output-tag, --limit, --case-id,
      --normalization-mode, --fallback-mode를 읽습니다.
      --case-id와 --limit 동시 지정 시 case-id를 우선 적용하고 경고를 출력합니다.

    2단계 - 프로젝트 루트/import 환경 준비:
      find_project_root()로 루트 경로를 확정합니다.
      prepare_environment()로 sys.path에 src를 추가하고 .env를 로드합니다.
      입력 경로를 절대 경로로 변환합니다(상대 경로는 루트 기준).

    3단계 - 입력 JSON 읽고 케이스 선택:
      read_json_file()로 테스트 케이스 목록을 읽습니다.
      select_cases()로 --limit / --case-id 옵션을 적용합니다.
      load_templates()로 Mustache 템플릿을 읽습니다.

    4단계 - LangGraph 사용 가능 여부에 따라 app 준비:
      USE_LANGGRAPH == True 이면 build_langgraph_app()으로 StateGraph를 구성합니다.
      LangGraph 구성 실패 시 langgraph_app = None으로 설정하고
      함수 pipeline으로 fallback합니다(LangGraph fallback).
      [주의] 이 "LangGraph fallback"은 LLM 실패 시의 "LLM fallback"과 다릅니다.

    5단계 - 케이스별 generate → validate → repair → finalize 실행:
      각 케이스마다:
        - build_initial_state()로 초기 state 생성
        - run_state()로 전체 파이프라인 실행 (LangGraph 또는 함수 pipeline)
        - 경과 시간(elapsed_seconds)을 state에 기록
        - 실행 결과(state)를 states 목록에 누적

    6단계 - summary 생성 및 결과 파일 저장:
      build_summary(states)로 PASS/WARNING/FAIL/repair 통계를 집계합니다.
      save_outputs()로 결과 4종(results.json, validation_result.json,
      report.md, trace.jsonl)을 outputs/day4/ 에 저장합니다.
      산출물 경로를 콘솔에 출력합니다.
    """
    args = parse_args()

    # ── 1단계: CLI 인자 검증 ─────────────────────────────────────────────────
    if args.case_id and args.limit is not None:
        print("[안내] --case-id와 --limit이 동시에 지정되어 --case-id를 우선 적용합니다.")

    # ── 2단계: 프로젝트 루트 / import 환경 준비 ───────────────────────────────
    project_root = find_project_root()
    prepare_environment(project_root)

    # 입력 경로: 절대 경로면 그대로, 상대 경로면 프로젝트 루트 기준으로 처리합니다.
    raw_input = Path(args.input)
    if raw_input.is_absolute():
        input_path = raw_input
    else:
        input_path = project_root / raw_input

    if not input_path.exists():
        print(f"[오류] 입력 파일을 찾을 수 없습니다: {input_path}")
        print("       경로가 맞는지, 프로젝트 루트에서 실행 중인지 확인해 주세요.")
        return

    # 보고서/결과에 기록할 입력 파일 표시 문자열 (가능하면 루트 기준 상대 경로)
    try:
        input_file_display = str(input_path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        input_file_display = str(input_path)

    # output tag: 지정되지 않으면 입력 파일명에서 자동 추출
    # 이 값은 이후 save_outputs()에서 출력 파일명 생성에 사용됩니다.
    if args.output_tag:
        output_tag = re.sub(r"[^A-Za-z0-9_-]+", "_", args.output_tag).strip("_") or "all"
    else:
        output_tag = derive_output_tag(input_path)

    # ── 3단계: 입력 JSON 읽고 케이스 선택 ───────────────────────────────────
    cases = read_json_file(input_path)
    cases = select_cases(cases, args.limit, args.case_id)

    templates = load_templates(project_root)

    # ── 4단계: LangGraph 사용 가능 여부에 따라 app 준비 ─────────────────────
    # USE_LANGGRAPH: 모듈 상단에서 langgraph import 성공 여부로 결정된 플래그
    # build_langgraph_app() 자체가 실패하는 경우에도 함수 pipeline으로 fallback합니다.
    langgraph_app = None
    if USE_LANGGRAPH:
        try:
            langgraph_app = build_langgraph_app(templates)
            langgraph_mode = "enabled"
        except Exception as error:
            print(f"[안내] LangGraph 구성 실패로 fallback pipeline을 사용합니다: {type(error).__name__}")
            langgraph_app = None
            langgraph_mode = "fallback function pipeline"
    else:
        langgraph_mode = "fallback function pipeline"

    # 진행 로그: tqdm이 있으면 진행률 bar, 없으면 일반 print 로그로 fallback합니다.
    total_cases = len(cases)
    if tqdm is not None:
        case_iter = enumerate(tqdm(cases, desc="Tool selection cases", unit="case"), start=1)
    else:
        case_iter = enumerate(cases, start=1)

    def log_line(message):
        """tqdm 사용 시에도 안전하게 보이도록 출력합니다."""
        if tqdm is not None:
            tqdm.write(message)
        else:
            print(message, flush=True)

    # ── 5단계: 케이스별 generate → validate → repair → finalize 실행 ─────────
    states = []
    for index, case in case_iter:
        case_id = case.get("case_id", "")
        user_query = str(case.get("user_query", "") or "")
        # 콘솔 로그용 쿼리 미리보기: 80자 초과 시 말줄임표 추가
        query_preview = user_query[:80] + ("..." if len(user_query) > 80 else "")

        log_line(f"[{index}/{total_cases}] Running {case_id}: {query_preview}")

        # 케이스 실행 시작 시각 기록 (경과 시간 계산용)
        started_at = time.perf_counter()
        state = build_initial_state(
            case,
            normalization_mode=args.normalization_mode,
            fallback_mode=args.fallback_mode,
        )
        state = run_state(state, templates, langgraph_app)
        elapsed = time.perf_counter() - started_at
        # elapsed_seconds 는 이후 build_result_record / build_trace_record에 사용됩니다.
        state["elapsed_seconds"] = round(elapsed, 3)

        log_line(
            f"[{index}/{total_cases}] Done {case_id} -> "
            f"{state.get('final_status', '')} "
            f"(elapsed: {elapsed:.1f}s, "
            f"llm_used: {state.get('llm_used', False)}, "
            f"fallback_used: {state.get('fallback_used', False)}, "
            f"repair_attempted: {state.get('repair_attempted', False)})"
        )

        states.append(state)

    # ── 6단계: summary 생성 및 결과 파일 저장 ────────────────────────────────
    summary = build_summary(states)
    results_path, validation_path, report_path, trace_path = save_outputs(
        project_root, states, summary, langgraph_mode,
        input_file=input_file_display, output_tag=output_tag,
    )

    print("[Day4 LangGraph Tool Selector v2 Runner]")
    print(f"Input: {input_file_display}")
    print(f"Output tag: {output_tag}")
    print(f"LangGraph mode: {langgraph_mode}")
    print(f"Normalization mode: {args.normalization_mode}")
    print(f"Fallback mode: {args.fallback_mode}")
    print(f"Total cases: {summary['total_cases']}")
    print(f"PASS: {summary['pass_count']}")
    print(f"WARNING: {summary['warning_count']}")
    print(f"FAIL: {summary['fail_count']}")
    print(f"LLM used: {summary['llm_used_count']}")
    print(f"Fallback: {summary['fallback_count']}")
    print(f"Repair attempted: {summary['repair_attempt_count']}")
    print(f"Repair success: {summary['repair_success_count']}")
    print(f"Needs review: {summary['needs_review_count']}")
    print("")
    print("Output:")
    print(f"- {results_path.relative_to(project_root)}")
    print(f"- {validation_path.relative_to(project_root)}")
    print(f"- {report_path.relative_to(project_root)}")
    print(f"- {trace_path.relative_to(project_root)}")


if __name__ == "__main__":
    main()
