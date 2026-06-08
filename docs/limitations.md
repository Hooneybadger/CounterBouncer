# 한계

공유 bare-metal i9-14900K 한 대입니다. 기존 컨테이너와 통제하지 않은
호스트 활동이 있습니다. 격리된 전용 호스트라고 쓰지 않습니다.

CloudSuite memcached 서버는 PARSEC holdout 동안 그대로 떠 있었습니다.
blackscholes 뒤에 끄면 그 표본이 갈라지므로 그냥 뒀습니다. CLEAN은
CounterBouncer가 간섭을 더 넣지 않았다는 뜻이지 빈 호스트가 아닙니다.

하이브리드 P/E에서 명시한 P-core 이벤트는 UNPINNED의 E-core 시간을
빠뜨립니다. 이 캠페인에서는 그 측정을 degrade했습니다.

CPU 네 개로 affinity를 걸어도 그 집합 안의 스레드 이동은 남습니다.
이 정책은 그 이동을 측정 품질 저하로 봅니다.

PMU 스케줄링 비율이 정확도를 증명하지 않습니다. 동시에 센 값도
체계적으로 치우칠 수 있습니다.

동적 주파수와 터보는 관측만 했고 고정하지 않았습니다. E5는 선택 항목이고
하지 않았습니다.

generic cache 이벤트는 CPU마다 매핑이 다릅니다. 다른 CPU에도 그대로
쓰는 메모리 대역폭, CXL, 가속기 카운터라고 쓰지 않습니다.

PARSEC 시간은 프로세스 전체입니다. 초기화와 I/O가 들어가고 hook만의
ROI가 아닙니다.

CloudSuite는 로컬 Docker bridge에서 고정 offered load입니다. 최대
처리량이나 분산 네트워크 실험이 아닙니다.

CloudSuite PMU 창에는 클라이언트 시작이 들어갑니다. 보고하는
interval-p99 중앙값은 pooled p99가 아닙니다.

공식 loadtester v4.0 `stats.c`의 `timeDiff`는 `tv_sec`를 두 번 씁니다.
소스를 조용히 고치지 않았습니다.

같은 동결 runtime CV를 CloudSuite throughput과 interval-p99 요약에도
적용했습니다. 런타임으로 맞춘 CV heuristic을 latency에 옮긴 것은
한계로 남깁니다.

동결한 heuristic 임계와 적은 반복 수로 일반 정확도나 인과를 주장하지
않습니다.

그룹 분산은 불안정하다는 근거이지 그 그룹의 매 run이 무효라는 단언이
아닙니다.

calibration 커널, 로컬 STREAM-like triad, freeze 이후 공식 STREAM
pipeline check는 보조입니다. Azure 자료는 클라우드 변동의 외부 근거이지
PMU 참값이 아닙니다.
