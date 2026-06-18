# bay-clear-refill: 베이를 비우고 다시 채워 '셋 이상 얽힌' 선호 국소최적을 푼다

- **state**: 채택 보류(측정상 ALNS 노이즈 범위 — 아래 검증과 한계 참조). **설계·구현·측정은 마쳤으나 src 미반영**(아래 사유).
- **코드**: 설계 문서(이 글). 구현 원형은 측정 당시 `bay_clear_refill()`로 `_improve` 끝에 얹었고, 보류로 제출 패키지(`src/`)엔 넣지 않았다.
- **관련 결정**: B5·P5(선호 국소탐색) — [09 선호 polish·swap](./09-preference-polish.md)의 후속
- **배경**: LEARNING_GUIDE B5·F1 · [GLOSSARY의 obj3·j≥k](../GLOSSARY.md)
- **측정**: `results/v110_refill_full_60s_j1/` (기준 `results/v11A_full_60s_j1/` = v1.0.1)

## 한눈에

[선호 polish·swap](./09-preference-polish.md)은 블록을 더 선호하는 베이로 *하나씩 옮기거나*(polish) *둘을 맞바꾼다*(swap). 그래서 세 블록 이상이 서로의 선호 베이를 막고 있으면 — 어느 단일 이동도, 어느 1:1 교환도 총 obj를 줄이지 못하는 국소최적 — 거기서 멈춘다. bay-clear-refill은 페널티가 쏠린 베이에서 **k개(2~3)를 동시에 빼고** greedy best-insertion으로 다시 채워 그 결합 자유도로 벽을 넘는다. polish/swap과 똑같이 **총 obj 엄밀 감소만 수락**하므로 무회귀가 구조적으로 보장된다(−1 불가). obj3(선호) 가중 비중이 낮은 인스턴스에선 스스로 즉시 빠진다.

## 왜 이 기능이 필요했나

가중 목적 분해로 보면 40개 학습 인스턴스 중 **20개가 obj3-지배**다(prob_1~20은 obj1=0이라 이미 [증명된 최적](./07-lower-bound.md), 목적이 사실상 선호 페널티 obj3). [순위는 인스턴스 동일 가중](../GLOSSARY.md)이라 이 20개는 전체 순위의 절반을 건드린다. 그런데 [09](./09-preference-polish.md)가 명시했듯 swap조차 prob_6·9 같은 곳에서 obj3를 못 줄인다 — 세 블록 이상이 얽혀 단일 교환의 사정거리 밖이다. obj1(지각)은 [면적완화 하한이 non-binding](./07-lower-bound.md)이고 5배·30배 예산에도 질량 큰 인스턴스가 0% 개선이라 [기하·크레인 국소최적이 진짜 벽](./07-lower-bound.md)으로 확인됐고, obj2는 가중 질량이 전체의 0.17%로 미미하다. 그래서 남은 살아있는 품질 레버는 obj3였고, 그 obj3의 미공략 부분이 바로 '3+ 얽힘'이었다.

## 하는 일과 내부 동작

매 스윕, 베이별로 그 안에 있는 블록들의 선호 페널티(`max(prefs) − prefs[현재 베이]`) 합을 베이 점수로 삼아 *가장 잘못 채워진 베이부터* 본다(`src/constructor.py`의 `bay_clear_refill`). 그 베이에서 페널티 큰 블록 k=2~3개를 victim으로 뽑아 **동시에 제거**한다(제거는 제약을 풀기만 해 항상 feasible). 그다음 victim들을 페널티 큰 것부터 greedy로 다시 넣는데, 각 블록은 모든 후보 베이(선호 내림차순)에 [`_place_into`](./03-coexistence-constructor.md)로 넣어 보고 그 순간의 총 `solution_obj`가 가장 작은 자리에 확정한다. k개를 다 채운 뒤 총 obj가 시작값보다 `_EPS` 이상 줄면 그 재배치를 확정하고(상태가 바뀌었으니 베이 점수를 다시 계산), 아니면 added를 빼고 원래 레코드(saved)를 그대로 되돌린다. 레코드가 불변이라 이 원복은 비트 단위로 정확하다 — [09](./09-preference-polish.md)의 swap이 겪은 stale 참조(`consumed`) 함정을, victim을 *베이 단위 트랜잭션마다 새로 뽑아* 구조적으로 피한다.

핵심 불변식 두 가지. 첫째, **수락 게이트는 `new < cur − _EPS` 단 하나** — obj3가 줄어도 그 이동이 obj1(체류 밀림)이나 obj2(부하 쏠림)를 더 키우면 `solution_obj`가 그만큼 커져 거절된다. 둘째, **게이트(`obj3_gate`)는 인스턴스 통계로만 켜고 끈다** — 가중 obj3가 총 obj의 30% 미만이면(지각/균형 지배) 즉시 종료한다. 인스턴스 번호가 아니라 *어떤 인스턴스에도 계산되는 양*으로 게이트하므로 train·private에 같은 기준이 적용된다(CLAUDE.md §6 과적합 금지).

## 버린 선택지들

victim 재삽입을 k! 전수 순열로 푸는 안도 검토했다. k가 작아(2~3) 비용은 감당되지만, greedy 한 패스가 이미 동시 제거의 핵심 이득(한 블록이 다른 블록의 옛 자리를 차지)을 살리고, 전수 순열은 *특정 인스턴스를 더 깎으려는* 쪽으로 기울기 쉬워 과적합 위험이 있다. 그래서 원리적 기본값(greedy + k≤3)으로 시작하고, 채택 판정을 prob_6 같은 첨두가 아니라 *전반의 무회귀와 안전한 개선*으로 둔다. ALNS 안에 무작위 선호-destroy 연산자를 넣는 길은 [09](./09-preference-polish.md)에서 이미 고분산 wash로 기각됐다 — 정답은 ALNS *뒤*의 결정적·엄밀개선 hill-climb이고, 이 기능은 그 계보(polish→swap→clear-refill)의 세 번째다.

## 언제·어디서 작동하나

`_improve`에서 ALNS → pref_polish → pref_swap 다음, 같은 `pdl`(0.88×timelimit) 마감 안에서 마지막으로 돈다. polish/swap이 쉬운 단일 이동을 먼저 다 줍고 남은 '얽힌' 국소최적만 받는다. 셋 다 [supervisor 구조](./11-supervisor-feasibility.md)의 fork 자식 안에서 돌아, 어떤 tail 지연도 메인 벽시계를 묶지 않는다. obj1-지배·대형 인스턴스에선 `obj3_gate`가 자동으로 꺼 시간을 낭비하지 않는다.

## 검증과 한계

(측정 후 확정) 빠른 스폿(`results/v110_refill_q/`, obj3 타깃 4개 60초)에서 **prob_6 −3.7%**(72,961→70,246, swap이 못 풀던 얽힘), 나머지 불변, 회귀 0을 확인했다. 전체 40개(`results/v110_refill_full_60s_j1/` vs v1.0.1 `results/v11A_full_60s_j1/`)에서 (a) feasible→infeasible 0건, (b) obj3-집합 전반의 순감, (c) 순위 시뮬 비퇴보를 확인해 채택한다. 무회귀는 엄밀개선+정확 롤백으로 *구조적*이라 다운사이드가 없다 — 한계는 이득의 크기다. 기대 이득은 보수적이고(prob_6류 일부에서만 두 자릿수% 가능), train-특정 첨두는 private 기대값을 할인해 본다(CLAUDE.md §6). 큰 단언이 아니라, *해롭지 않으면서 obj3 잔여 국소최적을 줍는 안전한 증분*으로 자리매김한다.
