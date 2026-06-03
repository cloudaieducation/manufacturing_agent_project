"""
Day3 Multi-Agent Roles (LangGraph 버전) - FastMCP standalone 연동 단순화 버전

본 코드는 교육용 가상 제조 시나리오를 사용합니다.
실제 사내 데이터나 실제 사내 시스템에 접속하지 않습니다.
(여기 나오는 EQP-EV-03, ALM-TEMP-402, EDU-LINE-* 같은 값은 모두 강의용으로 만든 "가짜" 값입니다.
 그래서 API 키가 없어도, 사내망이 아니어도, 수강생이 안전하게 실습할 수 있습니다.)

────────────────────────────────────────────────────────────────────────
[이 파일이 Day3 아키텍처에서 맡는 역할 — Day3의 핵심 파일]
────────────────────────────────────────────────────────────────────────
- 여러 Agent가 "역할을 나눠" 하나의 장애 대응 흐름을 처리하는 구조를 보여 줍니다.
- 핵심은 이름을 나누는 것이 아니라 "책임(responsibility)을 분리"하는 것입니다.
    · CoordinatorAgent     : 사용자 요청 분석(설비 ID/알람 코드 추출)
    · DBInvestigationAgent : DB/Log Tool 호출 책임
    · ManualRAGAgent       : search_manual(RAG) Tool 호출 책임
    · IncidentSummaryAgent : DB 결과 + RAG 결과 종합 책임

  ▶ 왜 Agent를 여러 개로 나눌까요? (설명)
    하나의 거대한 함수가 "질문 분석 → DB 조회 → 문서 검색 → 요약"을 전부 하면,
    코드가 길어지고 어디서 틀렸는지 찾기 어렵습니다.
    제조 현장으로 비유하면, 한 사람이 접수·점검·문서확인·보고서작성을 다 하는 것과 같습니다.
    대신 "접수 담당 / 설비 점검 담당 / 매뉴얼 확인 담당 / 보고서 작성 담당"으로 나누면
    각자 책임이 분명해지고, 문제가 생긴 단계만 콕 집어 고칠 수 있습니다.
    Multi-Agent 구조는 바로 이 "역할 분담"을 코드로 옮긴 것입니다.

────────────────────────────────────────────────────────────────────────
[State 전달 구조 — 반드시 이해해야 할 개념]
────────────────────────────────────────────────────────────────────────
- 모든 Agent는 하나의 dict인 "State"를 차례로 받고, 자기 책임만큼 채운 뒤 넘깁니다.
  (State = Agent들이 함께 보고 함께 적어 넣는 "공유 작업판/공유 노트"라고 생각하세요.)
- State 안의 주요 칸:
    · equipment_id / alarm_code / line_id : 추출한 핵심 정보
    · db_results   : DB Tool 호출 결과 모음
    · rag_results  : RAG Tool 호출 결과
    · agent_steps  : 어떤 Agent가 무엇을 했는지 적는 실행 기록
    · final_summary: 최종 종합 요약
- db_results와 rag_results를 분리해 두는 이유: "사실 데이터(DB)"와 "절차 근거(RAG)"는
  성격이 다르므로, 나중에 결과를 해석/평가할 때 출처별로 구분하기 위함입니다.
  (현장 비유: "지금 설비가 어떤 상태인가"라는 사실과, "그럴 때 매뉴얼은 뭐라고 하는가"라는
   근거는 종류가 다른 정보이므로 서랍을 나눠서 보관하는 것입니다.)

────────────────────────────────────────────────────────────────────────
[LangGraph 관점]
────────────────────────────────────────────────────────────────────────
- 각 Agent의 run(state)은 LangGraph의 한 Node(노드, 처리 단계)로 해석할 수 있습니다.
  (State를 입력받아 갱신된 State를 반환하는 노드 → 노드들을 순서대로 연결한 그래프)
- 이 파일은 형제 파일(multi_agent_roles.py)이 "그냥 순서대로 함수 호출"로 만든 흐름을,
  LangGraph의 StateGraph(그래프 설계도)로 똑같이 다시 그린 버전입니다.
  → 실행 결과는 같지만, "노드와 엣지로 흐름을 그림처럼 정의"한다는 점이 다릅니다.

────────────────────────────────────────────────────────────────────────
[MCP 서버 모드 vs fallback 모드 차이]
────────────────────────────────────────────────────────────────────────
- "fastmcp" 모드 : 별도로 띄운 MCP 서버(manufacturing_mcp_server.py)에 네트워크로 접속해
                   Tool(get_equipment_status 등)을 호출합니다. (실제 분산 구조에 가까움)
- "fallback" 모드 : MCP 서버 없이, 같은 파이썬 프로세스 안의 함수로 Tool을 직접 호출합니다.
                   (서버를 못 띄우는 환경에서도 실습이 멈추지 않도록 하는 "대체 경로")
  → 중요한 점: Agent 코드는 둘 중 무엇을 쓰는지 몰라도 됩니다. 아래 load_tool_caller()가
    경로를 골라 call_tool 함수만 건네주기 때문입니다. (자세한 내용은 해당 함수 주석 참고)

────────────────────────────────────────────────────────────────────────
[현업 적용 시 확장 방향]
────────────────────────────────────────────────────────────────────────
- Agent 간 Handoff 평가, Guardrail(안전 점검), 사람 승인(approval) 흐름 등을 더할 수 있습니다.
  (※ 본 파일에는 안전 검토 Agent가 구현되어 있지 않으며, 그런 확장은 4일차 Guardrail 주제입니다.)

실행 구조 예:

파워쉘 1:
cd C:\\work\\manufacturing_agent_project
uv run python .\src\day3\manufacturing_mcp_server.py

파워쉘 2: (또다른 파워쉘)
cd C:\\work\\manufacturing_agent_project
set MCP_MODE=fastmcp
set MCP_FASTMCP_URL=http://127.0.0.1:8765/mcp
python src/day3/multi_agent_roles_graph.py
"""

# from __future__ import annotations
#   파이썬의 "미래 기능 미리 쓰기" 선언입니다.
#   이 한 줄 덕분에 아래에서 str | None (str 또는 None) 같은 최신 타입 표기를
#   구버전 파이썬에서도 오류 없이 쓸 수 있습니다. (반드시 파일 맨 위쪽에 있어야 합니다.)
from __future__ import annotations

