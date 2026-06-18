# 4코어 시드 포트폴리오: 유휴 코어로 ALNS 분산을 잡는다

> 처음 보는 용어([ALNS](../GLOSSARY.md), [무회귀](../GLOSSARY.md), [feasibility-first](../GLOSSARY.md), [시간 가드](../GLOSSARY.md))는 용어집에 정의해 두었습니다.

- **state**: 구현 · 측정완료
- **코드**: `src/myalgorithm.py`의 `algorithm`(오케스트레이터)·`_construct_incumbent`(메인 1회 구성)·`_improve`(시드별 ALNS+선호개선, 메인·워커 공용)·`_worker_improve`(워커 본체)·`_n_workers`.
- **관련 결정**: [STRATEGY_PLAN](../STRATEGY_PLAN.md) P4c·B3 · **배경**: [LEARNING_GUIDE](../LEARNING_GUIDE.md) E2 · **위에 섬**: [features/06](./06-alns.md)·[features/09](./09-preference-polish.md)
- **측정**: `results/dev_swap2_60s`(단일 시드 베이스), `results/dev_p4c3_60s`·`results/dev_p4c3_gate10s`(포트폴리오), `results/p4c3_j1_sub`(저경합 서브셋), 시드 헤드룸 `learning/p4c_seedvar.py`

## 한눈에

평가 서버는 솔버 하나에 **4코어**를 주는데, 우리 알고리즘은 순수 파이썬 단일 스레드라 코어 셋이 논다. 게다가 [ALNS](./06-alns.md)는 시드에 따라 전혀 다른 궤적을 그린다. 같은 인스턴스를 시드만 바꿔 네 번 돌리면 prob_16은 obj가 (max−min)/min 기준 37.7%나 벌어진다. 단일 시드는 복권이라, 운 나쁜 추첨 하나에 갇혀 있었던 셈이다.

먼저 헤드룸을 쟀다(`learning/p4c_seedvar.py`, `--repeat 4`로 시드를 흔들어). best-of-4가 13개 중 7개에서 단일 시드를 이겼고, prob_16은 −27.4%였다. 그래서 노는 코어에 시드를 흩뿌린다. 메인이 시드 0을, 워커 셋이 시드 1~3을 병렬로 풀고 best feasible을 취한다. best-of는 시드 0(=옛 단일 실행)을 포함하므로 그보다 나빠질 수 없다.

설계가 한 번 뒤집혔다. 처음엔 워커마다 전체 파이프라인(구성 포함)을 독립으로 돌렸는데, 4잡 병렬 측정(코어당 4프로세스 = 16개 활성)에서 큰 인스턴스가 *무너졌다*. 경합이 [scan 구성](./05-temporal-nesting.md)을 늦춰 더 나쁜 base로 추락하니 prob_38이 70M→76M, prob_40이 +22.9%, 순위 시뮬이 65→60으로 *퇴보*했다. 진단은 분명했다. **구성은 경합에 취약하고, 시드와 무관하다.** 그래서 구성을 메인에서 한 번만 하고 그 incumbent를 [fork](../GLOSSARY.md)로 워커에 공유해, *ALNS와 선호개선만* 병렬화하도록 고쳤다. 그러자 큰 인스턴스의 구성이 경합 전에 끝나 보호된다. 같은 비관적 16-활성 측정에서 순위 시뮬이 **61→68**로 올랐고 prob_38·40·33은 무회귀(tie)다. 솔버 하나만 도는 저경합(실서버에 가까운) 조건에선 12개 서브셋에서 **8승 0패**다.

## 왜 이게 필요했나

[P5a](./07-lower-bound.md)가 큰 인스턴스의 병목은 시간이 아니라 *이동의 질*이라 했고, [선호 polish/swap](./09-preference-polish.md)을 만들며 거듭 부딪힌 벽은 *ALNS의 벽시계 비결정성*이었다. 같은 시드도 머신 부하로 반복 수가 갈려 obj가 ±1~2% 흔들렸고, 그게 단일 실행 비교를 더럽혔다. 두 문제가 한 손잡이를 가리켰다. ALNS는 시드에 민감하고 분산이 크니, 그 분산을 *낭비하지 말고 활용*하면 된다. 마침 코어 셋이 놀고 있었다.

