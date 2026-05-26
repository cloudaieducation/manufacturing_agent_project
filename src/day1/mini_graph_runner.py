"""
삼성디스플레이 재직자 대상 AI Agent Architecture 1일차 6교시 단순 LangGraph 실습 파일입니다.

이 파일은 초보자가 위에서 아래로 실행 흐름을 이해할 수 있도록
핵심 코드를 run_mini_graph() 함수 안에 모아 둔 교육용 단순 버전입니다.

실습 주제:
- LangGraph의 State, Node, Edge, Conditional Edge 이해
- State가 Node 사이를 이동하며 수정되는 흐름 이해
- 필수 정보가 있으면 로그 검색으로 이동하고, 부족하면 추가 정보 요청으로 이동하는 조건부 분기 이해
- Prompt와 Trace Report를 Mustache 템플릿으로 분리하는 구조 이해

중요:
- 이 파일은 실제 LangGraph를 사용합니다.
- 이 파일은 Gemini/OpenAI/Anthropic/Ollama/NVIDIA SDK를 직접 import하지 않습니다.
- LLM 호출은 llm_client.py의 generate_response(prompt)를 통해서만 수행합니다.
- API Key, Authorization, token, password, secret 값은 출력하거나 저장하지 않습니다.
- 실제 사내 데이터가 아니라 DisplayEdu Fab 교육용 가상 데이터만 사용합니다.
"""

from pathlib import Path
import json
import sys

import pandas as pd
import pystache
from langgraph.graph import END, START, StateGraph


