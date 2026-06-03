# 1일차 LangGraph mini Graph 실행 Trace

# 정상 케이스: 교육용 가상 실습 결과

> 이 결과는 AI Agent Architecture 강의용 가상 데이터로 생성되었습니다.  
> 실제 제조 기업의 사내 데이터, 실제 설비명, 실제 라인명, 실제 알람 코드, 실제 공정 조건과 무관합니다.  
> 이 파일은 LangGraph의 State, Node, Edge, Conditional Edge와 LLM 호출부 분리 구조를 이해하기 위한 교육용 산출물입니다.

---

## 1. 실습 목적

이번 실습은 Chain과 Graph의 차이를 이해하기 위한 미니 실습입니다.  
Chain은 정해진 순서대로 실행되지만, Graph는 조건에 따라 다음 단계가 달라질 수 있습니다.  
또한 LLM 호출은 `src/day1/mini_graph_runner.py`에서 직접 처리하지 않고 `src/llm_client.py`로 분리합니다.

---

## 2. 실행 케이스 이름

- 정상 케이스

---

## 3. 입력 정보

| 항목 | 값 |
|---|---|
| user_query | EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생했습니다. sample_alarm_logs.csv와 alarm_manual.md를 참고하여 반복 발생 여부, 원인 후보, 1차 확인 항목, 권장 조치, 추가 확인 필요 사항을 Markdown 리포트로 정리해 주세요. |
| line_id | EDU-LINE-07 |
| process_name | Thin Film Deposition |
| equipment_id | EQP-EV-03 |
| alarm_code | ALM-TEMP-402 |

---

## 4. LangGraph 흐름 요약

```text
START
 → start_node
 → parse_query_node
 → check_required_info_node
 → 조건부 분기
    - 필수 정보 있음:
      search_log_node
      → summarize_result_node
      → build_llm_prompt_node
      → generate_llm_response_node
      → END

    - 필수 정보 부족:
      ask_more_info_node
      → END
```

---

## 5. Node 실행 Trace

| 순서 | Node | 입력 요약 | 출력 요약 | 다음 이동 |
|---:|---|---|---|---|
| 1 | start_node | 초기 State 입력 | 실행 시작 메시지 추가 | parse_query_node |
| 2 | parse_query_node | user_query와 query 필드 확인 | equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402 확인 | check_required_info_node |
| 3 | check_required_info_node | equipment_id와 alarm_code 존재 여부 확인 | 필수 정보 있음 → search_log_node로 이동 | search_log_node |
| 4 | search_log_node | equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402 | 관련 로그 14건 발견 | summarize_result_node |
| 5 | summarize_result_node | log_results 요약 | 관련 로그 14건 요약 완료 (최초=2026-05-01 09:05:12, 마지막=2026-05-02 10:55:29) | build_llm_prompt_node |
| 6 | build_llm_prompt_node | log_summary 기반 프롬프트 템플릿 렌더링 | llm_prompt 생성 완료 | generate_llm_response_node |
| 7 | generate_llm_response_node | llm_prompt를 llm_client.generate_response에 전달 | llm_client.py를 통한 LLM 응답 생성 완료 | END |

---

## 6. Conditional Edge 분기 결과

- next_action: `search_log`
- 분기 결과: search_log_node로 이동

---

## 7. 로그 요약

```json
{
  "total_count": 14,
  "first_timestamp": "2026-05-01 09:05:12",
  "last_timestamp": "2026-05-02 10:55:29",
  "severity_counts": {
    "WARNING": 8,
    "CRITICAL": 6
  },
  "repeat_count_max": 14
}
```

---

## 8. 생성된 LLM 프롬프트

