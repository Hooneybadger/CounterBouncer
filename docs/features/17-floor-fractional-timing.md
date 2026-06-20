# floor 분수 timing 올림: release/processing를 truncate가 아니라 ceil한다

- **state**: 측정완료 (방어적 강건화)
- **코드**: `src/myalgorithm.py:_ceil_int()` · `_guaranteed_place()` · `_safe_finish_place()` · `_guaranteed_solution()` · 회귀 게이트 `tools/floor_gate.py:_check_fractional_timing()`
- **관련 결정**: B1·P1(feasibility-first) — [16 floor FP 정합](./16-floor-fp-soundness.md)과 같은 round-2 red-team 산물
- **배경**: LEARNING_GUIDE F2 · [GLOSSARY의 빈-베이 윈도우](../GLOSSARY.md)
- **측정**: QA red-team round 2 · 분수 timing 게이트 · train timing 정수 전수 확인

## 한눈에

floor는 블록의 `release_time`·`processing_time`을 `int()`로 정수화해 entry·exit를 잡았다 — 그런데 `int()`는 *내림(truncation)*이다. `release_time=5.7`이면 `int(5.7)=5`라 floor가 entry=5를 내는데, 검증기는 `entry_time ≥ release_time`을 요구한다(`utils.py:1131`) → `5 < 5.7` → Stage-1 위반 → infeasible. 올바른 정수 entry는 `ceil(5.7)=6`이고, 그 자리에 두면 feasible하다. `processing_time`도 마찬가지로 `exit−entry ≥ processing_time`(`utils.py:1126`)을 truncation이 깬다. 이 변경은 두 timing을 `_ceil_int`(올림)로 잡아, *어떤 분수 timing이 들어와도* entry≥release·exit−entry≥proc를 만족시킨다. train의 timing은 전부 정수라 `ceil(5)=5=int(5)`로 무영향(무회귀)이지만, 숨김 인스턴스가 분수 timing을 주면 truncation은 −1이다.

## 왜 이 기능이 필요했나

[16](./16-floor-fp-soundness.md)의 FP 버그를 고친 뒤 동일 10-페르소나 패널을 수정본에 다시 돌린 *수렴 라운드(round 2)*에서, 한 페르소나가 red-team의 의무로 이 표면을 surface했다. 정직한 발견이었다 — feasibility 보존 변환(re-anchor·translate·scale-time·duplicate·permute)은 *정수 timing을 보존*하고(scale-time은 정수×정수 k), train 7500블록의 timing은 전수 검사 결과 **22500개 필드 전부 정수**라, 이 −1은 그 과제의 known-feasible 입력에서 *도달 불가*하며 triage가 "진짜 버그 아님"으로 분류했다(round 2 최종 verdict: 진짜 버그 0).

그럼에도 고친 이유는 [ref-anchor 버그](./15-floor-ref-anchor.md)와 *정확히 같은 계열*이기 때문이다 — "train이 늘 X이므로 숨김도 X"라는 *훈련-속성 가정*. ref의 경우 train 좌표에 분수 정점이 694124개나 있어 분수 ref가 그럴듯했고 실제로 −1을 냈다. timing은 train에 분수가 0개라 *증거는 더 약하지만*, (1) 재현되는 실제 infeasibility 표면이고(분수 release_time=5.7 → 직접 −1 확인), (2) 수정이 *공짜이자 무해*하며(정수 timing엔 `ceil=int`라 floor 출력 바이트 동일), (3) 검증 없이 반환되는 floor가 −1의 급소라(feasibility-first), 틀렸을 때의 비용(−1)이 고칠 때의 비용(2글자)을 압도한다. 시니어 판단: 증거가 약해도 *공짜이고 무회귀인 강건화*는 채택한다.

## 하는 일과 내부 동작

`_ceil_int(v)`(`src/myalgorithm.py`)가 `math.ceil(v or 0)`로 올리고, 숫자가 아니면 0으로 안전 폴백한다(malformed timing에도 crash 없음). floor의 모든 timing 진입점 — `_guaranteed_place`·`_safe_finish_place`의 `r_time`·`proc`, `_guaranteed_solution`의 fast-finish·예외 폴백 — 여덟 곳이 `int()` 대신 이 함수를 쓴다. `proc`는 `max(1, _ceil_int(processing_time))`로 [proc=0 봉인](./13-floor-scale-hardening.md)을 유지한다(`ceil(0)=0 → max(1,0)=1`). entry는 빈-베이 윈도우가 `r_time` 이후를 보장하므로 `entry ≥ ceil(release) ≥ release`이고, `exit = entry + proc = entry + ceil(processing) → exit−entry ≥ processing`이다. 검증기에 makespan 제약이 없어(features/15에서 확인) exit가 조금 늦어도 feasibility엔 무해하고 tardiness(목적값)만 미세 증가한다 — 안전망에선 정당한 트레이드오프다. `_utilization`의 `int(processing_time)`(혼잡도 *지표*, 자식 모드 게이트용)은 feasibility 경로가 아니라 그대로 둔다.

## 버린 선택지들

**고치지 않고 두는 길**(round 2가 "진짜 버그 아님"으로 분류했으니)도 진지하게 고려했다. 버린 이유는 위 "왜"의 셋 — 재현되는 표면 + 공짜·무회귀 + floor의 −1 급소성. **반올림(round)으로 잡는 길**은 틀렸다 — `round(5.4)=5 < 5.4`라 여전히 release를 어긴다. 경계 제약을 *만족시키는* 방향은 올림뿐이다. **검증기 tolerance(1e-6)에 기대는 길**도 버렸다 — 그건 [13의 epsilon 함정](./13-floor-scale-hardening.md)과 같아, `5 < 5.7−1e-6`이라 어차피 못 막는다.

## 언제·어디서 작동하나

floor가 발동하는 모든 경로의 timing 계산에서 작동한다. 정수 timing(=모든 train)에선 `ceil=int`라 완전 무영향(no-op). 분수 timing 입력에서만 동작이 갈린다. 자식 결과 경로는 무관하다 — 자식은 `check_feasibility` 통과분만 내보내므로 분수 timing을 잘못 처리하면 self-reject되어 floor로 떨어지고, 그 floor가 이제 올바르다.

## 검증과 한계

**재현 플립**: `release_time=5.7`(+ 0.1·10.999 변형)에서 floor가 수정 전 entry=5→Stage-1 infeasible이던 것이 수정 후 entry=6→feasible(stage 5)로 바뀐다(normal·fast-finish). **게이트 잠금**: `tools/floor_gate.py:_check_fractional_timing`이 알려진-feasible 인스턴스(7개)에 분수 release/proc를 주입해 floor feasibility를 요구한다 — 수정본은 통과, 되돌리면(features/15 truncation) `INFEAS(S1)`로 *게이트 exit 1*(직접 확인). **무회귀**: train timing 전수 정수(22500/22500) → 현재 floor 출력이 features/15와 **80/80 바이트 동일**. 기존 게이트 전 항목 통과.

한계는 정직히: 이 −1은 *분수 timing 입력*에서만 난다. train에 분수 timing이 0개라 [16의 FP 버그](./16-floor-fp-soundness.md)·[15의 ref 버그](./15-floor-ref-anchor.md)보다 도달 가능성이 *낮다*(그 둘은 train에 분수 좌표가 실재했다). 즉 "확인된 도달 가능 버그"가 아니라 *방어적 강건화*다 — 같은 훈련-속성 가정 계열의 사각을, 공짜이고 무회귀라 선제적으로 닫았다.
