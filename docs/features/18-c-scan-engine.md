# C scan 엔진: native 비트마스크로 단축-tl 대형-혼잡의 nesting 천장을 깬다

> 처음 보는 용어([전 위치 스캔](../GLOSSARY.md), [temporal nesting](../GLOSSARY.md), [크레인 j≥k](../GLOSSARY.md), [차등검증](../GLOSSARY.md), [BLF](../GLOSSARY.md))는 용어집에 정의해 두었습니다.

- **state**: 구현 · 측정완료
- **코드**: `src/scan_engine.c`(정적 C 바이너리 `src/scan_engine`) · `src/c_engine.py`(마샬링·subprocess·검증 래퍼) · `src/myalgorithm.py`의 `_cengine_body`/특수 자식 게이트
- **관련 결정**: [STRATEGY_PLAN](../STRATEGY_PLAN.md) 단축-tl 병목 항목 · **위에 섬**: [features/05](./05-temporal-nesting.md)(scan nesting)·[08](./08-repair-acceleration.md)(순수-파이썬 천장)·[14](./14-relax-repair.md)(relax 부분회수)
- **측정**: `learning/_scale_quality/c_engine/`(마샬·벤치·검증), train 10개 byte-identical, 합성 900-혼잡 −48%

## 한눈에

[scan 구성](./05-temporal-nesting.md)은 오버행 아래 [nesting](../GLOSSARY.md) 자리를 [전 위치 스캔](../GLOSSARY.md)으로 찾아 obj1(지각)을 크게 줄인다. 그런데 그 스캔은 위치마다 베이 크기 정수를 비트연산하는 [O(IFP)](../GLOSSARY.md)라, **혼잡 900블록에서 완주에 ~134초**가 든다. 그래서 채점 제한시간 10·60초에선 scan이 못 끝나고 빠른 [BLF](../GLOSSARY.md) base(혼잡 900블록 obj 655M)에 묶였다 — scan이 완주하는 300·1800초의 품질(339M)보다 **약 2배 나빴다**. 순수 파이썬 가속(행 단위·타깃 후보)은 [features/08](./08-repair-acceleration.md)에서 ~1.1~1.3×로 천장을 쳤다(원본이 이미 비트병렬).

그래서 *같은 알고리즘을 컴파일 언어로* 옮겼다. Python이 [래스터 엔진](./02-raster-engine.md)으로 마스크를 만들어(기하) 바이너리로 마샬링하면, 동봉한 **정적 C 바이너리**가 EDD 순서 + scan 구성 + 크레인 j≥k + occupancy를 native u64 비트마스크로 돌려 placement를 돌려준다. C는 Python scan 구성기의 **byte-identical 복제**(train 10개에서 obj가 한 자리까지 같다)이되 **~19배 빠르다**(혼잡 900블록 scan 134초 → C 7초, 마샬 포함 end-to-end 18.8초). 효과는 직접적이다 — 60초/900블록 혼잡에서 full algorithm obj가 **655M → 338,679,249(−48%)** 로, 단축-tl 대형-혼잡이 마침내 scan 품질을 *완주*해 낸다.

## 왜 이게 필요했나

숨김 인스턴스 P3(feasible, obj 736,453,961)가 단서였다. 그 7.4억은 train 최대(prob_38 76M)의 ~10배라, P3는 train 분포 밖의 *혼잡 대형* 인스턴스다(합성 900블록 혼잡이 655M으로 일치). 진단([STRATEGY](../STRATEGY_PLAN.md))이 둘로 갈렸다 — (1) 채점은 네 제한시간(10·60·300·1800초) 전부에서 이뤄지고, (2) 300·1800초는 scan이 122초에 완주해 339M이지만 **10·60초는 미완주라 BLF 655M에 묶인다**. 그 −48% 격차가 고-w1 대형-혼잡(점수 지배 구간)에서 순위를 깎았다. 순수 파이썬 레버는 모두 1.1~1.3×에 막혔고([features/08](./08-repair-acceleration.md)), 2배 빨라져도 122→61초로 60초를 못 맞춘다. 60초에 닿으려면(122→<48초) 범주적으로 다른 속도가 필요했고, [조직위 FAQ](../../CLAUDE.md)가 *다른 언어로 만든 정적 바이너리를 zip에 동봉해 subprocess로 호출*하는 길을 연다. 마이크로벤치로 전제를 먼저 못박았다 — C가 같은 스캔 작업량을 Python의 ~560분의 1 시간에 한다(비트병렬 native vs Python 큰정수).

## 하는 일과 내부 동작

