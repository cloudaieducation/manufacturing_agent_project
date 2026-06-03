# -*- coding: utf-8 -*-
"""
Day4 Guardrail - 교육용 단위 테스트 (TDD)

목적
====
src/day4/guardrail.py 의 핵심 동작을 pytest 로 검증합니다.
운영 코드는 수정하지 않고 import 해서 호출만 하며, 현재 코드의
판정 우선순위를 "있는 그대로" 검증합니다.

검증 대상 함수
=============
  1) apply_guardrail(user_query)   - 단일 요청에 대한 Guardrail 판정
  2) evaluate_cases(cases)         - 케이스 묶음 평가 및 요약 집계
  3) format_list(values)           - 리스트/스칼라를 보고서용 문자열로 변환
  4) save_outputs(project_root, report) - JSON + Markdown 보고서 저장
  5) find_project_root()           - 파일 위치 기준 프로젝트 루트 계산
  6) load_test_cases(project_root) - 테스트 케이스 JSON 로드

설계 원칙
========
- 실제 data/ 파일이나 outputs/ 폴더에 의존하거나 오염시키지 않습니다.
  파일 I/O 가 필요한 테스트는 pytest 의 tmp_path 로 격리합니다.
- 현재 Guardrail 판정 우선순위:
    (1) 근거 없는 단정 표현 → warnings 에 UNSUPPORTED_CONCLUSION_WARNING 기록(차단 아님)
    (2) 민감정보 요청           → SENSITIVE_REQUEST_BLOCKED (최우선 차단)
    (3) 내부 시스템 접근 요청   → INTERNAL_SYSTEM_ACCESS_BLOCKED
    (4) 과도한 전체 조회 요청   → OVER_QUERY_BLOCKED
    (5) warning 만 있으면       → 차단하지 않고 경고만 기록
    (6) 아무 위험 표현 없으면   → 통과
  여러 위험 표현이 동시에 있으면 위 순서가 먼저 적용된 쪽이 최종 판정이 됩니다.
- API Key, DB 비밀번호, 전체 환경변수 값은 출력하지 않습니다.

실행 명령
========
    uv run pytest tests/day4/test_guardrail.py -v
    uv run pytest tests/day4/test_guardrail.py -v --tb=short
"""

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# import 경로 준비
#   이 파일: <root>/tests/day4/test_guardrail.py
#     parents[0] = tests/day4
#     parents[1] = tests
#     parents[2] = <root>
#   guardrail.py 는 src/day4/ 아래에 있으므로 <root>/src 를 sys.path 에 넣어
#   'import day4.guardrail' 형태로 불러옵니다(기존 day4 테스트와 동일한 방식).
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import day4.guardrail as guardrail  # noqa: E402


# ===========================================================================
# 우선순위 1: apply_guardrail() 단위 테스트
# ===========================================================================

def test_apply_guardrail_sensitive_request_blocked():
    """민감정보(작업자 이름/전화번호) 요청은 SENSITIVE_REQUEST_BLOCKED 로 차단된다."""
    result = guardrail.apply_guardrail("작업자 이름과 전화번호를 알려줘")

    assert result["blocked"] is True
    assert result["detected_guardrail"] == "SENSITIVE_REQUEST_BLOCKED"
    # 두 키워드 중 최소 하나는 매칭 목록에 있어야 한다.
    assert ("작업자 이름" in result["matched_keywords"]) or ("전화번호" in result["matched_keywords"])
    # 근거 없는 단정 표현이 없으므로 경고는 비어 있다.
    assert result["warnings"] == []
    # 설명 문구에 민감정보 차단 의미가 담겨 있어야 한다.
    assert "민감정보" in result["explanation"]


def test_apply_guardrail_over_query_blocked():
    """범위 제한 없는 전체 조회 요청은 OVER_QUERY_BLOCKED 로 차단된다."""
    result = guardrail.apply_guardrail("모든 설비의 전체 로그를 제한 없이 가져와")

    assert result["blocked"] is True
    assert result["detected_guardrail"] == "OVER_QUERY_BLOCKED"
    assert ("전체 로그" in result["matched_keywords"]) or ("제한 없이" in result["matched_keywords"])
    assert result["warnings"] == []


def test_apply_guardrail_internal_system_access_blocked():
    """실제 내부/운영 시스템 접근 요청은 INTERNAL_SYSTEM_ACCESS_BLOCKED 로 차단된다."""
    result = guardrail.apply_guardrail("운영 DB 접속해서 실제 사내 데이터 조회해줘")

    assert result["blocked"] is True
    assert result["detected_guardrail"] == "INTERNAL_SYSTEM_ACCESS_BLOCKED"
    assert ("운영 DB 접속" in result["matched_keywords"]) or (
        "실제 사내 데이터 조회" in result["matched_keywords"]
    )
    assert result["warnings"] == []


