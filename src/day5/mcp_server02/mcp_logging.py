# -*- coding: utf-8 -*-
"""
Day5 mcp_server02 - MCP Logging (안전한 JSONL 호출 이력 저장)

[이 모듈의 역할]
MCP Tool 호출 이벤트를 한 줄 단위 JSONL 로그 파일로 안전하게 저장합니다.
교육용 디버깅/실습 확인을 목적으로 하며, 민감정보는 절대 남기지 않습니다.

[전체 흐름에서의 위치]
    mcp_server 의 진입 함수
        ↓ (이벤트 발생 시)
    [mcp_logging.log_event]  ← sanitize_log_payload 로 안전 필드만 추려서
        ↓
    outputs/day5/mcp_server02/logs/mcp_server02.jsonl  (utf-8, 한 줄=한 이벤트)

[설계 원칙]
1. import 방향은 mcp_logging → security 단방향이다.
   security.py 는 sanitize/masking 전담 leaf 모듈이며, 이 파일을 import 하지 않는다.
   → 순환 import 위험이 없다.
2. 로그 저장 실패가 MCP Tool 실행 실패로 이어지면 안 된다.
   log_event() 는 내부 예외를 모두 흡수하고 성공 True / 실패 False 만 반환한다.
3. 저장 대상은 반드시 sanitize_log_payload() 를 통과한 '안전 필드'만이다.
   raw user_query / raw arguments / raw result / LLM prompt·response /
   token·password·endpoint·환경변수 값 / stack trace 전체는 저장하지 않는다.
4. 로그 경로는 '현재 작업 디렉터리'가 아니라 '프로젝트 루트' 기준으로 계산한다.
   → 어디서 실행해도 같은 위치에 기록된다.

[교육 포인트]
"호출 이력을 남기되, 절대 민감정보를 함께 남기지 않는다"가 핵심입니다.
로그는 외부로 나가는 또 하나의 경계(boundary)이므로, 결과 반환과 동일하게
허용 필드 화이트리스트 + 마스킹을 적용합니다.

[JSONL 인코딩 주의]
JSONL 은 append 로 한 줄씩 누적되므로, 줄마다 BOM 이 섞이면 파싱이 깨집니다.
따라서 이 파일은 (프로젝트의 일반 입력 파일과 달리) BOM 없는 'utf-8' 로 기록하고,
읽을 때는 혹시 모를 BOM 을 흡수하도록 'utf-8-sig' 로 읽습니다.
"""
import json          # 이벤트 1건을 JSONL 한 줄(json.dumps)로 직렬화하기 위해 사용.
import os             # 로그 디렉터리 override 환경변수를 읽기 위해 사용(값은 출력하지 않음).
import datetime       # 이벤트 timestamp(ISO 문자열) 생성에 사용.
from pathlib import Path  # 프로젝트 루트 기준 로그 경로를 OS 무관하게 계산하기 위해 사용.

# import 방향: mcp_logging → security (단방향). security 는 이 파일을 import 하지 않는다.
# security 의 마스킹/인자 정리 함수를 재사용해, 로그도 결과 반환과 '동일한' 안전 기준을 적용한다.
from day5.mcp_server02.security import mask_sensitive_text, sanitize_arguments


# ---------------------------------------------------------------------------
# 경로/환경변수 상수
# ---------------------------------------------------------------------------
# [프로젝트 루트 계산]
#   이 파일 위치: <root>/src/day5/mcp_server02/mcp_logging.py
#   parents[0]=mcp_server02, [1]=day5, [2]=src, [3]=<root>
#   → parents[3] 이 프로젝트 루트다(현재 작업 디렉터리와 무관).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# 로그 디렉터리를 바꿀 때 쓰는 환경변수 이름.
# [주의] 이 변수의 '값'은 로그/콘솔에 절대 출력하지 않는다(이름만 코드/문서에 노출).
LOG_DIR_ENV = "MCP_SERVER01_LOG_DIR"

# 기본 로그 파일명.
LOG_FILE_NAME = "mcp_server02.jsonl"


