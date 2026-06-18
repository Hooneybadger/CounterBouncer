# 공존 구성기: 한 베이에 여러 블록을 동시에, 만들 때부터 feasible하게

> 처음 보는 용어([공존 패킹](../GLOSSARY.md), [빈-베이 윈도우](../GLOSSARY.md), [j≥k](../GLOSSARY.md), [BLF](../GLOSSARY.md), [EDD](../GLOSSARY.md), [feasibility-by-construction](../GLOSSARY.md))는 용어집에 한 줄씩 정의해 두었습니다.

- **state**: 구현 · 측정완료
- **코드**: `src/constructor.py` (`construct` 진입점, `_best_in_bay` 베이별 최선, `_blf_candidates` 후보 위치, `_fallback_place` 보장 배치). 연결은 `src/myalgorithm.py:algorithm`.
- **관련 결정**: [STRATEGY_PLAN](../STRATEGY_PLAN.md) B3·P3 · **배경**: [LEARNING_GUIDE](../LEARNING_GUIDE.md) B3·D1 · **엔진**: [features/02](./02-raster-engine.md)

## 한눈에

이 문서가 다루는 기능은 전략 계획의 세 번째 단계, P3다. 출발점은 [P1 안전망](./01-feasibility-first-wrapper.md)의 한계다.

P1은 베이를 *한 번에 한 블록*으로 직렬화한다. 한 블록이 나가야 다음이 들어온다. feasibility(규칙을 다 지킨 상태)는 자명하지만 블록들이 줄을 서서 기다리니 [지각](../GLOSSARY.md)이 폭발한다. 이 공존 구성기는 같은 베이에 여러 블록을 *동시에* 쌓아(공존 패킹), 블록을 들어올 수 있는 가장 이른 시각([release](../GLOSSARY.md)) 즈음에 일찍 넣는다. 목적값(obj)은 가중치가 `w1≫w2,w3`(실측 prob_2: w1=29091)이라 사실상 지각 항이 전부고, 그래서 이 한 가지 변화가 점수의 거의 전부를 좌우한다.

숫자로 본다. 베이스라인이 feasible했던 9개 인스턴스에서 obj가 **평균 68.9% 개선**됐고(9개 중 8개가 95~100% 개선), 직렬화된 P1 대비로는 자릿수가 바뀐다. 예컨대 prob_1의 obj1(지각)이 P1 15,133에서 **7**로, prob_12는 obj 55.7M(베이스라인)에서 **0.20M**으로 떨어진다. 그러면서 **40개 전부 feasible**(infeasible 0건), 최대 소요 16.6초로 [시간 가드](../GLOSSARY.md) 안에 끝난다.

| | P1 안전망(직렬) | 베이스라인(EDD+repair) | **공존 구성기** |
|---|---|---|---|
| prob_1 obj | 440.8M | 17.4M | **0.31M** |
| prob_12 obj | 643.6M | 55.7M | **0.20M** |
| 40개 feasible | 40/40 | 9/20 (서버 모사) | **40/40** |
| baseline-9 평균 개선 | 해당 없음 | 기준 | **+68.9%** |

## 왜 이 구성기가 필요했나

P1은 −1 회피만을 목표로 *증명 가능한 안전망*을 반환했다. 그 대가가 직렬화다. [빈-베이 윈도우](../GLOSSARY.md)는 베이가 통째로 빌 때만 블록을 넣으므로, 베이 하나에 블록이 줄지어 기다리고 지각이 쌓인다. 실측이 이를 그대로 보여준다. P1의 obj1(지각)이 인스턴스마다 수천~수만이고(prob_19 obj1=64,180), w1이 압도적이라 obj가 수억에 이른다. 베이스라인은 공존을 허용해 지각을 줄였지만(prob_1 obj1=597) 단방향 검사 + 사후 repair가 큰 인스턴스에서 무너져 20개 중 11개가 서버 기준 −1이었다([STRATEGY](../STRATEGY_PLAN.md) A2).

그래서 P3의 과제는 분명하다. **베이스라인의 공존 패킹은 가져오되, repair가 필요했던 실패 모드는 구조적으로 제거한다.** 그리고 그 검사를 [래스터 엔진](./02-raster-engine.md)의 비트 연산 위에 올려, 베이스라인이 Shapely로 못 돌린 큰 인스턴스까지 시간 안에 끝낸다.

