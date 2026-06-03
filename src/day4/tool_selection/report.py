# -*- coding: utf-8 -*-
"""
Day4 Tool Selection Report

평가 결과(summary/states)를 사람이 읽는 Markdown 보고서(report.md)로 만드는 출력 계층입니다.
JSON/JSONL 결과 저장과 분리되어 있으며, 실행/판정 로직에는 영향을 주지 않습니다.

설계 메모:
- plan_tool_names / read_text_file / render_template 은 day4.tool_selection.utils의
  leaf 유틸을 재사용합니다(runner를 import하지 않아 의존 방향/순환 import를 방지).
  기존 패턴을 유지해 함수 내부에서 import 합니다.
- report template(mustache)이 없거나 렌더링 실패 시 build_report_markdown으로 fallback 합니다.
- case_id / expected_tools 기반 보정 정보는 표시만 하며, 평가 정답으로 사용하지 않습니다.

[설계 의도] JSON 결과 저장과 Markdown 보고서 생성을 분리한 이유
─────────────────────────────────────────────────────────────
pipeline 흐름: results.py → report.py → output_writer.py

이 파일(report.py)은 사람이 읽는 보고서 텍스트만 담당합니다.
JSON/JSONL 저장은 results.py → output_writer.py 경로가 처리합니다.

분리 이유:
1. 관심사 분리 (SoC): 판정·집계 로직(results.py)과 표현 형식(report.py)이
   서로를 알 필요가 없으므로, 한쪽을 수정해도 다른 쪽에 영향이 없습니다.
2. 테스트 용이성: Markdown 생성 경로만 독립적으로 검증할 수 있습니다.
3. 포맷 교체 가능성: Markdown 대신 HTML/CSV로 바꾸려면 이 파일만 교체하면 됩니다.
4. 출력 실패 격리: 보고서 렌더링이 실패해도 JSON 결과는 이미 저장된 상태이므로
   평가 데이터 손실이 없습니다.
"""


def md_escape(text):
    """Markdown 표 셀용 간단 이스케이프.

    역할:
        Markdown 표(|로 구분되는 GFM 테이블)에서 파이프 문자(|)와 개행(\n)은
        셀 구분자·행 구분자로 해석되어 표 구조가 깨집니다.
        이 함수는 셀 값으로 삽입하기 전에 두 문자를 안전하게 변환합니다.

    Markdown 표에서 escape가 필요한 이유:
        GFM(GitHub Flavored Markdown) 테이블은 | 문자를 열 구분자로,
        줄바꿈을 행 구분자로 사용합니다.
        예: ALM-PIPE|FAULT 를 escape 없이 삽입하면 열이 3개로 분리됩니다.
        따라서 데이터 값 안의 | 는 \\| 로, \\n 은 공백으로 변환해야
        보고서 Markdown이 올바르게 렌더링됩니다.

    입력:
        text: 표 셀에 들어갈 임의 객체. str()로 변환 후 처리합니다.
    반환:
        파이프·개행이 안전하게 치환된 문자열.
    호출 시점:
        각 표 행을 f-string으로 조립하기 직전, 셀 값마다 호출됩니다.
    주의:
        백슬래시 자체는 별도 escape하지 않습니다.
        셀 값이 None이면 str(None) → "None" 으로 처리됩니다.
    """
    return str(text).replace("|", "\\|").replace("\n", " ")


