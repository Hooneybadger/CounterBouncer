1. 제출 파일
    - "Base.hpp": c++ 코드에서 사용되는 타입 별칭(type alias), 인라인 함수, 상수 등을 정의하는 c++ 헤더 파일
    - "Graph.hpp": Deck graph의 노드 클래스를 선언하는 헤더 파일
    - "myalgorithm.cpp": 알고리듬을 실행하는 c++ 소스 코드
    - "myalgorithm.hpp": "myalgorithm.cpp" 파일의 헤더 파일
    - "function.cpp": "myalgorithm.cpp" 파일의 알고리듬에 필요한 함수들의 구현이 있는 소스 코드
    - "function.hpp": "function.cpp" 파일의 헤더 파일
    - "build.sh": "function.cpp", "myalgorithm.cpp" 파일로 "lib_myalgorithm.so" 파일을 만드는 shell 파일
    - "lib_myalgorithm.so": "build.sh" 파일 실행을 통해 만들어지는 shared object 파일
    - "myalgorithm.py": 문제의 입력을 받아 "lib_myalgorithm.so" 파일에 있는 알고리듬을 실행하는 함수를 가지고 있는 파일
    - "util.py": 주최측에서 제공하는 파일

2. 외부 라이브러리
    - Gurobi의 설치가 필요합니다.

3. 알고리듬 실행 방법:
    1. "build.sh" 파일을 실행하여 "lib_myalgorithm.so" 파일 생성
    2. "myalgorithm.py" 파일의 algorithm 함수 실행


문의 사항은 newsky0329@snu.ac.kr로 연락 바랍니다.