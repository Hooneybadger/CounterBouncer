# floor 스케일·경계 강건화: 메인의 마지막 무경계 작업을 없앤다

- **state**: 측정완료
- **코드**: `src/myalgorithm.py:_empty_bay_entry_fast()` · `_guaranteed_place()` · `_safe_finish_place()` · `_guaranteed_solution()` · 회귀 게이트 `tools/floor_gate.py`  (★당시의 `_origin_fit`은 [15](./15-floor-ref-anchor.md)·[16](./16-floor-fp-soundness.md)에서 `_orient_corners`/`_placed_corner`로 대체됨 — 아래 본문은 그 시점 기준)
- **관련 결정**: B1·P1(feasibility-first) — [11 supervisor](./11-supervisor-feasibility.md)의 후속(메인 무경계 작업 제거의 마지막 조각)
- **배경**: LEARNING_GUIDE F2 · [GLOSSARY의 빈-베이 윈도우](../GLOSSARY.md)
- **측정**: `results/v102_2s/` · `results/v102_scale/` · `results/v12p1_full_60s_j1/`(무회귀)

## 한눈에

floor(`_guaranteed_solution`)는 −1을 막는 우리의 마지막 안전망인데, 정작 그 floor 자체가 큰 인스턴스에서 −1을 냈다. 블록수에 거의 세제곱으로 폭발(900블록 floor가 15초)해 메인이 제한시간 안에 돌아오지 못했기 때문이다. 이 기능은 두 가지를 고친다. 하나는 floor를 거의 선형으로 낮추고(900블록 15s→0.03s) deadline을 줘 무조건 시간 안에 반환하게 한 것이고, 다른 하나는 floor의 경계 검사를 평가 서버의 검증기와 *정확히* 맞춰 경계에 걸치는 블록이 floor를 통과한 뒤 검증기에 거절당해 −1 나는 구멍을 막은 것이다. [supervisor](./11-supervisor-feasibility.md)가 구성·ALNS를 자식으로 빼 메인을 hard-bounded로 만들었지만 floor만은 메인에 남아 있었다. 이 변경이 그 마지막 무경계 작업까지 없앤다.

## 왜 이 기능이 필요했나

학습 인스턴스는 블록이 최대 300개라 floor가 0.5초면 끝나, 한 번도 문제가 되지 않았다. 그러나 [과적합 금지 원칙](../../CLAUDE.md)에 따라 train 범위를 넘겨 스트레스했더니 floor가 초선형으로 폭발했다. prob_20을 복제해 측정하니 300블록 0.52초, 600블록 4.35초, **900블록 15.05초**다. floor는 `algorithm()`에서 `return_cap`(0.93×timelimit) 검사보다 *먼저*, 시간 한계 없이 메인에서 직접 돈다. 그래서 floor 시간이 0.93×timelimit을 넘으면 메인이 제때 돌아오지 못해 −1이다. 900블록·10초 게이트에서 정확히 그렇다. [P3 −1](./11-supervisor-feasibility.md)과 같은 실패 모드인데, 이번엔 방아쇠가 *스케일*이다. private 인스턴스가 공개분과 "비슷한 난이도"라도 블록이 2~3배면 충분히 일어난다.

원인은 `_empty_bay_entry`(baseline 헬퍼)가 베이 스케줄 길이에 대해 `while changed` 재시작 루프라 O(m²)이고, `_guaranteed_place`가 이걸 *블록마다 × 베이마다 × 방향마다* 부른다는 데 있다. 방향 루프 안의 호출은 entry가 방향과 무관한데도 중복돼 n_orient배(최대 8배) 낭비였다.

두 번째 구멍은 경계 검사의 허용 오차다. floor의 `_origin_fit`은 `px + bb[2] <= width + 1e-6`으로 1e-6을 더 허용했는데, 검증기 `Bay.contains_block`은 `bb[2] <= width`로 무허용이다. px+bb[2]는 검증기의 bounding_rect[2]와 같은 값이라(둘 다 모든 층을 같은 ref로 평행이동), 경계에 sub-eps 걸치는 블록을 floor는 통과시키고 검증기는 거절한다 → floor가 −1. train은 경계에 딱 걸치는 블록이 없어 드러나지 않았을 뿐이다.

