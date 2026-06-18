# supervisor 구조: 메인을 감독자로 — 어떤 제한시간에서도 −1을 구조적으로 막는다

- **state**: 측정완료 (v1.1.1에서 fork 메커니즘 정정 — 아래 ★ 참조)
- **코드**: `src/myalgorithm.py:algorithm()` (감독자), `_run_forked()` (os.fork 수집), `_child_body()`/`_full_body()`/`_relax_body()` (자식 본체), `_in_process_bounded()` (seccomp 폴백)
- **관련 결정**: STRATEGY_PLAN.md B1(feasibility-first) · P4c(시드 포트폴리오) 위에 얹힘
- **배경**: LEARNING_GUIDE.md Part F2(시간 관리) · GLOSSARY의 [floor](../GLOSSARY.md)
- **측정**: `results/v11sup2_2s/` · `results/v11sup2_10s/` · `results/v11sup2_full_60s_j1/`

## 한눈에

메인 프로세스는 더 이상 무거운 일을 직접 하지 않는다. 빠르고 시간이 묶이지 않는 일(floor 계산,
래스터 엔진 생성)만 직접 맡고, **구성·ALNS·선호 개선·최종 검증은 전부 fork 자식이 한다.** 메인은
`return_cap = 0.93 × timelimit`까지 큐에서 결과를 거두기만 하다가, 그 시각이 오면 무슨 일이 있어도
가장 좋은 feasible 결과(없으면 floor)를 반환한다. 자식 하나가 느린 Shapely 호출에 묶이거나 OOM으로
죽어도 메인의 벽시계는 자식과 무관하게 흐르니, 메인은 항상 제한시간 안에 답을 낸다. 이 구조의 목적은
한 줄로 줄어든다 — *어떤 제한시간에서도 −1(시간 초과·미반환)을 구조적으로 불가능하게* 만드는 것.

## ★ v1.1.1 정정 — 이 구조가 서버에서 무력했던 이유와 진짜 수정

처음 이 구조를 `multiprocessing.get_context("fork").Process`로 구현했을 때(v1.0.1/v1.1.0), **서버에서는
단 한 번도 작동하지 않았다.** 평가 서버는 우리 `algorithm()`을 *daemon 프로세스* 안에서 실행하는데,
daemon 프로세스는 자식을 만들 수 없다(`AssertionError: daemonic processes are not allowed to have children`).
그래서 `Process.start()`가 예외를 던지고, 코드는 `except`로 떨어져 **메인 단독 degraded 경로**(메인에서
`construct`를 직접 실행)를 탔다. 그런데 `construct`는 deadline을 무시하고 overrun한다 — 작은 인스턴스에선
0.6초 꼬리라 10초 제한에 묻혔지만, **큰 인스턴스(900블록 합성)에선 deadline 10초를 무시하고 16.46초까지
달려** 시간을 초과했다(floor 0.03초·최종 check 0.19초는 빠른데 `construct`만 16.46초). 그 결과 feasible한
해를 *늦게* 반환 → 서버가 시간 초과로 −1. **v1.0.0(설계상 in-process)과 v1.1.0(fork 실패→in-process)이 둘 다
숨김 P3에서 −1을 받은 단일 원인이 이것이다.** supervisor는 daemon 서버에서 fork를 못 해 무력했고, 로컬
게이트가 통과한 건 `batch_runner`가 `subprocess`(non-daemon)로 돌려 fork가 됐기 때문이다 — train≠서버
*실행환경* 미스매치.

진짜 수정은 **raw `os.fork()`** 다. `multiprocessing`의 daemon-자식 금지는 파이썬 레벨 assertion이지만
`os.fork()`는 OS 직접호출이라 daemon 프로세스에서도 통과한다(실측 확인). `_run_forked()`가 `os.fork()`로
`nw`개 자식을 띄우고, 각 자식은 결과를 임시파일에 원자적으로 피클(rename으로 "존재=완전기록" 보장),
메인은 `return_cap`까지 *종료한* 자식만 비차단(`os.waitpid(WNOHANG`)으로 수집하고 미완은 `SIGKILL`+reap한다.
이로써 supervisor가 **서버(daemon)에서도 작동** → construct가 종료 가능한 자식에서 돌고 메인은 bounded.
부수 효과로 **그동안 서버에서 degraded single-seed로 돌던 품질이 풀 포트폴리오로 복원**됐다(daemon
prob_17 2.69M→108K). `os.fork`마저 막히는 극단(seccomp)에선 `_in_process_bounded()`가 `SIGALRM`으로
construct overrun을 `return_cap`에 끊고 floor를 반환한다 — 아래 "버린 선택지들"의 SIGALRM 한계(C 호출
중단 불가)와 달리, 여기서 끊는 대상은 *파이썬 레벨 construct 루프*라 시그널이 바이트코드 경계에서 듣는다.

