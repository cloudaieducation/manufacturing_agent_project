# Day4 LangGraph Tool Selector v2 Report

- LangGraph mode: enabled

## 1. Summary

- Total cases: 1
- PASS: 1
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
- LLM used: 1
- Fallback: 0
- Repair attempted: 0
- Repair success: 0
- Needs review: 0

## 2. Case Results

| Case ID | Expected Tools | Final Tools | Final Status | Repair | LLM/Fallback | Issues |
|---|---|---|---|---|---|---|
| TC-005 | - | - | PASS | no | llm | - |

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

## 4. Teaching Notes

- LangGraph changes Tool Selection from a single LLM generation task into a generate -> validate -> repair -> finalize flow.
- This structure connects to ReAct: reason is Thought, tool_name is Action, arguments are Action Input, and validation result is Observation.
- Tool Selection quality depends on Tool Contract, prompt structure, validation rules, and repair loop.
- Text-to-SQL is not part of this MCP Tool Selector.
- Fallback results must be distinguished from actual LLM-generated results.
