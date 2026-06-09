# 측정 방법

Linux bare-metal에서 `perf stat` JSON을 모읍니다. PARSEC는 공식 native
바이너리를 perf가 직접 감쌉니다. 입력 풀기와 빌드는 측정 밖입니다.
카운터 구간과 런타임 모두 애플리케이션 초기화와 파일 I/O를 포함합니다.
측정 구간을 PARSEC hook으로 자르지 않습니다.

CloudSuite는 memcached 서버의 호스트 PID에 붙입니다. Docker CLI나
클라이언트 카운터는 안 씁니다. 클라이언트는 다른 CPU set에서
돕니다. 서버 카운터 창에는 클라이언트 명령(시작 구간 포함)이 들어갑니다.
로더가 낸 interval 중 앞 두 개를 빼고 통계를 냅니다. 클라이언트 명령은
`timeout`으로 `duration_s=60`에 묶입니다.

## 핀과 이벤트

P-core affinity는 `2,4,6,8`입니다. SMT 경쟁은 `3,5,7,9`, 메모리 경쟁은
`24,25,26,27`입니다. PCORE는 `/sys/devices/cpu_core/cpus`(이 호스트는
`0-15`) 안에서만 이동합니다. HYBRID는 present CPU 전체이며 `cpu_core`
부분 coverage를 의도적으로 봅니다. IPC는 PMU끼리 합치지 않습니다.

pin 안 `cpu-migrations`만으로는 integrity가 떨어지지 않습니다.
프로세스 트리의 관측 CPU를 읽어 affinity 이탈, P/E 이동,
NUMA 이동을 봅니다.

카운터 그룹은 cycles/instructions, branches/branch-misses,
cache-references/cache-misses입니다. 파생값은 각 쌍에서 event-runtime과
pcnt-running이 맞을 때만 씁니다. missing / unsupported / not-counted는
null로 남깁니다. 독립 alias 이벤트 쌍을 같이 요청하면 실제
multiplexing이 생깁니다. generic cache 비율은 CPU마다 의미가 다릅니다.

REFERENCE는 `{cpu_core/cycles, cpu_core/instructions}`와 software
이벤트만 요청합니다. 절대 참값이 아니라 high-coverage minimal-event
group입니다.

## 반복과 라벨

조건마다 같은 실행 파일과 설정을 씁니다. 워크로드마다 warmup 한 번
뒤에, PARSEC 10회 또는 CloudSuite 5회 repetition block 안에서 조건
순서를 무작위화합니다. 시도는 모두 남깁니다. 조건 라벨은 manifest가
만듭니다. 그림의 가로 jitter만 난수입니다.

CLEAN은 CounterBouncer가 추가 간섭을 안 넣었다는 뜻입니다. 전용
머신은 아닙니다. `native-holdout-v2` PARSEC는 프로젝트 CloudSuite
컨테이너를 끈 뒤에 돌립니다. 다른 랩 컨테이너는 그대로 둡니다.

## 정책 freeze

정책 후보는 heuristic입니다. 업계 표준은 아닙니다. holdout 전에
calibration 각 케이스 10회를 모읍니다. freeze에서 runtime CV degrade는
`max(0.05, 3× CLEAN calibration CV 최댓값)`, reject는
`max(0.20, 2× degrade)`입니다. running 임계는 후보 50/90%를 유지합니다.
CloudSuite 그룹 안정성은 interval-p99 CV입니다. latency cutoff는
freeze 전에 정책 파일에 적어 둔 후보 heuristic입니다.

`native-holdout-v1` 정책은 `configs/experiment.yaml`에 그대로 둡니다.
새 캠페인은 `configs/experiment_v2.yaml`만 씁니다. holdout을 보고 정책은
그대로 둡니다.

하드 판정은 run 단위입니다. `HIGH_RUN_VARIANCE`는 그룹 주석입니다.

