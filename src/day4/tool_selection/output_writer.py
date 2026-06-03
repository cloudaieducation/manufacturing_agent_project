# -*- coding: utf-8 -*-
"""
Day4 Tool Selection Output Writer

실행 결과(states/summary)를 output_tag별 파일로 저장하는 출력 계층입니다.
  - results.json / validation_result.json : json.dump
  - report.md                            : render_report_markdown (report 모듈)
  - trace.jsonl                          : build_trace_record를 줄 단위 JSON으로 기록

설계 메모:
- 결과 record/trace record 생성은 results 모듈, Markdown 본문 생성은 report 모듈에 위임합니다.
- runner를 import하지 않습니다(순환 import 방지). 의존 방향: output_writer -> results / report.
- 파일명 규칙·JSON 옵션·trace 저장 방식은 기존 runner와 동일하게 유지합니다.

--------------------------------------------------------------------
[출력 파일 4종의 역할 구분]

1. results.json
   - 각 테스트 케이스에 대한 핵심 평가 결과(selected_tools, is_correct 등)를
     배열 형태로 담는 "기록 파일"입니다.
   - 정확도 집계(summary) 없이 건별 레코드만 포함하므로, 다른 스크립트에서
     개별 케이스를 재처리하거나 추가 분석할 때 입력으로 재사용하기 편합니다.

2. validation_result.json
   - results.json 의 내용에 summary(정확도·집계 통계)를 추가한 "최종 검증 파일"입니다.
   - quality_gate_runner.py 는 이 파일을 읽어 합격/조건부합격/보류를 판정합니다.
   - 두 파일이 별도로 존재하는 이유: 집계가 포함된 파일과 원시 레코드 파일을
     분리해야 파이프라인 각 단계가 필요한 것만 읽을 수 있기 때문입니다.

3. report.md
   - 사람이 읽는 Markdown 형식의 보고서입니다.
   - Mustache 템플릿을 통해 렌더링되며, 표·판정 근거·경고 메시지가 포함됩니다.
   - JSON 파일과 달리 프로그램이 파싱하지 않으므로 레이아웃이 자유롭습니다.

4. trace.jsonl
   - 각 케이스의 그래프 실행 경로(노드 통과 순서, 입출력 스냅샷)를
     한 줄 = 한 케이스 JSON 으로 저장하는 "실행 추적 파일"입니다.
   - JSONL 형식(줄 단위 JSON)을 사용하는 이유: 전체 배열을 메모리에 올리지 않고
     스트리밍으로 한 줄씩 읽거나 grep 으로 특정 케이스를 추출할 수 있기 때문입니다.
     대규모 실험에서 파일 크기가 커져도 파서가 실패하지 않는 장점도 있습니다.
--------------------------------------------------------------------
"""
import json
from datetime import datetime

from day4.tool_selection.results import build_result_record, build_trace_record


