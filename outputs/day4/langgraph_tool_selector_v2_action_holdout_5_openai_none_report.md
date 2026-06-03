# Day4 LangGraph Tool Selector v2 Report

- LangGraph mode: enabled
- Input file: data/tool_selection_test_cases_action_holdout_5.json
- Output tag: action_holdout_5_openai_none
- Normalization mode: none
- Normalization: disabled. Raw LLM plan is validated directly.
- Normalization: case_id / expected_tools 기반 보정 없음 (Tool Contract + user_query entity + 교육용 시나리오 컨텍스트 기준)

## 1. Summary

- Total cases: 5
- PASS: 0
- WARNING: 0
- FAIL: 0
- JSON parse errors: 0
- Missing tool: 7
- Extra tool: 0
- Missing argument: 1
- Wrong argument name: 0
- Missing condition: 0
- Weak reason: 0
- Tool contract mismatch: 0
- LLM used: 5
- Fallback: 0
- Repair attempted: 5
- Repair success: 0
- Needs review: 5
- Normalization applied: 0/5
- Action policy rules: 0
- Argument normalization rules: 0
- Argument removed rules: 0
- Dedup rules: 0

## 2. Case Results

| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |
|---|---|---|---|---|---|---|
| HOLDOUT-ACTION-001 | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | get_equipment_status, get_recent_alarm_events, get_quality_metrics, get_maintenance_history, search_manual | NEEDS_REVIEW | yes | llm | missing_tool |
| HOLDOUT-ACTION-002 | get_recent_alarm_events, get_process_status, get_quality_metrics, search_manual | - | NEEDS_REVIEW | yes | llm | empty_plan_error, missing_tool |
| HOLDOUT-ACTION-003 | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | get_recent_alarm_events, get_equipment_status, get_quality_metrics, get_maintenance_history, search_manual | NEEDS_REVIEW | yes | llm | missing_tool |
| HOLDOUT-ACTION-004 | get_recent_alarm_events, get_process_status, get_quality_metrics, search_manual | get_recent_alarm_events, get_process_status, get_quality_metrics, get_quality_metrics, get_quality_metrics, search_manual | NEEDS_REVIEW | yes | llm | missing_argument |
| HOLDOUT-ACTION-005 | get_equipment_status, get_recent_alarm_events, get_process_status, get_maintenance_history, search_manual | get_equipment_status, get_recent_alarm_events, get_maintenance_history, search_manual | NEEDS_REVIEW | yes | llm | missing_tool |

## 3. Representative Failures

### Missing Tool

- HOLDOUT-ACTION-001: 기대 Tool 'get_process_status'이(가) plan에 없습니다.
- HOLDOUT-ACTION-002: 기대 Tool 'get_process_status'이(가) plan에 없습니다.
- HOLDOUT-ACTION-003: 기대 Tool 'get_process_status'이(가) plan에 없습니다.
- HOLDOUT-ACTION-005: 기대 Tool 'get_process_status'이(가) plan에 없습니다.

### Extra Tool

- 없음

### Missing Argument

- HOLDOUT-ACTION-004: step 1: 'get_recent_alarm_events'의 필수 argument 'equipment_id' 누락.

### Wrong Argument Name

- 없음

### Needs Review

- HOLDOUT-ACTION-001: EQP-EV-03에서 ALM-TEMP-402가 주기적으로 올라오는 것 같습니다. 확정 원인은 말하지 말고 설비 상태, 최근 알람 이력, 공정 상태, 품질 지표, 정비 이력, 관련 매뉴얼 근거를 바탕으로 확인해야 할 가능성 있는 원인 관점을 정리해 주세요.
- HOLDOUT-ACTION-002: ALM-TEMP-402가 발생했을 때 현장에서 빠르게 먼저 확인해야 할 초기 점검 항목을 묶어 정리하고 싶습니다. 최근 알람 이력, 증착 공정 상태, 품질 지표, 관련 매뉴얼 근거를 함께 확인해 주세요.
- HOLDOUT-ACTION-003: EQP-EV-03에서 온도 편차 관련 알람이 반복되는 상황입니다. 이 이슈를 설비, 공정, 품질, 정비 중 어느 관점에서 먼저 봐야 할지 판단할 수 있도록 관련 근거를 수집해 주세요.
- HOLDOUT-ACTION-004: ALM-TEMP-402가 다시 나타나는지 추적할 기준을 만들고 싶습니다. 최근 알람 발생 패턴, 증착 공정 상태, defect_rate, particle_count, 박막 두께 균일도 같은 품질 지표, 관련 문서 근거를 확인해 주세요.
- HOLDOUT-ACTION-005: EQP-EV-03의 ALM-TEMP-402 반복 발생 상황을 교육용 점검 안내 초안으로 정리하려고 합니다. 실제 조치를 지시하는 내용이 아니라, 설비 상태, 알람 이력, 공정 상태, 정비 이력, 매뉴얼 근거를 확인하는 점검 중심으로 구성해 주세요.

## 4. Normalization Rules Summary

| Case ID | Normalization Applied | Rule IDs |
|---|---|---|
| HOLDOUT-ACTION-001 | False | - |
| HOLDOUT-ACTION-002 | False | - |
| HOLDOUT-ACTION-003 | False | - |
| HOLDOUT-ACTION-004 | False | - |
| HOLDOUT-ACTION-005 | False | - |

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
