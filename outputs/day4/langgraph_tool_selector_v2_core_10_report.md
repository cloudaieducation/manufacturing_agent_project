# Day4 LangGraph Tool Selector v2 Report

- LangGraph mode: enabled
- Input file: data/tool_selection_test_cases_core_10.json
- Output tag: core_10

## 1. Summary

- Total cases: 10
- PASS: 8
- WARNING: 0
- FAIL: 0
- JSON parse errors: 0
- Missing tool: 1
- Extra tool: 0
- Missing argument: 1
- Wrong argument name: 0
- Missing condition: 0
- Weak reason: 0
- Tool contract mismatch: 0
- LLM used: 9
- Fallback: 2
- Repair attempted: 3
- Repair success: 1
- Needs review: 2

> If fallback_count is high, this result includes fallback pipeline behavior and should not be interpreted as pure LLM Tool Selector performance.

## 2. Case Results

| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |
|---|---|---|---|---|---|---|
| TC-001 | get_recent_alarm_events | get_recent_alarm_events | PASS | no | llm | - |
| TC-002 | get_quality_metrics | get_quality_metrics | PASS | no | llm | - |
| TC-003 | search_manual | search_manual | PASS | no | llm | - |
| TC-004 | get_recent_alarm_events, get_quality_metrics, search_manual | get_recent_alarm_events, get_quality_metrics, search_manual | PASS | no | llm | - |
| TC-006 | get_maintenance_history | get_maintenance_history | PASS | no | llm | - |
| TC-007 | get_process_status | get_process_status | NEEDS_REVIEW | yes | fallback | missing_argument |
| TC-008 | get_equipment_status | get_equipment_status | PASS | yes | llm | - |
| TC-010 | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | get_recent_alarm_events, search_manual, get_equipment_status, get_maintenance_history, get_quality_metrics | NEEDS_REVIEW | yes | fallback | missing_tool |
| TC-014 | get_recent_alarm_events, get_maintenance_history | get_recent_alarm_events, get_maintenance_history | PASS | no | llm | - |
| TC-016 | get_recent_alarm_events, get_quality_metrics | get_recent_alarm_events, get_quality_metrics | PASS | no | llm | - |

## 3. Representative Failures

### Missing Tool

- TC-010: 기대 Tool 'get_process_status'이(가) plan에 없습니다.

### Extra Tool

- 없음

### Missing Argument

- TC-007: step 1: 'get_process_status'은 process_name, line_id 중 하나 이상이 필요합니다.

### Wrong Argument Name

- 없음

### Needs Review

- TC-007: EQP-EV-03의 최근 온도, 압력, 진공 상태를 확인해줘
- TC-010: EQP-EV-03에서 ALM-TEMP-402가 발생했는데 설비 상태, 알람 이력, 공정 상태, 품질 영향, 정비 이력, 조치 절차를 모두 확인해줘

## 4. Teaching Notes

- LangGraph changes Tool Selection from a single LLM generation task into a generate -> validate -> repair -> finalize flow.
- This structure connects to ReAct: reason is Thought, tool_name is Action, arguments are Action Input, and validation result is Observation.
- Tool Selection quality depends on Tool Contract, prompt structure, validation rules, and repair loop.
- Text-to-SQL is not part of this MCP Tool Selector.
- Fallback results must be distinguished from actual LLM-generated results.