def build_report_markdown(summary, states, langgraph_mode, input_file="", output_tag=""):
    """Markdown 보고서 텍스트를 만듭니다 (template fallback 경로).

    역할:
        Mustache template 없이도 보고서를 생성할 수 있는 순수 Python 경로입니다.
        render_report_markdown()에서 template을 읽지 못하거나
        렌더링 예외가 발생할 때 호출됩니다.

    template이 없을 때 fallback report를 쓰는 이유:
        1. 환경 독립성: template 파일이 배포 환경에 없거나 경로가 달라도
           보고서 생성이 중단되지 않습니다.
        2. 강의 안정성: 수강생 환경에서 template 오류가 발생해도
           평가 결과를 확인할 수 있어야 합니다.
        3. 단계적 개발: template 작성 전에도 파이프라인 전체를 실행해
           결과를 검토할 수 있습니다.
        fallback이 실행되면 "[안내] ..." 메시지가 콘솔에 표시됩니다.

    입력:
        summary: results.py가 집계한 통계 dict (total_cases, pass_count 등).
        states:  케이스별 최종 상태 dict 리스트
                 (case_id, expected_tools, final_tool_plan, final_status 등 포함).
        langgraph_mode: "langgraph" 또는 "sequential" — 실행 모드 표기용.
        input_file:  평가에 사용한 테스트 케이스 파일 경로 (표기용, 기본값 "").
        output_tag:  출력 파일 식별용 태그 문자열 (기본값 "").
    반환:
        보고서 전체 Markdown 문자열 (\\n 구분).
    호출 시점:
        render_report_markdown()이 template 없음 또는 렌더링 실패를 감지했을 때.
    주의:
        이 함수 자체는 파일을 쓰지 않습니다. 저장은 output_writer.py가 담당합니다.
    """
    from day4.tool_selection.utils import plan_tool_names

    lines = []
    lines.append("# Day4 LangGraph Tool Selector v2 Report")
    lines.append("")

    # ── 실행 환경 메타 정보 조립 ──
    # states[0]에서 normalization_mode를 읽어 보고서 상단에 표시합니다.
    # states가 비어 있으면 기본값 "full"을 사용합니다.
    normalization_mode = states[0].get("normalization_mode", "full") if states else "full"

    # normalization_mode별 설명 문구를 dict lookup으로 결정합니다.
    # none: LLM raw plan 그대로 검증 / argument-only: 인자 정규화만 적용 /
    # full: Action Tool Policy까지 포함한 운영형 구조 전체 적용
    mode_desc = {
        "none": "Normalization: disabled. Raw LLM plan is validated directly.",
        "argument-only": "Normalization: Tool Contract argument normalization only. "
                         "Action Tool Policy is disabled.",
        "full": "Normalization: Tool Contract + user_query entity + educational scenario "
                "context + Action Intent Policy.",
    }.get(normalization_mode, "Normalization: full.")

    lines.append(f"- LangGraph mode: {langgraph_mode}")
    lines.append(f"- Input file: {input_file}")
    lines.append(f"- Output tag: {output_tag}")
    lines.append(f"- Normalization mode: {normalization_mode}")
    lines.append(f"- {mode_desc}")
    lines.append("- Normalization: case_id / expected_tools 기반 보정 없음 "
                 "(Tool Contract + user_query entity + 교육용 시나리오 컨텍스트 기준)")
    lines.append("")

    # ── 1. Summary 섹션 조립 ──
    # normalization_applied 플래그가 True인 케이스 수를 집계합니다.
    normalized_count = sum(1 for s in states if s.get("normalization_applied"))
    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"- Total cases: {summary['total_cases']}")
    lines.append(f"- PASS: {summary['pass_count']}")
    lines.append(f"- WARNING: {summary['warning_count']}")
    lines.append(f"- FAIL: {summary['fail_count']}")
    lines.append(f"- JSON parse errors: {summary['json_parse_error_count']}")
    lines.append(f"- Missing tool: {summary['missing_tool_count']}")
    lines.append(f"- Extra tool: {summary['extra_tool_count']}")
    lines.append(f"- Missing argument: {summary['missing_argument_count']}")
    lines.append(f"- Wrong argument name: {summary['wrong_argument_name_count']}")
    lines.append(f"- Missing condition: {summary['missing_condition_count']}")
    lines.append(f"- Weak reason: {summary['weak_reason_count']}")
    lines.append(f"- Tool contract mismatch: {summary['tool_contract_mismatch_count']}")
    lines.append(f"- LLM used: {summary['llm_used_count']}")
    lines.append(f"- Fallback: {summary['fallback_count']}")
    lines.append(f"- Repair attempted: {summary['repair_attempt_count']}")
    lines.append(f"- Repair success: {summary['repair_success_count']}")
    lines.append(f"- Needs review: {summary['needs_review_count']}")
    lines.append(f"- Normalization applied: {normalized_count}/{summary['total_cases']}")
    lines.append(f"- Action policy rules: {summary.get('action_policy_rule_count', 0)}")
    lines.append(f"- Argument normalization rules: {summary.get('argument_normalization_rule_count', 0)}")
    lines.append(f"- Argument removed rules: {summary.get('argument_removed_rule_count', 0)}")
    lines.append(f"- Dedup rules: {summary.get('dedup_rule_count', 0)}")
    lines.append("")

    # ── fallback_count 경고 안내 ──
    # fallback_count가 0보다 크면 보고서에 blockquote 안내를 추가합니다.
    # fallback_count가 높을 때 LLM 성능으로 해석하면 안 되는 이유:
    #   fallback 케이스는 LLM이 계획을 생성하지 못해 rule-based 경로 또는
    #   strict 경로로 대체된 것입니다. 이 케이스들의 PASS/FAIL은 LLM 능력을
    #   반영하지 않으므로, fallback_count를 감안하지 않고 전체 PASS율을
    #   "LLM Tool Selector 정확도"로 읽으면 결과를 과대 해석하게 됩니다.
    #   initial_fallback_count(초기 생성 fallback)와
    #   repair_fallback_count(수정 시도 fallback)를 분리해서 봐야 합니다.
    if summary["fallback_count"] > 0:
        lines.append(
            "> If fallback_count is high, this result includes fallback pipeline "
            "behavior and should not be interpreted as pure LLM Tool Selector performance."
        )
        lines.append("")

    # ── 2. Case Results 표 조립 ──
    # 각 케이스의 핵심 정보를 한 행에 담아 GFM 표로 출력합니다.
    lines.append("## 2. Case Results")
    lines.append("")
    lines.append("| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |")
    lines.append("|---|---|---|---|---|---|---|")
    for state in states:
        # expected_tools: 테스트 케이스에 기록된 기대 툴 목록 (보정 정답이 아닌 참고용)
        expected = ", ".join(state.get("expected_tools", [])) or "-"
        # final_tool_plan: 검증·보정이 완료된 최종 툴 계획에서 이름만 추출합니다.
        final_tools = ", ".join(plan_tool_names(state.get("final_tool_plan", {}))) or "-"
        repair = "yes" if state.get("repair_attempted") else "no"

        # LLM/Fallback 열: fallback이 우선 표시됩니다.
        # fallback_used=True면 LLM 계획이 사용되지 않은 것이므로 명시적으로 구분합니다.
        if state.get("fallback_used"):
            llm_fb = "fallback"
        elif state.get("llm_used"):
            llm_fb = "llm"
        else:
            llm_fb = "-"

        # issue_types: 중복을 제거하고 정렬하여 이슈 유형 목록을 만듭니다.
        issue_types = sorted({i.get("type") for i in (state.get("final_issues") or [])})
        issues_text = ", ".join(issue_types) or "-"

        # md_escape를 적용해 셀 값의 | 와 개행이 표 구조를 깨지 않도록 합니다.
        lines.append(
            f"| {md_escape(state.get('case_id', ''))} | {md_escape(expected)} | "
            f"{md_escape(final_tools)} | {md_escape(state.get('final_status', ''))} | "
            f"{repair} | {llm_fb} | {md_escape(issues_text)} |"
        )
    lines.append("")

    # ── 3. Representative Failures 섹션 조립 ──
    # 이슈 유형별로 대표 케이스를 한 건씩 나열합니다.
    # 이슈가 없는 유형은 "없음" 으로 표시해 섹션이 비어 있지 않음을 명확히 합니다.
    lines.append("## 3. Representative Failures")
    lines.append("")
    for title, itype in [
        ("Missing Tool", "missing_tool"),
        ("Extra Tool", "extra_tool"),
        ("Missing Argument", "missing_argument"),
        ("Wrong Argument Name", "wrong_argument_name"),
        ("Needs Review", None),  # itype=None 이면 final_status로 분기합니다.
    ]:
        lines.append(f"### {title}")
        lines.append("")
        found = False
        for state in states:
            if itype is None:
                # Needs Review: 판정 결과가 NEEDS_REVIEW인 케이스를 수집합니다.
                if state.get("final_status") == "NEEDS_REVIEW":
                    lines.append(f"- {md_escape(state.get('case_id'))}: {md_escape(state.get('user_query'))}")
                    found = True
            else:
                # 해당 이슈 유형의 첫 번째 메시지만 대표로 표시합니다.
                matching = [i for i in (state.get("final_issues") or []) if i.get("type") == itype]
                if matching:
                    msg = matching[0].get("message", "")
                    lines.append(f"- {md_escape(state.get('case_id'))}: {md_escape(msg)}")
                    found = True
        if not found:
            lines.append("- 없음")
        lines.append("")

    # ── Normalization Rules Summary (raw plan 전체는 넣지 않고 요약만) ──
    lines.append("## 4. Normalization Rules Summary")
    lines.append("")
    lines.append("| Case ID | Normalization Applied | Rule IDs |")
    lines.append("|---|---|---|")
    for state in states:
        applied = state.get("normalization_applied", False)
        # normalization_rules 리스트에서 rule_id를 중복 없이 정렬해 표시합니다.
        rule_ids = sorted({r.get("rule_id") for r in (state.get("normalization_rules") or [])})
        rule_text = ", ".join(r for r in rule_ids if r) or "-"
        # rule_text도 md_escape를 통과시켜 ID에 포함될 수 있는 특수문자를 처리합니다.
        lines.append(
            f"| {md_escape(state.get('case_id', ''))} | {applied} | {md_escape(rule_text)} |"
        )
    lines.append("")

    # ── 5. Teaching Notes 섹션 조립 ──
    # Teaching Notes가 교육용 보고서에서 하는 역할:
    #   단순 수치 요약에 그치지 않고, 이 파이프라인의 구조적 의미를
    #   학습 맥락에서 해설합니다.
    #   - "왜 이런 수치가 나왔는가"를 읽는 방법을 안내합니다.
    #   - Ablation 모드·fallback 구분·LLM 단독 성능 해석 오류 등
    #     결과를 잘못 읽을 수 있는 지점을 미리 짚어줍니다.
    #   - ReAct 구조와의 연결, Tool Contract 역할, Repair 루프의 의미 등
    #     아키텍처 개념을 보고서 안에서 복습할 수 있게 합니다.
    lines.append("## 5. Teaching Notes")
    lines.append("")
    lines.append("- LangGraph changes Tool Selection from a single LLM generation task "
                 "into a generate -> validate -> repair -> finalize flow.")
    lines.append("- This structure connects to ReAct: reason is Thought, tool_name is Action, "
                 "arguments are Action Input, and validation result is Observation.")
    lines.append("- Tool Selection quality depends on Tool Contract, prompt structure, "
                 "validation rules, and repair loop.")
    lines.append("- Text-to-SQL is not part of this MCP Tool Selector.")
    lines.append("- Fallback results must be distinguished from actual LLM-generated results.")
    lines.append("")
    lines.append("본 평가는 case_id별 정답 하드코딩이나 expected_tools 참조를 사용하지 않습니다.")
    lines.append("모든 보정은 Tool Contract, 사용자 질문에서 추출한 entity, "
                 "교육용 시나리오 기준 데이터에 기반합니다.")
    lines.append("보고서에는 LLM 원본 plan과 보정 후 plan을 함께 기록해 "
                 "평가 과정을 투명하게 확인할 수 있습니다.")
    lines.append("- 교육용 시나리오 컨텍스트(EQP-EV-03 -> 증착 공정/EDU-LINE-01 등)는 "
                 "테스트 정답이 아니라 DisplayEdu Fab 가상 제조 시나리오 기준 데이터입니다.")
    lines.append("- Ablation 모드는 Raw LLM 성능(none), Tool Contract argument 정규화 효과"
                 "(argument-only), Action Tool Policy까지 포함한 운영형 Agent 구조 효과(full)를 "
                 "분리해서 보기 위한 검증 모드입니다.")
    lines.append("- full 결과가 좋더라도 LLM 단독 성능으로 해석하면 안 됩니다. "
                 "Ablation comparison is safest when --output-tag includes the normalization mode.")
    lines.append("")
    return "\n".join(lines)


