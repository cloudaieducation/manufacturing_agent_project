# Day4 LangGraph Tool Selector v2 Report

- LangGraph mode: enabled
- Input file: data/tool_selection_test_cases_action_5.json
- Output tag: action_5_openai_preview

## 1. Summary

- Total cases: 3
- PASS: 0
- WARNING: 0
- FAIL: 0
- JSON parse errors: 0
- Missing tool: 0
- Extra tool: 0
- Missing argument: 4
- Wrong argument name: 1
- Missing condition: 0
- Weak reason: 0
- Tool contract mismatch: 0
- LLM used: 3
- Fallback: 0
- Repair attempted: 3
- Repair success: 0
- Needs review: 3

## 2. Case Results

| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |
|---|---|---|---|---|---|---|
| TC-ACTION-001 | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | NEEDS_REVIEW | yes | llm | missing_argument, wrong_argument_name |
| TC-ACTION-002 | get_recent_alarm_events, get_process_status, get_quality_metrics, search_manual | search_manual, get_quality_metrics, get_process_status, get_recent_alarm_events | NEEDS_REVIEW | yes | llm | missing_argument |
| TC-ACTION-003 | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | get_equipment_status, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | NEEDS_REVIEW | yes | llm | missing_argument |

## 3. Representative Failures

### Missing Tool

- 없음

### Extra Tool

- 없음

### Missing Argument

- TC-ACTION-001: step 4: 'get_quality_metrics'은 metric_name, equipment_id, line_id 중 하나 이상이 필요합니다.
- TC-ACTION-002: step 3: 'get_process_status'은 process_name, line_id 중 하나 이상이 필요합니다.
- TC-ACTION-003: step 3: 'get_process_status'은 process_name, line_id 중 하나 이상이 필요합니다.

### Wrong Argument Name

- TC-ACTION-001: step 4: 'get_quality_metrics'에 정의되지 않은 argument 'process_name'.

### Needs Review

- TC-ACTION-001: EQP-EV-03에서 ALM-TEMP-402가 반복 발생했습니다. 박막 증착 공정 관점에서 원인 후보를 가능성 순서대로 정리해 주세요. 단, 원인을 확정하지 말고 근거와 추가 확인 항목을 함께 제시해 주세요.
- TC-ACTION-002: ALM-TEMP-402 발생 시 현장 엔지니어가 10분 안에 확인할 1차 체크리스트를 만들어 주세요. 챔버 온도, 진공도, 증착률, 박막 두께 균일도, 파티클 관련 품질 지표도 함께 확인하고 싶습니다.
- TC-ACTION-003: EQP-EV-03의 챔버 온도 편차 알람이 반복 발생했습니다. 설비팀, 공정팀, 품질팀, 정비팀 중 어디에 먼저 공유해야 하는지 판단해 주세요.

## 4. Teaching Notes

- LangGraph changes Tool Selection from a single LLM generation task into a generate -> validate -> repair -> finalize flow.
- This structure connects to ReAct: reason is Thought, tool_name is Action, arguments are Action Input, and validation result is Observation.
- Tool Selection quality depends on Tool Contract, prompt structure, validation rules, and repair loop.
- Text-to-SQL is not part of this MCP Tool Selector.
- Fallback results must be distinguished from actual LLM-generated results.
