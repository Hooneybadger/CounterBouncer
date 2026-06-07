# 완료 점검

기계 검사는 `python scripts/audit_results.py` → `artifacts/completion-audit.json`이다. 그 파일이 통과하기 전에는 이 표를 완료로 보지 않는다. `artifacts/`는 git에 없다.

2026-09-08: `artifacts/completion-audit.json` 상태 **PASS** (실제 애플리케이션 225회, 문제 0).

| 명세 요구 | 근거 |
|---|---|
| Bare-metal preflight | `artifacts/preflight/authorized/system.json` |
| perf parser 테스트 | `tests/test_perf_parser.py`와 테스트 출력 |
| PARSEC 실제 애플리케이션 4종 | native-holdout-v1, blackscholes/canneal/dedup/streamcluster |
| CloudSuite 실제 워크로드 | native-holdout-v1, data-caching |
| CLEAN + 오염 조건 최소 3개 | manifest: CLEAN/MULTIPLEX/SMT/MEMORY/UNPINNED |
| 원시 출력 보존 | 각 run의 `perf.jsonl`/`stdout.txt`/`stderr.txt` + SHA256 |
| 기계가 읽는 quality 이유 | `run.json` quality, `report.json` quality_with_stability |
| Calibration / holdout 분리 | `configs/experiment.yaml` `frozen_at` + calibration 해시 |
| Azure 외부 분석 | `artifacts/azure/dispersion.csv`, `metadata.json` |
| Figure 5장 | `artifacts/figures/figure1`–`figure5` (PNG·PDF), GitHub용 복사 `docs/figures/` |
| 재현 매니페스트 | `experiments/manifest.yaml`, `experiments/README.md` |
| 한계 | `docs/limitations.md` |
| 최종 성능값을 지어내지 않음 | 결과는 측정 run에서만. 단위 테스트 fixture는 별도 |

선택 항목 E5(frequency/power)와 upstream PR은 완료 조건이 아니다. 겹쳐서 버린 calibration은 `artifacts/calibration-development-overlap`에 남아 있다.