# ===========================================================================
# Mustache 기반 Markdown 보고서 (template 분리, fallback = build_report_markdown)
# ===========================================================================
# 이 섹션의 함수들은 보고서를 구성 요소(section)별로 조립합니다.
# build_report_context()가 각 section 문자열을 Mustache context dict에 모아
# render_report_markdown()이 template에 주입합니다.
# template 없음·렌더링 실패 → build_report_markdown() fallback으로 이어집니다.

def _normalization_mode_description(normalization_mode):
    """normalization mode 설명 문구를 반환합니다 (report 상단용).

    역할:
        normalization_mode 값("none" / "argument-only" / "full")을
        보고서 헤더에 표시할 사람이 읽을 수 있는 설명 문구로 변환합니다.
    입력:
        normalization_mode: states[0]["normalization_mode"] 에서 읽은 문자열.
    반환:
        보고서 상단 메타 정보 줄에 삽입할 설명 문자열.
    호출 시점:
        build_report_context()에서 "normalization_description" 키를 채울 때 호출됩니다.
    주의:
        알 수 없는 mode 값은 "full" 설명으로 처리됩니다.
    """
    return {
        "none": "Normalization: disabled. Raw LLM plan is validated directly.",
        "argument-only": "Normalization: Tool Contract argument normalization only. "
                         "Action Tool Policy is disabled.",
        "full": "Normalization: Tool Contract + user_query entity + educational scenario "
                "context + Action Intent Policy.",
    }.get(normalization_mode, "Normalization: full.")


