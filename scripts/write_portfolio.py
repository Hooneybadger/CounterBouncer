#!/usr/bin/env python3
"""Print campaign counts from measured artifacts. Does not write README."""
from pathlib import Path
from collections import Counter
import json
import statistics
import yaml

root = Path(__file__).resolve().parents[1]
report = json.loads((root / 'artifacts/analysis/report.json').read_text())
policy = yaml.safe_load((root / 'configs/experiment.yaml').read_text())
azure = json.loads((root / 'artifacts/azure/metadata.json').read_text())
audit = json.loads((root / 'artifacts/completion-audit.json').read_text())
runs = report['runs']
counts = Counter(r['quality_with_stability']['verdict'] for r in runs)
reasons = Counter(
    e['code'] for r in runs for e in r['quality_with_stability']['reasons']
)
calibration = [
    json.loads(p.read_text())
    for p in sorted((root / 'artifacts/calibration').glob('*/run.json'))
]
print('README is hand-maintained; this script does not overwrite it.')
print(f"audit={audit['status']} runs={len(runs)} verdicts={dict(counts)}")
print(f"frozen_at={policy['frozen_at']} calibration_runs={len(calibration)}")
print(f"reasons={dict(reasons)}")
print(
    f"azure files={azure['files']} observations={azure['observations']} "
    f"matched={azure['matched_partitions']}"
)
# Keep a cheap calibration sanity print so a missing artifact still fails closed.
for name, mode, event in [
    ('branch', 'predictable', 'branch-misses'),
    ('branch', 'random', 'branch-misses'),
    ('cache', 'small', 'cache-misses'),
    ('cache', 'large', 'cache-misses'),
]:
    values = [
        e['value']
        for r in calibration
        if r['condition'] == 'CLEAN'
        and r['workload']['name'] == name
        and r['workload']['input'] == mode
        for e in r['events']
        if e['name'] == f'cpu_core/{event}/'
    ]
    print(f'{name}/{mode} median {event}={statistics.median(values):,.1f}')
