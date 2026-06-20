# floor reference-point 경계 정합: 검증기 기하를 직접 호출해 ref≠(0,0) −1을 없앤다

- **state**: 측정완료
- **코드**: `src/myalgorithm.py:_ref_bbox()` · `_orient_corners()` · `_origin_fit()` · `_min_overflow_place()` · `_guaranteed_place()` · `_safe_finish_place()` · 회귀 게이트 `tools/floor_gate.py`
- **관련 결정**: B1·P1(feasibility-first) — [13 floor 스케일·경계 강건화](./13-floor-scale-hardening.md)의 후속이자 *정정*, [11 supervisor](./11-supervisor-feasibility.md)의 계열
- **배경**: LEARNING_GUIDE F2 · [GLOSSARY의 빈-베이 윈도우](../GLOSSARY.md)
- **측정**: `results/v13_base/`(기준, 수정 전 60s) vs `results/fix13_ref_correct/`(무회귀) · ref≠(0,0) 합성 게이트

## 한눈에

제출 v1.2.1은 [13](./13-floor-scale-hardening.md)의 floor 경계 수정을 이미 담고 있었는데도 서버에서 숨김 P3가 *여전히* infeasible로 돌아왔다. 13은 floor의 경계 판정을 검증기와 "정확히" 맞췄다고 적었지만, 한 가지 가정을 남겨 두었다 — **블록의 reference point(첫 층 첫 정점)가 (0,0)이라는 가정**이다. 검증기는 모든 정점을 ref만큼 평행이동해 배치를 읽는데(`utils.py:308`), floor의 `_block_bbox`는 그 평행이동을 생략하고 ref=(0,0)을 전제했다. train의 57560개 방향이 *전부* ref=(0,0)이라 세 버전 동안 이 가정이 우연히 맞아 떨어졌을 뿐이다. 숨김 인스턴스의 한 방향이라도 ref≠(0,0)이면 floor는 블록을 ref만큼 어긋나게 놓아 경계 밖으로 밀어내고, 검증 없이 반환되는 floor가 그대로 −1을 낸다. 이 변경은 floor의 기하 계산을 *검증기 자신의 `Block.bounding_rect()`로 대체*해 가정을 제거하고(어떤 ref에도 검증기와 일치), 그 정확성을 ref≠(0,0)·malformed·fast-finish를 강제로 만들어 검증기로 때리는 회귀 게이트로 제출 전에 못박는다.

## 왜 이 기능이 필요했나

신호는 제출 피드백이었다. v1.2.1(=13의 (0,0)·스케일 수정 포함)이 P1·P2·P4·P5·P6은 feasible 목적값을 받았는데 **P3만 "infeasible"**로 분류됐다. 조직위 FAQ상 "infeasible"은 `crashed or killed`(시간 초과·세그폴트)와도 `algo_error`(예외)와도 다른 버킷이다 — *해는 반환됐고 검증기가 그 해를 거절했다*는 뜻이다. 시간 가드와 [supervisor](./11-supervisor-feasibility.md)는 작동했고(시간 초과 아님), 크래시·예외도 아니다. 그리고 자식 결과는 `_improve`가 `check_feasibility` 통과분만 내보내는데(`src/myalgorithm.py:385`), 문제 갱신이 없어 로컬 검증기 = 서버 검증기이므로 *자식 결과가 반환됐다면 서버에서도 feasible*이어야 한다. 소거법이 한 곳을 가리켰다 — **P3는 floor를 반환했고, floor가 검증 없이 나가 −1을 냈다**(P3는 전체 167건 중 60건이 실패한, 느리고 큰 인스턴스라 자식이 제때 결과를 못 주면 floor로 떨어진다).

floor가 well-formed feasible 인스턴스에서 −1을 낼 수 있는 자리를 코드에서 좁히니, 경계 판정과 검증기의 정합이 유일하게 남은 의심이었다. 검증기 `Block.__post_init__`은 정점을 `(x - ref_x, y - ref_y)`만큼 옮겨(`utils.py:308-312`, ref=첫 층 첫 정점) 배치를 해석하고 `Bay.contains_block`이 그 ref 보정된 bbox로 경계를 본다(`utils.py:262`). 반면 floor의 `_block_bbox`(baseline 헬퍼)는 ref 보정을 생략한다. train 40개 인스턴스 7500블록 57560방향을 전수 검사하니 첫 정점이 (0,0)이 아닌 방향은 **0개**였다 — 가정이 train에선 100% 맞지만 *데이터에 대한 검증되지 않은 가정*이지 floor가 보장하는 불변식이 아니다. 직접 재현했다: train 블록 하나를 (5,5)만큼 재정렬(모든 정점에 상수를 더해 형상은 그대로, ref만 (5,5)로 이동)하면 검증기는 같은 월드 배치로 읽어 *인스턴스는 여전히 feasible*인데, 현재 floor는 그 블록을 경계 밖에 놓아 `Stage2: block exceeds bay boundary`로 거절당한다. 모든 shift 크기(5·50·500)와 normal·fast-finish 양쪽에서 재현됐다. v1.0.0이 train 네 게이트를 다 통과하고도 숨김 P3에서 −1을 받은 것과 같은 계열의 사각 — train 커버리지 ≠ 정확성이다.

