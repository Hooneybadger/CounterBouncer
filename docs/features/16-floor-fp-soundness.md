# floor fit 판정의 부동소수 정합: 검증기 contains_block을 직접 써 ULP 경계 −1을 없앤다

- **state**: 측정완료
- **코드**: `src/myalgorithm.py:_placed_corner()` · `_orient_corners()` · `_min_overflow_place()` · `_guaranteed_place()` · `_safe_finish_place()` · 회귀 게이트 `tools/floor_gate.py:_check_fp_boundary()`
- **관련 결정**: B1·P1(feasibility-first) — [15 floor ref-anchor 정합](./15-floor-ref-anchor.md)의 후속이자 *심화*
- **배경**: LEARNING_GUIDE F2 · [GLOSSARY의 빈-베이 윈도우](../GLOSSARY.md)
- **측정**: ref≠(0,0) 분수 합성 게이트 · 10-페르소나 QA red-team(round 1 발견, round 2 수렴)

## 한눈에

[15](./15-floor-ref-anchor.md)는 floor의 경계 계산을 검증기 `Block.bounding_rect()`로 바꿔 reference point가 (0,0)이 아닌 블록을 바로 놓게 고쳤다. 그런데 거기엔 *더 깊은* 한 겹이 남아 있었다. 15는 ref 보정된 bbox를 *원점에서 한 번* 구한 뒤(`_ref_bbox`), floor가 직접 `px+bb[2] ≤ width`로 경계를 판정했다. 검증기는 다르게 한다 — 블록을 실제 `(px,py)`에 놓고 bbox를 *다시* 계산한 다음 `contains_block`으로 본다. `py + max(v−ref)`와 `max(v + (py−ref))`는 수학적으로 같지만 부동소수 비결합성으로 **약 1 ULP 어긋난다**. 그래서 블록 extent가 베이 변과 *정확히* 일치하고 ref가 분수이면, floor는 `15 + 0.0 = 15.0 ≤ 15`(통과)인데 검증기는 같은 자리에서 `15.000000000000002 ≤ 15`(거절)이 되어, 깨끗이 드는 다른 방향이 있는데도 floor가 그 1 ULP 초과 배치를 커밋해 −1을 낸다. 이 변경은 floor의 fit 판정 자체를 검증기 `contains_block`(placed Block)으로 만들어 *float 연산 순서까지* 일치시킨다 — 이제 floor가 통과시키는 배치는 검증기도 반드시 통과시킨다.

## 왜 이 기능이 필요했나

15를 만든 직후, 팀은 "정말 −1이 없는가"를 그 한 사람의 분석만으로 믿지 못했다. 그래서 서로 다른 경력·관점을 가진 **QA 페르소나 10명**(property-based·계산기하·OR·카오스·경계값·SRE·공격보안·패킹·실데이터·커버리지 비평가)을 띄워 각자 다른 각도로 floor를 적대적으로 두들겼다. 규율은 하나였다 — *infeasible 출력은 입력이 실제로 feasible할 때만 버그*이므로, feasibility 보존 변환(re-anchor·scale-time·duplicate·permute)으로 known-feasible 입력만 만들어 때리고, 발견은 독립 triage가 재현해 판정한다.

커버리지 비평가 페르소나(Grace Hall)가 1건을 찾았고 triage가 독립 재현했다. `train/prob_37`의 한 블록을 분수 `(1.586…, −2.944…)`만큼 re-anchor한 단일-베이(85×15) 단일-블록 인스턴스에서, floor가 orient 2를 `(16,15)`에 놓는다 — `py + bb[3] = 15 + 0.0 = 15.0 ≤ 15`이라 통과시키지만, 검증기는 `Block(x=16,y=15)`를 만들어 `max_y = 15.000000000000002`(1.78e-15 = 1 ULP 차)를 얻어 `contains_block`이 False → `Stage2: block 0 exceeds bay boundary (area=0.000)` → infeasible. 입력이 feasible함은 증명됐다 — orient 6을 `(1,0)`에 놓으면 깨끗이 들고(`bbox=(0.93, 0, 16.71, 14.47)`, contains_block True) 전체 `check_feasibility`가 stage 5로 통과한다. floor는 그 orient 6을 *시도조차 안 하고* 1 ULP 초과한 orient 2를 먼저 커밋했다.

[15가 이 사각을 못 본 이유]가 핵심이다. train 57560개 방향은 ref가 전부 정수 (0,0)이고 [15의 회귀 게이트]는 re-anchor에 *정수* shift만 썼다 — 정수 ref는 `py + (정수)`와 `정수 + ...`가 정확히 같아 ULP 발산이 없다. **분수 non-(0,0) reference**라야 발산이 생기는데, train은 좌표에 분수 정점이 694124개 있어(Elena 측정) 숨김 인스턴스가 분수 ref 블록을 가질 가능성은 충분하다. 즉 15의 게이트조차 못 보던 한 겹 아래의 −1이었고, 10-페르소나 적대적 검증이라야 드러났다.

## 하는 일과 내부 동작