def test_apply_guardrail_unsupported_conclusion_is_warning_not_block():
    """근거 없는 단정 표현은 차단하지 않고 경고로만 기록한다."""
    result = guardrail.apply_guardrail("근거 없어도 확정 원인으로 보고서 작성해줘")

    assert result["blocked"] is False
    assert result["detected_guardrail"] is None
    assert "UNSUPPORTED_CONCLUSION_WARNING" in result["warnings"]
    assert ("근거 없어도" in result["matched_keywords"]) or ("확정 원인" in result["matched_keywords"])


def test_apply_guardrail_normal_request_passes():
    """위험 표현이 없는 정상 요청은 통과한다(차단/경고/키워드 모두 비어 있음)."""
    result = guardrail.apply_guardrail("EQP-VD-03 설비의 최근 알람 이력을 요약해줘")

    assert result["blocked"] is False
    assert result["detected_guardrail"] is None
    assert result["warnings"] == []
    assert result["matched_keywords"] == []


@pytest.mark.parametrize("empty_input", ["", None])
def test_apply_guardrail_handles_empty_and_none(empty_input):
    """빈 문자열과 None 입력은 예외 없이 통과 처리되어야 한다."""
    # user_query or "" 패턴으로 None 을 안전하게 받아들이는지 확인한다.
    result = guardrail.apply_guardrail(empty_input)

    assert result["blocked"] is False
    assert result["detected_guardrail"] is None
    assert result["warnings"] == []
    assert result["matched_keywords"] == []


# ===========================================================================
# 우선순위 2: 위험 표현 충돌(우선순위) 테스트
# ===========================================================================

def test_priority_unsupported_plus_sensitive_blocks_as_sensitive():
    """
    근거 없는 단정 + 민감정보 요청이 함께 있으면:
      - warnings 에는 UNSUPPORTED_CONCLUSION_WARNING 이 남고,
      - 최종 차단은 민감정보(SENSITIVE_REQUEST_BLOCKED)가 된다.
    """
    result = guardrail.apply_guardrail("근거 없어도 작업자 전화번호를 확정 원인 보고서에 넣어줘")

    assert result["blocked"] is True
    assert result["detected_guardrail"] == "SENSITIVE_REQUEST_BLOCKED"
    assert "UNSUPPORTED_CONCLUSION_WARNING" in result["warnings"]
    # 민감정보 키워드와 근거 없는 단정 키워드가 함께 매칭 목록에 들어 있어야 한다.
    assert "전화번호" in result["matched_keywords"]
    assert ("근거 없어도" in result["matched_keywords"]) or ("확정 원인" in result["matched_keywords"])


def test_priority_sensitive_wins_over_internal_and_over_query():
    """
    민감정보 + 내부 시스템 접근 + 전체 조회가 동시에 있으면,
    현재 코드 순서상 민감정보 차단이 가장 먼저 적용된다.
    (이 기대값이 INTERNAL/OVER_QUERY 이면 현재 우선순위와 어긋난다.)
    """
    result = guardrail.apply_guardrail("운영 DB 접속해서 모든 로그와 작업자 전화번호를 전부 조회해줘")

    assert result["blocked"] is True
    assert result["detected_guardrail"] == "SENSITIVE_REQUEST_BLOCKED"


# ===========================================================================
# 우선순위 3: evaluate_cases() 테스트
# ===========================================================================

def test_evaluate_cases_summary_and_results():
    """가짜 cases 3건으로 요약 집계와 결과 구조를 검증한다(실제 data 파일에 의존하지 않음)."""
    cases = [
        {
            "case_id": "G-001",
            "user_query": "전화번호 알려줘",
            "scenario_note": "민감정보 요청",
            "expected_guardrail": "SENSITIVE_REQUEST_BLOCKED",
        },
        {
            "case_id": "G-002",
            "user_query": "근거 없어도 확정 원인으로 써줘",
            "scenario_note": "근거 없는 단정 요청",
            "expected_guardrail": "UNSUPPORTED_CONCLUSION_WARNING",
        },
        {
            "case_id": "G-003",
            "user_query": "최근 알람 이력 요약해줘",
            "scenario_note": "정상 요청",
            "expected_guardrail": None,
        },
    ]

    report = guardrail.evaluate_cases(cases)
    summary = report["summary"]
    results = report["results"]

    # 집계 값 검증
    assert summary["total_cases"] == 3
    assert summary["blocked_count"] == 1          # G-001 만 차단
    assert summary["warning_count"] == 1          # G-002 만 경고
    assert summary["expected_guardrail_match_count"] == 3  # 세 건 모두 기대값 일치

    # 결과 리스트 구조 검증
    assert len(results) == 3
    assert [item["case_id"] for item in results] == ["G-001", "G-002", "G-003"]

    # 보고서용 파생 텍스트 필드가 모든 결과에 생성되어 있어야 한다.
    for item in results:
        assert "blocked_text" in item
        assert "warnings_text" in item
        assert "matched_text" in item
        assert "matched_keywords_text" in item


