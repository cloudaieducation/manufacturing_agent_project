# -*- coding: utf-8 -*-
"""
mcp_server01.mcp_server TDD 테스트

대상:
- src/day5/mcp_server01/mcp_server.py

원칙:
- 외부 API/LLM/DB/ChromaDB/FastMCP 실제 서버 실행 없음
- 테스트 전용 JSONL 로그 저장 확인
- mcp_server.py의 진입점 orchestration만 검증
"""

import os
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch

# day5.mcp_server01 패키지를 import 하려면 <root>/src 가 sys.path 에 있어야 한다.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from day5.mcp_server01 import mcp_server


class TestMcpServer01EntryPoints(unittest.TestCase):

    def setUp(self):
        self.project_root = Path(__file__).resolve().parents[2]
        self.test_log_dir = self.project_root / "outputs" / "day5" / "mcp_server01" / "test_logs"
        self.test_log_path = self.test_log_dir / "mcp_server01.jsonl"
        self.test_log_dir.mkdir(parents=True, exist_ok=True)
        if self.test_log_path.exists():
            self.test_log_path.unlink()
        self._old_log_dir = os.environ.get("MCP_SERVER01_LOG_DIR")
        os.environ["MCP_SERVER01_LOG_DIR"] = str(self.test_log_dir)

    def tearDown(self):
        if self._old_log_dir is None:
            os.environ.pop("MCP_SERVER01_LOG_DIR", None)
        else:
            os.environ["MCP_SERVER01_LOG_DIR"] = self._old_log_dir

    # ------------------------------------------------------------------
    # 로그 검증 helper
    # ------------------------------------------------------------------
    def _read_test_log_lines(self):
        self.assertTrue(self.test_log_path.exists(), "테스트 로그 파일이 생성되어야 합니다.")
        text = self.test_log_path.read_text(encoding="utf-8").strip()
        self.assertTrue(text, "테스트 로그 파일에 최소 1줄 이상 기록되어야 합니다.")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def _assert_log_contains_event_type(self, event_type):
        lines = self._read_test_log_lines()
        event_types = [line.get("event_type") for line in lines]
        self.assertIn(event_type, event_types)

    def _assert_log_contains_any_event_type(self, event_types):
        lines = self._read_test_log_lines()
        actual_event_types = [line.get("event_type") for line in lines]
        self.assertTrue(
            any(event_type in actual_event_types for event_type in event_types),
            f"로그에 {event_types} 중 하나가 있어야 합니다. actual={actual_event_types}",
        )

    def _assert_log_does_not_expose_sensitive_values(self):
        if not self.test_log_path.exists():
            return
        text = self.test_log_path.read_text(encoding="utf-8")
        forbidden_values = [
            "SECRETabc123",
            "Bearer ",
            "internal.example",
            "http://",
            "https://",
        ]
        for value in forbidden_values:
            self.assertNotIn(value, text)

    # ------------------------------------------------------------------
    # 테스트
    # ------------------------------------------------------------------
    def test_01_import_module(self):
        expected_callables = [
            "list_mcp_tools",
            "call_mcp_tool",
            "call_select_tools_for_manufacturing_query",
            "call_validate_tool_plan",
            "call_execute_selected_tools",
            "call_execute_query",
            "create_fastmcp_server",
            "run_fastmcp_server",
        ]
        for name in expected_callables:
            self.assertTrue(hasattr(mcp_server, name), f"{name} 함수가 존재해야 합니다.")
            self.assertTrue(callable(getattr(mcp_server, name)), f"{name} 은 callable 이어야 합니다.")

    def test_02_list_mcp_tools_excludes_forbidden_sql_tools(self):
        fake_schemas = [
            {"name": "get_equipment_status"},
            {"name": "search_manual"},
        ]
        with patch.object(mcp_server.mcp_schemas, "build_mcp_tool_schemas",
                          return_value=fake_schemas) as mock_build:
            result = mcp_server.list_mcp_tools()

        self.assertIsInstance(result, list)
        mock_build.assert_called_once_with()
        names = [item.get("name") for item in result]
        self.assertNotIn("execute_sql", names)

    def test_03_call_mcp_tool_rejects_forbidden_sql_tool_and_writes_log(self):
        with patch.object(mcp_server, "FORBIDDEN_SQL_TOOLS", {"execute_sql"}), \
             patch.object(mcp_server, "ALLOWED_TOOLS", {"get_equipment_status"}), \
             patch.object(mcp_server.tool_executor, "build_single_tool_plan") as mock_build, \
             patch.object(mcp_server.tool_executor, "execute_tool_plan") as mock_execute:
            result = mcp_server.call_mcp_tool("execute_sql", {"query": "select * from users"})

        self.assertEqual(result.get("status"), "rejected")
        self.assertEqual(result.get("validation_status"), "FAIL")
        self.assertEqual(result.get("executed_count"), 0)
        message = result.get("message", "")
        self.assertTrue(("SQL" in message) or ("Tool" in message) or ("금지" in message))
        mock_build.assert_not_called()
        mock_execute.assert_not_called()
        self._assert_log_contains_any_event_type(["tool_rejected", "tool_error"])
        self._assert_log_does_not_expose_sensitive_values()

    def test_04_call_mcp_tool_rejects_unknown_tool_and_writes_log(self):
        with patch.object(mcp_server, "FORBIDDEN_SQL_TOOLS", {"execute_sql"}), \
             patch.object(mcp_server, "ALLOWED_TOOLS", {"get_equipment_status"}), \
             patch.object(mcp_server.tool_executor, "build_single_tool_plan") as mock_build, \
             patch.object(mcp_server.tool_executor, "execute_tool_plan") as mock_execute:
            result = mcp_server.call_mcp_tool("unknown_tool", {})

        self.assertEqual(result.get("status"), "rejected")
        self.assertEqual(result.get("validation_status"), "FAIL")
        self.assertEqual(result.get("executed_count"), 0)
        mock_build.assert_not_called()
        mock_execute.assert_not_called()
        self._assert_log_contains_any_event_type(["tool_rejected", "tool_error"])
        self._assert_log_does_not_expose_sensitive_values()

    def test_05_call_mcp_tool_executes_allowed_tool_via_executor_and_writes_log(self):
        fake_plan = {"plan": [{"tool_name": "get_equipment_status",
                               "arguments": {"equipment_id": "EQP-EV-03"}}]}
        fake_result = {
            "status": "executed",
            "validation_status": "PASS",
            "executed_count": 1,
            "results": [{"tool_name": "get_equipment_status",
                         "result": {"equipment_id": "EQP-EV-03"}}],
            "issues": [],
            "message": "ok",
        }
        with patch.object(mcp_server, "FORBIDDEN_SQL_TOOLS", {"execute_sql"}), \
             patch.object(mcp_server, "ALLOWED_TOOLS", {"get_equipment_status"}), \
             patch.object(mcp_server.tool_executor, "build_single_tool_plan",
                          return_value=fake_plan) as mock_build, \
             patch.object(mcp_server.tool_executor, "execute_tool_plan",
                          return_value=fake_result) as mock_execute:
            result = mcp_server.call_mcp_tool("get_equipment_status", {"equipment_id": "EQP-EV-03"})

        self.assertEqual(result.get("status"), "executed")
        mock_build.assert_called_once_with("get_equipment_status", {"equipment_id": "EQP-EV-03"})
        mock_execute.assert_called_once_with(fake_plan, user_query="")
        self._assert_log_contains_any_event_type(["tool_called", "tool_executed"])
        self._assert_log_does_not_expose_sensitive_values()

    def test_06_select_tools_logs_selection_summary(self):
        # LLM 전용 기본 정책(strict): LLM 실패 시 rule fallback 으로 대체 실행하지 않고
        # unavailable/llm_error 등 strict 실패 메타데이터를 그대로 통과시킨다.
        fake_selection = {
            "tool_plan": {"plan": []},
            "generation_source": "unavailable",
            "fallback_used": False,
            "error_message": "LLM 실패 또는 비정상 응답으로 strict mode 처리",
        }
        with patch.object(mcp_server.tool_selector, "select_tool_plan_with_llm",
                          return_value=fake_selection) as mock_select:
            result = mcp_server.call_select_tools_for_manufacturing_query("ALM-TEMP-402 조치 방향")

        self.assertEqual(result.get("generation_source"), "unavailable")
        self.assertIs(result.get("fallback_used"), False)
        self._assert_log_contains_event_type("tool_selected")
        self._assert_log_does_not_expose_sensitive_values()

    def test_07_validate_tool_plan_uses_dry_run_and_writes_log(self):
        fake_result = {
            "status": "dry_run",
            "validation_status": "PASS",
            "executed_count": 0,
            "results": [],
            "issues": [],
        }
        with patch.object(mcp_server.tool_executor, "execute_tool_plan",
                          return_value=fake_result) as mock_execute:
            result = mcp_server.call_validate_tool_plan({"plan": []}, user_query="test query")

        self.assertEqual(result.get("validation_status"), "PASS")
        self.assertIs(result.get("executable"), True)
        self.assertEqual(mock_execute.call_args.kwargs.get("dry_run"), True)
        self._assert_log_contains_event_type("tool_validated")
        self._assert_log_does_not_expose_sensitive_values()

    def test_08_execute_selected_tools_delegates_to_executor_and_writes_log(self):
        fake_result = {
            "status": "executed",
            "validation_status": "PASS",
            "executed_count": 1,
            "results": [],
            "issues": [],
        }
        with patch.object(mcp_server.tool_executor, "execute_tool_plan",
                          return_value=fake_result) as mock_execute:
            result = mcp_server.call_execute_selected_tools({"plan": []}, user_query="query",
                                                            dry_run=False)

        mock_execute.assert_called_once_with({"plan": []}, user_query="query", dry_run=False)
        self.assertEqual(result.get("status"), "executed")
        self._assert_log_contains_event_type("tool_executed")
        self._assert_log_does_not_expose_sensitive_values()

    def test_09_execute_query_adds_selection_metadata_and_writes_log(self):
        # LLM 전용 기본 정책(strict): 기본 호출에서 LLM 실패 시 rule fallback 으로
        # 대체 실행하지 않고, strict 실패 메타데이터를 결과 dict 에 그대로 덧붙인다.
        fake_selection = {
            "tool_plan": {"plan": []},
            "generation_source": "unavailable",
            "fallback_used": False,
            "error_message": "LLM 실패 또는 비정상 응답으로 strict mode 처리",
        }
        fake_result = {
            "status": "executed",
            "validation_status": "PASS",
            "executed_count": 1,
            "results": [],
            "issues": [],
        }
        with patch.object(mcp_server.tool_selector, "select_tool_plan_with_llm",
                          return_value=fake_selection) as mock_select, \
             patch.object(mcp_server.tool_executor, "execute_tool_plan",
                          return_value=fake_result) as mock_execute:
            result = mcp_server.call_execute_query("ALM-TEMP-402 조치 방향")

        self.assertEqual(result.get("generation_source"), "unavailable")
        self.assertIs(result.get("fallback_used"), False)
        self.assertEqual(result.get("selection_error_message"),
                         "LLM 실패 또는 비정상 응답으로 strict mode 처리")
        mock_select.assert_called_once()
        mock_execute.assert_called_once()
        self._assert_log_contains_event_type("tool_selected")
        self._assert_log_contains_event_type("tool_executed")
        self._assert_log_does_not_expose_sensitive_values()

    def test_10_create_fastmcp_server_registers_tools_under_installed_fastmcp(self):
        # FastMCP 설치 전제: create_fastmcp_server() 가 server 객체를 생성한다.
        # (server.run() 은 블로킹이므로 실행하지 않고, 생성/등록 구조만 확인한다.)
        server = mcp_server.create_fastmcp_server()
        self.assertIsNotNone(server, "FastMCP 설치 전제에서 server 객체가 생성되어야 합니다.")
        # MCP Tool 진입점 wrapper(_fastmcp_*) 6개가 유지되는지 확인.
        for name in [
            "_fastmcp_execute_query",
            "_fastmcp_select_tools_for_manufacturing_query",
            "_fastmcp_validate_tool_plan",
            "_fastmcp_execute_selected_tools",
            "_fastmcp_call_mcp_tool",
            "_fastmcp_list_mcp_tools",
        ]:
            self.assertTrue(callable(getattr(mcp_server, name, None)),
                            f"{name} wrapper 가 유지되어야 합니다.")
        self._assert_log_does_not_expose_sensitive_values()

    def test_11_test_log_file_is_jsonl_and_has_no_sensitive_values(self):
        with patch.object(mcp_server, "FORBIDDEN_SQL_TOOLS", {"execute_sql"}), \
             patch.object(mcp_server, "ALLOWED_TOOLS", {"get_equipment_status"}), \
             patch.object(mcp_server.tool_executor, "build_single_tool_plan") as mock_build, \
             patch.object(mcp_server.tool_executor, "execute_tool_plan") as mock_execute:
            mcp_server.call_mcp_tool("execute_sql", {"query": "select * from users"})
            mock_build.assert_not_called()
            mock_execute.assert_not_called()

        lines = self._read_test_log_lines()
        self.assertGreaterEqual(len(lines), 1)
        for line in lines:
            self.assertIn("event_type", line)
        self._assert_log_does_not_expose_sensitive_values()


if __name__ == "__main__":
    unittest.main(verbosity=2)
