# floor 스케일·경계 강건화: 메인의 마지막 무경계 작업을 없앤다

- **state**: 측정완료
- **코드**: `src/myalgorithm.py:_empty_bay_entry_fast()` · `_guaranteed_place()` · `_guaranteed_solution()` · `_origin_fit()`
- **관련 결정**: B1·P1(feasibility-first) — [11 supervisor](./11-supervisor-feasibility.md)의 후속(메인 무경계 작업 제거의 마지막 조각)
- **배경**: LEARNING_GUIDE F2 · [GLOSSARY의 빈-베이 윈도우](../GLOSSARY.md)
- **측정**: `results/v102_2s/` · `results/v102_scale/` · `results/v12p1_full_60s_j1/`(무회귀)

## 한눈에

floor(`_guaranteed_solution`)는 −1을 막는 우리의 마지막 안전망인데, 그 floor 자체가 큰 인스턴스에서 −1을 낼 수 있었다. 블록수에 거의 세제곱으로 폭발(900블록 floor가 15초)해 메인이 제한시간 안에 못 돌아왔기 때문이다. 이 기능은 두 가지를 고친다 — (1) floor를 거의 선형으로 낮추고(900블록 15s→0.03s) deadline을 줘 무조건 시간 안에 반환하게 하며, (2) floor의 경계 검사를 평가 서버의 검증기와 *정확히* 맞춰 경계에 걸치는 블록이 floor를 통과하고 검증기에 거절당해 −1 나는 구멍을 막는다. [supervisor](./11-supervisor-feasibility.md)가 구성·ALNS를 자식으로 빼 메인을 hard-bounded로 만들었지만 floor만은 메인에 남아 있었는데, 이 변경이 그 마지막 무경계 작업까지 없앤다.

## 왜 이 기능이 필요했나

학습 인스턴스는 블록이 최대 300개라 floor가 0.5초면 끝나 한 번도 문제가 안 됐다. 그러나 [과적합 금지 원칙](../../CLAUDE.md)에 따라 train 범위를 넘겨 스트레스했더니 floor가 초선형으로 폭발했다 — prob_20을 복제해 측정한 결과 300블록 0.52초, 600블록 4.35초, **900블록 15.05초**다. floor는 `algorithm()`에서 `return_cap`(0.93×timelimit) 검사보다 *먼저*, 시간 한계 없이 메인에서 직접 돈다. 그래서 floor 시간이 0.93×timelimit을 넘으면 메인이 제때 못 돌아와 −1이다 — 900블록·10초 게이트에서 정확히 그렇다. 이건 [P3 −1](./11-supervisor-feasibility.md)과 같은 실패 모드이고, 이번엔 *스케일*이 방아쇠다. private 인스턴스가 공개분과 "비슷한 난이도"라도 블록이 2~3배면 충분히 일어난다.

원인은 `_empty_bay_entry`(baseline 헬퍼)가 베이 스케줄 길이에 대해 `while changed` 재시작 루프라 O(m²)이고, `_guaranteed_place`가 이걸 *블록마다 × 베이마다 × 방향마다* 부른다는 데 있다. 방향 루프 안의 호출은 entry가 방향과 무관한데도 중복돼 n_orient배(최대 8배) 낭비였다.

두 번째 구멍은 경계 검사의 허용 오차다. floor의 `_origin_fit`은 `px + bb[2] <= width + 1e-6`으로 1e-6을 더 허용했는데, 검증기 `Bay.contains_block`은 `bb[2] <= width`로 무허용이다. px+bb[2]는 검증기의 bounding_rect[2]와 같은 값이므로(둘 다 모든 층을 같은 ref로 평행이동), 경계에 sub-eps 걸치는 블록을 floor는 통과시키고 검증기는 거절한다 → floor가 −1. train은 경계에 딱 걸치는 블록이 없어 안 드러났을 뿐이다.

## 하는 일과 내부 동작

