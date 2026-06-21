# relax-and-repair: obj1 전역 스케줄 천장을 CP로 깬다

- **state**: 측정완료
- **코드**: `src/relax_repair.py` (CP 코어 스케줄 + 크레인 repair) · `src/myalgorithm.py:_worker_relax()` · `_utilization()`
- **관련 결정**: STRATEGY_PLAN.md B3·B5 · [11 supervisor](./11-supervisor-feasibility.md)의 포트폴리오 위에 얹힘
- **배경**: LEARNING_GUIDE F1(수리 최적화) · [GLOSSARY의 obj1·j≥k](../GLOSSARY.md) · [07 하한](./07-lower-bound.md)·[RESULTS 4.1](../RESULTS.md)
- **측정**: `results/relax_gated_full_60s_j1/` (기준 `results/v12p1_full_60s_j1/` = v1.0.2)

## 한눈에

obj1(지각)이 큰 인스턴스는 그동안 어떤 레버로도 안 움직였다. prob_38은 obj1=5129에서 1800초(30배 예산)를 줘도 1px을 못 내렸다. 그 정체가 물리 천장이 아니라 EDD-greedy 구성의 *전역 스케줄* 국소최적임을 [RESULTS 4.1](../RESULTS.md)이 증명했고, 이 기능이 거기를 깬다. 혼잡한 코어 블록의 (베이, entry) 스케줄을 CP-SAT로 *전역 최적*하고(bbox 완화), 그 스케줄을 우리 [nesting](./05-temporal-nesting.md) repair로 크레인-feasible하게 만든다. 이 일은 포트폴리오의 자식 하나가 맡고 나머지 셋은 표준 ALNS라, best-of가 무회귀를 보장한다. CP는 *혼잡 인스턴스에만* 켠다(utilization 게이트). obj3-지배 인스턴스에선 CP가 선호를 무시해 오히려 손해이기 때문이다.

## 왜 이 기능이 필요했나

[하한 분석](./07-lower-bound.md)과 헤드룸 프로브가 두 가지를 박았다. 첫째, prob_38의 같은 60블록이 *격리*하면 지각 36인데 full 인스턴스에선 216이다(6배). 나중 블록이 먼저 블록을 밀어내는 전역 스케줄 실수다. 둘째, bbox 완화를 CP-SAT로 푼 코어 스케줄에 nesting repair를 붙이자 prob_38이 5129에서 4583으로(−10.6%) 내려갔다. 1800초에도 꿈쩍 않던 값이다. 정체의 한계는 시간이 아니라 *이웃 구조*였고, EDD-독립 repair로는 결합 제약(크레인 j≥k + 빈-베이 직렬화)을 풀지 못한다. 그리고 결정적으로, 평가 환경(`ogc2026` conda)에 **ortools가 포함**돼 있어(`ogc2026_env.yml`) CP를 제출 코드에서 쓸 수 있다. 그래서 이 레버가 분석을 넘어 기능이 됐다.

## 하는 일과 내부 동작

`solve_core_schedule`(`src/relax_repair.py`)가 release 이른 혼잡 코어(최대 60블록, CP가 다룰 수 있는 상한이지 train에 맞춘 값이 아니다)의 (베이·방향·위치·entry)를 CP-SAT로 푼다. 모델은 bbox(직사각형) 2D no-overlap(같은 베이·시간겹침 시 x/y/시간 5-way 분리) + `entry≥release` + `exit=entry+proc`이고, 목적은 Σ지각 최소화다. bbox는 다각형보다 *크므로* bbox-no-overlap 스케줄은 공간상 진짜로도 feasible하다(보수적 완화). 크레인·다각형은 솔버에서 빼 [B5](../STRATEGY_PLAN.md)(임의-다각형 MIP 금지)를 지키고, 그 둘은 repair가 처리한다.

