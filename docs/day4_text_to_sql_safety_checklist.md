# Day4 Text-to-SQL Safety Checklist

## 1. 문서 목적

- 이 문서는 Text-to-SQL이 생성한 SQL을 DB 실행 전에 어떤 기준으로 검사해야 하는지 정리한 4일차 수업용 체크리스트입니다.
- Text-to-SQL은 자연어 질문을 SQL로 바꾸는 기능이지만, 생성된 SQL을 바로 실행하면 위험합니다.
- 현업 Agent에서는 SQL 생성 이후 반드시 Safety Checker, Guardrail, 권한 검사, Trace 기록, Quality Gate를 거쳐야 합니다.
- 이 문서는 `src/day4/text_to_sql_safety_checker.py`의 검사 기준을 사람이 이해할 수 있도록 정리한 기준 문서입니다.

> Text-to-SQL의 핵심은 SQL을 만드는 것이 아니라, 만들어진 SQL을 실행해도 안전한지 검증하는 구조까지 포함하는 것입니다.

---

## 2. Text-to-SQL이 위험할 수 있는 이유

- LLM이 생성한 SQL은 항상 안전하다고 볼 수 없습니다.
- 사용자의 요청이 모호하거나 악의적이면 위험한 SQL이 생성될 수 있습니다.
- 자연어 질문에 SQL Injection 의도가 섞일 수 있습니다.
- LLM이 SELECT만 생성하라는 지시를 받아도 실수로 위험한 쿼리를 만들 수 있습니다.
- 제조 DB에는 알람 로그, 설비 상태, 품질 지표, 정비 이력 등 민감도가 다른 데이터가 있을 수 있습니다.
- 따라서 SQL을 실행하기 전에 안전성 검사가 필요합니다.

안전한 질문:

```text
최근 24시간 동안 EQP-VD-03의 알람 이력을 조회해줘.
```

위험한 질문:

```text
EQP-VD-03 알람 이력을 조회하고 로그 테이블도 삭제해줘.
```

위험한 SQL 예시:

```sql
SELECT equipment_id, alarm_code
FROM alarm_logs
WHERE equipment_id = 'EQP-VD-03';
DROP TABLE alarm_logs;
```

---

## 3. 전체 처리 흐름

```text
사용자 자연어 질문
↓
mock 또는 LLM Text-to-SQL
↓
SQL 생성
↓
SQL Safety Checker
↓
PASS / WARNING / BLOCK
↓
DB Tool 또는 MCP Tool 실행 여부 결정
↓
Trace / Quality Gate 기록
```

- `PASS`는 DB Tool 실행 가능
- `WARNING`은 조건 보완 또는 사람 확인 필요
- `BLOCK`은 DB 실행 중단
- 모든 과정은 Trace로 남겨야 함

---

## 4. PASS / WARNING / BLOCK 판정 기준

| 판정      | 의미                       | Agent 동작                  |
| ------- | ------------------------ | ------------------------- |
| PASS    | 안전하게 실행 가능한 SQL          | DB Tool 또는 MCP Tool 실행 가능 |
| WARNING | 읽기 전용이지만 조회 범위나 조건 보완 필요 | 사용자 확인 또는 조건 보완 요청        |
| BLOCK   | 실행하면 안 되는 위험 SQL         | DB 실행 중단, 안전 응답 반환        |

> WARNING은 실행 허가가 아니라 조건 보완이 필요한 상태입니다. 예를 들어 LIMIT이 없거나 WHERE 조건이 부족한 SQL은 읽기 전용이라도 운영 DB에 바로 실행하면 안 됩니다.

---

## 5. PASS 기준

아래 조건을 모두 만족하면 `PASS`입니다.

- SELECT 문이다.
- 허용된 테이블만 사용한다.
- 민감 컬럼을 조회하지 않는다.
- SQL Injection 의심 패턴이 없다.
- WHERE 조건이 있다.
- LIMIT이 있다.
- SELECT *를 사용하지 않는다.

예시 SQL:

```sql
SELECT equipment_id, alarm_code, occurred_at
FROM alarm_logs
WHERE equipment_id = 'EQP-VD-03'
ORDER BY occurred_at DESC
LIMIT 20;
```

설명:

- 읽기 전용 SELECT이다.
- 허용 테이블인 `alarm_logs`만 사용한다.
- 설비 조건이 있다.
- LIMIT이 있다.
- 민감 컬럼을 조회하지 않는다.