# ---------------------------------------------------------------------------
# 로그에 저장해도 되는 필드 화이트리스트
# ---------------------------------------------------------------------------
# [용도] sanitize_log_payload() 가 이 집합에 있는 키만 통과시킨다.
#        목록에 없는 키(result/results/issues 원문/tool_plan/prompt/response 등)는
#        통째로 제거되어, raw 데이터가 로그로 새어 나가는 것을 원천 차단한다.
# [주의] 'user_query' 와 'arguments' 는 여기에 직접 넣지 않는다.
#        대신 'user_query_preview' / 'arguments_preview' 로 가공해서만 남긴다.
_ALLOWED_LOG_FIELDS = {
    "timestamp",
    "event_type",
    "tool_name",
    "validation_status",
    "execution_status",
    "status",                # 실행 결과 status(executed/rejected/needs_review/error 등)
    "executed_count",
    "generation_source",
    "fallback_used",
    "user_query_preview",
    "arguments_preview",
    "issue_types",
    "error_type",
    "safe_error_message",
    "message",               # server_started/fastmcp_unavailable 등 고정 안내 문구
    "has_fastmcp",
}

# user_query 미리보기 최대 길이(원문 전체 저장 금지).
_MAX_QUERY_PREVIEW = 80
# 일반 문자열 값의 최대 길이(과도한 길이/숨은 본문 방지).
_MAX_STR = 300


def get_log_dir():
    """로그 디렉터리 경로(Path)를 돌려준다.

    [반환]
        - 환경변수 MCP_SERVER01_LOG_DIR 가 설정돼 있으면 그 경로.
        - 없으면 프로젝트 루트 기준 outputs/day5/mcp_server02/logs.

    [주의]
        환경변수 '값' 자체는 로그/콘솔에 출력하지 않는다(경로 노출 방지).
    """
    override = os.environ.get(LOG_DIR_ENV, "").strip()
    if override:
        return Path(override)
    return _PROJECT_ROOT / "outputs" / "day5" / "mcp_server02" / "logs"


def get_log_path():
    """로그 파일 전체 경로(Path)를 돌려준다(get_log_dir()/mcp_server02.jsonl)."""
    return get_log_dir() / LOG_FILE_NAME