# re  : 정규식(Regular Expression) 모듈입니다.
#       "EQP-EV-03", "ALM-TEMP-402" 같은 정해진 형태의 문자열을 찾아낼 때 사용합니다.
#       (LLM 없이 규칙만으로 핵심 식별자를 뽑는 데 쓰입니다 — extract_* 함수 참고)
import re
# sys : 파이썬 실행 환경을 다루는 모듈입니다.
#       여기서는 sys.path(파이썬이 모듈을 찾는 폴더 목록)에 프로젝트 루트를 추가하는 데 씁니다.
import sys
# Path: 파일/폴더 경로를 객체로 다루는 도구입니다.
#       문자열로 경로를 더하는 것보다 안전하고, 윈도우/리눅스 경로 차이도 알아서 처리해 줍니다.
from pathlib import Path

# pystache: Mustache 템플릿 엔진입니다.
#           {{변수}} 형태의 템플릿 파일에 실제 값을 끼워 넣어 최종 Markdown 문서를 만듭니다.
#           (코드 안에 긴 보고서 문자열을 직접 쓰지 않고, 템플릿 파일과 데이터를 "합치는" 방식)
import pystache


# DEFAULT_MODE: Tool 호출 경로 기본값. "fastmcp"면 MCP 서버를 통해 호출합니다.
#   (서버가 없으면 Client의 auto 동작이나 fallback 모드로 바꿔야 합니다.)
#   ▶ 설명: 이 값은 "기본적으로 어떤 길로 Tool을 부를까?"의 기본 설정입니다.
#     "fastmcp" = MCP 서버라는 별도 프로그램을 통해 부른다(네트워크 경유).
DEFAULT_MODE = "fastmcp"
# SAMPLE_USER_QUERY: 직접 실행 시 사용하는 교육용 예시 질문(가상 설비/알람 코드 포함).
#   ▶ 강의에서 "이런 질문이 들어오면 Agent들이 어떻게 처리하는지"를 보여주기 위한 샘플 문장입니다.
#     실제 서비스라면 사용자가 입력한 문장이 여기에 들어옵니다.
SAMPLE_USER_QUERY = "EQP-EV-03에서 ALM-TEMP-402 알람이 반복 발생했습니다. 원인과 조치 방향을 알려주세요."
# EDUCATION_NOTICE: 결과물에 항상 붙이는 "교육용 가상 데이터" 고지 문구.
#   ▶ 왜 매번 붙일까요? 이 결과가 실제 사내 데이터로 오해되면 안 되기 때문입니다.
#     "이건 교육용 가짜 시나리오다"라는 점을 결과물에 분명히 남겨 혼동을 막습니다.
EDUCATION_NOTICE = "본 실습은 실제 사내 데이터가 아닌 교육용 가상 제조 시나리오입니다."


def get_project_root() -> Path:
    """
    현재 파일 위치를 기준으로 프로젝트 루트 폴더를 반환합니다.

    ▶ 왜 필요한가:
        - 이 파일은 .../manufacturing_agent_project/src/day3/ 안에 있습니다.
        - 하지만 결과 파일을 저장하거나 다른 모듈을 import할 때는
          "프로젝트 맨 위 폴더(루트)"를 기준점으로 삼아야 안정적입니다.
        - 그래서 "내 파일 위치"에서 위로 거슬러 올라가 루트를 계산합니다.
    """
    # Path(__file__)  : 지금 이 .py 파일의 경로
    # .resolve()      : 상대경로/심볼릭링크 등을 모두 풀어 "절대경로"로 변환
    # .parents[2]     : 부모 폴더로 2번 거슬러 올라감
    #                   parents[0]=현재 파일이 든 폴더(day3) → parents[1]=src → parents[2]=프로젝트 루트
    return Path(__file__).resolve().parents[2]


# PROJECT_ROOT: 위 함수로 계산한 프로젝트 루트 경로를 한 번 구해 변수에 보관해 둡니다.
PROJECT_ROOT = get_project_root()
# sys.path 는 "파이썬이 import할 모듈을 찾아다니는 폴더 목록"입니다.
#   여기에 프로젝트 루트를 추가해 두면, 아래에서 from src.day3.xxx import ... 가
#   "어느 위치에서 실행하든" 안정적으로 동작합니다.
#   ▶ 강의 팁: 수강생마다 터미널을 연 위치(현재 폴더)가 다를 수 있는데,
#     이 장치가 있으면 "import 오류"로 실습이 막히는 일을 크게 줄여 줍니다.
if str(PROJECT_ROOT) not in sys.path:          # 중복 추가를 막기 위해 이미 있는지 먼저 확인
    sys.path.insert(0, str(PROJECT_ROOT))      # 목록 맨 앞(0번)에 넣어 가장 먼저 탐색되게 함


def create_initial_state(user_query: str) -> dict:
    """
    사용자 요청을 받아 Agent들이 함께 사용할 초기 State(dict)를 만듭니다.

    설계 의미:
        - 이 dict가 Agent들 사이를 흐르는 "공유 작업판"입니다.
          (제조 현장 비유: 한 장의 점검표를 여러 담당자가 돌려 보며 자기 칸을 채워 나가는 것)
        - 모든 칸을 미리 만들어 두어, 각 Agent가 자기 칸만 채우면 되도록 합니다.
          (어떤 정보가 오갈지 한눈에 보이는 것이 State 설계의 장점입니다.)
        - LangGraph에서도 이 State가 노드(Node) 사이를 이동하는 데이터 구조가 됩니다.
    출력: 빈 값으로 초기화된 State dict
    """
    # ▶ 처음에는 왜 None / 빈 dict / 빈 list 로 둘까요?
    #   "아직 아무도 채우지 않았다"를 분명히 표시하기 위해서입니다.
    #   각 Agent가 자기 단계에서 이 빈칸을 실제 값으로 바꿔 채웁니다.
    return {
        "user_query": user_query,   # 원본 사용자 질문 (가장 먼저 들어오는 입력)
        "equipment_id": None,       # Coordinator가 추출 (예: "EQP-EV-03")
        "alarm_code": None,         # Coordinator가 추출 (예: "ALM-TEMP-402")
        "line_id": None,            # DB 조회 중 설비 정보에서 얻음 (품질 지표 조회에 사용)
        "db_results": {},           # DBInvestigationAgent가 채움 (사실 데이터: 설비/알람/공정/정비/품질)
        "rag_results": {},          # ManualRAGAgent가 채움 (절차 근거: 매뉴얼/기술문서 검색 결과)
        "agent_steps": [],          # 각 Agent의 실행 기록(흐름 추적용 trace 로그)
        "final_summary": "",        # IncidentSummaryAgent가 채움 (최종 종합 요약 보고서)
        "mode": DEFAULT_MODE,       # 실제 사용된 Tool 호출 모드(실행 시 갱신)
    }


