# ALNS: 놓은 블록을 뜯어 다시 채워 경합을 풀다

> 처음 보는 용어([ALNS](../GLOSSARY.md), [destroy/repair](../GLOSSARY.md), [SA 수락](../GLOSSARY.md), [incumbent](../GLOSSARY.md), [공존 패킹](../GLOSSARY.md))는 용어집에 정의해 두었습니다.

- **state**: 구현 · 측정완료
- **코드**: `src/alns.py` — `alns`(루프), `destroy_random`/`destroy_worst`/`destroy_window`, `_repair`, `_undo`. 상태/평가는 `src/constructor.py`의 `construct(return_state=True)`·`solution_obj`·`operations_from_committed`. 연결은 `src/myalgorithm.py:algorithm`.
- **관련 결정**: [STRATEGY_PLAN](../STRATEGY_PLAN.md) B3·P4 · **배경**: [LEARNING_GUIDE](../LEARNING_GUIDE.md) E2 · **위에 섬**: [features/05](./05-temporal-nesting.md)

## 한눈에

[구성기](./03-coexistence-constructor.md)는 블록을 한 번에 하나씩 *놓고 끝*이라 greedy 국소 최적에 갇힌다. [features/04](./04-insertion-order-portfolio.md)가 잰 헤드룸(경합 지각이 obj의 93.6%)의 마지막 손잡이는, 이미 놓은 블록을 *움직이는* 것이다. ALNS는 해의 일부를 [뜯어내고(destroy) 다시 채워(repair)](../GLOSSARY.md), [SA 수락](../GLOSSARY.md)으로 국소 최적을 탈출한다.

측정이 구성을 정해 줬다. 핵심 발견은 **scan(nesting)으로 깐 베이스 위에서 빠른 BLF repair로 ALNS를 돌리는 것**이 이긴다는 점이다. nesting은 이미 베이스에 박혀 있고, ALNS는 빠른 반복으로 나머지를 재배치만 해도 크게 깎인다. 효과가 크다. 60초에서 prob_1 obj가 P3c 84K에서 **25K(−70%)**, prob_9가 117K에서 **75K(−36%)**로 떨어진다. feasibility는 구성에서 그대로 보장되고(destroy는 빼기만, repair는 양방향 검사), incumbent는 절대 나빠지지 않는다.

## 왜 이게 필요했나

P3까지의 해는 전부 *한 방향 greedy 구성*이다. 블록을 EDD 순으로 한 번 훑어 놓으면 끝이라, 앞에서 내린 결정이 뒤를 옭아매도 되돌리지 못한다. [features/04](./04-insertion-order-portfolio.md)에서 무대기 지각 하한이 0인데 obj1이 큰 것을 보고 적었듯, 남은 지각은 전부 경합이고 그 회수에는 *이미 놓은 블록을 움직이는* 능력이 필요하다. 그게 ALNS다.

## 하는 일과 내부 동작

해를 `committed`(베이별 레코드 리스트) + `bay_loads`로 들고, `construct(return_state=True)`가 그 가변 상태를 그대로 넘겨준다(`constructor.py`). ALNS 한 반복은 다음이다.

**destroy** 는 세 연산자 중 하나로 블록 k개(전체의 약 2~7%)를 뺀다. `destroy_random`(다양성), `destroy_worst`(지각 큰 블록 우선, 재배치 이득이 클 후보를 상위 풀에서 무작위로), `destroy_window`(시간상 가까운 한 묶음으로 한 시간대의 경합을 통째로 다시 푼다)이다. **repair** 는 뺀 블록을 EDD 순으로 `_place_block`에 다시 넣는다. **수락** 은 `solution_obj`로 새 obj를 재고 [SA](../GLOSSARY.md)를 따른다. 더 좋으면 받고 나빠도 `exp(−Δ/T)` 확률로 받으며, T는 선형 냉각한다. **거절이면 `_undo`로 O(k) 되돌린다.** repair가 넣은 k개를 빼고 뺀 k개를 도로 넣는다.

두 가지가 속도를 만든다. 첫째, **매 반복 `check_feasibility`를 부르지 않는다.** destroy는 빼기만 해 feasibility를 못 깨고, repair는 P3a의 양방향 크레인 검사(`_place_block`)로 넣어 *만들 때부터* feasible이라, obj만 직접 세면 된다(`solution_obj`는 판정기의 obj 계산을 정확히 복제). 최종 incumbent만 `algorithm()`이 1회 중재한다. 둘째, **거절 복원이 O(k)** 라 전체 해를 복사하지 않는다. 그래서 작은 인스턴스에서 30초에 6,000회를 돈다.