def build_summary_markdown(summary, states):
    """Summary 섹션에 들어갈 Markdown bullet list 문자열을 만듭니다.

    역할:
        summary dict와 states 리스트에서 통계 항목을 읽어
        보고서 "## 1. Summary" 섹션의 bullet list 문자열로 변환합니다.
        template 경로에서는 이 문자열이 Mustache {{summary_markdown}} 자리에 들어갑니다.
    입력:
        summary: results.py가 집계한 통계 dict.
        states:  케이스별 최종 상태 dict 리스트
                 (normalization_applied 플래그를 읽어 정규화 적용 건수를 셉니다).
    반환:
        \\n으로 구분된 Markdown bullet list 문자열.
    호출 시점:
        build_report_context()에서 "summary_markdown" 키를 채울 때 호출됩니다.
    주의:
        fallback_count 관련 항목은 이 함수가 포함합니다.
        fallback_count 경고 blockquote는 build_fallback_note()가 별도로 생성합니다.
    """
    # normalization_applied=True 케이스 수를 states에서 직접 집계합니다.
    normalized_count = sum(1 for s in states if s.get("normalization_applied"))
    lines = [
        f"- Total cases: {summary['total_cases']}",
        f"- PASS: {summary['pass_count']}",
        f"- WARNING: {summary['warning_count']}",
        f"- FAIL: {summary['fail_count']}",
        f"- JSON parse errors: {summary['json_parse_error_count']}",
        f"- Missing tool: {summary['missing_tool_count']}",
        f"- Extra tool: {summary['extra_tool_count']}",
        f"- Missing argument: {summary['missing_argument_count']}",
        f"- Wrong argument name: {summary['wrong_argument_name_count']}",
        f"- Missing condition: {summary['missing_condition_count']}",
        f"- Weak reason: {summary['weak_reason_count']}",
        f"- Tool contract mismatch: {summary['tool_contract_mismatch_count']}",
        f"- LLM used: {summary['llm_used_count']}",
        f"- Fallback: {summary['fallback_count']}",
        f"- Repair attempted: {summary['repair_attempt_count']}",
        f"- Repair success: {summary['repair_success_count']}",
        f"- Needs review: {summary['needs_review_count']}",
        f"- Normalization applied: {normalized_count}/{summary['total_cases']}",
        f"- Action policy rules: {summary.get('action_policy_rule_count', 0)}",
        f"- Argument normalization rules: {summary.get('argument_normalization_rule_count', 0)}",
        f"- Argument removed rules: {summary.get('argument_removed_rule_count', 0)}",
        f"- Dedup rules: {summary.get('dedup_rule_count', 0)}",
        # ── fallback 세분화 항목 ──
        # strict/rule fallback 모드, initial/repair 단계 구분이
        # fallback_count 해석을 위해 필요합니다.
        f"- Fallback mode: {summary.get('fallback_mode', 'rule')}",
        f"- Fallback total cases: {summary.get('fallback_count', 0)}",
        f"- Initial generation fallback: {summary.get('initial_fallback_count', 0)}",
        f"- Repair fallback: {summary.get('repair_fallback_count', 0)}",
        f"- LLM error count: {summary.get('llm_error_count', 0)}",
        f"- LLM unavailable count: {summary.get('llm_unavailable_count', 0)}",
    ]
    return "\n".join(lines)