def extract_equipment_id(text: str) -> str | None:
    """
    사용자 요청 문자열에서 EQP-EV-03 같은 교육용 설비 ID 패턴을 정규식으로 찾습니다.

    ▶ 정규식(Regular Expression)이란?
        - "이런 모양의 글자"를 찾는 검색 규칙입니다.
          예: "EQP- 다음에 영문 2글자 - 숫자 2글자" 같은 패턴을 한 줄로 표현합니다.
        - 사람이 문장에서 설비 번호를 눈으로 찾는 일을, 컴퓨터가 규칙으로 자동 처리하는 것입니다.

    설계 의미:
        - LLM 없이 규칙(정규식)만으로 핵심 식별자를 뽑는 가장 단순한 추출 방식입니다.
          (LLM은 비용/지연/불확실성이 있는데, 형식이 정해진 코드값은 규칙만으로 빠르고 정확히 뽑힙니다.)
        - 앞뒤로 (?<![A-Z0-9]) / (?![A-Z0-9])를 둬, 더 긴 코드의 일부를 잘못 잡는 것을 막습니다.
    출력: 찾으면 "EQP-..." 문자열, 없으면 None
    """
    if not text:           # 입력이 비어 있으면(빈 문자열/ None) 찾을 것도 없으므로
        return None        # 바로 None 을 돌려줍니다. (불필요한 검색 방지)

    # text.upper()로 대문자 통일 후 매칭해, 소문자로 적힌 경우(eqp-ev-03)도 잡습니다.
    #   패턴 풀이:
    #     (?<![A-Z0-9]) : 바로 앞이 영문/숫자가 "아니어야" 함 (예: XEQP-EV-03 처럼 붙은 건 제외)
    #     EQP-          : 문자 그대로 "EQP-"
    #     [A-Z]{2}      : 영문 대문자 2글자 (예: EV)
    #     -\d{2}        : "-" 뒤에 숫자 2자리 (예: -03)
    #     (?![A-Z0-9])  : 바로 뒤가 영문/숫자가 "아니어야" 함 (예: EQP-EV-031 같은 더 긴 코드 제외)
    match = re.search(r"(?<![A-Z0-9])EQP-[A-Z]{2}-\d{2}(?![A-Z0-9])", text.upper())
    # match가 있으면 매칭된 전체 문자열(group(0))을, 없으면 None을 반환합니다.
    #   ▶ 현업 확장: 실제로는 설비 코드 체계가 더 복잡하거나, 문맥을 이해해야 해서
    #     LLM 기반 추출이나 사내 마스터 데이터 조회로 확장되기도 합니다.
    return match.group(0) if match else None


def extract_alarm_code(text: str) -> str | None:
    """
    사용자 요청 문자열에서 ALM-TEMP-402 같은 교육용 알람 코드 패턴을 찾습니다.

    (설비 ID 추출과 같은 규칙 기반 방식이며, 알람 코드 형태에 맞춰 패턴만 다릅니다.)
    출력: 찾으면 "ALM-..." 문자열, 없으면 None
    """
    if not text:           # 설비 ID 추출과 동일하게, 입력이 비면 바로 None
        return None

    # 알람 코드 패턴 풀이:
    #   ALM-           : 문자 그대로 "ALM-"
    #   [A-Z]{2,10}    : 영문 대문자 2~10글자 (예: TEMP) — 설비 ID(딱 2글자)보다 길이를 넉넉히 허용
    #   -\d{2,4}       : "-" 뒤에 숫자 2~4자리 (예: -402)
    #   앞뒤의 (?<![A-Z0-9]) / (?![A-Z0-9]) 의도는 설비 ID와 동일(더 긴 문자열의 일부 오인 방지)
    match = re.search(r"(?<![A-Z0-9])ALM-[A-Z]{2,10}-\d{2,4}(?![A-Z0-9])", text.upper())
    return match.group(0) if match else None


def add_step(state: dict, agent_name: str, message: str) -> None:
    """
    State의 agent_steps에 "어떤 Agent가 무엇을 했는지" 한 줄을 추가합니다.

    설계 의미:
        - agent_steps는 실행 흐름을 사람이 따라 읽을 수 있게 남기는 기록(trace)입니다.
          (제조 현장 비유: 작업일지/점검 로그. 나중에 "어디서 멈췄는지"를 되짚는 근거가 됩니다.)
        - 결과만 보는 것이 아니라 "누가 무엇을 했고 어디서 막혔는지"를 해석하는 근거가 됩니다.
          ([ERROR]/[WARN] 같은 표식을 메시지에 넣어 문제 지점을 구분합니다.)
        - 이 trace 개념은 현업에서 LangSmith 같은 추적/평가 도구로 자연스럽게 확장됩니다.
    """
    # f"{agent_name}: {message}" → "CoordinatorAgent: ...했습니다." 형태의 한 줄을 만들고
    # 리스트의 맨 뒤에 append(추가) 합니다. 순서대로 쌓이므로 곧 실행 순서 기록이 됩니다.
    state["agent_steps"].append(f"{agent_name}: {message}")


def load_tool_caller(mode: str = DEFAULT_MODE):
    """
    실행 모드에 맞는 "Tool 호출 함수"를 골라 돌려줍니다.

    ▶ 한 문장 요약: 이 함수는 "Tool을 어느 길로 부를지" 고르는 스위치입니다.

    설계 의미:
        - Agent들은 자기가 어떤 경로(MCP/fallback)로 Tool을 부르는지 몰라도 되도록,
          여기서 call_tool 함수 자체를 주입(inject)해 줍니다. (의존성 주입 = Dependency Injection)
          (비유: 작업자에게 "전화기"만 쥐어 주면, 그 전화가 사내 유선망이든 휴대폰망이든
                작업자는 신경 쓰지 않고 통화만 하면 됩니다. 망 선택은 이 함수가 합니다.)
        - 그래서 DBInvestigationAgent/ManualRAGAgent는 받은 call_tool만 호출하면 됩니다.
        - 덕분에 현업에서 Tool 호출 경로가 바뀌어도(서버 주소 변경, 프로토콜 교체 등)
          Agent 코드는 거의 그대로 둘 수 있습니다. (변경 지점을 한 곳으로 모음)

    입력: mode("fastmcp"/"fallback"/"server")
    출력: (call_tool 함수, 실제로 정해진 모드 문자열) 튜플

    분기 설명:
        - "server"라고 들어오면 fastmcp로 해석합니다(같은 의미의 별칭 처리).
        - "fallback"이면 fallback registry의 call_tool을, 그 외에는 MCP Client의 call_tool을 씁니다.
    """
    # 들어온 mode 값을 안전하게 정리합니다.
    #   str(mode or DEFAULT_MODE) : mode가 None/빈값이면 기본값으로 대체
    #   .strip()                  : 앞뒤 공백 제거
    #   .lower()                  : 소문자로 통일 ("FastMCP", "FASTMCP" 등도 동일하게 처리)
    requested_mode = str(mode or DEFAULT_MODE).strip().lower()

    # "server"는 fastmcp의 별칭으로 취급합니다.
    #   ▶ 왜? 어떤 사람은 "서버 모드"라고 부르고 어떤 사람은 "fastmcp"라고 부르기 때문에,
    #     같은 의미의 표현을 하나로 통일해 혼동을 줄입니다.
    if requested_mode == "server":
        requested_mode = "fastmcp"

    # fallback 모드: 서버 없이 Python 함수로 직접 호출하는 경로
    #   ▶ import를 함수 안에서 하는 이유: 실제로 그 모드를 쓸 때만 해당 모듈을 불러오기 위함입니다.
    #     (fallback을 안 쓰면 굳이 fallback 모듈을 메모리에 올리지 않음)
    if requested_mode == "fallback":
        from src.day3.tool_registry_fallback import call_tool

        return call_tool, "fallback"   # (호출 함수, 실제 모드명) 두 개를 함께 돌려줌

    # 기본: MCP Client를 통한 호출 경로 (네트워크로 MCP 서버에 접속해 Tool 실행)
    from src.day3.manufacturing_mcp_client import call_tool

    return call_tool, "fastmcp"