repair에는 **BLF 후보**를 쓴다. scan보다 빠르고, nesting은 이미 scan 베이스에 박혀 있어 빠른 reshuffle이 더 멀리 간다.

## 버린 선택지들

선택은 전부 측정으로 갈렸다.

**BLF 베이스 + ALNS**는 scan 구성을 못 이긴다. BLF repair가 오버행 [nesting](../GLOSSARY.md)을 못 만들어, 30초를 돌려도 prob_1이 212K에 그친다(scan 구성 84K). 그래서 ALNS는 *scan 베이스 위에서* 돌려야 한다. **scan repair**는 BLF repair보다 오히려 *나쁘다.* 같은 20초에서 prob_1이 scan repair −12% 대 BLF repair **−50%**다. scan repair가 정확하지만 ~2배 느려 반복이 절반이고, nesting은 어차피 베이스에 있어 빠른 BLF reshuffle이 이긴다. **큰 인스턴스**에서는 repair가 가득 찬 베이를 스캔해 느려, prob_38이 30초에 31회뿐이라 효과가 거의 없다. 다만 예산 배분이 이를 자연히 흡수한다. scan 구성이 빠른(작은·중간) 인스턴스가 ALNS 시간을 많이 받고, 거기서 ALNS가 가장 크게 깎기 때문이다. **adaptive 연산자 가중치**와 **4코어 포트폴리오**는 [STRATEGY](../STRATEGY_PLAN.md) P4에 적힌 다음 단계(P4b·P4c)로 미뤘다. 균일 가중·단일 코어로 먼저 가치를 확인했다.

## 언제·어디서 작동하나

`algorithm()`은 구성기 포트폴리오로 best incumbent 상태를 잡은 뒤, 남는 예산(`0.83×timelimit`까지)을 ALNS에 준다(`myalgorithm.py`). 짧은 제한시간(10초)에선 구성이 예산을 거의 다 써 ALNS는 거의 못 돌지만, scan이 빠른 인스턴스는 10초에서도 ALNS가 돈다(prob_1 10초 46K). 60초에선 작은·중간 인스턴스가 ALNS 시간을 충분히 받는다. ALNS는 best snapshot을 추적해 초기 incumbent보다 *절대* 나빠지지 않으므로, 회귀가 구조적으로 불가능하다. 시드는 고정해(`random.Random`) feasibility는 결정적이고, obj만 벽시계에 따라 미세하게 흔들린다.

## 검증과 한계

종료 기준은 단조 수렴 곡선과 P3 대비 추가 20% 이상 개선이었다([STRATEGY](../STRATEGY_PLAN.md) P4). 둘 다 충족했다. 수렴 곡선은 단조 비증가다. prob_10에서 best가 200,567에서 113,937로 48번의 개선을 거쳐 매끄럽게 내려가고(전 구간 비증가 확인), prob_1은 84,079에서 25,331로 떨어진다. 서버 모사(`--jobs 1 -t 60`, `results/p4a_60s`)에서 P3c(`results/p3c_60s`) 대비 **회귀 0, 31개 개선·9개 동률**(동률은 ALNS 예산이 적은 큰 인스턴스), 순위 시뮬 **80:50**으로 전 인스턴스 우세, **40/40 feasible**, 최대 소요 50.6초다. 추가 20% 이상 개선은 ALNS 예산이 남는 12개 인스턴스에서 달성됐다(prob_1 −70%, prob_10 −52%, prob_9 −36%, prob_2 −36%, prob_17 −34%, prob_15 −32%, prob_12 −31%).

한계는 분명하다. ALNS의 이득은 *예산이 남는* 작은·중간 인스턴스에 몰린다. 큰 인스턴스는 repair가 비싸 반복이 적어 거의 정지한다. 가속(타깃 repair, 증분 occ 캐시)이 다음 과제다. 연산자 가중치가 균일하고(adaptive 미적용), 단일 코어다(서버 4코어를 시드·온도가 다른 포트폴리오로 채우는 P4c가 남았다). 그리고 ALNS는 *구성 품질*을 못 넘는 한계가 있어, scan repair로 nesting을 더 만들 여지도 측정 대상으로 남는다.
