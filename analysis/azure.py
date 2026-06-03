#!/usr/bin/env python3
"""External dispersion only: never used as PMU truth or gate accuracy labels."""
from pathlib import Path
import hashlib
import json
import subprocess
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[1]
repo = root / 'vendor/azure'
output = root / 'artifacts/azure'
output.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans', 'axes.unicode_minus':False})
rows = []
for path in sorted((repo / 'vm-noise-data').rglob('*.csv')):
    dimensions = dict(part.split('=', 1) for part in path.relative_to(repo / 'vm-noise-data').parts if '=' in part)
    if not dimensions:
        continue
    frame = pd.read_csv(path)
    values = pd.to_numeric(frame['value'], errors='coerce')
    valid = values.dropna()
    median = valid.median()
    rows.append({**dimensions, 'unit': dimensions['unit'].removesuffix('.csv'),
                 'n': len(valid), 'invalid': int(values.isna().sum()),
                 'mean': valid.mean(), 'median': median,
                 'mad': (valid - median).abs().median(),
                 'cv': valid.std() / abs(valid.mean()) if valid.mean() != 0 else None,
                 'p05': valid.quantile(.05), 'p95': valid.quantile(.95),
                 'start': frame['starttime'].min(), 'end': frame['starttime'].max(),
                 'vm_count': frame['VM_id'].nunique(),
                 'source': str(path.relative_to(repo)),
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
summary = pd.DataFrame(rows)
summary.to_csv(output / 'dispersion.csv', index=False)
summary.to_json(output / 'dispersion.json', orient='records', indent=2)
# Compare same suite/test/unit/SKU/region; do not pool incompatible metric values.
paired = summary.pivot_table(index=['test_suite', 'test_name', 'unit', 'vm_sku', 'vm_region'],
                             columns='vm_lifespan', values='cv').dropna()
paired.to_csv(output / 'lifespan_pairs.csv')
fig, ax = plt.subplots(figsize=(8, 5))
for suite, group in paired.reset_index().groupby('test_suite'):
    ax.scatter(group['long'], group['short'], s=16, alpha=.65, label=suite)
ax.set(xlabel='Long-lived VM CV', ylabel='Short-lived VM CV',
       title='Azure external validation: matched metric partitions')
ax.set_xlim(left=0)
ax.set_ylim(bottom=0)
limit=min(ax.get_xlim()[1], ax.get_ylim()[1])
ax.plot([0,limit],[0,limit],linestyle='--',color='grey',linewidth=1,label='Equal CV')
ax.grid(alpha=.2)
ax.legend(fontsize=7, ncol=2)
fig.tight_layout()
fig.savefig(output / 'azure_dispersion.png', dpi=180)
docs_fig = root / 'docs/figures'
docs_fig.mkdir(parents=True, exist_ok=True)
fig.savefig(docs_fig / 'azure_dispersion.png', dpi=180)
metadata = {'source_commit': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
            'files': len(summary), 'observations': int(summary['n'].sum()),
            'invalid_values': int(summary['invalid'].sum()), 'matched_partitions': len(paired),
            'scope': 'External long-term variability; not local PMU ground truth; no accuracy calculation',
            'attribution': 'Freischuetz, Kanellis, Kroth, Venkataraman. TUNA, EuroSys 2025. Azure VM Noise Dataset 2024, CC-BY.',
            'lifespan_median_cv': summary.groupby('vm_lifespan')['cv'].median().to_dict()}
(output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps(metadata, indent=2))
