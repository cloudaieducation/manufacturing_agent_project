# -*- coding: utf-8 -*-
"""
Day5 mcp_client02 패키지 실행 진입점.

[__main__.py 가 진입점이 되는 이유]
Python 에서 `python -m day5.mcp_client02` 처럼 '패키지'를 -m 옵션으로 실행하면, Python 은
그 패키지 안의 __main__.py 를 찾아 실행합니다. 즉 이 파일이 패키지를 모듈로 실행할 때의 시작 지점입니다.

[실행 순서]
1) 아래에서 client_app 의 main 함수를 import 한다.
2) __name__ == "__main__" (이 파일이 직접 실행된 경우)일 때 main() 을 호출한다.
3) 실제 인자 처리(argparse)와 그래프 실행은 client_app.main() 안에서 이루어진다.
(client_app.py 를 직접 실행하는 것과 동일하게 동작한다.)
"""
from day5.mcp_client02.client_app import main


if __name__ == "__main__":
    main()
