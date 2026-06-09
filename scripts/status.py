#!/usr/bin/env python3
"""Lightweight read-only status of a measurement campaign."""
from collections import Counter
from pathlib import Path
import argparse
import json
import yaml

parser = argparse.ArgumentParser()
parser.add_argument('--manifest', default='experiments/manifest.yaml')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
manifest = yaml.safe_load((root / args.manifest).read_text())
counts = Counter()
axes = Counter()
active = []
failed = []
for path in (root / 'artifacts/experiments' / manifest['experiment_id']).glob('*/run.json'):
    run = json.loads(path.read_text())
    if run.get('status') == 'complete':
        counts[run['workload']['name']] += 1
        quality = run.get('quality') or {}
        axes[f"{quality.get('integrity', quality.get('verdict'))}/{quality.get('context', '')}"] += 1
        if run.get('returncode') not in run.get('accepted_returncodes', [0]):
            failed.append(run['run_id'])
    else:
        active.append(run['run_id'])
expected = {}
for suite in ('parsec', 'cloudsuite'):
    if suite not in manifest:
        continue
    names = manifest[suite].get('workloads', [manifest[suite].get('workload')])
    for name in names:
        expected[name] = manifest[suite]['repeats'] * len(manifest['conditions'])
print(json.dumps({
    'experiment_id': manifest['experiment_id'],
    'completed_by_workload': dict(counts),
    'expected_by_workload': expected,
    'remaining': {name: expected[name] - counts.get(name, 0) for name in expected},
    'axes': dict(axes),
    'active': active,
    'execution_failures': failed,
}, indent=2))
