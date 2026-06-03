# mcp_server02 search_manual RAG 검색 성능 평가 보고서 (보완판 v2)

## 1. 평가 기준 변경 요약
- 평가 스크립트 위치 이동: `scripts/day5/` → **`tests/day5/`**.
- `answer_caution_policy` 는 전용 doc_name 이 없어 **doc_hit 을 N/A 처리**(doc_hit_rate 분모 제외).
- `auxiliary_equipment_id_hit` 추가: metadata.equipment_id 공백을 보조 필드로 보완 표시(정식 metadata_hit 과 분리).
- `direct_evidence_found` 추가: query 추출 식별자(alarm_code/equipment_id/process)의 문서 직접 존재 여부.
- quality gate 추가(리포트용, exit code 는 실패로 만들지 않음).
- out_of_scope 분리 / evidence doc·signal 분리 / metadata_gap 유지.

## 2. evidence_type_doc_hit 해석
- doc 기준(`evidence_type_doc_hit`): `metadata.doc_name` 이 전용 문서와 일치.
- signal 기준(`evidence_type_signal_hit`): title/section_title/keywords/snippet signal 부합.
- `answer_caution_policy` 는 전용 doc_name 이 없으므로 **doc_hit=N/A**, signal 로만 판정.
- evidence_type_doc_evaluable_count=14 (answer_caution_policy/none/out_of_scope 제외).

| evidence_type | preferred doc_name | doc_hit 평가 | signal 키워드(일부) |
|---|---|---|---|
| alarm_manual | alarm_manual.md | 평가 | alarm, manual, 알람, 매뉴얼 |
| troubleshooting_manual | troubleshooting_guide.md | 평가 | troubleshooting, 트러블슈팅, 조치, 원인, 반복 |
| quality_standard_document | quality_standard.md | 평가 | quality, 품질, 수율, 불량률, 검사 |
| maintenance_and_troubleshooting_guide | troubleshooting_guide.md | 평가 | maintenance, 정비, troubleshooting, 조치, 반복 |
| answer_caution_policy | - | N/A | caution, policy, 단정, 확정, 근거 |
| none | - | N/A | - |
| out_of_scope | - | N/A | - |

## 3. 주요 지표 요약
| 지표 | 값 |
|---|---|
| total_cases | 20 |
| pass_count | 17 |
| warning_count | 3 |
| fail_count | 0 |
| info_count | 0 |
| error_count | 0 |
| positive_case_count | 17 |
| positive_rank_evaluable_count | 17 |
| keyword_any_hit_rate | 0.85 |
| keyword_all_hit_rate | 0.65 |
| metadata_hit_rate | 0.8235 |
| metadata_partial_hit_rate | 0.0588 |
| metadata_gap_case_count | 1 |
| auxiliary_equipment_id_hit_count | 3 |
| auxiliary_equipment_id_hit_rate | 0.75 |
| evidence_type_doc_evaluable_count | 14 |
| evidence_type_doc_hit_rate | 0.9286 |
| evidence_type_signal_hit_rate | 1.0 |
| evidence_type_hit_rate | 1.0 |
| hit_at_1_positive | 0.8824 |
| hit_at_3_positive | 0.9412 |
| hit_at_5_positive | 1.0 |
| hit_at_10_positive | 1.0 |
| mean_mrr_positive | 0.9235 |
| out_of_scope_case_count | 3 |
| out_of_scope_warning_count | 3 |
| out_of_scope_fail_count | 0 |
| out_of_scope_false_positive_count | 0 |
| direct_evidence_found_count | 16 |
| direct_evidence_missing_count | 3 |
| chroma_count | 20 |
| fallback_count | 0 |
| avg_returned_doc_count | 10.0 |
| forbidden_field_case_count | 0 |

## 4. quality gate 결과 (리포트용)
- 전체 통과: **True** (gate 실패해도 exit code 는 0)
| gate | threshold | actual | passed |
|---|---|---|---|
| min_positive_hit_at_3 | 0.9 | 0.9412 | True |
| min_mean_mrr_positive | 0.9 | 0.9235 | True |
| min_keyword_any_hit_rate | 0.8 | 0.85 | True |
| min_evidence_type_doc_hit_rate | 0.7 | 0.9286 | True |
| max_forbidden_field_case_count | 0 | 0 | True |
| max_fallback_count | 0 | 0 | True |
| max_fail_count | 0 | 0 | True |

