# Day1 Agent v0 실행 Trace: 교육용 가상 실습 Trace

> 이 Trace는 AI Agent Architecture 강의용 가상 데이터로 생성되었습니다.  
> 실제 삼성디스플레이의 사내 데이터, 실제 설비명, 실제 라인명, 실제 알람 코드, 실제 공정 조건과 무관합니다.  
> API Key, 환경변수 전체 목록, 시스템 민감정보는 저장하지 않습니다.

---

## 1. Trace 목적

이 파일은 Day1 Agent v0가 어떤 Node를 어떤 순서로 실행했는지 확인하기 위한 교육용 Trace입니다.  
LangGraph의 State, Node, Edge, Conditional Edge를 이해하는 데 사용합니다.

---

## 2. 입력 정보

| 항목 | 값 |
|---|---|
| user_query | EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생했습니다. sample_alarm_logs.csv와 alarm_manual.md를 참고하여 반복 발생 여부, 원인 후보, 1차 확인 항목, 권장 조치, 추가 확인 필요 사항을 Markdown 리포트로 정리해 주세요. |
| line_id | EDU-LINE-07 |
| process_name | Thin Film Deposition |
| equipment_id | EQP-EV-03 |
| alarm_code | ALM-TEMP-402 |

---

## 3. LangGraph 실행 흐름

```text
START
 → load_input_node
 → check_required_info_node
 → 조건부 분기
    - 필수 정보 있음:
      search_log_node
      → search_manual_node
      → build_prompt_node
      → generate_response_node
      → build_final_report_node
      → END

    - 필수 정보 부족:
      ask_more_info_node
      → END
```

---

## 4. Node 실행 Trace

| 순서 | Node | 입력 요약 | 출력 요약 | 다음 이동 |
|---:|---|---|---|---|
| 1 | load_input_node | sample_query 기반 입력 State 확인 | 입력 확인: equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402 | check_required_info_node |
| 2 | check_required_info_node | equipment_id와 alarm_code 존재 여부 확인 | LangGraph 분기: 필수 정보 있음 → 로그 조회 | search_log_node |
| 3 | search_log_node | equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402 | 로그 조회: 관련 로그 14건 발견 | search_manual_node |
| 4 | search_manual_node | alarm_code=ALM-TEMP-402 | 매뉴얼 검색: ALM-TEMP-402 관련 내용 확인 | build_prompt_node |
| 5 | build_prompt_node | log_summary와 manual_section 기반 프롬프트 템플릿 렌더링 | LLM 프롬프트 생성 완료 | generate_response_node |
| 6 | generate_response_node | llm_prompt를 llm_client.generate_response에 전달 | llm_client.py를 통한 LLM 응답 생성 완료 | build_final_report_node |
| 7 | build_final_report_node | log_summary, manual_section, llm_response 템플릿 렌더링 | final_report 생성 완료 | END |

---

## 5. Conditional Edge 분기 결과

- next_action: `investigate`
- 분기 결과: search_log_node로 이동

---

## 6. LLM 호출부 교체 가능 구조 설명

- `src/day1/day1_agent_v0_simple` 파일은 `llm_client.py`만 호출합니다.
- Agent 본체는 `cloud_llm.py` 또는 `mock_llm.py`를 직접 알지 못합니다.
- `llm_client.py`가 Cloud LLM 또는 mock LLM을 선택합니다.
- 따라서 회사 정책에 따라 OpenAI, Claude, 사내 LLM, 로컬 LLM 등으로 바꾸더라도 Agent 본체 코드는 크게 바꾸지 않는 구조를 만들 수 있습니다.

---

## 7. 메시지

- 입력 확인: equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402
- LangGraph 분기: 필수 정보 있음 → 로그 조회
- 로그 조회: 관련 로그 14건 발견
- 매뉴얼 검색: ALM-TEMP-402 관련 내용 확인
- LLM 프롬프트 생성 완료
- llm_client.py를 통한 LLM 응답 생성 완료
- 최종 리포트 생성 완료

---

## 8. 오류 및 주의 사항

- 오류 없음

---

## 9. 다음 실습 연결

2일차에는 `alarm_manual.md` 단순 검색을 RAG 검색으로 확장합니다.  
문서를 chunk로 나누고 metadata를 붙인 뒤 Top-3 검색 결과를 State에 저장하는 구조로 발전시킵니다.
