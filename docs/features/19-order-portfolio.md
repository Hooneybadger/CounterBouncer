# 순서 포트폴리오: C 배치로 수천 개 구성 순서를 훑어 소형~중형의 구성-순서 헤드룸을 깬다

> 처음 보는 용어([전 위치 스캔](../GLOSSARY.md), [EDD](../GLOSSARY.md), [ALNS](../GLOSSARY.md), [BLF](../GLOSSARY.md), [best-of](../GLOSSARY.md))는 용어집에 정의해 두었습니다.

- **state**: 구현 · 측정완료
- **코드**: `src/c_engine.py`의 `run_portfolio`/`_gen_orders`(배치 마샬·재구성) · `src/scan_engine.c`의 배치 루프(`compute_obj`·시간가드) · `src/myalgorithm.py`의 `_portfolio_body`/특수 자식 게이트
- **관련 결정**: [STRATEGY_PLAN](../STRATEGY_PLAN.md) 분류·특화 항목 · **위에 섬**: [features/18](./18-c-scan-engine.md)(C scan 엔진)·[features/04](./04-insertion-order-portfolio.md)(파이썬 순서 포트폴리오의 한계)·[features/06](./06-alns.md)(ALNS)
- **측정**: `learning/_scale_quality/c_engine/`(`portfolio.py` 배치·결합 벤치, `confirm.py` 폭 확인), train n=100 4/4 승(+27~76%)

## 한눈에

[features/04](./04-insertion-order-portfolio.md)에서 우리는 구성 순서를 EDD·edd_area 두 개만 best-of로 봤다 — 파이썬 scan이 느려 더는 못 돌렸기 때문이다. 그런데 [features/18](./18-c-scan-engine.md)이 같은 구성기를 ~19배 빠른 C로 옮기자, *한 번 호출에 수천 개의 서로 다른 구성 순서*를 돌리는 길이 열렸다. 그래서 물었다 — 소형 인스턴스에서 우리가 흘리는 품질이 *순서 탐색의 부족*에서 오는가? 측정이 그렇다고 답했다: prob_1(n=100)에서 우리 full 파이프라인 obj 21,021을, 수천 순서 best 위에 [ALNS](../GLOSSARY.md)를 얹은 경로가 **4,905(+76.7%)** 로 깼다. n=100 네 인스턴스 전부 이겼다(+2.8~76.4%).

핵심은 **구성 순서가 소형에서 obj를 지배하는데 EDD+ALNS는 그 공간을 거의 안 본다**는 것이다. C 배치 엔진이 EDD·edd_area·slack·release + 폭넓게 perturb한 EDD 수천 개를 돌려 내부 obj로 best를 고르고, 그 best를 [committed](../GLOSSARY.md) 상태로 재구성해 [ALNS](../GLOSSARY.md)가 마저 다듬는다. [best-of](../GLOSSARY.md)라 순수 추가다 — 포트폴리오가 약한 구간(n≈200 혼잡)에선 같은 [supervisor](./11-supervisor-feasibility.md) 안의 relax·표준 자식이 거둬 무회귀를 지킨다.

## 왜 이게 필요했나

직접적 단서는 순위였다. 제출 피드백상 우리 코드는 ~30위권인데, 그것은 *우리를 앞선 팀이 29팀 있다*는 뜻이고 곧 헤드룸이 실재한다는 증거다. [features/07 하한](./07-lower-bound.md)은 느슨해 obj1 천장을 못 박지 못하고, 메모리의 "obj1 = 측정 천장" 결론은 *우리 도구함의 한계*였지 *문제의 천장*이 아니었다. 상위권이 private 과적합일 수도, 인스턴스를 분류해 특화 알고리즘으로 처리하는 것일 수도 있다 — 블랙박스다. 1등이 목표라면 후자를 가정하고 우리 약점을 찾는 게 옳다.

그 약점이 소형의 구성 순서였다. [features/04](./04-insertion-order-portfolio.md)는 regret-k를 기각하고 edd_area best-of를 채택했지만, 본질은 "파이썬 scan이 느려 순서를 두세 개밖에 못 본다"였다. C 엔진(features/18)이 그 제약을 풀자 가설을 측정할 수 있게 됐다. `learning/_scale_quality/c_engine/confirm.py`로 train 1~12을 우리 full 파이프라인(@60초) 대 순서 포트폴리오(@55초)로 대조하니 분포가 또렷했다 — **n=100은 4/4 승(평균 +37%)**, n=150·200은 패(순서가 적게 들고 ALNS가 더 중요). 격차의 폭(prob_1 +68%, prob_4 +50%)이 우연한 노이즈가 아니라 구조적 누락임을 말했다.

