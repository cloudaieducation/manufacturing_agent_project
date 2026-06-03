# -*- coding: utf-8 -*-
"""
Day5 mcp_server01 - Security (민감정보 보호 / 안전한 반환)

[이 모듈의 역할]
MCP Tool 실행 결과나 에러 메시지가 외부(MCP Client, trace, 콘솔)로 나가기 전에
민감정보를 제거하고, 반환 데이터를 안전한 요약 형태로 제한하는 leaf 계층입니다.

[전체 흐름에서의 위치]
    mcp_server → tool_executor → equipment_data / manual_search
                                      ↓
                                 [security] ← 결과/에러를 sanitize 한 뒤 반환
                                      ↓
                                 안전한 dict 만 외부로 나감

[설계 원칙]
1. leaf 모듈: 표준 라이브러리(re)만 사용하고, day5 내부 다른 모듈을 import 하지 않는다.
   → 순환 import 위험이 원천적으로 없다. (security 는 누구나 자유롭게 import 가능)
2. 절대 출력/반환 금지 대상:
   - API Key / token / password / authorization / bearer 값
   - endpoint / host / url 전체 문자열
   - 전체 환경변수 값
   - 실제 API/DB raw 응답 전체
3. sanitize_result() 는 tool_name 별 '허용 필드 화이트리스트'만 남긴다.
   허용 목록에 없는 필드는 제거하거나 safe_summary 로 축약한다.

[교육 포인트]
"조회 결과를 그대로 흘려보내지 않는다"가 핵심입니다.
실제 운영에서는 응답에 내부 호스트명, 자격증명, 작업자 개인정보 등이 섞여 들어올 수
있으므로, 외부로 나가는 경계(boundary)에서 한 번 더 거르는 계층을 두는 패턴을 학습합니다.
"""
import re


# ---------------------------------------------------------------------------
# 민감정보로 간주할 key 이름 / 패턴
# ---------------------------------------------------------------------------
# [용도] sanitize_arguments() 와 mask_sensitive_text() 에서 공통으로 참조한다.
#        key 이름에 아래 단어가 (대소문자 무관) 포함되면 그 값을 마스킹한다.
# [주의] 교육용 가상 시나리오 기준이며, 실제 운영에서는 보안팀 기준에 맞춰 확장한다.
SENSITIVE_KEY_MARKERS = (
    "token",
    "password",
    "passwd",
    "pwd",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "credential",
    "endpoint",
    "host",
    "url",
    "access_key",
)

# 마스킹 후 노출되는 안전한 치환 문자열
REDACTED = "[REDACTED]"


# [용도] "key=value" 또는 "key: value" 형태의 문자열에서 민감 key 의 값을 가린다.
# 예) "authorization: Bearer abc.def" / "endpoint=https://internal/api"
_KEYVALUE_PATTERN = re.compile(
    r"(?i)\b("
    r"token|password|passwd|pwd|secret|api[_-]?key|apikey|authorization|"
    r"bearer|credential|endpoint|host|url|access[_-]?key"
    r")\b(\s*[=:]\s*)(\S+)"
)

# [용도] "Bearer <토큰>" 단독 표현을 가린다(key=value 형태가 아닐 때 대비).
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*")

# [용도] http/https URL 전체를 가린다(endpoint/host 노출 방지).
_URL_PATTERN = re.compile(r"(?i)\bhttps?://\S+")


def mask_sensitive_text(text):
    """문자열 안의 민감정보(토큰/비밀번호/endpoint/URL 등)를 [REDACTED]로 치환한다.

    [입력]
        text: 임의 객체. str() 로 변환 후 처리한다(예외를 던지지 않는다).
    [반환]
        민감정보가 가려진 문자열.

    [처리 순서]
        1) "Bearer <토큰>" 표현을 먼저 가린다.
           (key=value 보다 먼저 처리해야 "authorization: Bearer <토큰>" 의 토큰까지 가려진다.
            key=value 를 먼저 돌리면 'Bearer' 한 단어만 값으로 잡혀 뒤 토큰이 남는다.)
        2) http/https URL 전체를 [REDACTED_URL] 로.
        3) "key=value" / "key: value" 형태에서 민감 key 의 value 를 [REDACTED] 로.

    [호출 시점]
        safe_error_message(), sanitize_arguments(), 그리고 외부로 문자열을 내보내기
        직전의 모든 경계에서 호출한다.

    [주의]
        완벽한 비밀 탐지는 불가능하다. 이 함수는 '흔한 형태'를 거르는 1차 방어선이며,
        애초에 민감정보를 결과/로그에 담지 않는 것이 우선이다.
    """
    s = str(text)
    # 1) Bearer 토큰 표현(두 단어 형태 "Bearer <토큰>")을 먼저 가린다.
    s = _BEARER_PATTERN.sub("Bearer " + REDACTED, s)
    # 2) URL 전체(endpoint/host 노출 방지)
    s = _URL_PATTERN.sub("[REDACTED_URL]", s)
    # 3) key=value / key: value 형태의 값 마스킹 (key 와 구분자는 보존, 값만 가림)
    s = _KEYVALUE_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", s)
    return s


