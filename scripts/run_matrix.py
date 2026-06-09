#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import random
import sys
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from counterbouncer.host import project_containers_running, start_named_containers, server_container, client_container
from counterbouncer.runner import measure
from counterbouncer.workloads import parsec, cloudsuite
from counterbouncer.model import save, sha256, now
from counterbouncer.topology import affinity_for


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', default='experiments/manifest.yaml')
    parser.add_argument('--suite', choices=['parsec', 'cloudsuite', 'all'], default='all')
    parser.add_argument('--workload')
    parser.add_argument('--require-clean-host', action='store_true',
                        help='Refuse PARSEC if project memcached/client containers are running')
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
    if 'parsec' in suites and args.require_clean_host:
        resident = project_containers_running()
        if resident:
            raise SystemExit(f'Project containers still running: {resident}. Run scripts/prepare_baseline.py first.')
    if 'cloudsuite' in suites:
        start_named_containers([server_container(), client_container()])
    rng = random.Random(manifest['seed'])
    pin = manifest['cpus']
    smt = manifest.get('smt_siblings', '3,5,7,9')
    mem = manifest.get('memory_interference_cpus', '24,25,26,27')
    for suite in suites:
        names = manifest[suite].get('workloads', [manifest[suite].get('workload')])
        for name in names:
            if args.workload and args.workload != name:
                continue

            def workload(condition):
                cpus = affinity_for(condition, pin)
                if suite == 'parsec':
                    return parsec.make(name)
                return cloudsuite.make(condition, manifest[suite]['duration_s'],
                                        manifest[suite]['target_rps'], cpus=cpus)

            warmup_dir = Path('artifacts/warmups') / manifest['experiment_id']
            warmup_condition = 'CLEAN' if 'CLEAN' in manifest['conditions'] else manifest['conditions'][0]
            jobs = [(warmup_condition, f'{suite}-{name}-warmup', warmup_dir)]
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
                result = measure(workload(condition), condition, run_id, output, manifest['policy'],
                                 cpus=affinity_for(condition, pin), smt_cpus=smt, memory_cpus=mem)
                if 'warmup' in run_id and (not result['workload']['outcome'] or result['returncode'] not in result['accepted_returncodes']):
                    raise SystemExit(f'Warmup failed: {run_id}; preserve and investigate')
                quality = result['quality']
                print(now(), run_id, result['returncode'],
                      quality.get('integrity'), quality.get('context'), quality.get('usability'),
                      result['wall_runtime_s'], flush=True)


if __name__ == '__main__':
    main()