## 5. 케이스별 결과
| case_id | type | status | oos | docs | kw_all | md_hit | md_part | aux_eq | ev_doc | ev_sig | direct | hit@1 | mrr |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RAG-EVAL-001 | direct_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-002 | direct_evidence | PASS | False | 10 | False | False | True | True | False | True | True | True | 1.0 |
| RAG-EVAL-003 | direct_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-004 | multi_document_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-005 | out_of_scope | WARNING | True | 10 | False | False | False | None | None | None | False | None | None |
| RAG-EVAL-006 | multi_document_evidence | PASS | False | 10 | False | True | False | True | True | True | True | True | 1.0 |
| RAG-EVAL-007 | multi_document_evidence | PASS | False | 10 | True | True | False | True | True | True | True | True | 1.0 |
| RAG-EVAL-008 | multi_document_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-009 | out_of_scope | WARNING | True | 10 | False | False | False | False | None | None | False | None | None |
| RAG-EVAL-010 | low_confidence | PASS | False | 10 | False | None | None | None | None | True | True | False | 0.5 |
| RAG-EVAL-011 | direct_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-012 | multi_document_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-013 | direct_evidence | PASS | False | 10 | False | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-014 | direct_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-015 | multi_document_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-016 | multi_document_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-017 | direct_evidence | PASS | False | 10 | True | True | False | None | None | True | True | True | 1.0 |
| RAG-EVAL-018 | multi_document_evidence | PASS | False | 10 | True | True | False | None | True | True | True | True | 1.0 |
| RAG-EVAL-019 | out_of_scope | WARNING | True | 10 | False | None | None | None | None | None | False | None | None |
| RAG-EVAL-020 | low_confidence | PASS | False | 10 | True | None | None | None | None | True | None | False | 0.2 |

## 6. metadata gap / auxiliary 분석
- **RAG-EVAL-002**: matched={'alarm_code': 'ALM-TEMP-402'} missing=['equipment_id'] aux_eq_hit=True(rank=1)
- **RAG-EVAL-006**: matched={'alarm_code': 'ALM-TEMP-402'} missing=[] aux_eq_hit=True(rank=6)
- **RAG-EVAL-007**: matched={'alarm_code': 'ALM-TEMP-402'} missing=[] aux_eq_hit=True(rank=6)

## 7. direct evidence 분석 (out_of_scope 포함)
- **RAG-EVAL-005** [WARNING] direct_found=False matched=[] missing=['ALM-9999']
- **RAG-EVAL-009** [WARNING] direct_found=False matched=[] missing=['ALM-PRESS-105', 'EQP-CVD-02', 'cvd']
- **RAG-EVAL-019** [WARNING] direct_found=False matched=[] missing=['etch']
- 해석: out_of_scope 에서 direct_evidence_found=false 는 '유사 문서만 검색됨'을 시사. 강한 거절/확정 근거 억제는 Guardrail 단계로 이관(이번 단계 미구현).

## 8. positive 검색 지표 (out_of_scope 제외)
- positive_rank_evaluable_count=17
- hit@1=0.8824, hit@3=0.9412, hit@5=1.0, hit@10=1.0, mean_mrr=0.9235

## 9. 파일 위치 변경
- 평가 스크립트는 `scripts/day5/evaluate_mcp_server02_rag.py` 에서 `tests/day5/evaluate_mcp_server02_rag.py` 로 이동했다. 실행 경로/루트 탐색은 동일하게 동작한다.

## 10. 개선 제안
- 검색 코드 수정 없이도, doc_hit N/A·auxiliary·direct_evidence 도입으로 지표 '해석'이 정확해졌다.
- 추후 rerank 보강 시 오버피팅 금지: expected_* 라벨/case_id 전용 분기 금지, 일반 정규식·키워드만.
- Guardrail 단계로 이관: out_of_scope 확정 근거 억제/거절, 범위밖 공정 판정, 부분 근거 종합 판단.
- TODO: CI/회귀 단계에서 `--fail-on-gate` 옵션으로 quality gate 실패 시 exit code 1 처리.