## 하는 일과 내부 동작

구성기는 **완전한 feasible 해 하나**를 만들어 돌려준다(`construct`, `constructor.py:202`). 입력은 인스턴스와 시간 예산, 출력은 `operations` 딕트다. 품질(지각 최소화)을 노리되 feasibility를 *만드는 순간* 지킨다. 사후 검증도 repair도 없다.

전체 흐름은 블록 하나를 넣을 때마다 "어느 베이에, 언제, 어디에, feasible하게"를 차례로 정하는 파이프라인이다.

**블록 순서는 [EDD](../GLOSSARY.md).** 납기 빠른 블록부터 넣어 이른 자리를 선점한다(`constructor.py:236`). 각 블록 X에 대해, 모든 베이에서 "가장 빨리 넣을 수 있는 시각과 그때의 최선 위치"를 구하고(`_best_in_bay`, `constructor.py:113`), 베이들끼리 `_placement_cost`(baseline `_placement_score`와 동형: `w1·지각 + w2·부하 + w3·선호`)로 비교해 가장 싼 베이에 커밋한다.

**가장 빠른 entry를 먼저.** 지각은 `max(0, entry+proc−due)`라 entry에 단조 증가한다. 그래서 후보 entry 시각을 `{release} ∪ {겹칠 수 있는 exit들}`로 잡아 *오름차순*으로 보고, 어떤 시각이든 feasible한 위치가 하나라도 나오면 그 시각이 이 베이의 최적이다(`constructor.py:128`). 그 시각의 여러 방향 중 상단 모서리(top_y)가 가장 낮은 자리, 곧 가장 빽빽한 자리를 고른다.

**그 시각의 위치 후보는 [BLF](../GLOSSARY.md) 앵커다**(`_blf_candidates`, `constructor.py:78`). 베이 좌하단, 그리고 함께 놓인 블록들의 우·상단 모서리에 X를 붙이는 자리들이다. 바닥-왼쪽 우선으로 정렬해 첫 feasible을 취하면 그게 가장 빽빽한 자리가 된다.

**핵심은 양방향 크레인 검사다.** 블록 X를 위치 (px,py)·구간 [t,te)에 넣을 때, 그 베이에서 시간이 겹치는 committed 블록(이미 배치를 확정한 블록) C 전부에 대해 두 방향을 본다(`constructor.py:140`).

- *forward*: X가 들어오는 순간 베이에 있는 블록들(`present_entry`)이 X의 하강 경로를 막지 않아야 하고(`entry_feasible`), 나가는 순간의 블록들(`present_exit`)이 상승 경로를 막지 않아야 한다(`exit_feasible`). 둘 다 [래스터 엔진](./02-raster-engine.md)의 [상부 점유 맵](../GLOSSARY.md)과 AND 한 번이다.
- *reverse*: X가 베이에 있는 *동안* 들어오거나 나가는 C는, 새로 생긴 X 때문에 크레인 경로가 막히면 안 된다. X만으로 점유 정수를 세우고, 그 C들의 마스크를 질의한다(`constructor.py:166`).

이 둘을 합치면 stage 2/3/4가 전부 닫힌다. [j≥k](../GLOSSARY.md) 크레인 검사는 최종 안착 위치(j=k)의 같은-레이어 겹침까지 포함하므로, 시간이 겹치는 어떤 두 블록도 한쪽의 크레인 이벤트가 다른 쪽을 반드시 한 번은 본다. 그래서 stage 4(공간 충돌)는 따로 검사할 필요가 없다. 이미 놓인 블록을 절대 옮기지 않으니 이 불변식은 삽입마다 귀납적으로 유지된다.

**왜 fallback이 거의 필요 없나.** 후보 시각 집합에는 그 베이가 X의 체류구간 동안 *완전히 비는* 시각([빈-베이 윈도우])이 항상 들어 있다. 그 시각엔 공존 블록이 없어 X가 자명히 feasible하다. 즉 탐색은 늦어도 그 시각엔 자리를 찾으므로, **P1의 보장이 이 탐색의 최악 경우로 포함된다.** 시간 가드(예산 90%)를 넘긴 잔여 블록이나 극단적 기하만 `_fallback_place`(`constructor.py:289`)로 보장 배치한다.