def build_fallback_note(summary):
    """fallback_count가 높을 때의 안내 문구를 만듭니다 (없으면 빈 문자열).

    역할:
        fallback_count > 0 이면 보고서에 삽입할 blockquote 경고 문구를 반환합니다.
        fallback_count = 0 이면 빈 문자열을 반환해 Mustache 렌더링 시 섹션이 나타나지 않습니다.

    fallback_count가 높을 때 LLM 성능으로 해석하면 안 되는 이유:
        fallback 케이스는 LLM Tool Plan 생성에 실패해 rule-based 경로나
        strict 경로로 대체된 결과입니다.
        이 케이스들의 PASS/FAIL은 LLM의 계획 품질을 나타내지 않으므로,
        전체 PASS율을 단순히 "LLM Selector 정확도"로 읽으면 결과를 왜곡합니다.
        initial_fallback_count와 repair_fallback_count를 분리해야
        어느 단계에서 LLM이 실패했는지 파악할 수 있습니다.

    입력:
        summary: results.py가 집계한 통계 dict ("fallback_count" 키 포함).
    반환:
        blockquote 형식의 안내 문자열, 또는 빈 문자열.
    호출 시점:
        build_report_context()에서 "fallback_note" 키를 채울 때 호출됩니다.
    """
    if summary.get("fallback_count", 0) > 0:
        return (
            "> If fallback_count is high, this result includes fallback pipeline "
            "behavior and should not be interpreted as pure LLM Tool Selector performance."
        )
    return ""


def build_case_results_table(states):
    """Case Results Markdown table 문자열을 만듭니다.

    역할:
        케이스별 최종 상태를 GFM 테이블 형식의 문자열로 변환합니다.
        template 경로에서는 {{case_results_table}} 자리에 삽입됩니다.

    Markdown 표 조립 시 md_escape 적용 이유:
        case_id, 툴 이름, 이슈 메시지 등의 셀 값에 파이프(|)나 개행이
        포함되면 GFM 표 파서가 열을 잘못 분리합니다.
        모든 동적 셀 값은 md_escape()를 통과시켜 안전하게 삽입합니다.

    입력:
        states: 케이스별 최종 상태 dict 리스트.
    반환:
        헤더 행 + 구분선 + 데이터 행으로 구성된 \\n 구분 문자열.
    호출 시점:
        build_report_context()에서 "case_results_table" 키를 채울 때 호출됩니다.
    주의:
        plan_tool_names()는 day4.tool_selection.utils에서 지연 import합니다.
        순환 import 방지를 위해 함수 내부에서 import합니다.
    """
    from day4.tool_selection.utils import plan_tool_names

    # GFM 표 헤더와 구분선을 먼저 추가합니다.
    lines = [
        "| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |",
        "|---|---|---|---|---|---|---|",
    ]
    for state in states:
        # expected_tools: 테스트 케이스의 기대 툴 목록 (보정에 사용되지 않는 참고값)
        expected = ", ".join(state.get("expected_tools", [])) or "-"
        # final_tool_plan에서 툴 이름만 추출합니다.
        final_tools = ", ".join(plan_tool_names(state.get("final_tool_plan", {}))) or "-"
        repair = "yes" if state.get("repair_attempted") else "no"

        # fallback_used가 True이면 LLM이 최종 계획에 기여하지 않은 것을 명시합니다.
        if state.get("fallback_used"):
            llm_fb = "fallback"
        elif state.get("llm_used"):
            llm_fb = "llm"
        else:
            llm_fb = "-"

        # 이슈 유형 집합(중복 제거) → 정렬 → 쉼표 결합
        issue_types = sorted({i.get("type") for i in (state.get("final_issues") or [])})
        issues_text = ", ".join(issue_types) or "-"

        # 각 셀 값에 md_escape를 적용하여 표 구조가 깨지지 않도록 합니다.
        lines.append(
            f"| {md_escape(state.get('case_id', ''))} | {md_escape(expected)} | "
            f"{md_escape(final_tools)} | {md_escape(state.get('final_status', ''))} | "
            f"{repair} | {llm_fb} | {md_escape(issues_text)} |"
        )
    return "\n".join(lines)


