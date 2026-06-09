# 벤치마크 선정

PARSEC 3.0은 `native-holdout-v1`에서 blackscholes(연산/금융),
canneal(라우팅 최적화와 불규칙 메모리), dedup(데이터 처리 파이프라인),
streamcluster(스트림 클러스터링)를 썼습니다. `native-holdout-v2`는
blackscholes와 canneal을 유지하고 freqmine(OpenMP 빈도 패턴)과
swaptions(파생상품 시뮬레이션)를 넣었습니다. 스레드는 네 개이고
`native.runconf` 인자는 수정하지 않았습니다.

native 입력은 cirosantilli/parsec-benchmark가 미러한 원본 아카이브입니다.
이 저장소가 명세에 적힌 설치 기준입니다. csail-csg 포크는 RISC-V
교차컴파일이 중심이라 x86-64에는 Ubuntu에서 돌아가는 쪽을 썼습니다.
아카이브 해시, 소스 커밋, 컴파일러 출력, 빌드 실패가 있으면 로컬
`artifacts/setup`에 남깁니다.

CloudSuite Data Caching은 공식 이미지와 Twitter 데이터셋 28배, 서버
10 GB, 서버 스레드 4, 클라이언트 스레드 8, 연결 200, get 비율 0.8입니다.
로더가 뜬 뒤 60초 동안 offered load는 100,000 req/s로 고정입니다. 최대
준수 처리량을 찾는 실험이 아니라 측정 품질 실험입니다. 네트워크는 호스트
하나 위의 전용 Docker bridge입니다. 이미 떠 있던 다른 컨테이너는 끄지
않았고 공유 호스트 한계로 기록했습니다.

calibration은 로컬 branch 예측·working-set 커널과 메모리 간섭용 로컬
STREAM-like triad입니다. 공식 STREAM C 바이너리는 정책 freeze 뒤에
pipeline check로만 실행했습니다. 이 결과로 실제 애플리케이션 성능을
말하지 않습니다.

streamcluster의 공식 native 명령은 입력 파일에 `none`을 쓰고 점을
내부에서 만듭니다. 이 패키지에는 native 입력 아카이브가 없습니다.
swaptions native도 입력 아카이브가 없고 CLI 인자만 씁니다. 임의
워크로드로 바꾼 것이 아니라 공식 애플리케이션 벤치마크 설정입니다.
provenance에 이 경우의 `native.runconf` 해시를 남겼습니다.

출처:

- https://github.com/cirosantilli/parsec-benchmark
- https://github.com/csail-csg/parsec
- https://github.com/parsa-epfl/cloudsuite/blob/main/docs/benchmarks/data-caching.md
- https://github.com/parsa-epfl/memcached-loadtester/tree/v4.0
- https://github.com/jeffhammond/STREAM