```markdown
# 역할
당신은 교육용 제조 장애 대응 AI Agent입니다.

# 교육용 가상 데이터 안내
이 실습은 DisplayEdu Fab 가상 시나리오를 사용합니다.
실제 제조 기업의 사내 데이터, 실제 설비명, 실제 라인명, 실제 알람 코드, 실제 공정 기준, 실제 조치 절차와 무관합니다.
실제 현장 조치 지시가 아니라 AI Agent 응답 구조를 학습하기 위한 교육용 답변만 작성해야 합니다.

# 사용자 요청
EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생했습니다. sample_alarm_logs.csv와 alarm_manual.md를 참고하여 반복 발생 여부, 원인 후보, 1차 확인 항목, 권장 조치, 추가 확인 필요 사항을 Markdown 리포트로 정리해 주세요.

# 입력 정보
- line_id: EDU-LINE-07
- process_name: Thin Film Deposition
- equipment_id: EQP-EV-03
- alarm_code: ALM-TEMP-402

# 로그 요약
```json
{
  "total_count": 14,
  "first_timestamp": "2026-05-01 09:05:12",
  "last_timestamp": "2026-05-02 10:55:29",
  "severity_counts": {
    "WARNING": 8,
    "CRITICAL": 6
  },
  "repeat_count_max": 14
}
```

# 출력 형식
Markdown 리포트 형식으로 작성하세요.
다음 항목을 포함하세요.

1. 교육용 가상 응답 안내
2. 요청 요약
3. 로그 기반 관찰 내용
4. 원인 후보
5. 1차 확인 항목
6. 권장 조치 방향
7. 추가 확인 필요 사항
8. Agent 응답 시 주의 사항

# 제약 조건
- 실제 조치 지시처럼 단정하지 마세요.
- 로그에 없는 내용을 추측하지 마세요.
- 실제 사내 데이터나 실제 공정 기준처럼 말하지 마세요.
- 원인 후보와 확인 항목을 구분하세요.
- 추가 확인 필요 사항을 반드시 포함하세요.
- 교육용 가상 응답임을 표시하세요.
- "가능성이 있습니다", "확인할 수 있습니다", "추가 확인이 필요합니다" 같은 교육용 표현을 사용하세요.
- 실제 내부 시스템명, 실제 장비 제조사명, 실제 공정 레시피, 실제 품질 기준은 포함하지 마세요.

```

---

## 9. LLM 응답

```markdown
# DisplayEdu Fab 교육용 가상 장애 대응 리포트

## 1. 교육용 가상 응답 안내
본 리포트는 **DisplayEdu Fab 가상 시나리오**를 기반으로 한 교육용 응답입니다. 실제 제조 기업의 사내 데이터, 설비명, 라인명, 알람 코드, 공정 기준, 조치 절차와 **무관**합니다. 실제 현장 조치 지시가 아닌, AI Agent 응답 구조 학습을 목적으로 작성되었습니다.

---

## 2. 요청 요약
- **라인 ID**: EDU-LINE-07
- **공정명**: Thin Film Deposition
- **장비 ID**: EQP-EV-03
- **알람 코드**: ALM-TEMP-402
- **요청**: `sample_alarm_logs.csv` 및 `alarm_manual.md` 참고하여 반복 발생 분석 및 대응 방향 제시

---

## 3. 로그 기반 관찰 내용
제공된 로그 요약(`sample_alarm_logs.csv` 기반)을 분석한 결과:
- **총 발생 횟수**: 14회
- **발생 기간**: 2026-05-01 09:05:12 ~ 2026-05-02 10:55:29 (약 25시간 50분)
- **심각도 분포**:
  - `WARNING`: 8회
  - `CRITICAL`: 6회
- **반복 특성**: 동일 장비(EQP-EV-03)에서 동일 알람 코드(ALM-TEMP-402)가 지속적으로 발생
- **최대 반복 횟수**: 14회 (전체 기간 내 단일 알람 기준)

---

## 4. 원인 후보 (교육용 가상 범주)
`alarm_manual.md`의 일반적 알람 설명 및 제조 환경 온도 알람 패턴을 고려한 **가상 원인 후보**:
1. **온도 센서 신호 불안정**: 센서 연결 불량, 노이즈, 또는 보정 오류 가능성
2. **설정 임계값 문제**: 공정 설정 온도 범위가 실제 운영 조건과 맞지 않을 가능성
3. **냉각/열 관리 시스템 이상**: 냉각수 유량 부족, 열교환기 성능 저하, 또는 히터 제어 불안정
4. **환경 요인**: 장비 주변 온도/습도 변동 또는 공기 흐름 방해
5. **일시적 공정 변동**: 레시피 실행 중 예외적인 부하 변화 (단, 반복 발생 시 근본 원인 가능성 낮음)

---

## 5. 1차 확인 항목 (로그 기반 가능 범위)
제공된 로그 데이터 내에서 확인 가능한 항목:
- 알람 발생 **시간 간격 패턴** (규칙적/불규칙적)
- 심각도(`WARNING`/`CRITICAL`) **변화 추이**
- 동일 기간 내 **다른 관련 알람** 동시 발생 여부 (예: ALM-FLOW, ALM-PRESSURE)
- 알람 발생 시점과 **공정 단계(Thin Film Deposition)**의 상관관계
- 장비 운영 로그의 **이벤트 타임스탬프**와의 일치 여부

---

## 6. 권장 조치 방향 (교육용 일반 조언)
- **모니터링 강화**: 해당 장비의 온도 로그를 실시간으로 추적하여 패턴 분석
- **알람 메뉴얼 참조**: `alarm_manual.md` 내 ALM-TEMP-402의 정의 및 표준 조치 절차 확인
- **운영 조건 점검**: 현재 공정 레시피의 온도 설정값이 정상 범위 내인지 확인
- **일시적 조치**: 알람 발생 시 자동/수동으로 공정을 안전 상태로 전환하는 프로토콜 준수

---

## 7. 추가 확인 필요 사항 (로그 외 가상 범위)
제공된 `sample_alarm_logs.csv`에는 포함되지 않아 추가 확인이 필요한 항목:
- **온도 센서 실제 측정값** 및 **설정값 대비 편차** 기록
- 장비 **유지보수 기록** (최근 센서 교체, 보정 일정)
- **냉각 시스템 성능 데이터** (유량, 압력, 온도 추이)
- **동일 라인(EDU-LINE-07) 내 다른 장비**의 유사 알람 발생 여부
- **공정 물질(Thin Film)의 특성 변화** (최근 배치 변경 등)

---

## 8. Agent 응답 시 주의 사항
- 본 응답은 **교육용 가상 시나리오** 결과이며, 실제 제조 현장의 조치 지시가 아닙니다.
- `sample_alarm_logs.csv` 및 `alarm_manual.md`에 명시된 정보만을 근거로 판단했습니다.
- 로그에 없는 데이터(예: 센서 정확도, 물리적 상태)에 대한 추측은 하지 않았습니다.
- "~할 수 있습니다", "~확인이 필요합니다"와 같은 **조심스러운 표현**을 사용하여 불확실성을 반영했습니다.
- 실제 사내 시스템명, 장비 제조사명, 공정 레시피, 품질 기준 등은 **일체 포함하지 않았습니다**.
```

