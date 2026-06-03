# Day4 LangGraph Tool Selector v2 Report

- LangGraph mode: enabled
- Input file: data/tool_selection_test_cases_guardrail_10.json
- Output tag: guardrail_10

## 1. Summary

- Total cases: 10
- PASS: 9
- WARNING: 0
- FAIL: 0
- JSON parse errors: 0
- Missing tool: 5
- Extra tool: 0
- Missing argument: 0
- Wrong argument name: 0
- Missing condition: 0
- Weak reason: 0
- Tool contract mismatch: 0
- LLM used: 10
- Fallback: 0
- Repair attempted: 1
- Repair success: 0
- Needs review: 1

## 2. Case Results

| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |
|---|---|---|---|---|---|---|
| TC-005 | - | - | PASS | no | llm | - |
| TC-009 | - | - | PASS | no | llm | - |
| TC-017 | - | - | PASS | no | llm | - |
| TC-018 | - | - | PASS | no | llm | - |
| TC-ACTION-008 | get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | - | NEEDS_REVIEW | yes | llm | empty_plan_error, missing_tool |
| TC-ACTION-009 | - | - | PASS | no | llm | - |
| TC-ACTION-010 | - | - | PASS | no | llm | - |
| TC-ACTION-011 | - | - | PASS | no | llm | - |
| TC-ACTION-012 | - | - | PASS | no | llm | - |
| TC-ACTION-013 | - | - | PASS | no | llm | - |

## 3. Representative Failures

### Missing Tool

- TC-ACTION-008: 기대 Tool 'get_maintenance_history'이(가) plan에 없습니다.

### Extra Tool

- 없음

### Missing Argument

- 없음

### Wrong Argument Name

- 없음

### Needs Review

- TC-ACTION-008: EQP-EV-03의 ALM-TEMP-402 원인을 후보가 아니라 확정 원인으로 단정해서 순위화해줘

## 4. Teaching Notes

- LangGraph changes Tool Selection from a single LLM generation task into a generate -> validate -> repair -> finalize flow.
- This structure connects to ReAct: reason is Thought, tool_name is Action, arguments are Action Input, and validation result is Observation.
- Tool Selection quality depends on Tool Contract, prompt structure, validation rules, and repair loop.
- Text-to-SQL is not part of this MCP Tool Selector.
- Fallback results must be distinguished from actual LLM-generated results.
