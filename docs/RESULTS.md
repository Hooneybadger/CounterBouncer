# 결과 종합 — 측정으로 본 전체 개선 호

> 이 문서는 흩어진 측정을 한 곳에 모은 결선 보고서의 정량적 척추다. 각 단계의 *왜·어떻게*는 [features/](./features/)에, 결정의 맥락은 [STRATEGY_PLAN](./STRATEGY_PLAN.md)에, 용어는 [GLOSSARY](./GLOSSARY.md)에 있다. 숫자는 모두 `results/<run>/`에서 인용했고(gitignore라 커밋하지 않는다), 의사결정 지표는 평균이 아니라 [순위 시뮬레이션](./GLOSSARY.md) 점수다.

## 한눈에

우리 접근은 두 단계로 나뉜다. 먼저 **−1을 0으로** 돌려놓아 무슨 일이 있어도 feasible을 보장하고, 그 위에서 **품질을 깊이 회수**한다. 대회 베이스라인은 60초에서 40개 중 15개만 feasible해 25개가 −1점을 받지만, 우리 해는 10·60·300·1800초 전부에서 40/40 feasible이다. 그 바닥 위에서 품질이 합계 목적 기준 한 자릿수 백만대까지 내려갔고, 그 도약의 대부분은 [temporal nesting](./features/05-temporal-nesting.md)에서 나왔다. 후반의 [선호 polish·swap](./features/09-preference-polish.md)과 [4코어 포트폴리오](./features/10-seed-portfolio.md)는 합계로는 작아 보이지만(합을 큰 인스턴스가 지배한다) 지각이 0인 절반의 인스턴스에서 순위를 가르는 마지막 한 자리를 회수한다.

## 1. feasibility-first — −1을 0으로

채점은 인스턴스별 `R − nb`점이고 infeasible·시간 초과·크래시는 −1점이다. 그래서 첫 싸움은 품질이 아니라 *생존*이었다.

| 해 | 60초 feasible | 비고 |
|---|---|---|
| 대회 베이스라인(`baseline_40_60s`) | **15 / 40** | 25개가 −1(크래시·시간 초과). 사후 repair가 큰 인스턴스에서 수렴 못 함 |
| P1 증명 가능 안전망(`myalg_v1_40_60s`) | **40 / 40** | 빈-베이 윈도우 직렬 배치. 품질은 낮아도 −1이 구조적으로 없다 |

[feasibility-first 래퍼](./features/01-feasibility-first-wrapper.md)가 이 40/40을 모든 후속 단계의 바닥으로 깔았다. 이후 어떤 개선도 이 바닥 아래로 내려가지 않는다.

## 2. 구조적 품질 도약 — 합계 목적 (60초 전수, 같은 조건)

P1 안전망의 직렬 배치는 feasible하지만 지각이 폭발한다(합계 254억). 거기서 *공간을 나눠 쓰고 빽빽이 쌓는* 구조가 품질의 자릿수를 바꿨다.

| 단계 | 합계 목적 | 직전 대비 | 기능 |
|---|---|---|---|
| P1 안전망 | 25,488,553,408 | — | [01](./features/01-feasibility-first-wrapper.md) |
| 공존 구성기 | 282,703,670 | **−98.9%** | [03](./features/03-coexistence-constructor.md) 양방향 크레인 검사 |
| 삽입 순서 포트폴리오 | 269,789,098 | −4.6% | [04](./features/04-insertion-order-portfolio.md) best-of-orders |
| **temporal nesting** | **227,559,134** | **−15.7%** | [05](./features/05-temporal-nesting.md) 오버행 아래 패킹 |
| ALNS | 225,651,401 | −0.8% | [06](./features/06-alns.md) destroy/repair+SA |
| repair 가속 | 225,293,532 | (안정화) | [08](./features/08-repair-acceleration.md) 핫패스 인라인 |

가장 큰 단일 도약은 [nesting](./features/05-temporal-nesting.md)에서 나온다. j≥k 크레인 비대칭을 역이용해 키 큰 블록의 오버행 *아래* 빈 공간에 "먼저 들어와 나중에 나가는" 블록을 끼우는 방식이다. 같은 EDD에서 후보만 BLF→scan으로 바꾸는 nesting on/off ablation(prob_1이 306K→84K)이 보고서의 중심 Figure다. ALNS부터는 합계가 거의 안 움직인다. 합을 큰 obj1-heavy 인스턴스가 지배하기 때문인데(prob_38 한 개가 70M), 그래서 후반 기능의 진짜 가치는 합이 아니라 순위에 있다(아래 4절).

## 3. 정밀 회수 — obj3·분산 (순위 시뮬 ablation)