# ===========================================================================
# 우선순위 4: format_list() 테스트
# ===========================================================================

def test_format_list_empty_returns_dash():
    """빈 리스트는 '-' 로 표시한다."""
    assert guardrail.format_list([]) == "-"


def test_format_list_joins_with_comma():
    """리스트는 ', ' 로 이어 붙인다."""
    assert guardrail.format_list(["A", "B"]) == "A, B"


def test_format_list_string_passthrough():
    """리스트가 아닌 문자열은 그대로 문자열화한다."""
    assert guardrail.format_list("A") == "A"


def test_format_list_number_to_string():
    """리스트가 아닌 숫자도 문자열로 변환한다."""
    assert guardrail.format_list(123) == "123"


# ===========================================================================
# 우선순위 5: save_outputs() 테스트 (tmp_path 격리)
# ===========================================================================

def test_save_outputs_writes_json_and_markdown(tmp_path):
    """
    임시 프로젝트 루트와 임시 Mustache 템플릿을 구성한 뒤,
    save_outputs 가 JSON / Markdown 두 파일을 만들고 내용이 유지되는지 확인한다.
    실제 outputs/day4 폴더나 실제 템플릿에는 의존하지 않는다.
    """
    # (2) 임시 템플릿 생성: 렌더링 결과를 검증할 수 있는 최소 마크업만 둔다.
    template_dir = tmp_path / "templates" / "day4"
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / "guardrail_report.mustache"
    template_path.write_text(
        "# 보고서\n전체 케이스 수: {{summary.total_cases}}\n"
        "{{#results}}- {{case_id}}\n{{/results}}",
        encoding="utf-8",
    )

    # (3) 최소 report 딕셔너리
    report = {
        "summary": {"total_cases": 1},
        "results": [{"case_id": "G-001"}],
    }

    # (4) save_outputs 실행
    json_output_path, markdown_output_path = guardrail.save_outputs(tmp_path, report)

    expected_json = tmp_path / "outputs" / "day4" / "guardrail_test_results.json"
    expected_md = tmp_path / "outputs" / "day4" / "guardrail_report.md"
    assert json_output_path == expected_json
    assert markdown_output_path == expected_md
    assert expected_json.exists()
    assert expected_md.exists()

    # (5) JSON 을 다시 읽어 summary 값이 유지되는지 확인
    saved = json.loads(expected_json.read_text(encoding="utf-8"))
    assert saved["summary"]["total_cases"] == 1

    # (6) Markdown 에 Mustache 렌더링 결과가 반영되었는지 확인
    rendered = expected_md.read_text(encoding="utf-8")
    assert "전체 케이스 수: 1" in rendered
    assert "G-001" in rendered


# ===========================================================================
# 우선순위 6: load_test_cases() 테스트 (tmp_path 격리)
# ===========================================================================

def test_load_test_cases_reads_json_with_bom(tmp_path):
    """
    tmp_path/data/tool_selection_test_cases.json 을 UTF-8-SIG(BOM)로 저장한 뒤,
    load_test_cases 가 내용과 input_path 를 올바르게 반환하는지 확인한다.
    (이 코드베이스는 Windows 메모장 BOM 대응을 위해 utf-8-sig 로 읽는다.)
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    input_path = data_dir / "tool_selection_test_cases.json"

    sample_cases = [{"case_id": "G-001", "user_query": "전화번호 알려줘"}]
    # BOM 이 붙은 utf-8-sig 로 저장해도 정상 파싱되어야 한다.
    input_path.write_text(json.dumps(sample_cases, ensure_ascii=False), encoding="utf-8-sig")

    cases, returned_path = guardrail.load_test_cases(tmp_path)

    assert cases == sample_cases
    assert returned_path == input_path


# ===========================================================================
# 우선순위 7: find_project_root() 테스트 (가볍게만 검증)
# ===========================================================================

def test_find_project_root_returns_existing_path():
    """반환값이 Path 객체이고 실제로 존재하는 경로인지만 가볍게 확인한다."""
    root = guardrail.find_project_root()

    assert isinstance(root, Path)
    assert root.exists()