## 버린 선택지들

가장 큰 갈림길은 **단방향 + 사후 repair**(베이스라인)였다. 베이스라인은 새 블록을 *이미 놓인* 블록에만 검사하고, [EDD](../GLOSSARY.md) 순서가 시간 순서와 달라 나중에 놓인 블록이 앞 블록의 크레인 경로를 소급해 막으면 repair로 고쳤다. 그 repair가 큰 인스턴스에서 수렴하지 못해 −1을 냈다. 우리는 reverse 검사로 "새 블록이 기존 블록을 막는" 경우까지 삽입 순간에 차단해, repair가 필요했던 원인 자체를 없앴다. 전체 문제를 한 번에 푸는 MIP는 비충돌 disjunctive 제약이 폭발하므로 처음부터 배제했다([STRATEGY](../STRATEGY_PLAN.md) B5).

위치 생성에서는 [래스터 엔진](./02-raster-engine.md)의 `feasible_positions` 전 위치 스캔(IFP 직사각형 전수) 대신 BLF 앵커를 택했다. 전수 스캔은 베이 한 칸까지 빽빽한 자리를 보지만 위치 수가 수천이라, 같은 시각의 첫 feasible만 필요한 우리에겐 과하다. 빽빽한 오목 틈의 회수는 측정으로 정당화될 때(삽입 순서 [features/04](./04-insertion-order-portfolio.md)·전수 스캔) 투자한다. 점유 표현은 P2의 결정을 그대로 계승해 numpy 배열이 아닌 [단일 Python 큰정수](./02-raster-engine.md)를 쓴다.

## 언제·어디서 작동하나

`algorithm()`은 feasibility-first anytime 골격을 따른다(`myalgorithm.py:algorithm`). 먼저 P1 `_guaranteed_solution`을 floor로 확보하고, 그다음 `construct`가 제안을 만들고, `utils.check_feasibility`가 그 제안을 **1회 중재**한다. 제안이 feasible하고 obj가 더 좋을 때만 incumbent로 채택하고, 아니면 floor를 반환한다. 그래서 구성기에 어떤 버그가 있어도 출력은 최소한 P1 안전망이고 −1은 어떤 경우에도 없다. [P4 ALNS](../STRATEGY_PLAN.md) 개선 루프는 이 incumbent를 *검증된 feasible* 해로만 교체하며 같은 자리에 들어온다.

## 검증과 한계

종료 기준은 둘이었다. 베이스라인이 feasible했던 9개에서 obj 평균 50% 이상 개선, 그리고 전 인스턴스 무회귀([STRATEGY](../STRATEGY_PLAN.md) P3). 40개 학습 인스턴스를 서버 모사(`--jobs 1 -t 60`)로 돌린 결과 **infeasible 0건**, baseline-9 **평균 +68.9%** 개선으로 두 기준을 넘겼다(`results/p3a_60s`). P1 기준런(`results/myalg_v1_40_60s`) 대비 **회귀 0**이다. 40개 모두 feasible을 유지하며 obj가 자릿수로 개선됐고, 순위 시뮬레이션 점수도 퇴보가 없다. 각 인스턴스 소요는 1.1~16.6초로, 남은 예산은 전부 P4 ALNS의 몫이다.

한계는 분명하다. 유일하게 베이스라인에 진 prob_2는 지각이 이미 0이고 차이가 전부 obj3(선호)에서 난다. obj2·obj3은 *할당*만의 함수라 패킹이 아니라 [외층 할당 재최적화](../STRATEGY_PLAN.md)(P5)의 영역이고, 여기서 다루지 않는다. BLF 앵커는 빽빽한 오목 자리 일부를 놓칠 수 있어, 삽입 순서([features/04](./04-insertion-order-portfolio.md))와 전 위치 스캔이 다음 개선 여지다. 그리고 현재는 한 번의 구성으로 멈추므로, 같은 예산에서 obj를 더 깎는 ALNS(P4)가 그 위에 선다.
