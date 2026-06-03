# -*- coding: utf-8 -*-
"""
Day5 mcp_server02 패키지 마커.

이 파일은 mcp_server02 를 import 가능한 패키지로 만들기 위한 최소 마커입니다.
하위 모듈(security / mcp_schemas / tool_selector / tool_executor /
equipment_data / manual_search / mcp_server)을 여기서 import/export 하지 않습니다.

이유:
- __init__ 에서 모든 모듈을 끌어오면, 한 모듈의 import 실패가 패키지 전체 import 를
  깨뜨립니다. Day5 MCP Server 는 "MCP SDK 없이도, LLM API Key 없이도 import 가
  깨지지 않는다"를 보장해야 하므로, 의존 로딩을 각 모듈 사용 시점으로 미룹니다.
- 따라서 각 모듈은 항상 직접 경로로 import 합니다.
    예) from day5.mcp_server02.mcp_server import list_mcp_tools

import 가 동작하려면 <root>/src 가 sys.path 에 있어야 합니다(day4 와 동일한 규약).
"""
