# -*- coding: utf-8 -*-
"""
Day4 Tool Selection 패키지 초기화 파일
=======================================

이 폴더(src/day4/tool_selection/)는 Tool Selection 파이프라인의 보조 모듈 묶음입니다.

────────────────────────────────────────────────────────────────────────────────
패키지 구조 개요
────────────────────────────────────────────────────────────────────────────────
사용자 질문은 다음 순서로 처리됩니다:

    사용자 질문
        ↓
    [prompt_builder]  LLM 호출용 prompt 문자열 구성 (Mustache 템플릿 렌더링 포함)
        ↓
    [runner]          파이프라인 진입점 — 단, runner는 이 패키지 안이 아닌
                      상위 디렉터리(src/day4/langgraph_tool_selector_v2_runner.py)에 위치
        ↓
    [LLM / fallback]  LLM 정상 응답 또는 rule 기반 fallback plan 생성
        ↓
    [normalizer]      validation 전 구조 보정(누락 필드 채우기, 타입 통일)
        ↓
    [validation]      PASS / WARNING / FAIL 판정 및 issue 목록 산출
        ↓
    [repair]          FAIL/WARNING 항목 자동 수정 시도 (runner 내부 로직)
        ↓
    [finalize]        최종 plan 확정 (runner 내부 로직)
        ↓
    [results]         결과 record / trace record / summary 집계 구성
        ↓
    [report]          Markdown 형식 보고서 문자열 생성
        ↓
    [output_writer]   JSON / JSONL / Markdown 파일로 저장

────────────────────────────────────────────────────────────────────────────────
각 보조 모듈의 역할
────────────────────────────────────────────────────────────────────────────────
contracts      허용 Tool 목록(ALLOWED_TOOLS), Tool Contract 정의(TOOL_CONTRACTS),
               공용 상수(SEVERITY_ORDER, MIN_REASON_LENGTH 등)를 모아 둔 기준표(leaf 모듈).
               다른 day4 모듈에 의존하지 않으므로 최하위 의존 계층에 위치합니다.

fallback       LLM 호출 실패·파싱 실패 시 rule 기반 대체 plan을 생성합니다.
               user_query의 키워드 패턴만 참조하며, 정답(expected_tools 등)은 사용하지
               않습니다. fallback 결과는 runner가 generation_source 필드로 표시합니다.

normalizer     LLM 또는 fallback이 생성한 plan을 validation 단계 이전에 Tool Contract에
               맞게 구조 보정합니다(누락 필드 채우기, arguments 타입 통일 등).
               validation 규칙 자체를 완화하지 않으며, 정답을 참조하지 않습니다.

validation     Tool Plan을 rule 기반으로 검증해 PASS / WARNING / FAIL status와
               issue 목록·issue_counts를 결정합니다. contracts만 import하며
               runner / normalizer / fallback / results / report를 가져오지 않습니다.

prompt_builder LLM Tool Plan 생성(initial) 및 repair용 prompt 문자열을 구성합니다.
               Mustache 템플릿 파일이 있으면 렌더링하고, 없으면 내장 fallback 문자열을
               사용합니다. contracts와 utils(render_template)에만 의존합니다.

results        실행 완료된 state dict에서 결과 record / trace record / summary 집계를
               만드는 관측 가능성(Observability) 계층입니다. 실행 흐름·판정 규칙을
               변경하지 않고 이미 계산된 값을 직렬화·집계합니다.

report         집계된 summary / states를 사람이 읽는 Markdown 보고서로 변환합니다.
               JSON/JSONL 저장과 분리된 출력 계층이며, 실행·판정 로직에 영향을 주지
               않습니다. 렌더링 실패 시 내장 fallback Markdown 생성 함수를 사용합니다.

output_writer  실행 결과를 output_tag별 파일(results.json, validation_result.json,
               report.md, trace.jsonl)로 저장하는 출력 계층입니다. record 생성은
               results 모듈, Markdown 본문 생성은 report 모듈에 위임합니다.

utils          runner와 report가 공통으로 사용하는 소형 leaf 유틸 함수 모음입니다.
               (read_text_file, render_template, plan_tool_names 등)
               표준 라이브러리만 사용하며 runner / report를 import하지 않습니다.

────────────────────────────────────────────────────────────────────────────────
runner를 이 패키지 안에 두지 않는 이유
────────────────────────────────────────────────────────────────────────────────
runner(langgraph_tool_selector_v2_runner.py)는 LangGraph StateGraph를 정의하고
파이프라인 전체를 조율하는 진입점입니다. 진입점은 패키지 내부가 아닌 상위 디렉터리
(src/day4/)에 위치해야 Streamlit 앱·CLI·품질 게이트(quality_gate_runner.py)에서
독립적으로 호출할 수 있습니다.

────────────────────────────────────────────────────────────────────────────────
__init__.py가 실행 로직을 갖지 않는 이유
────────────────────────────────────────────────────────────────────────────────
패키지 초기화 파일에서 무거운 import나 실행 코드를 두면:
  1. 패키지의 어느 한 모듈만 import할 때도 의도치 않은 부작용이 발생합니다.
  2. 순환 import 오류가 발생하기 쉽습니다.
  3. 테스트·학습 목적의 단독 실행이 어려워집니다.
따라서 이 파일은 패키지 식별자 역할과 문서화만 담당하며, 구체적인 심볼은
각 하위 모듈에서 직접 import해 사용합니다.

contracts / fallback / results / report / utils 모듈을 포함합니다.
runner는 src/day4/langgraph_tool_selector_v2_runner.py에 진입점으로 남깁니다.
"""