## 하는 일과 내부 동작

`_empty_bay_entry_fast`는 시작시각으로 정렬된 슬롯을 한 번만 훑어 같은 값(빈-베이 윈도우의 가장 빠른 entry)을 O(m)에 낸다. 정렬 단일 패스가 원본의 while-changed와 일치하는 이유는, 슬롯이 시작순이라 entry를 앞으로만 밀며 한 번 훑으면 최종 윈도우와 겹칠 수 있는 모든 슬롯을 이미 보기 때문이다. `_guaranteed_solution`은 베이별 스케줄을 `bisect.insort`로 시작시각 정렬로 유지해 이 전제를 만족시키고, `_guaranteed_place`는 entry를 *베이당 한 번*만 계산한다(방향 무관이라 첫 적합 방향이면 충분하다 — entry·sort_key가 방향과 무관해 결과는 원본과 같다). 이 둘로 floor가 거의 선형이 된다: 900블록 0.032초, 1800블록 0.106초.

거기에 `_guaranteed_solution`은 deadline을 받아, 64블록마다 잔여 시간을 보고 부족하면 *남은 블록을 즉시 단순 직렬 윈도우로 마감*한다(베이별 마지막 exit만 추적해 블록당 O(베이)). 그래서 아무리 큰 인스턴스라도 메인은 `return_cap` 안에 완전한 feasible operations를 낸다. [supervisor](./11-supervisor-feasibility.md)가 구성에 한 일을 floor에도 적용해 메인의 마지막 무경계 작업을 없앤 셈이다.

경계 쪽은 `_origin_fit`의 `+1e-6`을 제거해 검증기와 정확히 같은 판정을 하게 했다. 어떤 (베이,방향)도 맞지 않는 `best is None` 극단(=사실상 배치 불가 블록)에선 orient 0 고정 대신 *경계 초과가 가장 작은* (베이,방향)을 고른다. 초과가 0이면 실제로 feasible해진다.

## 버린 선택지들

`_empty_bay_entry`를 baseline_greedy.py에서 직접 고치는 길도 있었지만, 그건 구성기의 `_fallback_place`와 공유돼 blast radius가 넓다. floor의 −1 위험만 정확히 겨냥하려고 myalgorithm.py 안에 빠른 헬퍼를 두고 baseline 헬퍼는 건드리지 않았다(구성기 동작 불변). 구성기/자식 쪽의 스케일(900블록 scan 구성이 51초)은 별개 문제인데, 이건 자식이 supervisor에 묶여 −1이 아니라 *품질* 저하(큰 인스턴스서 floor급 해)라 v1.2.0 품질 항목으로 미뤘다. `best is None` 자체도 인스턴스가 본질적으로 infeasible할 때만 트리거돼 −1을 *막지는* 못하므로(그땐 −1이 정답), least-overflow는 방어적 정돈으로만 둔다.

## 언제·어디서 작동하나

`algorithm()`이 floor를 만들 때마다(메인, 매 호출) 작동한다. 복잡도 개선은 모든 인스턴스에 적용되고, deadline fast-finish는 floor가 `return_cap`을 위협하는 초대형에서만 발화한다. 경계 정렬은 floor가 배치하는 모든 블록에 적용되되, 경계에 걸치지 않는 블록(대다수)에는 영향이 없다.

## 검증과 한계

train 40개 floor를 측정해 sum_obj가 25,488,553,408로 변경 전과 **byte 단위 동일**, feasible 40/40임을 확인했다(`_empty_bay_entry_fast`는 결과 불변, 경계 정렬은 train에 걸치는 블록이 없어 무영향). 전체 파이프라인 무회귀는 `results/v12p1_full_60s_j1/`(vs v1.0.1)에서 40/40 feasible·순위 시뮬 76:76 동률로 확인했다(floor 변경은 train 최적화 경로에 무영향이라 차이는 [ALNS](./06-alns.md) 잡음이다). 스케일은 합성(prob_20 복제)으로 실측했다 — floor가 900블록 15.05s→0.032s, 1800블록 0.106s로 내려가 −1 경계가 사라졌고, end-to-end로 600·900블록을 10초에 feasible 반환한다(`results/v102_scale/`, v1.0.1은 900블록서 −1). 경계 엣지는 폭 10.0000005 블록을 폭 10 베이에 넣어 floor가 검증기와 똑같이 거절함을 확인했다. 남은 한계는 큰 인스턴스의 *품질*이다 — floor는 빠르고 feasible하나 직렬 배치라 지각이 크고, 구성기의 scan이 큰 인스턴스서 느려 자식이 좋은 해를 내지 못한다(v1.2.0 과제). 그러나 스케일이 floor *시간*을 위협해 내던 −1은 구조적으로 없앴다 — 다만 이 fast-finish가 남은 블록을 `(0,0)`에 놓던 두 번째 구멍이 있었고(이 문서를 쓸 땐 못 봤다), 그것이 숨김 P3의 진짜 −1이었다. 아래 후속에서 닫는다.

