# CounterBouncer — Performance Measurement Quality Gate
## XCENA Performance & Developer Tools 지원용 상세 개발/실험 명세서

- 문서 버전: 1.0
- 기준일: 2026-09-08
- 대상 독자: 구현을 인계받는 하위 에이전트/개발자
- 목표 기간: 3~4주
- 실행 환경: Linux bare-metal x86-64 우선
- 핵심 원칙: **실제 애플리케이션을 실제 CPU에서 실행하여 얻은 PMU/OS 측정값만 최종 성능 근거로 사용한다.**
- OSS upstream PR: 선택 사항. 프로젝트 완료 조건이 아님.

---

# 0. 이 문서의 우선순위

이 문서의 목적은 아이디어 브레인스토밍이 아니라 **구현 범위 고정**이다.

하위 에이전트는 아래 우선순위를 따른다.

1. 이 문서의 `MUST / MUST NOT` 규칙
2. 실제 실행 환경에서 재현 가능한 사실
3. 공식 benchmark 및 공식 문서
4. 구현 편의성
5. 추가 아이디어

추가 아이디어가 1~3과 충돌하면 **추가하지 않는다.**

---

# 1. 프로젝트 한 문장

> **CounterBouncer는 Linux PMU 성능 측정 결과가 실제 진단에 사용 가능한 품질인지 판단하기 위해, PMU scheduling 상태·실행환경·반복측정 안정성·보조 calibration 결과를 함께 수집하고 명시적 근거와 함께 `ACCEPT / DEGRADED / REJECT` 판정을 내리는 Performance Measurement Quality Gate다.**

이 프로젝트는 profiler가 아니다.

이 프로젝트는 hardware counter의 절대적 진실값을 알아내는 시스템도 아니다.

이 프로젝트의 질문은 오직 다음이다.

> **“이번 측정 결과를 성능 진단의 근거로 사용해도 되는가?”**

---

# 2. 지원 직무와의 연결

대상 직무: **XCENA Performance & Developer Tools**

프로젝트가 보여줘야 하는 역량:

- Linux 성능 측정
- PMU / hardware counter 이해
- cache / branch / IPC / memory 계층 이해
- benchmark 설계
- 성능 측정 노이즈와 재현성 관리
- raw counter → developer-facing metric으로의 추상화
- 원시 숫자를 무비판적으로 사용하지 않는 진단 태도

프로젝트 설명 시 `CXL counter를 재현했다`고 주장하지 않는다.

정확한 연결 문장은 다음이어야 한다.

> “CPU PMU를 실험 기반으로 사용해, hardware counter를 상위 metric으로 추상화하기 전에 measurement validity를 검증하는 계층을 설계했습니다. 실제 accelerator/CXL counter는 다루지 않았지만, counter → metric → diagnosis 과정에서 필요한 신뢰성 검증 문제를 다뤘습니다.”

---

# 3. 비목표 / 금지사항

## 3.1 MUST NOT

다음 행동을 금지한다.

1. `perf`를 대체하는 profiler를 새로 만들지 않는다.
2. flame graph UI를 만들지 않는다.
3. 단순 benchmark dashboard를 만들지 않는다.
4. PMU event 목록을 보여주는 wrapper를 만들지 않는다.
5. “AI가 병목을 자동 진단한다” 같은 LLM/ML 기능을 추가하지 않는다.
6. 웹 UI 개발에 시간을 사용하지 않는다.
7. 임의 생성한 CSV/JSON 성능값을 최종 결과에 사용하지 않는다.
8. 임의로 만든 workload만으로 프로젝트 성능을 주장하지 않는다.
9. 실제 hardware counter의 ground truth를 안다고 주장하지 않는다.
10. `CounterBouncer 정확도 95%`처럼 정의되지 않은 정확도 수치를 만들지 않는다.
11. 특정 CPU vendor의 undocumented event를 근거 없이 사용하지 않는다.
12. CPU/커널/benchmark 버전을 숨기지 않는다.
13. 실패한 실험을 제거해 결과를 예쁘게 만들지 않는다.
14. 실제 CXL device를 사용하지 않았는데 CXL 성능 프로젝트라고 표현하지 않는다.
15. OSS merge/PR을 완료 조건으로 잡지 않는다.

