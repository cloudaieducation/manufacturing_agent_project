# Day5 Final Agent Integration Backlog

## 1. Purpose

4일차 평가 결과를 5일차 Final Agent 통합 항목으로 연결한다.

## 2. Day4 Quality Gate Summary

- Overall Status: HOLD
- Tool Plan Validation: HOLD
- Guardrail: WARNING
- RAG Quality: HOLD
- Text-to-SQL Safety: WARNING
- Text-to-SQL Trace: PASS
- Prompt Evaluation: WARNING

## 3. Integration Backlog

| Priority | Backlog Item | Reason |
|---:|---|---|
| 1 | check_text_to_sql_safety를 MCP Tool로 등록 | 4일차 Quality Gate 결과 반영 |
| 1 | PASS일 때만 DB Tool 실행하도록 Agent 분기 추가 | 4일차 Quality Gate 결과 반영 |
| 2 | WARNING일 때 사용자에게 조건 보완 요청 | 4일차 Quality Gate 결과 반영 |
| 1 | BLOCK일 때 Safe Refusal 응답 | 4일차 Quality Gate 결과 반영 |
| 1 | Text-to-SQL Trace를 Final Trace Review에 포함 | 4일차 Quality Gate 결과 반영 |
| 2 | RAG WARN/FAIL 케이스를 Final Report에서 근거 부족으로 표시 | 4일차 Quality Gate 결과 반영 |
| 2 | Guardrail BLOCK 케이스를 Edge Case 시나리오에 포함 | 4일차 Quality Gate 결과 반영 |
| 2 | Tool Plan mismatch가 있으면 Tool Contract와 Tool 설명 보강 | 4일차 Quality Gate 결과 반영 |
| 2 | RAG 평가가 HOLD/WARNING이므로 Final Report에 근거 신뢰도를 표시 | 4일차 Quality Gate 결과 반영 |
| 2 | Prompt Scorecard가 없으므로 5일차 전 Prompt Evaluation 결과를 보완 | 4일차 Quality Gate 결과 반영 |
| 2 | Quality Gate가 PASS가 아니므로 5일차 첫 시간에 보완 항목을 먼저 설명 | 4일차 Quality Gate 결과 반영 |

## 4. Text-to-SQL Safety Integration

- check_text_to_sql_safety를 MCP Tool로 등록
- PASS일 때만 DB Tool 실행
- WARNING일 때 조건 보완 요청
- BLOCK일 때 Safe Refusal 응답

## 5. RAG / Guardrail / Trace Integration

- RAG Quality: HOLD → 근거 신뢰도 표시 검토
- Guardrail: WARNING → BLOCK 케이스를 Edge Case 시나리오에 포함
- Text-to-SQL Trace: PASS → Final Trace Review에 포함

## 6. Day5 Opening Message

4일차에는 Agent가 올바르게 판단하고 안전하게 실행되는지 평가했다.
5일차에는 이 평가 결과를 Final Agent에 반영한다.