def get_tool_data(result):
    """
    Tool 응답에서 "실제 알맹이 데이터"를 꺼내는 정규화 헬퍼입니다.

    왜 필요한가:
        - 호출 경로(FastMCP vs fallback)나 Tool에 따라 결과 형태가 조금씩 다릅니다.
          (어떤 건 {"status":"success","data":...}, 어떤 건 {"data":...}, 어떤 건 그냥 값)
        - 요약 Agent가 형태마다 다르게 처리하지 않도록, 여기서 data 부분을 통일해 꺼냅니다.
          (비유: 택배가 어떤 건 이중 포장, 어떤 건 단순 포장으로 와도,
                "안에 든 물건"만 일관되게 꺼내 주는 개봉 담당자 역할)
    출력: 감싸진 data 또는 원본 그대로
    """
    # 표준 성공 응답: {"status": "success", "data": ...}
    #   → 성공 표시가 있으면 그 안의 "data" 칸만 꺼냅니다.
    if isinstance(result, dict) and result.get("status") == "success":
        return result.get("data")

    # data 키만 있는 경우 (status는 없지만 data는 있는 형태)
    if isinstance(result, dict) and "data" in result:
        return result["data"]

    # 그 외에는 받은 값을 그대로 데이터로 간주합니다. (이미 알맹이 형태인 경우)
    return result


def count_items(data) -> int:
    """
    Tool 결과에서 "몇 건인지"를 세는 헬퍼입니다.

    설계 의미:
        - 요약문에 "알람 N건, 공정 상태 M건..."처럼 건수를 적기 위한 공통 계산기입니다.
        - 데이터가 list면 길이를, dict면 미리 약속된 count 키나 list 키를 보고 셉니다.
          (서버 래퍼가 event_count 등으로 건수를 함께 주므로 이를 우선 활용)
        - 이렇게 한 곳에서 세는 규칙을 통일해 두면, 요약 Agent가 결과 형태와 무관하게
          안정적으로 "건수"를 계산할 수 있습니다.
    출력: 항목 개수(정수). 셀 수 없으면 0.
    """
    if isinstance(data, list):   # 데이터 자체가 목록이면 → 목록 길이가 곧 건수
        return len(data)

    if isinstance(data, dict):   # 데이터가 dict(사전)이면 두 단계로 건수를 찾습니다.
        # 1순위: 서버가 넣어 준 *_count 정수 값을 그대로 사용
        #   (서버가 "내가 N건 줬어"라고 미리 세어 알려준 값을 신뢰)
        for count_key in ["event_count", "status_count", "metric_count", "maintenance_count", "result_count"]:
            value = data.get(count_key)
            if isinstance(value, int):   # 그 키가 정수로 들어 있으면 그 값을 건수로 사용
                return value

        # 2순위: 목록 키를 찾아 그 길이로 셈
        #   (count 값이 없으면, 실제 목록이 담긴 키를 찾아 길이를 세어 건수로 사용)
        for list_key in ["events", "statuses", "metrics", "maintenance_history", "results"]:
            value = data.get(list_key)
            if isinstance(value, list):
                return len(value)

    return 0   # list도 dict도 아니거나, 셀 만한 칸이 없으면 0건으로 처리


class CoordinatorAgent:
    """
    [요청 분석 Agent] 사용자 요청에서 후속 처리에 필요한 핵심 정보를 추출합니다.

    ▶ 비유:
        이 Agent는 사용자의 질문을 가장 먼저 읽는 "접수 담당자"입니다.
        제조 현장으로 비유하면, 작업자가 신고한 내용을 접수하고
        "어느 설비에서(equipment_id)", "어떤 알람이 발생했는지(alarm_code)"를
        먼저 정리해 두는 역할입니다. 이 정리가 있어야 다음 담당자들이 일을 시작할 수 있습니다.

    책임:
        - user_query에서 equipment_id, alarm_code를 뽑아 State에 적습니다.
        - 이후 DB/RAG Agent가 무엇을 조회해야 할지의 출발점을 만듭니다.
    State 변화: equipment_id, alarm_code, agent_steps를 기록합니다.
    LangGraph 관점: 그래프의 첫 입력 처리 Node에 해당합니다.
    """

    # agent_name: 이 Agent의 이름표. add_step 기록에 "누가 한 일인지" 표시할 때 씁니다.
    agent_name = "CoordinatorAgent"

    def run(self, state: dict) -> dict:
        # State에서 원본 질문을 읽어 옵니다. (State 읽기)
        #   .get("user_query", "") → 키가 없으면 빈 문자열을 기본값으로 (오류 방지)
        user_query = state.get("user_query", "")

        # 규칙 기반 추출로 핵심 식별자를 뽑습니다. (위에서 정의한 정규식 함수 사용)
        equipment_id = extract_equipment_id(user_query)
        alarm_code = extract_alarm_code(user_query)

        # 추출 결과를 State에 기록합니다. (State 쓰기 → 다음 Agent들이 이 값을 보고 일함)
        state["equipment_id"] = equipment_id
        state["alarm_code"] = alarm_code

        # equipment_id가 없으면 이후 DB 조회 자체가 불가하므로 ERROR로 남깁니다.
        #   (설비를 모르면 "어느 설비를 조회할지"가 없으므로 치명적 → ERROR 등급)
        if equipment_id is None:
            add_step(state, self.agent_name, "[ERROR] equipment_id를 찾을 수 없습니다.")

        # alarm_code는 없어도 전체 알람을 볼 수 있으므로 WARN 수준으로 남깁니다.
        #   (알람 코드를 몰라도 "그 설비의 최근 알람 전체"는 볼 수 있으므로 경고 수준)
        if alarm_code is None:
            add_step(state, self.agent_name, "[WARN] alarm_code를 찾을 수 없습니다.")

        # 정상적으로 무엇을 확인했는지 한 줄 기록을 남깁니다. (성공 여부와 무관하게 흐름 추적용)
        add_step(
            state,
            self.agent_name,
            f"사용자 요청에서 equipment_id={equipment_id}, alarm_code={alarm_code}를 확인했습니다.",
        )

        # 갱신된 State를 그대로 돌려줍니다. → 다음 Agent(또는 다음 LangGraph 노드)로 넘어갑니다.
        return state


