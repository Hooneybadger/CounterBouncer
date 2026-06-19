# v2.0.0 설계 — sparrow 패러다임 × jagua CDE, 우리 제약으로

> 이 문서는 v2.0.0의 *의사결정 + 빌드 계획*이다([STRATEGY_PLAN](./STRATEGY_PLAN.md)의 연장). 아직 구현 전이라 [features/](./features/) 문서가 아니라 설계 기록이다(§5.2: 문서는 구현 뒤에 쓴다 — 단 *계획*은 STRATEGY 층의 몫). 측정으로 각 단계를 닫기 전엔 어느 것도 "확정"이 아니다.

## 0. 한눈에 — 결정

v1 아키텍처(greedy 구성 → 기하-국소 ALNS 개선 포트폴리오)는 천장에 닿았다. **회수 가능한 점수는 전부 2D 불규칙 패킹 + 크레인 j≥k에 있고**(하한 분석: 면적 자원은 non-binding, 18/40 증명 최적, 나머지 22개의 지각은 기하·크레인에서 옴), v1의 이산 재배치 ALNS는 *이동 품질* 벽에 막힌다(features/08: 반복 2.8배 가속에도 prob_38 obj1=5129 불변). de-risk 실험이 "전체 CP 스케줄" 대안을 기각했다(bbox 완화 스케줄은 지각 0으로 풀려도 실현 시 4656 — 병목은 스케줄이 아니라 기하).

v2.0.0은 OR(CP/MIP) 돌파가 아니라 **기하 탐색 돌파**다. SOTA 조사가 패러다임 자체를 준다:

- **탐색**: [sparrow](https://arxiv.org/abs/2509.13329)의 *비중첩 완화 + 가중 GLS 겹침 해소*(구성적 배치가 아니라, 다 놓고 겹침을 연속 push/pull로 밀어내며 자원축을 조인다). 저자가 명시한 일반화 — strip-shrinking → **지각 축소**.
- **기하**: [jagua-rs CDE](https://arxiv.org/pdf/2508.08341)(INFORMS JoC)의 *분리된 충돌검출 엔진* — quadtree + poles surrogate + 증분 갱신, 크레인·시간을 hazard로.
- **희소(18개)**: obj2/obj3 할당을 MIP로 증명 최적.
- **안전망**: v1의 feasibility floor + os.fork 감독자 유지(−1 불가 구조는 양보 없음).

## 1. SOTA 조사 결론 (§5.3 선행 조사)

**jagua-rs CDE — 기하층 설계도.** quadtree 공간 인덱스로 broad phase(대부분 쿼리를 싸게 기각), 통과분만 narrow phase(다각형 교차). 도형은 **poles**(Pole of Inaccessibility 기반 내접원 집합) + **piers**(내부 선분) surrogate로 표현해 fail-fast(surrogate 충돌 → 실제 충돌 확정). AABB 캐시. `move_item(i,t)`로 한 아이템이 움직이면 quadtree를 *증분* 갱신 — 이게 "초당 수백만 쿼리"의 핵심이다(매번 전체 재스캔하는 우리 v1 래스터의 정반대). **hazard 추상화**: 아이템 내부·컨테이너 경계·결함을 한 모델로 — 우리 크레인 j≥k 차폐와 시간 공존을 *hazard*로 자연스레 넣는다. API는 `collisions(shape)→집합`, `move_item`. 보수적(가까우면 충돌, exact fit은 infeasible) — 우리 floor 철학과 같다.

**sparrow — 탐색 패러다임(이동-품질 벽의 답).** 최적화를 *feasibility 문제들의 시퀀스*로 분해: 자원축(strip 길이)을 고정·점감하며, 비중첩을 *일시 완화*(겹침 허용)하고 "겹침 없는 배치를 찾는다". 해소는 **가중 Guided Local Search** — 겹친 쌍마다 가중치 w, 겹친 아이템을 *연속 샘플링*(divergence: 전역 무작위 + focus: 현 위치 근방) + 좌표하강으로 재배치, 점수 = Σ w·quantify_collision. 지속 겹침은 가중치 ×1.2~2.0(escape), 비겹침은 ×0.95 감쇠 → 아이템이 push/pull하다 결국 멀리 "점프". 충돌 정량화는 정확 침투깊이 대신 pole 쌍 가중 침투 + 형상 패널티(큰·오목 도형 가중). 2단계: exploration(0.1%씩 축소·swap 교란) → compression(감쇠율 축소, feasible만 수용). 13개 벤치 전부 SOTA 경신(SWIM +3.9pp). **저자 명시 전이성: strip-shrinking → time/load 축소, 연속 샘플링 → 배치+시작시각, 가중 패널티 → 새 제약 유형.** 우리에게 정확히 맞는다.

## 2. v2.0.0 아키텍처

```
[안전망] feasibility floor + os.fork 감독자  (v1 유지, −1 불가)
[라우팅] utilization 게이트 (희소 / 혼잡)
   ├ 희소(obj1≈0): obj2/obj3 할당 MIP(증명 최적) + 지각-0 유지 스케줄
   └ 혼잡(obj1 지배): sparrow-style 탐색 ───────────────┐
        비중첩 완화 → 가중 GLS 겹침 해소 → 지각 축소     │ collisions()/move_item()
        (연속/격자 샘플링, push/pull, 2단계)            ↓
[기하층 CDE]  분리된 충돌검출 엔진 (jagua 설계)
   quadtree/grid 인덱스 + poles surrogate + AABB 캐시 + 증분 move_item
   hazard = {아이템 내부, 베이 경계, 크레인 j≥k 차폐, 시간 공존}
   numpy 벡터화(안전) + numba/cython/Rust(폴백 게이트된 가속)
```

네 가지가 v1과 근본적으로 다르다:
1. **기하-최적화 분리(CDE).** v1은 탐색이 매 이동마다 느린 feasibility(베이 재스캔)를 부른다. v2는 증분 CDE가 `move_item` 후 영향받은 노드만 갱신 → 쿼리가 싸다. 이게 "반복 수" 병목(features/08)을 친다.
2. **겹침 완화 + 연속 해소(이동 품질).** v1의 이산 destroy/repair가 못 넘던 벽을, sparrow의 가중 push/pull이 넘는다 — 이게 prob_38류 정체의 진짜 후보다.
3. **자원축 = 지각.** strip-shrinking 대신 exit를 due로 당기며(또는 horizon을 조이며) 시공간 겹침·크레인 위반을 GLS로 해소. obj1을 *직접* 압박한다.
4. **크레인·시간 = hazard.** 솔버에 임의-다각형을 안 싣고(B5 유지) CDE의 hazard로 처리 — 우리 temporal nesting(B4)이 "시간 포함 쌍만 오버행 hazard 완화"로 여기 들어간다.

## 3. 구현 제약 — 환경에서 실제로 도는가 (§5.3 / §6)

- **numba는 fragile.** 로컬 ogc2026에서 `numba 0.61 needs numpy≤2.1, got 2.2`로 깨진다([[env-python-shapely-numba]]). 서버는 numba 0.61 명시지만 numpy 해석을 제출 전 확인 불가. ⇒ **속도 1순위는 numpy 벡터화(비트마스크 AND·broadcast)** — 서버에 확실, 버전 무관. numba/cython 컴파일·Rust 정적 바이너리는 [§6 FAQ](../CLAUDE.md)로 *허용되나*(zip 동봉/subprocess) OS·arch·버전 호환 리스크가 있어, **import/실행 실패 시 numpy 경로로 폴백**하는 게이트 뒤에서만 쓴다.
- **CDE를 per-query subprocess로 부르면 죽는다**(쿼리당 IPC). 외부 바이너리는 *덩어리 작업*(예: 한 베이 정적 패킹) 단위로만 의미. 따라서 CDE는 in-process(numpy/numba)가 정석이고, Rust 바이너리는 *측정으로 정당화될 때만* 덩어리 단위로.
- **floor·감독자·정수 출력·utils 미러는 v1 그대로.** v2 코어가 무엇을 하든 floor가 −1을 막는다.

## 4. 냉정한 리스크

- **sparrow엔 시간·크레인이 없다.** GLS를 시공간+크레인+지각으로 적응하는 건 *포팅이 아니라 연구*다 — 충돌 정량화에 시간 겹침·크레인 위반·지각을 어떻게 한 점수로 묶나가 핵심 미지수.
- **sparrow는 20분 런타임에서 SOTA.** 우리는 4코어 throttle·10~1800초. *anytime* 품질(10~60초)이 ALNS보다 나은지는 미검증 — 짧은 tl에서 겹침이 다 안 풀리면 floor로 떨어진다.
- **정수 격자 적응.** sparrow는 연속. poles/quadtree는 정수에 맞으나, 연속 좌표하강을 격자 샘플링으로 바꾼 효과는 측정 필요.
- **할당 MIP 회수가 실재하는지 미확정.** obj3_assign-as-child는 기각됐다(realize가 obj3 흘림). 코어로 승격해도 기하-결합이 같은 한계일 수 있다 — S0에서 갭부터 잰다.

## 5. 단계적 빌드 + de-risk (각 단계 측정 게이트, 무회귀)

전면 재작성을 한 번에 하지 않는다. 가장 싸고 확실한 것부터, 각 단계가 다음을 정당화해야 진행:

- **S0 — 할당 갭 측정(완료, 측정).** obj1=0 희소 인스턴스에서 우리 obj3가 fit-제약 하한 대비 *크게* 벌어졌다(prob_19 w3·gap≈9만, prob_17≈7.8만, prob_3≈5.6만; prob_8만 거의 0). ⇒ 희소 obj3엔 여유가 *실재*한다. **단** 그 하한은 obj2·obj1·기하 실현성을 무시한 낙관치이고, 분리형 obj3_assign(gurobi)·pref 자식은 이미 "realize가 obj3를 흘려" 기각됐다([[p4b-pref-polish]]·features 09). **결론: 별도 할당 MIP를 짓지 않는다 — obj3/obj2를 v2 GLS의 *가중 목적항*으로 흡수한다**(선호·균형·지각·feasibility를 한 점수로 trade off). v1 obj3_assign이 *bolt-on*이라 실패한 자리를, v2는 탐색에 *내장*해 푼다. S0은 이 설계 선택을 확정했다.
- **S1 — CDE 프로토타입(완료, 측정).** `src/v2/gls_raster.py`: 래스터 비트마스크를 CDE로 재사용(poles/quadtree 신규 제작 대신 — §5.3), 충돌 = 레이어별 `(maskᵢ<<shiftᵢ)&(maskⱼ<<shiftⱼ)`.bit_count(). **속도 ✓ 10~30배**(shapely 12~48초 → 0.1~7초). 그러나 *정확한 all-layer 충돌*로 다시 재면 GLS가 BLF를 *근소하게만* 이긴다(best-of-6: prob_27 +1, prob_1 동률, prob_40 +2) — S2의 +6~10%는 layer0-only 충돌(느슨)의 산물이었다. ★진단: 내 충돌 정량화가 *셀 수*(평탄 — 1셀 이동에 카운트 불변 → gradient 없음 → 잔여 2셀에 stuck)라, sparrow의 *pole 침투깊이*(매끄러운 gradient로 블록을 흘려보냄)를 빠뜨렸다(§5.3 impl-gap 반복). 정적 단일베이는 *시간축 자유가 없는* 더 어려운 프록시라, 진짜 가치(시간이동으로 충돌 해소 + 지각 직접 압박)는 S3에서만 드러난다.
- **S2 — sparrow 정적 단일베이 프로토(완료, 측정 — 통과).** `src/v2/gls_proto.py`: shapely CDE(STRtree) + 겹침완화+가중 GLS+정수 좌표하강. 결과: **GLS가 BLF보다 조밀**(3/3: prob_27 bay0 29→**32**, prob_1 34→**36**, prob_40 65→**71**, 정수 격자 겹침 0 검증). 근사 구현(poles 없음·단순 샘플·400반복)으로 +6~10%. ⇒ **sparrow 패러다임이 우리 도형에 통한다(thesis 1차 실증).** 부수 발견: GLS가 한 베이 32~36블록에 12~48초(shapely 교차가 후보마다) → **S1(빠른 CDE)이 필수**임이 확정됐다(jagua poles surrogate+quadtree의 존재 이유). 정적·orient0·회전없음이라 *필요조건*이고, 진짜 검증은 S3(시간+크레인).
- **S3 — 시간+크레인 추가(완료, 측정 — ★기각).** `src/v2/temporal_gls.py`: v1 해에서 출발, (x,y,entry)를 relax-resolve GLS로(공간충돌+크레인 j≥k+지각, 래스터 비트마스크), `check_feasibility` 게이트. 결과: **4/4 인스턴스에서 v1과 동률**(prob_23 474=474, prob_25 661=661, prob_21 187=187, prob_29 4=4). 진단이 결정적이다 — 지각 큰 블록의 entry를 당기면 cur_obj1은 내려가나(prob_23 474→453) **그 충돌·크레인을 해소할 수 없다**(resolve=False) → 되돌림 → 무이득. *지각이 기하/크레인에 묶여 있어 더 이른 entry가 실현 불가*하다는 [하한](./features/07-lower-bound.md)의 발견을 아키텍처 수준에서 실측 확인. ⇒ **S3 게이트 불통과 → v2.0.0 전체 빌드 중단**(아래 판정).

## 판정 — v2.0.0 전체 빌드 중단

de-risk 게이트(S0~S3)의 종합 결론은 **"v2.0.0 기하-탐색은 v1을 의미 있게 못 이긴다"**이고, 따라서 제출가능 v2.0.0 전체 재작성을 *하지 않는다*. 네 갈래 증거가 한 곳으로 모인다 — (1) [하한](./features/07-lower-bound.md): dense obj1 헤드룸은 작다(면적 non-binding, 5배 시간=1.4%, 기하/크레인-locked). (2) S2 정적 GLS: 정확한 충돌로 재면 BLF를 근소하게만(+0~2) 이긴다. (3) S3 시간축 GLS: 4/4 동률, 더 이른 entry가 해소 불가. (4) v1은 18/40에서 obj1=0 증명 최적. 즉 v1은 *지배 목적에서 이미 기하 천장 근처*다. v2의 기대이득(있어도 한 자릿수 %)이 거대·위험한 재작성을 정당화하지 못한다 — 측정-only·무회귀·과적합금지 규율의 결론이다.

한계(정직하게): GLS resolver가 근사(sparrow의 pole-gradient/가중 미구현)라 *완벽한* 구현은 미세하게 더 풀 수 있다. 그러나 (a) "더 이른 entry 해소 불가"는 resolver 약점이 아니라 *구조*(공간이 없음)이고, (b) 하한은 impl-무관 CP 증명이라 *완벽한 엔진도* 작은 헤드룸에 묶인다. 4갈래 수렴이 높은 확신을 준다.

이 탐색의 가치는 *버린 길*로서다 — "우리는 SOTA 패러다임(sparrow×jagua)을 우리 문제에 적응해 실측하고, 지각 천장이 기하/크레인-locked임을 위·아래에서 못박았다"는 서사는 결선 보고서의 강한 차별점이다(대부분 팀은 자기 천장을 증명 못 한다). 다음 투자는 v2 재작성이 아니라 **보고서 + v1 미세개선(targeted repair 등)**이다.
- **S4 — 통합·포트폴리오·floor 폴백·전체 게이트**(40개×4 제한시간 invalid 0).

각 단계는 floor 폴백을 유지하고, batch_runner 무회귀를 통과해야 한다. S0/S2가 핵심 분기점 — 둘 다 싸게 닫고 나서야 비싼 S1/S3에 투자한다.

## 참조 (SOTA)

- Gardeyn, Vanden Berghe, Wauters. *An open-source heuristic to reboot 2D nesting research* (sparrow), [arXiv:2509.13329](https://arxiv.org/abs/2509.13329), 2025.
- *Decoupling Geometry from Optimization in 2D Irregular C&P: an Open-Source Collision Detection Engine* (jagua-rs), INFORMS JoC, [arXiv:2508.08341](https://arxiv.org/pdf/2508.08341).
- 우리 측 근거: [features/07 하한](./features/07-lower-bound.md)(기하가 병목)·[features/08 repair 가속](./features/08-repair-acceleration.md)(이동 품질 벽)·[features/14 relax-repair](./features/14-relax-repair.md)(스케줄 레버의 한계)·de-risk 실험(전체 CP 기각).
