# Day4 LangGraph Tool Selector v2 Report

- LangGraph mode: enabled
- Input file: data/tool_selection_test_cases_guardrail_10.json
- Output tag: guardrail_10_norm_check
- Normalization: case_id / expected_tools 기반 보정 없음 (Tool Contract + user_query entity + 교육용 시나리오 컨텍스트 기준)

## 1. Summary

- Total cases: 10
- PASS: 9
- WARNING: 0
- FAIL: 0
- JSON parse errors: 0
- Missing tool: 3
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
- Normalization applied: 0/10

## 2. Case Results

| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |
|---|---|---|---|---|---|---|
| TC-005 | - | - | PASS | no | llm | - |
| TC-009 | - | - | PASS | no | llm | - |
| TC-017 | - | - | PASS | no | llm | - |
| TC-018 | - | - | PASS | no | llm | - |
| TC-ACTION-008 | get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history, search_manual | get_recent_alarm_events, search_manual | NEEDS_REVIEW | yes | llm | missing_tool |
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

## 4. Normalization Rules Summary

| Case ID | Normalization Applied | Rule IDs |
|---|---|---|
| TC-005 | False | - |
| TC-009 | False | - |
| TC-017 | False | - |
| TC-018 | False | - |
| TC-ACTION-008 | False | - |
| TC-ACTION-009 | False | - |
| TC-ACTION-010 | False | - |
| TC-ACTION-011 | False | - |
| TC-ACTION-012 | False | - |
| TC-ACTION-013 | False | - |

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
