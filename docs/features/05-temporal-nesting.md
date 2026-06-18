# temporal nesting 후보: 오버행 아래 공간을 패킹에 쓰다

> 처음 보는 용어([temporal nesting](../GLOSSARY.md), [j≥k](../GLOSSARY.md), [BLF](../GLOSSARY.md), [IFP](../GLOSSARY.md), [공존 패킹](../GLOSSARY.md), [레이어](../GLOSSARY.md))는 용어집에 정의해 두었습니다.

- **state**: 구현 · 측정완료
- **코드**: `src/constructor.py`의 `_best_in_bay(..., cand="scan")` — 위치 후보를 [래스터 엔진](./02-raster-engine.md)의 전 위치 스캔(`feasible_positions`)으로 생성. 포트폴리오 결합은 `src/myalgorithm.py:algorithm`.
- **관련 결정**: [STRATEGY_PLAN](../STRATEGY_PLAN.md) B4·P3 · **배경**: [LEARNING_GUIDE](../LEARNING_GUIDE.md) D3 · **위에 섬**: [features/03](./03-coexistence-constructor.md)·[features/04](./04-insertion-order-portfolio.md)

## 한눈에

이 프로젝트의 1순위 차별화는 [j≥k](../GLOSSARY.md) 비대칭의 활용이다([STRATEGY](../STRATEGY_PLAN.md) B4). 키 큰 블록의 위층은 *오버행*(아래층보다 넓게 튀어나온 부분)을 만들고, 그 그늘의 바닥 공간은 비어 있다. [공존 구성기](./03-coexistence-constructor.md)의 [BLF](../GLOSSARY.md) 후보는 코너 자리만 만들어 이 그늘을 못 본다. 그래서 위치 후보를 [래스터 엔진](./02-raster-engine.md)의 *전 위치 스캔*으로 바꿔, 크레인이 닿는 모든 자리를, 오버행 아래 [nesting](../GLOSSARY.md) 자리까지 후보에 넣었다.

효과가 크다. 같은 [EDD](../GLOSSARY.md) 순서에서 후보만 BLF→scan으로 바꾸자 obj가 prob_1 306K→**84K**(−72%), prob_21 −38%, prob_33 −21%, prob_40 −19%, prob_27 −14%로 떨어진다(전 40개 ablation은 아래). 무대기 지각 하한이 0인데도([features/04](./04-insertion-order-portfolio.md)) 남아 있던 경합 지각이 더 빽빽한 패킹으로 회수된 것이다. 이 ablation이 보고서의 중심 Figure다.

## 왜 이게 필요했나

[features/04](./04-insertion-order-portfolio.md)에서 잰 헤드룸은 분명했다. P3a/P3b에 남은 지각은 전부 경합이고 그게 obj의 93.6%다. 순서를 바꿔선(P3b) 일부만 회수됐다. 남은 길은 더 빽빽이 쌓는 것, 곧 *공간*을 더 쓰는 것이다.

여기서 본 문제의 핵심 비대칭이 들어온다. [안착(stage 4)](../GLOSSARY.md)은 같은 레이어끼리만 겹치면 안 되지만, 크레인(stage 2/3)은 [j≥k](../GLOSSARY.md) 전부를 본다. 그래서 키 큰 블록 A의 위층 오버행 *아래* 바닥은, 같은 레이어로는 비어 있어 짧은 블록 B가 공간상 들어갈 수 있다. 다만 크레인으로 넣고 빼려면 시간 조건이 맞아야 한다. B가 A보다 먼저 들어오거나(A의 오버행이 아직 없을 때 내려오고) 시간 구간이 어긋나야, B의 하강이 A에 막히지 않는다. 학습 인스턴스의 다층 블록이 86%라([STRATEGY](../STRATEGY_PLAN.md) A2) 이 자유도는 거의 모든 배치에 존재하고, 대부분의 팀이 회피할 것이라 우리의 1순위 차별화다.

## 하는 일과 내부 동작

`_best_in_bay`에 위치 후보 생성 모드 `cand`를 더했다. 기존 `"blf"`는 코너 앵커를, 새 `"scan"`은 [래스터 엔진](./02-raster-engine.md)의 `feasible_positions`로 그 시각 [IFP](../GLOSSARY.md) 안의 *entry-크레인을 통과하는 모든 (px,py)* 를 만든다(`constructor.py`). 이 집합은 오버행 그늘 자리를 자동으로 포함한다. 그 자리가 entry-feasible한 것은, X가 들어오는 순간 그 위를 덮을 블록이 아직 present하지 않기(또는 j≥k가 빈 위층이라) 때문이고, 바로 그게 nesting의 성립 조건이다. 후보를 바닥 우선(py, px)으로 정렬해 가장 낮은, 곧 가장 빽빽한 자리를 먼저 본다.