검증: daemon 모드(서버 조건 재현) 900블록 10초 16.26초→**9.33초 ok**, 전체 40개 daemon 게이트 tl=10초·60초
모두 **invalid 0·overtime 0**, seccomp 폴백 900블록 9.30초 floor. 아래 본문은 supervisor의 *원리*를 설명하며,
fork 메커니즘만 `multiprocessing`→`os.fork`로 바뀌었다(감독자·return_cap·floor 폴백 불변).

## 왜 이 기능이 필요했나

v1.0.0 제출에서 숨김 인스턴스 **P3가 infeasible(−1)** 로 돌아왔다. 같은 라운드의 P1·P2·P4·P5·P6는
전부 feasible이었고, P4~P6는 목적값이 8.6M~48.7M로 P3보다 훨씬 큰데도 통과했다. 로컬 학습 40개는
네 제한시간(10·60·300·1800초) 게이트에서 한 번도 infeasible이 없었다. 그러니 P3는 우리가 학습셋에서
본 적 없는 실패 모드를 건드린 셈이었다.

정적 분석과 실측으로 모든 infeasible 경로를 좁혔다. improve 경로는 `check_feasibility`로 스스로 검증하니
feasible만 반환하고, floor는 40개 전부 feasible이며(`learning/diag_floor_and_check.py`), `src/utils.py`는
`baseline/utils.py`와 바이트 동일이라 서버 검증과 로컬 검증이 같고, 최종 검증 비용은 dense 해에서도
0.11초에 그쳐 overrun 원인이 아니었다. 남은 결론은 하나였다 — **메인이 제한시간 안에 floor를 반환하지
못한 시간 초과.** v1.0.0은 구성(`construct`)과 시드 0의 `_improve`를 *메인에서* 돌렸는데, `construct`는
deadline을 넘겨도 남은 블록을 마저 배치하느라 300블록 기준 약 0.6초를 더 쓰고, 시드 0의 ALNS 마지막
반복과 예산 없는 최종 `check_feasibility`까지 메인을 묶는다. 느린 서버나 무거운 기하에서 이 tail이 쌓여
벽시계를 넘기면, 서버가 출력 전에 프로세스를 종료한다. floor는 이미 메모리에 있었지만 v1.0.0은 그걸
들고만 있다가 끝내 내지 못했다. 이 진단은 재현으로 확증됐다 — **2초 제한시간에서 prob_20·38(300·250
블록)이 3.1초에 overtime** 났고, 반환값은 floor였다(늦게 반환).

## 하는 일과 내부 동작

메인의 책임은 두 가지로 줄었다. 첫째, `_guaranteed_solution`으로 floor를 만든다 — 증명적으로 feasible한
직렬 배치이고 300블록에서도 0.7초 안에 끝나며, 메인이 손에 쥐고 있는 보장 답이다. 둘째, `InstanceRaster`를
생성한다(약 3밀리초). 둘 다 시간이 묶일 수 없는 hard-bounded 작업이다.

