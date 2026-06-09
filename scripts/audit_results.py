#!/usr/bin/env python3
"""Fail closed on incomplete portfolio evidence; preserve every failed run."""
import argparse
from pathlib import Path
import json
import sys
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from counterbouncer.model import sha256, save

DEFAULT_FIGURES = ['figure1_architecture', 'figure2_multiplexing', 'figure3_stability',
                    'figure4_verdicts', 'figure5_outcome']
V2_FIGURES = ['figure_v2_architecture', 'figure_v2_axes', 'figure_v2_outcome',
              'figure_v2_reference']

parser = argparse.ArgumentParser()
parser.add_argument('--manifest', default='experiments/manifest.yaml')
parser.add_argument('--output')
parser.add_argument('--require-azure', action='store_true')
parser.add_argument('--skip-azure', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
manifest = yaml.safe_load((root / args.manifest).read_text())
policy_path = root / manifest['policy']
policy = yaml.safe_load(policy_path.read_text())
problems = []
runs = [json.loads(p.read_text()) for p in (root / 'artifacts/experiments' / manifest['experiment_id']).glob('*/run.json')]
if policy['status'] != 'frozen':
    problems.append('policy not frozen')
for suite in ['parsec', 'cloudsuite']:
    if suite not in manifest:
        continue
    names = manifest[suite].get('workloads', [manifest[suite].get('workload')])
    for name in names:
        for condition in manifest['conditions']:
            group = [r for r in runs if r['workload']['suite'] == suite and r['workload']['name'] == name and r['condition'] == condition]
            if len(group) < manifest[suite]['repeats']:
                problems.append(f'{suite}/{name}/{condition}: {len(group)} attempts')
            if sum(bool(r['workload'].get('outcome')) and r.get('returncode') in r['accepted_returncodes'] for r in group) < manifest[suite]['repeats']:
                problems.append(f'{suite}/{name}/{condition}: insufficient successful outcomes')
        warmup = root / 'artifacts/warmups' / manifest['experiment_id'] / f'{suite}-{name}-warmup' / 'run.json'
        if manifest.get('experiment_id') == 'native-holdout-v1':
            warmup = root / 'artifacts/warmups' / f'{suite}-{name}-warmup' / 'run.json'
        if not warmup.exists() or json.loads(warmup.read_text()).get('status') != 'complete':
            problems.append(f'{suite}/{name}: missing completed warmup')
for r in runs:
    if r.get('status') != 'complete':
        problems.append(f"{r['run_id']}: incomplete")
        continue
    if not r['git_commit'] or r['policy_sha256'] != sha256(policy_path):
        problems.append(f"{r['run_id']}: provenance/policy mismatch")
    if r['timestamp'] <= policy['frozen_at']:
        problems.append(f"{r['run_id']}: precedes policy freeze")
    quality = r['quality']
    comparable = quality.get('usability') == 'COMPARABLE' or (
        'usability' not in quality and quality.get('verdict') == 'ACCEPT')
    if not comparable and not quality.get('reasons'):
        problems.append(f"{r['run_id']}: missing reason code")
    directory = root / 'artifacts/experiments' / manifest['experiment_id'] / r['run_id']
    for file, digest in r['raw_files'].items():
        if not (directory / file).exists() or sha256(directory / file) != digest:
            problems.append(f"{r['run_id']}: raw hash mismatch {file}")
for p, digest in policy.get('calibration_run_hashes', {}).items():
    if sha256(root / p) != digest:
        problems.append(f'calibration hash mismatch: {p}')
figures = manifest.get('audit_figures', V2_FIGURES if manifest.get('schema_version') == 2 else DEFAULT_FIGURES)
for name in figures:
    if not (root / 'artifacts/figures' / f'{name}.png').exists():
        problems.append(f'missing figure {name}')
if args.skip_azure:
    require_azure = False
elif args.require_azure:
    require_azure = True
else:
    require_azure = manifest.get('schema_version', 1) == 1
if require_azure and not (root / 'artifacts/azure/metadata.json').exists():
    problems.append('missing Azure external analysis')
experiment = manifest['experiment_id']
out = Path(args.output) if args.output else root / (
    'artifacts/completion-audit.json' if experiment == 'native-holdout-v1' else f'artifacts/completion-audit-{experiment}.json')
result = {'status': 'PASS' if not problems else 'INCOMPLETE', 'real_runs': len(runs),
          'experiment_id': experiment, 'problems': problems}
save(out, result)
print(json.dumps(result, indent=2))
raise SystemExit(bool(problems))