class DBInvestigationAgent:
    """
    [DB 조사 Agent] 설비/알람/공정/정비/품질 같은 "사실 데이터"를 DB Tool로 수집합니다.

    ▶ 비유:
        이 Agent는 현장에 나가 "지금 설비가 실제로 어떤 상태인지"를 확인하는 점검 담당자입니다.
        설비 상태, 최근 알람, 공정 상태, 정비 이력, 품질 지표를 차례로 조회해 사실을 모읍니다.
        (DB 결과 = "현재 현장 상태를 보여주는 사실 데이터")

    책임:
        - Coordinator가 추출한 equipment_id/alarm_code로 여러 DB Tool을 순서대로 호출합니다.
        - 결과는 모두 state["db_results"]의 칸에 나눠 담습니다.
    설계:
        - 생성자에서 call_tool 함수를 주입받습니다. 그래서 이 Agent는 MCP/fallback 어느
          경로로 호출되는지 몰라도 됩니다. (load_tool_caller가 정해 줌)
    """

    agent_name = "DBInvestigationAgent"

    def __init__(self, call_tool_func) -> None:
        # 어떤 경로로 Tool을 호출할지는 외부에서 주입받습니다(의존성 주입).
        #   self.call_tool 에 담아 두면, 아래 run()에서 self.call_tool("도구이름", {...})로 부를 수 있습니다.
        self.call_tool = call_tool_func

    def run(self, state: dict) -> dict:
        # Coordinator가 채워 둔 핵심 값들을 State에서 꺼냅니다.
        equipment_id = state.get("equipment_id")
        alarm_code = state.get("alarm_code")

        # equipment_id가 없으면 DB 조회의 기준이 없으므로 전체 DB 단계를 건너뜁니다.
        # (이 가드가 없으면 빈 ID로 무의미한 조회를 하게 됩니다.)
        #   ▶ 이런 "앞단 점검(guard)"은 잘못된 입력으로 뒤 작업이 헛돌지 않게 막는 안전장치입니다.
        if not equipment_id:
            add_step(state, self.agent_name, "[ERROR] equipment_id가 없어 DB Tool 호출을 건너뜁니다.")
            return state   # 더 진행할 수 없으므로 여기서 State를 그대로 반환하고 종료

        # 1) 설비 기본 정보 조회 → db_results에 저장
        #    self.call_tool("도구이름", {입력 인자들}) 형태로 Tool을 호출합니다.
        equipment_status = self.call_tool("get_equipment_status", {"equipment_id": equipment_id})
        state["db_results"]["equipment_status"] = equipment_status

        # 설비 정보에서 line_id를 뽑아 State에 올려 둡니다.
        # 이 line_id는 아래 품질 지표 조회의 입력으로 쓰입니다. (Tool 간 데이터 연결고리)
        #   ▶ 핵심 흐름: "한 Tool의 출력"이 "다음 Tool의 입력"이 되는, 작은 체이닝(연결)입니다.
        equipment_data = get_tool_data(equipment_status)   # 응답에서 알맹이 데이터만 추출
        if isinstance(equipment_data, dict):               # dict 형태일 때만 안전하게 line_id 추출
            state["line_id"] = equipment_data.get("line_id")

        # 2) 최근 알람 이력 조회 (alarm_code가 있으면 해당 알람으로 좁혀짐)
        #    alarm_code가 None이면 그 설비의 최근 알람 전체를 보게 됩니다(앞서 WARN으로 안내).
        recent_alarm_events = self.call_tool(
            "get_recent_alarm_events",
            {"equipment_id": equipment_id, "alarm_code": alarm_code, "limit": 5},
        )
        state["db_results"]["recent_alarm_events"] = recent_alarm_events

        # 3) 최근 공정 상태 조회 (온도/압력 등 공정이 정상 범위였는지 확인용)
        process_status = self.call_tool(
            "get_process_status",
            {"equipment_id": equipment_id, "limit": 3},
        )
        state["db_results"]["process_status"] = process_status

        # 4) 최근 정비 이력 조회 (최근 부품 교체/점검이 알람과 관련 있는지 확인용)
        maintenance_history = self.call_tool(
            "get_maintenance_history",
            {"equipment_id": equipment_id, "limit": 3},
        )
        state["db_results"]["maintenance_history"] = maintenance_history

        # 5) 품질 지표는 line_id가 있어야만 조회 가능합니다(품질은 라인 단위).
        #    line_id를 못 구했으면 이 단계만 건너뛰고 WARN으로 남깁니다.
        #    ▶ 왜 라인 단위인가: 품질은 설비 하나가 아니라 "그 설비가 속한 생산 라인" 기준으로
        #      집계되는 지표라서, 라인 ID가 없으면 조회 자체가 성립하지 않습니다.
        if state.get("line_id"):
            quality_metrics = self.call_tool(
                "get_quality_metrics",
                {"line_id": state["line_id"], "limit": 3},
            )
            state["db_results"]["quality_metrics"] = quality_metrics
        else:
            add_step(state, self.agent_name, "[WARN] line_id를 찾지 못해 품질 지표 조회를 건너뜁니다.")

        # 모든 DB 조회를 마쳤다는 기록을 남깁니다.
        add_step(
            state,
            self.agent_name,
            "교육용 제조 DB Tool을 호출하여 설비 정보, 알람 이력, 공정 상태, 정비 이력, 품질 지표를 확인했습니다.",
        )

        return state


