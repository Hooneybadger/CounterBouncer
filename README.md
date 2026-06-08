# CounterBouncer

Linux `perf stat`으로 모은 PMU 숫자가, 그 상태로 성능 진단에
넣어도 되는지 가리는 바운서입니다.

이름은 카운터 앞 바운서에서 따왔습니다. 프로그램이 평소 속도로
끝났다고 해서 그 순간 센 카운터를 바로 믿지는 않습니다. 이벤트가
실제로 돌고 있었는지, 어느 CPU에서 돌았는지, 같은 조건에서 반복이
흔들렸는지를 모아 들여보낼지 말지를 정합니다.

Profiler가 아니고, 병목을 찾아 주지도 않습니다. PMU 참값을 추정하지
않고, CXL이나 가속기 카운터, 성능 개선율도 다루지 않습니다.

## 무엇을 푸는 문제인가

카운터가 찍혔다는 것과 그 숫자를 믿어도 된다는 것은 별개입니다.
애플리케이션 시간만 보고는 알 수 없는 것들이 있습니다. 요청한
이벤트가 PMU에서 실제로 돌았는지(`pcnt-running`), 스레드가 어느
CPU로 옮겨 다녔는지, 같은 조건의 반복이 얼마나 흔들렸는지입니다.

어려운 지점은 이 근거를 한 점수로 합치는 데 있습니다. 실행이 평소
속도로 끝났다고 해서 카운터 coverage가 충분한 것은 아니고,
coverage가 좋아도 실행 환경이 깨끗한 것은 아닙니다.

## 결과

`native-holdout-v1`은 Intel Core i9-14900K bare-metal에서 PARSEC 3.0
native 네 개(blackscholes, canneal, dedup, streamcluster, 각 4스레드)와
CloudSuite Data Caching을 돌린 holdout입니다. 실제 애플리케이션 225회,
warmup은 별도, 실행 실패 0회입니다. 판정은 ACCEPT 15, DEGRADED 160,
REJECT 50입니다. 분류 정확도나 PMU 절대 오차율이 아닙니다.

정책은 calibration 80회 뒤에 고정했습니다. holdout을 보고 다시
맞추지 않았습니다.

MULTIPLEX 45회는 최소 `pcnt-running` 중앙값 30%로 전부 REJECT였고,
PARSEC runtime은 CLEAN과 거의 같았습니다. blackscholes SMT는 PMU
running 100%에 ACCEPT가 많았지만 median runtime은 +45.3%였습니다.
CloudSuite는 고정 100,000 req/s라 throughput CV가 0.00%이고,
UNPINNED에서 interval-p99는 CLEAN 대비 +121.7%였습니다.

표와 해석은 [결과 보고서](docs/technical_report.md)에 있습니다.

## 5분 만에 돌려보기

Python 3.11 이상이면 단위 테스트를 돌릴 수 있습니다. 실제 측정은
Linux bare-metal과 `perf` 권한이 필요합니다.

```console
python3 -m venv .venv
.venv/bin/pip install -e '.[analysis,test]'
.venv/bin/python -m unittest discover -s tests -v
```

단위 테스트는 저장소 안의 fixture만 씁니다. 벤치마크 증거가 아닙니다.
벤치마크 설치부터 holdout까지는 [실험 재현](experiments/README.md)을
따릅니다. 실패했거나 중간에 끊긴 run은 덮어쓰지 않습니다.

## 어떻게 동작하나

![측정 파이프라인](docs/figures/figure1_architecture.png)

워크로드 어댑터가 실제 애플리케이션에 `perf stat -j`를 걸고 실행
환경 스냅샷을 붙입니다. PARSEC는 공식 native 바이너리 전체(초기화·I/O
포함)를 재고, CloudSuite Data Caching은 서버 호스트 PID를 잽니다.

게이트는 하드 규칙과 그룹 안정성을 `ACCEPT` / `DEGRADED` / `REJECT`
한 줄로 합칩니다. 조건은 CLEAN, MULTIPLEX, SMT, MEMORY, UNPINNED입니다.
UNPINNED에서 명시한 `cpu_core`는 E-core 시간을 세지 않습니다.

run 디렉터리에는 원시 JSON, stdout/stderr, 명령, git SHA,
입력·바이너리 해시, 정책 해시가 같이 있습니다.

## 저장소 구조

| 경로 | 내용 |
| --- | --- |
| `counterbouncer/` | `perf stat` 파서, 품질 게이트, 워크로드 어댑터 |
| `configs/` | 동결된 정책과 이벤트 목록 |
| `experiments/` | 매니페스트 |
| `docs/` | 결과 보고서, 방법, 한계, 벤치마크 선정 |
| `tests/` | fixture만 쓰는 단위 테스트 |

측정 원본(`artifacts/`)과 vendor 트리는 git에 없습니다. 용량 때문입니다.
그림만 [docs/figures](docs/figures)에 복사해 두었습니다. 로컬에서 다시
돌리면 `artifacts/` 아래에 JSON·CSV가 생깁니다.

## 문서

프로젝트를 이해하려면 다음 순서로 읽으면 됩니다.

- [결과 보고서](docs/technical_report.md)
- [방법](docs/methodology.md)
- [한계](docs/limitations.md)
- [벤치마크 선정](docs/benchmark_selection.md)
- [용어와 자주 나오는 질문](docs/interview.md)
- [실험 재현](experiments/README.md)
- [출처](docs/sources.md)
- [완료 점검](docs/completion_checklist.md)

## 한계

공유 호스트 한 대이고, 주파수와 터보는 고정하지 않았습니다.
UNPINNED에서 `cpu_core`는 E-core 시간을 세지 않습니다. generic cache
이벤트를 다른 CPU에도 그대로 쓰는 LLC나 대역폭이라고 쓰지 않습니다.
CloudSuite는 단일 호스트 Docker bridge, 고정 offered load입니다.
보고하는 p99는 interval p99의 중앙값이지, 요청 전체를 모은 p99가
아닙니다.

전체는 [한계](docs/limitations.md)에 있습니다.

## 라이선스

MIT. [LICENSE](LICENSE). 기여 방법은 [CONTRIBUTING](CONTRIBUTING.md)를
따릅니다. Azure VM Noise Dataset은 CC-BY입니다. 인용은
[출처](docs/sources.md)에 있습니다.