def build_representative_failures_markdown(states):
    """Representative Failures 섹션 Markdown 문자열을 만듭니다.

    역할:
        이슈 유형별로 대표 케이스(첫 번째 매칭)를 Markdown bullet로 나열합니다.
        이슈가 없는 유형은 "없음"으로 표시해 섹션이 비지 않도록 합니다.
        template 경로에서는 {{representative_failures_markdown}} 자리에 들어갑니다.

    입력:
        states: 케이스별 최종 상태 dict 리스트.
                final_issues 리스트와 final_status, case_id, user_query를 읽습니다.
    반환:
        이슈 유형별 h3 섹션과 bullet 목록으로 구성된 \\n 구분 문자열.
        trailing 공백은 rstrip()으로 제거합니다.
    호출 시점:
        build_report_context()에서 "representative_failures_markdown" 키를 채울 때.
    주의:
        Needs Review(itype=None)는 final_status == "NEEDS_REVIEW"로 수집합니다.
        나머지 유형은 final_issues 리스트의 type 필드로 매칭합니다.
    """
    lines = []
    for title, itype in [
        ("Missing Tool", "missing_tool"),
        ("Extra Tool", "extra_tool"),
        ("Missing Argument", "missing_argument"),
        ("Wrong Argument Name", "wrong_argument_name"),
        ("Needs Review", None),  # itype=None → final_status 기반 분기
    ]:
        lines.append(f"### {title}")
        lines.append("")
        found = False
        for state in states:
            if itype is None:
                # NEEDS_REVIEW 케이스: 사용자 쿼리를 표시해 검토 맥락을 제공합니다.
                if state.get("final_status") == "NEEDS_REVIEW":
                    lines.append(f"- {md_escape(state.get('case_id'))}: {md_escape(state.get('user_query'))}")
                    found = True
            else:
                # 해당 이슈 유형의 첫 번째 케이스 메시지를 대표로 표시합니다.
                matching = [i for i in (state.get("final_issues") or []) if i.get("type") == itype]
                if matching:
                    msg = matching[0].get("message", "")
                    lines.append(f"- {md_escape(state.get('case_id'))}: {md_escape(msg)}")
                    found = True
        if not found:
            lines.append("- 없음")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_normalization_rules_table(states):
    """Normalization Rules Summary table 문자열을 만듭니다.

    역할:
        각 케이스에 적용된 정규화 규칙 ID를 GFM 테이블로 요약합니다.
        raw plan 전체를 출력하지 않고 rule_id 목록만 표시해
        보고서가 지나치게 길어지지 않도록 합니다.
        template 경로에서는 {{normalization_rules_table}} 자리에 들어갑니다.

    입력:
        states: 케이스별 최종 상태 dict 리스트.
                normalization_applied(bool)와 normalization_rules(list) 키를 읽습니다.
    반환:
        헤더 행 + 구분선 + 케이스별 행으로 구성된 \\n 구분 문자열.
    호출 시점:
        build_report_context()에서 "normalization_rules_table" 키를 채울 때 호출됩니다.
    주의:
        rule_id가 None인 항목은 필터링합니다.
        rule_text도 md_escape를 통과시켜 ID에 포함된 특수문자를 처리합니다.
    """
    # GFM 표 헤더와 구분선을 먼저 추가합니다.
    lines = [
        "| Case ID | Normalization Applied | Rule IDs |",
        "|---|---|---|",
    ]
    for state in states:
        applied = state.get("normalization_applied", False)
        # rule_id 집합(중복 제거) → 정렬 → 쉼표 결합
        rule_ids = sorted({r.get("rule_id") for r in (state.get("normalization_rules") or [])})
        rule_text = ", ".join(r for r in rule_ids if r) or "-"
        # rule_text도 md_escape로 처리해 셀 구조가 깨지지 않게 합니다.
        lines.append(
            f"| {md_escape(state.get('case_id', ''))} | {applied} | {md_escape(rule_text)} |"
        )
    return "\n".join(lines)


