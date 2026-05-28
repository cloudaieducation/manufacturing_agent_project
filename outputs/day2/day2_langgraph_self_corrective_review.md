# Day2 LangGraph Self-RAG / Corrective RAG 검토 산출물

> 이 산출물은 외부 LLM grader/웹 검색 없이 **규칙 기반 검증**과 **제조 Tool/MCP fallback 계획**으로 작성되었습니다(실제 Tool 호출 없음).

## 1. 사용자 질문

- 질문: EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생했습니다. sample_alarm_logs.csv와 alarm_manual.md를 참고하여 반복 발생 여부, 원인 후보, 1차 확인 항목, 권장 조치, 추가 확인 필요 사항을 Markdown 리포트로 정리해 주세요.
- equipment_id: EQP-EV-03
- alarm_code: ALM-TEMP-402
- grounding_status: grounded

## 2. Self-RAG 검증 결과

| 검증 항목 | 상태 | 판단 이유 |
|---|---|---|
| 문서 관련성 (document_relevance) | pass | 문서 3건 / 로그 14건의 검색 근거가 존재합니다. |
| 답변 근거성 (answer_grounding) | pass | 답변이 설비 ID/알람 코드 또는 검색 근거 키워드를 반영합니다. |
| 답변 유용성 (answer_helpfulness) | pass | 확인/점검/검토/조치/추가 확인 등 실무 안내 표현이 포함됩니다. |
| 단정 표현 점검 (overclaim_check) | pass | 원인을 단정하는 표현이 발견되지 않았습니다. |
| 민감정보 점검 (safety_check) | pass | 개인정보·작업자 이름·사번·연락처 등 민감정보 표현이 발견되지 않았습니다. |

## 3. Guardrail 경고 (guardrail_warnings)

- (경고 없음) 원인 단정·근거 부족·민감정보 가능성 경고가 발견되지 않았습니다.

## 4. Corrective RAG 보정 계획 (제조 Tool/MCP fallback)

> 원본 Corrective RAG는 근거 부족 시 웹 검색으로 보정하지만, 제조/사내 환경에서는 승인된 Tool과 제한된 데이터 소스로 보정합니다. 아래는 실제 호출이 아니라 3일차 MCP Tool로 확장 가능한 계획입니다.

| 단계 | Action/Tool | 목적 | MCP 연결 |
|---:|---|---|---|
| 1 | search_manual | 알람 코드의 매뉴얼 근거와 1차 확인 항목을 재확인합니다. | 3일차 search_manual MCP Tool로 확장 가능 |
| 2 | get_recent_alarm_events | 동일 설비/알람 코드의 최근 알람 이벤트와 반복 발생 추이를 조회합니다. | 3일차 get_recent_alarm_events MCP Tool로 확장 가능 |
| 3 | get_process_status | 현재 공정/설비 상태(온도·압력·진공 등) 값을 확인합니다. | 3일차 get_process_status MCP Tool로 확장 가능 |
| 4 | get_quality_metrics | 해당 구간의 품질 지표(불량/수율 등) 영향 여부를 확인합니다. | 3일차 get_quality_metrics MCP Tool로 확장 가능 |
| 5 | get_maintenance_history | 설비의 정비/부품 교체 이력을 확인합니다. | 3일차 get_maintenance_history MCP Tool로 확장 가능 |

## 5. 추천 Tool 후보 (recommended_tools)

- search_manual
- get_recent_alarm_events
- get_process_status
- get_quality_metrics
- get_maintenance_history

## 6. 3일차 MCP Tool 연결

- 위 보정 계획의 Tool 후보는 3일차에 FastMCP 기반 Tool Contract(search_manual, get_recent_alarm_events, get_process_status, get_quality_metrics, get_maintenance_history)로 확장됩니다.
- 이 노트북에서는 실제 호출 없이 '어떤 Tool을 어떤 목적으로 호출할지'에 대한 계획만 State(corrective_plan)에 남깁니다.

## 7. 4일차 Guardrail/Trace 평가 연결

- self_rag_review와 guardrail_warnings는 4일차의 Guardrail/품질 게이트, Trace 평가 기준으로 확장됩니다.
- trace와 함께 보면 '어떤 Node에서 근거가 부족했고, 어떤 보정 계획을 세웠는지'를 실행 품질 관점에서 평가할 수 있습니다.