## 후속: fast-finish의 (0,0) 배치가 낸 숨은 −1 — 숨김 P3 근본 수정

바로 위에서 deadline fast-finish가 "아무리 큰 인스턴스라도 메인은 `return_cap` 안에 완전한 feasible operations를 낸다"고 적었다. *완전한*은 맞았지만 *feasible*은 틀렸다. fast-finish가 남은 블록을 마감할 때 위치를 `(px,py)=(0,0)`·orient 0으로 고정했는데, 그 좌표가 대다수 블록에서 베이 경계 밖이다. 제출 피드백이 그것을 드러냈다 — v1.0.0부터 [supervisor](./11-supervisor-feasibility.md)·os.fork·이 문서의 스케일 강건화를 거친 v1.2.0까지, 숨김 인스턴스 P3가 *계속* infeasible이었다. timeout 가설로 세 번을 고쳤는데 P3는 꿈쩍도 안 했다. 그 자체가 가설이 틀렸다는 신호였다.

왜 `(0,0)`이 경계 밖인가. 블록은 회전 다각형이라 좌표가 실수이고, 로컬 bbox의 min-corner가 음수인 경우가 흔하다(train 전수 측정: 정점 57560개 중 음수 min 54264개). 검증기 `Block`은 reference point(=layers[0][0], 로컬 (0,0))를 월드 (x,y)에 놓으므로, `(0,0)`에 놓인 블록의 월드 min은 로컬 min 그대로 음수다 → `Bay.contains_block`의 `bb[0] >= 0` 위반 → Stage 2/4 경계 위반. 정상 경로의 `_origin_fit`은 `px=ceil(-bb[0])`로 이 음수를 정확히 상쇄해 월드 min≥0을 보장하는데, fast-finish는 그 시프트를 건너뛰고 `(0,0)`에 떨어뜨려 보장을 깬 것이다.

이 −1이 오래 안 보인 이유는 *로컬 게이트가 서버 조건을 재현하지 못해서*다. `batch_runner`는 taskset으로 코어를 *핀*하고(throttle 아님) `subprocess.Popen`으로 non-daemon 실행한다. 서버는 [firejail+cpulimit 400% throttle](../../CLAUDE.md)(코어는 보이나 총량 제한 → 죽지 않고 느려짐)에 daemon 프로세스다. fast-finish는 floor가 `return_cap`을 넘길 때만 발화하는데, throttle 없는 핀 환경에선 floor가 너무 빨라(900블록 0.03s) 한 번도 발화하지 않는다. 그래서 로컬 40개 게이트는 늘 통과했고 fast-finish의 `(0,0)`은 한 번도 실행되지 않았다. 서버에선 throttle된 큰 인스턴스 + 짧은 제한시간이 floor를 deadline 너머로 밀어 fast-finish→`(0,0)`→−1. P4·P5·P6가 통과하고 P3만 실패한 것도 이 그림과 맞는다 — 그 거대한 목적값들은 지각(obj1×w1, w1이 수만 규모)이 만든 값이라 *블록수가 많다는 뜻이 아니다*. P3가 블록수로 가장 큰 인스턴스라면 throttle 하에서 floor만 fast-finish에 걸린다.