## 3.2 synthetic 사용 규칙

synthetic microbenchmark는 **calibration/test용으로만 허용**한다.

허용 예:
- STREAM
- uarch-bench
- 직접 작성한 branch-predictability microkernel

금지:
- synthetic microbenchmark 결과를 최종 “real application 성능 개선”의 주 근거로 사용
- synthetic 결과만으로 reliability policy를 완성했다고 주장

최종 검증에는 반드시 실제 application benchmark가 포함되어야 한다.

---

# 4. 핵심 가설

다음 가설을 검증한다.

## H1. PMU scheduling 품질

PMU event가 hardware counter capacity를 넘어 multiplexing되거나, derived metric을 구성하는 event가 충분히 동시에 측정되지 않으면 해당 metric을 진단에 사용하는 위험이 커진다.

## H2. 실행환경 오염

동일 application이라도 CPU affinity, SMT sibling contention, background CPU/memory load, CPU migration 등의 조건이 달라지면 측정 결과의 분산 및 application outcome이 달라질 수 있다.

## H3. 단일 숫자보다 측정 메타데이터가 중요

`counter-value`만 저장하는 것보다 `event-runtime`, `pcnt-running`, 반복 분산, 실행 환경 정보를 함께 보존하면 불안정한 측정을 사전에 식별할 수 있다.

## H4. 품질 판정은 진단과 분리되어야 함

CounterBouncer는 “왜 느린가”를 자동 판단하지 않고, “이 측정을 진단에 투입해도 되는가”를 판단해야 한다.

---

# 5. 실제 데이터 / benchmark 정책

## 5.1 필수 Primary Benchmark A — PARSEC

실제 multicore application workload.

필수 조건:

- 가능한 경우 `native` input 사용
- 최소 4개 서로 다른 성격의 workload 선택
- `test` input은 sanity check에만 사용
- 성능 결과에는 `native` 또는 성능 분석에 적절한 input 사용

권장 후보:
- blackscholes: compute/parallel
- canneal: memory-intensive
- dedup: pipeline/data
- streamcluster 또는 ferret: mixed workload

환경에서 특정 package가 깨지면 동일 성격의 다른 PARSEC workload로 교체 가능하나,
**교체 이유를 `docs/benchmark_selection.md`에 기록**한다.

참고:
- PARSEC native input은 실제 hardware benchmark용으로 정의되어 있다.
- source: https://github.com/csail-csg/parsec
- 참고 mirror/setup: https://github.com/cirosantilli/parsec-benchmark

## 5.2 필수 Primary Benchmark B — CloudSuite

최소 1개를 실제로 실행한다.

우선순위:
1. Data Caching
2. Web Serving
3. Web Search

단일 머신에서 Docker container 여러 개를 사용하는 것은 허용한다.

Web Serving 선택 시:
- web server
- MariaDB
- Memcached
- Faban client
구성을 동일 host에서 실행 가능하다.
QoS는 CloudSuite 지침에 따라 latency 중심으로 본다.

source:
- https://github.com/parsa-epfl/cloudsuite
- https://github.com/parsa-epfl/cloudsuite/blob/main/docs/benchmarks/web-serving.md

## 5.3 필수 External Validation — Azure VM Noise Dataset 2024

이 데이터는 PMU ground truth가 아니다.

목적:
- 실제 장기간 cloud benchmark에서 noise/variation이 존재함을 외부 데이터로 확인
- local 반복 측정 결과의 variance 해석을 보조
- project result의 외부 타당성 설명

