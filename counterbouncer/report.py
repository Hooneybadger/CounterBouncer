import copy
from collections import defaultdict
from pathlib import Path
import json
from .model import save
from .quality.stability import summarize
from .quality.verdict import reason, verdict


def build_report(paths, policy, output):
    runs = [json.loads(Path(p).read_text()) for p in paths]
    groups = defaultdict(list)
    for run in runs:
        groups[(run['workload']['suite'], run['workload']['name'], run['condition'])].append(run)
    summary = []
    annotated = []
    for (suite, name, condition), members in sorted(groups.items()):
        key = 'throughput_rps' if suite == 'cloudsuite' else 'runtime_s'
        successful = [r for r in members if r['workload'].get('outcome') and
                      r['returncode'] in r['accepted_returncodes'] and not r.get('timeout')]
        values = [r['workload']['outcome'][key] for r in successful]
        stats = summarize(values)
        required = policy['minimum_repeats_cloudsuite' if suite == 'cloudsuite' else 'minimum_repeats_parsec']
        statistical_reasons = []
        if len(values) < required:
            statistical_reasons.append(reason('INSUFFICIENT_REPEATS', 'DEGRADED', actual=len(values), required=required))
        latency_stats = summarize(r['workload']['outcome']['p99_latency_ms'] for r in successful
                                  if 'p99_latency_ms' in r['workload']['outcome'])
        for metric, observed in [(key, stats), ('p99_latency_ms', latency_stats)]:
            if observed['cv'] is not None and observed['cv'] > policy['cv_degrade']:
                severity = 'REJECT' if observed['cv'] > policy['cv_reject'] else 'DEGRADED'
                statistical_reasons.append(reason('HIGH_RUN_VARIANCE', severity, metric=metric, cv=observed['cv'],
                                                 degrade=policy['cv_degrade'], reject=policy['cv_reject']))
        for r in members:
            r = copy.deepcopy(r)
            r['quality_with_stability'] = verdict(r['quality']['reasons'] + statistical_reasons)
            annotated.append(r)
        summary.append({'suite': suite, 'workload': name, 'condition': condition, 'outcome_key': key,
                        'attempts': len(members), 'outcome_statistics': stats,
                        'statistical_reasons': statistical_reasons,
                        'latency_statistics': latency_stats,
                        'metric_statistics': {metric: summarize(r['metrics'][metric] for r in successful if r['metrics'].get(metric) is not None) for metric in ['ipc', 'branch_miss_rate', 'cache_miss_ratio']},
                        'ipc_statistics': summarize(r['metrics']['ipc'] for r in successful if r['metrics'].get('ipc') is not None)})
    result = {'groups': summary, 'runs': annotated}
    save(output, result)
    return result
