# Day4 LangGraph Tool Selector v2 Report

- LangGraph mode: enabled
- Input file: data/tool_selection_test_cases_action_holdout_5.json
- Output tag: action_holdout_5_intent_nvidia_full
- Normalization mode: full
- Normalization: Tool Contract + user_query entity + educational scenario context + Action Intent Policy.
- Normalization: case_id / expected_tools 기반 보정 없음 (Tool Contract + user_query entity + 교육용 시나리오 컨텍스트 기준)

## 1. Summary

- Total cases: 5
- PASS: 5
- WARNING: 0
- FAIL: 0
- JSON parse errors: 0
- Missing tool: 0
- Extra tool: 0
- Missing argument: 0
- Wrong argument name: 0
- Missing condition: 0
- Weak reason: 0
- Tool contract mismatch: 0
- LLM used: 2
- Fallback: 3
- Repair attempted: 0
- Repair success: 0
- Needs review: 0
- Normalization applied: 5/5
- Action policy rules: 2
- Argument normalization rules: 10
- Argument removed rules: 0
- Dedup rules: 0

> If fallback_count is high, this result includes fallback pipeline behavior and should not be interpreted as pure LLM Tool Selector performance.

## 2. Case Results

| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |
|---|---|---|---|---|---|---|
| HOLDOUT-ACTION-001 | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | get_recent_alarm_events, search_manual, get_maintenance_history, get_quality_metrics, get_process_status, get_equipment_status | PASS | no | fallback | - |
| HOLDOUT-ACTION-002 | get_recent_alarm_events, get_process_status, get_quality_metrics, search_manual | get_recent_alarm_events, search_manual, get_quality_metrics, get_process_status | PASS | no | fallback | - |
| HOLDOUT-ACTION-003 | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | get_recent_alarm_events, get_equipment_status, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | PASS | no | llm | - |
| HOLDOUT-ACTION-004 | get_recent_alarm_events, get_process_status, get_quality_metrics, search_manual | get_recent_alarm_events, search_manual, get_quality_metrics, get_process_status | PASS | no | fallback | - |
| HOLDOUT-ACTION-005 | get_equipment_status, get_recent_alarm_events, get_process_status, get_maintenance_history, search_manual | get_equipment_status, get_recent_alarm_events, get_maintenance_history, search_manual, get_process_status | PASS | no | llm | - |

## 3. Representative Failures

### Missing Tool

- 없음

### Extra Tool

- 없음

### Missing Argument

- 없음

### Wrong Argument Name

- 없음

### Needs Review

- 없음

## 4. Normalization Rules Summary

| Case ID | Normalization Applied | Rule IDs |
|---|---|---|
| HOLDOUT-ACTION-001 | True | ARG-get_equipment_status-equipment_id, ARG-get_process_status-anyof-process_name, POLICY-root_cause_ranking-get_equipment_status |
| HOLDOUT-ACTION-002 | True | ARG-get_process_status-anyof-process_name, ARG-get_quality_metrics-anyof-equipment_id, ARG-get_recent_alarm_events-equipment_id |
| HOLDOUT-ACTION-003 | True | ARG-get_process_status-anyof-process_name |
| HOLDOUT-ACTION-004 | True | ARG-get_process_status-anyof-process_name, ARG-get_quality_metrics-anyof-equipment_id, ARG-get_recent_alarm_events-equipment_id |
| HOLDOUT-ACTION-005 | True | ARG-get_process_status-anyof-process_name, POLICY-work_instruction_draft-get_process_status |

## 5. Teaching Notes

- LangGraph changes Tool Selection from a single LLM generation task into a generate -> validate -> repair -> finalize flow.
- This structure connects to ReAct: reason is Thought, tool_name is Action, arguments are Action Input, and validation result is Observation.
- Tool Selection quality depends on Tool Contract, prompt structure, validation rules, and repair loop.
- Text-to-SQL is not part of this MCP Tool Selector.
- Fallback results must be distinguished from actual LLM-generated results.

본 평가는 case_id별 정답 하드코딩이나 expected_tools 참조를 사용하지 않습니다.
모든 보정은 Tool Contract, 사용자 질문에서 추출한 entity, 교육용 시나리오 기준 데이터에 기반합니다.
보고서에는 LLM 원본 plan과 보정 후 plan을 함께 기록해 평가 과정을 투명하게 확인할 수 있습니다.
- 교육용 시나리오 컨텍스트(EQP-EV-03 -> 증착 공정/EDU-LINE-01 등)는 테스트 정답이 아니라 DisplayEdu Fab 가상 제조 시나리오 기준 데이터입니다.
- Ablation 모드는 Raw LLM 성능(none), Tool Contract argument 정규화 효과(argument-only), Action Tool Policy까지 포함한 운영형 Agent 구조 효과(full)를 분리해서 보기 위한 검증 모드입니다.
- full 결과가 좋더라도 LLM 단독 성능으로 해석하면 안 됩니다. Ablation comparison is safest when --output-tag includes the normalization mode.
