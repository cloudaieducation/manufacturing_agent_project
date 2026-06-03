# Day5 통합 계획 — Tool Plan & RAG 보완

> 4일차 Quality Gate가 **HOLD**로 판정된 두 영역(Tool Plan Validation, RAG Quality)을
> 5일차 Final Agent 통합 전에 보완하기 위한 계획 문서입니다.
> 모든 수치는 `uv`(.venv) 환경에서 실제 실행한 4일차 산출물 기준입니다.

## 0. 현재 상태 (왜 HOLD인가)

| 영역 | 상태 | 핵심 수치 | 근본 원인 |
|---|---|---|---|
| Tool Plan Validation | HOLD | 32건 중 PASS 16 / WARN 3 / **FAIL 13**, 인자 누락 13 | 실제 LLM(NVIDIA, real_llm) 선택 결과 기준 검증 — 도구 선택 불일치 + Guardrail 불일치가 남음 |
| RAG Quality | HOLD | 10건 중 PASS 1 / WARN 3 / **FAIL 6** (실제 Chroma, fallback 0) | day2 인덱스가 day4 질의의 키워드/메타데이터를 거의 커버하지 못함 |

관련 산출물:
- `outputs/day4/llm_tool_plan_validation_result.json`
- `outputs/day4/rag_quality_evaluation_result.json`
- `outputs/day4/quality_gate_result.json`

---

## 1. Tool Plan 보완 계획

**진단 (실데이터, 실제 LLM `selector_type=real_llm`, baseline 기준):**
- FAIL 13건의 사유 분포: `MISSING_EXPECTED_TOOL`(6), `EXTRA_UNEXPECTED_TOOL`(5), `GUARDRAIL_MISMATCH`(5), `UNEXPECTED_GUARDRAIL`(1)
  - 즉 **약 6건은 Guardrail 불일치로 도구 설명/선택과 무관**하다(도구 튜닝으로 못 내리는 바닥).
- 자주 누락된 도구: `get_maintenance_history`(3), `get_equipment_status`(2), `get_process_status`(2), `get_quality_metrics`(2)
- 잘못 추가된 도구: `search_manual`(3), `get_recent_alarm_events`(2), `get_quality_metrics`(1)
- 인자 누락(WARNING 레벨): `get_recent_alarm_events`(8), `get_quality_metrics`(3), `get_process_status`(2) — 질문에 `equipment_id`/`alarm_code`가 실제로 없는 정당한 케이스 포함

> 경과 메모:
> - 규칙 기반 대체본(FAIL 17) → 실제 LLM(FAIL 12~13)으로 개선됨.
> - **Tool 설명/가이드 보강을 시도했으나 과선택을 유발해 FAIL 12→15로 악화 → baseline으로 원복**(FAIL 13). 프롬프트 미세조정으로 FAIL을 0으로 만드는 것은 비현실적임을 확인.
> - 실행 간 매칭 수가 19~22로 변동 → LLM tool-selection은 본질적으로 비결정적이며, 이것이 게이트/Trace로 지속 점검해야 하는 이유다.

**5일차 통합 항목 (우선순위 재정렬):**

1. (완료) 실제 LLM Tool Selector 실행 → 진짜 selector 결과로 재검증. 검증기 `input_file` = `llm_tool_plan_results.json`.
2. (완료) Tool Contract(인자 계약) 강화 — `search_manual`에 `query`를 항상 채워 "alarm_code 또는 query" 계약 충족(`build_tool_arguments`). → `search_manual` 인자 누락 5→0.
3. (효과 없음 — 보류) Tool 설명/프롬프트 가이드 보강은 과선택을 유발해 역효과였음. 추가 프롬프트 튜닝은 권장하지 않음.
4. **Guardrail 정합성 점검** (신규 최우선) — FAIL의 ~6건인 Guardrail 불일치를 `check_guardrail` 키워드 vs 케이스의 `expected_guardrail` 정합성 관점에서 해소. (도구와 무관한 확실한 FAIL 감축 레버)
5. Final Agent 분기: 잔여 FAIL 케이스는 실행 대상에서 제외하거나 사람 확인을 거치고, Edge Case 시나리오로 이관한다. (무리한 PASS화 대신 정직한 운영 처리)

**게이트 재통과 조건:** `fail_count = 0`, `missing_argument_count = 0` (단, Guardrail 불일치 해소가 선행되어야 현실적으로 도달 가능)

---

## 2. RAG 보완 계획

**진단 (실데이터, FAIL 6건):**
- 대부분 키워드 0~1/5, 메타데이터 0/2~3 → 인덱스에 해당 문서가 없거나 메타데이터가 부착되지 않음
- 실패 주제: `EQP-VD-03 온도/냉각/센서`, `압력 불안정`, `ALM-3091 품질 지표`, `EQP-CVD-02 압력 계통`, `세정 설비 반복 알람/정비`, `ETCH 불량률/품질`

**5일차 통합 항목:**

1. 인덱스 커버리지 확충: 위 6개 주제 문서를 day2 코퍼스에 추가한 뒤 재인덱싱한다.
2. 메타데이터 스키마 보강: chunk에 `equipment_id`, `alarm_code`, `symptom`, `equipment_type`, `quality_related`, `requires_maintenance_context`를 부착한다. (메타 매칭 0건 문제 해소)
3. 검색 강화: Query Rewrite(예: 압력 불안정 ↔ 진공도 이상 ↔ 챔버 압력 편차), Top-K 3 → 5, 필요 시 Reranker 도입.
4. Final Report 분기: RAG가 WARN/FAIL인 근거는 Final Report에서 "근거 부족 / 추가 확인 필요"로 표시하고 확정 근거로 사용하지 않는다. (none / low-confidence 케이스 원칙 유지)

**게이트 재통과 조건:** `fail_count = 0` (WARN은 허용), fallback 0 유지(실제 Chroma 검색)

---

## 3. 5일차 실행 순서 (통합 → 재게이트)

```
1. (Tool) 실제 LLM selector 실행 → Tool Contract/설명 보강 → 검증 재실행
2. (RAG) 문서 추가 + 메타데이터 부착 → 재인덱싱 → Query Rewrite/Top-K 조정 → 평가 재실행
3. quality_gate_runner 재실행 (uv)
4. Tool Plan·RAG가 HOLD를 벗어나면 Final Agent 통합 진행
   - PASS    → DB/Tool 실행 허용
   - WARNING → 조건 보완 또는 사람 확인
   - 잔여 BLOCK/FAIL → 실행 제외 + Edge Case 시나리오로 이관
```

---

## 4. 완료 기준 (Definition of Done)

- Quality Gate `overall_status`가 HOLD → WARNING 이상으로 상승
- Tool Plan: `fail_count = 0`, `missing_argument_count = 0`
- RAG: `fail_count = 0`, fallback 0 유지(실제 Chroma 검색)
- 위 결과가 `outputs/day4/quality_gate_result.json` 및 `outputs/day4/day5_final_agent_integration_backlog.md`에 반영

---

## 5. 실행 환경 주의

- 모든 실행·검증은 `uv run python ...`(= `.venv`)으로 수행한다. 시스템 Python에는 `chevron`, `chromadb`가 없어 결과가 달라진다.
- 실제 RAG 검색은 Ollama가 실행 중이어야 한다(`nomic-embed-text`, 768차원). 미실행 시 평가기는 자동으로 mock fallback 된다.
