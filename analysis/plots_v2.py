#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

root = Path(__file__).resolve().parents[1]
out = root / 'artifacts/figures'
docs_fig = root / 'docs/figures'
out.mkdir(parents=True, exist_ok=True)
docs_fig.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'axes.unicode_minus': False, 'font.size': 10})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(out / f'{name}.png', dpi=180)
    fig.savefig(out / f'{name}.pdf')
    fig.savefig(docs_fig / f'{name}.png', dpi=180)
    plt.close(fig)


parser = argparse.ArgumentParser()
parser.add_argument('--report', default='artifacts/analysis/report-native-holdout-v2.json')
parser.add_argument('--reference', default='artifacts/analysis/reference-v2.json')
args = parser.parse_args()

fig, ax = plt.subplots(figsize=(11, 4.2))
ax.set(xlim=(0, 12), ylim=(0, 4.2))
ax.axis('off')
boxes = [
    (0.2, 2.4, 'Measurement integrity\nVALID / DEGRADED / INVALID'),
    (4.2, 2.4, 'Experiment context\nCONTROLLED / CONTAMINATED / UNKNOWN'),
    (8.2, 2.4, 'Usability\nCOMPARABLE or not'),
    (0.2, 0.3, 'PMU scheduling, groups,\nhybrid coverage'),
    (4.2, 0.3, 'SMT / memory / placement\n/ resident project server'),
]
for x, y, label in boxes:
    ax.add_patch(FancyBboxPatch((x, y), 3.6, 1.4, boxstyle='round,pad=0.1', facecolor='#e6eef5', edgecolor='#304e6a'))
    ax.text(x + 1.8, y + 0.7, label, ha='center', va='center')
ax.set_title('v2 quality gate: two axes, not one ACCEPT/DEGRADED/REJECT score')
save(fig, 'figure_v2_architecture')

report_path = root / args.report
if report_path.exists():
    report = json.loads(report_path.read_text())
    rows = []
    for r in report['runs']:
        outcome = r['workload'].get('outcome') or {}
        ratios = [e['pcnt_running'] for e in r['events'] if e['name'].startswith('cpu_core/') and e['pcnt_running'] is not None]
        q = r.get('quality_with_stability') or r['quality']
        rows.append({'workload': r['workload']['name'], 'suite': r['workload']['suite'],
                     'condition': r['condition'], 'integrity': q.get('integrity'),
                     'context': q.get('context'), 'usability': q.get('usability'),
                     'runtime_s': outcome.get('runtime_s'), 'throughput_rps': outcome.get('throughput_rps'),
                     'p99_latency_ms': outcome.get('p99_latency_ms'),
                     'ipc': r.get('metrics', {}).get('ipc'),
                     'running_pct': min(ratios) if ratios else None})
    frame = pd.DataFrame(rows)
    conditions = [c for c in ['CLEAN', 'MULTIPLEX', 'SMT', 'MEMORY', 'PCORE', 'HYBRID', 'REFERENCE']
                  if c in set(frame.condition)]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    if conditions:
        pd.crosstab(frame.condition, frame.integrity).reindex(index=conditions).plot.bar(ax=axes[0], stacked=True)
        pd.crosstab(frame.condition, frame.context).reindex(index=conditions).plot.bar(ax=axes[1], stacked=True)
    axes[0].set(title='Measurement integrity', ylabel='Runs')
    axes[1].set(title='Experiment context')
    for ax in axes:
        ax.tick_params(axis='x', rotation=25)
    save(fig, 'figure_v2_axes')

    frame['outcome_deviation_pct'] = np.nan
    for name, group in frame.groupby('workload'):
        metric = 'throughput_rps' if group.suite.iloc[0] == 'cloudsuite' else 'runtime_s'
        baseline = group.loc[group.condition == 'CLEAN', metric].median()
        if pd.notna(baseline) and baseline > 0:
            sign = -1 if metric == 'throughput_rps' else 1
            frame.loc[group.index, 'outcome_deviation_pct'] = sign * (group[metric] / baseline - 1) * 100
    fig, ax = plt.subplots(figsize=(11, 4.5))
    rng = np.random.default_rng(42)
    labels = ['COMPARABLE', 'VALID_BUT_CONTAMINATED', 'DEGRADED_COUNTERS', 'UNUSABLE']
    present = [u for u in labels if u in set(frame.usability.dropna())]
    extra = [u for u in sorted(frame.usability.dropna().unique()) if u not in present]
    order = present + extra
    for i, usability in enumerate(order):
        subset = frame[frame.usability == usability]
        ax.scatter(i + rng.uniform(-0.15, 0.15, len(subset)), subset.outcome_deviation_pct, s=20, alpha=.6)
    ax.axhline(0, color='grey', linewidth=1)
    ax.set(xticks=range(len(order)), xticklabels=order,
           ylabel='Outcome deviation vs CLEAN median (%)',
           title='Usability vs outcome (association, not PMU accuracy)')
    ax.tick_params(axis='x', rotation=20)
    save(fig, 'figure_v2_outcome')
    frame.to_csv(root / 'artifacts/analysis/runs-v2.csv', index=False)

ref_path = root / args.reference
if Path(ref_path).exists():
    payload = json.loads(Path(ref_path).read_text())
    points = payload.get('points') or []
    fig, ax = plt.subplots(figsize=(8, 4.8))
    if points:
        by_name = {}
        for point in points:
            by_name.setdefault(point['workload'], {'x': [], 'y': []})
            if point.get('pcnt_running') is not None and point.get('relative_deviation') is not None:
                by_name[point['workload']]['x'].append(point['pcnt_running'])
                by_name[point['workload']]['y'].append(100 * point['relative_deviation'])
        for name, xy in by_name.items():
            ax.scatter(xy['x'], xy['y'], label=name, alpha=.7)
    ax.axhline(0, color='grey', linewidth=1)
    ax.set(xlabel='Multiplexed run minimum cpu_core pcnt-running (%)',
           ylabel='IPC relative deviation vs REFERENCE median (%)',
           title='Minimal-group reference vs multiplex (not absolute ground truth)')
    ax.legend()
    save(fig, 'figure_v2_reference')

print('Wrote v2 figures that had available inputs')