데이터 특성:
- 2023-05-28 ~ 2024-09-23, 약 483일
- 40 benchmarks
- 92 metrics
- PostgreSQL, Redis, fio, perf-bench, stress-ng, sysbench, MLC 등 포함

source:
- https://github.com/Azure/AzurePublicDataset/blob/master/AzureVMNoiseDataset2024.md

MUST NOT:
- Azure 데이터의 benchmark value를 local PMU counter ground truth로 취급

## 5.4 Calibration-only benchmarks

허용:
- STREAM: memory bandwidth calibration
- uarch-bench: microarchitecture sanity
- 소규모 branch/cache microkernel

이 결과는 `calibration` 섹션에만 표시한다.

---

# 6. 실행 환경 요구사항

## 6.1 필수

- Linux bare-metal
- x86-64
- root 또는 필요한 perf 권한
- `perf`
- Python 3.11+
- C/C++ compiler
- Docker (CloudSuite용)
- 충분한 디스크

## 6.2 권장

- 8 cores 이상
- 32GB RAM 이상
- SMT 지원 CPU
- frequency governor 확인 가능
- NUMA가 있으면 기록하되 필수 아님

## 6.3 VM에서 실행 금지

최종 PMU 결과는 VM을 primary evidence로 쓰지 않는다.

VM만 사용 가능한 경우:
- 개발/파싱 테스트는 가능
- 최종 benchmark를 진행하지 말고 `BLOCKED: bare-metal required`로 보고

하위 에이전트가 VM에서 임의 결과를 만들어 완료 처리하면 실패다.

---

# 7. Preflight 단계

구현 시작 전에 `scripts/preflight.py`를 실행한다.

수집 항목:

- hostname
- kernel version
- CPU vendor/model
- logical/physical cores
- SMT enabled
- NUMA topology
- governor
- turbo/boost 상태(가능한 범위)
- `perf --version`
- `perf stat` 기본 event 사용 가능 여부
- `kernel.perf_event_paranoid`
- NMI watchdog 상태
- Docker version
- free RAM/disk

필수 기본 event:

- cycles
- instructions
- branches
- branch-misses
- cache-references
- cache-misses
- context-switches
- cpu-migrations
- page-faults

필수 event 중 hardware-specific unsupported가 있다면:
- 지원되는 generic event subset으로 진행
- unsupported fact를 기록
- 가짜 0 값으로 대체 금지

출력:
`artifacts/preflight/system.json`

---

# 8. 시스템 아키텍처

```text
                         Real workload
                 PARSEC / CloudSuite / calibration
                              |
                              v
+----------------------+  Measurement  +-----------------------+
| Workload Adapter     | ------------> | perf stat JSON        |
| - command            |               | - counter-value       |
| - result parser      |               | - event-runtime       |
| - ROI/phase metadata |               | - pcnt-running        |
+----------+-----------+               +-----------+-----------+
           |                                           |
           |                                           |
           |       +----------------------+            |
           +------>| Environment Collector|<-----------+
                   | affinity / SMT       |
                   | governor / load      |
                   | migrations / ctxt    |
                   +----------+-----------+
                              |
                              v
                   +----------------------+
                   | Quality Analyzer     |
                   | hard validity rules  |
                   | stability analysis   |
                   | evidence generation  |
                   +----------+-----------+
                              |
                              v
                  ACCEPT / DEGRADED / REJECT
                  + machine-readable reasons
```

---

# 9. 저장소 구조 — 변경 금지 원칙

권장 저장소:

```text
counterbouncer/
├─ README.md
├─ pyproject.toml
├─ configs/
│  ├─ events_generic.yaml
│  ├─ parsec.yaml
│  ├─ cloudsuite.yaml
│  └─ experiment.yaml
├─ counterbouncer/
│  ├─ __init__.py
│  ├─ cli.py
│  ├─ model.py
│  ├─ runner.py
│  ├─ perf_parser.py
│  ├─ environment.py
│  ├─ quality/
│  │  ├─ rules.py
│  │  ├─ stability.py
│  │  └─ verdict.py
│  ├─ workloads/
│  │  ├─ base.py
│  │  ├─ parsec.py
│  │  ├─ cloudsuite.py
│  │  └─ calibration.py
│  └─ report.py
├─ scripts/
│  ├─ preflight.py
│  ├─ setup_parsec.sh
│  ├─ setup_cloudsuite.sh
│  └─ run_matrix.py
├─ calibration/
│  ├─ branch/
│  ├─ cache/
│  └─ memory/
├─ tests/
│  ├─ test_perf_parser.py
│  ├─ test_quality_rules.py
│  ├─ test_verdict.py
│  └─ fixtures/
├─ experiments/
│  ├─ manifest.yaml
│  └─ README.md
├─ analysis/
│  ├─ analyze.py
│  └─ plots.py
├─ docs/
│  ├─ benchmark_selection.md
│  ├─ methodology.md
│  ├─ limitations.md
│  └─ sources.md
└─ artifacts/
   └─ .gitkeep
```

웹 프론트엔드 폴더를 추가하지 않는다.

---

# 10. 데이터 모델

각 run은 JSON 한 파일로 저장한다.

예시 schema:

```json
{
  "run_id": "parsec-canneal-clean-r03",
  "timestamp": "ISO-8601",
  "git_commit": "...",
  "workload": {
    "suite": "parsec",
    "name": "canneal",
    "input": "native",
    "command": "...",
    "outcome": {
      "runtime_s": 12.34
    }
  },
  "system": {
    "kernel": "...",
    "cpu_model": "...",
    "smt": true,
    "governor": "...",
    "affinity": "0-7"
  },
  "events": [
    {
      "name": "cycles",
      "value": 123,
      "event_runtime_ms": 1000,
      "pcnt_running": 100.0
    }
  ],
  "software_events": {
    "cpu_migrations": 0,
    "context_switches": 123
  },
  "quality": {
    "verdict": "ACCEPT",
    "reasons": []
  }
}
```

원시 `perf` 출력도 별도로 보존한다.

---

# 11. 측정 방법

## 11.1 perf backend

기본:
`perf stat -j`

반복:
- 동일 조건 최소 10회 권장
- 시간 비용이 큰 CloudSuite는 최소 5회 허용
- 실제 횟수는 manifest에 기록

수집해야 할 perf JSON field:

- counter-value
- event
- event-runtime
- pcnt-running
- variance (사용 시)

공식 perf stat JSON이 제공하는 필드를 그대로 파싱한다.

source:
https://man7.org/linux/man-pages/man1/perf-stat.1.html

## 11.2 Event grouping

derived metric의 event는 가능한 경우 group으로 묶는다.

예:
`{cycles,instructions}`

perf는 event가 hardware counter 수를 초과하면 time multiplexing을 사용하고,
workload profile이 시간에 따라 바뀔 때 error가 생길 수 있다고 명시한다.

source:
https://github.com/torvalds/linux/blob/master/tools/perf/Documentation/perf-list.txt

---

# 12. Metric 범위

1차 버전에서 지원할 metric:

- IPC = instructions / cycles
- branch miss rate
- cache miss ratio (generic perf event 기반, CPU별 의미 차이 명시)
- context switches / second
- CPU migrations / second
- page faults / second

Memory bandwidth는:
- generic cross-CPU metric으로 강제 구현하지 않는다.
- vendor tool / uncore event가 확인된 시스템에서만 `experimental`로 추가 가능

MUST NOT:
- 모든 x86 CPU에서 동일 의미의 LLC/memory bandwidth metric이라고 주장

---

# 13. Quality Analyzer

Quality Analyzer는 두 종류 판단을 분리한다.

## 13.1 Hard evidence

예:
- required event unsupported
- event running ratio가 현저히 낮음
- required metric event 일부 누락
- run 실패
- process migration 존재
- benchmark result parser 실패