class ManualRAGAgent:
    """
    [RAG 조사 Agent] search_manual Tool로 "조치 절차/기술 문서 근거"를 검색합니다.

    ▶ 비유:
        DB Agent가 "현장 점검 담당"이라면, 이 Agent는 "매뉴얼/기술문서 확인 담당"입니다.
        같은 온도 알람이라도 "그럴 때 어떻게 조치하라"는 절차 근거는 문서에서 찾아야 하므로,
        이 Agent가 기술 문서를 검색(RAG)해 근거를 모아 옵니다.

    ▶ RAG(검색 증강)란? 답을 지어내지 않고, 먼저 관련 문서를 "검색"해 근거로 삼는 방식입니다.

    책임:
        - alarm_code와 사용자 질문을 입력으로 RAG Tool을 호출하고,
          결과를 state["rag_results"]에 저장합니다.
    DB Agent와의 차이:
        - DB Agent는 "현장의 사실"을, 이 Agent는 "대응 지식/절차"를 모읍니다.
          그래서 결과 칸도 db_results와 분리합니다. (사실 ↔ 근거를 섞지 않기 위함)
    """

    agent_name = "ManualRAGAgent"

    def __init__(self, call_tool_func) -> None:
        # DB Agent와 동일하게 call_tool 함수를 주입받습니다. (어느 경로인지 몰라도 됨)
        self.call_tool = call_tool_func

    def run(self, state: dict) -> dict:
        # 검색에 사용할 값들을 State에서 꺼냅니다.
        alarm_code = state.get("alarm_code")
        user_query = state.get("user_query", "")

        # search_manual에 넘길 입력을 구성합니다.
        # symptom은 알람 코드가 있을 때만 교육용 예시 증상을 넣어 검색 신호를 보강합니다.
        # (현업에서는 실제 증상 텍스트나 분류된 증상 코드를 넣게 됩니다.)
        #   ▶ 왜 symptom을 넣나: 알람 코드만으로는 검색어가 빈약할 수 있어, "온도 이상"이라는
        #     증상 키워드를 함께 넣으면 더 관련 높은 문서를 찾을 가능성이 커집니다.
        tool_input = {
            "alarm_code": alarm_code,                                  # 알람 코드(없으면 None)
            "symptom": "temperature abnormal" if alarm_code else None, # 알람 코드 있을 때만 증상 보강
            "query": user_query,                                       # 원본 질문 전체도 검색 신호로 사용
            "top_k": 3,                                                # 상위 3건만 가져오기(과다 결과 방지)
        }

        # RAG Tool 호출 결과를 통째로 rag_results에 저장합니다.
        #   (DB처럼 항목별로 나누지 않고 검색 결과 묶음 자체를 한 칸에 보관)
        rag_result = self.call_tool("search_manual", tool_input)
        state["rag_results"] = rag_result

        add_step(
            state,
            self.agent_name,
            "교육용 기술 문서 검색 Tool을 호출하여 알람 코드와 사용자 요청 관련 근거를 검색했습니다.",
        )

        return state


class IncidentSummaryAgent:
    """
    DB 결과와 RAG 결과를 합쳐 교육용 장애 대응 요약을 만드는 Agent입니다.

    ▶ 비유:
        이 Agent는 "보고서 작성 담당자"입니다. 앞선 담당자들이 모아 둔
        현장 사실(DB)과 매뉴얼 근거(RAG)를 한데 모아, 사람이 읽을 수 있는
        장애 대응 요약 보고서를 만들어 냅니다.

    ▶ 중요한 점: 이 요약은 외부 LLM 호출 없이 "규칙 기반"으로 만든 교육용 결과입니다.
       (실제 운영에서는 이 자리에 LLM 요약, 근거 인용, Guardrail 검토 등이 추가될 수 있습니다.)
    """

    agent_name = "IncidentSummaryAgent"

    def run(self, state: dict) -> dict:
        # 핵심 식별자들을 꺼내되, 없으면 "미확인"으로 표시해 보고서가 비지 않도록 합니다.
        #   ( ... or "미확인" → 앞 값이 None/빈값이면 "미확인"을 사용 )
        equipment_id = state.get("equipment_id") or "미확인"
        alarm_code = state.get("alarm_code") or "미확인"
        line_id = state.get("line_id") or "미확인"

        # 앞 단계에서 모아 둔 두 종류의 결과를 꺼냅니다. (사실 데이터 / 절차 근거)
        db_results = state.get("db_results", {})
        rag_result = state.get("rag_results", {})

        # 각 Tool 결과에서 "알맹이 데이터"만 일관되게 추출합니다. (get_tool_data로 형태 통일)
        equipment_data = get_tool_data(db_results.get("equipment_status", {}))
        alarm_data = get_tool_data(db_results.get("recent_alarm_events", {}))
        process_data = get_tool_data(db_results.get("process_status", {}))
        maintenance_data = get_tool_data(db_results.get("maintenance_history", {}))
        quality_data = get_tool_data(db_results.get("quality_metrics", {}))
        rag_data = get_tool_data(rag_result)

        # 각 결과가 "몇 건"인지 세어 둡니다. (보고서에 건수를 적기 위함 — count_items로 통일)
        alarm_count = count_items(alarm_data)
        process_count = count_items(process_data)
        maintenance_count = count_items(maintenance_data)
        quality_count = count_items(quality_data)
        rag_count = count_items(rag_data)

        # 설비 유형/공정명도 보고서에 넣기 위해 준비합니다. 기본값은 "미확인".
        process_name = "미확인"
        equipment_type = "미확인"

        # 설비 데이터가 dict 형태일 때만 안전하게 세부 값을 꺼냅니다.
        if isinstance(equipment_data, dict):
            process_name = str(equipment_data.get("process_name", "미확인"))
            equipment_type = str(equipment_data.get("equipment_type", "미확인"))

        # 최종 요약 보고서를 하나의 긴 문자열로 만들어 State에 저장합니다.
        #   f"""...{변수}...""" : 여러 줄 문자열 안에 위에서 구한 값들을 그대로 끼워 넣습니다.
        #   ▶ 형식이 Markdown(##, - 등)이라, 나중에 그대로 .md 파일로 저장하면 보기 좋게 렌더링됩니다.
        state["final_summary"] = f"""# 교육용 장애 대응 요약

## 요청 요약
- 설비 ID: {equipment_id}
- 알람 코드: {alarm_code}
- 라인 ID: {line_id}
- 공정/설비 유형: {process_name} / {equipment_type}
- 실행 모드: {state.get("mode")}

## DB 조회 요약
- 최근 교육용 알람 이력 조회 건수: {alarm_count}건
- 최근 공정 상태 조회 건수: {process_count}건
- 최근 정비 이력 조회 건수: {maintenance_count}건
- 최근 품질 지표 조회 건수: {quality_count}건

## 기술 문서 검색 요약
- 교육용 기술 문서 검색 결과: {rag_count}건

## 원인 후보
- 반복 온도 알람이므로 교육용 시나리오 기준으로 온도 제어 상태, 압력/진공 상태 변화, 최근 정비 이력, 공정 상태 변화를 함께 확인해야 합니다.
- 하나의 지표만으로 원인을 확정하지 않고, 알람 이력과 공정 상태, 품질 지표를 함께 비교해야 합니다.

## 1차 조치 방향
- 동일 알람의 반복 발생 시간대와 공정 상태 변화를 먼저 비교합니다.
- 최근 정비 이력 또는 조건 변경 여부를 확인합니다.
- 교육용 기술 문서 검색 결과의 조치 기준을 참고해 점검 항목을 순서대로 확인합니다.

## 추가 확인 항목
- 알람 발생 직전의 온도, 압력, 진공 상태 변화
- 같은 라인의 품질 지표 변화 여부
- 최근 부품 교체, 점검, 조건 변경 여부
- 동일 알람의 반복 주기와 발생 패턴

## 주의
- {EDUCATION_NOTICE}
- 이 요약은 외부 LLM 호출 없이 규칙 기반으로 생성한 교육용 결과입니다.
"""

        add_step(state, self.agent_name, "DB 결과와 RAG 결과를 기반으로 교육용 장애 대응 요약을 생성했습니다.")

        return state

