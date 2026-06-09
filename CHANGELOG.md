# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer](https://semver.org/) for the Python package API,
not for measurement campaigns (those are named, e.g. `native-holdout-v1`).

## [0.2.1] - 2026-06-09

### Fixed

- After `docker update --cpuset-cpus`, pin memcached threads with `sched_setaffinity`.
  Ignore a thread's last-run CPU when it is outside the current affinity mask.

### Changed

- MULTIPLEX `INVALID` is a coverage-policy miss, not a claim that scaled IPC is wrong.
  REFERENCE deviations stay blackscholes +0.02% and swaptions -0.22%.
- Results report leads with v2/v2.1. v1 is a retrospective, not deleted.

### Added

- Complementary CloudSuite check `native-cloudsuite-v2.1` (CLEAN and MEMORY only).
  `configs/experiment_v2.yaml` is not retuned.
- Campaign aggregates, audits, and raw `perf.jsonl` kept in local
  `artifacts/` (not in git).

## [0.2.0] - 2026-06-09

### Changed

- Quality gate is two axes: measurement integrity (`VALID` / `DEGRADED` / `INVALID`) and
  experiment context (`CONTROLLED` / `CONTAMINATED` / `UNKNOWN`). The old one-word verdict is
  only a collapse of those axes.
- Within-pin `cpu-migrations` is no longer treated as measurement degradation.
- CloudSuite group variance uses latency/p99, not the batch-runtime CV cutoff.
- `native-holdout-v1` and `configs/experiment.yaml` stay frozen. v2 uses
  `configs/experiment_v2.yaml` and a new holdout.

### Added

- PCORE vs HYBRID conditions (v1 UNPINNED split), minimal-group REFERENCE measurements,
  placement sampling, and `scripts/prepare_baseline.py`.

## [0.1.0] - 2026-06-08

Published name: **CounterBouncer**. Python package `counterbouncer`, CLI `bouncer`.

### Added

- `perf stat -j` parser, quality gate, PARSEC and CloudSuite adapters
- Frozen calibration policy and `native-holdout-v1` campaign tooling
- Results report, GitHub-visible figure copies under `docs/figures/`, and contribution templates

