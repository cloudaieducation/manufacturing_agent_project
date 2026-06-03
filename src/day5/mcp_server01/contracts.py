# -*- coding: utf-8 -*-
"""
Day4 Tool Selection Contracts
==============================

[이 모듈의 역할]
langgraph_tool_selector_v2_runner / normalizer / validator 세 모듈이
공통으로 참조하는 '기준표(Tool Contract)' 모듈입니다.

전체 파이프라인 흐름에서 이 파일이 차지하는 위치:
    사용자 질문
      → prompt_builder   : 질문을 LLM 입력용 프롬프트로 변환
      → runner           : LLM 또는 fallback(규칙 기반)으로 Tool Plan 생성
      → normalizer       : LLM 출력의 필드명·형식을 ALLOWED_PLAN_ITEM_FIELDS 기준으로 정규화
      → validator        : TOOL_CONTRACTS 기준으로 각 tool 호출의 인수·이름 적합성 검증
      → repair           : validator가 발견한 문제를 자동 수정 시도
      → finalize         : 최종 Tool Plan 확정
      → results          : 검증 결과 집계
      → report           : 결과 렌더링(Mustache)
      → output_writer    : JSON/Markdown 아티팩트 저장

이 파일(contracts.py)은 위 흐름에서 normalizer와 validator가 공통으로
가져다 쓰는 '기준표' 역할을 담당합니다.

[이 모듈이 담당하지 않는 것]
- LLM 호출 · Tool Plan 생성 로직   → runner / prompt_builder
- Tool Plan 정규화(필드명 교정)     → normalizer
- Tool Plan 검증 판정 로직          → validator
- 자동 수정 로직                    → repair
- 평가 정답(case_id / expected_tools / expected_arguments)
  → 테스트 케이스 데이터 파일(data/day4_*.json)에 별도 보관

[다른 모듈과의 관계]
- 이 파일은 day4 내 다른 어떤 모듈도 import하지 않는 '잎 모듈(leaf module)'.
  순환 임포트 위험 없이 누구든 자유롭게 참조 가능.
- validator.py : TOOL_CONTRACTS 를 읽어 required/any_of_required/optional 인수 충족 여부 판정
- normalizer.py: ALLOWED_PLAN_ITEM_FIELDS 를 읽어 예상치 못한 필드 제거/경고
- runner.py    : ALLOWED_TOOLS, FORBIDDEN_SQL_TOOLS 를 읽어 LLM 출력 후처리에서
                 허용 범위 밖 tool을 걸러냄
- SEVERITY_ORDER: validator가 여러 issue를 집계할 때 최악 severity를 결정하는 데 사용

[교육 목적]
이 예제의 Tool Contract와 상수들은 'DisplayEdu Fab' 가상 제조 시나리오를
기반으로 설계된 교육용 기준입니다. 실제 제조 기업의 설비 규격·운영
기준과는 무관하며, 실 운영 환경에 그대로 적용할 수 없습니다.

langgraph_tool_selector_v2_runner / normalizer / validator가 공유하는
Tool 정의·Tool Contract·공용 상수를 모아 둔 모듈입니다.

이 파일은 다른 day4 모듈에 의존하지 않는 leaf 모듈입니다.
(case_id / expected_tools / expected_arguments 같은 평가 정답은 포함하지 않습니다.)
"""