# ──────────────────────────────────────────────────────────────────────
# 여기서부터 LangGraph 관련 코드입니다.
# (위쪽 역할 클래스들은 "일하는 사람"이고, 아래는 그 사람들을 "어떤 순서로 일하게 할지"를
#  그래프(설계도)로 정의하는 부분입니다.)
# ──────────────────────────────────────────────────────────────────────

# StateGraph : LangGraph에서 "노드(처리 단계)와 엣지(순서)를 연결해 흐름을 만드는 설계도" 클래스
# END        : 그래프의 "끝"을 표시하는 특수 지점. 어떤 노드가 END로 연결되면 거기서 흐름이 끝납니다.
from langgraph.graph import StateGraph, END
# TypedDict : "이 dict에는 이런 키들이, 이런 타입으로 들어간다"를 코드로 명시하는 도구입니다.
#             실제 동작을 바꾸지는 않지만, 사람이 State 구조를 한눈에 이해하고
#             편집기(IDE)의 자동완성/오류 검사를 돕는 "설명서" 역할을 합니다.
from typing import TypedDict
class MultiAgentState(TypedDict):
    """
    LangGraph에서 사용할 State 타입입니다.

    기존 create_initial_state()가 반환하는 dict 구조를 타입으로 표현합니다.
    실제 데이터 구조는 기존 dict와 동일하게 유지합니다.
    ▶ 즉, 데이터가 달라지는 게 아니라 "어떤 칸들이 있는지"를 글로 적어 둔 설명서입니다.
    """
    user_query: str          # 원본 사용자 질문
    equipment_id: str | None # 설비 ID (없을 수 있으므로 None 허용)
    alarm_code: str | None   # 알람 코드 (없을 수 있으므로 None 허용)
    line_id: str | None      # 라인 ID (없을 수 있으므로 None 허용)
    db_results: dict         # DB 조회 결과 모음 (사실 데이터)
    rag_results: dict        # RAG 검색 결과 (절차 근거)
    agent_steps: list[str]   # 실행 기록(trace) 목록
    final_summary: str       # 최종 요약 보고서
    mode: str                # 실제 사용된 Tool 호출 모드

def run_multi_agent_flow(user_query: str, mode: str = DEFAULT_MODE) -> dict:
    """
    전체 Multi-Agent 역할 분담 흐름을 실행합니다.

    ▶ 이 함수가 곧 "전체 실행의 진입점"입니다. 사용자 질문을 받아서
       (1) Tool 호출 경로 결정 → (2) Agent들을 LangGraph 노드로 등록 →
       (3) 그래프 조립/컴파일 → (4) 초기 State 준비 후 그래프 실행 → (5) 최종 State 반환
       순서로 진행합니다.
    """
    # (참고) 아래 한 줄은 의도적으로 주석 처리되어 있습니다.
    #   초기 State는 그래프를 다 조립한 뒤(아래쪽)에서 한 번만 만들어 사용합니다.
    #state = create_initial_state(user_query)
    # (1) Tool을 어느 경로로 부를지 결정하고, 호출 함수와 실제 모드명을 받습니다.
    #     call_tool_func : Agent들에게 주입할 "Tool 호출 함수"
    #     actual_mode    : 실제로 정해진 모드("fastmcp"/"fallback") — 보고서에 표시됨
    call_tool_func, actual_mode = load_tool_caller(mode)
    #state["mode"] = actual_mode

    # 실행 시작을 사람이 보기 좋게 콘솔에 안내합니다. (강의 중 화면으로 흐름을 보여주기 위함)
    print("[Day3 Multi-Agent Roles]")
    print("교육용 제조 Multi-Agent 역할 분담 실습을 시작합니다.")
    print(f"실행 모드: {actual_mode}")
    print()

    # (2-a) 각 Agent 객체를 먼저 생성합니다.
    #       DB/RAG Agent에는 위에서 정한 call_tool_func를 주입합니다(의존성 주입).
    #       → 이렇게 미리 만들어 두면 아래 노드 함수들이 이 객체의 run()을 호출만 하면 됩니다.
    coordinator = CoordinatorAgent()
    db_agent = DBInvestigationAgent(call_tool_func)
    rag_agent = ManualRAGAgent(call_tool_func)
    summary_agent = IncidentSummaryAgent()

    # (2-b) LangGraph에 등록할 "노드 함수"들을 정의합니다.
    #
    #   ▶ 왜 Agent.run()을 직접 노드로 쓰지 않고, 얇은 wrapper 함수로 감쌀까요?
    #     - LangGraph 노드는 "State를 입력받아 State를 반환하는 함수" 형태여야 합니다.
    #     - wrapper로 감싸 두면, 실행 직전에 State에 값(mode)을 넣거나
    #       나중에 로그/검증 같은 추가 로직을 끼워 넣기 편해집니다. (확장 지점 확보)
    def coordinator_node(state):
        # coordinator 노드 진입 시, 실제 사용된 모드를 State에 기록해 둡니다.
        state["mode"] = actual_mode
        # 실제 일은 CoordinatorAgent.run()이 합니다. (설비ID/알람코드 추출)
        return coordinator.run(state)

    def db_investigation_node(state):
        # DB 조사 단계: 설비/알람/공정/정비/품질 사실 데이터 수집
        return db_agent.run(state)

    def manual_rag_node(state):
        # RAG 검색 단계: 매뉴얼/기술문서 근거 검색
        return rag_agent.run(state)

    def incident_summary_node(state):
        # 종합 요약 단계: DB 결과 + RAG 결과로 최종 보고서 작성
        return summary_agent.run(state)

    # (3-a) StateGraph(설계도)를 만듭니다. 괄호 안의 MultiAgentState로 State 구조를 알려 줍니다.
    graph_builder = StateGraph(MultiAgentState)

    # add_node("이름", 함수) : 그래프에 "처리 단계(노드)"를 등록합니다.
    #   첫 번째 인자는 노드의 이름표, 두 번째는 실제 실행될 함수입니다.
    graph_builder.add_node("coordinator", coordinator_node)
    graph_builder.add_node("db_investigation", db_investigation_node)
    graph_builder.add_node("manual_rag", manual_rag_node)
    graph_builder.add_node("incident_summary", incident_summary_node)

    # set_entry_point("coordinator") : 그래프가 "어느 노드부터 시작할지"를 지정합니다(시작점).
    graph_builder.set_entry_point("coordinator")

    # add_edge("A", "B") : "A 노드가 끝나면 B 노드로 간다"는 실행 순서(엣지)를 연결합니다.
    #   아래 4줄로 coordinator → db_investigation → manual_rag → incident_summary → END
    #   라는 한 줄짜리(선형) 흐름이 완성됩니다.
    graph_builder.add_edge("coordinator", "db_investigation")
    graph_builder.add_edge("db_investigation", "manual_rag")
    graph_builder.add_edge("manual_rag", "incident_summary")
    graph_builder.add_edge("incident_summary", END)   # 마지막 노드 다음은 END(흐름 종료)

    # (3-b) compile() : 지금까지 그린 "설계도(graph_builder)"를 실제 실행 가능한 그래프 객체로 굳힙니다.
    #                   (설계도를 다 그렸으니 "실행 가능한 기계"로 만드는 단계라고 생각하세요.)
    graph = graph_builder.compile()

    # (4) 그래프 실행에 사용할 State를 준비합니다.
    #     기존 create_initial_state() 구조를 그대로 사용합니다.
    state = create_initial_state(user_query)
    state["mode"] = actual_mode   # 실제 모드를 State에 기록(보고서/노드에서 사용)

    # graph.invoke(state) : 준비된 State를 그래프에 "흘려보내" 실행합니다.
    #   coordinator부터 시작해 엣지를 따라 노드들이 차례로 실행되고,
    #   각 노드가 State를 채워 나간 뒤, 최종 State(final_state)가 반환됩니다.
    final_state = graph.invoke(state)

    # (5) 최종 State를 일반 dict로 변환해 돌려줍니다.
    #     (모든 Agent가 채운 결과 — 추출값, db_results, rag_results, final_summary 등 — 이 들어 있음)
    return dict(final_state)


