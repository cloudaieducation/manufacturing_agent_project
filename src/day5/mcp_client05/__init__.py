# -*- coding: utf-8 -*-
"""
Day5 mcp_client05 패키지 (Streamlit UI 전용 — 화면 단계)

[이 패키지가 무엇인가]
mcp_client04(실제 MCP transport + ToolCaller + LangGraph + Agent + ThreadPool 병렬 실행 엔진)의
다음 단계로, 그 실행 결과를 '웹 화면'에서 확인하는 Streamlit UI 단계 패키지입니다.

[경계 — 매우 중요]
- 핵심 실행 로직(graph/agents/mcp_tools/transport/runner/config)은 mcp_client04 에 그대로 남아 있습니다.
- mcp_client05 는 그 로직을 '복사'하지 않고, mcp_client04 의 public 계층(runner/config)을
  import 해서 '재사용'합니다(`from day5.mcp_client04 import config, runner`).
- 따라서 mcp_client05 는 '화면 계층'이며, graph/agents/mcp_tools/transport 를 복사하지 않습니다.
- 서버(mcp_server03) 내부 모듈(repositories/db_access/rag_*/Tool 함수)도 직접 import 하지 않습니다.
  모든 데이터 접근은 mcp_client04 의 ToolCaller(=runner)를 통해서만 이뤄집니다.

[구성]
- streamlit_app.py : mcp_client04 의 runner 를 호출해 결과를 보여 주는 얇은 교육용 웹 UI.

[실행]
    streamlit run src/day5/mcp_client05/streamlit_app.py
  (uv 환경) uv run streamlit run src/day5/mcp_client05/streamlit_app.py
  → python -m 진입점(__main__.py)은 두지 않는다(Streamlit 은 파일을 스크립트로 실행).
"""