수정은 fast-finish와 예외 경로의 `(0,0)`을 `_safe_finish_place`로 바꾼 것이다. 고정 좌표 대신 가장 빨리 비는 베이부터 `_origin_fit`으로 *실제로 드는* 방향·위치(ceil 시프트 포함)를 찾고, entry는 그 베이 tail(마지막 exit) 이후로 잡아 빈-베이 윈도우(무충돌·크레인 자유)를 보장한다. 베이별 O(orient)뿐이라 스케줄 스캔이 있는 정상 경로보다도 싸다 — fast-finish의 *속도* 목적을 지키면서 *feasibility*를 회복한다. 어느 베이·방향에도 정수 격자에서 안 드는 블록(=인스턴스 본질 infeasible)만 최소-경계-초과 배치로 떨어진다(그땐 −1이 정답이라 더 할 게 없다).

검증은 측정으로 못 박았다. fast-finish를 강제(deadline을 과거로)해 floor를 돌리면 수정 전 train 12/12 infeasible(전부 Stage2 경계 위반), 수정 후 **0/40**이다. 정상 경로는 40/40 feasible로 불변(무회귀, `results/fix_ff_t10/` 40/40 ok). end-to-end로도 `algorithm()`을 12000블록·2초(=floor가 반드시 fast-finish)에 돌려 1.91초에 feasible 반환을 확인했다(수정 전이라면 infeasible floor를 냈을 조건). 예외 경로도 `_guaranteed_place`를 1/3 확률로 인위 실패시켜 feasible 유지를 확인했다. 한계: 이 수정은 *feasibility*만 보장한다 — fast-finish가 발화한 초대형 인스턴스의 *품질*(직렬 배치라 지각 큼)은 여전히 별개 과제다. 그러나 floor는 이제 모든 경로에서 구조적으로 feasible하고, 직렬 floor는 베이당 공존 블록이 없어 Shapely 충돌 계산 자체가 없으므로(경계는 정수 산술) GEOS 버전과도 무관하게 robust하다. 더 깊은 교훈은 *로컬 게이트가 못 보는 실패는 영영 안 고쳐진다*는 것이다 — 다음 과제는 `batch_runner`에 daemon+throttle 모사를 넣어 이 류의 −1이 다시 숨지 못하게 하는 일이다.

## 재검토: (0,0) 수정은 옳다, 그러나 그게 서버 −1의 원인이라 단정하면 안 된다

위 (0,0) 수정을 원자단위로 다시 들여다본 결과, 두 가지가 분명해졌다 — 수정은 옳고, 동시에 그 수정만으로 숨김 −1이 사라졌다고 믿어선 안 된다. 먼저 수정의 정당성. 위 본문이 "12/12 infeasible"이라 적었지만 강제 fast-finish를 train 전수로 다시 돌리니 **40/40 전부 infeasible**(전부 Stage2 경계 위반)이었다 — 옛 `(0,0)` 경로가 도는 순간 *어떤* 인스턴스든 −1이었다는 뜻으로, 12/12는 과소표본이었다. 새 `_safe_finish_place`는 강제 fast-finish·정상 둘 다 **40/40 feasible**, 250블록 전부를 강제로 통과시켜도 3ms라 타이밍 회귀도 없다. 첫 정점이 로컬 `(0,0)`임은 57560/57560 방향 전수로 확인했고, 좌표는 정수가 아니라 회전 다각형 실수(예 `[3.9166, -0.3357]`)이며, floor의 경계 검사는 검증기와 **비트 단위로 동일**하다(`max(v)+px == max(v+px)`, eps 제거). 그래서 이 패치는 유지한다.

그런데 그 경로는 *유사 난이도 히든*에서 거의 안 켜진다. fast-finish는 normal floor가 `0.93×timelimit`(tl=10이면 9.3초)를 넘겨야 발화하는데, normal floor는 300블록에서 **5ms**다 — 발화하려면 train의 ~1,800배 규모가 필요하고, floor는 fork *이전*에 단독 실행이라 400% throttle도 단일스레드를 거의 못 늦춘다. 예외 경로(`_guaranteed_place` throw)도 정상 입력이면 안 던진다(train 40/40 무예외). 즉 이 −1이 v1.0.0~v1.2.0 내내 안 보인 건 *어려워서*가 아니라 로컬 게이트가 그 경로를 한 번도 실행하지 않아서이고, 동시에 유사 난이도 서버에서도 거의 안 켜진다는 뜻이다.