def save_result_markdown(state: dict) -> Path:
    """
    Mustache 템플릿을 사용해 최종 결과 Markdown을 저장합니다.

    ▶ 왜 파일로 저장하나: 강의 중 실행 결과를 눈으로 확인하고, 다시 열어 비교하기 위함입니다.
    ▶ 왜 템플릿을 쓰나: 보고서의 "틀(레이아웃)"은 .mustache 파일에 두고, "값"만 코드에서 채우면
       디자인 변경 시 코드를 건드리지 않아도 되기 때문입니다. (틀과 데이터의 분리)
    """
    # 결과를 저장할 경로: outputs/day3/day3_multi_agent_roles_result.md
    output_path = get_project_root() / "outputs" / "day3" / "day3_multi_agent_roles_result.md"
    # 저장 폴더가 없으면 자동으로 만듭니다. (parents=True: 중간 폴더까지, exist_ok=True: 있어도 오류 없음)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 사용할 템플릿 파일 경로와 그 내용을 읽어 옵니다.
    template_path = get_project_root() / "templates" / "day3" / "multi_agent_roles_result.mustache"
    template_text = template_path.read_text(encoding="utf-8")

    # template_data : 템플릿의 {{변수}} 자리에 끼워 넣을 "값 묶음"입니다.
    #   State에서 필요한 값을 꺼내되, 없으면 "미확인"/기본값으로 채워 빈 보고서를 방지합니다.
    template_data = {
        "user_query": state.get("user_query", ""),
        "equipment_id": state.get("equipment_id") or "미확인",
        "alarm_code": state.get("alarm_code") or "미확인",
        "line_id": state.get("line_id") or "미확인",
        "mode": state.get("mode", ""),
        "agent_steps": state.get("agent_steps", []),
        "final_summary": state.get("final_summary", "최종 요약이 생성되지 않았습니다."),
    }

    # pystache.render(틀, 값) : 템플릿과 값 묶음을 합쳐 최종 문서 문자열을 만듭니다.
    rendered = pystache.render(template_text, template_data)
    # 만든 문서를 utf-8로 파일에 씁니다.
    output_path.write_text(rendered, encoding="utf-8")

    # 저장한 파일 경로를 돌려줍니다. (호출한 쪽에서 어디에 저장됐는지 출력할 수 있도록)
    return output_path


def main() -> None:
    """
    샘플 Multi-Agent 흐름을 실행하고 Markdown 결과를 저장합니다.

    ▶ 강의자가 터미널에서 이 파일을 실행하면 일어나는 일(순서):
        1) SAMPLE_USER_QUERY(예시 질문)로 Multi-Agent 흐름을 실행하고
        2) 그 결과 State를 Markdown 파일로 저장한 뒤
        3) 저장된 파일 경로를 화면에 출력합니다.
    """
    # 1) 예시 질문으로 전체 흐름 실행 → 모든 Agent가 채운 최종 State를 받습니다.
    state = run_multi_agent_flow(SAMPLE_USER_QUERY, mode=DEFAULT_MODE)
    # 2) 최종 State를 Markdown 파일로 저장하고, 저장 경로를 받습니다.
    output_path = save_result_markdown(state)

    # 3) 저장 완료 안내와 경로를 출력합니다.
    #    상대경로로 바꾸고 \ 를 / 로 바꿔, 어느 환경에서 봐도 읽기 좋게 표시합니다.
    print("[저장 완료]")
    print(str(output_path.relative_to(get_project_root())).replace("\\", "/"))


# if __name__ == "__main__":
#   ▶ 이 조건은 "이 파일을 직접 실행했을 때만" 참이 됩니다.
#     - python src/day3/multi_agent_roles_graph.py 로 직접 실행 → main() 실행됨
#     - 다른 파일에서 import만 했을 때 → main()이 자동 실행되지 않음
#     덕분에 이 파일을 "실행 스크립트"로도, "재사용 모듈"로도 쓸 수 있습니다.
if __name__ == "__main__":
    main()