지각이 0인 18개 인스턴스에선 합계가 거의 안 변해도 [선호 손실 obj3](./GLOSSARY.md)와 부하 균형이 순위를 가른다. 여기 기능들은 같은 조건 A/B의 [순위 시뮬](./GLOSSARY.md)로 측정했다(R=2, per-instance `R−nb`).

| 기능 | A/B (기준 → 후보) | 순위 시뮬 | 헤드라인 |
|---|---|---|---|
| repair 가속 | `src_fresh` → `src_dev_combined` | 54 → 78 | prob_38 안정적 70M 채택([벽시계 결합](./GLOSSARY.md) fix) |
| 선호 재배치 polish | `base_pref` → `dev_polish` | 65 → 77 | 18개 obj1=0 집합 obj3 −6.1% |
| 선호 교환 swap | `dev_polish` → `dev_swap2` | 67 → 78 | 정체 인스턴스 교환으로 뚫음(prob_7 −15%) |
| 4코어 포트폴리오(저경합, 전수) | `dev_swap2` → `final_j1` | **53 → 79** (27승 1패) | prob_16 −27%·prob_6 −22%(시드 분산 활용) |
| 4코어 포트폴리오(고경합) | `dev_swap2` → `dev_p4c3` | 61 → 68 | 대형 보호, 작은 인스턴스만 경합 손해 |

[polish·swap](./features/09-preference-polish.md)은 ALNS 뒤에서 *엄밀 개선만 수락하는* 결정적 국소탐색이라 [무회귀](./GLOSSARY.md)가 구조적으로 보장된다. [포트폴리오](./features/10-seed-portfolio.md)는 노는 코어 셋에 시드를 흩뿌려 ALNS의 큰 분산(prob_16 spread 37.7%)을 활용한다. best-of가 시드 0(옛 단일 실행)을 포함하니 저경합 서버에선 손해가 없다.

## 4. 천장 — 우리가 최적에 얼마나 가까운가

자기 과거 버전이 아니라 절대 기준으로도 쟀다([07](./features/07-lower-bound.md)). obj1(지각)의 [면적완화 cumulative 하한](./GLOSSARY.md)을 CP-SAT로 풀었더니 **40개 전부 ≈0(non-binding)**, 그중 **18/40은 우리 obj1이 이미 0이라 증명된 최적**이다. 지배 목적을 절반 가까이에서 최적으로 풀었다는 뜻이다. 남은 지각은 자원이 아니라 [2D 기하·크레인 j≥k](./GLOSSARY.md)에서 오고, 그래서 [nesting](./features/05-temporal-nesting.md)·블록 이동이 옳은 레버였다. prob_38·40 같은 큰 인스턴스는 그 기하 국소 최적에 묶여 가속·포트폴리오·scan-repair 어느 것도 크게 못 깬다(아래 5절). 다만 1800초에선 탐색이 더 진행돼(prob_27 −6.5%, prob_20 −15%) 긴 제한시간의 여지는 남는다.

## 5. 버린 길 — 측정으로 기각한 것들

*고르지 않은 길*을 적는 것이 보고서의 차별화 서사다. 셋 모두 그럴듯했지만 측정이 막았다.

- **regret-k 삽입 순서** — area 완화로 값싸게 만든 동적 regret-2가 EDD에 전패했다. area 추정이 크레인 기하를 무시해 "면적은 비지만 못 넣는" 자리를 일찍 줘서다. → best-of-orders 포트폴리오로 대체([04](./features/04-insertion-order-portfolio.md)). 코드는 참고용으로 남겨 `constructor.py`에 *실험·기각*으로 표시했다.
- **균일 가중 destroy_pref(ALNS 연산자)** — 선호를 겨냥하는 destroy를 ALNS에 균일 가중으로 섞으니 SA 난수 궤적이 통째로 흔들렸다. obj3가 인스턴스별 ±10~30% 출렁이는 고분산 wash로, 순위가 67→62로 퇴보했다. → ALNS 밖의 결정적 polish로 대체([09](./features/09-preference-polish.md)).
- **큰 인스턴스 scan-repair** — n≥200에서 ALNS repair를 BLF→scan(nesting)으로 바꿔봤다. 9승 9패 고분산 wash라 거부했다. obj1=0 큰 인스턴스는 scan이 느려 polish 베이스를 악화(prob_10 +38%)시켰고, obj1-heavy는 잡음 밴드 안이며 prob_38·40은 불변이었다. [P5a](./features/07-lower-bound.md) 진단(지각은 repair 후보 종류로 회수 안 됨)을 재확인한 셈이다.

## 6. 제출 준비 상태