---

## 10. 오류 및 주의 사항

- 오류 없음

---

## 11. 최종 메시지

- LangGraph mini graph 실행을 시작합니다.
- equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402 확인
- 필수 정보 있음 → search_log_node로 이동
- 관련 로그 14건 발견
- 관련 로그 14건 요약 완료 (최초=2026-05-01 09:05:12, 마지막=2026-05-02 10:55:29)
- LLM 요약 응답 생성을 위한 프롬프트를 생성했습니다.
- llm_client.py를 통한 LLM 응답 생성 완료

---

## 12. Chain과 LangGraph의 차이

- Chain은 “정해진 순서대로 처리하는 흐름”입니다.
- LangGraph는 State를 들고 Node 사이를 이동합니다.
- Conditional Edge를 사용하면 입력 정보 유무에 따라 다음 단계가 달라질 수 있습니다.
- 이번 예제에서는 equipment_id와 alarm_code가 있으면 로그 조회와 LLM 요약으로 이동하고, 없으면 추가 정보 요청으로 이동합니다.

---

## 13. LLM 호출부 교체 가능 구조 설명

- `src/day1/mini_graph_runner.py`는 `src/llm_client.py`만 호출합니다.
- `mini_graph_runner.py`는 `cloud_llm.py` 또는 `mock_llm.py`를 직접 알지 못합니다.
- `llm_client.py`가 Cloud LLM 또는 mock LLM을 선택합니다.
- 따라서 나중에 회사 정책에 따라 OpenAI, Claude, 사내 LLM, 로컬 LLM 등으로 바꾸더라도 Graph 본체 코드는 크게 바꾸지 않는 구조를 만들 수 있습니다.

---

## 14. 다음 실습 연결

7교시 `src/day1/day1_agent_v0_template.py`에서는 로그 조회, 매뉴얼 검색, 프롬프트 생성, LLM 응답 생성을 하나의 Day1 Agent v0 흐름으로 통합합니다.


---

# 정보 부족 케이스: 교육용 가상 실습 결과

> 이 결과는 AI Agent Architecture 강의용 가상 데이터로 생성되었습니다.  
> 실제 제조 기업의 사내 데이터, 실제 설비명, 실제 라인명, 실제 알람 코드, 실제 공정 조건과 무관합니다.  
> 이 파일은 LangGraph의 State, Node, Edge, Conditional Edge와 LLM 호출부 분리 구조를 이해하기 위한 교육용 산출물입니다.