`_placed_corner(blk_data, oi)`가 한 방향을 leftmost-lowest 정수 코너에 놓은 *검증기 `Block` 객체 자체*와 그 `(px,py)`를 돌려준다(`src/myalgorithm.py`). `(px,py)`는 여전히 원점 bbox(`_ref_bbox`)로 `px=max(0,ceil(−bb[0]))`처럼 잡지만, **경계 판정은 그 값으로 하지 않는다.** 대신 `placed = Block(0, blk, px, py, oi)`를 만들어 호출부가 베이마다 `bay.contains_block(placed)`로 본다 — 검증기가 채점 때 쓰는 *바로 그 코드, 바로 그 float 연산 순서*다. 그래서 floor가 fit이라 판정한 배치는 검증기도 반드시 fit이라 판정한다(정의상).

좌·하 경계(`bb[0]≥0, bb[1]≥0`)는 베이와 무관하므로 `_placed_corner`가 placed bbox로 한 번 확인해, 분수 ref에서 1 ULP만큼 음수로 떨어지면 `px`(또는 `py`)를 1 올려 보정한다. 우·상 경계는 베이 치수에 걸리므로 베이별 `contains_block`이 본다. 방향별 placed Block은 베이와 무관해 `_orient_corners`가 블록당 한 번만 만들고, `contains_block`은 Block에 캐시된 `bounding_rect`를 읽어 4번 비교만 하므로 베이 루프는 여전히 O(1)이다 — 15 대비 추가 비용은 방향당 Block 1개 더 생성하는 정도(safety net이라 무시 가능, 250블록 floor ≈ 10ms 유지). `_min_overflow_place`의 경계 초과도 placed bbox로 재 검증기와 일치시켰다.

## 버린 선택지들

**floor 판정에 epsilon 허용오차(`px+bb[2] ≤ width + 1e-6`)를 주는 길**은 버렸다 — 이건 [13](./13-floor-scale-hardening.md)이 *반대 방향으로* 이미 밟은 함정이다(13은 1e-6 허용이 경계에 걸친 블록을 floor가 통과시키고 검증기가 거절하게 해 −1을 내자 그 허용을 *제거*했다). 허용오차는 한쪽 −1을 막으면 다른 쪽 −1을 연다. 검증기와 *정확히* 같아야 하는데, 임의의 epsilon은 그 일치를 보장 못 한다. **검증기 bbox를 손으로 더 정확히 복제하는 길**도 버렸다 — 15에서 손계산이 ref를 빠뜨렸고 16에서 손계산이 float 순서를 빠뜨렸다. 같은 교훈이 두 번 났다: *검증기 기하는 복제하지 말고 검증기 코드를 호출한다.* 그래서 fit 판정의 마지막 한 줄까지 `contains_block`에 위임한다. **placed Block을 베이마다 새로 만드는 길**(나이브)은 비용이 n_bays배라 버리고, placed가 베이 무관임을 이용해 방향당 한 번만 만든다.

## 언제·어디서 작동하나

floor가 발동하는 *모든* 경로(정상 빈-베이 윈도우 `_guaranteed_place`, fast-finish 직렬 `_safe_finish_place`, 예외 폴백 `_min_overflow_place`)에서 fit 판정이 `contains_block`을 거친다. 자식 결과 경로는 무관하다 — 자식은 `_improve`가 `check_feasibility` 통과분만 내보내므로 애초에 검증기로 걸러진다. 이 변경은 검증 없이 반환되는 유일한 해(floor)의 경계 판정을 검증기와 비트 단위로 정합시킨다.

## 검증과 한계

red-team의 발견을 그대로 검증 자산으로 삼았다. 첫째, **결정적 repro 플립**: Grace의 최소 인스턴스에서 floor가 수정 전 orient 2@(16,15)→infeasible이던 것이 수정 후 orient 6@(1,0)→feasible(stage 5)로 바뀐다(normal·fast-finish 양쪽). 둘째, **게이트가 회귀를 잠근다**: `tools/floor_gate.py:_check_fp_boundary`가 그 결정적 repro와 분수 re-anchor sweep(9 인스턴스 × 3 패턴)을 건다 — 수정본에선 통과하고, 수정을 되돌리면(15 코드) repro가 `INFEAS(S2)`로 *실패해 게이트가 exit 1*을 낸다(직접 확인). 셋째, **대량 분수 fuzz**: 40개 인스턴스 × 25 trial × 2 모드 = **2000회 분수 re-anchor floor 평가에서 0 실패**. 넷째, **10-페르소나 수렴 라운드**: 동일 적대 패널을 수정본에 다시 돌려(round 2) FP 클래스 사멸과 잔여 −1 부재를 확인한다. 기존 게이트(40 train·proc==0·ref≠0·malformed)는 그대로 통과하고, ref=0(=모든 train)에선 `contains_block(placed)`가 정수 산술이라 옛 판정과 동일해 무회귀다.

한계는 정직히 둘이다. (1) 이 −1은 *분수 ref + extent가 베이 변과 ULP 차로 일치*라는 좁은 기하에서만 deterministic하게 난다 — red-team 추정으로 무작위 분수 re-anchor ~1/500, 정상 모드 무작위 sweep은 0. 숨김 인스턴스가 그 정확한 기하를 가질지는 알 수 없다. 다만 수정은 *모든* 분수 ref에 대해 floor 판정 = 검증기 판정을 보장하므로(특정 기하에 의존하지 않음) 클래스를 통째로 닫는다. (2) [15의 한계](./15-floor-ref-anchor.md)와 같이 구성기·래스터의 분수-ref 처리는 범위 밖이라, 그런 인스턴스는 자식이 self-reject하면 floor 품질에 머문다(feasibility는 보장).