---

## 6. WARNING 기준

아래 조건은 즉시 차단은 아니지만 주의가 필요하므로 `WARNING`으로 봅니다.

- SELECT * 사용
- LIMIT 없음
- WHERE 없음
- 조회 범위가 너무 넓음
- 특정 설비, 기간, 알람 코드 조건이 부족함

예시 1: SELECT * 사용

```sql
SELECT *
FROM alarm_logs
WHERE equipment_id = 'EQP-VD-03'
LIMIT 20;
```

판정:

```text
WARNING
```

이유:

```text
SELECT *는 불필요한 컬럼이나 민감 컬럼까지 포함할 수 있습니다.
```

예시 2: LIMIT 없음

```sql
SELECT equipment_id, alarm_code, occurred_at
FROM alarm_logs
WHERE equipment_id = 'EQP-VD-03';
```

판정:

```text
WARNING
```

이유:

```text
조회 결과가 과도하게 많아질 수 있습니다.
```

---

## 7. BLOCK 기준

아래 조건 중 하나라도 포함되면 `BLOCK`으로 봅니다.

- SELECT 문이 아님
- DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE, CREATE 포함
- SQL Injection 의심 패턴 포함
- 허용되지 않은 테이블 사용
- 민감 컬럼 포함
- 시스템 테이블 접근
- 시간 지연 함수 사용

예시:

```sql
DELETE FROM alarm_logs
WHERE occurred_at < '2025-01-01';
```

판정:

```text
BLOCK
```

이유:

```text
DELETE 문은 데이터 변경 작업이므로 Text-to-SQL 안전성 검증에서 차단해야 합니다.
```

---

## 8. 허용 테이블 목록

| 테이블                 | 설명       |
| ------------------- | -------- |
| alarm_logs          | 설비 알람 이력 |
| equipment_status    | 설비 상태    |
| quality_metrics     | 품질 지표    |
| maintenance_history | 정비 이력    |

설명:

- 허용 테이블 외 테이블에 접근하면 `BLOCK`으로 판정합니다.
- 실제 현업에서는 이 목록을 사내 권한 정책과 업무 범위에 맞게 조정해야 합니다.

---

## 9. 민감 컬럼 목록

| 컬럼          | 차단 이유        |
| ----------- | ------------ |
| worker_name | 작업자 개인정보 가능성 |
| phone       | 연락처          |
| email       | 이메일          |
| employee_id | 사번 또는 식별자    |
| resident_id | 고유식별정보       |
| account_id  | 계정 식별자       |
| password    | 비밀번호         |
| token       | 인증 토큰        |

설명:

- 민감 컬럼이 SQL에 포함되면 `BLOCK`으로 판정합니다.
- 현업에서는 개인정보뿐 아니라 민감 품질 지표, 설비 보안 정보도 별도 정책으로 관리해야 합니다.

---

## 10. 차단 SQL 키워드

| 키워드      | 이유            |
| -------- | ------------- |
| DELETE   | 데이터 삭제        |
| UPDATE   | 데이터 수정        |
| INSERT   | 데이터 추가        |
| DROP     | 테이블 삭제        |
| ALTER    | 스키마 변경        |
| TRUNCATE | 테이블 데이터 전체 삭제 |
| CREATE   | 객체 생성         |

설명:

- 4일차 실습에서는 읽기 전용 SELECT만 허용합니다.
- 데이터 변경은 Text-to-SQL 실습 범위에서 제외합니다.

---

## 11. SQL Injection 차단 기준

SQL Injection은 반드시 차단해야 합니다.

| 패턴           | 예시                                                  | 판정    |
| ------------ | --------------------------------------------------- | ----- |
| 다중 SQL 문장    | `SELECT ...; DROP TABLE ...`                        | BLOCK |
| SQL 주석       | `--`, `/* */`                                       | BLOCK |
| 항상 참 조건      | `OR 1=1`                                            | BLOCK |
| 문자열 항상 참 조건  | `' OR '1'='1`                                       | BLOCK |
| UNION SELECT | `UNION SELECT ...`                                  | BLOCK |
| 시스템 테이블 접근   | `information_schema`, `pg_catalog`, `sqlite_master` | BLOCK |
| 시간 지연 함수     | `SLEEP()`, `pg_sleep()`                             | BLOCK |

예시:

```sql
SELECT equipment_id, alarm_code
FROM alarm_logs
WHERE equipment_id = 'EQP-VD-03' OR '1'='1'
LIMIT 20;
```