# ---------------------------------------------------------------------------
# Allowed MCP Tools (Text-to-SQL / SQL 관련 Tool은 의도적으로 제외)
# ---------------------------------------------------------------------------
# [역할] LLM이 선택할 수 있는 MCP Tool 이름의 허용 목록(allowlist).
#        runner와 validator가 이 목록을 참조하여 LLM이 출력한 tool_name이
#        실제로 존재하는 도구인지 확인한다.
#
# [사용 단계] runner → normalizer → validator 세 단계 모두에서 참조.
#   - runner   : LLM 출력의 selected_tools 필드가 이 목록 안에 있는지 1차 확인
#   - validator: tool_name이 이 목록에 없으면 "unknown_tool" 이슈 발생
#
# [판단 기준] 목록에 없는 tool_name은 validator에서 FAIL 처리.
#
# [변경 시 영향]
#   - 새 MCP Tool을 추가하려면 이 목록과 TOOL_CONTRACTS 두 곳 모두 업데이트 필요.
#   - 목록에서 제거하면 기존 테스트 케이스 결과가 FAIL로 바뀔 수 있으므로
#     데이터 파일(data/day4_*.json)의 expected_tools도 함께 검토할 것.
#
# [교육용 가상 시나리오 기준]
#   아래 7개 Tool은 DisplayEdu Fab 가상 시나리오 전용 MCP 도구이며
#   실제 운영 시스템의 API 목록이 아닙니다.
ALLOWED_TOOLS = [
    "get_equipment_status",       # 특정 설비의 현재 상태 조회
    "get_recent_alarm_events",    # 설비·알람 코드별 최근 알람 이력 조회
    "get_process_status",         # 공정 또는 라인의 현재 상태 조회
    "get_quality_metrics",        # 품질 지표·불량률·수율·검사 결과 조회
    "get_maintenance_history",    # 설비 정비·보전·부품 교체 이력 조회
    "get_equipment_overview",     # 설비 요약 정보·개요 조회
    "search_manual",              # 기술 문서·알람 조치 절차·트러블슈팅 근거 검색
]

# [역할] Tool Plan에 등장하면 즉시 validation issue(FAIL)로 처리할 금지 Tool 목록.
#        Text-to-SQL 계열 Tool이 포함된다.
#
# [의도적 제외 이유]
#   이 day4 예제의 목적은 'MCP Tool 선택 흐름(tool selection pipeline)'의
#   설계와 검증 방식을 학습하는 데 있다.
#   Text-to-SQL 관련 Tool(sql_generator, execute_sql 등)은 SQL 인젝션 방지,
#   쿼리 안전성 검사, DB 접근 권한 등 별도의 안전성 검토 프레임워크가 필요하며,
#   이는 day4 Text-to-SQL 안전성 예제(data/day4_text_to_sql_cases.json 기반)에서
#   독립적으로 다룬다. 두 흐름을 혼합하면 각 개념의 책임 경계가 불분명해지므로
#   여기서는 의도적으로 분리하였다.
#
# [사용 단계] validator 단계에서만 사용.
#   tool_name이 이 목록에 포함되면 "forbidden_tool" 이슈(FAIL)를 생성한다.
#
# [판단 기준] 목록에 있는 tool_name → 즉시 FAIL. ALLOWED_TOOLS 목록과 교집합 없음.
#
# [변경 시 영향]
#   새 SQL 계열 Tool을 가상 시나리오에 추가할 경우 이 목록에도 함께 추가.
#   목록 내 이름을 임의로 바꾸면 validator가 해당 Tool을 걸러내지 못하게 된다.
#
# [교육용 가상 시나리오 기준]
#   아래 Tool 이름은 DisplayEdu Fab 시나리오에서 Text-to-SQL 흐름을 시뮬레이션하기
#   위해 만든 가상의 도구 이름입니다.
FORBIDDEN_SQL_TOOLS = [
    "check_text_to_sql_safety",   # SQL 안전성 사전 검사 (Text-to-SQL 전용)
    "sql_generator",              # 자연어 → SQL 변환 생성기
    "execute_sql",                # SQL 직접 실행 (DB 직접 접근)
    "run_sql",                    # SQL 실행의 별칭(alias) 형태
    "query_database_with_sql",    # SQL을 이용한 DB 조회
]