def save_outputs(project_root, states, summary, langgraph_mode,
                 input_file="data/tool_selection_test_cases.json", output_tag="all"):
    """결과 JSON 2개, 보고서 1개, trace 1개를 output_tag별 파일명으로 저장합니다.

    output_tag로 파일명을 분리하므로 core / guardrail / action 실행 결과가
    서로 덮어써지지 않습니다.

    매개변수 설명
    ----------
    project_root : pathlib.Path
        프로젝트 루트 경로. outputs/day4/ 하위 디렉터리를 이 경로 기준으로 생성합니다.
    states : list[dict]
        LangGraph 또는 일반 파이프라인이 생성한 케이스별 상태(state) 딕셔너리 목록.
        각 state 에는 selected_tools, expected_tools, is_correct, trace 등이 포함됩니다.
    summary : dict
        전체 케이스에 대한 정확도·집계 통계. validation_result.json 에만 포함됩니다.
    langgraph_mode : bool
        True 이면 LangGraph StateGraph 실행, False 이면 순수 Python 순차 실행.
        메타데이터로 기록되어 결과 재현 시 실행 모드를 식별하는 데 사용됩니다.
    input_file : str
        테스트 케이스 원본 파일의 상대 경로. 결과 파일 메타데이터에 기록됩니다.
    output_tag : str
        파일명에 삽입되는 구분자(예: "core_10", "guardrail_10", "action_5").
        동일 output_dir 에서 여러 케이스 그룹을 실행해도 파일이 겹치지 않도록 합니다.

    반환값
    ------
    tuple[Path, Path, Path, Path]
        (results_path, validation_path, report_path, trace_path) — 저장된 파일 경로 4개.
        호출측(runner)은 이 경로를 화면에 출력하거나 quality_gate_runner 에 전달합니다.

    설계 원칙: 출력 계층은 "어디에 어떤 형식으로 쓸지"만 결정합니다.
    "무엇을 담을지(레코드 구성)"는 results 모듈, "어떻게 보여줄지(보고서 본문)"는
    report 모듈이 각각 담당합니다. 이 분리 덕분에 출력 형식이 바뀌어도
    비즈니스 로직을 건드리지 않고 이 파일만 수정하면 됩니다.
    """
    # outputs/day4/ 디렉터리가 없으면 자동으로 생성합니다.
    # parents=True 는 중간 경로(outputs/)도 함께 만들어 주므로
    # 프로젝트를 처음 실행하는 환경에서도 오류 없이 동작합니다.
    output_dir = project_root / "outputs" / "day4"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------
    # 파일명 접두사 결정
    # output_tag 를 파일명 중간에 삽입하는 이유:
    #   같은 output_dir 에서 core_10 / guardrail_10 / action_5 케이스를
    #   순서에 상관없이 실행해도 각 그룹의 결과가 독립된 파일로 저장됩니다.
    #   태그 없이 고정 파일명을 사용하면 나중에 실행된 결과가
    #   앞서 실행된 결과를 덮어 써 비교가 불가능해집니다.
    # 예시: output_tag="core_10" → "langgraph_tool_selector_v2_core_10_results.json"
    # ----------------------------------------------------------------
    prefix = f"langgraph_tool_selector_v2_{output_tag}_"

    # 4개 출력 파일의 전체 경로를 미리 확정합니다.
    # 이 시점에서 파일은 아직 존재하지 않으며, open/write 시에 생성됩니다.
    results_path = output_dir / f"{prefix}results.json"          # 건별 결과 (집계 미포함)
    validation_path = output_dir / f"{prefix}validation_result.json"  # 건별 결과 + 집계
    report_path = output_dir / f"{prefix}report.md"              # 사람이 읽는 보고서
    trace_path = output_dir / f"{prefix}trace.jsonl"             # 케이스별 실행 추적 로그

    # ----------------------------------------------------------------
    # 공통 데이터 준비
    # build_result_record(s) 는 results 모듈이 정의한 변환 함수입니다.
    # 원시 state 딕셔너리에서 저장에 필요한 필드만 추출하여
    # 직렬화 가능한 레코드(dict)로 반환합니다.
    # ----------------------------------------------------------------
    result_records = [build_result_record(s) for s in states]

    # normalization_mode / fallback_mode 는 states 첫 번째 항목에서 읽습니다.
    # 동일 실행 배치(batch) 안의 모든 케이스는 같은 모드를 공유하므로
    # 인덱스 0 에서 한 번만 읽어도 충분합니다.
    normalization_mode = states[0].get("normalization_mode", "full") if states else "full"
    fallback_mode = states[0].get("fallback_mode", "rule") if states else "rule"

    # ----------------------------------------------------------------
    # [1/4] results.json 저장 — 건별 결과만 포함하는 가벼운 레코드 파일
    #
    # 이 파일에는 summary(집계)가 없습니다.
    # 다른 분석 스크립트가 결과를 재처리할 때 summary 없는 순수 레코드가
    # 더 다루기 편하기 때문입니다.
    # ----------------------------------------------------------------
    results_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "runner_name": "langgraph_tool_selector_v2_runner",
        "langgraph_mode": langgraph_mode,
        "input_file": input_file,
        "output_tag": output_tag,
        "normalization_mode": normalization_mode,
        "fallback_mode": fallback_mode,
        "results": result_records,
    }
    # ensure_ascii=False : 한글 문자를 \uXXXX 이스케이프 없이 그대로 저장합니다.
    # Python 기본값(True)으로 두면 모든 비ASCII 문자가 \uXXXX 로 치환되어
    # 텍스트 에디터나 diff 도구에서 한글을 읽을 수 없게 됩니다.
    with results_path.open("w", encoding="utf-8") as f:
        json.dump(results_payload, f, ensure_ascii=False, indent=2)

    # ----------------------------------------------------------------
    # [2/4] validation_result.json 저장 — 집계 통계(summary)를 포함한 검증 파일
    #
    # quality_gate_runner.py 는 이 파일의 summary 필드를 읽어
    # 합격(PASS) / 조건부합격(CONDITIONAL_PASS) / 보류(HOLD) 를 판정합니다.
    # results.json 과 동일한 result_records 를 공유하므로 데이터 중복이지만,
    # 파일을 분리하면 두 파이프라인 단계가 독립적으로 파일을 교환할 수 있습니다.
    # ----------------------------------------------------------------
    validation_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "runner_name": "langgraph_tool_selector_v2_runner",
        "langgraph_mode": langgraph_mode,
        "input_file": input_file,
        "output_tag": output_tag,
        "normalization_mode": normalization_mode,
        "fallback_mode": fallback_mode,
        "summary": summary,        # results.json 에는 없는 집계 필드
        "results": result_records,
    }
    # ensure_ascii=False 이유: results.json 와 동일 (한글 보존)
    with validation_path.open("w", encoding="utf-8") as f:
        json.dump(validation_payload, f, ensure_ascii=False, indent=2)

    # ----------------------------------------------------------------
    # [3/4] report.md 저장 — 사람이 읽는 Markdown 보고서
    #
    # render_report_markdown 을 지역 import(함수 내부 import)로 호출하는 이유:
    #   report 모듈도 output_writer 의 경로를 알 필요가 있을 수 있어,
    #   모듈 상단에 두면 순환 import 위험이 생깁니다.
    #   함수가 실제로 호출될 때만 import 하므로 안전합니다.
    #
    # 보고서 본문 생성을 report.py 에 위임하는 이유:
    #   Mustache 템플릿 렌더링, 표 레이아웃, 경고 메시지 조건부 삽입 등
    #   표현(presentation) 로직은 저장(persistence) 로직과 무관합니다.
    #   분리하면 보고서 양식을 바꿀 때 output_writer 를 수정하지 않아도 됩니다.
    # ----------------------------------------------------------------
    from day4.tool_selection.report import render_report_markdown
    report_text = render_report_markdown(
        project_root,
        summary,
        states,
        langgraph_mode,
        input_file,
        output_tag,
    )
    # Markdown 파일은 BOM 없는 UTF-8 로 저장합니다.
    # write_text 는 str → bytes 변환을 내부에서 처리하므로 json.dump 처럼
    # ensure_ascii 옵션을 별도로 지정할 필요가 없습니다.
    report_path.write_text(report_text, encoding="utf-8")

    # ----------------------------------------------------------------
    # [4/4] trace.jsonl 저장 — 케이스별 그래프 실행 경로 추적 파일
    #
    # JSONL(JSON Lines) 형식을 선택한 이유:
    #   - 한 줄 = 한 케이스이므로 grep, awk, 스트림 파서로 특정 케이스만 추출 가능합니다.
    #   - 전체 파일을 JSON 배열로 파싱하지 않아도 되므로 케이스 수가 많아져도
    #     메모리 사용량이 일정하게 유지됩니다.
    #   - 파일 일부가 손상되어도 나머지 줄은 독립적으로 파싱할 수 있습니다.
    #
    # build_trace_record(state) 는 results 모듈이 제공합니다.
    # 그래프 노드 통과 순서, 각 노드의 입력·출력 스냅샷 등
    # 디버깅에 필요한 정보를 state 에서 추출해 반환합니다.
    # ----------------------------------------------------------------
    with trace_path.open("w", encoding="utf-8") as f:
        for state in states:
            record = build_trace_record(state)
            # ensure_ascii=False : 한글 alarm 메시지, 장비 ID 등을 그대로 저장
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")  # JSONL: 각 레코드는 반드시 개행 문자로 끝나야 합니다

    return results_path, validation_path, report_path, trace_path