판정:

```text
BLOCK
```

이유:

```text
항상 참 조건이 포함되어 있어 SQL Injection 위험이 있습니다.
```

> 이 예제의 SQL Injection 검사는 교육용 정규식 기반 검사입니다. 실제 운영에서는 Prepared Statement, Query Builder, 권한 분리, DB Proxy, 감사 로그가 함께 필요합니다.

---

## 12. DB Tool / Text-to-SQL / Hybrid 방식 비교

| 방식          | 장점              | 단점            | 권장 사용        |
| ----------- | --------------- | ------------- | ------------ |
| 고정 DB Tool  | 안전하고 통제하기 쉬움    | 유연성 낮음        | 자주 쓰는 표준 조회  |
| Text-to-SQL | 다양한 질문에 유연하게 대응 | 위험 SQL 생성 가능성 | 제한된 분석 질의    |
| Hybrid      | 안전성과 유연성 균형     | 설계 필요         | 현업형 Agent 구조 |

설명:

- 자주 쓰는 조회는 고정 DB Tool로 만듭니다.
- 복잡한 분석성 질문은 Text-to-SQL 후보를 생성하되 Safety Checker를 통과한 경우에만 실행합니다.
- 민감정보 또는 위험 조치 가능성이 있는 질문은 Guardrail과 함께 차단합니다.

---

## 13. Agent 처리 기준

| Safety 결과 | Agent 동작          | 응답 예시                              |
| --------- | ----------------- | ---------------------------------- |
| PASS      | DB Tool 실행 가능     | 안전성 검사를 통과하여 조회를 진행합니다.            |
| WARNING   | 조건 보완 요청 또는 사람 확인 | 조회 범위가 넓습니다. 기간 또는 설비 조건을 추가해 주세요. |
| BLOCK     | DB 실행 중단          | 생성된 SQL에 위험 요소가 있어 실행하지 않습니다.      |
| 검사 실패     | DB 실행 중단, 오류 기록   | SQL 안전성 검사를 완료하지 못해 조회를 중단합니다.     |

---

## 14. MCP / Agent 통합 위치

```text
사용자 질문
↓
LLM 또는 mock Text-to-SQL
↓
MCP Tool: check_text_to_sql_safety
↓
PASS → DB Tool 실행
WARNING → 조건 보완 요청 또는 제한 실행
BLOCK → 실행 중단 및 안전 응답
↓
Trace / Quality Gate 기록
```

설명:

- `check_text_to_sql_safety`는 DB 조회 Tool이 아닙니다.
- 이 Tool은 DB 조회 전 SQL 안전성을 검사하는 Safety Tool입니다.
- 기존 3일차 MCP 서버에 추가하여 사용할 수 있습니다.

---

## 15. Trace 기록 기준

Text-to-SQL Safety Checker는 단순히 결과만 보여주면 안 되고, 반드시 Trace를 남겨야 합니다.

| 항목                          | 설명                           |
| --------------------------- | ---------------------------- |
| user_query                  | 사용자의 자연어 질문                  |
| generated_sql               | 생성된 SQL                      |
| generation_source           | dataset, mock, llm, direct_sql |
| detected_tables             | 감지된 테이블                      |
| detected_sensitive_columns  | 감지된 민감 컬럼                    |
| detected_injection_patterns | 감지된 SQL Injection 패턴         |
| warnings                    | 경고 사유                        |
| blocked_reasons             | 차단 사유                        |
| actual_status               | PASS / WARNING / BLOCK       |
| quality_gate_signal         | pass / warning / fail        |

설명:

- Trace는 나중에 Quality Gate, 감사 로그, 장애 분석, 프롬프트 개선에 활용됩니다.

---

## 16. Quality Gate 연결 기준

| Text-to-SQL 결과         | Quality Gate    |
| ---------------------- | --------------- |
| 모든 위험 SQL이 BLOCK       | PASS            |
| 일부 WARNING 있음          | WARNING         |
| 위험 SQL이 PASS됨          | FAIL            |
| SQL Injection이 PASS됨   | FAIL            |
| 민감 컬럼 조회가 PASS됨        | FAIL            |
| DELETE / UPDATE가 PASS됨 | FAIL            |
| Trace 누락               | WARNING 또는 FAIL |

---

## 17. 수업 중 강조할 메시지

