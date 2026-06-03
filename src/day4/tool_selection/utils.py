# -*- coding: utf-8 -*-
"""
Day4 Tool Selection — leaf utility 모듈.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
왜 이 모듈이 필요한가?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

day4 파이프라인은 아래 방향으로 import 합니다.

    runner  →  normalizer / validation / report / output_writer
    report  →  utils          (read_text_file, render_template, plan_tool_names)
    runner  →  utils          (read_text_file, render_template)

만약 utils.py 가 runner 나 report 를 import 하면, Python 이 모듈을 로드하는
시점에 아직 초기화가 끝나지 않은 모듈을 참조하게 되어 순환 import(circular
import) 오류가 발생합니다.

이 모듈은 순환 고리의 '잎(leaf)' 에 해당하므로, 다른 day4 내부 모듈을
import 하지 않고 표준 라이브러리(pathlib)만 사용합니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
runner 와 report 가 공통으로 쓰는 함수만 두는 이유
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

runner.py 와 report.py 는 역할이 다릅니다.
- runner: LLM 호출 → normalizer → validation → repair → finalize 를 실행
- report: 완료된 state/summary 를 사람이 읽는 Markdown 으로 변환

두 모듈이 파일 읽기(read_text_file), 템플릿 치환(render_template),
plan 에서 도구 이름 추출(plan_tool_names) 을 동일하게 필요로 합니다.
중복 없이 공유하되 순환 import 를 발생시키지 않으려면, 어느 쪽도
import 하지 않는 별도 공통 모듈에 두는 것이 최선입니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
요약 (학습자 참고)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- 표준 라이브러리만 사용합니다.
- runner / report 를 import 하지 않습니다.
- 함수 동작(반환 구조/치환 방식)은 기존과 동일합니다.
"""
from pathlib import Path


def read_text_file(path):
    """텍스트(템플릿) 파일을 읽어 문자열로 반환합니다.

    역할:
        runner 가 Mustache 프롬프트 템플릿 파일을 읽을 때,
        report 가 Mustache 보고서 템플릿 파일을 읽을 때 호출됩니다.
        두 호출 경로가 동일한 인코딩 처리 로직을 공유하기 위해 이 모듈에 둡니다.

    입력:
        path (str | Path): 읽을 파일의 경로. 존재하지 않아도 오류를 발생시키지 않습니다.

    반환:
        str  — 파일을 성공적으로 읽으면 전체 텍스트를 반환합니다.
        None — 파일이 존재하지 않거나 두 인코딩 모두 실패하면 None 을 반환합니다.
               호출하는 쪽(runner / report)이 None 을 확인해 fallback 처리를 합니다.

    인코딩 처리 순서:
        1) utf-8-sig: Windows 메모장이나 한글 편집기에서 저장할 때 파일 앞에
           BOM(Byte Order Mark, '﻿')이 붙는 경우가 있습니다. utf-8-sig 는
           BOM 을 자동으로 제거하면서 읽으므로, 불필요한 첫 글자 문제를 방지합니다.
        2) utf-8 : BOM 이 없는 일반 UTF-8 파일에 대응합니다.
        두 인코딩 모두 실패하면 루프를 빠져나와 None 을 반환합니다.

    주의:
        파일 존재 여부를 먼저 확인하여 OS 예외 대신 None 을 반환합니다.
        UnicodeError 만 포착하므로, 권한 오류 등 다른 OS 예외는 그대로 전파됩니다.

    호출 시점:
        - runner 가 LLM 프롬프트용 Mustache 파일을 불러올 때
        - report.render_report_markdown 이 보고서 Mustache 파일을 불러올 때
    """
    p = Path(path)
    # ── 파일 존재 여부를 먼저 확인해 예외 없이 None 을 반환 ──
    if not p.exists():
        return None
    # ── utf-8-sig(BOM 포함) → utf-8(BOM 없음) 순서로 시도 ──
    # Windows 환경에서 저장된 파일은 BOM 이 있는 경우가 많으므로 먼저 시도합니다.
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return p.read_text(encoding=encoding)
        except UnicodeError:
            # 현재 인코딩으로 읽기 실패 시 다음 인코딩을 시도합니다.
            continue
    # 두 인코딩 모두 실패하면 None 을 반환해 호출자가 fallback 을 처리하게 합니다.
    return None