핵심은 **신뢰 경계**다. `algorithm()`의 반환은 둘뿐이다 — 자식 결과는 `_improve`(`myalgorithm.py:381`)에서 `check_feasibility`를 통과한 *바로 그 바이트*이고, [제공 `utils.py`가 서버 검증기와 동일](../../CLAUDE.md)하므로 **서버에서도 feasible이 보장**된다. floor는 그 검증을 거치지 않는 *유일한* 경로다. `check_feasibility` 호출은 코드 전체에서 `:381` 단 하나이고, 자식 모듈(constructor·alns·relax·obj3)은 전부 `operations_from_committed`(정수 캐스팅)→`_improve`를 거치므로 버그가 있어도 *폐기*될 뿐 infeasible로 반환되지 않는다(서브에이전트 감사로 −1 경로 0건 재확인). 그래서 −1의 표면은 사실상 floor 하나로 좁혀진다 — feasibility는 증명+실측(40/40)으로 닫혔고, 남은 건 timeout(supervisor가 `return_cap`으로 bound, 실측 ≤9.4s/10s)뿐이다. 실제 서버 −1의 더 그럴듯한 후보는 (a) supervisor가 *이미* 고친 v1.0.0 시절의 메인 overrun이거나 (b) 우리가 볼 수 없는 다른 무엇이며, 다음 깨끗한 제출의 feasibility 수로만 검증된다.

## 회귀 게이트: 미검증 경로를 영구히 커버한다

이 −1이 세 버전을 숨은 메커니즘은 단 하나 — *로컬 게이트가 floor의 fast-finish 경로를 한 번도 실행하지 않는다*. 그래서 그 경로를 강제로 켜는 회귀 게이트 `tools/floor_gate.py`를 못박았다. 인스턴스마다 floor를 두 모드로 만든다 — normal(`deadline=None`)과 fast-finish(`deadline=과거` → 전 블록이 fast-finish를 탄다) — 그리고 *제공 검증기*로 때려 feasible과 *정수 출력*을 확인한다(검증기는 float x/y를 허용하므로 정수 불변식은 게이트가 따로 막는다). 거기에 한 블록의 `processing_time`을 0으로 바꾼 합성 인스턴스로 proc==0 봉인(아래)을 확인한다. 하나라도 실패하면 종료코드 1이라 제출 전 게이트로 쓴다. 현재 결과: **40/40 feasible+정수(양 모드), proc==0 봉인 OK**. 이 게이트는 floor를 건드리는 모든 미래 변경이 미검증 경로에서 −1을 다시 들이지 못하게 막는다 — 이 문서가 줄곧 말한 "로컬 게이트가 못 보는 실패"를 보이게 만드는 장치다.

## proc==0 봉인: 마지막 잠복 floor −1

floor가 emit하는 유일한 잠복 −1 벡터가 하나 남아 있었다. floor는 `exit = entry + proc`로 두는데, 어떤 블록의 `processing_time`이 0이면 `entry == exit`가 되고, `_build_operations`가 같은 시각에 EXIT를 ENTRY보다 앞에 놓아(제출 형식 규칙) 검증기가 그 블록의 EXIT를 ENTRY *이전*에 처리한다 → "EXIT before present"로 Stage1/5 infeasible. floor는 미검증 경로라 이게 곧 보이지 않는 −1이다. train 최소 proc=3이라 안 나타나지만, 숨김 인스턴스가 proc=0을 주면 −1이다. 봉인은 floor의 proc 읽기를 `max(1, proc)`로 바꾼 것 하나다 — proc≥1엔 완전한 no-op(윈도우·exit·bay_tail이 같은 proc로 일관)이고, proc=0인 블록만 1단위 점유시켜 표현 가능하게 만든다. 측정으로 load-bearing을 확인했다 — block0를 proc=0으로 만든 합성 인스턴스에서 *봉인 전* floor는 infeasible(Stage1: "block 0 has no EXIT"), *봉인 후* feasible(Stage5 통과)이다. train floor sum_obj는 25,488,553,408로 봉인 전과 **byte 단위 동일**이라 무회귀다. 이 변경은 train 특정이 아니라 *어떤 입력에도 계산되는* 구조적 방어(최악을 막는 구조는 일반화한다)라, 자식 경로(검증으로 proc=0을 폐기→floor 폴백)는 건드리지 않고 floor에만 둔다.