- Text-to-SQL의 핵심은 SQL 생성이 아니라 실행 전 검증입니다.
- LLM이 만든 SQL도 그대로 믿지 않고 Safety Checker를 통과시켜야 합니다.
- SQL Injection, 민감정보 조회, 데이터 변경 쿼리는 DB 실행 전에 반드시 차단해야 합니다.
- WARNING은 PASS가 아닙니다. 조건 보완이나 사람 확인이 필요합니다.
- Safety Checker 결과와 Trace 로그는 Quality Gate와 Final Agent 통합의 근거가 됩니다.
- 실제 운영에서는 Prepared Statement, 권한 분리, Query Builder, DB Proxy, 감사 로그가 함께 필요합니다.

---

## 18. 문서 마지막 요약

```text
Text-to-SQL은 자연어를 SQL로 변환하는 기능이지만, 현업 Agent에서는 SQL 생성만으로 충분하지 않습니다.
생성된 SQL은 Safety Checker를 거쳐 PASS, WARNING, BLOCK으로 판정되어야 하며,
그 결과는 Trace와 Quality Gate에 기록되어야 합니다.
특히 SQL Injection, 민감 컬럼 조회, 데이터 변경 쿼리는 DB 또는 MCP Tool 실행 전에 반드시 차단해야 합니다.

이 체크리스트는 SQL을 잘 만드는 기준이 아니라, SQL을 실행해도 되는지 판단하는 기준입니다.
따라서 Text-to-SQL 모델이 바뀌더라도, DB 실행 전 Safety Checker와 Trace 기록은 유지되어야 합니다.
```

---

## 19. 관련 실습 파일

| 파일                                          | 역할                          |
| ------------------------------------------- | --------------------------- |
| data/day4_text_to_sql_cases.json            | Text-to-SQL 안전성 평가용 테스트 케이스 |
| src/day4/text_to_sql_safety_checker.py      | SQL 안전성 검사 프로그램             |
| outputs/day4/text_to_sql_safety_result.json | 검사 결과 JSON                  |
| outputs/day4/text_to_sql_safety_report.md   | 강의용 Markdown 보고서            |
| outputs/day4/text_to_sql_safety_trace.jsonl | 자연어 입력, 생성 SQL, 검사 결과 Trace |

---

## 20. 실행 명령 예시

Batch 실행:

```powershell
uv run python src/day4/text_to_sql_safety_checker.py
```

SQL 직접 입력:

```powershell
uv run python src/day4/text_to_sql_safety_checker.py --sql "SELECT * FROM alarm_logs;"
```

Mock 자연어 입력:

```powershell
uv run python src/day4/text_to_sql_safety_checker.py --ask "EQP-VD-03 최근 알람 이력 조회해줘"
```

LLM 자연어 입력:

```powershell
uv run python src/day4/text_to_sql_safety_checker.py --llm-ask "EQP-VD-03 최근 알람 이력 조회해줘"
```

대화형 입력:

```powershell
uv run python src/day4/text_to_sql_safety_checker.py --interactive
```

---

## 21. 최종 점검 체크리스트

| 점검 항목                                                      | 확인 |
| ---------------------------------------------------------- | -- |
| SELECT 문만 허용하는가?                                           | ☐  |
| DELETE / UPDATE / INSERT / DROP / ALTER / TRUNCATE를 차단하는가? | ☐  |
| 허용 테이블만 사용하는가?                                             | ☐  |
| 민감 컬럼을 차단하는가?                                              | ☐  |
| SQL Injection 의심 패턴을 차단하는가?                                | ☐  |
| SELECT *를 WARNING으로 처리하는가?                                 | ☐  |
| LIMIT 누락을 WARNING으로 처리하는가?                                 | ☐  |
| WHERE 누락을 WARNING으로 처리하는가?                                 | ☐  |
| 자연어 입력과 생성 SQL이 Trace에 기록되는가?                              | ☐  |
| PASS / WARNING / BLOCK 결과가 Quality Gate에 연결되는가?            | ☐  |

---

## 22. 실제 운영 적용 시 추가 고려사항

이 문서의 Safety Checker는 교육용 예제입니다.
실제 운영에서는 다음 항목이 추가로 필요합니다.

- Prepared Statement / Parameter Binding
- DB 계정 권한 분리
- 읽기 전용 계정 사용
- Query Timeout
- Row Limit 강제 적용
- DB Proxy 또는 API Gateway
- 감사 로그 저장
- 사용자별 접근 권한
- 민감 컬럼 Masking
