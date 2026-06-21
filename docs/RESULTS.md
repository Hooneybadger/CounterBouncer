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

## 3.5 C 엔진과 순서 포트폴리오 — "obj1 천장"의 재발견

제출 피드백상 ~30위라는 사실이 "obj1은 측정 천장"이라는 우리 결론을 반증했다 — 29팀이 앞선다는 건 헤드룸이 실재한다는 뜻이고, 그 "천장"은 *우리 도구함의 한계*였다([하한](./features/07-lower-bound.md)이 느슨해 진짜 천장을 못 박는다). 두 곳에서 천장을 깼다. **(1) C scan 엔진([features/18](./features/18-c-scan-engine.md))** — Python scan을 native u64로 byte-identical·~19× 복제해, 단축-tl 대형-혼잡(P3류, n≈900)이 못 끝내던 scan 완주를 60초 안에 해낸다(합성 900블록 혼잡 655M→339M, −48%). **(2) 순서 포트폴리오([features/19](./features/19-order-portfolio.md))** — 그 C 속도로 *한 호출에 수천 개 구성 순서*를 배치 평가해 best를 골라 그 위에 [ALNS](./features/06-alns.md)를 얹는다. 구성 순서가 소형~중형 obj를 지배하는데 EDD+ALNS는 그 공간을 안 봐 헤드룸을 흘렸다.

| 측정 | 기준 | 개선 | 비고 |
|---|---|---|---|
| 순서 포트폴리오 n≤250 전체 36개 합(1개씩) | 214,345,123 | **205,393,381 (−4.2%)** | **26승 / 9무 / 1패**(prob_27 −1.0%) |
| └ 고-obj 20개(prob_21~40, rank 지배) | 213,284,352 | **204,491,929 (−4.1%)** | 16/20 승. 최대 prob_1 +80.8%·prob_4 +69.7%·prob_35 +34.0% |
| C 엔진 대형(P3류, 합성 900-혼잡) | 736M(cengine 前)·339M(EDD단일) | **332,308,186** | cengine로 736→339M(−54%), 다시 4순서 best-of로 −1.9%([features/18](./features/18-c-scan-engine.md)) |

대형도 구성 순서가 obj를 가른다 — C 엔진은 단일 EDD가 아니라 4개 결정 순서(EDD·edd_area·slack·release)의 best-of로 construct한다(900-혼잡 −1.9%). 각 construct가 비싸 *정밀 시간가드*(매 순서마다 체크+다음순서 예측, overshoot 0, EDD가 첫 순서라 1개만 들어도 옛 단일 EDD=무회귀)로 deadline 안에 든 순서만 평가한다. 옛 8순서마다 체크는 대형서 너무 성겨 tl=30에 자식이 죽었는데(2.38억 회귀) 정밀가드가 단일 EDD(3.39억)로 안전 degrade해 고쳤다.

★**측정 방법론 — oversubscription 아티팩트.** 이 표는 전부 `systemd-run --user --scope -p CPUQuota=400%`·**1개씩**(서버=1인스턴스·4코어 전용 모델)이다. `batch_runner`의 *병렬* 실행은 포트폴리오 자식의 C 서브프로세스가 다른 자식을 굶겨 per-instance obj에 ±20~30% 노이즈를 실어, "회귀 13건"을 *허위로* 만들었다(예: 포트폴리오를 안 쓰는 n=300 경로의 prob_20이 +20%로 뜸). 1개씩 재측정하니 그 13건 중 12건이 승·tie였고 진짜 회귀는 prob_27(−1.0%) 하나뿐이다([THROTTLE_MEASUREMENT](../learning/THROTTLE_MEASUREMENT.md)). 교훈: 동시 실행 측정은 feasibility·순위 *방향*엔 쓰되 per-instance obj 결정엔 못 쓴다.

통합은 *크기 하드 분기가 아니라 [best-of](./GLOSSARY.md)*다(과적합 금지) — `n≤250`이면 자식 0을 포트폴리오로, 혼잡(util≥0.45)이면 자식 1에 [relax](./features/14-relax-repair.md)를 *함께* 띄워, 포트폴리오가 진 인스턴스에서도 다른 자식이 거둔다. `n>350`은 검증된 cengine 단독을 유지하고, `250<n≤350`은 표준 경로 그대로다. feasibility는 40/40 invalid 0(60초 전수 2회)·[supervisor floor](./features/11-supervisor-feasibility.md)로 −1 불가.

## 4. 천장 — 우리가 최적에 얼마나 가까운가

자기 과거 버전이 아니라 절대 기준으로도 쟀다([07](./features/07-lower-bound.md)). obj1(지각)의 [면적완화 cumulative 하한](./GLOSSARY.md)을 CP-SAT로 풀었더니 **40개 전부 ≈0(non-binding)**, 그중 **18/40은 우리 obj1이 이미 0이라 증명된 최적**이다. 지배 목적을 절반 가까이에서 최적으로 풀었다는 뜻이다. 남은 지각은 자원이 아니라 [2D 기하·크레인 j≥k](./GLOSSARY.md)에서 오고, 그래서 [nesting](./features/05-temporal-nesting.md)·블록 이동이 옳은 레버였다. prob_38·40 같은 큰 인스턴스는 그 기하 국소 최적에 묶여 가속·포트폴리오·scan-repair 어느 것도 크게 못 깬다(아래 5절). 다만 1800초에선 탐색이 더 진행돼(prob_27 −6.5%, prob_20 −15%) 긴 제한시간의 여지는 남는다.