# [역할] LLM이 생성한 plan item(dict)에 허용되는 키(필드) 집합.
#        normalizer가 이 집합에 없는 필드를 unknown_field 경고로 처리하거나 제거한다.
#
# [사용 단계] normalizer 단계에서 LLM 출력 정규화 시 참조.
#   LLM이 계약에 없는 필드(예: "note", "comment", "confidence")를 출력한 경우
#   normalizer가 경고를 남기고 해당 필드를 제거한다.
#
# [각 필드 의미]
#   "step"      : 실행 순서를 나타내는 정수 (1부터 시작).
#                 여러 tool이 순차 또는 조건 분기로 실행될 때 순서를 명시.
#   "tool_name" : ALLOWED_TOOLS 목록에 있는 MCP Tool 이름 (문자열).
#   "arguments" : tool 호출에 전달할 인수 딕셔너리.
#                 TOOL_CONTRACTS의 required/any_of_required/optional로 검증.
#   "condition" : 이 step이 실행되는 조건 (선택 필드, 문자열).
#                 예: "equipment_id를 확인한 후에만 실행".
#   "reason"    : LLM이 이 tool을 선택한 이유 설명 (문자열).
#                 MIN_REASON_LENGTH 미만이면 weak_reason 경고 발생.
#
# [판단 기준] 집합에 없는 키 → normalizer에서 unknown_field WARNING 처리.
#
# [변경 시 영향] 새 필드를 plan item 스키마에 추가할 때 이 집합도 함께 업데이트.
#   Mustache 리포트 템플릿(templates/day4/)도 새 필드를 렌더링하도록 수정 필요.
#
# [교육용 가상 시나리오 기준] 실제 MCP 표준 스키마가 아닌 교육 설계 전용 필드 집합.
ALLOWED_PLAN_ITEM_FIELDS = {"step", "tool_name", "arguments", "condition", "reason"}

# [역할] plan item의 "reason" 필드가 충분히 서술되었는지 판단하는 최소 글자 수 임계값.
#
# [사용 단계] validator 단계에서 reason 품질 검사 시 참조.
#   len(reason) < MIN_REASON_LENGTH 이면 "weak_reason" WARNING 이슈를 생성한다.
#
# [판단 기준]
#   - 10자 미만: weak_reason (WARNING) → LLM이 이유를 충분히 서술하지 않은 것으로 판단.
#   - 10자 이상: reason 길이 기준 통과 (내용의 논리적 타당성은 별도 판단 불필요).
#
# [변경 시 영향]
#   값을 높이면 더 많은 plan item이 weak_reason 경고를 받게 되어
#   quality gate 통과율이 낮아질 수 있다. 교육 시나리오 난이도 조정 시 변경 가능.
#
# [교육용 가상 시나리오 기준]
#   10자는 가상 시나리오에서 "최소한의 이유 서술"을 요구하기 위해 설정한
#   교육 목적 임계값이며, 실 운영 기준이 아닙니다.
MIN_REASON_LENGTH = 10