헤드룸은 추측이 아니라 측정이다. `--repeat 4`로 시드를 흔들어(`OGC_RUN_INDEX`가 ALNS 시드를 민다) best-of-4를 보니, prob_16 −27.4%, prob_21 −8.6%, prob_20 −6.2% 등 7/13에서 단일을 이겼고 평균 3.68%였다. 분산이 큰 인스턴스(prob_16 spread 37.7%, prob_18 34.1%)일수록 best-of의 이득이 컸다. [분산 최소화가 평균보다 먼저](../STRATEGY_PLAN.md)인 이 프로젝트에서, best-of는 운 나쁜 추첨(−1에 가까운 해)을 걸러내는 장치이기도 하다.

## 하는 일과 내부 동작

`algorithm`은 셋을 차례로 한다. 먼저 `_construct_incumbent`가 [구성 포트폴리오](./04-insertion-order-portfolio.md)를 *한 번* 돈다. 구성은 결정적이라 시드와 무관하므로 워커마다 되풀이할 이유가 없고, 무엇보다 경합에 취약한 이 단계를 워커가 뜨기 *전에* 끝내야 한다. 그다음 [fork 컨텍스트](../GLOSSARY.md)의 daemon `Process` 셋을 띄워 시드 1~3을 병렬로 풀고, 메인은 시드 0을 in-process로 푼다. 시드별 풀이 `_improve`는 ALNS(seed) → [선호 polish → 교환 swap](./09-preference-polish.md) → `check_feasibility` 중재로, feasible할 때만 `(obj, 해)`를 돌려준다. 마지막에 best feasible obj를 취한다(`myalgorithm.py`의 `algorithm`).

fork를 고른 데는 두 이유가 있다. 하나는 **무거운 인자를 공유**하기 위해서다. 워커는 메인이 만든 incumbent(`committed`)와 [래스터 엔진](./02-raster-engine.md)(`ir`)을 fork의 [copy-on-write](../GLOSSARY.md)로 상속받는다. 직렬화 없이 페이지를 공유하다가, ALNS가 `committed`를 제자리 변형하는 순간에만 그 페이지가 워커별로 복사돼 서로 격리된다. 그래서 워커마다 같은 incumbent에서 출발하되 독립으로 흩어진다. 둘은 **종료가 행을 만들지 않게** 하기 위해서다. daemon 프로세스는 메인이 끝나면 자동으로 죽으므로, 워커가 어떤 이유로 마감을 못 지켜도 메인이 종료에서 멈추지 않는다. 그 멈춤은 [시간 가드](../GLOSSARY.md)를 넘겨 −1이 되므로 무슨 일이 있어도 막아야 한다. 수확이 끝나면 살아있는 워커를 명시적으로도 `terminate`한다.

[feasibility-first](../GLOSSARY.md)는 세 겹으로 지킨다. 워커가 다 죽어도 메인의 시드 0(=옛 단일 실행)이 남고, fork 자체가 막히면(서버가 seccomp로 차단하는 등) `try/except`가 단독 실행으로 떨어지며, 그래도 안 되면 floor가 있다. 즉 멀티프로세싱이 통째로 실패해도 *정확히 옛 production 결과*가 나온다. 포트폴리오는 순수 upside다. 워커 수는 `_n_workers`가 `os.sched_getaffinity`로 잡아([taskset](../GLOSSARY.md) 핀을 존중해 서버에서 4), 핀된 코어에 정확히 맞춘다.

## 버린 선택지들

처음엔 `concurrent.futures`의 **`ProcessPoolExecutor`**를 썼다. 측정 로그가 바로 깨뜨렸다 — `PicklingError: Can't pickle _solve_once ... not the same object as myalgorithm._solve_once`. 평가 서버(와 우리 `batch_runner`)가 `myalgorithm`을 `importlib`로 *커스텀 이름*으로 로드해 `sys.modules`에 등록하지 않는데, `ProcessPoolExecutor`는 작업 함수를 qualified-name으로 피클하므로 워커가 그 함수를 되찾지 못한다. fork `Process`는 함수·인자를 피클하지 않고 메모리로 상속하므로 이 문제가 없다. 이 실패가 fork 설계의 근거다.