[제출 게이트](./GLOSSARY.md)를 네 제한시간 전부에서 통과했다. **10·60·300·1800초 모두 40/40 feasible, invalid 0**(60초 최대 54.4초, 10초 9.22초, 300초 270.4초, 1800초 1620.5초로 시간 초과 0)이다. 솔버 하나만 도는 실서버 조건을 `-j 1`로 모사한 전수 최종 검증(`final_j1`)에서도 40/40 feasible(최대 54.45초)에 단일 시드 대비 **순위 시뮬 53→79**(27승 1패, 유일한 손해 prob_26 +0.1%는 [ALNS](./features/06-alns.md) 잡음)로, 제출 품질을 확정했다. [4코어 포트폴리오](./features/10-seed-portfolio.md)의 멀티프로세싱은 30분 장기 실행에도 메모리 누수·행·OOM이 0이다(피크 747MB/16프로세스 안정). 제출 패키지는 `submit.py`가 `src/`를 zip으로 묶되 평가 서버가 덮어쓰는 `utils.py`는 제외하며(우리 `utils.py`는 대회 원본과 바이트 동일), 빌드·검증(myalgorithm 루트, 필수 5모듈, ≤15MB, 서버 utils.py 모사 import)을 통과했다.

## 7. v1.0.1 — 제출이 드러낸 −1과 그 구조적 제거

로컬 게이트를 다 통과한 v1.0.0 제출이 평가에서 **숨김 인스턴스 P3 하나에 infeasible(−1)** 을 받았다. 학습 40개엔 없던 실패 모드였다. 정직한 진단([11](./features/11-supervisor-feasibility.md))으로 모든 infeasible 경로를 좁혔더니 — improve 경로는 자체 `check_feasibility`로 feasible만 반환하고, floor는 40개 전부 feasible이며, 우리 `utils.py`는 서버 것과 바이트 동일이고, 최종 검증 비용도 dense 해에서 0.11초였다 — 남은 원인은 **메인이 제때 floor를 반환하지 못한 시간 초과**뿐이었다. v1.0.0은 구성(`construct`)과 시드 0의 ALNS·최종 검증을 *메인에서* 돌렸는데, `construct`는 deadline을 넘겨도 남은 블록을 마저 처리하느라 300블록 기준 약 0.6초를 더 쓴다. 재현으로 확증했다 — **2초 제한시간에서 300블록이 3.1초에 overtime** 났다.

수정은 메인을 **감독자(supervisor)** 로 바꾼 것이다. 메인은 floor와 래스터 엔진만 직접 만들고(둘 다 시간이 묶일 수 없다), 구성·ALNS·선호 개선·최종 검증은 전부 종료 가능한 fork 자식이 한다. 메인은 `0.93×timelimit`까지 큐에서 결과를 거두기만 하다가 floor-or-best를 반환하므로, 자식이 느린 Shapely 호출에 묶이거나 OOM으로 죽어도 메인의 벽시계는 자식과 무관하게 흘러 **−1이 구조적으로 불가능**해진다. 측정으로 확인했다 — 2초 overtime이 사라졌고(1.8초 반환), 전체 40개 `-j 1`이 40/40 feasible(sum-obj 223.285M로 v1.0.0의 223.287M과 사실상 동일), **고경합 `-j 4`(16-활성)에서도 40/40 feasible·invalid 0·overtime 0**, 1800초 장기에도 메모리 bounded(자식 ~48MB)다. 품질은 v1.0.0과 동등하게 유지하면서 v1.0.0이 가졌던 −1 위험(timeout·고경합 두 갈래)을 양쪽에서 0으로 만든 것이 v1.0.1의 핵심이다.

## 각 단계 상세

| # | 기능 | 문서 |
|---|---|---|
| 01 | feasibility-first 래퍼 | [01](./features/01-feasibility-first-wrapper.md) |
| 02 | 정수 격자 래스터 엔진 | [02](./features/02-raster-engine.md) |
| 03 | 공존 구성기(양방향 크레인) | [03](./features/03-coexistence-constructor.md) |
| 04 | 삽입 순서 포트폴리오 | [04](./features/04-insertion-order-portfolio.md) |
| 05 | temporal nesting | [05](./features/05-temporal-nesting.md) |
| 06 | ALNS 개선 루프 | [06](./features/06-alns.md) |
| 07 | obj1 하한과 천장 | [07](./features/07-lower-bound.md) |
| 08 | repair 가속 | [08](./features/08-repair-acceleration.md) |
| 09 | 선호 재배치·교환 polish | [09](./features/09-preference-polish.md) |
| 10 | 4코어 시드 포트폴리오 | [10](./features/10-seed-portfolio.md) |