## 하는 일과 내부 동작

핵심은 floor가 기하를 *직접 복제*하지 않고 *검증기 코드를 호출*하게 만든 것이다. `_ref_bbox(blk_data, oi)`는 블록을 (0,0)에 놓은 검증기 `Block(0, blk_data, 0, 0, oi).bounding_rect()`를 돌려준다 — 이 값이 곧 ref 보정된 로컬 bbox다(검증기가 정점을 `-ref`만큼 옮기므로). 손으로 ref를 빼는 식을 다시 적지 않는 이유는, *바로 그 손계산이 13에서 ref 항을 빠뜨려 이 버그를 만들었기* 때문이다. 정전(canonical) 코드를 호출하면 어떤 ref에도 검증기와 정의상 일치한다. `_origin_fit`은 이 bbox로 `px=max(0,ceil(-bb[0]))`, `py=max(0,ceil(-bb[1]))`를 잡고 `px+bb[2]≤width ∧ py+bb[3]≤height`를 본다 — 이 네 부등식이 정확히 placed block의 `contains_block`이다(월드 bbox = `_ref_bbox`+(px,py), 좌·하 경계는 px·py 선택이 자명 충족). 방향별 bbox·코너는 베이와 무관하므로 `_orient_corners`가 블록당 한 번만 계산해 베이 루프에서 O(1)로 비교한다(옛 코드의 베이마다 재계산을 없애 비용은 오히려 같거나 낮다).

배치 함수들은 이 정합 위에서 *예외에 강건하고 (0,0)을 절대 쓰지 않게* 다시 짰다. `_guaranteed_place`(빈-베이 윈도우)와 `_safe_finish_place`(fast-finish 직렬)는 코너가 드는 첫 (베이,방향)을 쓰고, 어디에도 안 들면 `_min_overflow_place`로 *경계 초과가 가장 작은* 배치를 고른다(초과 0이면 실제 feasible). 읽히는 블록이 (0,0)·orient 0으로 떨어지던 옛 예외 경로 두 곳(`_guaranteed_solution`의 fast-finish 폴백과 정상 폴백)을 제거했다 — (0,0)은 음수 min-corner 블록을 경계 밖에 놓는 또 다른 −1 표면이었다. 이제 (0,0)은 *기하를 전혀 못 읽는* 블록(=표현 불가, 인스턴스가 본질적으로 infeasible)에만 닿고, 그 경우엔 어떤 위치도 손해를 줄이지 못한다.

정확성을 *못박는* 책임은 런타임이 아니라 게이트에 둔다. floor는 검증 없이 반환될 수 있는 유일한 해라 "반환 직전 `check_feasibility`로 때리는" 런타임 방어선이 자연스러워 보이고 실제로 처음엔 그렇게 넣었지만, 측정 끝에 뺐다(아래 '버린 선택지들'). 대신 `tools/floor_gate.py`가 모든 train 인스턴스의 floor를 *제출 전에* 검증기로 때린다 — 로컬 검증기 = 서버 검증기(문제 미갱신)라 게이트를 통과한 구성 로직은 서버서도 feasible이다. 게이트는 정상·fast-finish·proc==0에 더해 **ref≠(0,0) 재정렬**과 **malformed 형상**을 강제로 만들어, train이 자연히 못 내는 구조까지 floor에 들이민다. 검증을 런타임에서 빼도 feasibility가 흔들리지 않는 이유는, floor의 feasibility가 *구성의 정확성*(ref 보정된 코너 = `contains_block`)으로 보장되고 그 정확성을 게이트가 잠그기 때문이다.

## 버린 선택지들

