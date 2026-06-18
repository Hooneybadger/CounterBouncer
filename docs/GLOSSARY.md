# 용어집 — 이 프로젝트의 공용 어휘

이 문서는 `docs/` 전체에서 반복되는 용어를 한 곳에 정의합니다. 다른 문서는 용어를 다시 설명하지 않고 여기로 링크합니다(예: "[빈-베이 윈도우](../GLOSSARY.md#빈-베이-윈도우)"). 각 항목은 한두 문장의 직관적 정의이고, 더 깊은 설명이 필요하면 [LEARNING_GUIDE](./LEARNING_GUIDE.md)의 해당 Part를 가리킵니다.

읽는 순서를 권하지는 않습니다 — 문서를 읽다 모르는 단어가 나오면 그때 여기서 찾으세요.

---

## 1. 문제의 물리 모델

이 대회는 항만의 블록 적치장을 본뜬 2차원 + 시간 배치 문제입니다. (배경: LEARNING_GUIDE Part A)

- **베이(bay)** — 블록을 놓는 직사각형 격자 공간. `width × height`(정수 셀). 인스턴스마다 2~5개.
- **블록(block)** — 일정 기간 베이를 점유하는 물체. 들어올 시각·나갈 시각·모양·납기를 가진다. 인스턴스마다 100~300개.
- **레이어(layer) / 층** — 블록은 여러 층으로 쌓인 3차원 물체다. 각 층은 평면 위 하나의 **다각형(footprint)**. layer 0이 맨 아래, 위로 갈수록 인덱스가 커진다. 학습 인스턴스의 80~100%가 다층 블록이다.
- **방향(orientation)** — 같은 블록의 회전 후보(블록당 2~8개). 배치할 때 그중 하나(`orient_idx`)를 고른다.
- **footprint / 다각형 정점** — 한 층의 평면 윤곽. 정점 좌표는 **실수**(격자에 안 맞음). 블록을 놓는 *위치*만 정수다 — 이 구분이 중요하다(INSTANCE_ANALYSIS 4.3).
- **ENTRY / EXIT** — 블록이 베이에 들어오는 동작 / 나가는 동작. 해(solution)는 모든 블록의 ENTRY·EXIT 시각과 위치의 목록이다.
- **크레인(crane) / 크레인 경로** — 블록은 수직(위아래)으로만 움직인다. 들어올 때 위에서 똑바로 내려오고, 나갈 때 똑바로 올라간다. 이때 지나는 위 공간이 "크레인 경로"이고, 거기에 다른 블록이 있으면 막힌다.
- **sweep collision(쓸림 충돌)** — 블록이 최종 위치로 내려오는(또는 올라가는) *도중에* 위쪽 블록과 부딪히는 것. 최종 위치에서의 겹침과 구별된다.
- **j ≥ k 규칙** — 본 문제의 핵심 비대칭. 내려오는 새 블록의 layer `k`는 기존 블록의 layer `j`와 `j ≥ k`일 때만 부딪힌다(`j=k`는 최종 위치 충돌, `j>k`는 쓸림 충돌, `j<k`는 절대 충돌 없음). 그래서 키 큰 블록 아래 빈 공간을 키 작은 블록이 *공간상*으론 쓸 수 있지만, 크레인으로 넣고 빼는 건 또 다른 문제가 된다. (배경: LEARNING_GUIDE B1)

## 2. 블록의 시간 속성

- **release_time(출시 시각)** — 이 시각 이전에는 블록이 들어올 수 없다.
- **due_date(납기)** — 이 시각 이후에 나가면 하루당 지각 페널티가 붙는다.
- **processing_time(가공/체류 기간)** — 블록이 베이에 머물러야 하는 최소 기간(`exit − entry ≥ proc`).
- **slack(여유)** — `due_date − release_time − processing_time`. 0이면 출시 즉시 들어가 납기에 딱 맞춰 빼야 지각이 없는 *구속 블록*. 학습셋엔 0~14가 섞여 있다(INSTANCE_ANALYSIS 4.1).
- **workload(부하)** — 목적함수 obj2(베이 부하 균형)에만 쓰이는 블록의 무게값.
- **bay_preferences(선호)** — 베이별 선호 점수 목록. 가장 높은 점수의 베이에 놓으면 obj3 페널티가 0.

