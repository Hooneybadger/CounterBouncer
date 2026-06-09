#!/usr/bin/env python3
"""Collect calibration before any holdout; freeze candidates deterministically.

v1 freeze lives in configs/experiment.yaml and must not be retuned.
v2: --policy configs/experiment_v2.yaml --output artifacts/calibration-v2
"""
import argparse
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', default='configs/experiment.yaml')
    parser.add_argument('--output', default='artifacts/calibration')
    parser.add_argument('--seed', type=int, default=20260608)
    parser.add_argument('--repeats', type=int, default=10)
    parser.add_argument('--cpus', default='2')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    policy_path = root / args.policy
    policy = yaml.safe_load(policy_path.read_text())
    if policy['status'] == 'frozen':
        raise SystemExit(f'Already frozen ({policy_path}); refusing to retune')
    output = root / args.output
    conditions = [('branch', 'predictable', 'CLEAN'), ('branch', 'random', 'CLEAN'),
                  ('cache', 'small', 'CLEAN'), ('cache', 'large', 'CLEAN'), ('memory', 'stream', 'CLEAN'),
                  ('branch', 'random', 'MULTIPLEX'), ('branch', 'random', 'SMT'), ('memory', 'stream', 'MEMORY')]
    jobs = [(name, mode, condition, rep) for name, mode, condition in conditions for rep in range(args.repeats)]
    random.Random(args.seed).shuffle(jobs)
    for name, mode, condition, rep in jobs:
        run_id = f'{name}-{mode}-{condition.lower()}-r{rep:02d}'
        target = output / run_id / 'run.json'
        if target.exists():
            if json.loads(target.read_text()).get('status') != 'complete':
                raise SystemExit(f'Incomplete run: {target}; preserve and investigate')
            continue
        r = measure(make(name, mode), condition, run_id, output, policy_path, cpus=args.cpus)
        quality = r['quality']
        print(run_id, r['returncode'], quality.get('integrity'), quality.get('context'),
              quality.get('verdict'), flush=True)

    summary = {}
    for name, mode, condition in conditions:
        runs = [json.loads(p.read_text()) for p in output.glob(f'{name}-{mode}-{condition.lower()}-*/run.json')]
        if any(r['returncode'] != 0 or not r['workload']['outcome'] for r in runs):
            raise SystemExit('Calibration failed; refusing freeze')
        summary[f'{name}-{mode}-{condition}'] = summarize(r['workload']['outcome']['runtime_s'] for r in runs)
    cv = max(v['cv'] for k, v in summary.items() if k.endswith('-CLEAN'))
    runtime_degrade = max(.05, 3 * cv)
    runtime_reject = max(.20, 2 * runtime_degrade)
    policy['policy']['cv_runtime_degrade'] = runtime_degrade
    policy['policy']['cv_runtime_reject'] = runtime_reject
    # Keep v1 key name as an alias of the batch-runtime cutoff only.
    policy['policy']['cv_degrade'] = runtime_degrade
    policy['policy']['cv_reject'] = runtime_reject
    if policy['policy'].get('cv_latency_degrade') is None:
        raise SystemExit('Declare cv_latency_degrade in the draft policy before freeze; do not copy v1 CloudSuite holdout')
    policy['status'] = 'frozen'
    policy['frozen_at'] = now()
    policy['calibration_summary'] = summary
    policy['calibration_run_hashes'] = {str(p.relative_to(root)): sha256(p) for p in sorted(output.glob('*/run.json'))}
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False))
    save(output / 'freeze.json', {'timestamp': now(), 'policy_sha256': sha256(policy_path), 'summary': summary,
                                   'cv_runtime_degrade': runtime_degrade, 'cv_runtime_reject': runtime_reject,
                                   'cv_latency_degrade': policy['policy']['cv_latency_degrade'],
                                   'cv_latency_reject': policy['policy']['cv_latency_reject']})
    print('FROZEN', sha256(policy_path), flush=True)


if __name__ == '__main__':
    main()
