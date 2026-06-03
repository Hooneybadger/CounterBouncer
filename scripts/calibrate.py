#!/usr/bin/env python3
"""Collect calibration before any holdout; freeze candidates deterministically."""
import json
from pathlib import Path
import random
import sys
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from counterbouncer.runner import measure
from counterbouncer.workloads.calibration import make
from counterbouncer.model import now, save, sha256
from counterbouncer.quality.stability import summarize

root = Path(__file__).resolve().parents[1]
policy_path = root / 'configs/experiment.yaml'
policy = yaml.safe_load(policy_path.read_text())
if policy['status'] == 'frozen':
    raise SystemExit('Already frozen; refusing to retune holdout policy')
conditions = [('branch', 'predictable', 'CLEAN'), ('branch', 'random', 'CLEAN'),
              ('cache', 'small', 'CLEAN'), ('cache', 'large', 'CLEAN'), ('memory', 'stream', 'CLEAN'),
              ('branch', 'random', 'MULTIPLEX'), ('branch', 'random', 'SMT'), ('memory', 'stream', 'MEMORY')]
jobs = [(name, mode, condition, rep) for name, mode, condition in conditions for rep in range(10)]
random.Random(20260908).shuffle(jobs)
for name, mode, condition, rep in jobs:
    run_id = f'{name}-{mode}-{condition.lower()}-r{rep:02d}'
    target = root / 'artifacts/calibration' / run_id / 'run.json'
    if target.exists():
        if json.loads(target.read_text()).get('status') != 'complete':
            raise SystemExit(f'Incomplete run: {target}; preserve and investigate')
        continue
    r = measure(make(name, mode), condition, run_id, root / 'artifacts/calibration', policy_path, cpus='2')
    print(run_id, r['returncode'], r['quality']['verdict'], flush=True)

summary = {}
for name, mode, condition in conditions:
    runs = [json.loads(p.read_text()) for p in (root / 'artifacts/calibration').glob(f'{name}-{mode}-{condition.lower()}-*/run.json')]
    if any(r['returncode'] != 0 or not r['workload']['outcome'] for r in runs):
        raise SystemExit('Calibration failed; refusing freeze')
    summary[f'{name}-{mode}-{condition}'] = summarize(r['workload']['outcome']['runtime_s'] for r in runs)
cv = max(v['cv'] for k, v in summary.items() if k.endswith('-CLEAN'))
policy['policy']['cv_degrade'] = max(.05, 3 * cv)
policy['policy']['cv_reject'] = max(.20, 2 * policy['policy']['cv_degrade'])
policy['status'] = 'frozen'
policy['frozen_at'] = now()
policy['calibration_summary'] = summary
policy['calibration_run_hashes'] = {str(p.relative_to(root)): sha256(p) for p in sorted((root / 'artifacts/calibration').glob('*/run.json'))}
policy_path.write_text(yaml.safe_dump(policy, sort_keys=False))
save(root / 'artifacts/calibration/freeze.json', {'timestamp': now(), 'policy_sha256': sha256(policy_path), 'summary': summary})
print('FROZEN', sha256(policy_path), flush=True)