분리가 핵심이다 — **Python이 기하, C가 비트마스크 루프.** `src/c_engine.py`의 `run_c_engine`이 `ir.masks()`로 래스터화한 (블록,방향,레이어) 마스크와 메타(release·proc·due·workload·선호·베이 크기·가중치)를 작은 바이너리로 마샬링한다. 마스크 행은 행당 u64 묶음으로, 경계는 Python `feasible_positions`와 *동일한* float rel_bbox(`local_bbox − ref`)로 싣는다 — 이 float 경계가 C의 후보집합을 Python과 일치시켜 byte-identical을 만든다(정수 셀 경계로 근사했을 땐 보수적이라 품질이 어긋났다). `src/scan_engine.c`는 이를 읽어 EDD 정렬 → 블록마다 베이별 `best_in_bay`(candidate-entry 시각 → present/exit/reverse 집합 → 크레인 상부맵 AND로 entry/exit/reverse 검사 → 바닥-우선 첫 feasible = BLF) → `placement_cost`로 최저 베이 선택 → 안 되면 빈-베이 윈도우 폴백, 을 Python `constructor.py`와 같은 순서로 한다. 크레인 비트연산은 [래스터 엔진](./02-raster-engine.md)의 상부맵 AND(`_overlap_any`)를 멀티워드 u64 시프트로 옮긴 것이다. C가 placement(블록→베이·위치·방향·entry·exit)를 바이너리로 내면 Python이 `check_feasibility`로 검증해 feasible일 때만 (obj, 해)를 채택한다.

[포트폴리오](./10-seed-portfolio.md) 안에서 자식 0이 C 엔진을 맡는다(나머지는 표준 Python). C가 None(바이너리 부재·비-0 종료·파싱오류·infeasible·예외 — 서버 호환 실패 포함)을 내면 그 자식이 표준 Python 구성으로 폴백하므로 **순수 추가**다 — best-of가 무회귀를, [supervisor floor](./11-supervisor-feasibility.md)가 −1 불가를 지킨다.

**대형도 구성 순서가 obj를 가른다 — 그래서 C 엔진은 단일 EDD가 아니라 4개 결정 순서**(EDD·edd_area·slack·release)**의 best-of로 construct한다**([features/19](./19-order-portfolio.md)의 순서 포트폴리오 통찰을 대형에 적용). 측정: 900-혼잡에서 EDD 단일 338,679,249 대 4순서 best **332,308,186(−1.9%)**. 순서는 **4개면 충분하다** — 같은 인스턴스서 N=12·30으로 늘려도 c_obj가 332,245,594로 *동일*(perturbed 순서가 4개 결정 순서의 best를 못 깸 = 대형 order-search는 4 결정순서에서 포화). 그래서 perturbed를 더 싣지 않고 결정 4개만 쓴다(소형~중형은 수천 perturbed가 이득인 것과 대비 — 대형은 construct가 비싸 결정적 소수만 든다). 단 대형은 순서당 construct가 비싸(900블록 ~5초) 네 순서를 다 못 돌 수 있어, `run_c_engine`이 *마샬 직후 남은 시간*으로 C 배치의 `max_s`를 정하고(`deadline = return_cap − check_여유(블록수 비례)`), C는 **정밀 시간가드**로 든 순서만 評価한다 — 매 순서마다 "현 경과 + 직전 순서 소요 > max_s"면 다음 순서를 *시작하지 않아*(overshoot 0) deadline을 넘기지 않고, EDD가 첫 순서라 1개만 들어도 옛 단일 EDD와 동일하다(무회귀). 옛 8순서마다 체크는 대형서 순서당 수 초라 너무 성겨 짧은 제한시간(10초 환산 검증서 tl=30·900블록)에 자식이 [return_cap](../GLOSSARY.md)을 넘겨 죽었는데(2.38억 회귀), 정밀가드가 그것을 단일 EDD(3.39억)로 안전 degrade해 고쳤다.

## 버린 선택지들

**순수 파이썬 가속**(features/08)은 1.1~1.3×라 60초/900블록을 못 맞춰 버렸다 — 단 행 단위 `feasible_positions`는 byte-identical이라 전역 채택돼 *보조로* 남는다. **타깃 nesting 후보**(`blfnest`: 앵커 레이어별 모서리)는 nesting이 앵커-가장자리에 정렬되지 않아 scan의 339M에 못 닿고(366M) 더 느려 기각했다. **Rust**(jagua-rs/sparrow)는 정전 참조이나 — (a) 우리 병목은 2D nesting *품질*이 아니라 시간축+크레인 *스캔 속도*라 jagua가 drop-in이 아니고([V2_DESIGN](../V2_DESIGN.md)이 품질로 기각), (b) 로컬에 Rust 툴체인이 없고 gcc 정적링크는 있어, 같은 속도를 더 단순·확실하게 주는 **C**를 택했다. **쿼리당 subprocess**는 IPC 비용으로 죽으니, *인스턴스 전체 구성*을 한 번 호출하는 덩어리 단위로 한다(마샬 1회 + C 1회).

## 언제·어디서 작동하나

`algorithm()`이 `n > 350`(train 최대 300 너머라 train은 절대 안 걸림 = byte-identical 무영향) + 바이너리 가용 + 제한시간 `≥30초`(마샬+C ~19초가 들어갈 예산)일 때만 자식 0을 C 엔진으로 띄운다. 그 외(작은 인스턴스·짧은 제한시간·바이너리 부재)는 표준 경로 그대로다. 10초 제한에선 마샬+C(~19초)가 [return_cap](../GLOSSARY.md)(0.93·tl)을 넘겨 자식이 종료되고 floor로 안전 폴백한다(scale_gate @10초 −1 0 확인). 300·1800초에선 C가 일찍 끝나 339M을 채택하고 남는 예산은 ALNS/relax가 받는다.

