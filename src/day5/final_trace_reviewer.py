"""
Day5 Final Trace Reviewer

수강생용 단순화 버전입니다.

핵심 메시지:
- Trace는 Agent 실행의 블랙박스입니다.
- Agent가 어떤 Tool을 사용했는지 확인해야 합니다.
- Guardrail이 작동했는지 확인해야 합니다.
- 결과 파일이 생성되었는지 확인해야 합니다.
- Trace가 없으면 "아직 생성되지 않음"으로 확인하며, 임의 샘플 Trace를 만들지 않습니다.

주의:
- 실제 사내 데이터나 실제 내부 시스템명을 사용하지 않습니다.
- 외부 API, DB, MCP Server, LLM API를 호출하지 않습니다.
- pandas, langchain, langgraph, chromadb 같은 외부 패키지를 사용하지 않습니다.

필요 패키지:
pip install chevron
"""

from pathlib import Path
import json

import chevron


EDUCATION_MESSAGE = (
    "Trace는 Agent가 어떤 판단을 했고 어떤 Tool을 호출했으며 "
    "어떤 결과를 만들었는지 확인하는 실행 기록입니다."
)


# 1
def find_project_root():
    """현재 파일 위치를 기준으로 프로젝트 루트를 계산합니다."""
    return Path(__file__).resolve().parents[2]


# 2
def read_jsonl(path):
    """JSONL 파일을 읽고, 깨진 JSON 줄은 건너뜁니다."""
    result = {"records": [], "broken_row_count": 0}

    if not path.exists():
        return result

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                result["records"].append(item)
        except json.JSONDecodeError:
            result["broken_row_count"] += 1

    return result


# 3
def load_trace_files(project_root):
    """Day5의 주요 Trace 파일 2개를 읽습니다. 없는 파일은 샘플을 만들지 않습니다."""
    final_path = project_root / "outputs" / "day5" / "final_mcp_call_trace.jsonl"
    action_path = project_root / "outputs" / "day5" / "action_lab_trace.jsonl"

    final_result = read_jsonl(final_path)
    action_result = read_jsonl(action_path)

    trace_files = [
        {
            "name": "final_mcp_call_trace",
            "path": "outputs/day5/final_mcp_call_trace.jsonl",
            "exists": final_path.exists(),
            "row_count": len(final_result["records"]),
            "broken_row_count": final_result["broken_row_count"],
        },
        {
            "name": "action_lab_trace",
            "path": "outputs/day5/action_lab_trace.jsonl",
            "exists": action_path.exists(),
            "row_count": len(action_result["records"]),
            "broken_row_count": action_result["broken_row_count"],
        },
    ]

    return {
        "final_records": final_result["records"],
        "action_records": action_result["records"],
        "trace_files": trace_files,
        "broken_row_count": final_result["broken_row_count"] + action_result["broken_row_count"],
    }


# 4
def summarize_traces(final_records, action_records, broken_row_count):
    """Trace row 수, Tool 사용 횟수, Guardrail 이벤트, Action 이벤트를 단순 요약합니다."""
    tool_counter = {}
    guardrail_event_count = 0
    action_event_count = 0

    for record in final_records:
        tool_name = record.get("tool_name")
        if tool_name:
            tool_counter[tool_name] = tool_counter.get(tool_name, 0) + 1
        if record.get("guardrail_result") or record.get("tool_name") == "GUARDRAIL":
            guardrail_event_count += 1

    for record in action_records:
        used_tools = record.get("used_tools", [])
        if isinstance(used_tools, list):
            for tool_name in used_tools:
                tool_counter[str(tool_name)] = tool_counter.get(str(tool_name), 0) + 1
        if record.get("guardrail_result") or record.get("tool_name") == "GUARDRAIL":
            guardrail_event_count += 1
        if record.get("action_type") or record.get("action_name"):
            action_event_count += 1

    tool_counts = [
        {"tool_name": tool_name, "count": tool_counter[tool_name]}
        for tool_name in sorted(tool_counter)
    ]

    summary = {
        "final_trace_count": len(final_records),
        "action_trace_count": len(action_records),
        "total_trace_count": len(final_records) + len(action_records),
        "tool_kind_count": len(tool_counts),
        "guardrail_event_count": guardrail_event_count,
        "action_event_count": action_event_count,
        "broken_row_count": broken_row_count,
    }

    return {"summary": summary, "tool_counts": tool_counts}


# 5
def check_output_files(project_root):
    """Day5 주요 결과 파일 생성 여부를 확인합니다."""
    targets = [
        ("final_incident_report", "outputs/day5/final_incident_report.md"),
        ("final_mcp_call_trace", "outputs/day5/final_mcp_call_trace.jsonl"),
        ("action_lab_result_md", "outputs/day5/action_lab_result.md"),
        ("action_lab_result_json", "outputs/day5/action_lab_result.json"),
        ("action_lab_trace", "outputs/day5/action_lab_trace.jsonl"),
        ("edge_case_test_results_md", "outputs/day5/edge_case_test_results.md"),
        ("edge_case_test_results_json", "outputs/day5/edge_case_test_results.json"),
    ]

    outputs = []
    for name, relative_path in targets:
        path = project_root / relative_path
        outputs.append({
            "name": name,
            "path": relative_path,
            "status": "생성됨" if path.exists() else "없음",
        })

    return outputs


# 6
def main():
    """Trace 로딩, 요약, 결과 파일 확인, Markdown/JSON 저장을 수행합니다."""
    project_root = find_project_root()
    output_dir = project_root / "outputs" / "day5"
    template_dir = project_root / "templates" / "day5"
    output_dir.mkdir(parents=True, exist_ok=True)
    template_dir.mkdir(parents=True, exist_ok=True)

    trace_data = load_trace_files(project_root)
    summary_data = summarize_traces(
        trace_data["final_records"],
        trace_data["action_records"],
        trace_data["broken_row_count"],
    )
    outputs = check_output_files(project_root)

    data = {
        "summary": summary_data["summary"],
        "tool_counts": summary_data["tool_counts"],
        "outputs": outputs,
        "trace_files": trace_data["trace_files"],
        "education_message": EDUCATION_MESSAGE,
    }

    template_path = template_dir / "final_trace_summary.mustache"
    template_text = template_path.read_text(encoding="utf-8")
    markdown_text = chevron.render(template_text, data)

    markdown_path = output_dir / "final_trace_summary.md"
    json_path = output_dir / "final_trace_summary.json"

    markdown_path.write_text(markdown_text, encoding="utf-8-sig")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[Day5 Final Trace Reviewer]")
    print(f"- Final MCP Trace row 수: {data['summary']['final_trace_count']}")
    print(f"- Action Lab Trace row 수: {data['summary']['action_trace_count']}")
    print(f"- Tool 사용 종류 수: {data['summary']['tool_kind_count']}")
    print(f"- Guardrail 이벤트 수: {data['summary']['guardrail_event_count']}")
    print(f"- 깨진 JSONL row 수: {data['summary']['broken_row_count']}")
    print("- 결과 저장 경로:")
    print("  - outputs/day5/final_trace_summary.md")
    print("  - outputs/day5/final_trace_summary.json")


if __name__ == "__main__":
    main()
