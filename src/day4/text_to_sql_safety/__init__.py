# -*- coding: utf-8 -*-
"""
Day4 Text-to-SQL Safety 패키지 - 교육용

이 패키지는 길었던 text_to_sql_safety_checker.py를 역할별로 나누기 위한 묶음입니다.
교육용 리팩토링 1단계에서는 "안전성 정책 상수"만 policies.py로 분리했습니다.

- policies.py : 허용 테이블/민감 컬럼/차단 키워드/SQL Injection 패턴/Intent 키워드 등
  Safety Checker가 사용하는 '규칙표'(정책 상수)를 한곳에 모아 둔 순수 상수 모듈입니다.

(주의) 이 단계에서는 함수 export를 하지 않습니다. 진입점은 여전히
src/day4/text_to_sql_safety_checker.py 이며 실행 방법도 그대로입니다.
"""