`_repair_from_schedule`이 그 스케줄을 [래스터 엔진](./02-raster-engine.md)으로 크레인-repair한다. CP entry 오름차순으로 각 코어 블록을 CP-베이에 `_best_in_bay(cand="scan")`로 넣어 가장 빠른 크레인-feasible 자리에 둔다. scan이라 [오버행 nesting](./05-temporal-nesting.md) 자리까지 쓴다. 코어 밖 블록은 EDD로 둘러 채운다. CP 최적해가 유일하지 않아(같은 코어 지각 0이라도 배치가 다르다) repair 결과가 갈리므로, 타이밍 존중(honor)·release 우선 두 변형을 돌려 `solution_obj`가 작은 쪽을 쓴다. feasibility는 `_best_in_bay`의 양방향 크레인 검사가 보장하고, 마지막에 [supervisor](./11-supervisor-feasibility.md) 자식이 `check_feasibility`로 한 번 더 중재한다.

`_worker_relax`가 이 base 위에서 [ALNS+선호 polish/swap](./06-alns.md)을 마저 돌린다. 포트폴리오에서 자식 0이 relax, 1~3이 표준이다. relax가 못 이기면 표준 셋이 받으므로 **순수 추가**다(best-of 무회귀). CP가 없거나(ortools 부재) 실패하면 relax 자식도 표준 구성으로 폴백한다.

## 버린 선택지들

full 인스턴스(250블록) bbox-CP는 90초에도 좋은 해를 못 찾았고(cp_tard 16900), bbox가 nesting을 버려 우리 솔버보다 나빴다. 그래서 *혼잡 코어만* CP로 풀고 나머지는 nesting repair에 맡긴다. 임의-다각형 + 크레인을 솔버에 직접 싣는 exact는 B5 금지선(폭발)이라 버렸다. CP를 *모든* 인스턴스에 켜는 안은 측정으로 기각했다. CP가 obj3(선호)를 무시해 비혼잡(obj3-지배) 인스턴스에선 베이 할당을 망쳐 prob_18이 +16.4% 퇴보했기 때문이다. 그래서 obj1 발생의 물리 신호인 utilization(블록 면적·체류 / 베이 면적·horizon)으로 게이트해 *혼잡 인스턴스에만* 켠다. obj3-지배 util≤0.42와 obj1-지배 util≥0.42로 깨끗이 갈려 0.45를 경계로 쓴다. 인스턴스 번호가 아니라 어떤 인스턴스에도 계산되는 양으로 게이트하므로 [과적합 금지](../../CLAUDE.md) 원칙에 맞는다.

## 언제·어디서 작동하나

`algorithm()`이 자식을 fork할 때, `ortools` 가용 + 제한시간 `≥30초`(CP 코어 ~9초 + repair 예산) + `utilization ≥ 0.45`이면 자식 0을 relax로 띄운다. 그 외(짧은 제한시간·비혼잡·ortools 부재)엔 표준 4시드 포트폴리오 그대로다. CP 시간 상한은 `min(tl×0.15, 20)`초, CP 워커는 코어 수(`nw`)다. 1워커로는 8초에 코어를 못 풀어(측정) 병렬이 필요하다. CP의 ~9초 동안만 일시적으로 코어를 다투고 그 뒤엔 1스레드로 돌아간다.

## 검증과 한계

전체 40개(`results/relax_gated_full_60s_j1/` vs v1.0.2)에서 40/40 feasible·invalid 0·시간 초과 0을 확인했다. 효과는 relax-OFF 인스턴스의 ALNS 런 노이즈를 걷어내고 **relax-ON 집합만** 보면 선명하다. **7승(평균 −4.3%: prob_38 −10.0%, prob_40 −5.9%, prob_28 −4.1%, prob_39 −3.6%, prob_26 −3.5%, prob_23 −2.5%, prob_31) / 4패(평균 +0.6%, 최대 prob_32 +1.5%) / 6 동률**. 패는 CP가 시간 상한 안에 코어를 못 푼 경우다(prob_27 코어는 90초+ 필요). obj3-지배(relax-OFF)는 게이트로 표준 경로를 타 v1.0.2와 동일하다(예: prob_18 85,057 그대로). 전체 2-way 순위가 동률인 것은 relax-OFF의 단일 런 노이즈가 상쇄해서일 뿐이고, 실제 평가는 *타 팀* 대비라 relax-ON의 큰 obj1 감소가 순점수를 올린다. **무회귀는 best-of(표준 자식이 v1.0.2 보장) + supervisor floor로 구조적**이고, 고경합 `-j 4`(16-활성, CP 멀티스레드 × 4 동시)에서도 40/40 feasible·invalid 0·시간 초과 0(max 55.8초)이며, ortools가 없거나 실패하면 relax 자식이 표준으로 폴백한다. 즉 어떤 환경에서도 −1이 없다.

