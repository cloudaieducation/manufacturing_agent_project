# Day4 LangGraph Tool Selector v2 Report

- LangGraph mode: enabled
- Input file: data/tool_selection_test_cases.json
- Output tag: all
- Normalization mode: full
- Normalization: Tool Contract + user_query entity + educational scenario context + Action Intent Policy.
- Report template: templates/day4/langgraph_tool_selector_v2_report.mustache
- Normalization: case_id / expected_tools 기반 보정 없음 (Tool Contract + user_query entity + 교육용 시나리오 컨텍스트 기준)

## 1. Summary

- Total cases: 10
- PASS: 9
- WARNING: 0
- FAIL: 0
- JSON parse errors: 0
- Missing tool: 1
- Extra tool: 0
- Missing argument: 0
- Wrong argument name: 0
- Missing condition: 0
- Weak reason: 0
- Tool contract mismatch: 0
- LLM used: 9
- Fallback: 2
- Repair attempted: 4
- Repair success: 3
- Needs review: 1
- Normalization applied: 2/10
- Action policy rules: 0
- Argument normalization rules: 2
- Argument removed rules: 0
- Dedup rules: 0
- Fallback mode: rule
- Fallback total cases: 2
- Initial generation fallback: 1
- Repair fallback: 1
- LLM error count: 0
- LLM unavailable count: 0

> If fallback_count is high, this result includes fallback pipeline behavior and should not be interpreted as pure LLM Tool Selector performance.

## 2. Case Results

| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |
|---|---|---|---|---|---|---|
| TC-001 | get_recent_alarm_events | get_recent_alarm_events | PASS | no | llm | - |
| TC-002 | get_quality_metrics | get_quality_metrics | PASS | no | llm | - |
| TC-003 | search_manual | search_manual | PASS | no | llm | - |
| TC-004 | get_recent_alarm_events, get_quality_metrics, search_manual | get_recent_alarm_events, get_quality_metrics, search_manual | PASS | yes | llm | - |
| TC-005 | - | - | PASS | no | llm | - |
| TC-006 | get_maintenance_history | get_maintenance_history | PASS | no | llm | - |
| TC-007 | get_process_status | get_process_status | PASS | yes | fallback | - |
| TC-008 | get_equipment_status | get_equipment_status | PASS | yes | llm | - |
| TC-009 | - | - | PASS | no | llm | - |
| TC-010 | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | get_recent_alarm_events, search_manual, get_maintenance_history, get_quality_metrics, get_equipment_status | NEEDS_REVIEW | yes | fallback | missing_tool |

## 3. Representative Failures

### Missing Tool

- TC-010: 기대 Tool 'get_process_status'이(가) plan에 없습니다.

### Extra Tool

- 없음

### Missing Argument

- 없음

### Wrong Argument Name

- 없음

### Needs Review

- TC-010: EQP-EV-03에서 ALM-TEMP-402가 발생했는데 설비 상태, 알람 이력, 공정 상태, 품질 영향, 정비 이력, 조치 절차를 모두 확인해줘

## 4. Normalization Rules Summary

| Case ID | Normalization Applied | Rule IDs |
|---|---|---|
| TC-001 | False | - |
| TC-002 | False | - |
| TC-003 | False | - |
| TC-004 | False | - |
| TC-005 | False | - |
| TC-006 | False | - |
| TC-007 | True | ARG-get_process_status-anyof-process_name |
| TC-008 | False | - |
| TC-009 | False | - |
| TC-010 | True | ARG-get_process_status-anyof-process_name |

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
- Fallback count는 LLM 성능 해석에 직접 영향을 주므로 initial generation fallback과 repair fallback을 분리해서 봐야 합니다.
- LangGraph fallback function pipeline은 LLM fallback이 아니라 실행 경로 fallback입니다.
- strict fallback mode는 순수 LLM 평가용이고, rule fallback mode는 강의 안정성용입니다.
- llm_used는 사용 가능한 LLM Tool Plan이 최종 생성되었는지를 의미하며, LLM 호출 시도 여부와는 다를 수 있습니다.