def run_mini_graph():
    """
    1일차 LangGraph 미니 실습을 실행합니다.

    이 함수는 초보자가 Graph 기반 Agent 흐름을 이해할 수 있도록
    핵심 코드를 한 곳에 모아 둔 교육용 단순 버전입니다.

    실행 흐름:
    1. 프로젝트 경로를 찾습니다.
    2. sample_query.json과 sample_alarm_logs.csv를 읽습니다.
    3. 정상 케이스와 정보 부족 케이스의 초기 state를 만듭니다.
    4. LangGraph Node들을 내부 함수로 정의합니다.
    5. Conditional Edge를 포함한 Graph를 구성합니다.
    6. 정상 케이스와 정보 부족 케이스를 실행합니다.
    7. Mustache 템플릿으로 Trace Markdown을 생성합니다.
    8. outputs/day1/mini_graph_trace.md 파일로 저장합니다.
    """
    print("[1일차 LangGraph 실습] StateGraph 조건부 분기 흐름을 실행합니다.")

    current_file = Path(__file__).resolve()
    project_root = current_file.parents[2]

    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    query_path = project_root / "data" / "sample_query.json"
    csv_path = project_root / "data" / "sample_alarm_logs.csv"
    prompt_template_path = project_root / "templates" / "day1" / "mini_graph_llm_prompt.mustache"
    trace_template_path = project_root / "templates" / "day1" / "mini_graph_trace_report.mustache"
    output_path = project_root / "outputs" / "day1" / "mini_graph_trace.md"

    query_data = json.loads(query_path.read_text(encoding="utf-8-sig"))
    logs = pd.read_csv(csv_path, encoding="utf-8-sig")

    normal_state = {
        "user_query": str(query_data.get("user_query", "")),
        "line_id": str(query_data.get("line_id", "")),
        "process_name": str(query_data.get("process_name", "")),
        "equipment_id": str(query_data.get("equipment_id", "")),
        "alarm_code": str(query_data.get("alarm_code", "")),
        "has_required_info": False,
        "log_results": [],
        "log_summary": {},
        "llm_prompt": "",
        "llm_response": "",
        "next_action": "",
        "messages": [],
        "trace": [],
        "errors": [],
    }

    # dict.copy()는 얕은 복사입니다.
    # 그래서 list/dict 필드는 반드시 새 값으로 다시 초기화합니다.
    missing_state = normal_state.copy()
    missing_state["equipment_id"] = ""
    missing_state["user_query"] = "ALM-TEMP-402 교육용 알람이 반복 발생한 것 같습니다. 어떤 정보를 더 확인해야 하나요?"
    missing_state["messages"] = []
    missing_state["trace"] = []
    missing_state["errors"] = []
    missing_state["log_results"] = []
    missing_state["log_summary"] = {}
    missing_state["llm_prompt"] = ""
    missing_state["llm_response"] = ""
    missing_state["next_action"] = ""

    def add_trace(state, node_name, input_summary, output_summary, next_node):
        state["trace"].append(
            {
                "node_name": node_name,
                "input_summary": input_summary,
                "output_summary": output_summary,
                "next_node": next_node,
            }
        )
        return state

    def start_node(state):
        print("start_node 실행")
        state["messages"].append("LangGraph mini graph 실행을 시작합니다.")
        return add_trace(state, "start_node", "초기 State 입력", "실행 시작 메시지 추가", "parse_query_node")

    def parse_query_node(state):
        print("parse_query_node 실행")
        for key in ["user_query", "line_id", "process_name", "equipment_id", "alarm_code"]:
            state[key] = str(state.get(key) or "")
        output_summary = f"equipment_id={state['equipment_id'] or '없음'}, alarm_code={state['alarm_code'] or '없음'} 확인"
        state["messages"].append(output_summary)
        return add_trace(state, "parse_query_node", "user_query와 query 필드 확인", output_summary, "check_required_info_node")

    def check_required_info_node(state):
        print("check_required_info_node 실행")
        has_equipment_id = bool(state.get("equipment_id", "").strip())
        has_alarm_code = bool(state.get("alarm_code", "").strip())
        if has_equipment_id and has_alarm_code:
            state["has_required_info"] = True
            state["next_action"] = "search_log"
            message = "필수 정보 있음 → search_log_node로 이동"
            next_node = "search_log_node"
        else:
            state["has_required_info"] = False
            state["next_action"] = "ask_more_info"
            message = "필수 정보 부족 → ask_more_info_node로 이동"
            next_node = "ask_more_info_node"
        print(f"check_required_info_node: {message}")
        state["messages"].append(message)
        return add_trace(state, "check_required_info_node", "equipment_id와 alarm_code 존재 여부 확인", message, next_node)

    def route_after_required_info_check(state):
        if state.get("next_action") == "search_log":
            return "search_log_node"
        return "ask_more_info_node"

    def search_log_node(state):
        print("search_log_node 실행")
        equipment_id = state.get("equipment_id", "")
        alarm_code = state.get("alarm_code", "")
        filtered = logs[
            (logs["equipment_id"].astype(str) == str(equipment_id))
            & (logs["alarm_code"].astype(str) == str(alarm_code))
        ].copy()
        if "timestamp" in filtered.columns:
            filtered = filtered.sort_values("timestamp")
        state["log_results"] = filtered.to_dict(orient="records")
        message = f"관련 로그 {len(state['log_results'])}건 발견"
        print(f"search_log_node: {message}")
        state["messages"].append(message)
        return add_trace(state, "search_log_node", f"equipment_id={equipment_id}, alarm_code={alarm_code}", message, "summarize_result_node")

    def ask_more_info_node(state):
        print("ask_more_info_node 실행")
        missing = []
        if not state.get("equipment_id", "").strip():
            missing.append("equipment_id")
        if not state.get("alarm_code", "").strip():
            missing.append("alarm_code")
        missing_text = ", ".join(missing) if missing else "필수 정보"
        message = (
            f"알람 원인을 확인하려면 {missing_text} 값이 필요합니다. "
            "교육용 예시로는 equipment_id=EQP-EV-03, alarm_code=ALM-TEMP-402를 사용할 수 있습니다."
        )
        state["messages"].append(message)
        state["llm_response"] = "정보 부족 케이스이므로 LLM을 호출하지 않았습니다."
        return add_trace(state, "ask_more_info_node", f"누락 정보: {missing_text}", "추가 정보 요청 메시지 생성, LLM 호출 없음", "END")

    def summarize_result_node(state):
        print("summarize_result_node 실행")
        records = state.get("log_results", [])
        if not records:
            summary = {
                "total_count": 0,
                "message": "해당 조건의 로그가 없습니다.",
                "severity_counts": {},
                "repeat_count_max": None,
            }
        else:
            severity_counts = {}
            timestamps = []
            repeat_values = []
            for row in records:
                severity = str(row.get("severity", ""))
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
                if row.get("timestamp"):
                    timestamps.append(str(row.get("timestamp")))
                try:
                    repeat_values.append(int(float(row.get("repeat_count", 0))))
                except (TypeError, ValueError):
                    pass
            summary = {
                "total_count": len(records),
                "first_timestamp": timestamps[0] if timestamps else "",
                "last_timestamp": timestamps[-1] if timestamps else "",
                "severity_counts": severity_counts,
                "repeat_count_max": max(repeat_values) if repeat_values else None,
            }
        state["log_summary"] = summary
        if summary.get("total_count", 0) == 0:
            message = "해당 조건의 로그가 없습니다."
        else:
            message = (
                f"관련 로그 {summary['total_count']}건 요약 완료 "
                f"(최초={summary.get('first_timestamp', 'N/A')}, "
                f"마지막={summary.get('last_timestamp', 'N/A')})"
            )
        state["messages"].append(message)
        return add_trace(state, "summarize_result_node", "log_results 요약", message, "build_llm_prompt_node")

    def build_llm_prompt_node(state):
        print("build_llm_prompt_node 실행")
        summary_text = json.dumps(state.get("log_summary", {}), ensure_ascii=False, indent=2)
        prompt_template = prompt_template_path.read_text(encoding="utf-8-sig")
        prompt_data = {
            "user_query": state.get("user_query", ""),
            "line_id": state.get("line_id", ""),
            "process_name": state.get("process_name", ""),
            "equipment_id": state.get("equipment_id", ""),
            "alarm_code": state.get("alarm_code", ""),
            "summary_text": summary_text,
        }
        state["llm_prompt"] = pystache.render(prompt_template, prompt_data)
        state["messages"].append("LLM 요약 응답 생성을 위한 프롬프트를 생성했습니다.")
        return add_trace(state, "build_llm_prompt_node", "log_summary 기반 프롬프트 템플릿 렌더링", "llm_prompt 생성 완료", "generate_llm_response_node")

    def generate_llm_response_node(state):
        print("generate_llm_response_node 실행")
        print("generate_llm_response_node: llm_client.py를 통해 LLM 응답 생성")
        from llm_client import generate_response
        state["llm_response"] = generate_response(state["llm_prompt"])
        message = "llm_client.py를 통한 LLM 응답 생성 완료"
        state["messages"].append(message)
        return add_trace(state, "generate_llm_response_node", "llm_prompt를 llm_client.generate_response에 전달", message, "END")

    graph = StateGraph(dict)
    graph.add_node("start_node", start_node)
    graph.add_node("parse_query_node", parse_query_node)
    graph.add_node("check_required_info_node", check_required_info_node)
    graph.add_node("search_log_node", search_log_node)
    graph.add_node("ask_more_info_node", ask_more_info_node)
    graph.add_node("summarize_result_node", summarize_result_node)
    graph.add_node("build_llm_prompt_node", build_llm_prompt_node)
    graph.add_node("generate_llm_response_node", generate_llm_response_node)
    graph.add_edge(START, "start_node")
    graph.add_edge("start_node", "parse_query_node")
    graph.add_edge("parse_query_node", "check_required_info_node")
    graph.add_conditional_edges(
        "check_required_info_node",
        route_after_required_info_check,
        {
            "search_log_node": "search_log_node",
            "ask_more_info_node": "ask_more_info_node",
        },
    )
    graph.add_edge("search_log_node", "summarize_result_node")
    graph.add_edge("summarize_result_node", "build_llm_prompt_node")
    graph.add_edge("build_llm_prompt_node", "generate_llm_response_node")
    graph.add_edge("generate_llm_response_node", END)
    graph.add_edge("ask_more_info_node", END)
    app = graph.compile()

    print("[정상 케이스] 실행 시작")
    normal_result = app.invoke(normal_state)

    print("[정보 부족 케이스] 실행 시작")
    missing_result = app.invoke(missing_state)

    def make_report(state, case_name):
        trace_rows = []
        for index, item in enumerate(state.get("trace", []), start=1):
            trace_rows.append(
                "| {idx} | {node} | {inp} | {out} | {next_node} |".format(
                    idx=index,
                    node=str(item.get("node_name", "")).replace("|", "\\|"),
                    inp=str(item.get("input_summary", "")).replace("|", "\\|"),
                    out=str(item.get("output_summary", "")).replace("|", "\\|"),
                    next_node=str(item.get("next_node", "")).replace("|", "\\|"),
                )
            )
        trace_table = "\n".join(trace_rows) if trace_rows else "| - | - | - | - | - |"
        message_text = "\n".join(f"- {message}" for message in state.get("messages", [])) or "- 메시지 없음"
        error_text = "\n".join(f"- {error}" for error in state.get("errors", [])) or "- 오류 없음"
        summary_text = json.dumps(state.get("log_summary", {}), ensure_ascii=False, indent=2)
        route_result = "search_log_node로 이동" if state.get("next_action") == "search_log" else "ask_more_info_node로 이동"
        llm_prompt = state.get("llm_prompt", "") or "정보 부족 케이스이므로 LLM 프롬프트를 생성하지 않았습니다."
        llm_response = state.get("llm_response", "") or "LLM 응답이 없습니다."
        template_data = {
            "case_name": case_name,
            "user_query": state.get("user_query", ""),
            "line_id": state.get("line_id", ""),
            "process_name": state.get("process_name", ""),
            "equipment_id_display": state.get("equipment_id", "") or "없음",
            "alarm_code_display": state.get("alarm_code", "") or "없음",
            "trace_table": trace_table,
            "next_action": state.get("next_action", ""),
            "route_result": route_result,
            "summary_text": summary_text,
            "llm_prompt": llm_prompt,
            "llm_response": llm_response,
            "error_text": error_text,
            "message_text": message_text,
        }
        template_text = trace_template_path.read_text(encoding="utf-8-sig")
        return pystache.render(template_text, template_data)

    normal_report = make_report(normal_result, "정상 케이스")
    missing_report = make_report(missing_result, "정보 부족 케이스")
    combined_report = f"# 1일차 LangGraph mini Graph 실행 Trace\n\n{normal_report}\n\n---\n\n{missing_report}\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(combined_report, encoding="utf-8-sig")

    print(f"결과 저장: {output_path.relative_to(project_root)}")
    print("다음 단계: src/day1/day1_agent_v0_template.py에서 Prompt, Chain, LangGraph 흐름을 통합합니다.")


def main():
    """
    프로그램 시작점입니다.
    """
    run_mini_graph()


if __name__ == "__main__":
    main()