nesting의 *시간* 안전성은 새로 만들 필요가 없었다. [공존 구성기의 양방향 크레인 검사](./03-coexistence-constructor.md)가 이미 보장한다. X를 오버행 아래 놓을 때, 나중에 그 위를 덮는 블록 C가 committed되면 C의 하강이 X를 침범하지 않는지(reverse), X가 나갈 때 위 블록이 막지 않는지(forward)를 삽입 순간 전부 본다. 그래서 scan은 *후보를 넓히기만* 하고, feasibility는 기존 불변식이 그대로 지킨다. 잘못된 nesting은 검사에서 걸러진다.

## 버린 선택지들

가장 정밀한 길은 **NFP/IFP 해석 생성**이다. 오버행 다각형 아래 들어갈 수 있는 자리를 기하로 직접 계산하는 방식인데, 정확하지만 구현이 무겁고, 전 위치 스캔이 이미 같은 자리를 *측정 가능한 비용*으로 찾아내 보류했다([STRATEGY](../STRATEGY_PLAN.md) B2의 "측정 없이 정밀화 금지"). 더 가벼운 길은 **타깃 nesting 후보**, 곧 베이 전체가 아니라 committed 블록의 x-구간과 겹치는 자리만 스캔하는 길이다. 전 위치 스캔이 60초 예산에 맞아(아래) 지금은 미루고, 큰 인스턴스에서 프로파일에 잡히면 그때 좁힌다. 점유·질의는 P2의 [단일 Python 큰정수](./02-raster-engine.md)를 그대로 쓴다.

## 언제·어디서 작동하나

scan은 비싸다(전 위치 스캔이라 BLF의 약 2배). 그래서 `algorithm()`의 포트폴리오가 예산을 보고 켠다([features/04](./04-insertion-order-portfolio.md)). 조합은 `("edd","blf") → ("edd","scan") → ("edd_area","scan")` 순서이고, best-of다. 10초 제한에선 빠른 `blf-edd`만 돌고(scan은 느려 잘리면 오히려 나쁨), 60초+에선 `scan-edd`의 nesting 이득까지 챙긴다. best-of라 scan이 어떤 인스턴스에서 손해여도 앞선 blf 해를 그대로 지켜, 회귀가 불가능하다.

## 검증과 한계

종료 기준은 nesting on/off ablation에서 베이 활용률과 obj1의 개선 측정이었다([STRATEGY](../STRATEGY_PLAN.md) B4). 같은 EDD 순서에서 후보만 BLF→scan으로 바꾼 전 40개 ablation(시간 압박 없이 순수 품질만)에서 **obj1이 38/40에서 줄고**(prob_29 −89%, prob_4 −83%, prob_6·9·12·15 −100%), 총 obj가 282.7M→232.5M(**−17.8%**, 인스턴스별 중앙값 약 −25%, 경합 큰 것은 −59%까지)이다. nesting이 실제로 일어났다는 근거도 같이 나온다. 시간이 겹치는 두 블록의 footprint bbox가 겹치는 쌍이 scan에서 거의 2배가 되고(prob_40 180→308, prob_33 92→222), 그중 *서로 높이가 다른*(오버행) 쌍이 상당수다(prob_40 218, prob_32 151, prob_14 145). 짧은 블록이 키 큰 블록의 그늘로 들어간 것이다. 단 scan 단독은 greedy 근시 때문에 2개(prob_10·17)에서 +3% 손해를 봤는데, 포트폴리오 best-of가 그 자리에서 BLF 해를 지켜 덮는다.

포트폴리오 전체는 서버 모사(`--jobs 1 -t 60`, `results/p3c_60s`)에서 **40/40 feasible**, P3b(`results/p3b_60s`) 대비 **회귀 0, 39개 개선·1개 동률**(prob_14 −64%, prob_2 −65%, prob_24 −59%), 순위 시뮬 **80:41**로 전 인스턴스 우세, 최대 소요 48.3초로 시간 초과 0이다.

한계는 비용이다. scan은 BLF의 약 2배라 큰 인스턴스의 60초가 빠듯하고(prob_38 ~47초), 10초 제한에선 못 쓴다. 타깃 nesting 후보나 슬라이딩 비트 스캔으로 좁히면 더 짧은 제한시간까지 nesting을 켤 수 있다. 다음 가속 여지다. 그리고 nesting은 *구성* 단계의 자유도일 뿐, 이미 놓은 블록을 옮겨 더 푸는 일은 [P4 ALNS](../STRATEGY_PLAN.md)의 몫으로 남는다.
