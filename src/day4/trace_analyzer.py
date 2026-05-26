"""
Day4 MCP Call Trace 분석기 - 초보자 교육용 단순화 버전

역할:
- MCP Tool 호출 기록(JSONL)을 읽습니다.
- 전체 호출 수, 성공/실패 수, Tool별 호출 수, 평균 latency를 계산합니다.
- 느린 호출 Top 5와 실패 호출 목록을 JSON/Markdown 보고서로 저장합니다.

필요 패키지:
    pip install chevron

주의:
- 실제 사내 데이터나 민감정보를 사용하지 않는 교육용 예제입니다.
- 프로젝트 루트 경로를 코드에 직접 적지 않습니다.
- Markdown 보고서 양식은 templates/day4/trace_review_result.mustache 파일에 분리합니다.
"""

from pathlib import Path
from datetime import datetime
from collections import defaultdict
import json
import chevron


# 현재 파일 위치: 프로젝트루트/src/day4/trace_analyzer_YYYYMMDD_HHMMSS.py
# parents[0] = day4, parents[1] = src, parents[2] = 프로젝트 루트

def find_project_root():
    current_file = Path(__file__).resolve()
    return current_file.parents[2]


def find_trace_file(project_root):
    candidate_paths = [
        project_root / "outputs" / "day3" / "mcp_call_trace.jsonl",
        project_root / "mcp_call_trace.jsonl",
        project_root / "data" / "day4" / "mcp_call_trace_sample.jsonl",
    ]

    for path in candidate_paths:
        if path.exists():
            return path

    return None


def load_trace(trace_path):
    records = []

    with trace_path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))

    return records


def make_average(values):
    if not values:
        return 0

    return round(sum(values) / len(values), 2)


def analyze_trace(records, trace_path):
    success_count = 0
    error_count = 0
    latencies = []
    tool_groups = defaultdict(list)
    slow_candidates = []
    failed_calls = []

    for record in records:
        status = str(record.get("status", "")).lower()
        tool_name = record.get("tool_name") or "UNKNOWN_TOOL"
        error_code = record.get("error_code")

        if status == "success":
            success_count += 1
        elif status in ("error", "failed"):
            error_count += 1

        latency = None
        latency_value = record.get("latency_ms")
        if latency_value is not None:
            try:
                latency = float(latency_value)
            except (TypeError, ValueError):
                latency = None

        if latency is not None:
            latencies.append(latency)
            slow_candidates.append(
                {
                    "timestamp": record.get("timestamp", ""),
                    "tool_name": tool_name,
                    "status": record.get("status", ""),
                    "latency_ms": round(latency, 2),
                }
            )

        tool_groups[tool_name].append(
            {
                "status": status,
                "latency_ms": latency,
            }
        )

        if status in ("error", "failed") or error_code is not None:
            tool_output = record.get("tool_output")
            message = ""
            if isinstance(tool_output, dict):
                message = tool_output.get("message", "")

            failed_calls.append(
                {
                    "timestamp": record.get("timestamp", ""),
                    "tool_name": tool_name,
                    "status": record.get("status", ""),
                    "error_code": error_code or "",
                    "message": message,
                }
            )

    tool_summary = []
    for tool_name in sorted(tool_groups):
        tool_records = tool_groups[tool_name]
        tool_latencies = [item["latency_ms"] for item in tool_records if item["latency_ms"] is not None]
        tool_success_count = sum(1 for item in tool_records if item["status"] == "success")
        tool_error_count = sum(1 for item in tool_records if item["status"] in ("error", "failed"))

        tool_summary.append(
            {
                "tool_name": tool_name,
                "call_count": len(tool_records),
                "success_count": tool_success_count,
                "error_count": tool_error_count,
                "average_latency_ms": make_average(tool_latencies),
            }
        )

    slow_candidates.sort(key=lambda item: item["latency_ms"], reverse=True)
    slow_calls = []
    for index, item in enumerate(slow_candidates[:5], start=1):
        item["rank"] = index
        slow_calls.append(item)

    return {
        "input_file": str(trace_path),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "overall": {
            "total_records": len(records),
            "success_count": success_count,
            "error_count": error_count,
            "average_latency_ms": make_average(latencies),
            "max_latency_ms": round(max(latencies), 2) if latencies else 0,
            "min_latency_ms": round(min(latencies), 2) if latencies else 0,
        },
        "tool_summary": tool_summary,
        "slow_calls": slow_calls,
        "failed_calls": failed_calls,
    }


def save_outputs(project_root, report):
    output_dir = project_root / "outputs" / "day4"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_output_path = output_dir / "trace_summary.json"
    markdown_output_path = output_dir / "trace_review_result.md"
    template_path = project_root / "templates" / "day4" / "trace_review_result.mustache"

    with json_output_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    template_text = template_path.read_text(encoding="utf-8")
    markdown_text = chevron.render(template_text, report)
    markdown_output_path.write_text(markdown_text, encoding="utf-8")

    return json_output_path, markdown_output_path


def main():
    print("[Day4 Trace Analyzer]")

    project_root = find_project_root()
    trace_path = find_trace_file(project_root)

    if trace_path is None:
        print("[안내] 분석할 MCP Call Trace 파일을 찾지 못했습니다.")
        print("[안내] 아래 위치 중 하나에 파일을 준비한 뒤 다시 실행해 주세요.")
        print("- outputs/day3/mcp_call_trace.jsonl")
        print("- mcp_call_trace.jsonl")
        print("- data/day4/mcp_call_trace_sample.jsonl")
        return

    records = load_trace(trace_path)
    report = analyze_trace(records, trace_path)
    save_outputs(project_root, report)

    overall = report["overall"]

    print(f"입력 파일: {trace_path}")
    print(f"전체 Trace 개수: {overall['total_records']}")
    print(f"성공: {overall['success_count']}")
    print(f"실패: {overall['error_count']}")
    print("결과 저장:")
    print("- outputs/day4/trace_summary.json")
    print("- outputs/day4/trace_review_result.md")


if __name__ == "__main__":
    main()