## 검증과 한계

[feasibility-first](../GLOSSARY.md)가 절대 규율이라 *byte-identical*과 *무회귀*를 먼저 증명했다. C 엔진 obj가 Python scan 구성기와 **train 10개에서 한 자리까지 동일**하다(prob_1 84,079·prob_20 205,519·prob_38 69,994,299·prob_40 3,237,747·…). 합성 900블록 혼잡에서 full algorithm이 **60초·300초 모두 338,679,249**(= Python scan @300초 완주값)로, 60초가 BLF 655M에서 −48% 내려갔다. train(≤300)은 `n>350` 게이트로 표준 경로 그대로라 무영향(prob_38 64.3M·prob_40 3.04M 등 정상). [scale_gate](../../learning/scale_gate.py)가 600·900·1200·1800블록 + 엣지에서 **60초·10초 −1 0·시간초과 0**을 확인했다(60초 C 발화, 10초 floor 폴백). 바이너리는 정적·제너릭 x86-64(`-march=native` 없음, GNU/Linux 3.2.0 호환)라 서버 의존성이 0이고, 호환 실패 시에도 subprocess 실패→None→폴백이라 −1이 불가하다(732KB, zip 15MB 한도 여유).

한계는 정직하게 적는다. **마샬(래스터화)은 900블록서 ~12초**(Python `ir.masks()` Shapely)지만, 대형 order-search가 4 결정순서서 포화하므로(위) 4순서 + 12초 마샬이 tl=60 예산(deadline) 안에 들어 *품질의 병목은 아니다* — 래스터화를 C로 옮기거나 캐시하면 마샬이 빨라지나 순서가 포화라 더 나은 obj로 이어지지 않는다(저EV, 기각). **★서버에서 정적 바이너리가 실제로 도는지는 제출로만 확정되는데, v1.3.0·v1.3.1 제출이 그것을 *반증*했다.** v1.3.0은 평가 서버가 zip을 `zipfile.extractall`로 풀어 +x가 벗겨진 것(0o644)이 원인이라 보고 `c_engine_available()`이 런타임 `os.chmod(0o755)`로 복원하게 고쳤다(v1.3.1, commit 5c64068). **그런데 v1.3.1도 서버서 P3=736M 그대로였다**(2026-06-22 피드백) — 제자리 chmod가 부족했다. 정밀 진단이 [supervisor](./11-supervisor-feasibility.md)에서 나왔다: 메인이 `os.fork()` + `/tmp` pickle로 자식 IPC를 하는데 *이게 서버서 작동한다*(P1~P6가 floor 아닌 정상값) → **fork도 `/tmp`도 서버서 OK**다. 그러면 C가 그보다 추가로 하는 단 하나 — *외부 바이너리 execve* — 거기서 막힌다. 제자리 `os.chmod`는 우리가 그 파일을 *소유하고* 폴더가 쓰기가능할 때만 통하는데(읽기전용 *디렉터리*는 소유 파일 chmod를 못 막는다 — 실측), 평가 서버가 추출을 다른 유저로 하거나(비소유→EPERM) 제출을 ro-mount하면(EROFS) chmod가 실패→0o644 유지→실행 불가→`_CENGINE_OK=False`→C가 *라우팅조차 안 됨*이다. 로컬은 우리가 소유+쓰기가능이라 늘 통과해 못 잡았다. **수정(v1.3.2): `_resolve_binary()`가 제자리 chmod 실패 시 바이너리를 *우리가 소유하는 쓰기+실행 위치(실행폴더·`/tmp`·cwd·홈)로 복사*해 거기서 +x·실행한다.** 후보 순서가 의도적이다 — **실행폴더는 원본이 거기서 도니 exec 보장**(비소유여도 폴더 쓰기가능하면 소유 복사본 생성)이라 첫 후보고, `/tmp`는 supervisor가 쓰기 입증했으나 noexec 마운트일 수 있어 그다음이다. 각 후보를 *실제 execve*로 판정해(noexec까지 거름) 첫 성공을 쓰고, 전부 실패면 None→폴백. 정적·제너릭 빌드 + 폴백으로 *그래도* −1은 불가하다(실행 실패 시 floor). 이 수정이 서버서 실제로 P3를 332M로 깨는지는 다음 제출 피드백이 확정한다 — 그대로 736M이면 원인은 execve 자체 차단(seccomp)이라 순수-Python 가속으로 피벗한다. 그리고 이 엔진은 scan 구성기를 *빠르게* 할 뿐 *더 좋게* 하진 않는다 — 332M 아래는 여전히 [features/14 relax](./14-relax-repair.md)·localized repair의 몫이고, 300·1800초의 헤드룸이 거기 있다.
