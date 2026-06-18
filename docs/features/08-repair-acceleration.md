# repair·구성 가속: 위치 무관 계산을 위치 루프 밖으로

> 처음 보는 용어([차등검증](../GLOSSARY.md), [상부 점유 맵](../GLOSSARY.md), [래스터 엔진](../GLOSSARY.md), [BLF](../GLOSSARY.md), [전 위치 스캔](../GLOSSARY.md))는 용어집에 정의해 두었습니다.

- **state**: 구현 · 측정완료
- **코드**: `src/constructor.py`의 `_best_in_bay`(repair·구성 공용 핫패스)와 `src/raster_engine.py`의 `feasible_positions`([전 위치 스캔](../GLOSSARY.md)) — 둘 다 위치 후보 루프의 크레인 검사를 인라인.
- **관련 결정**: [STRATEGY_PLAN](../STRATEGY_PLAN.md) B3·P4 · **배경**: [LEARNING_GUIDE](../LEARNING_GUIDE.md) E2 · **위에 섬**: [features/06](./06-alns.md)
- **측정**: `results/src_fresh_60s` vs `results/src_dev_combined_60s`(같은 조건 A/B), 프로파일 `learning/p5_profile_repair.py`·`learning/p5_profile_scan.py`, 차등검증 `learning/p5_difftest.py`

## 한눈에

[P5a](./07-lower-bound.md)는 큰 인스턴스에서 [ALNS](./06-alns.md)가 죽는다는 걸 숫자로 박았다. prob_38은 30초에 31반복뿐이고, 5배·30배 예산을 줘도 obj1이 안 줄었다. 그래서 두 핫패스를 [cProfile](../GLOSSARY.md)로 떴더니 repair의 `_best_in_bay`와 scan 구성의 `feasible_positions`가 똑같은 낭비를 하고 있었다. 위치와 무관한 값(블록 마스크·로컬 bbox·`int_for_R(R)`·[상부 점유 맵](../GLOSSARY.md))을 후보 위치마다 다시 조회한다. repair 한 측정에서 `entry_feasible`이 386만 번, scan 한 구성에서 셀 크레인 검사가 7,300만 번 불렸고, 그 안의 캐시 조회(`dict.get`)만 각각 1,580만·7,690만 번이었다.

고친 방법은 단순하고 똑같다. 그 위치 무관 값들을 방향(orient)당 한 번만 stamp로 만들어 두고, 크레인 검사를 비트 AND로 인라인했다. 같은 자리를 같은 순서로 고르되 더 빠르게 고른다. repair는 prob_38 ALNS 반복이 20초에 5→14회(약 2.8배)로, scan 구성은 prob_38이 35.9→19.3초(약 1.9배)로 빨라졌다. 이게 [feasibility](../GLOSSARY.md)를 깨지 않음은 [차등검증](../GLOSSARY.md)으로 증명했다. 옛 코드와 새 코드의 구성 출력이 40개 전부(blf)·다층 6개(scan) 바이트 단위로 동일하다.

## 왜 이게 필요했나

[P5a 헤드룸 프로브](./07-lower-bound.md)의 진단이 출발점이다. 큰 인스턴스는 60초에서 ALNS가 거의 안 도는데, 시간을 더 줘도(300·1800초) obj1이 그대로였다. 막힌 이유는 곧 드러났다. *시간*이 아니라 *한 반복의 비용*이었고, 그 비용은 가득 찬 베이를 매번 새로 스캔하는 데서 나온다.

프로파일이 범인을 정확히 짚었다. repair를 20초 떴더니 `_best_in_bay` 141번 도는 동안 `entry_feasible`이 386만 번 불렸고(자체 시간 상위는 비트 AND·`fits_in_bay`·래퍼), `masks`·`local_bbox`·`_ref`·`int_for_R`가 각각 약 390만 번, 그 `dict.get`이 1,580만 번이었다. scan 구성을 떴더니 `feasible_positions`가 구성 시간의 95%였고, 그 안에서 셀당 `_crane_blocked`→`_overlap_any`가 7,300만 번, `int_for_R`가 7,520만 번 돌았다. 두 함수 모두 `(블록, 방향)`에만 의존해 위치가 바뀌어도 같은 값을 주는데, 위치 루프 안에서 매번 다시 꺼내고 있었다.

## 하는 일과 내부 동작

두 곳에 같은 변형을 넣었다. *방향당 한 번* precompute하는 것이다. 방향마다 위치 무관 stamp `(int_for_R(R), my0·R+mx0, k)`를 비어 있지 않은 레이어별로 한 번 만들고, [상부 점유 맵](../GLOSSARY.md) `occ.upper()`도 한 번 고정한다. 그다음 위치 루프 안에서는 크레인 막힘을 `(stamp_int << (py·R+px+off)) & upper[k]`의 비트 AND로 인라인한다(`raster_engine.py`의 `feasible_positions`, `constructor.py`의 `_best_in_bay`). `_best_in_bay`는 여기에 경계 검사도 `rel[i]+px/py`의 네 비교로 인라인했다(=`fits_in_bay` 정확 복제). 이 비트 연산들은 옛 `_crane_blocked`·`entry_feasible`·`exit_feasible`이 하던 것과 글자 그대로 같아서 결과 boolean이 동일하다. reverse 검사(새 블록이 기존 블록의 크레인 경로를 막는지)는 병목이 아니라 그대로 뒀다.