def build_teaching_notes_markdown():
    """Teaching Notes 섹션 Markdown 문자열을 만듭니다.

    역할:
        보고서 마지막 섹션으로, 파이프라인의 구조적 의미와 결과 해석 주의사항을
        교육 맥락에서 설명합니다.
        template 경로에서는 {{teaching_notes_markdown}} 자리에 들어갑니다.

    Teaching Notes가 교육용 보고서에서 하는 역할:
        1. 결과 해석 안내: PASS율·fallback 수치를 잘못 읽지 않도록 주의점을 짚어줍니다.
        2. 아키텍처 연결: LangGraph 노드 흐름, ReAct 패턴, Tool Contract의 역할을
           보고서 안에서 재확인합니다.
        3. Ablation 설계 의도: none / argument-only / full 모드가 무엇을 분리 측정하는지 설명합니다.
        4. fallback 해석 경계: fallback count가 LLM 성능 해석에 영향을 미침을 명시합니다.
        5. 평가 공정성 명시: case_id별 정답 하드코딩이 없음을 기록해 평가 투명성을 확보합니다.

    입력: 없음 (고정 문자열 목록).
    반환:
        \\n으로 구분된 Markdown bullet list + 산문 형식의 Teaching Notes 문자열.
    호출 시점:
        build_report_context()에서 "teaching_notes_markdown" 키를 채울 때 호출됩니다.
    주의:
        이 함수의 반환 문자열은 코드 문자열(report 템플릿 텍스트)이므로
        내용을 수정할 때는 해당 문자열 리터럴을 편집해야 합니다.
    """
    lines = [
        # ── LangGraph가 Tool Selection에 가져오는 구조적 변화 ──
        "- LangGraph changes Tool Selection from a single LLM generation task "
        "into a generate -> validate -> repair -> finalize flow.",
        # ── ReAct 패턴과의 연결 ──
        "- This structure connects to ReAct: reason is Thought, tool_name is Action, "
        "arguments are Action Input, and validation result is Observation.",
        # ── Tool Selection 품질 결정 요소 ──
        "- Tool Selection quality depends on Tool Contract, prompt structure, "
        "validation rules, and repair loop.",
        # ── 범위 명시: Text-to-SQL은 이 Tool Selector의 대상이 아닙니다 ──
        "- Text-to-SQL is not part of this MCP Tool Selector.",
        # ── fallback과 LLM 결과 구분 필수 ──
        "- Fallback results must be distinguished from actual LLM-generated results.",
        "",
        # ── 평가 공정성: expected_tools 참조 없음 명시 ──
        "본 평가는 case_id별 정답 하드코딩이나 expected_tools 참조를 사용하지 않습니다.",
        "모든 보정은 Tool Contract, 사용자 질문에서 추출한 entity, "
        "교육용 시나리오 기준 데이터에 기반합니다.",
        # ── LLM 원본 plan vs. 보정 후 plan 비교 투명성 ──
        "보고서에는 LLM 원본 plan과 보정 후 plan을 함께 기록해 "
        "평가 과정을 투명하게 확인할 수 있습니다.",
        # ── 교육용 시나리오 컨텍스트 데이터의 역할 명시 ──
        "- 교육용 시나리오 컨텍스트(EQP-EV-03 -> 증착 공정/EDU-LINE-01 등)는 "
        "테스트 정답이 아니라 DisplayEdu Fab 가상 제조 시나리오 기준 데이터입니다.",
        # ── Ablation 모드 설명 ──
        "- Ablation 모드는 Raw LLM 성능(none), Tool Contract argument 정규화 효과"
        "(argument-only), Action Tool Policy까지 포함한 운영형 Agent 구조 효과(full)를 "
        "분리해서 보기 위한 검증 모드입니다.",
        # ── full 모드 결과를 LLM 단독 성능으로 해석하지 말 것 ──
        "- full 결과가 좋더라도 LLM 단독 성능으로 해석하면 안 됩니다. "
        "Ablation comparison is safest when --output-tag includes the normalization mode.",
        # ── fallback count 세분화 해석 ──
        "- Fallback count는 LLM 성능 해석에 직접 영향을 주므로 initial generation "
        "fallback과 repair fallback을 분리해서 봐야 합니다.",
        # ── LangGraph fallback과 LLM fallback의 차이 ──
        "- LangGraph fallback function pipeline은 LLM fallback이 아니라 실행 경로 "
        "fallback입니다.",
        # ── strict/rule fallback 모드 용도 구분 ──
        "- strict fallback mode는 순수 LLM 평가용이고, rule fallback mode는 강의 "
        "안정성용입니다.",
        # ── llm_used 의미 명시 ──
        "- llm_used는 사용 가능한 LLM Tool Plan이 최종 생성되었는지를 의미하며, "
        "LLM 호출 시도 여부와는 다를 수 있습니다.",
    ]
    return "\n".join(lines)


