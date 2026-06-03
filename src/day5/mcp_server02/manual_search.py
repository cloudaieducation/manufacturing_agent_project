# -*- coding: utf-8 -*-
"""
Day5 mcp_server02 - Manual Search (매뉴얼/RAG 검색 interface 모듈)

[이 모듈의 역할]
search_manual Tool 의 'interface' 계층입니다. 외부(tool_executor)는 이 모듈의
search_manual() 만 호출하며, 실제 RAG 검색 구현은 rag_quality_adapter 로 위임합니다.
adapter 호출이 실패하면 기존 mock 문서로 안전하게 fallback 합니다.

[왜 adapter 로 위임하는가 — 이전 1단계 예제와의 차이]
- 이전 1단계 예제: search_manual 이 mock 만 반환.
- 이번 단계(02): search_manual 은 interface 유지, 실제 검색은
  rag_quality_adapter → rag_search → vector_db/chroma_db(read-only) 로 내려간다.
- 이 모듈은 Day4 rag_quality 를 '직접' import 하지 않는다(adapter 가 감싼다).

[왜 equipment_data 와 분리하는가]
- 설비 조회: 실시간/이력 '사실 데이터' (equipment_data)
- 매뉴얼 검색: 절차/근거 '문서 검색'(RAG 성격) (manual_search)

[보안 원칙]
- 문서 전문(full text)/chroma:document/내부 파일 경로/사내 URL 을 반환하지 않는다.
- doc_id / title / snippet / metadata(허용 key) / matched_alarm_code 같은 '요약 필드'만 반환한다.
- 최종 반환은 security.sanitize_result("search_manual", ...) 가 한 번 더 제한한다.

[전체 흐름에서의 위치]
    tool_executor.execute_single_tool()
        ↓ (tool_name == "search_manual" 인 경우)
    [manual_search.search_manual]  ← interface
        ↓ (정상) rag_quality_adapter.search_manual_documents
        ↓ (실패) mock fallback
    security.sanitize_result("search_manual", ...) 로 정리되어 외부로 반환
"""
# 실제 RAG 검색 구현은 adapter 로 위임한다. 이 모듈은 search_manual 의 '인터페이스'만 유지하고,
# Day4 rag_quality 를 직접 import 하지 않는다(adapter 가 rag_search 계층을 감싼다).
from day5.mcp_server02 import rag_quality_adapter


def _mock_documents(alarm_code=None):
    """adapter 실패 시 사용할 mock 문서(교육용 허구 문서)를 만든다.

    문서 전문/내부 경로/사내 URL 은 포함하지 않고 짧은 snippet 요약만 제공한다.
    """
    code_label = alarm_code or "일반"
    return [
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


def search_manual(query, alarm_code=None, equipment_type=None):
    """매뉴얼/조치 절차 문서를 검색한다(interface).

    [입력]
        query         : 검색 자연어 질의문(필수).
        alarm_code    : 특정 알람 코드로 범위를 좁힐 때 사용(선택).
        equipment_type: 설비 유형으로 필터링할 때 사용(선택).
    [반환]
        요약 dict:
        {
          "query": <질의문>,
          "matched_alarm_code": <alarm_code 또는 None>,
          "documents": [ {"doc_id":..., "title":..., "snippet":..., "metadata":{...}}, ... ],
          "retrieval_source": "chroma" | "mock" | "error" | "mock_fallback",
          "fallback_used": bool
        }

    [동작]
        1) rag_quality_adapter.search_manual_documents(query, alarm_code, equipment_type, top_k=10) 시도.
        2) adapter 호출이 실패(예외)하면 기존 mock 문서로 안전 fallback 한다.
        - top_k 는 adapter 내부 기본값 10 으로 처리한다(이 함수는 top_k 를 인자로 받지 않는다).

    [주의]
        문서 전문/내부 경로/사내 URL 은 어떤 경로에서도 포함하지 않는다.
        adapter 결과는 이후 security.sanitize_result 가 nested whitelist 로 한 번 더 제한한다.
    """
    try:
        # 실제 RAG 검색은 adapter 로 위임(top_k=10 은 adapter 기본값).
        result = rag_quality_adapter.search_manual_documents(
            query, alarm_code=alarm_code, equipment_type=equipment_type
        )
        if isinstance(result, dict) and isinstance(result.get("documents"), list):
            return result
        # 형식이 예상과 다르면 안전하게 mock fallback 으로 처리.
        raise ValueError("adapter 응답 형식이 올바르지 않습니다.")
    except Exception:
        # adapter 호출 실패 → 기존 mock 문서 구조로 fallback(검색 흐름이 끊기지 않게).
        return {
            "query": query,
            "matched_alarm_code": alarm_code,
            "documents": _mock_documents(alarm_code),
            "retrieval_source": "mock_fallback",
            "fallback_used": True,
        }
