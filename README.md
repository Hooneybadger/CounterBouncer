# CounterBouncer

[![CI](https://github.com/Hooneybadger/CounterBouncer/actions/workflows/ci.yml/badge.svg)](https://github.com/Hooneybadger/CounterBouncer/actions/workflows/ci.yml)

A bouncer in front of Linux `perf stat` PMU numbers: whether they are
fit to feed a performance diagnosis.

The name is the job. **"Did it get slower?" and "can I trust this
measurement?" are different questions.** Not a profiler. It will not
find your bottleneck.

Research and experiment tooling. Not a wrap-any-command CLI.
`bouncer run` drives local calibration kernels only.

## Problem

A counter that printed is not a number you can trust. Finishing in
the usual wall time does not mean coverage was enough, and good
coverage does not mean the run was clean.

The gate has two axes. The one-word `ACCEPT` / `DEGRADED` /
`REJECT` is only the collapse of those axes.

| Measurement integrity | Experiment context | Use |
| --- | --- | --- |
| VALID | CONTROLLED | diagnosis and comparison |
| VALID | CONTAMINATED | measurement holds; compare with care |
| INVALID | (any) | do not diagnose from it |

## Results

`native-holdout-v2` is four PARSEC native apps plus CloudSuite Data
Caching, 270 runs, on an i9-14900K bare metal. Warmups are separate.
Zero launch failures. Integrity: VALID 160, INVALID 110. Collapsed
verdict: ACCEPT 70, DEGRADED 90, REJECT 110. The 225-run
`native-holdout-v1` is kept as a retrospective.

| Condition | Integrity | Context | Application |
| --- | --- | --- | --- |
| CLEAN | mostly VALID | mostly CONTROLLED | baseline |
| MULTIPLEX | INVALID | CONTROLLED (PARSEC) | runtime ~ CLEAN |
| SMT | VALID | CONTAMINATED | up to +61.8% |
| MEMORY | VALID | CONTAMINATED | up to +73.8% |
| PCORE | VALID | CONTROLLED | ~ CLEAN |
| HYBRID | INVALID | UNKNOWN | CloudSuite p99 +113.1% |

INVALID is not "the value is wrong." MULTIPLEX missed the coverage
bar (`pcnt-running` median 30%). REFERENCE IPC is blackscholes
+0.02% and swaptions -0.22%.

All 30 CloudSuite runs in `native-holdout-v2` are INVALID: server
threads left the pin. `native-cloudsuite-v2.1` pins those threads
and adds CLEAN x5 (VALID/CONTROLLED) and MEMORY x5
(VALID/CONTAMINATED).

Aggregates and raw `perf.jsonl` are not in git. They live under
local `artifacts/`.

## Unit tests

```console
python3 -m venv .venv
.venv/bin/pip install -e '.[analysis,test]'
.venv/bin/python -m unittest discover -s tests -v
```

Tests use fixtures only. GitHub Actions runs the same suite.

## Measurement smoke

Needs Linux and `perf` permission. Default pin is `2,4,6,8`. Other
machines need their topology checked. This command is one
calibration kernel, not PARSEC or CloudSuite.

```console
bash scripts/build_calibration.sh
.venv/bin/bouncer run calibration branch --mode predictable \
  --condition CLEAN --run-id smoke-branch --output artifacts/smoke
```

PARSEC and CloudSuite reproduction:
[experiments/README.md](experiments/README.md).

## How it runs

![Measurement pipeline](docs/figures/figure1_architecture.png)

PARSEC is the official native binary, including init and I/O.
CloudSuite attaches to the memcached server host PID. Migrations
inside the pin do not, by themselves, drop integrity. Conditions:
CLEAN, MULTIPLEX, SMT, MEMORY, PCORE, HYBRID. REFERENCE is the
minimal group `{cpu_core/cycles, cpu_core/instructions}`. It is not
ground truth.

Figures: [docs/figures](docs/figures).

## Docs

- [Results report](docs/technical_report.md)
- [Method](docs/methodology.md)
- [Limitations](docs/limitations.md)
- [Benchmark selection](docs/benchmark_selection.md)
- [Reproduce](experiments/README.md)
- [Sources](docs/sources.md)

## Later

v0.3.0 is productization (arbitrary command, host topology probe).
That is not a new holdout, and this version does not do it.

## License

MIT. [LICENSE](LICENSE). Azure VM Noise Dataset is CC-BY.