## 하는 일과 내부 동작

세 단계다 — **순서 생성(Python) → 배치 평가(C) → best 위 ALNS(Python).**

`src/c_engine.py`의 `_gen_orders`가 결정적 네 순서(EDD, due+면적, slack, release)에 더해 due-span에 비례하는 폭넓은 강도로 perturb한 EDD를 섞어 n_orders개를 만든다. 강도를 `span·(0.03~0.73)`로 넓게 흩뿌리는 게 요점이다 — 좁게 흔들면 EDD 근방만 보고, 넓게 흔들면 전혀 다른 적치 순서까지 표본해 best가 깊어진다. 이 순서들을 인스턴스 기하(features/18의 마샬 포맷) 뒤에 `N_ORD`개로 평탄화해 한 파일에 싣는다.

`src/scan_engine.c`의 main이 배치 루프를 돈다 — 각 순서마다 occupancy·bay_loads를 리셋하고 그 순서로 [scan 구성](./05-temporal-nesting.md)을 완주한 뒤 `compute_obj`(검증기와 같은 공식: obj1=Σmax(0,exit−due), obj2=⌊max 쌍 불균형⌋, obj3=Σ(maxpref−pref))로 내부 obj를 재고, 최저를 best로 추적한다. 루프 머리에 벽시계 가드(`max_s`)를 둬 *예산 안에 든 순서만* 평가하고 best placement(+그 obj)를 낸다 — 그래서 호출부는 "8000개를 만들되 든 만큼만 돈다"를 안전하게 쓴다. 모든 비트연산은 features/18의 native u64 시프트라 각 construct가 파이썬의 ~1/19 시간이다.

C가 낸 best placement를 `run_portfolio`가 [committed](../GLOSSARY.md) 레코드로 재구성한다 — `constructor.py`가 만드는 것과 *정확히 같은 포맷*(`bay·bid·orient·px·py·entry·exit·masks·wbb`)이라, `operations_from_committed`·`solution_obj`·[ALNS](./06-alns.md)가 그대로 소비한다. `src/myalgorithm.py:_portfolio_body`가 그 committed 위에서 `_improve`(ALNS + 선호 polish + 교환)를 돌린다. 순서 탐색이 좋은 *출발점*을, ALNS가 그 위 *국소 개선*을 맡아 둘이 곱해진다 — prob_1에서 포트폴리오 4,996을 ALNS가 2,884까지 더 내렸다(결합 +86%). feasibility는 `_improve`의 `check_feasibility`가 보증한다 — infeasible이면 None을 내고 best-of가 무시한다.

## 버린 선택지들

**순서당 subprocess**(`portfolio.py:portfolio`)는 호출당 마샬+프로세스 비용이 들어 55초에 600~1000순서에 그쳤다 — 배치(한 호출에 다 싣기)로 같은 예산에 수천 개로 늘렸고, prob_1이 +68%→+76%로 더 깊어졌다. **포트폴리오 단독(ALNS 없이)** 은 n=100엔 강하나 n≥150에선 졌다(prob_5 −6.8%) — ALNS를 얹자 n=150이 +5.6% 승으로 뒤집혔다. 그래서 "순서탐색+국소탐색"을 한 단위로 묶었다. **크기로 하드 분기**(n≤120만 포트폴리오)는 과적합 위험이다 — train 임계를 박으면 private의 다른 크기에서 무너진다([anti-overfit](../STRATEGY_PLAN.md)). 대신 *모든 크기에서 best-of*로 두고(포트폴리오가 지면 relax·표준이 거둔다), 크기 게이트는 "포트폴리오를 *띄울지*"(n≤250 — n=300은 포트폴리오가 자식 슬롯만 차지해 −4.9% 손해라 제외)에만 써 무회귀를 구조로 보장한다. **순서 생성도 C로**(시드→C 내부 생성) 옮겨 더 많은 순서를 보는 길은 **측정으로 기각**했다 — order-search가 포화하기 때문이다(prob_1은 ~40초/수천 순서서 4,996에 평평, 대형은 4 결정순서서 포화). 더 많은 순서는 obj를 더 안 내리고, 남는 예산은 ALNS가 더 잘 쓴다(국소탐색이 order-search 평탄면 *아래로* 간다, prob_1 4,996→2,884). 즉 헤드룸은 순서 *수*가 아니라 ALNS·구성순서 다양성의 *질*에 있다.