**워커마다 구성을 재실행**하는 첫 설계는 앞서 적은 대로 큰 인스턴스를 무너뜨렸다(16-활성에서 prob_38 76M, prob_40 +22.9%, 순위 65→60). 구성을 공유하는 재설계가 이를 *측정으로* 고쳤다(같은 16-활성에서 prob_38·40 무회귀, 순위 61→68). 이 on/off가 "무엇을 병렬화하지 *않을지*"가 핵심임을 보이는 좋은 ablation이다.

**워커를 더 많이** 띄우는 길(예: 하이퍼스레드까지 8개)은 메모리 대역폭 경합을 키워 시드마다의 ALNS를 더 얕게 만든다. 핀된 물리 코어 수(4)에 맞추는 게 균형점이었다.

## 언제·어디서 작동하나

포트폴리오는 구성 뒤 ALNS 단계에서 켜진다. 이득이 큰 곳은 *시드 분산이 큰* 인스턴스다. obj1=0의 중형들이 대표적이고, 특히 [선호 swap](./09-preference-polish.md)이 못 깨던 prob_6(−22.4%)·prob_9(−15.6%)를 다른 시드의 ALNS 궤적이 풀어낸다. 반대로 큰 인스턴스(prob_38·40)는 ALNS가 거의 안 도는 결정적 영역이라 모든 시드가 같은 자리에 모여 best-of≈시드0, 곧 무회귀다. 짧은 제한시간(10초)에서도 시드 다양성이 작아 ≈시드0이라 손해가 없다. fork가 막히거나 코어가 하나뿐이면 단독 실행으로 물러난다.

## 검증과 한계

저경합(솔버 하나, 실서버에 가까운) 조건을 `-j 1`로 모사한 12개 서브셋(`results/p4c3_j1_sub` vs `results/dev_swap2_60s`)에서 **8승 0패 4무**다 — prob_16 −27.4%, prob_6 −22.4%, prob_11 −20.1%, prob_9 −15.6%, prob_20 −6.2%, 큰 인스턴스(prob_38·33) 무회귀, 최대 54.4초. 비관적 고경합(4잡×4프로세스=16-활성)을 `-j 4`로 본 전수(`results/dev_p4c3_60s`)에서도 순위 시뮬이 **61→68**로 올랐고 **40/40 feasible**, prob_38·40·33은 무회귀다. 제출 게이트는 60초 40/40(최대 54.36초)·10초 40/40(최대 9.22초)로 시간 초과 0, floor 폴백 0이다. best-of가 같은 실행의 시드 0을 이긴 인스턴스는 22/40으로, 포트폴리오가 자기 시드 0보다 나빠질 수 없다는 구조적 보장이 로그로도 확인된다.

한계는 정직하게 적는다. 고경합 16-활성에서는 *깊게 수렴하는 작은 인스턴스*가 손해를 본다. prob_1은 단일 시드가 깊이 21,021까지 가는데, 경합으로 얕아진 시드 넷의 best는 25,331(+20.5%)에 그쳤다. 이 12개 소폭 회귀는 저경합(`-j 1`)에선 사라지므로, 손익은 **평가 서버의 동시성에 달렸다**. 솔버를 적게 띄우는 서버일수록 우리에게 유리하다. 그래도 어느 쪽이든 큰 인스턴스는 보호되고, 멀티프로세싱이 실패하면 옛 production으로 떨어지며, [시간 가드](../GLOSSARY.md)가 −1을 막는다. 다음은 경합을 더 줄이는 길이다. 시드별로 ALNS만 짧게 흩고 best 위에서 한 번 더 깊이 파는 2단 구성인데, 그 전에 이 포트폴리오가 노는 코어를 처음으로 쓰기 시작했다.

