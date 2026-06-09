# 한계

공유 bare-metal i9-14900K 한 대입니다. 기존 컨테이너와 통제하지 않은
호스트 활동이 있습니다. 격리된 전용 호스트라고 쓰지 않습니다.

`native-holdout-v1` PARSEC 동안 CloudSuite memcached는 그대로 떠
있었습니다. `native-holdout-v2` PARSEC는 프로젝트 컨테이너를 끈 뒤
CLEAN을 돌렸습니다. 다른 랩 Docker는 죽이지 않으므로 CLEAN은 여전히
전용 머신이 아닙니다.

하이브리드 P/E에서 명시한 P-core 이벤트는 HYBRID의 E-core 시간을
빠뜨립니다. 그 측정은 integrity INVALID입니다.

CPU 네 개로 affinity를 걸어도 그 집합 안의 스레드 이동은 남습니다.
그 이동만으로는 integrity를 떨어뜨리지 않습니다. 허용 집합을 벗어나면
`AFFINITY_ESCAPE`입니다. freqmine CLEAN 10회는 CPU `0`으로 나갔습니다.

CloudSuite 서버 스레드는 pin과 P-core를 벗어나 30회 전부 integrity
INVALID입니다. Docker 워크로드의 호스트 PID attach 한계입니다.

PMU 스케줄링 비율이 정확도를 증명하지 않습니다. REFERENCE는 상대 비교를
위한 minimal-event group이지 절대 참값이 아닙니다.

동적 주파수와 터보는 관측만 했고 고정하지 않았습니다. E5는 하지
않았습니다.

generic cache 이벤트는 CPU마다 매핑이 다릅니다. 다른 CPU에도 그대로
쓰는 메모리 대역폭, CXL, 가속기 카운터라고 쓰지 않습니다.

PARSEC 시간은 프로세스 전체입니다. 초기화와 I/O가 들어가고 hook만의
ROI가 아닙니다.

CloudSuite는 로컬 Docker bridge에서 고정 offered load입니다. 보고하는
interval-p99 중앙값은 pooled p99가 아닙니다.

공식 loadtester v4.0 `stats.c`의 `timeDiff`는 `tv_sec`를 두 번 씁니다.
소스를 조용히 고치지 않았습니다.

`native-holdout-v2` runtime CV degrade 0.5086은 CLEAN `cache-large`
캘리브레이션 CV 0.1695에서 나왔습니다. 이 컷에서는 그룹
`HIGH_RUN_VARIANCE`가 붙지 않았습니다.

holdout 270회의 `git_dirty`는 true입니다. 게이트 코드가 측정 중에
아직 커밋되지 않았습니다.

동결한 heuristic 임계와 적은 반복 수로 일반 정확도나 인과를 주장하지
않습니다.

calibration 커널과 Azure 자료는 보조입니다. PMU 참값이 아닙니다.