## 3. 목적함수 — 낮을수록 좋다

`objective = w1·obj1 + w2·obj2 + w3·obj3`. 가중치 `w1, w2, w3`는 인스턴스마다 다르다. (배경: LEARNING_GUIDE A1·A3)

- **obj1 = 지각(tardiness)** — Σ max(0, exit − due). 위치·스케줄에 의존하는 유일한 항. 대개 w1이 압도적이라 가장 중요하다.
- **obj2 = 부하 불균형** — 베이 간 정규화된 부하 차이. *할당*(어느 베이에 보냈는가)만의 함수.
- **obj3 = 선호 손실** — Σ(최고 선호점수 − 놓인 베이의 선호점수). 역시 *할당*만의 함수.
- **2층 분해** — obj1만 패킹·스케줄에 의존하고 obj2·obj3은 할당에만 의존한다는 사실. 그래서 "패킹·스케줄(내층)"과 "할당 재최적화(외층)"로 나눠 공략한다. (배경: STRATEGY B3)

## 4. 검증 — `check_feasibility`의 5단계

평가 서버가 해를 채점하는 함수(`utils.py`). 한 단계라도 위반하면 즉시 멈추고 그 단계 번호를 돌려준다. 우리 해는 결국 이 다섯 단계를 모두 통과해야 점수를 받는다. (배경: LEARNING_GUIDE B2)

- **stage 1 — 형식·시간 유효성**: 모든 블록이 ENTRY·EXIT 정확히 한 번, 인덱스 범위, `entry ≥ release`, `exit − entry ≥ proc` 등.
- **stage 2 — 크레인 진입**: ENTRY 시점에 크레인이 막히지 않는지(+베이 경계 안에 드는지).
- **stage 3 — 크레인 반출**: EXIT 시점에 막히지 않고 빠져나가는지.
- **stage 4 — 공간 충돌**: 시간이 겹치는 두 블록이 *같은 층*에서 평면상 겹치는지.
- **stage 5 — 시간순 재생**: 모든 동작을 시각 순으로 재생하며 매 시점 베이 상태가 일관적인지. 같은 시각엔 EXIT가 ENTRY보다 먼저 와야 하고, 동시 진입의 순서까지 본다.

## 5. 채점과 의사결정

- **feasible / infeasible** — 5단계를 모두 통과 / 어느 단계라도 위반.
- **−1 점** — infeasible·시간 초과·크래시는 인스턴스당 −1점. 이걸 피하는 게 다른 모든 점수의 전제다.
- **R − nb 점** — feasible하면 `평가 팀 수 − (나보다 strictly 좋은 팀 수)`점. 동점은 같은 점수.
- **rank 시뮬레이션** — 여러 버전을 위 채점식으로 가상 대결시켜 순위 점수를 매기는 `batch_runner compare`의 출력. 우리의 의사결정 지표(평균 obj가 아니라 이 점수로 채택을 정한다, STRATEGY B6).
- **무회귀(no-regression)** — 어떤 인스턴스도 feasible→infeasible로 퇴보하지 않는 것. 채택의 절대 조건. obj만 나빠지는 건(feasible→feasible) 별개로 다룬다.

## 6. 알고리즘 개념