**손으로 ref 항을 더해 `_block_bbox`를 고치는 길**은 가장 작은 패치였지만 버렸다. 13이 이미 `_block_bbox` 기반 경계 식을 손으로 "검증기와 정확히 맞췄다"고 적고도 ref 항을 빠뜨렸다 — 같은 함정을 반복할 위험이 있고, `_resolve_layers`·빈 층 처리·degenerate 폴백 같은 검증기의 세부와 또 어긋날 수 있다. 검증기 `Block`을 직접 호출하면 이 모든 세부가 정의상 일치한다. **검증만 추가하고 floor 기하는 그대로 두는 길**도 버렸다 — 검증이 실패를 *로그*할 뿐 floor가 여전히 −1을 내면 막지 못한다(더 나은 폴백이 없다). 근본을 고쳐야 한다. **런타임 인라인 검증(반환 직전 `check_feasibility`)**은 처음 넣었다가 측정 후 뺐다 — 자식 결과는 이미 self-check를 거치고 floor는 구성으로 정확하므로 런타임 검증은 *새 정보를 안 주고*, 로그뿐이라 서버서 관측도 안 되며(더 나은 폴백도 없다), 메인의 fork 전 시간을 잡아먹는다(250블록 floor check 27~40ms). prob_18을 동일 조건 3회씩 옛·새 코드로 재면 정확히 *바이트 동일*(`[85088, 100066, 104909]`)이라 그 비용이 무해함을 보였지만, 검증의 책임은 관측·조치 가능한 **게이트**가 맡는 게 옳아 런타임에선 들어냈다. **모든 블록을 베이를 가로질러 전역 직렬화하는 초보수 floor**는 검증기의 entry·exit·충돌 검사가 *베이별*이라(같은 베이 안에서만 obstruction을 본다, `utils.py:1173·1217·1268`) 베이별 배타 윈도우 이상의 feasibility를 주지 못해 불필요하다 — 베이별 배타 윈도우가 이미 구조적으로 최강의 안전망이다.

## 언제·어디서 작동하나

ref 정합과 (0,0) 제거는 floor가 발동하는 *모든* 경로에서 작동한다 — 정상 빈-베이 윈도우, fast-finish 직렬, 그리고 예외 폴백. 검증은 런타임이 아니라 `tools/floor_gate.py`(제출 전 관문)에서 돈다. 자식 결과 경로는 건드리지 않았다 — 자식은 `_improve`가 이미 `check_feasibility` 통과분만 내보내 서버-feasible이 보장된다(ref≠0 블록을 자식이 잘못 놓으면 자식의 self-check가 거절해 그 자식은 결과를 못 내고, 그래서 floor로 떨어진다). 이 변경은 그 floor 경로 하나를 정확하게 만든다.

## 검증과 한계

네 층으로 정당화했다. 첫째, **무회귀가 구조적으로 보장**된다: ref=(0,0)인 모든 train 방향에서 새 `_ref_bbox`가 옛 `_block_bbox`와 *바이트 동일*함을 57560개 전수 확인했다(불일치 0) — train에서 floor 출력이 한 비트도 바뀌지 않고, 자식 경로는 무수정이며 런타임 인라인 검증도 들어냈으므로(위), 새 코드는 ref=0(=모든 train)에서 옛 코드와 *같은 실행 경로*다. feasible→infeasible 회귀가 원천적으로 불가능하다. 둘째, **게이트가 빨강→초록**이다: `tools/floor_gate.py`에 ref≠(0,0) 재정렬 합성(작은·큰 인스턴스 × 세 shift 패턴 × normal·fast-finish)과 malformed 형상(no-shape·empty-layers·no-proc 등) 합성을 추가했다. 수정 전 코드에선 ref≠0 케이스가 *전부* `INFEAS(S2)`로 실패하고, 수정 후엔 *전부* 통과한다(malformed는 crash 없이 완전한 정수 operations). 기존 40개 train floor·proc==0 게이트도 그대로 통과한다. 셋째, **batch_runner 60s feasibility 무회귀**: `results/v13_base/`(수정 전) 대비 `results/fix13_ref_correct/`에서 valid 40/40 → 40/40, feasible→infeasible 퇴보 0건. 넷째, **목적값 무회귀를 통제 측정으로 확인**: 60s 4-job 비교에서 보인 9개 목적값 차이는 *인스턴스 간 경합 노이즈*다 — 같은 코드를 j=2로 3회씩 돌리면 prob_18이 23.3% 폭으로 튀고(85k~105k), 옛·새 코드를 동일 조건에서 맞대면 prob_18은 세 회 모두 *바이트 동일*, prob_23은 범위가 겹친다. v13_base의 낮은 수치는 옛 코드를 *오늘* 다시 돌려도 안 나오므로(다른 조건의 run) 품질 기준으로 부적합하다. 정확한 품질 측정은 [throttling 규율](../../CLAUDE.md)대로 `systemd-run 400%·1개씩`이 필요하다.

남은 한계는 정직히 둘이다. (1) 숨김 P3 자체를 가질 수 없어 *그 인스턴스에서의* 수정을 직접 확인할 수는 없다 — 재현은 P3와 *같은 구조*(ref≠0)를 합성해 증명한 것이고, "floor가 우리 check를 무조건 통과한다 + 로컬=서버 check"라는 사슬로 −1 제거를 보인다. (2) ref≠0 블록에 대해 *자식*은 여전히 self-reject할 수 있어(구성기·래스터의 ref 처리는 이번 범위 밖) 그런 인스턴스는 floor 품질에 머문다 — feasibility는 보장되나 품질 개선은 별도 작업이다. 구성기·래스터의 ref 일반화는 품질 레버로 후속에 남긴다.
