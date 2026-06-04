#!/usr/bin/env python3
from pathlib import Path
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
    # GitHub-visible copy. artifacts/ is gitignored.
    fig.savefig(docs_fig / f'{name}.png', dpi=180)
    plt.close(fig)

fig, ax = plt.subplots(figsize=(11, 4))
ax.set(xlim=(0, 11), ylim=(0, 4)); ax.axis('off')
boxes = [(0.1, 2, 'Real application\nPARSEC / CloudSuite'), (3.7, 2, 'perf stat JSON\nraw counters + scheduling'),
         (3.7, .2, 'Environment collector\naffinity / SMT / governor'), (7.4, 2, 'Quality gate\nhard + statistical evidence'),
         (7.4, .2, 'ACCEPT / DEGRADED / REJECT\nreason codes + provenance')]
for x, y, label in boxes:
    ax.add_patch(FancyBboxPatch((x, y), 3.2, 1.2, boxstyle='round,pad=0.1', facecolor='#e6eef5', edgecolor='#304e6a'))
    ax.text(x+1.6, y+.6, label, ha='center', va='center')
for a, b in [((3.3,2.6),(3.6,2.6)),((6.9,2.6),(7.3,2.6)),((5.3,1.4),(7.4,2.2)),((9,2),(9,1.4))]:
    ax.annotate('', xy=b, xytext=a, arrowprops={'arrowstyle':'->'})
save(fig, 'figure1_architecture')

report = json.loads((root / 'artifacts/analysis/report.json').read_text())
rows = []
for r in report['runs']:
    outcome = r['workload'].get('outcome') or {}
    ratios = [e['pcnt_running'] for e in r['events'] if e['name'].startswith('cpu_core/') and e['pcnt_running'] is not None]
    rows.append({'workload': r['workload']['name'], 'suite': r['workload']['suite'], 'condition': r['condition'],
                 'verdict': r['quality_with_stability']['verdict'], 'hard_verdict': r['quality']['verdict'],
                 'runtime_s': outcome.get('runtime_s'), 'throughput_rps': outcome.get('throughput_rps'),
                 'p99_latency_ms': outcome.get('p99_latency_ms'), 'ipc': r.get('metrics', {}).get('ipc'),
                 'running_pct': min(ratios) if ratios else None,
                 'requested_events': len(r['events']), 'run_id': r['run_id']})
frame = pd.DataFrame(rows)
frame.to_csv(root / 'artifacts/analysis/runs.csv', index=False)
conditions = ['CLEAN', 'MULTIPLEX', 'SMT', 'MEMORY', 'UNPINNED']
colors = {'CLEAN':'#387aab','MULTIPLEX':'#a54b53','SMT':'#bd8430','MEMORY':'#5b9465','UNPINNED':'#8065a9'}

fig, axes = plt.subplots(1, 2, figsize=(11, 4))
data = [frame.loc[frame.condition == c, 'running_pct'].dropna() for c in conditions]
axes[0].boxplot(data, tick_labels=conditions, showfliers=True)
axes[0].set(ylabel='Minimum PMU running (%)', title='Observed scheduling coverage')
ipc_cv = frame.groupby(['workload','condition']).ipc.agg(lambda s: s.std()/s.mean() if s.mean() else np.nan).unstack().reindex(columns=conditions)
ipc_cv.plot.bar(ax=axes[1], color=[colors[c] for c in conditions])
axes[1].set(ylabel='IPC coefficient of variation', title='Derived metric repeatability')
axes[0].tick_params(axis='x', rotation=25); axes[1].tick_params(axis='x', rotation=25)
save(fig, 'figure2_multiplexing')

stats = pd.DataFrame([{'workload':g['workload'],'condition':g['condition'], 'cv':g['outcome_statistics']['cv']} for g in report['groups']])
fig, ax = plt.subplots(figsize=(10, 5))
stats.pivot(index='workload', columns='condition', values='cv').reindex(columns=conditions).plot.bar(ax=ax, color=[colors[c] for c in conditions])
ax.set(ylabel='Outcome coefficient of variation',
       title='Real workload stability (PARSEC runtime; CloudSuite throughput CV is ~0 at fixed offered load)')
ax.tick_params(axis='x', rotation=20)
save(fig, 'figure3_stability')

fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, col, title in zip(axes, ['hard_verdict','verdict'], ['Per-run hard evidence','Hard + group stability evidence']):
    table = pd.crosstab(frame.condition,frame[col]).reindex(index=conditions,columns=['ACCEPT','DEGRADED','REJECT'],fill_value=0)
    table.plot.bar(stacked=True, ax=ax, color=['#569769','#d3a84b','#b55d60'])
    ax.set(ylabel='Number of measured runs', title=title); ax.tick_params(axis='x',rotation=25)
save(fig, 'figure4_verdicts')

frame['outcome_deviation_pct'] = np.nan
for name, group in frame.groupby('workload'):
    metric = 'throughput_rps' if group.suite.iloc[0] == 'cloudsuite' else 'runtime_s'
    baseline = group.loc[group.condition == 'CLEAN',metric].median()
    if pd.notna(baseline) and baseline > 0:
        sign = -1 if metric == 'throughput_rps' else 1
        frame.loc[group.index,'outcome_deviation_pct'] = sign*(group[metric]/baseline-1)*100
fig, (ax, latency_ax) = plt.subplots(1, 2, figsize=(12, 5))
rng = np.random.default_rng(42) # horizontal display jitter only; never alters measured values
for i, v in enumerate(['ACCEPT','DEGRADED','REJECT']):
    group = frame[frame.verdict == v]
    for name, subset in group.groupby('workload'):
        ax.scatter(i+rng.uniform(-.15,.15,len(subset)), subset.outcome_deviation_pct, s=20, alpha=.6,
                   label=name if i==0 else None)
ax.axhline(0,color='grey',linewidth=1)
ax.set(xticks=[0,1,2],xticklabels=['ACCEPT','DEGRADED','REJECT'],ylabel='Outcome degradation vs CLEAN median (%)',
       title='Verdict vs outcome (association, not PMU accuracy)')
cloud = frame[frame.suite == 'cloudsuite'].copy()
latency_baseline = cloud.loc[cloud.condition == 'CLEAN', 'p99_latency_ms'].median()
frame['p99_deviation_pct'] = np.nan
if pd.notna(latency_baseline) and latency_baseline > 0:
    frame.loc[cloud.index, 'p99_deviation_pct'] = (cloud.p99_latency_ms / latency_baseline - 1) * 100
for i, v in enumerate(['ACCEPT', 'DEGRADED', 'REJECT']):
    subset = frame[(frame.suite == 'cloudsuite') & (frame.verdict == v)]
    latency_ax.scatter(i+rng.uniform(-.1,.1,len(subset)), subset.p99_deviation_pct, s=24, alpha=.7)
latency_ax.axhline(0,color='grey',linewidth=1)
latency_ax.set(xticks=[0,1,2],xticklabels=['ACCEPT','DEGRADED','REJECT'],
               ylabel='Interval-p99 median deviation vs CLEAN (%)',title='CloudSuite latency outcome')
save(fig, 'figure5_outcome')
frame.to_csv(root / 'artifacts/analysis/runs.csv', index=False)
print('Generated five figures as PNG and PDF')