그다음 메인은 `nw`개(코어 수, 서버 4)의 자식을 fork한다. 각 자식은 `_worker_full`로 **best-of-3 구성을 짓고
그 위에서 ALNS와 선호 개선을 돌려** 결과를 큐에 넣는다. 구성(`_construct_incumbent`)은 `(edd, blf)`·
`(edd, scan)`·`(edd_area, scan)` 중 가장 좋은 base를 고르는데, 무작위가 없어 결정적이라 **모든 자식이 같은
최고 base를 얻고 시드만 ALNS에서 갈린다** — v1.0.0의 포트폴리오(최고 base에 4시드)와 정확히 같은
탐색이다. v1.0.0은 이 구성을 메인에서 한 번만 돌려 fork로 공유했지만, 그 무거운 구성이 짧은 제한시간에
메인을 묶어 overrun했다. 이제 구성은 각 자식이 독립으로 돌린다 — 결정적이라 품질은 같고, 전용 4코어에선
4중 중복 구성이 병렬이라 벽시계 손해가 없다(메인 단독 구성 때 놀던 코어를 쓰는 것뿐). `InstanceRaster`는
읽기 전용이라 fork의 copy-on-write로 그대로 공유되고(자식별 복제 없음, RSS 자식당 ~35MB로 OOM 없음),
자식이 만드는 `committed`는 각자 고유라 격리된다. 자식 내부 예산은 ALNS 0.83·polish 0.88이고, 그 뒤 최종
`check_feasibility`까지 보통 0.90 안에 끝나 메인의 수집 cap이 거둔다.

메인은 감독자로서 `return_cap = t0 + 0.93 × timelimit`까지 `q.get(timeout=...)`으로만 결과를 거둔다. 이
수집 루프는 timeout으로 묶여 있어 자식이 무엇을 하든 메인은 `return_cap`에 반드시 빠져나온다. 그 뒤 남은
자식을 `terminate()`(SIGTERM, 비동기라 tail 없음 — Shapely C 호출에 묶인 자식도 OS가 종료)하고, 거둔 것 중
가장 좋은 feasible 해를, 없으면 floor를 반환한다. 0.93은 CLAUDE.md의 절대 규칙값이고, 메인은 그 뒤 무거운
일을 하지 않으므로(수집·종료·min·반환만, ~밀리초) 7% 여유가 느린 서버의 직렬화·IPC tail까지 덮는다. 핵심
불변식은 *메인에는 deadline을 넘길 수 있는 무거운 일이 없다*는 한 가지 — floor와 ir만 직접 하고 나머지는 종료
가능한 자식 안에 둔다. floor 자체도 블록별 try로 감싸 *어떤 블록이 망가져도 빈 operations(= 미배치
= infeasible)를 내지 않게* 강건화했다 — floor가 발동하는 비상 상황이야말로 빈 해를 내면 안 되는 순간이다.

## 버린 선택지들

처음엔 `algorithm()`의 단계 *사이사이*에 `0.93×timelimit` 가드를 넣는 hotfix를 시도했다. 그러나 overrun은
`construct`와 `_improve` *내부*에서 나므로, 단계 사이 가드는 이미 늦은 시점에야 발화해 막지 못했다. 무거운
일을 메인에서 빼는 것만이 근본 해법이었다.

`signal.alarm`(SIGALRM)으로 메인을 강제 인터럽트하는 길도 검토했다. 파이썬 시그널 핸들러는 바이트코드
경계에서만 도므로 긴 Shapely C 호출을 중간에 끊지 못한다 — 중단 불가능한 C 호출을 시간 안에 끊는 유일한
방법은 그 호출을 *자식 프로세스에서 돌리고 `terminate()`* 하는 것뿐이다.

COW로 구성을 한 번만 짓고 공유하던 v1.0.0 설계(P4c)를 그대로 둔 채 메인만 감독자로 바꾸는 2단계 fork도
검토했다. 그런데 daemon 자식은 또 fork할 수 없고, 비-daemon 손자를 쓰면 메인이 중간 자식을 종료할 때 손자가
고아로 남아 제한시간 뒤까지 떠도는 위험이 있었다. 재현이 불가능한 상황에서 이 복잡도는 새 실패 모드를
부를 수 있어 버렸다. 대신 자식마다 독립 구성을 택했고, 메모리 측정에서 자식당 RSS가 약 35MB라 4개를
합쳐도 16GB 서버에 부담이 없어 OOM을 새로 만들지 않음을 확인했다. 독립 구성은 고경합에서 공유 대비
구성 CPU를 더 쓰지만(P4c가 측정한 rank 손해), 전용 4코어 환경에선 차이가 작고 무엇보다 −1을 구조적으로
없애는 안전이 그 손해를 압도한다.