## 13.2 Statistical evidence

반복 run의:
- median
- MAD
- CV
- outlier

를 계산한다.

### 중요

`ACCEPT/DEGRADED/REJECT` threshold는 “업계 표준 절대값”이라고 주장하지 않는다.

정책:
1. calibration workload에서 threshold 후보 정의
2. threshold를 freeze
3. holdout real workload에서 검증
4. test workload 결과를 본 뒤 threshold를 재튜닝하지 않는다

모든 threshold는 `configs/experiment.yaml`에 기록한다.

---

# 14. Calibration

Calibration 목적:
- parser/system correctness 검증
- known qualitative relation 확인
- threshold 후보 설정

예:

## Branch

predictable vs unpredictable branch

검증:
`branch-misses(random) > branch-misses(predictable)`

## Working set

cache-resident vs cache-exceeding size

검증:
큰 working set에서 cache miss 관련 signal 증가 여부

## STREAM

memory-intensive workload에서 측정 pipeline이 정상 동작하는지 확인

주의:
calibration 결과는 real-app 최종 성능 주장이 아니다.

---

# 15. 실제 실험 Matrix

각 real workload에 대해 다음 조건을 실행한다.

## E0 CLEAN

- CPU pinned
- background experiment load 없음
- 고정된 benchmark config
- 충분한 warmup
- 동일 machine

## E1 MULTIPLEX

실제 hardware counter capacity를 넘도록 event 수를 증가시킨다.

목적:
- `pcnt-running`
- event-runtime
- derived metric stability
관찰

## E2 SMT CONTENTION

benchmark pinned CPU의 sibling logical CPU에 실제 competing workload 실행.

단, 임의 데이터 생성이 아니라 실제 process를 실행하는 controlled interference다.

권장 interference:
- stress-ng CPU worker
- 또는 calibration workload

## E3 MEMORY CONTENTION

동일 machine에서 STREAM/stress-ng memory workload를 concurrent 실행.

## E4 UNPINNED

benchmark CPU affinity를 제거한다.

`cpu-migrations` 실제 event를 측정한다.

### 선택 조건

E5 FREQUENCY/POWER
환경이 안정적으로 제어 가능한 경우만 수행.

---

# 16. “목 데이터”를 피하는 규칙

실험에서 값을 임의로 주입하지 않는다.

허용:
- 실제 concurrent process 실행
- 실제 PMU event 수 증가
- 실제 CPU affinity 변경

금지:
- JSON에서 migration=10으로 수동 변경
- runtime에 random noise 더하기
- bandwidth를 코드에서 sleep으로 가짜 저하
- 결과 CSV에 사람이 “bad” label 삽입

label은 **실험 조건 manifest로부터 자동 생성**한다.

---

# 17. 평가 방법

CounterBouncer가 정답 PMU counter를 맞추는지 평가하지 않는다.

다음을 평가한다.

## 17.1 Quality gate separability

CLEAN과 controlled contamination 조건에서 verdict 분포 비교.

## 17.2 Application outcome deviation

각 workload의 CLEAN median 대비:
- runtime
- throughput
- p99 latency(CloudSuite)
변화 확인.

quality verdict와 outcome degradation의 관계를 분석한다.

## 17.3 Repeatability

같은 condition에서 run-to-run variance.

## 17.4 Explainability

각 REJECT/DEGRADED verdict에는 반드시 machine-readable reason code가 존재해야 한다.

예:
- `LOW_PMU_RUNNING_RATIO`
- `CPU_MIGRATION`
- `HIGH_RUN_VARIANCE`
- `MISSING_REQUIRED_EVENT`
- `ENVIRONMENT_MISMATCH`

---

# 18. Azure 외부 검증

Azure VM Noise Dataset 분석은 별도 notebook/스크립트로 한다.

목적:
- benchmark별 long-term dispersion
- short-lived vs long-lived VM variability
- workload 종류별 noise 양상