# ---------------------------------------------------------------------------
# Tool Contract
# ---------------------------------------------------------------------------
# [역할] 각 MCP Tool에 대해 '언제 써야 하는지', '어떤 인수가 필수인지',
#        '어떤 인수가 선택적인지'를 정의한 기준표(contract).
#        validator.py가 이 기준표를 읽어 LLM이 생성한 Tool Plan의 각 step을 검증한다.
#
# [사용 단계]
#   - validator : TOOL_CONTRACTS[tool_name]을 읽어 인수 충족 여부를 판정
#   - repair    : 부족한 인수를 보완할 때 어떤 인수가 필요한지 파악하기 위해 참조
#   - (선택적) prompt_builder: Tool 목록을 프롬프트에 포함할 때 purpose/when_to_use 활용 가능
#
# [각 Contract 항목의 구조]
#   "purpose"                 : 이 tool의 담당 업무를 한 문장으로 기술.
#                               validator 오류 메시지와 Mustache 리포트에 그대로 표시됨.
#   "when_to_use"             : 이 tool을 선택해야 하는 사용자 질문 유형.
#   "when_not_to_use"         : 이 tool을 선택하면 안 되는 상황.
#                               LLM이 잘못된 tool을 선택했을 때 repair 단계에서
#                               어떤 tool로 교체해야 하는지 판단하는 힌트로도 활용 가능.
#   "required_arguments"      : 이 tool 호출 시 반드시 제공해야 하는 인수 이름 목록.
#                               누락 시 validator에서 "missing_required_argument" FAIL 발생.
#   "any_of_required_arguments": 이 목록 중 하나 이상의 인수가 있어야 함.
#                               모두 없으면 "missing_any_of_required" FAIL 발생.
#                               빈 리스트([])이면 이 조건은 적용되지 않음.
#   "optional_arguments"      : 있어도 되고 없어도 되는 인수 이름 목록.
#                               이 목록 + required + any_of_required 외의 인수를
#                               LLM이 제공하면 "tool_contract_mismatch" WARNING 발생.
#
# [판단 기준]
#   required_arguments 전부 충족 AND any_of_required_arguments 중 하나 이상 충족
#   → 인수 검증 통과.
#   contract에 정의되지 않은 인수(unknown argument) 사용 → tool_contract_mismatch WARNING.
#
# [변경 시 영향]
#   - required_arguments에 새 항목을 추가하면 기존 LLM 출력이 FAIL로 바뀔 수 있음.
#   - optional_arguments에서 항목을 제거하면 해당 인수를 쓰는 기존 plan이
#     tool_contract_mismatch 경고를 받게 됨.
#   - 새 tool을 추가할 때 ALLOWED_TOOLS 목록도 함께 업데이트해야 함.
#
# [교육용 가상 시나리오 기준]
#   아래 모든 contract은 DisplayEdu Fab 가상 시나리오 전용 MCP 도구 명세이며
#   실제 설비 API 스펙이 아닙니다.
#
#   required_arguments       : 모두 있어야 함
#   any_of_required_arguments: 이 중 하나 이상 있어야 함
#   optional_arguments       : 있어도 되고 없어도 됨
#   contract에 정의되지 않은 argument 사용은 tool_contract_mismatch
# ---------------------------------------------------------------------------
TOOL_CONTRACTS = {
    # -----------------------------------------------------------------------
    # get_equipment_status
    # -----------------------------------------------------------------------
    # [담당 업무] 특정 설비 하나의 현재 상태를 실시간으로 조회한다.
    #             설비가 정상(NORMAL)인지, 경보(ALARM)인지, 정지(STOP) 상태인지
    #             파악하는 가장 기본적인 첫 번째 조회 도구.
    #
    # [언제 선택] 사용자 질문에 "현재 설비 상태", "설비가 정상인지",
    #             "설비 상태 코드", "지금 돌아가고 있는지" 등의 표현이 있을 때.
    #
    # [언제 선택하면 안 되는지]
    #   - 조치 절차나 매뉴얼을 원하는 경우 → search_manual 사용
    #   - 품질 수치(불량률·수율)만 원하는 경우 → get_quality_metrics 사용
    #   - 알람 발생 이력이 필요한 경우 → get_recent_alarm_events 사용
    #
    # [required_arguments]
    #   "equipment_id": 조회할 설비의 고유 식별자 (예: "EQP-CVD-001").
    #                   이 인수 없이는 어떤 설비를 조회할지 특정할 수 없으므로
    #                   반드시 필요하며, 누락 시 FAIL 처리.
    #
    # [any_of_required_arguments] 빈 리스트 → 이 조건은 적용되지 않음.
    #
    # [optional_arguments] 없음 → equipment_id 외 인수는 모두 tool_contract_mismatch.
    "get_equipment_status": {
        "purpose": "특정 설비의 현재 상태를 조회한다.",
        "when_to_use": "현재 설비 상태, 설비 정상 여부, 설비 상태 코드 요청.",
        "when_not_to_use": "조치 절차, 매뉴얼, 품질 수치만 요청한 경우.",
        "required_arguments": ["equipment_id"],
        "any_of_required_arguments": [],
        "optional_arguments": [],
    },
    # -----------------------------------------------------------------------
    # get_recent_alarm_events
    # -----------------------------------------------------------------------
    # [담당 업무] 특정 설비 또는 알람 코드에 해당하는 최근 알람 이력을 조회한다.
    #             알람이 얼마나 자주 발생했는지(빈도), 최근에 어떤 알람이 떴는지
    #             파악할 때 사용하는 이력 조회 도구.
    #
    # [언제 선택] "최근 알람", "반복 알람", "알람이 몇 번 발생했는지",
    #             "알람 발생 이력", "알람 빈도" 등의 표현이 있을 때.
    #
    # [언제 선택하면 안 되는지]
    #   - 알람 조치 절차나 매뉴얼 근거가 필요한 경우 → search_manual 사용
    #   - 알람의 원인 설명·기술 문서만 원하는 경우 → search_manual 사용
    #   - 현재 설비 상태(NORMAL/ALARM 등)만 원하는 경우 → get_equipment_status 사용
    #
    # [required_arguments]
    #   "equipment_id": 알람 이력을 조회할 설비의 고유 식별자.
    #                   설비를 특정하지 않으면 어떤 설비의 이력인지 알 수 없으므로 필수.
    #
    # [any_of_required_arguments] 빈 리스트 → 이 조건은 적용되지 않음.
    #
    # [optional_arguments]
    #   "alarm_code": 특정 알람 코드(예: "ALM-0042")로 이력을 좁혀 조회할 때 사용.
    #                 생략하면 해당 설비의 모든 알람 유형 이력을 반환.
    #   "limit"     : 반환할 최대 알람 건수. 생략하면 서버 기본값(보통 10~20건) 사용.
    "get_recent_alarm_events": {
        "purpose": "특정 설비 또는 알람 코드의 최근 알람 이력을 조회한다.",
        "when_to_use": "최근 알람, 반복 알람, 알람 발생 이력, 알람 빈도 확인 요청.",
        "when_not_to_use": "조치 절차, 매뉴얼, 원인 설명, 기술 문서 근거만 요청한 경우.",
        "required_arguments": ["equipment_id"],
        "any_of_required_arguments": [],
        "optional_arguments": ["alarm_code", "limit"],
    },
    # -----------------------------------------------------------------------
    # get_process_status
    # -----------------------------------------------------------------------
    # [담당 업무] 특정 공정(process) 또는 생산 라인(line)의 현재 상태를 조회한다.
    #             단일 설비가 아닌 공정 단위·라인 단위의 상태를 확인할 때 사용.
    #
    # [언제 선택] "공정 상태", "라인 상태", "CVD 공정 현황",
    #             "EDU-LINE-A 라인이 정상인지" 등의 표현이 있을 때.
    #
    # [언제 선택하면 안 되는지]
    #   - 단일 설비의 상태만 원하는 경우 → get_equipment_status 사용
    #   - 알람 이력만 원하는 경우 → get_recent_alarm_events 사용
    #
    # [required_arguments] 빈 리스트 → 단독 필수 인수 없음.
    #
    # [any_of_required_arguments]
    #   "process_name": 조회할 공정 이름 (예: "CVD", "ETCH", "CMP").
    #   "line_id"     : 조회할 라인 식별자 (예: "EDU-LINE-A").
    #   둘 중 하나 이상은 반드시 제공해야 어떤 공정/라인인지 특정 가능.
    #   둘 다 없으면 "missing_any_of_required" FAIL 발생.
    #
    # [optional_arguments]
    #   "equipment_id": 공정/라인 내 특정 설비로 범위를 좁힐 때 사용 (선택적).
    #   "limit"       : 반환할 최대 항목 수 (선택적).
    "get_process_status": {
        "purpose": "특정 공정 또는 라인의 현재 상태를 조회한다.",
        "when_to_use": "공정 상태, 라인 상태, 제조 공정 흐름 상태 요청.",
        "when_not_to_use": "단일 설비 상태나 알람 이력만 요청한 경우.",
        "required_arguments": [],
        "any_of_required_arguments": ["process_name", "line_id"],
        "optional_arguments": ["equipment_id", "limit"],
    },
    # -----------------------------------------------------------------------
    # get_quality_metrics
    # -----------------------------------------------------------------------
    # [담당 업무] 품질 지표(불량률, 수율, 검사 결과 등)를 조회한다.
    #             제품 품질 데이터를 수치로 확인하고 싶을 때 사용.
    #
    # [언제 선택] "품질", "불량률", "수율", "검사 결과",
    #             "품질 지표", "yield" 등의 표현이 있을 때.
    #
    # [언제 선택하면 안 되는지]
    #   - 설비 상태(NORMAL/ALARM 등)만 원하는 경우 → get_equipment_status 사용
    #   - 알람 이력만 원하는 경우 → get_recent_alarm_events 사용
    #
    # [required_arguments] 빈 리스트 → 단독 필수 인수 없음.
    #
    # [any_of_required_arguments]
    #   "metric_name" : 조회할 품질 지표 이름 (예: "defect_rate", "yield").
    #   "equipment_id": 특정 설비의 품질 지표를 조회할 때 사용.
    #   "line_id"     : 특정 라인의 품질 지표를 조회할 때 사용.
    #   셋 중 하나 이상 제공해야 어떤 품질 데이터인지 특정 가능.
    #   모두 없으면 "missing_any_of_required" FAIL 발생.
    #
    # [optional_arguments]
    #   "date_range": 조회 기간 범위 (예: "last_7_days", "2025-05-01~2025-05-31").
    #                 생략 시 서버 기본 기간 사용.
    #   "limit"     : 반환할 최대 결과 건수 (선택적).
    "get_quality_metrics": {
        "purpose": "품질 지표, 불량률, 수율, 검사 결과를 조회한다.",
        "when_to_use": "품질, 불량률, 수율, 검사 결과, 품질 지표 요청.",
        "when_not_to_use": "설비 상태나 알람 이력만 요청한 경우.",
        "required_arguments": [],
        "any_of_required_arguments": ["metric_name", "equipment_id", "line_id"],
        "optional_arguments": ["date_range", "limit"],
    },
    # -----------------------------------------------------------------------
    # get_maintenance_history
    # -----------------------------------------------------------------------
    # [담당 업무] 설비 정비 이력, 보전 이력, 부품 교체 이력을 조회한다.
    #             "언제 마지막으로 점검했는가", "어떤 부품을 교체했는가"를
    #             파악할 때 사용하는 이력 조회 도구.
    #
    # [언제 선택] "정비 이력", "보전 이력", "PM 이력", "부품 교체 기록",
    #             "마지막 점검 일자" 등의 표현이 있을 때.
    #
    # [언제 선택하면 안 되는지]
    #   - 현재 설비 상태(실시간)만 원하는 경우 → get_equipment_status 사용
    #   - 품질 수치만 원하는 경우 → get_quality_metrics 사용
    #
    # [required_arguments]
    #   "equipment_id": 정비 이력을 조회할 설비의 고유 식별자.
    #                   어떤 설비의 이력인지 반드시 특정해야 하므로 필수.
    #                   누락 시 "missing_required_argument" FAIL 발생.
    #
    # [any_of_required_arguments] 빈 리스트 → 이 조건은 적용되지 않음.
    #
    # [optional_arguments]
    #   "date_range": 조회할 정비 이력의 기간 범위 (선택적).
    #                 생략 시 최근 일정 기간의 전체 이력 반환.
    #   "part_replaced": 교체 또는 정비 대상 부품명으로 이력을 좁혀 조회할 때 사용 (선택적).
    #                    예: "pump", "filter", "heater".
    #                    (실제 정비 이력 테이블의 'part_replaced' 컬럼 의미에 맞춘 이름이다.
    #                     교육용 Contract argument 와 DB 컬럼 의미를 일치시켜 혼란을 줄인다.)
    "get_maintenance_history": {
        "purpose": "설비 정비 이력, 보전 이력, 부품 교체 이력을 조회한다.",
        "when_to_use": "정비 이력, 보전 이력, 부품 교체 기록 요청.",
        "when_not_to_use": "현재 상태나 품질 수치만 요청한 경우.",
        "required_arguments": ["equipment_id"],
        "any_of_required_arguments": [],
        "optional_arguments": ["date_range", "part_replaced"],
    },
    # -----------------------------------------------------------------------
    # get_equipment_overview
    # -----------------------------------------------------------------------
    # [담당 업무] 특정 설비의 요약 정보(개요)를 조회한다.
    #             설비의 기본 정보(설비 유형, 설치 일자, 담당 공정 등 요약)를
    #             한 번에 확인하고 싶을 때 사용.
    #             get_equipment_status(실시간 상태)와 달리 정적 메타정보 중심.
    #
    # [언제 선택] "설비 개요", "설비 요약", "설비 기본 정보",
    #             "설비 스펙 요약" 등의 표현이 있을 때.
    #
    # [언제 선택하면 안 되는지]
    #   - 세부 알람 발생 이력이 필요한 경우 → get_recent_alarm_events 사용
    #   - 정비·부품 교체 이력이 필요한 경우 → get_maintenance_history 사용
    #   - 실시간 상태 코드가 필요한 경우 → get_equipment_status 사용
    #
    # [required_arguments]
    #   "equipment_id": 개요를 조회할 설비의 고유 식별자. 반드시 필요.
    #                   누락 시 "missing_required_argument" FAIL 발생.
    #
    # [any_of_required_arguments] 빈 리스트 → 이 조건은 적용되지 않음.
    #
    # [optional_arguments] 없음 → equipment_id 외 인수는 모두 tool_contract_mismatch.
    "get_equipment_overview": {
        "purpose": "특정 설비의 요약 정보 또는 개요를 조회한다.",
        "when_to_use": "설비 개요, 설비 요약, 설비 기본 정보 요청.",
        "when_not_to_use": "세부 알람 이력이나 정비 이력만 요청한 경우.",
        "required_arguments": ["equipment_id"],
        "any_of_required_arguments": [],
        "optional_arguments": [],
    },
    # -----------------------------------------------------------------------
    # search_manual
    # -----------------------------------------------------------------------
    # [담당 업무] 기술 문서, 알람 조치 절차, 트러블슈팅 근거를 전문 검색한다.
    #             벡터 유사도 기반 RAG 검색 도구로, "어떻게 대처해야 하는가",
    #             "왜 이 알람이 발생하는가"에 대한 절차·근거 문서를 찾을 때 사용.
    #             DB 조회 도구들과 달리 '절차 근거' 제공이 목적.
    #
    # [언제 선택] "매뉴얼", "조치 절차", "원인 후보", "기술 문서",
    #             "근거 문서", "트러블슈팅", "대처 방법" 등의 표현이 있을 때.
    #
    # [언제 선택하면 안 되는지]
    #   - 단순 알람 발생 이력만 필요한 경우 → get_recent_alarm_events 사용
    #   - 설비 상태 수치만 필요한 경우 → get_equipment_status 사용
    #   - 품질 지표 수치만 필요한 경우 → get_quality_metrics 사용
    #
    # [required_arguments]
    #   "query": 검색할 자연어 질의문 (예: "ALM-0042 알람 조치 절차").
    #            벡터 DB에서 유사 문서를 찾는 검색 키워드 역할이므로 반드시 필요.
    #            누락 시 "missing_required_argument" FAIL 발생.
    #
    # [any_of_required_arguments] 빈 리스트 → 이 조건은 적용되지 않음.
    #
    # [optional_arguments]
    #   "alarm_code"    : 특정 알람 코드(예: "ALM-0042")로 검색 범위를 좁힐 때 사용.
    #                     생략 시 query 전문 검색으로만 결과 반환.
    #   "equipment_type": 특정 설비 유형(예: "CVD", "ETCH")으로 문서 필터링 시 사용.
    #                     생략 시 모든 설비 유형의 문서를 대상으로 검색.
    "search_manual": {
        "purpose": "기술 문서, 알람 조치 절차, 트러블슈팅 근거를 검색한다.",
        "when_to_use": "매뉴얼, 조치 절차, 원인 후보, 기술 문서, 근거 문서 요청.",
        "when_not_to_use": "단순 알람 이력, 설비 상태, 품질 수치만 요청한 경우.",
        "required_arguments": ["query"],
        "any_of_required_arguments": [],
        "optional_arguments": ["alarm_code", "equipment_type"],
    },
}