def safe_error_message(error):
    """예외/에러를 외부로 내보내기 안전한 짧은 문자열로 변환한다.

    [입력]
        error: Exception 객체 또는 문자열.
    [반환]
        민감정보가 제거되고 길이가 제한된 안전한 에러 문자열.

    [왜 필요한가]
        예외 메시지에는 파일 경로, 환경변수 값, endpoint, 자격증명 등이 섞여
        들어올 수 있다. 이를 그대로 trace/report/콘솔에 노출하면 보안 사고가 된다.
        따라서 (1) 타입명 + 메시지만 취하고, (2) mask_sensitive_text 로 가린 뒤,
        (3) 과도한 길이를 잘라 반환한다.

    [호출 시점]
        tool_executor 의 except 블록, equipment_data/manual_search 의 오류 처리.
    """
    # 예외 객체면 "타입명: 메시지" 형태로, 아니면 그대로 문자열화
    if isinstance(error, BaseException):
        raw = f"{type(error).__name__}: {error}"
    else:
        raw = str(error)
    masked = mask_sensitive_text(raw)
    # 과도한 길이(스택성 정보 등)를 방지하기 위해 안전하게 절단
    if len(masked) > 300:
        masked = masked[:300] + "...(생략)"
    return masked


def enforce_limit(value, default=20, maximum=100):
    """조회 limit 값을 안전 범위로 강제한다(과도한 전체 조회 방지).

    [입력]
        value  : 요청된 limit (int/str/None 등 무엇이든 허용).
        default: value 가 없거나 해석 불가일 때 사용할 기본값.
        maximum: 허용 상한. 이보다 크면 maximum 으로 깎는다.
    [반환]
        1 이상 maximum 이하의 정수.

    [왜 필요한가]
        limit 를 지정하지 않거나 매우 큰 값을 주면 전체 조회에 가까운 부하/노출이
        발생할 수 있다. 읽기 전용 조회라도 반환량 상한을 강제해 두는 것이 안전하다.

    [호출 시점]
        equipment_data 의 각 fetch_* 함수에서 limit 인자를 정규화할 때.
    """
    try:
        # 문자열로 들어와도 int 변환을 시도한다.
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < 1:
        # 0 이하의 limit 는 의미가 없으므로 기본값으로 되돌린다.
        return default
    if n > maximum:
        return maximum
    return n


def sanitize_arguments(arguments):
    """Tool 인자 dict 에서 민감 key 의 값을 마스킹한다(trace/응답에 인자를 남길 때 대비).

    [입력]
        arguments: tool 호출 인자 dict (dict 가 아니면 빈 dict 로 처리).
    [반환]
        얕은 복사본. 민감 key 의 값은 [REDACTED], 그 외 문자열 값은 mask_sensitive_text 적용.

    [동작]
        - key 이름에 SENSITIVE_KEY_MARKERS 가 포함되면 값을 통째로 [REDACTED].
        - 일반 문자열 값은 내부에 토큰/URL 이 섞여 있을 수 있으므로 mask_sensitive_text 적용.
        - 그 외 타입(int/bool 등)은 그대로 둔다.

    [호출 시점]
        tool_executor 가 실행 인자를 결과/trace 에 기록하기 직전.
    """
    if not isinstance(arguments, dict):
        return {}
    safe = {}
    for key, value in arguments.items():
        key_lower = str(key).lower()
        if any(marker in key_lower for marker in SENSITIVE_KEY_MARKERS):
            # 민감 key 는 값 자체를 가린다.
            safe[key] = REDACTED
        elif isinstance(value, str):
            # 문자열 값 내부에 섞인 민감 패턴까지 가린다.
            safe[key] = mask_sensitive_text(value)
        else:
            safe[key] = value
    return safe