요점은 *무엇을 계산하느냐*는 한 비트도 안 바꾸고 *언제 계산하느냐*만 옮겼다는 데 있다. 그래서 같은 자리를 같은 우선순위(바닥-왼쪽, 최저 top_y)로 고른다.

## 버린 선택지들

가장 큰 절감은 *점유를 증분 유지*하는 길이다. 후보 시각이 오를 때 존재 집합이 조금씩 바뀌니, 매번 `_occ_of`로 새로 쌓지 말고 더하고 빼며 이어가면 된다. 그러나 점유는 레이어별 단일 정수의 OR이라 제거가 불가능하다(OR은 역연산이 없다). 셀별 reference-count로 바꾸면 제거가 되지만 [래스터 엔진](./02-raster-engine.md)의 비트 연산 자체를 뜯어고쳐야 해 −1 위험이 커, 이 증분은 보류했다.

*후보를 줄이는 길*(가득 찬 베이에서 후보 시각·위치 수를 캡)은 한 반복을 더 싸게 만들지만 *어느 자리를 고르느냐*를 바꾼다. 동작 보존이 아니라 품질 트레이드라 별도 측정이 필요하고, 이번 인라인과 섞으면 원인 분리가 안 돼 분리했다. 진짜 큰 레버인 *타깃 repair*(영향받는 시간 구간의 베이만 다시 풀기)는 더 큰 재설계라 다음으로 미뤘다.

## 언제·어디서 작동하나

두 인라인은 각각 다른 경로를 푼다. `_best_in_bay`의 것은 [ALNS repair](./06-alns.md)(blf 코너 후보)에서, `feasible_positions`의 것은 [scan 구성](./05-temporal-nesting.md)에서 효과가 크다. 후자가 특히 중요한 까닭은 *안정성*에 있다. scan 구성은 큰 인스턴스에서 60초 예산의 절반 가까이를 먹어, 끝나기 전에 잘리면 [구성 포트폴리오](./03-coexistence-constructor.md)가 더 나쁜 blf 베이스로 떨어진다. prob_38이 바로 그 칼끝에 있었다. 같은 코드가 scan을 제때 끝내면 obj 70M, 못 끝내면 76M으로 갈렸다(서버 속도에 점수가 흔들리는 [벽시계 결합](../GLOSSARY.md) 취약성). scan 구성을 35.9→19.3초로 줄이자 prob_38이 여유 있게 scan을 끝내, 더 나은 베이스를 *안정적으로* 채택한다.

## 검증과 한계

[feasibility-first](../GLOSSARY.md)가 절대 규율이라 속도보다 *회귀 없음*을 먼저 증명했다. [차등검증](../GLOSSARY.md)(`learning/p5_difftest.py`)으로 옛 `src`와 새 코드의 `construct` 출력을 인스턴스별 정규 서명(블록→베이·위치·방향·시각 정렬 md5)으로 비교했더니 blf-edd 40/40, scan-edd 6/6(2층·4층 혼합) 바이트 동일이다(두 인라인을 모두 켠 채로). 출력이 같으면 어떤 검증 단계도 같은 판정을 내리므로 −1 위험이 구조적으로 없다.

속도는 `learning/p5_profile_repair.py`·`learning/p5_profile_scan.py`로 쟀다. prob_38 repair 반복이 5→14회(약 2.8배), scan 구성이 35.9→19.3초(약 1.9배)다. 같은 조건 60초 A/B(`results/src_fresh_60s` vs `results/src_dev_combined_60s`)에서는 순위 시뮬이 54→78로 올랐고, 40/40 feasible로 회귀 0, 최대 소요 50.24초다. 핵심은 prob_38이다. 베이스라인은 scan을 못 끝내 `construct:edd/blf`(obj 76,010,985)로 떨어졌는데, 새 코드는 scan을 제때 끝내 `construct:edd/scan`(obj 69,994,299, −7.9%)을 *안정적으로* 채택한다. 남은 obj 손해는 둘뿐이고(prob_7 +0.5%, prob_10 +1.1%) 둘 다 SA 궤적이 반복 수에 따라 갈린 1% 안쪽 잡음이다.

한계는 정직하게 적는다. 이 가속은 *반복을 늘리고 구성을 안정화할 뿐, 이동의 질을 바꾸지 않는다.* [P5a](./07-lower-bound.md)가 가리킨 진짜 병목 — prob_38은 1800초·30배 예산에도 obj1=5129로 정체 — 은 이걸로 안 풀린다. 큰 인스턴스의 지각은 *반복 수*가 아니라 *이동의 질*(어디를 뜯어 어디에 넣느냐)이 병목이기 때문이다. 그래서 이 가속은 끝이 아니라 다음 레버, 곧 타깃 repair와 더 똑똑한 destroy/repair 연산자를 위한 더 빠르고 안정된 바닥이다. repair가 빨라지면 그 새 이동들이 더 많이 시도된다.

