# 한계

공유 bare-metal i9-14900K 한 대입니다. CLEAN은 전용 머신이 아닙니다.
`native-holdout-v1` PARSEC 동안 프로젝트 memcached가 떠 있었고,
`native-holdout-v2` PARSEC는 그 컨테이너만 끊었습니다.

HYBRID에서 `cpu_core`는 E-core 시간을 못 셉니다. pin 안
`cpu-migrations`만으로는 integrity가 떨어지지 않습니다. freqmine
CLEAN 10회는 CPU `0`으로 나갔습니다.

`native-holdout-v2` CloudSuite 30회는 서버 스레드가 pin 밖으로 나가
INVALID입니다. `native-cloudsuite-v2.1`은 그 30회를 그대로 두고, pin을
고친 뒤 CLEAN 5 / MEMORY 5만 추가했습니다.

p99는 interval p99의 중앙값입니다. loadtester `timeDiff` 오기는
그대로 뒀습니다. runtime CV degrade 0.5086은 CLEAN `cache-large`
CV 0.1695에서 나왔고, 이 임계로는 `HIGH_RUN_VARIANCE`가 안
붙었습니다. v2 holdout의 `git_dirty`는 true입니다.

주파수와 터보는 그대로 뒀습니다. generic cache를 만능 LLC나 대역폭으로
쓰지 않습니다. REFERENCE와 Azure는 PMU 참값이 아닙니다.
`pcnt-running` 고정 임계는 heuristic입니다. 시간 위상과 메트릭 종류는
아직 안 넣었습니다.