# ---------------------------------------------------------------------------
# tool_name 별 반환 허용 필드 화이트리스트
# ---------------------------------------------------------------------------
# [용도] sanitize_result() 가 각 Tool 응답에서 '남겨도 되는 요약 필드'만 통과시킨다.
#        목록에 없는 필드는 제거되며, 이를 통해 raw 응답 전체가 새어 나가는 것을 막는다.
# [주의] 실제 조회 대상 값이 아니라 '필드 이름' 화이트리스트다.
#        교육용 가상 시나리오 기준이며 실제 API 스키마가 아니다.
RESULT_FIELD_WHITELIST = {
    "get_equipment_status": ("equipment_id", "status_code", "status_label", "updated_at"),
    "get_recent_alarm_events": (
        "equipment_id", "alarm_code", "event_count", "recent_events", "limit",
    ),
    "get_process_status": ("process_name", "line_id", "process_state", "updated_at"),
    "get_quality_metrics": (
        "metric_name", "equipment_id", "line_id", "value", "unit", "period",
    ),
    "get_maintenance_history": ("equipment_id", "history", "count"),
    "get_equipment_overview": ("equipment_id", "equipment_type", "line_id"),
    "search_manual": ("query", "matched_alarm_code", "documents"),
}


def sanitize_result(tool_name, payload):
    """Tool 응답(payload)을 tool_name 별 허용 필드만 남긴 안전한 요약 dict 로 변환한다.

    [입력]
        tool_name: 실행한 Tool 이름.
        payload  : client 가 반환한 응답 dict.
    [반환]
        허용 필드만 남기고, 문자열 값은 마스킹한 안전한 dict.
        payload 가 dict 가 아니면 {"safe_summary": "<마스킹된 짧은 문자열>"} 로 축약한다.
        화이트리스트에 없는 tool_name 이면 모든 필드를 제거하고 safe_summary 만 남긴다.

    [동작]
        1) payload 가 dict 가 아니면 문자열로 축약(safe_summary).
        2) tool_name 의 허용 필드 집합을 조회한다.
           - 허용 목록이 없으면(미등록 tool) 안전을 위해 전체를 축약한다.
        3) 허용 필드만 추려서 _mask_value 로 재귀 마스킹한다.

    [왜 필요한가]
        raw API/DB 응답을 그대로 반환하면 내부 host, 자격증명, 작업자 개인정보 등이
        새어 나갈 수 있다. 외부 경계에서 '허용한 필드만' 통과시키는 것이 안전하다.

    [호출 시점]
        tool_executor.execute_single_tool() 이 client 결과를 반환하기 직전.
    """
    # 1) dict 가 아니면 안전 문자열로 축약
    if not isinstance(payload, dict):
        return {"safe_summary": mask_sensitive_text(payload)}

    # 2) 허용 필드 조회 (미등록 tool 은 전체 축약)
    allowed = RESULT_FIELD_WHITELIST.get(tool_name)
    if allowed is None:
        return {"safe_summary": "결과를 안전하게 표시할 수 없는 Tool 입니다."}

    # 3) 허용 필드만 추려서 마스킹
    safe = {}
    for key in allowed:
        if key in payload:
            safe[key] = _mask_value(payload[key])
    return safe


def _mask_value(value):
    """허용 필드의 값을 타입별로 안전하게 마스킹하는 내부 헬퍼.

    - 문자열: mask_sensitive_text 적용
    - dict  : 각 값에 재귀 적용 (단, key 이름은 보존)
    - list  : 각 요소에 재귀 적용
    - 그 외 : 그대로 반환 (int/bool/None 등)

    [주의]
        list/dict 깊이가 깊어도 동작하지만, client mock 응답은 얕은 구조를 권장한다.
    """
    if isinstance(value, str):
        return mask_sensitive_text(value)
    if isinstance(value, dict):
        return {k: _mask_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_value(v) for v in value]
    return value
