#!/usr/bin/env python3
from pathlib import Path
import sys
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from counterbouncer.report import build_report

root = Path(__file__).resolve().parents[1]
policy = yaml.safe_load((root / 'configs/experiment.yaml').read_text())
report = build_report(sorted((root / 'artifacts/experiments').glob('*/*/run.json')),
                      policy['policy'], root / 'artifacts/analysis/report.json')
print(f"Analyzed {len(report['runs'])} attempts in {len(report['groups'])} groups")
