# -*- coding: utf-8 -*-
"""
Day5 mcp_client_final 패키지 (Agent 판단 흐름 시각화 예제 — 최종 단계)

[이 패키지가 무엇인가]
mcp_client04(자연어 → MCP 연결 → DB/RAG 결과를 보여 주는 '조회/보고 UI')의 다음 단계로,
Agent 가 '조회 프로그램'이 아니라 **의도를 판단하고, Tool 을 선택하고, 여러 결과를 비교·검증하고,
다음 확인 항목을 제안하는 실행 주체**임을 단계별로 보여 주는 교육용 예제입니다.

[mcp_client04 와의 차이]
- mcp_client04 : 질문을 그대로 조회해서 '결과'를 보여 준다(supervisor 단일 경로 1 Tool).
- mcp_client_final : 질문의 '의도'를 먼저 판단하고, 여러 Tool 을 조합해 호출하며, DB↔RAG 를
  비교·검증하고, 교육용 점검 등급과 다음 확인 항목까지 제안한다. 화면의 주인공은 '결과'가 아니라
  'Agent 의 판단 단계'다.

[구성 — 4개 파일]
- agent_flow.py    : 규칙 기반 판단 흐름(질문 분석 → 의도 분류 → Tool 선택 → Tool 호출 →
                     DB/RAG 요약 → 비교/Evidence Check → 교육용 점검 등급 → 다음 확인 항목).
- scenarios.py     : 수업 시연용 예시 질문 3개(DB만 / RAG만 / DB+RAG)와 설명 문구.
- streamlit_app.py : 위 판단 흐름을 '세로 단계형' 화면으로 시각화하는 얇은 UI.

[경계 — 매우 중요]
- MCP 서버는 mcp_server03 이며 절대 수정하지 않는다. 기존 DB/RAG Tool 만 사용한다(execute_sql 미사용).
- 서버 내부 모듈(repositories/db_access/rag_*)을 직접 import 하지 않는다. 데이터 접근은 MCP Tool 호출뿐.
- mcp_client04 에서는 '실행 호출 방식'(config / ToolCaller)만 얇게 재사용하고, 화면·판단 흐름은 새로 작성한다.
- LLM 필수 의존을 만들지 않는다(판단 흐름은 규칙 기반).
- DB/RAG 메타데이터(data_source / retrieval_source / fallback_used / mock_fallback)는 숨기지 않고
  화면에 정직하게 표시한다. 서버 미기동/Tool 실패는 성공처럼 포장하지 않고 ERROR 로 표시한다.
"""
