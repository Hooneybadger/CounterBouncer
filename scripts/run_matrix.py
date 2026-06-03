#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import random
import sys
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from counterbouncer.runner import measure
from counterbouncer.workloads import parsec, cloudsuite
from counterbouncer.model import save, sha256, now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', default='experiments/manifest.yaml')
    parser.add_argument('--suite', choices=['parsec', 'cloudsuite', 'all'], default='all')
    parser.add_argument('--workload')
    args = parser.parse_args()
    manifest = yaml.safe_load(Path(args.manifest).read_text())
    policy = yaml.safe_load(Path(manifest['policy']).read_text())
    if policy['status'] != 'frozen':
        raise SystemExit('Freeze calibration before holdout')
    directory = Path('artifacts/experiments') / manifest['experiment_id']
    directory.mkdir(parents=True, exist_ok=True)
    manifest_file = directory / 'manifest.json'
    if manifest_file.exists():
        if json.loads(manifest_file.read_text())['manifest_sha256'] != sha256(args.manifest):
            raise SystemExit('Manifest changed: use a new experiment ID')
    else:
        save(manifest_file, {'created': now(), 'manifest': manifest, 'manifest_sha256': sha256(args.manifest),
                             'policy_sha256': sha256(manifest['policy'])})
    suites = ['parsec', 'cloudsuite'] if args.suite == 'all' else [args.suite]
    rng = random.Random(manifest['seed'])
    for suite in suites:
        names = manifest[suite].get('workloads', [manifest[suite].get('workload')])
        for name in names:
            if args.workload and args.workload != name:
                continue
            def workload(condition):
                return parsec.make(name) if suite == 'parsec' else cloudsuite.make(condition,
                       manifest[suite]['duration_s'], manifest[suite]['target_rps'])
            jobs = [('CLEAN', f'{suite}-{name}-warmup', 'artifacts/warmups')]
            for repeat in range(manifest[suite]['repeats']):
                conditions = list(manifest['conditions'])
                rng.shuffle(conditions)
                jobs.extend((c, f'{suite}-{name}-{c.lower()}-r{repeat:02d}', directory) for c in conditions)
            for condition, run_id, output in jobs:
                if Path('artifacts/setup/STOP_MATRIX').exists():
                    print('STOP_MATRIX present; exiting before', run_id, flush=True)
                    return
                existing = Path(output) / run_id / 'run.json'
                if existing.exists():
                    if json.loads(existing.read_text()).get('status') != 'complete':
                        raise SystemExit(f'Incomplete run preserved at {existing}')
                    continue
                result = measure(workload(condition), condition, run_id, output, manifest['policy'], cpus=manifest['cpus'])
                if 'warmup' in run_id and (not result['workload']['outcome'] or result['returncode'] not in result['accepted_returncodes']):
                    raise SystemExit(f'Warmup failed: {run_id}; preserve and investigate')
                print(now(), run_id, result['returncode'], result['quality']['verdict'],
                      result['wall_runtime_s'], flush=True)


if __name__ == '__main__':
    main()