# [역할] validation 결과의 심각도(severity) 수준을 숫자로 매핑하는 순서 기준표.
#        validator가 복수의 issue를 집계할 때 '가장 심각한' severity 하나를
#        최종 판정으로 채택하기 위해 사용.
#
# [사용 단계] validator 및 quality_gate_runner 단계에서 참조.
#   - validator : 각 plan item의 issue severity 중 최대값을 plan 전체 severity로 결정.
#   - quality_gate_runner: 전체 케이스 결과를 집계하여 PASS/CONDITIONAL_PASS/HOLD 결정.
#
# [각 severity 의미]
#   "PASS"        (0): 검증 문제 없음. Tool 이름·인수 모두 contract에 부합.
#   "WARNING"     (1): 경미한 불일치. 실행은 가능하지만 개선 권고.
#                      예: weak_reason(이유 설명 부족), tool_contract_mismatch(불필요 인수 포함).
#   "FAIL"        (2): 명백한 오류. 실행하면 안 되거나 실행 불가.
#                      예: unknown_tool(허용 목록 외 tool), missing_required_argument.
#   "NEEDS_REVIEW"(3): 자동 판정 불가, 사람이 직접 확인 필요.
#                      예: 논리적으로 불합리하지만 기술적으로는 오류가 아닌 경우.
#
# [판단 기준] 숫자가 클수록 더 심각. max(severity 목록) → 최종 severity 결정.
#
# [변경 시 영향]
#   severity 이름을 바꾸거나 숫자를 재조정하면 quality_gate_runner의
#   PASS/CONDITIONAL_PASS/HOLD 경계값도 함께 수정해야 한다.
#   Mustache 리포트 템플릿에서 severity 이름을 직접 비교하는 부분도 확인 필요.
#
# [교육용 가상 시나리오 기준]
#   이 4단계 severity 체계는 day4 교육 파이프라인 전용 설계이며
#   실 운영 품질 관리 시스템의 등급 체계가 아닙니다.
# severity 순서 (PASS < WARNING < FAIL < NEEDS_REVIEW)
SEVERITY_ORDER = {
    "PASS": 0,           # 문제 없음 — contract 완전 부합
    "WARNING": 1,        # 경고 — 실행 가능하나 개선 권고 (예: weak_reason, 불필요 인수)
    "FAIL": 2,           # 실패 — 실행 불가 또는 명백한 오류 (예: unknown_tool, 필수 인수 누락)
    "NEEDS_REVIEW": 3,   # 검토 필요 — 자동 판정 불가, 사람이 직접 확인 요망
}