`_empty_bay_entry_fast`는 시작시각으로 정렬된 슬롯을 한 번만 훑어 같은 값(빈-베이 윈도우의 가장 빠른 entry)을 O(m)에 낸다. 정렬 단일 패스가 원본의 while-changed와 일치하는 이유는, 슬롯이 시작순이라 entry를 앞으로만 밀며 한 번 훑으면 최종 윈도우와 겹칠 수 있는 모든 슬롯을 이미 보기 때문이다. `_guaranteed_solution`은 베이별 스케줄을 `bisect.insort`로 시작시각 정렬로 유지해 이 전제를 만족시키고, `_guaranteed_place`는 entry를 *베이당 한 번*만 계산한다(방향 무관이라 첫 적합 방향이면 충분 — entry·sort_key가 방향과 무관해 결과는 원본과 동일하다). 이 둘로 floor가 거의 선형이 된다: 900블록 0.032초, 1800블록 0.106초.

거기에 `_guaranteed_solution`은 deadline을 받아, 64블록마다 잔여 시간을 보고 부족하면 *남은 블록을 즉시 단순 직렬 윈도우로 마감*한다(베이별 마지막 exit만 추적해 블록당 O(베이)). 그래서 아무리 큰 인스턴스라도 메인은 `return_cap` 안에 완전한 feasible operations를 낸다 — [supervisor](./11-supervisor-feasibility.md)가 구성에 한 일을 floor에도 적용해 메인의 마지막 무경계 작업을 없앤 것이다.

경계 쪽은 `_origin_fit`의 `+1e-6`을 제거해 검증기와 정확히 같은 판정을 하게 했고, 어떤 (베이,방향)도 안 맞는 `best is None` 극단(=사실상 배치 불가 블록)에선 orient 0 고정 대신 *경계 초과가 가장 작은* (베이,방향)을 고른다 — 초과가 0이면 실제로 feasible해진다.

## 버린 선택지들

`_empty_bay_entry`를 baseline_greedy.py에서 직접 고치는 길도 있었지만, 그건 구성기의 `_fallback_place`와 공유돼 blast radius가 넓다. floor의 −1 위험만 정확히 겨냥하려고 myalgorithm.py 안에 빠른 헬퍼를 두고 baseline 헬퍼는 건드리지 않았다(구성기 동작 불변). 구성기/자식 쪽의 스케일(900블록 scan 구성이 51초)은 별개 문제인데, 이건 자식이 supervisor에 묶여 −1이 아니라 *품질* 저하(큰 인스턴스서 floor급 해)라 v1.2.0 품질 항목으로 미뤘다 — `best is None` 자체도 인스턴스가 본질적으로 infeasible할 때만 트리거돼 −1을 *막지는* 못하므로(그땐 −1이 정답), least-overflow는 방어적 정돈으로만 둔다.

## 언제·어디서 작동하나

`algorithm()`이 floor를 만들 때마다(메인, 매 호출) 작동한다. 복잡도 개선은 모든 인스턴스에 적용되고, deadline fast-finish는 floor가 `return_cap`을 위협하는 초대형에서만 발화한다. 경계 정렬은 floor가 배치하는 모든 블록에 적용되되, 경계에 걸치지 않는 블록(대다수)에는 무영향이다.

## 검증과 한계

train 40개 floor를 측정해 sum_obj가 25,488,553,408로 변경 전과 **byte 단위 동일**, feasible 40/40임을 확인했다(`_empty_bay_entry_fast`는 결과 불변, 경계 정렬은 train에 걸치는 블록이 없어 무영향). 전체 파이프라인 무회귀는 `results/v12p1_full_60s_j1/`(vs v1.0.1)에서 40/40 feasible·순위 시뮬 76:76 동률로 확인했다(floor 변경은 train 최적화 경로에 무영향이라 차이는 [ALNS](./06-alns.md) 잡음). 스케일은 합성(prob_20 복제)으로 실측 — floor가 900블록 15.05s→0.032s, 1800블록 0.106s로 내려가 −1 경계가 사라졌고, end-to-end로 600·900블록을 10초에 feasible 반환한다(`results/v102_scale/`, v1.0.1은 900블록서 −1). 경계 엣지는 폭 10.0000005 블록을 폭 10 베이에 넣어 floor가 검증기와 똑같이 거절함을 확인했다. 남은 한계는 큰 인스턴스의 *품질* — floor는 빠르고 feasible하나 직렬 배치라 지각이 크고, 구성기의 scan이 큰 인스턴스서 느려 자식이 좋은 해를 못 낸다(v1.2.0 과제). 그러나 −1은 어떤 스케일에서도 구조적으로 없다.