## 언제·어디서 작동하나

`algorithm()`이 `n ≤ 350` + 바이너리 가용 + 제한시간 `≥10초`일 때 자식 0을 포트폴리오로 띄운다(`src/myalgorithm.py`의 specials 라우팅). C 배치 예산은 `0.45·tl`, 나머지는 `_improve`의 ALNS(≤0.83·tl)가 받는다. 순서 수는 제한시간에 사다리로 맞춘다(tl≥45→8000, ≥20→3000, 그 외 1000; n>200이면 4000으로 캡 — 큰 인스턴스는 순서당 construct가 비싸다). 혼잡(util≥0.45)이면 자식 1에 [relax](./14-relax-repair.md)를 *함께* 띄워, 포트폴리오가 약한 n≈200 혼잡에서 relax가 안전망이 된다. `n > 350`은 포트폴리오를 띄우지 않고 검증된 [cengine 단독](./18-c-scan-engine.md)을 유지한다(대형은 순서당 construct가 비싸 포트폴리오가 약하고, 대형 경로를 건드리지 않아 무회귀). 바이너리 부재·짧은 tl이면 표준 경로 그대로다.

## 검증과 한계

[feasibility-first](../GLOSSARY.md)가 절대 규율이라 *무회귀*를 best-of 구조로 먼저 보장했다(40/40 invalid 0, 60초 전수 2회 + [supervisor floor](./11-supervisor-feasibility.md)). 채택의 종료 기준은 포트폴리오가 발화하는 **n≤250 전체 36개를 ON/OFF로 1개씩**(`systemd-run --user --scope -p CPUQuota=400%` = 서버 모델) 대조한 정의적 측정이다 — **합계 obj 214,345,123→205,393,381(−4.2%), 26승·9무·1패**(유일 패 prob_27 −1.0%, 노이즈 수준). 윈은 좁지 않고 넓다 — prob_1 **+80.8%**, prob_4 +69.7%, prob_14 +34.1%, prob_35 +34.0%, prob_16 +25.0%, prob_28 +24.8%… 그리고 결정적으로 *rank를 가르는 고-obj 20개*(prob_21~40)가 16/20 승·합계 −4.1%다(고-w1 obj1-지배 = R−nb 점수 집중 구간).

★**측정 방법론 — oversubscription 아티팩트를 조심한다.** 같은 비교를 `batch_runner`의 *병렬* 실행으로 하면 포트폴리오 자식의 C 서브프로세스가 다른 자식을 굶겨 per-instance obj에 ±20~30% 노이즈가 실린다 — "회귀 13건"이 *허위로* 떴고(포트폴리오를 쓰지도 않는 n=300 prob_20이 +20%로 뜸), 1개씩 재측정하니 12건이 승·tie였다. 그래서 이 표는 전부 1개씩이고, 병렬 측정은 feasibility·순위 *방향*에만 쓴다([THROTTLE_MEASUREMENT](../../learning/THROTTLE_MEASUREMENT.md)).

한계는 정직하게 적는다. **순서 생성이 파이썬**이라 8000개에 최대 ~4초가 들지만, order-search 포화로 더 많은 순서가 무이득이라 C 이관은 기각했다(위). **포트폴리오의 승은 크기 의존**이다 — n=100엔 +76%, n=150엔 +5.6%, n≥200 혼잡엔 종종 패다. best-of가 손해를 막지만, 큰 인스턴스의 헤드룸은 포트폴리오가 아니라 [relax](./14-relax-repair.md)·구성기 throughput([features/18](./18-c-scan-engine.md))의 몫이다. 그리고 이 측정은 train 표본 위의 것이라, private의 크기 분포가 다르면 이득의 크기는 달라진다 — 다만 *무회귀는 구조적*이라(best-of) 방향은 안전하다. **소형이 점수에서 차지하는 비중**은 hidden 분포에 달려 제출 피드백으로만 확인되나, 채점이 obj에 단조라 우리 obj가 내려간 만큼은 손해가 아니다.
