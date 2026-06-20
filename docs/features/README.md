# features/ (기능별 학습 동기화 문서)

이 폴더는 **앞으로 챌린지를 진행하며 우리가 실제로 구현한 기능**을, 기능 하나당 문서 하나로 설명하는 곳입니다. 운영 규칙은 `CLAUDE.md` 5절(학습 동기화 규율)에 있고, 이 README는 그 색인입니다. 이 기능들의 측정을 한 곳에 모아 전체 개선 호로 본 것은 [`docs/RESULTS.md`](../RESULTS.md)에 있습니다.

## 이 폴더의 전제

- **앞을 향한다.** 여기 글은 우리가 만든 코드를 따라간다. 기능이 착지하는 변경에서 그 문서가 함께 태어난다. 추측이 아니라 구현·측정 위에 선다.
- **백포팅하지 않는다.** `LEARNING_GUIDE.md`의 배경 지식과 `STRATEGY_PLAN.md`의 결정은 이미 그 자리에 있다. 그 내용을 이리로 옮기지 않는다. 대신 각 기능 문서가 자신의 배경(GUIDE Part X)과 결정(STRATEGY Bx)을 **링크로 역참조**한다.
- **한 호흡 분량.** 청자가 한 번에 읽을 수 있게(대략 1~2 화면). 더 커지면 기능이 둘 섞인 것이니 나눈다.
- **육하원칙을 산문에 녹인다.** 왜·무엇·어떻게·다른 선택지·언제·검증. 딱딱한 항목이 아니라 흐르는 글로 (`_TEMPLATE.md` 참고).

## 작성 규약

- 파일명: `<NN>-<slug>.md` (예: `01-edd-dispatch.md`, `02-raster-engine.md`). `NN`은 착지 순서.
- 새 문서를 만들면 아래 색인 표에 한 줄을 추가한다.
- 상태(`state`)는 `설계 / 구현 / 측정완료`로 적어 글과 코드의 동기화 상태를 드러낸다.

## 색인

| # | 기능 | 상태 | 관련 결정 | 배경 |
|---|------|------|-----------|------|
| [01](./01-feasibility-first-wrapper.md) | feasibility-first 래퍼 | 구현 | B1·P1 | LEARNING_GUIDE B5·F2 |
| [02](./02-raster-engine.md) | 래스터 기하 엔진 | 측정완료 | B2·P2 | LEARNING_GUIDE C1·C2·B1 |
| [03](./03-coexistence-constructor.md) | 공존 구성기 | 측정완료 | B3·P3 | LEARNING_GUIDE B3·D1 |
| [04](./04-insertion-order-portfolio.md) | 삽입 순서 포트폴리오 | 측정완료 | B3·P3 | LEARNING_GUIDE B3·E2 |
| [05](./05-temporal-nesting.md) | temporal nesting 후보 | 측정완료 | B4·P3 | LEARNING_GUIDE D3 |
| [06](./06-alns.md) | ALNS 개선 루프 | 측정완료 | B3·P4 | LEARNING_GUIDE E2 |
| [07](./07-lower-bound.md) | obj1 하한과 천장 | 측정완료 | B5·P5 | LEARNING_GUIDE B5·F1 |
| [08](./08-repair-acceleration.md) | repair 가속(핫패스 인라인) | 측정완료 | B3·P4 | LEARNING_GUIDE E2 |
| [09](./09-preference-polish.md) | 선호 재배치·교환 polish(obj3 국소탐색) | 측정완료 | B5·P5·P4b | LEARNING_GUIDE B5·F1 |
| [10](./10-seed-portfolio.md) | 4코어 시드 포트폴리오(best-of-seeds) | 측정완료 | P4c·B3 | LEARNING_GUIDE E2 |
| [11](./11-supervisor-feasibility.md) | supervisor 구조(메인=감독자, −1 구조제거) | 측정완료 | B1·P1·P4c | LEARNING_GUIDE F2 |
| [12](./12-bay-clear-refill.md) | bay-clear-refill(obj3 국소탐색) | 채택 보류(노이즈) | B5·P5 | LEARNING_GUIDE B5·F1 |
| [13](./13-floor-scale-hardening.md) | floor 스케일·경계 강건화(스케일 −1 제거) | 측정완료 | B1·P1 | LEARNING_GUIDE F2 |
| [14](./14-relax-repair.md) | relax-and-repair(CP 코어 스케줄→nesting repair, obj1 천장) | 측정완료 | B3·B5·P5 | LEARNING_GUIDE F1 |
| [15](./15-floor-ref-anchor.md) | floor reference-point 경계 정합(ref≠(0,0) −1 제거·검증기 Block 직접 호출) | 측정완료 | B1·P1 | LEARNING_GUIDE F2 |
| [16](./16-floor-fp-soundness.md) | floor fit 판정 부동소수 정합(검증기 contains_block 직접 사용·QA red-team 발견) | 측정완료 | B1·P1 | LEARNING_GUIDE F2 |
| [17](./17-floor-fractional-timing.md) | floor 분수 timing 올림(ceil release/proc·red-team round2 방어강건화) | 측정완료 | B1·P1 | LEARNING_GUIDE F2 |
