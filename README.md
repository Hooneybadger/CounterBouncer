# CounterBouncer

카운터 앞 바운서입니다. Linux `perf stat`으로 모은 PMU 숫자가 그 상태로 성능 진단에 넣어도 되는지 가리고, `ACCEPT` / `DEGRADED` / `REJECT`와 이유 코드를 남깁니다.

Profiler가 아니고 웹 대시보드도 아니고 병목을 찾아 주지도 않습니다. PMU 참값을 추정하지 않고 CXL·가속기 카운터나 성능 개선율도 다루지 않습니다.

## 왜 필요한가

카운터가 찍혔다는 것과 그 숫자를 믿어도 된다는 것은 별개입니다. 이벤트가 PMU에서 실제로 돌고 있었는지(`pcnt-running`), 스레드가 어느 CPU로 옮겨 다녔는지, 같은 조건에서 반복이 흔들렸는지는 애플리케이션 시간만으로는 안 보입니다. CounterBouncer는 그 근거를 모아 측정 품질만 판정합니다.

## 측정이 지나가는 길

![측정 파이프라인](docs/figures/figure1_architecture.png)

워크로드 어댑터가 실제 애플리케이션에 `perf stat -j`를 걸고 실행 환경 스냅샷을 붙입니다. 하드 규칙과 그룹 안정성을 본 뒤 판정과 이유 코드를 남깁니다. run 디렉터리에는 원시 JSON, stdout/stderr, 명령, git SHA, 입력·바이너리 해시, 정책 해시가 같이 있습니다.

PARSEC는 공식 native 바이너리 전체(초기화·I/O 포함)를 측정하고, CloudSuite Data Caching은 서버 호스트 PID를 잽니다.

## 이 저장소에 있는 것

코드, 동결된 정책(`configs/experiment.yaml`), 실험 매니페스트, 문서가 있습니다.

측정 원본(`artifacts/`)과 vendor 트리는 git에 없습니다. 용량 때문입니다. 그림만 [docs/figures](docs/figures)에 복사해 두었습니다. 표와 해석은 [결과 보고서](docs/technical_report.md)에 있습니다. 로컬에서 다시 돌리면 `artifacts/` 아래에 JSON·CSV가 생깁니다.

## 로컬에서 쓰기

Python 3.11 이상이 필요합니다. Linux bare-metal과 `perf` 권한이 있어야 실제 측정을 할 수 있습니다.

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[analysis,test]'
.venv/bin/python -m unittest discover -s tests -v
```

단위 테스트는 저장소 안의 fixture만 씁니다. 벤치마크 증거가 아닙니다. 벤치마크 설치부터 holdout까지는 [실험 재현](experiments/README.md)을 따릅니다. 실패했거나 중간에 끊긴 run은 덮어쓰지 않습니다.

## 이미 돌아간 실험

`native-holdout-v1`은 Intel Core i9-14900K bare-metal에서 PARSEC 3.0 native 네 개(blackscholes, canneal, dedup, streamcluster, 각 4스레드)와 CloudSuite Data Caching을 돌린 holdout입니다. 실제 애플리케이션 225회, warmup은 별도, 실행 실패 0회. 최종 판정은 ACCEPT 15, DEGRADED 160, REJECT 50입니다. 분류 정확도나 PMU 절대 오차율이 아닙니다.

정책은 calibration 80회 뒤 `2026-09-08T05:42:44.828333+00:00`에 고정했습니다. holdout을 보고 다시 맞추지 않았습니다. PMU running 임계는 degrade 90% / reject 50%, CV는 degrade 0.05115 / reject 0.20000입니다. 업계 표준이 아니라 이 호스트용 heuristic입니다.

조건은 CLEAN, MULTIPLEX, SMT, MEMORY, UNPINNED입니다. PARSEC는 조건당 10회, CloudSuite는 조건당 5회(클라이언트 timeout 60초), 워크로드마다 warmup 1회입니다. 조건 순서는 repetition block 안에서 무작위화했습니다.

선정 이유와 공식 설정은 [벤치마크 선정](docs/benchmark_selection.md), 측정 절차는 [방법](docs/methodology.md)에 있습니다.

## 문서

- [결과 보고서](docs/technical_report.md) — 판정 표, 애플리케이션 outcome, 실패·중단 기록
- [방법](docs/methodology.md)
- [한계](docs/limitations.md)
- [벤치마크 선정](docs/benchmark_selection.md)
- [용어와 자주 나오는 질문](docs/interview.md)
- [출처](docs/sources.md)
- [실험 재현](experiments/README.md) — `experiments/manifest.yaml` 포함
- [완료 점검](docs/completion_checklist.md), [진행 기록](docs/progress.md)

## 한계 (짧게)

공유 호스트 한 대, 주파수·터보는 고정하지 않았습니다. UNPINNED에서 `cpu_core`는 E-core 시간을 세지 않습니다. generic cache 이벤트를 다른 CPU에도 그대로 쓰는 LLC·대역폭이라고 쓰지 않습니다. CloudSuite는 단일 호스트 Docker bridge, 고정 offered load입니다. 보고하는 p99는 interval p99의 중앙값이지, 요청 전체를 모은 p99가 아닙니다.

전체는 [한계](docs/limitations.md)에 있습니다.

## 라이선스

MIT. [LICENSE](LICENSE). 기여 방법은 [CONTRIBUTING](CONTRIBUTING.md)를 따릅니다. Azure VM Noise Dataset은 CC-BY입니다. 인용은 [출처](docs/sources.md)에 있습니다.