### 4.1 정체는 물리가 아니라 *전역 스케줄*이다 — relax-and-repair 프로브

"prob_38의 obj1=5129는 진짜 천장인가, 아니면 우리 탐색의 한계인가?"를 직접 갈랐다. 두 측정이 답을 준다. 첫째, 같은 블록을 *격리*해 크레인을 완전히 켠 채 풀면 첫 60블록이 지각 36인데, 그 60블록이 *full 인스턴스 안*에서는 216이다(6배). 둘째, **bbox 완화를 CP-SAT로 푼 전역 스케줄(혼잡 코어 60블록을 OPTIMAL로) 위에 우리 [nesting](./features/05-temporal-nesting.md) repair를 얹자 prob_38이 5129→4583(−10.6%)으로 내려갔다** — 1800초(30배 예산)에도 1px 안 움직이던 값이다. 둘 다 같은 결론이다: 정체는 2D·크레인 물리가 아니라 **EDD-greedy 구성 + 독립 repair가 전역 스케줄 국소 최적에 갇힌 것**이고, 그 헤드룸은 시간이 아니라 *이웃 구조*로만 닿는다(`learning/p6_relax_repair_probe.py`).

처음엔 이걸 연구 결과로만 뒀다 — CP(ortools)가 제출 환경에 없을 줄 알았기 때문이다. 그런데 조직위가 평가를 *우리가 쓰는 `ogc2026` conda 환경*으로 돌린다고 답했고, 그 `ogc2026_env.yml`엔 **ortools(우리가 쓴 9.15.6755 그대로)·gurobi·xpress가 들어 있다**. 즉 CP를 제출 코드에서 쓸 수 있다 — 이 한 사실이 relax-and-repair를 분석에서 제출 기능으로 바꿨다([14](./features/14-relax-repair.md), v1.1.0).

기능으로 만들 때 두 가지를 측정으로 정리했다. CP는 obj1만 보고 obj3(선호)를 무시하므로 비혼잡(obj3-지배) 인스턴스에선 베이 할당을 망쳐 손해다 — 그래서 obj1 발생의 물리 신호인 utilization(블록 면적·체류 / 베이 면적·horizon)으로 게이트해 *혼잡 인스턴스에만* 켠다(obj3-지배 ≤0.42 vs obj1-지배 ≥0.42, 0.45가 분리선). 그리고 relax는 포트폴리오의 자식 하나로만 돌려, 못 이기면 표준 자식 셋이 받는다(best-of 무회귀). 결과는 relax-ON 집합에서 **7승(평균 −4.3%: prob_38 −10.0%·40 −5.9%·28 −4.1%·39 −3.6%·26 −3.5%) / 4패(평균 +0.6%) / 6 동률**, 전체 40/40 feasible(`-j 1`·고경합 `-j 4` 모두 −1 0). 1800초에도 안 움직이던 obj1 천장이 마침내 두 자릿수 % 내려갔다. 남은 진짜 도약은 nesting과 스케줄을 *동시에* 푸는 것인데, 그건 여전히 [B5](./STRATEGY_PLAN.md)의 다각형-MIP 금지선 너머다.

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

## 8. v1.0.2 — 스케일에서도 −1을 막는다 (floor 강건화)

v1.0.1이 메인의 무거운 일을 자식으로 뺐지만 **floor만은 메인에 남아 있었고**, 그 floor가 블록수에 거의 세제곱으로 폭발했다([13](./features/13-floor-scale-hardening.md)). train은 300블록이 최대라 안 보였지만, [과적합 금지 원칙](../CLAUDE.md)으로 train 범위를 넘겨 스트레스하자 floor가 600블록 4.4초·**900블록 15.0초**로 치솟아, `return_cap`(0.93×tl) 검사보다 먼저 메인에서 도는 floor가 짧은 게이트에서 −1을 냈다(P3와 같은 실패 모드, 이번엔 스케일이 방아쇠). 빈-베이 윈도우 계산(`_empty_bay_entry`)을 정렬 단일 패스로 바꾸고 방향 루프 밖으로 끌어내 floor를 거의 선형으로 낮췄다 — **900블록 15.0초→0.03초**, 1800블록 0.11초. 거기에 deadline fast-finish를 더해 아무리 큰 인스턴스라도 메인이 시간 안에 완전한 feasible을 낸다. 둘째로, floor의 경계 검사가 `+1e-6` 과대 허용이라 경계에 sub-eps 걸치는 블록을 통과시키고 검증기는 거절하던 구멍을, 검증기와 정확히 같은 무허용 검사로 맞춰 막았다. train floor는 sum-obj 25,488,553,408로 변경 전과 byte 단위 동일하고(무회귀), end-to-end로 600·900블록을 10초에 feasible 반환한다(v1.0.0/v1.0.1은 900블록서 −1). 같은 라운드에 시도한 obj3 [bay-clear-refill](./features/12-bay-clear-refill.md)은 측정상 이득이 ALNS 잡음에 묻혀(순위 비퇴보 미달) 채택을 보류했다 — 무회귀라 해롭진 않으나 측정이 복잡도를 정당화하지 못했다.

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
| 18 | C scan 엔진(대형-혼잡 −48%) | [18](./features/18-c-scan-engine.md) |
| 19 | 순서 포트폴리오(소형~중형 −4.2%·n=100 +80%) | [19](./features/19-order-portfolio.md) |

