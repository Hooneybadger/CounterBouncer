# 측정 방법

Linux bare-metal에서 `perf stat` JSON을 모읍니다. PARSEC는 공식 native
바이너리를 perf가 직접 감쌉니다. 입력 풀기와 빌드는 측정 밖입니다.
카운터 구간과 런타임 모두 애플리케이션 초기화와 파일 I/O를 포함합니다.
PARSEC hook을 측정 ROI라고 쓰지 않습니다.

CloudSuite는 memcached 서버의 호스트 PID에 붙입니다. Docker CLI나
클라이언트 카운터로 바꾸지 않습니다. 클라이언트는 다른 CPU set에서
돕니다. 서버 카운터 창에는 클라이언트 명령(시작 구간 포함)이 들어갑니다.
로더가 낸 interval 중 앞 두 개를 빼고 통계를 냅니다. 클라이언트 명령은
`timeout`으로 `duration_s=60`에 묶입니다. 12초 sanity는 통계가 없었고
60초 sanity는 있었습니다. 이 시간은 CloudSuite holdout을 시작하기 전에
고쳤습니다.

## 핀과 이벤트

P-core affinity는 `2,4,6,8`입니다. SMT 경쟁은 `3,5,7,9`, 메모리 경쟁은
`24,25,26,27`입니다. UNPINNED는 `0-31`을 허용합니다. 명시한 `cpu_core`
PMU는 E-core 체류를 못 세므로 unpinned run에는
`PARTIAL_HYBRID_PMU_COVERAGE`가 붙습니다. IPC를 PMU 간에 합산하지
않습니다.

CPU 네 개로 pin해도 그 안에서 migration은 일어납니다. 이 정책에서는
그 이동이 하나라도 있으면 DEGRADED입니다. CLEAN이 ACCEPT일 필요는
없었습니다.

카운터 그룹은 cycles/instructions, branches/branch-misses,
cache-references/cache-misses입니다. 파생값은 각 쌍에서 event-runtime과
pcnt-running이 맞을 때만 씁니다. 게이트가 그 run을 REJECT하면 파생값은
탐색용입니다. missing / unsupported / not-counted는 null로 남깁니다.
독립 alias 이벤트 쌍을 같이 요청하면 실제 multiplexing이 생깁니다.
근거는 관측된 running 비율입니다. generic cache 비율은 CPU마다 의미가
다릅니다. 다른 아키텍처에도 통하는 LLC나 대역폭 측정이 아닙니다.

## 반복과 라벨

조건마다 같은 실행 파일과 설정을 씁니다. 워크로드마다 warmup 한 번
뒤에, PARSEC 10회 또는 CloudSuite 5회 repetition block 안에서 조건
순서를 무작위화합니다. 시도는 모두 남깁니다. 인공 값이나 노이즈를
넣지 않습니다. 조건 라벨은 manifest가 만듭니다. 그림의 가로 jitter만
난수입니다. 애플리케이션 측정값은 건드리지 않습니다.

CLEAN은 CounterBouncer가 추가 간섭을 넣지 않았다는 뜻이지 전용
머신이 아닙니다. governor, SMT, load, pressure, 커널, 설정은 run
전후에 남깁니다.

## 정책 freeze

정책 후보는 heuristic이지 업계 표준이 아닙니다. holdout 전에
calibration 각 케이스 10회를 모읍니다. freeze에서 runtime CV degrade는
`max(0.05, 3× CLEAN calibration CV 최댓값)`, reject는
`max(0.20, 2× degrade)`입니다. running 임계는 후보 50/90%를 유지합니다.
migration이 하나라도 있으면 DEGRADED입니다. freeze는 calibration 해시와
시각을 기록합니다. holdout을 보고 정책을 고치지 않습니다.

하드 판정은 run 단위입니다. `HIGH_RUN_VARIANCE`는 그룹 주석입니다.
그 그룹의 매 run이 틀렸다는 증거가 아닙니다.

안정성은 표본 표준편차 / 절댓값 평균, 중앙값, raw MAD, modified-z
이상점 인덱스를 씁니다. 관측이 둘 미만이면 CV는 정의하지 않습니다.
MAD=0이면 이상점 스케일도 정의하지 않고 라벨을 지어내지 않습니다.
실패한 측정은 숫자 요약에서 빼되 시도 수에는 넣고 REJECT로 보존합니다.
편차는 워크로드별 CLEAN 중앙값 기준입니다. runtime 증가 또는
throughput 감소입니다.

CloudSuite latency는 interval p99의 중앙값이지 요청 전체 pooled p99가
아닙니다. 공식 histogram 해상도는 유한합니다. 소스 `timeDiff` 식에는
마이크로초 필드로 보이는 오기가 있습니다. 결과는 로더가 낸 그대로
보고하고 이 한계는 문서에 남깁니다.

같은 동결 CV 정책을 CloudSuite throughput과 interval-p99 요약에도
적용했습니다. 런타임으로 맞춘 CV heuristic을 latency에 옮긴 것은
한계입니다. CloudSuite 측정에 맞춰 latency 임계를 따로 맞추지
않았습니다. 메트릭별 CV와 이유 근거는 둘 다 보고합니다.

Azure는 별도로 suite/test/unit/SKU/region/lifespan으로 층화합니다.
long/short 비교는 같은 메트릭 partition만 짝짓습니다. PMU 참값이
아니고 정확도 라벨도 주지 않습니다.
