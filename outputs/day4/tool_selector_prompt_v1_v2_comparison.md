# Tool Selector Prompt v1/v2 Comparison

## 1. Purpose

v1은 안정적인 Tool 선택을 위한 프롬프트이고,
v2는 Tool Plan 생성을 위한 프롬프트이다.

- v1 (`llm_tool_selection_prompt_v1_simple.mustache`): 사용자 질문을 읽고 필요한 **Tool 이름만** 고른다.
- v2 (`llm_tool_selection_prompt_v2_tool_plan.mustache`): Tool 이름뿐 아니라 **호출 순서·arguments·condition·reason**까지 포함한 실행 계획(Tool Plan)을 만든다.

## 2. Comparison

| 항목 | v1 simple | v2 tool plan |
|---|---|---|
| 목적 | Tool 이름 선택 | 실행 계획 생성 |
| 출력 | selected_tools | plan |
| arguments | 없음 | 있음 |
| condition | 없음 | 있음 |
| reason | 없음 | 있음 |
| 호출 순서 | 없음 | 있음 |
| 안정성 | 높음 | 중간 |
| 설명 가능성 | 낮음 | 높음 |
| 평가 방식 | expected_tools 비교 | Tool, arguments, step, condition, reason 평가 |
| Trace 연결 | 약함 | 강함 |
| Final Agent 연결 | 약함 | 강함 |

## 3. Teaching Point

v1은 Tool 선택 정확도 평가에 적합하고,
v2는 Agent 실행 흐름, 조건부 실행, Trace 평가에 적합하다.

SQL 또는 DB 실행이 포함된 요청에서는 v2에서 `check_text_to_sql_safety`가 DB 실행보다 먼저 계획되어야 한다.
하지만 고정 DB Tool로 처리 가능한 단순 조회에는 Safety Tool을 과잉 호출하지 않는다.

- v2의 `condition` 필드는 "이 Tool을 언제 실행할지"를 자연어로 적는 **계획 설명**이며, 실행 코드가 아니다.
  대표 예: `"always"`, `"run only if check_text_to_sql_safety.actual_status is PASS"`.
- v2는 Text-to-SQL 생성기가 아니라 **Tool Plan 생성기**다. SQL이 아직 없으면 `generated_sql`을 `null`로 두고 reason에 사유를 적는다.

## 4. Recommended Usage

- 4일차 초반: v1으로 Tool 선택 정확도 평가
- 4일차 후반: v2로 Tool Plan, condition, Safety 분기 평가
- 5일차: v2 구조를 Final Agent와 LangGraph 분기 설계에 연결

## 5. Caution

These templates are added for comparison and teaching.
The current `src/day4/llm_tool_selector.py` may still use the original `templates/day4/llm_tool_selection_prompt.mustache`.
To use v1 or v2 in execution, the selector code must be extended later to choose a template version.

## 6. 실측 발견 — 기본 Batch vs LLM Batch (Text-to-SQL Safety)

`src/day4/text_to_sql_safety_checker.py`의 두 모드를 같은 `data/day4_text_to_sql_cases.json`로 비교한 결과입니다.

- 기본 Batch: dataset에 사람이 넣어 둔 `generated_sql`을 그대로 검사.
- `--llm-batch`: 같은 `user_query`를 실제 LLM(NVIDIA, `stepfun-ai/step-3.5-flash`)에 보내 **새 SQL을 생성**해 검사.

### 6.1 실측 수치 (실제 LLM 16/16 호출 성공, fallback 0)

| 구분 | PASS | WARNING | BLOCK | 기대 일치 | 비고 |
|---|---|---|---|---|---|
| 기본 Batch (dataset SQL) | 2 | 3 | 11 | 16/16 | 사람이 만든 위험 SQL을 그대로 검사 |
| LLM Batch (LLM 생성 SQL) | 6 | 7 | 3 | 5/16 | LLM이 만든 SQL을 검사 |

> 타임아웃 30초에서는 느린 호출이 timeout→mock fallback으로 빠졌으나, `TEXT_TO_SQL_LLM_TIMEOUT`을 120초로 올린 뒤 16/16 모두 실제 LLM 호출에 성공했습니다.

### 6.2 핵심 발견

- **불일치 11건은 Safety Checker 결함이 아니다.** `expected_status`는 dataset의 위험 SQL 기준인데, LLM은 위험 요청(DELETE/DROP/INSERT/UPDATE/민감 컬럼/일부 injection)에 대해 **위험 SQL을 만들지 않고 양성 SELECT로 바꿔** 생성했다. 그래서 Checker가 그 양성 SQL을 PASS/WARNING으로 정확히 판정한 것이다.
  - 예: `SQL-BLOCK-002~005`(UPDATE/INSERT/DROP/민감) → LLM은 양성 SELECT 생성 → PASS.
  - 예: `SQL-SAFE-001` → LLM이 `SELECT *` + 다른 컬럼명 생성 → WARNING.
- **그렇다고 LLM의 거부에 의존하면 안 된다.** 어떤 SQL이 나오든 Safety Checker를 반드시 통과시켜야 하며, 위험 SQL이 실제로 생성되면 BLOCK된다(`--sql "...; DROP TABLE ...;"` → BLOCK으로 확인).
- LLM은 종종 **다른 스키마(컬럼/테이블)명**(`created_at`, `line_name`, `recorded_at` 등)을 생성한다 → 안전성은 통과해도 **실행 정확성은 별개** 문제다.
- `--llm-batch`는 `llm_used_count`/`llm_fallback_count`로 **실제 LLM 결과인지 mock fallback인지 투명하게 구분**한다.

### 6.3 수업 포인트

- 기본 Batch는 "사람이 만든 SQL"을, LLM Batch는 "모델이 만든 SQL"을 검사한다 — 모델/프롬프트가 바뀌면 결과도 달라진다.
- 안전성 판정은 **생성 주체와 무관하게 Safety Checker가 출력 SQL 자체에 대해** 수행해야 한다.
- 타임아웃 같은 운영 파라미터가 "실제 LLM 테스트인지 mock fallback인지"를 좌우할 수 있으므로, fallback 카운트를 항상 확인해야 한다.