자식을 감독자로 옮기면서 처음엔 best-of-3 구성을 *직렬* 대신 자식마다 서로 다른 구성 하나씩 맡겨 병렬로
펼치는 변형을 시도했다(자식 0=edd/scan, 1=edd_area/scan, 2=edd/blf …). 구성 다양성이 포트폴리오에
더해져 더 좋으리라 기대했으나, 전체 40개 측정에서 순위 시뮬레이션이 **73 → 58로 퇴보**했다 —
약한 base(edd_area·blf)에 ALNS 예산을 흘려, edd/scan이 분명히 최고인 인스턴스에서 "최고 base에 시드 분산"이
"여러 base에 시드 1개씩"을 이겼기 때문이다(prob_15 +18.3%, prob_7 +15.8% 등). 그래서 각 자식이 *동일한*
best-of-3 최고 base를 짓고 시드만 가르는 v1.0.0 방식으로 되돌렸다 — 결정적 구성이라 모든 자식이 같은
base를 얻어 v1.0.0의 탐색을 그대로 복제한다. *고르지 않은 길을 측정으로 확인한* 사례다.

## 언제·어디서 작동하나

`algorithm()`의 전 경로에서 항상 작동한다. `os.fork()`는 daemon·non-daemon 양쪽에서 통과하므로 정상
환경·서버 모두 자식 포트폴리오가 돈다(이것이 v1.1.1 정정의 핵심). `os.fork()` 자체가 막히는 극단(seccomp)
에서만 `_in_process_bounded()`로 떨어져 메인이 단독 구성+개선을 SIGALRM으로 hard-bound한다 — construct가
overrun해도 `return_cap`에 알람이 끊고 floor를 반환한다(실측: os.fork 차단 시뮬레이션 900블록 10초에 9.30초
floor, overrun 0). 메인의 수집 cap(`return_cap = 0.93×timelimit`)이 단일 시간 경계이고, 그 뒤 best_sol(있으면)·
floor 중 하나를 곧바로 반환한다 — 둘 다 이미 만들어진 feasible dict이라 시간 가드가 더 좋은 best를 floor로
강등하지 않는다.

## 검증과 한계

`batch_runner`로 확인했다. (1) **2초 극단 제한시간** — v1.0.0이 3.1초로 overtime 나던 prob_20·38이 이제
1.8초에 feasible 반환. (2) **10초** — 큰 인스턴스가 8.6~8.8초에 반환되고 floor가 아닌 실최적화 결과를 낸다
(prob_38 floor 2.7B→0.18B, prob_40 104M→8M). (3) **60초 전체 40개 무회귀**(`results/v11A_full_60s_j1/` vs
기준 `results/v10_hotfix_full_60s/`) — 둘 다 40/40 feasible·invalid 0, sum-obj가 223.285M로 v1.0.0의 223.287M과
사실상 같고, 32/40이 동률-이상이다. 순위 시뮬레이션은 head-to-head 72:75로 3점 뒤지지만, 뒤진 8개는
대부분 +0.1~1.3%이고 눈에 띄는 prob_20조차 supervisor 런들에서 149603·156697·163435로 ±5% 출렁이는
ALNS 벽시계 변동이라, 체계적 퇴보가 아니라 노이즈 범위에 든다. (4) **메모리** — 자식당 RSS ~35MB로 OOM 없음.
(5) **C1 floor 강건성** — 빈 shape 블록을 주입해도 floor가 throw 없이 모든 블록을 배치하고, `timelimit=0.01s`로
floor 경로를 강제해도 빈 operations가 아니다. (6) **degraded** — *이 항목은 v1.1.1에서 정정됨.* 옛 degraded
(multiprocessing fork 실패→메인 단독 construct)는 train 크기에선 통과했으나 큰 인스턴스에서 overrun해 −1을
냈다(P3의 원인). 위 ★ v1.1.1 정정의 os.fork·SIGALRM 검증으로 대체한다.

남은 한계: 매우 짧은 제한시간(2초)에서 큰 인스턴스는 자식 구성이 끝나기 전 메인이 `return_cap`에 닿아
floor를 반환한다 — 품질은 낮아도 feasible이라 −1은 아니다(feasibility-first의 본령). 실제 평가는 게이트
범위(10초 이상)일 가능성이 높아 이 구간에선 정상 최적화가 돈다. 그리고 자식 독립 구성의 고경합 rank
손해는 서버 동시성에 달려 있어, 첫 재제출 피드백으로 확인할 미지수로 남는다.