최종 보고서에서는 다음 정도만 연결한다.

> “Local machine의 controlled interference 결과와 별도로, Azure 공개 데이터에서도 동일 benchmark 계열의 장기간 변동이 관찰됨을 확인했다. Azure trace는 PMU ground truth가 아니므로 CounterBouncer 판정의 정확도 계산에는 사용하지 않았다.”

---

# 19. 필수 결과 Figure

최종 README/PDF에 다음 Figure를 반드시 만든다.

## Figure 1 — Architecture
CounterBouncer measurement pipeline.

## Figure 2 — PMU Multiplexing
x: requested events 또는 condition  
y: `pcnt-running` + derived metric variability

## Figure 3 — Real workload stability
PARSEC/CloudSuite별 CLEAN vs interference CV 또는 outcome deviation

## Figure 4 — Quality verdict distribution
condition별 ACCEPT/DEGRADED/REJECT

## Figure 5 — Verdict vs application outcome
quality가 낮은 run에서 실제 runtime/latency deviation이 커지는지

선택:
Azure VM Noise external validation figure 1개.

---

# 20. README 구성

README 순서 고정:

1. Problem — “측정됐다는 것과 믿을 수 있다는 것은 다르다.”
2. One-line solution
3. What this project is NOT
4. Architecture
5. Real-world benchmarks
6. Measurement methodology
7. Reliability evidence
8. Results
9. Failure analysis
10. Reproducibility
11. Limitations
12. XCENA role relevance
13. Sources

README 첫 화면에 코드 설명부터 넣지 않는다.

---

# 21. 성공 기준

프로젝트 완료 조건:

- [ ] Linux bare-metal preflight 저장
- [ ] perf JSON parser tests 통과
- [ ] PARSEC real workload 최소 4종
- [ ] CloudSuite workload 최소 1종
- [ ] 각 primary workload에 CLEAN + 최소 3 contamination condition
- [ ] raw perf output 보존
- [ ] quality verdict reason code 제공
- [ ] threshold calibration/holdout 분리
- [ ] Azure dataset external analysis
- [ ] 최종 Figure 5개 이상
- [ ] experiment manifest로 재현 가능
- [ ] limitations 명시
- [ ] 임의 성능 데이터 0건

완료 기준에 OSS PR은 없다.

---

# 22. 실패 / 중단 기준

다음 상황에서는 방향을 임의 변경하지 말고 보고한다.

## BLOCKER A
bare-metal perf hardware event 접근 불가.

행동:
- 권한 해결 시도
- 해결 불가 시 최종 benchmark 중단
- VM synthetic 대체 금지

## BLOCKER B
CloudSuite 전체 setup 실패.

행동:
- Data Caching → Web Serving 등 동일 공식 suite의 다른 workload로 1회 교체 가능
- 교체 이유 기록
- 임의 custom web workload로 대체 금지

## BLOCKER C
PARSEC package 일부 build 실패.

행동:
- 최소 4개 성공 workload 확보
- 실패를 숨기지 말 것

## BLOCKER D
특정 PMU event unsupported.

행동:
- generic supported subset 사용
- unsupported 명시
- 값을 가짜 0으로 대체 금지

---

# 23. 4주 일정

## Week 1 — Measurement foundation
- preflight
- perf JSON parser
- event grouping
- environment collection
- calibration
- unit tests

산출:
`counterbouncer run calibration ...` 동작

## Week 2 — Real workload adapters
- PARSEC setup
- PARSEC 4 workloads
- CloudSuite 1 workload
- result parser
- experiment manifest

산출:
real workload raw runs 저장

## Week 3 — Quality engine / experiments
- contamination matrix
- threshold freeze
- holdout evaluation
- verdict/evidence

산출:
전체 experiment table

## Week 4 — Analysis / portfolio
- Azure dataset analysis
- plots
- failure analysis
- README
- reproducibility script
- technical report