- **feasibility-first** — 무슨 일이 있어도 제한시간 안에 feasible한 해를 반환한다는 제1원칙. −1 회피가 평균 점수보다 먼저다.
- **incumbent(현행 최선 해)** — 지금까지 찾은 가장 좋은 feasible 해. 개선 루프는 더 나은 feasible 해를 찾을 때만 이걸 교체한다.
- **anytime(언제든 멈춰도 되는)** — 언제 중단당해도 그 순간의 incumbent를 즉시 내놓을 수 있는 알고리즘 구조.
- **시간 가드(time guard)** — 벽시계가 `timelimit × 0.93`에 닿으면 무조건 incumbent를 반환하는 자기 검열. 마지막 검증 비용까지 예산에 넣는다.
- **supervisor 구조(메인=감독자)** — 메인 프로세스는 빠르고 시간이 묶일 수 없는 일(floor·래스터 엔진)만 직접 하고, 구성·ALNS·선호 개선·최종 검증처럼 *중단 불가능하거나 짧은 제한시간에 overrun하는* 무거운 일은 전부 종료 가능한 fork 자식이 한다. 메인은 `return_cap`까지 큐에서 결과를 거두기만 하다 floor-or-best를 반환하므로, 자식이 느린 Shapely 호출에 묶이거나 OOM으로 죽어도 메인 벽시계는 자식과 무관해 −1이 구조적으로 불가능하다. (v1.0.1, → [features/11](./features/11-supervisor-feasibility.md))
- **floor(보장 안전망)** — 모든 블록을 빈-베이 윈도우로 직렬 배치한, 검증 없이도 feasible이 보장되는 최후의 해. 메인이 항상 손에 쥐고 있다가 자식이 제때 더 나은 해를 못 주면 반환한다. 품질은 낮아도(직렬화→지각 큼) −1을 막는 절대 하한. 블록수에 거의 선형이고 deadline fast-finish로 어떤 스케일에서도 시간 안에 완성된다. (→ [features/01](./features/01-feasibility-first-wrapper.md)·[features/13](./features/13-floor-scale-hardening.md))
- **feasibility-by-construction(구성에 의한 보장)** — 해를 만든 뒤 검사해서 고치는 게 아니라, *놓는 순간* 규칙을 지켜 처음부터 feasible만 만드는 방식. 사후 검증·repair가 필요 없다.
- **relax-and-repair** — 어려운 제약(다각형 비중첩·크레인 j≥k)을 *완화*해 풀기 쉬운 문제(직사각형 bbox + 스케줄)를 솔버(CP-SAT)로 전역 최적한 뒤, 그 해를 진짜 제약으로 *repair*(래스터 nesting 배치)하는 분해. bbox≥다각형이라 bbox-해는 공간상 진짜로도 feasible(보수적 완화)이고, 크레인·다각형은 솔버서 빼 [B5](./STRATEGY_PLAN.md)를 지킨다. EDD-greedy가 못 깨는 obj1 전역 스케줄 국소최적을 깬다. 혼잡(utilization 높은) 인스턴스에만 켠다. (P5·F1, → [features/14](./features/14-relax-repair.md))
- **utilization(혼잡도)** — Σ(블록 bbox면적 × 체류) / (Σ베이면적 × horizon). 베이가 시간상 얼마나 빽빽한지의 물리 측정. 높으면 경합으로 지각(obj1)이 forced된다. obj1-지배(≥0.42)와 obj3-지배(≤0.42)를 가르는 *인스턴스 통계*라, relax-repair를 켤지를 인스턴스 번호가 아니라 이 값으로 게이트한다(과적합 금지). (→ [features/14](./features/14-relax-repair.md))
- **빈-베이 윈도우(empty-bay window)** — 그 구간 동안 베이가 *완전히 비어 있는* 시간 창. 거기에 블록을 넣으면 부딪힐 다른 블록이 없어 크레인 진입·반출·충돌(stage 2/3/4)이 자명히 통과한다. P1 안전망의 핵심. (→ [features/01](./features/01-feasibility-first-wrapper.md))
- **EDD(Earliest Due Date)** — 납기 빠른 블록부터 처리하는 정렬 규칙. 단일 기계 최대 지각 최소화에 최적인 고전 휴리스틱. 동률은 처리시간 짧은 순(SPT)으로 가른다. (배경: LEARNING_GUIDE B3)
- **repair(사후 수리)** — 일단 배치한 뒤 위반을 찾아 고치는 방식. 베이스라인이 썼고, 큰 인스턴스에서 수렴 못 해 실패했다(우리가 피하는 모드).
- **LNS / ALNS** — Large Neighborhood Search / Adaptive 버전. 해의 일부를 부수고(destroy) 다시 채우길(repair) 반복하는 개선 메타휴리스틱. (P4, 배경: LEARNING_GUIDE E2, → [features/06](./features/06-alns.md))
- **destroy/repair(ALNS의)** — 완성된 해에서 블록 일부를 *빼고*(destroy: 무작위·지각 큰 것·시간 묶음) 다시 *넣는*(repair: 구성기로 재삽입) ALNS의 한 반복. 베이스라인의 repair(사후 수리)와 이름은 같지만 다르다 — 그건 위반을 고치는 것이고, 이건 feasible 해를 더 좋게 흔드는 것이다. (P4, → [features/06](./features/06-alns.md))
- **SA 수락(Simulated Annealing acceptance)** — 더 좋은 해는 받고, 나쁜 해도 `exp(−Δ/T)` 확률로 받아 국소 최적을 탈출하는 규칙. 온도 T를 점차 낮춰(냉각) 탐색에서 수렴으로 옮겨간다. (P4, → [features/06](./features/06-alns.md))
- **선호 재배치·교환 polish(preference relocation/swap hill-climb)** — ALNS 뒤에 도는 *결정적* 국소탐색. 선호 페널티가 있는 블록을 더 선호하는 빈 베이로 *옮기거나*(`pref_polish`), 그 베이가 꽉 찼으면 거기 있던 블록과 *맞바꾼다*(`pref_swap`). 둘 다 총 목적이 *엄밀히* 줄 때만 확정한다. SA와 달리 나쁜 이동을 절대 안 받으므로(엄밀 개선 수락) 입력 incumbent를 나빠지게 할 수 없어 무회귀가 구조적으로 보장된다. obj1=0 인스턴스에서 ALNS의 지각 편향 destroy가 놓친 obj3를 줍는다. (P4b·#12, → [features/09](./features/09-preference-polish.md))
- **regret-k 삽입** — "지금 안 넣으면 나중에 얼마나 손해인가(후회)"가 큰 블록부터 삽입하는 구성 휴리스틱. 본 문제에서는 area 완화 추정으로 값싸게 구현해 측정했으나 EDD에 전패해 채택하지 않았다(area 추정이 크레인 기하를 무시해 과낙관적). (P3b, → [features/04](./features/04-insertion-order-portfolio.md))
- **삽입 순서 포트폴리오(best-of-orders)** — 삽입 순서를 하나로 못 박지 않고 여러 순서(edd·edd_area)를 모두 구성해 더 좋은 feasible 해를 취하는 방식. best-of라 어떤 순서도 floor보다 나빠질 수 없어 회귀가 불가능하다. (P3b, → [features/04](./features/04-insertion-order-portfolio.md))
- **공존 패킹(coexistence packing)** — 한 베이에 여러 블록을 *같은 시간 구간에* 함께 놓아 공간을 나눠 쓰는 것. 빈-베이 윈도우의 직렬화(한 번에 한 블록)와 대비된다 — 공존을 허용해야 블록을 release 즈음에 일찍 넣어 지각을 줄인다. (P3, → [features/03](./features/03-coexistence-constructor.md))
- **BLF(bottom-left fill)** — 새 블록을 베이의 바닥-왼쪽 우선으로, 이미 놓인 블록의 우/상단 모서리에 붙여 후보 위치를 만드는 패킹 휴리스틱. 후보를 (x,y) 오름차순으로 보면 첫 feasible 자리가 가장 빽빽하다. (P3, 배경: LEARNING_GUIDE D1, → [features/03](./features/03-coexistence-constructor.md))
- **양방향 크레인 검사(both-direction check)** — 블록을 넣을 때 (1)새 블록의 크레인 경로가 기존 블록에 막히는지(forward)뿐 아니라 (2)새 블록이 기존 블록의 크레인 경로를 소급해 막는지(reverse)까지 보는 것. baseline이 forward만 봐 생기던 소급 막힘(repair 실패)을 reverse가 제거한다. (P3, → [features/03](./features/03-coexistence-constructor.md))
- **래스터 엔진(raster engine)** — 좌표가 정수라는 점을 이용해 베이를 비트맵으로 만들어 충돌 판정을 비트 연산으로 빠르게 하는 기하 엔진. (P2, 배경: LEARNING_GUIDE C2, → [features/02](./features/02-raster-engine.md))
- **보수적 래스터화(conservative rasterization)** — 다각형이 셀과 *양(+)의 면적으로* 겹칠 때만 그 셀을 1로 칠하는 규칙. 그래서 "래스터가 안 겹치면 진짜 안 겹친다"가 보장되고(판정은 안전한 방향으로만 틀린다), 모서리 접촉(면적 0)은 칠하지 않아 밀착 패킹이 보존된다. (→ [features/02](./features/02-raster-engine.md))
- **상부 점유 맵(upper map)** — 레이어별 점유의 suffix-OR. `upper[k] = OR_{j≥k} occ[j]`. j≥k 크레인 검사를 새 블록 layer k 마스크와의 AND 한 번으로 끝내는 자료구조. (→ [features/02](./features/02-raster-engine.md))
- **보수적 손실(conservative loss)** — 래스터가 보수적이라 진짜로는 feasible한 *셀 경계에 걸친 빽빽한 자리*를 거절하는 비율. 측정치가 5%를 넘으면 NFP·국소 정밀화로 회수할지 검토한다(그 전엔 투자 안 함). (→ [features/02](./features/02-raster-engine.md))
- **NFP / IFP** — No-Fit Polygon / Inner-Fit Polygon. 두 다각형이 겹치지 않고 닿는 자리 / 한 다각형이 베이 안에 들어갈 수 있는 영역을 해석적으로 계산하는 도구. (배경: LEARNING_GUIDE C3·C4)
- **temporal nesting(시간 포함 중첩)** — j≥k 비대칭을 이용해, 키 큰 블록의 오버행 아래 공간을 "먼저 들어와 나중에 나가는" 블록만 쓰게 하는 우리의 차별화 설계. 구성기는 위치 후보를 코너(BLF) 대신 전 위치 스캔으로 넓혀 이 자리를 후보에 넣는다(P3c). (배경: STRATEGY B4, LEARNING_GUIDE D3, → [features/05](./features/05-temporal-nesting.md))
- **전 위치 스캔(scan 후보)** — 위치 후보를 코너 앵커가 아니라 IFP 직사각형 안의 entry-feasible한 모든 (px,py)로 생성하는 방식(`feasible_positions`). 오버행 아래 nesting 자리를 포함하나 BLF보다 ~2배 느리다. (P3c, → [features/05](./features/05-temporal-nesting.md))

## 7. 하한과 천장

- **천장(ceiling) / 최적성 격차(optimality gap)** — 우리 해가 진짜 최적에서 얼마나 떨어져 있는가. 아래에서는 *하한*으로(이보다 좋을 수 없다), 위에서는 더 긴 탐색이 찾은 *best*로(적어도 여기까진 줄어든다) 좁힌다. 둘 다 자기 과거 버전이 아니라 *절대 기준*이라 "우리가 충분히 좋은가"에 답한다. (P5a, → [features/07](./features/07-lower-bound.md))
- **무대기 하한(no-wait lower bound)** — 경합을 통째로 무시하고 모든 블록이 release 즉시 들어간다고 본 지각 하한 Σ max(0, release+proc−due). 가장 약한 하한이고, 학습 40개에서 전부 0이다(즉 단독으로는 누구도 지각하지 않는다). (P5a, → [features/07](./features/07-lower-bound.md))
- **면적완화 cumulative 하한(area-relaxation lower bound)** — 2D 패킹·크레인을 "어느 시각에도 존재 블록의 바닥(layer 0) 면적 합이 베이 면적을 못 넘는다"는 1차원 누적자원(cumulative) 제약으로 완화해 CP-SAT(OR-Tools)로 최소 지각을 푼 obj1 하한. 진짜 배치의 *필요조건*이라 유효한 하한이지만, 측정 결과 40개 전부 ≈0으로 **non-binding**이다 — 지각이 면적이 아니라 기하·크레인에서 온다는 진단이다. (P5a, → [features/07](./features/07-lower-bound.md))
- **유효한 완화(valid relaxation)** — 진짜 문제의 제약을 *느슨하게만* 바꾼 모델. 완화의 최적값은 항상 진짜 최적값 이하라, 완화를 풀면 유효한 하한이 나온다. 핵심 검증: 진짜 해가 obj1=0을 달성한 인스턴스에서 완화 하한은 반드시 0이어야 한다(아니면 demand를 과대계상한 버그). (P5a, → [features/07](./features/07-lower-bound.md))

## 8. 성능·검증 기법

- **차등검증(differential test)** — 코드를 *동작 보존* 방향으로 최적화했을 때, 옛 코드와 새 코드의 출력이 비트 단위로 같음을 전 인스턴스에서 확인하는 회귀 방어. 출력이 동일하면 feasibility가 정의상 보존되므로, 속도 최적화에 −1 위험이 없다. (#3, → [features/08](./features/08-repair-acceleration.md))
- **벽시계 결합(wall-clock coupling)** — 알고리즘의 *결과*가 벽시계 시간에 묶여 있는 성질. 구성 포트폴리오의 시간 게이트나 SA 온도가 경과 시간에 의존하면, 같은 코드라도 머신 속도·부하에 따라 다른 해를 낸다(예: prob_38이 scan 구성을 제때 끝내면 obj 70M, 못 끝내면 76M). 서버 속도에 점수가 흔들리는 안정성 리스크라, 핫패스를 빠르게 해 게이트가 여유 있게 통과되도록 만든다. (#3, → [features/08](./features/08-repair-acceleration.md))

## 9. 병렬 실행

- **시드 포트폴리오(best-of-seeds)** — 같은 인스턴스를 시드만 다르게 여러 번 풀어 best feasible을 취하는 방식. ALNS가 시드에 민감해 분산이 크므로(prob_16은 시드 넷의 obj가 37.7% 벌어짐), 노는 코어에 시드를 흩뿌려 운 나쁜 추첨을 거른다. best-of는 시드 0(옛 단일 실행)을 포함하므로 그보다 나빠질 수 없다. (P4c, → [features/10](./features/10-seed-portfolio.md))
- **fork / copy-on-write(COW)** — 프로세스를 복제(fork)할 때 메모리를 즉시 베끼지 않고 페이지를 공유하다가, 어느 한쪽이 *쓰는* 순간에만 그 페이지를 복사하는 기법. 워커가 메인이 만든 incumbent를 직렬화 없이 상속받되, ALNS가 그 상태를 변형하면 워커별로 갈라져 서로 격리된다. fork `Process`는 함수·인자를 피클하지 않아, 평가 서버가 모듈을 importlib로 커스텀 로드해 생기는 PicklingError도 피한다. (P4c, → [features/10](./features/10-seed-portfolio.md))
- **taskset / 코어 핀(affinity)** — 프로세스를 특정 CPU 코어에만 묶는 것. 평가 서버는 솔버를 4코어에 핀하고, `batch_runner`도 `taskset`으로 이를 모사한다. 자식 프로세스는 이 핀을 상속하므로, 포트폴리오 워커도 같은 4코어 안에서 돈다. 워커 수를 `os.sched_getaffinity`로 잡으면 이 핀된 코어 수에 정확히 맞는다. (→ [features/10](./features/10-seed-portfolio.md))