def render_template(template_text, context):
    """{{key}} 형태 placeholder 를 context dict 의 값으로 치환합니다.

    역할:
        Mustache 형식의 템플릿 문자열을 받아, context 딕셔너리에 담긴 값으로
        {{key}} 자리를 순서대로 문자열 치환하여 완성된 텍스트를 반환합니다.

    입력:
        template_text (str): {{key}} 형태의 placeholder 가 포함된 템플릿 문자열.
        context (dict):      key → value 형태의 치환 데이터.
                             value 는 str 로 변환(str(value))되어 삽입됩니다.

    반환:
        str — 모든 {{key}} 가 대응하는 value 로 치환된 결과 문자열.
              context 에 없는 key 에 해당하는 placeholder 는 그대로 남습니다.

    왜 외부 패키지(pystache / chevron 등)를 쓰지 않는가:
        utils.py 는 표준 라이브러리만 사용하는 leaf 모듈입니다.
        runner 와 report 양쪽에서 import 하므로, 외부 패키지 설치 여부에 관계없이
        동작을 보장해야 합니다. day4 에서 필요한 치환 패턴은 {{key}} 단순 치환
        수준이므로 str.replace 로 충분합니다.
        (반복 블록·조건 블록 등 Mustache 고급 기능이 필요하면 chevron/pystache 를
        report.py 또는 runner.py 에서 직접 import 하십시오.)

    주의:
        - context 의 key 순서대로 치환하므로, 한 key 의 value 안에 또 다른 {{key}}
          형태가 포함되어 있으면 연쇄 치환이 발생할 수 있습니다.
        - 이 함수는 예외를 발생시키지 않습니다.

    호출 시점:
        - runner 가 LLM 프롬프트 Mustache 템플릿을 완성할 때
        - report.render_report_markdown 이 보고서 Mustache 템플릿을 완성할 때
    """
    rendered = template_text
    # ── context 의 각 key 를 {{key}} 형식으로 감싸서 순서대로 치환 ──
    for key, value in context.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def plan_tool_names(tool_plan):
    """tool_plan dict 의 plan 항목에서 tool_name 목록을 추출합니다.

    역할:
        검증·수리(repair)가 끝난 final_tool_plan 에서 어떤 도구가 선택되었는지
        목록으로 꺼내는 헬퍼입니다.
        report 가 Markdown 표 'Final Tools' 열을 채울 때 호출하며,
        runner 가 validation 요약 로그를 남길 때도 사용됩니다.

    입력:
        tool_plan (dict | any): LLM 또는 normalizer 가 생성한 tool_plan dict.
                                {"plan": [{"tool_name": "...", ...}, ...]} 구조를 기대합니다.
                                dict 가 아니거나 plan 키가 없으면 빈 리스트를 반환합니다.

    반환:
        list[str] — plan 항목 중 tool_name 이 비어 있지 않은 것만 순서대로 담은 목록.
                    유효한 항목이 없거나 구조가 맞지 않으면 빈 리스트([])를 반환합니다.

    왜 report 에서 필요한가:
        report.build_case_results_table 은 state 마다 최종 선택된 도구 이름을
        쉼표로 이어 표 셀에 표시해야 합니다. tool_plan 의 내부 구조 접근 방식을
        report.py 에 직접 넣으면 구조 변경 시 report 도 함께 수정해야 합니다.
        이 함수에 접근 방식을 집중시켜 두면, 구조가 바뀌어도 이 함수만 수정하면
        runner·report 양쪽이 자동으로 반영됩니다.

    주의:
        tool_name 이 None 이거나 빈 문자열('')인 항목은 포함하지 않습니다.
        plan 이 리스트가 아닌 경우(None, dict, str 등)도 빈 리스트로 처리됩니다.

    호출 시점:
        - report.build_case_results_table 에서 각 state 의 final_tool_plan 처리
        - report.build_report_markdown 에서 동일 목적으로 호출
    """
    # tool_plan 자체가 dict 가 아니면 구조가 없으므로 빈 목록 반환
    if not isinstance(tool_plan, dict):
        return []
    items = tool_plan.get("plan")
    # plan 키가 없거나 리스트가 아니면 처리 불가
    if not isinstance(items, list):
        return []
    names = []
    for item in items:
        # 각 항목이 dict 이고 tool_name 이 비어 있지 않을 때만 추가
        if isinstance(item, dict) and item.get("tool_name"):
            names.append(item.get("tool_name"))
    return names