추가 기능은 Week 4 core 결과가 끝난 뒤만 허용.

---

# 24. 면접에서 방어해야 할 질문

반드시 답을 준비한다.

1. PMU와 hardware counter는 무엇인가?
2. `perf stat`이 multiplexing을 왜 하는가?
3. `pcnt-running`은 무엇을 의미하는가?
4. event group이 필요한 이유는?
5. IPC 계산의 한계는?
6. cache generic event가 CPU마다 다를 수 있는 이유는?
7. 왜 metric ground truth를 주장하지 않는가?
8. CLEAN run의 정의는 무엇인가?
9. CPU affinity가 왜 필요한가?
10. SMT sibling contention이 왜 영향을 주는가?
11. variance가 높다고 항상 잘못된 측정인가?
12. quality threshold를 어떻게 정했는가?
13. 왜 Azure dataset은 validation이지 ground truth가 아닌가?
14. CounterBouncer와 perf/LIKWID의 차이는?
15. 실제 CXL counter에 적용하려면 무엇이 추가되어야 하는가?

---

# 25. 최종 이력서 문구 템플릿

실제 결과 수치가 확보된 이후에만 숫자를 채운다.

> **CounterBouncer — PMU 성능 측정 Quality Gate 개발**  
> PARSEC·CloudSuite 실제 workload에서 Linux PMU counter, scheduling ratio, CPU migration, 반복 측정 분산과 실행환경을 함께 수집해 측정 결과의 사용 가능성을 판정하는 품질 검증 계층을 구현했습니다. PMU multiplexing·SMT/메모리 contention 등 실제 시스템 조건에서 측정 안정성과 application outcome 변화를 비교하고, 판정 근거를 machine-readable하게 제공했습니다.

금지:
- “PMU 오류를 완벽히 탐지”
- “모든 CPU에서 정확”
- 측정하지 않은 개선율 삽입

---

# 26. 공식/1차 참고 소스

구현 시 아래 소스를 먼저 본다.

1. Linux perf stat
   - https://man7.org/linux/man-pages/man1/perf-stat.1.html
2. Linux perf event groups / multiplexing
   - https://github.com/torvalds/linux/blob/master/tools/perf/Documentation/perf-list.txt
3. PARSEC
   - https://github.com/csail-csg/parsec
4. PARSEC setup reference
   - https://github.com/cirosantilli/parsec-benchmark
5. CloudSuite 4.0
   - https://github.com/parsa-epfl/cloudsuite
6. CloudSuite Web Serving
   - https://github.com/parsa-epfl/cloudsuite/blob/main/docs/benchmarks/web-serving.md
7. Azure VM Noise Dataset 2024
   - https://github.com/Azure/AzurePublicDataset/blob/master/AzureVMNoiseDataset2024.md
8. STREAM
   - https://github.com/jeffhammond/STREAM
9. uarch-bench
   - https://github.com/travisdowns/uarch-bench

---

# 27. 하위 에이전트 최종 행동 계약

하위 에이전트는 다음을 반드시 지킨다.

- 실제 benchmark를 설치/실행하기 전 성능 결과를 생성하지 않는다.
- benchmark setup이 어려워도 synthetic으로 몰래 대체하지 않는다.
- 프로젝트를 profiler/웹 dashboard/AI diagnosis로 바꾸지 않는다.
- CounterBouncer의 핵심 산출물은 `quality verdict + evidence + real workload experiment`다.
- 구현 범위를 줄여야 할 경우 UI/부가기능부터 제거하고 핵심 실험을 남긴다.
- “측정값이 틀렸다” 대신 “이번 측정은 진단 근거로 사용하기에 조건이 불충분하다”라는 표현을 우선한다.
- 모든 결과는 commit SHA, machine info, command, raw output과 연결 가능해야 한다.
- 측정하지 않은 숫자는 절대 작성하지 않는다.
