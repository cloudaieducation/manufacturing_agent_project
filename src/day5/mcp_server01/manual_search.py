# -*- coding: utf-8 -*-
"""
Day5 mcp_server01 - Manual Search (매뉴얼/RAG 검색 모듈)

[이 모듈의 역할]
search_manual Tool 을 위한 매뉴얼/트러블슈팅 문서 검색 계층입니다.
1차 구현은 mock 응답만 반환합니다.

[왜 equipment_data 와 분리하는가]
search_manual 은 설비 API/DB 조회(상태/알람/품질 등)와 성격이 다릅니다.
- 설비 조회: 실시간/이력 '사실 데이터' (equipment_data)
- 매뉴얼 검색: 절차/근거 '문서 검색'(RAG 성격) (manual_search)
책임을 분리해 두면, 2차에서 한쪽은 API Gateway 로, 다른 한쪽은 벡터 검색으로
독립적으로 확장할 수 있습니다.

[보안 원칙]
- 문서 전문(full text)이나 내부 파일 경로/사내 URL 을 반환하지 않는다.
- doc_id / title / snippet / matched_alarm_code 같은 '요약 필드'만 반환한다.

[전체 흐름에서의 위치]
    tool_executor.execute_single_tool()
        ↓ (tool_name == "search_manual" 인 경우)
    [manual_search.search_manual]
        ↓
    security.sanitize_result("search_manual", ...) 로 정리되어 외부로 반환

TODO(2차):
    - day2/day3 의 Chroma 벡터 검색 또는 RAG tool 과 연동
    - 문서 본문 대신 snippet 만 노출하는 정책 유지
"""


def search_manual(query, alarm_code=None, equipment_type=None):
    """매뉴얼/조치 절차 문서를 검색한다(1차: mock).

    [입력]
        query         : 검색 자연어 질의문(필수).
        alarm_code    : 특정 알람 코드로 범위를 좁힐 때 사용(선택).
        equipment_type: 설비 유형으로 필터링할 때 사용(선택).
    [반환]
        요약 dict:
        {
          "query": <질의문>,
          "matched_alarm_code": <alarm_code 또는 None>,
          "documents": [ {"doc_id":..., "title":..., "snippet":...}, ... ]
        }

    [동작]
        mock: 가상 문서 1~2건의 요약만 반환한다.
        문서 전문/내부 경로/사내 URL 은 절대 포함하지 않는다.

    [주의]
        반환 문서는 DisplayEdu Fab 가상 시나리오의 허구 문서이며,
        실제 사내 매뉴얼이 아니다. snippet 은 짧은 발췌만 제공한다.
    """
    # mock 문서: alarm_code 가 있으면 해당 코드 관련 문서를 우선 제목에 반영.
    code_label = alarm_code or "일반"
    documents = [
        {
            "doc_id": "EDU-MANUAL-0001",
            "title": f"{code_label} 알람 조치 절차(교육용)",
            "snippet": "온도 상승 알람 발생 시 우선 설비 상태와 최근 알람 이력을 확인하고, "
                       "절차에 따라 점검 항목을 순서대로 확인합니다.",
        },
        {
            "doc_id": "EDU-MANUAL-0002",
            "title": "증착 공정 트러블슈팅 개요(교육용)",
            "snippet": "공정 상태와 품질 지표를 함께 점검해 원인 후보를 좁히는 일반 절차를 설명합니다.",
        },
    ]
    return {
        "query": query,
        "matched_alarm_code": alarm_code,
        "documents": documents,
    }
