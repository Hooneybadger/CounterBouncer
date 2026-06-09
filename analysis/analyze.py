#!/usr/bin/env python3
from pathlib import Path
import argparse
import sys
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from counterbouncer.report import build_report

parser = argparse.ArgumentParser()
parser.add_argument('--manifest', default='experiments/manifest.yaml')
parser.add_argument('--output')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
manifest = yaml.safe_load((root / args.manifest).read_text())
policy = yaml.safe_load((root / manifest['policy']).read_text())
experiment = manifest['experiment_id']
output = Path(args.output) if args.output else root / 'artifacts/analysis' / f'report-{experiment}.json'
if args.manifest == 'experiments/manifest.yaml' and not args.output:
    output = root / 'artifacts/analysis/report.json'
paths = sorted((root / 'artifacts/experiments' / experiment).glob('*/run.json'))
report = build_report(paths, policy['policy'], output)
print(f"Analyzed {len(report['runs'])} attempts in {len(report['groups'])} groups -> {output}")