def build_report_context(summary, states, langgraph_mode, input_file="",
                         output_tag="", report_template=""):
    """report template에 넣을 context dict를 만듭니다 (table/list는 미리 문자열로).

    역할:
        Mustache template 렌더링에 필요한 모든 값을 dict로 조립합니다.
        표·목록 등 복잡한 구조는 미리 Markdown 문자열로 변환해 context에 담습니다.
        이렇게 하면 Mustache template 자체는 {{key}} 치환만 수행하면 되어
        template 로직이 단순해집니다.

    입력:
        summary:         results.py 집계 통계 dict.
        states:          케이스별 최종 상태 dict 리스트.
        langgraph_mode:  실행 모드 문자열 ("langgraph" 또는 "sequential").
        input_file:      테스트 케이스 파일 경로 (표기용).
        output_tag:      출력 식별 태그 (표기용).
        report_template: 사용된 template 파일의 상대 경로 (보고서 메타 표기용).
    반환:
        Mustache context dict.
        키: langgraph_mode, input_file, output_tag, normalization_mode,
            normalization_description, report_template,
            summary_markdown, fallback_note, case_results_table,
            representative_failures_markdown, normalization_rules_table,
            teaching_notes_markdown.
    호출 시점:
        render_report_markdown()에서 template 렌더링 직전에 호출됩니다.
    주의:
        normalization_mode는 states[0]에서 읽습니다. states가 비면 "full"로 기본 처리됩니다.
    """
    # states[0]에서 normalization_mode를 읽어 description 생성에 사용합니다.
    normalization_mode = states[0].get("normalization_mode", "full") if states else "full"
    return {
        "langgraph_mode": langgraph_mode,
        "input_file": input_file,
        "output_tag": output_tag,
        "normalization_mode": normalization_mode,
        # normalization_mode 설명 문구 (보고서 상단 메타 정보용)
        "normalization_description": _normalization_mode_description(normalization_mode),
        "report_template": report_template,
        # ── 각 섹션 문자열을 미리 조립해 context에 담습니다 ──
        # Mustache template은 이 값들을 단순 치환만 합니다.
        "summary_markdown": build_summary_markdown(summary, states),
        "fallback_note": build_fallback_note(summary),
        "case_results_table": build_case_results_table(states),
        "representative_failures_markdown": build_representative_failures_markdown(states),
        "normalization_rules_table": build_normalization_rules_table(states),
        "teaching_notes_markdown": build_teaching_notes_markdown(),
    }


def render_report_markdown(project_root, summary, states, langgraph_mode,
                          input_file="", output_tag=""):
    """report template을 렌더링합니다. 없거나 실패하면 build_report_markdown fallback.

    역할:
        1. Mustache template 파일을 읽습니다.
        2. template이 있으면 build_report_context()로 context를 조립하고
           render_template()으로 렌더링합니다.
        3. template이 없거나 렌더링 중 예외가 발생하면
           build_report_markdown() fallback을 사용합니다.

    template 사용 / fallback 분기:
        ┌─ template 파일 있음 → build_report_context() → render_template()
        │                         └─ 예외 발생 → fallback (print 안내 후)
        └─ template 파일 없음 → build_report_markdown() (즉시 fallback)

    render_report_markdown()에서 예외 상세를 출력하지 않는 이유:
        예외 메시지에는 내부 파일 경로, 환경변수 값, API 키 등
        민감 정보나 내부 구현 세부사항이 포함될 수 있습니다.
        이를 report 파일이나 콘솔에 그대로 출력하면
        보안·개인정보·내부 경로 노출 위험이 생깁니다.
        따라서 예외 상세는 기록하지 않고 "[안내] ..." 메시지만 출력합니다.
        디버깅이 필요할 때는 로깅 프레임워크(logging.debug)를 통해
        별도의 보안 채널에 기록하는 방법을 권장합니다.

    입력:
        project_root:    프로젝트 루트 Path 객체
                         (template 경로 구성과 상대 경로 계산에 사용).
        summary:         results.py 집계 통계 dict.
        states:          케이스별 최종 상태 dict 리스트.
        langgraph_mode:  실행 모드 문자열.
        input_file:      테스트 케이스 파일 경로 (표기용).
        output_tag:      출력 식별 태그 (표기용).
    반환:
        최종 Markdown 보고서 문자열.
    호출 시점:
        output_writer.py 또는 runner에서 보고서 파일을 저장하기 직전에 호출됩니다.
    주의:
        read_text_file / render_template 은 day4.tool_selection.utils에서
        지연 import합니다(순환 import 방지).
    """
    from day4.tool_selection.utils import read_text_file, render_template

    # template 파일 경로를 project_root 기준으로 구성합니다.
    template_path = project_root / "templates" / "day4" / "langgraph_tool_selector_v2_report.mustache"
    template_text = read_text_file(template_path)

    # ── template 없음 → 즉시 fallback ──
    # template 파일을 읽지 못하면(파일 없음 / 읽기 오류) 순수 Python 경로를 사용합니다.
    if not template_text:
        return build_report_markdown(summary, states, langgraph_mode, input_file, output_tag)

    # ── template 상대 경로 계산 (보고서 메타 정보용) ──
    # 절대 경로를 project_root 기준 상대 경로로 변환합니다.
    # project_root 외부에 template이 있으면 ValueError가 발생하므로 기본값으로 처리합니다.
    try:
        rel_template = str(template_path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        rel_template = "templates/day4/langgraph_tool_selector_v2_report.mustache"

    # ── template 렌더링 시도 ──
    try:
        context = build_report_context(
            summary,
            states,
            langgraph_mode,
            input_file,
            output_tag,
            report_template=rel_template,
        )
        return render_template(template_text, context)
    except Exception:
        # 예외 상세(환경변수/키 등)는 report·console에 노출하지 않고 fallback만 안내
        # 민감 정보·내부 경로가 포함될 수 있는 예외 메시지를 출력하지 않습니다.
        # 강의 환경에서는 수강생 화면에 내부 구현 세부사항이 노출되지 않아야 합니다.
        print("[안내] report template 렌더링 실패로 fallback report 사용")
        return build_report_markdown(summary, states, langgraph_mode, input_file, output_tag)
