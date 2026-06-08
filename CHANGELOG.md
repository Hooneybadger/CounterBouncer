# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer](https://semver.org/) for the Python package API,
not for measurement campaigns (those are named, e.g. `native-holdout-v1`).

## [0.1.0] — 2026-06-08

Published name: **CounterBouncer**. Python package `counterbouncer`, CLI `bouncer`.

### Added

- `perf stat -j` parser, quality gate, PARSEC and CloudSuite adapters
- Frozen calibration policy and `native-holdout-v1` campaign tooling
- Results report, GitHub-visible figure copies under `docs/figures/`, and contribution templates

Raw run artifacts are not shipped in git. The README is written for a first-time reader
and is not generated from the campaign tables.