def ensure_log_dir():
    """로그 디렉터리가 없으면 생성한다.

    [반환]
        True  : 디렉터리가 존재하거나 생성에 성공.
        False : 생성 실패(권한/경로 문제 등). 호출부는 이 값을 보고 조용히 넘어간다.

    [주의]
        실패해도 예외를 던지지 않는다. 로그 때문에 메인 실행이 깨지면 안 되기 때문.
    """
    try:
        get_log_dir().mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def _now_iso():
    """현재 시각을 초 단위 ISO 문자열로 돌려준다(예: '2026-06-01T10:00:00')."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _query_preview(value):
    """user_query 류 문자열을 '마스킹 + 80자 preview' 로 축약한다(원문 전체 저장 금지)."""
    text = mask_sensitive_text(value)
    if len(text) > _MAX_QUERY_PREVIEW:
        return text[:_MAX_QUERY_PREVIEW] + "...(생략)"
    return text


def _mask_log_value(value):
    """로그 값 한 개를 타입별로 안전하게 마스킹한다(내부 헬퍼).

    - 문자열: mask_sensitive_text 적용 후 과도 길이 절단.
    - dict  : 각 값에 재귀 적용(키 이름은 보존).
    - list  : 각 요소에 재귀 적용.
    - 그 외 : 그대로 반환(int/bool/None).
    """
    if isinstance(value, str):
        masked = mask_sensitive_text(value)
        if len(masked) > _MAX_STR:
            return masked[:_MAX_STR] + "...(생략)"
        return masked
    if isinstance(value, dict):
        return {k: _mask_log_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_log_value(v) for v in value]
    return value


def sanitize_log_payload(payload):
    """로그 payload(dict)를 '저장해도 되는 안전 필드'만 남긴 dict 로 변환한다.

    [입력]
        payload: 로그로 남기고 싶은 dict (dict 가 아니면 빈 dict 로 처리).
    [반환]
        화이트리스트 필드만 남기고, 문자열은 마스킹·길이 제한한 안전 dict.

    [처리 순서]
        1) user_query / user_query_preview → 'user_query_preview'(마스킹+80자)로만 보존.
           raw user_query 전체는 절대 남기지 않는다.
        2) arguments / arguments_preview → security.sanitize_arguments 로 정리한
           'arguments_preview' 로만 보존.
        3) 그 외 키는 _ALLOWED_LOG_FIELDS 에 있는 것만 통과시키고 _mask_log_value 적용.
           목록에 없는 키(result/results/issues 원문/tool_plan/prompt/response 등)는 제거.

    [왜 필요한가]
        로그도 외부로 나가는 경계다. 허용 필드만 통과시키고 나머지는 버려야
        raw 응답·프롬프트·민감값이 로그로 새어 나가지 않는다.
    """
    if not isinstance(payload, dict):
        return {}

    safe = {}

    # 1) user_query 는 preview 로만 (원문 전체 금지)
    if "user_query" in payload or "user_query_preview" in payload:
        raw_query = payload.get("user_query_preview", payload.get("user_query"))
        if raw_query is not None:
            safe["user_query_preview"] = _query_preview(raw_query)

    # 2) arguments 는 sanitize_arguments 결과(arguments_preview)로만
    if "arguments" in payload or "arguments_preview" in payload:
        raw_args = payload.get("arguments_preview", payload.get("arguments"))
        if isinstance(raw_args, dict):
            # 민감 key 마스킹 + 문자열 값 내부 마스킹(security 재사용)
            safe["arguments_preview"] = sanitize_arguments(raw_args)
        elif raw_args is not None:
            safe["arguments_preview"] = _mask_log_value(raw_args)

    # 3) 나머지 허용 필드만 통과 (비허용 키는 자동 제거)
    for key, value in payload.items():
        if key in ("user_query", "user_query_preview", "arguments", "arguments_preview"):
            continue  # 위에서 이미 처리
        if key not in _ALLOWED_LOG_FIELDS:
            continue  # raw result/prompt/response 등은 여기서 차단
        safe[key] = _mask_log_value(value)

    return safe


def log_event(event_type, payload):
    """MCP 호출 이벤트 한 건을 JSONL 한 줄로 저장한다.

    [입력]
        event_type: 이벤트 종류 문자열(예: "tool_executed").
        payload   : 이벤트 부가 정보 dict(저장 전 sanitize_log_payload 로 정리됨).
    [반환]
        True  : 저장 성공.
        False : 저장 실패(디렉터리 생성/쓰기 실패 등). 예외는 외부로 던지지 않는다.

    [동작]
        1) timestamp/event_type 를 먼저 채운다(이 둘은 항상 보존).
        2) payload 를 sanitize_log_payload 로 안전 필드만 남긴다.
        3) outputs/.../mcp_server02.jsonl 에 BOM 없는 utf-8 한 줄로 append.

    [보안/안정성]
        - 저장 실패가 Tool 실행 실패로 이어지지 않도록 모든 예외를 흡수한다.
        - sanitize 를 통과한 안전 필드만 기록한다(raw 데이터 미기록).

    [호출 시점]
        mcp_server 의 각 진입 함수(call_mcp_tool / call_execute_query 등) 내부.
    """
    try:
        record = {"timestamp": _now_iso(), "event_type": str(event_type)}
        safe = sanitize_log_payload(payload or {})
        # event_type/timestamp 는 record 값이 우선(payload 가 덮어쓰지 못하게)
        safe.pop("event_type", None)
        safe.pop("timestamp", None)
        record.update(safe)

        if not ensure_log_dir():
            return False

        line = json.dumps(record, ensure_ascii=False)
        # JSONL append: BOM 이 줄마다 섞이지 않도록 'utf-8'(BOM 없음)로 기록한다.
        with open(get_log_path(), "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return True
    except Exception:
        # 로그 실패는 조용히 무시한다(메인 실행 보호).
        return False