---

## 1. 실습 목적

이번 실습은 Chain과 Graph의 차이를 이해하기 위한 미니 실습입니다.  
Chain은 정해진 순서대로 실행되지만, Graph는 조건에 따라 다음 단계가 달라질 수 있습니다.  
또한 LLM 호출은 `src/day1/mini_graph_runner.py`에서 직접 처리하지 않고 `src/llm_client.py`로 분리합니다.

---

## 2. 실행 케이스 이름

- 정보 부족 케이스

---

## 3. 입력 정보

| 항목 | 값 |
|---|---|
| user_query | ALM-TEMP-402 교육용 알람이 반복 발생한 것 같습니다. 어떤 정보를 더 확인해야 하나요? |
| line_id | EDU-LINE-07 |
| process_name | Thin Film Deposition |
| equipment_id | 없음 |
| alarm_code | ALM-TEMP-402 |

---

## 4. LangGraph 흐름 요약

```text
START
 → start_node
 → parse_query_node
 → check_required_info_node
 → 조건부 분기
    - 필수 정보 있음:
      search_log_node
      → summarize_result_node
      → build_llm_prompt_node
      → generate_llm_response_node
      → END

    - 필수 정보 부족:
      ask_more_info_node
      → END
```

---

## 5. Node 실행 Trace

| 순서 | Node | 입력 요약 | 출력 요약 | 다음 이동 |
|---:|---|---|---|---|
| 1 | start_node | 초기 State 입력 | 실행 시작 메시지 추가 | parse_query_node |
| 2 | parse_query_node | user_query와 query 필드 확인 | equipment_id=없음, alarm_code=ALM-TEMP-402 확인 | check_required_info_node |
| 3 | check_required_info_node | equipment_id와 alarm_code 존재 여부 확인 | 필수 정보 부족 → ask_more_info_node로 이동 | ask_more_info_node |
| 4 | ask_more_info_node | 누락 정보: equipment_id | 추가 정보 요청 메시지 생성, LLM 호출 없음 | END |

---

## 6. Conditional Edge 분기 결과

- next_action: `ask_more_info`
- 분기 결과: ask_more_info_node로 이동

---

## 7. 로그 요약

```json
{}
```

---

## 8. 생성된 LLM 프롬프트

```markdown
정보 부족 케이스이므로 LLM 프롬프트를 생성하지 않았습니다.
```

---

## 9. LLM 응답

```markdown
정보 부족 케이스이므로 LLM을 호출하지 않았습니다.
```

---

## 10. 오류 및 주의 사항

- 오류 없음

---

## 11. 최종 메시지

- LangGraph mini graph 실행을 시작합니다.
- equipment_id=없음, alarm_code=ALM-TEMP-402 확인
- 필수 정보 부족 → ask_more_info_node로 이동
- 알람 원인을 확인하려면 equipment_id 값이 필요합니다. 교육용 예시로는 equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402를 사용할 수 있습니다.

---

## 12. Chain과 LangGraph의 차이

- Chain은 “정해진 순서대로 처리하는 흐름”입니다.
- LangGraph는 State를 들고 Node 사이를 이동합니다.
- Conditional Edge를 사용하면 입력 정보 유무에 따라 다음 단계가 달라질 수 있습니다.
- 이번 예제에서는 equipment_id와 alarm_code가 있으면 로그 조회와 LLM 요약으로 이동하고, 없으면 추가 정보 요청으로 이동합니다.

---

## 13. LLM 호출부 교체 가능 구조 설명

- `src/day1/mini_graph_runner.py`는 `src/llm_client.py`만 호출합니다.
- `mini_graph_runner.py`는 `cloud_llm.py` 또는 `mock_llm.py`를 직접 알지 못합니다.
- `llm_client.py`가 Cloud LLM 또는 mock LLM을 선택합니다.
- 따라서 나중에 회사 정책에 따라 OpenAI, Claude, 사내 LLM, 로컬 LLM 등으로 바꾸더라도 Graph 본체 코드는 크게 바꾸지 않는 구조를 만들 수 있습니다.

---

## 14. 다음 실습 연결

7교시 `src/day1/day1_agent_v0_template.py`에서는 로그 조회, 매뉴얼 검색, 프롬프트 생성, LLM 응답 생성을 하나의 Day1 Agent v0 흐름으로 통합합니다.