남은 한계는 이렇다. CP 코어 난이도가 인스턴스마다 달라(prob_40 코어 2.8초 vs prob_27 90초+) 시간 상한 안에 못 푸는 코어는 약한 스케줄을 줘 이득이 작거나 없고(그땐 표준 자식이 받아 손해는 노이즈 수준), relax가 표준 시드 하나를 대신해 그 한 시드의 분산을 잃는다. utilization 경계(0.45) 근처(prob_24·22)는 켜고 끔이 미묘하다. 큰 도약은 nesting과 스케줄을 *동시에* 푸는 것인데, 그건 여전히 [B5](../STRATEGY_PLAN.md) 너머다.

## 후속: 대형 인스턴스 예산-적응 repair

숨김 P3(혼잡 ~900블록, [STRATEGY](../STRATEGY_PLAN.md) 단축-tl 병목 항목)를 파다 이 기능의 대형 사각을 잡았다. repair가 모든 블록을 `"scan"`(nesting)으로, 게다가 두 변형(honor True/False)으로 placed하는데 — train(≤300블록)에선 맞지만 **900블록에선 scan repair가 한 변형만 134초**(blf는 42초)다. return_cap(0.93·tl) 안에 못 끝나 relax 자식이 *통째로 죽고*, 입증된 CP 스케줄 이득이 버려졌다(측정: 표준 655M, relax-scan 미완주로 0 기여). 그래서 train 최대 너머인 **n>350에서만**(=train 바이트동일·무회귀 구조보장) 예산-적응으로 바꿨다 — repair를 *완주하는* `"blf"`로, 한 변형만, CP 워커를 1로(4자식×4워커=16스레드>4코어 oversubscription이 CP를 굶겨 repair를 늦췄다, 측정 658→568M), `_improve`는 `light`로(대형서 ALNS inert(+0.2%)라 ALNS·polish를 건너뛰어 base를 바로 마감), 그리고 `repair_deadline`(0.72·tl)을 넘기면 남은 블록을 `_fallback_place`로 마감(하드 바운드, relax 자식이 반드시 cap 전에 결과를 쓰게).

효과는 *순수 gated upside*다. 60초/900블록 혼잡에서 relax-ON이 표준 대비 **mean −7%(원본 687M→639M, 4회)** — 단 경합 하 O(n²) blf repair가 매 런 진척이 갈려 분산이 크고(568~668M), 이득은 신뢰성보다 *기댓값*이다. 그래도 [best-of](../GLOSSARY.md)라 relax가 늦으면 표준 자식이 받아 **절대 나빠지지 않고**, [scale_gate](../../learning/scale_gate.py)가 600·900·1200·1800블록 + 엣지에서 60초·10초 −1 0·시간초과 0을 확인했다(10초 대형은 floor로 안전 폴백). train(≤300<350)은 `big=False`라 scan·2변형·cp=4·`light=False` 그대로 = *동작 무변*(혼잡 train 5개 feasible·정상 obj 재확인: prob_38 61.6M·40 3.04M·20 157k). 장기-tl(300·1800초)은 표준 scan 자식이 339M로 완주해 best-of로 relax(blf)를 이기므로 relax=blf가 무해하다.

정직한 한계: 이건 단축-tl 대형-혼잡의 *marginal* 개선이지 [scale-construction 병목](../STRATEGY_PLAN.md)의 해결이 아니다. 60초에 scan 품질(339M)에 닿으려면 `feasible_positions`의 O(IFP)·blf repair의 O(n²)를 범주적으로 깬 더 빠른 배치 엔진([skyline](../GLOSSARY.md)/NFP)이 필요하고, 그것이 다음 대규모 이니셔티브다.
