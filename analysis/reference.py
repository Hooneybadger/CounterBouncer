#!/usr/bin/env python3
"""Compare minimal-group REFERENCE IPC against multiplexed IPC. Not absolute ground truth."""
from collections import defaultdict
from pathlib import Path
import argparse
import json
import sys
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from counterbouncer.model import save
from counterbouncer.quality.stability import summarize

parser = argparse.ArgumentParser()
parser.add_argument('--manifest', default='experiments/manifest_reference.yaml')
parser.add_argument('--output', default='artifacts/analysis/reference-v2.json')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
manifest = yaml.safe_load((root / args.manifest).read_text())
runs = []
for path in sorted((root / 'artifacts/experiments' / manifest['experiment_id']).glob('*/run.json')):
    runs.append(json.loads(path.read_text()))

groups = defaultdict(list)
for run in runs:
    if run.get('status') != 'complete' or not run['workload'].get('outcome'):
        continue
    groups[(run['workload']['name'], run['condition'])].append(run)

workloads = sorted({name for name, _ in groups})
result = {'reference_kind': 'high-coverage minimal-event group', 'not': 'absolute ground truth', 'workloads': {}}
points = []
for name in workloads:
    ref = groups.get((name, 'REFERENCE'), [])
    mux = groups.get((name, 'MULTIPLEX'), [])
    ref_ipc = [r['metrics']['ipc'] for r in ref if r.get('metrics', {}).get('ipc') is not None]
    mux_ipc = [r['metrics']['ipc'] for r in mux if r.get('metrics', {}).get('ipc') is not None]
    ref_stats = summarize(ref_ipc)
    mux_stats = summarize(mux_ipc)
    ref_median = ref_stats['median']
    def min_running(run):
        ratios = [e['pcnt_running'] for e in run['events']
                  if e['name'].startswith('cpu_core/') and e.get('pcnt_running') is not None]
        return min(ratios) if ratios else None
    deviations = []
    for run in mux:
        ipc = run.get('metrics', {}).get('ipc')
        running = min_running(run)
        if ipc is None or ref_median in (None, 0):
            continue
        deviation = (ipc - ref_median) / ref_median
        point = {'run_id': run['run_id'], 'workload': name, 'ipc': ipc,
                 'pcnt_running': running, 'reference_median_ipc': ref_median,
                 'relative_deviation': deviation}
        deviations.append(point)
        points.append(point)
    result['workloads'][name] = {
        'reference': {'n': len(ref_ipc), **{k: ref_stats[k] for k in ('median', 'mean', 'cv', 'mad')}},
        'multiplex': {'n': len(mux_ipc), **{k: mux_stats[k] for k in ('median', 'mean', 'cv', 'mad')},
                      'pcnt_running_median': summarize(min_running(r) for r in mux if min_running(r) is not None)['median']},
        'points': deviations,
    }
result['points'] = points
save(root / args.output, result)
print(json.dumps({name: {k: v[k] for k in ('reference', 'multiplex') if k in v}
                    for name, v in result['workloads'].items()}, indent=2, default=str))
