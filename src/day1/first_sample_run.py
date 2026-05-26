"""
삼성디스플레이 재직자 대상 AI Agent Architecture 1일차 실습용 단순 실행 파일입니다.

이 파일은 초보자가 위에서 아래로 읽기 쉽도록 단순하게 구성했습니다.

역할:
- data/sample_query.json에서 실습 입력 조건을 읽습니다.
- data/sample_alarm_logs.csv에서 설비 ID와 알람 코드 기준으로 로그를 필터링합니다.
- docs/alarm_manual.md의 앞부분 일부를 참고 자료로 사용합니다.
- templates/day1/first_sample_run_prompt.mustache로 LLM Prompt를 만듭니다.
- llm_client.py의 generate_response(prompt)를 통해 LLM을 호출합니다.
- templates/day1/first_sample_run_result.mustache로 Markdown 결과를 만듭니다.
- outputs/day1/first_sample_run_result.md로 저장합니다.

중요:
- 이 파일은 Gemini/OpenAI/Anthropic/Ollama/NVIDIA SDK를 직접 import하지 않습니다.
- LLM 호출은 llm_client.py의 generate_response(prompt)를 통해서만 수행합니다.
- 실제 사내 데이터가 아니라 DisplayEdu Fab 교육용 가상 데이터만 사용합니다.
"""

from pathlib import Path
import json
import sys

import pandas as pd
import pystache


def run_first_sample():
    """
    1일차 첫 실행 예제입니다.

    이 함수는 교육용 제조 Agent가 다음 순서로 동작하는 것을 보여줍니다.

    1. 사용자 요청을 읽습니다.
    2. 제조 알람 로그 CSV를 읽습니다.
    3. 설비 ID와 알람 코드로 관련 로그를 찾습니다.
    4. 알람 매뉴얼을 읽습니다.
    5. Prompt 템플릿으로 LLM에게 보낼 프롬프트를 만듭니다.
    6. llm_client.py를 통해 LLM을 호출합니다.
    7. Result 템플릿으로 Markdown 결과를 만듭니다.
    8. 결과를 Markdown 파일로 저장합니다.
    """
    print("[1일차 첫 실행] 교육용 제조 Agent 예제를 실행합니다.")

    # 1. 현재 파일 위치를 기준으로 프로젝트 루트 경로를 찾습니다.
    # 이 파일은 src/day1 폴더 안에 있다고 가정합니다.
    current_file = Path(__file__).resolve()
    project_root = current_file.parents[2]

    # 2. src 폴더를 import 경로에 추가합니다.
    # 이렇게 해야 src/llm_client.py를 불러올 수 있습니다.
    src_dir = project_root / "src"

    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    # 3. 이번 예제에서 사용할 파일 경로를 준비합니다.
    query_path = project_root / "data" / "sample_query.json"
    log_path = project_root / "data" / "sample_alarm_logs.csv"
    manual_path = project_root / "docs" / "alarm_manual.md"

    prompt_template_path = project_root / "templates" / "day1" / "first_sample_run_prompt.mustache"
    result_template_path = project_root / "templates" / "day1" / "first_sample_run_result.mustache"

    output_path = project_root / "outputs" / "day1" / "first_sample_run_result.md"

    # 4. 사용자 요청 조건을 읽습니다.
    query_data = json.loads(query_path.read_text(encoding="utf-8-sig"))

    equipment_id = str(query_data["equipment_id"])
    alarm_code = str(query_data["alarm_code"])
    user_query = str(query_data["user_query"])

    print(f"필터 조건: equipment_id={equipment_id}, alarm_code={alarm_code}")

    # 5. 제조 알람 로그 CSV를 읽습니다.
    logs = pd.read_csv(log_path, encoding="utf-8-sig")

    # 6. 설비 ID와 알람 코드가 일치하는 로그만 찾습니다.
    filtered_logs = logs[
        (logs["equipment_id"].astype(str) == equipment_id)
        & (logs["alarm_code"].astype(str) == alarm_code)
    ].copy()

    if "timestamp" in filtered_logs.columns:
        filtered_logs = filtered_logs.sort_values("timestamp")

    # 7. 필터링된 로그를 간단히 요약합니다.
    total_count = len(filtered_logs)

    if total_count > 0:
        first_time = filtered_logs["timestamp"].iloc[0]
        last_time = filtered_logs["timestamp"].iloc[-1]
        severity_counts = filtered_logs["severity"].value_counts().to_dict()
    else:
        first_time = "해당 없음"
        last_time = "해당 없음"
        severity_counts = {}

    # 8. 알람 매뉴얼을 읽습니다.
    # 실제 RAG 검색은 2일차에서 더 자세히 다룹니다.
    # 여기서는 첫 실행 흐름을 단순하게 보기 위해 매뉴얼 앞부분 일부만 사용합니다.
    manual_text = manual_path.read_text(encoding="utf-8-sig")
    manual_preview = manual_text[:2000]

    # 9. 관련 로그 일부를 LLM이 읽기 쉬운 JSON 문자열로 바꿉니다.
    logs_json = filtered_logs.head(10).to_json(
        orient="records",
        force_ascii=False,
        indent=2,
    )

    # 10. Prompt Mustache 템플릿을 읽습니다.
    prompt_template = prompt_template_path.read_text(encoding="utf-8-sig")

    # 11. Prompt 템플릿에 넣을 데이터를 준비합니다.
    prompt_data = {
        "user_query": user_query,
        "equipment_id": equipment_id,
        "alarm_code": alarm_code,
        "total_count": total_count,
        "first_time": str(first_time),
        "last_time": str(last_time),
        "severity_counts": severity_counts,
        "logs_json": logs_json,
        "manual_preview": manual_preview,
    }

    # 12. Mustache 템플릿으로 LLM에게 보낼 Prompt를 만듭니다.
    prompt = pystache.render(prompt_template, prompt_data)

    # 13. llm_client.py를 통해 LLM을 호출합니다.
    # 이 파일에서는 provider별 SDK를 직접 import하지 않습니다.
    from llm_client import generate_response

    print("선택된 LLM으로 응답 생성 중...")
    llm_response = generate_response(prompt)

    # 14. Result Mustache 템플릿을 읽습니다.
    result_template = result_template_path.read_text(encoding="utf-8-sig")

    # 15. Result 템플릿에 넣을 데이터를 준비합니다.
    result_data = {
        "equipment_id": equipment_id,
        "alarm_code": alarm_code,
        "total_count": total_count,
        "first_time": str(first_time),
        "last_time": str(last_time),
        "severity_counts": severity_counts,
        "prompt": prompt,
        "llm_response": llm_response,
    }

    # 16. Mustache 템플릿으로 Markdown 결과를 만듭니다.
    report = pystache.render(result_template, result_data)

    # 17. 결과 Markdown 파일을 저장합니다.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8-sig")

    print(f"관련 로그 수: {total_count}건")
    print(f"결과 저장: {output_path.relative_to(project_root)}")


def main():
    """
    프로그램 시작점입니다.
    """
    run_first_sample()


if __name__ == "__main__":
    main()
