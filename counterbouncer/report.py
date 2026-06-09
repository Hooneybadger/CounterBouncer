import copy
from collections import defaultdict
from pathlib import Path
import json
from .model import save
from .quality.stability import summarize
from .quality.verdict import reason, assemble


def _cutoffs(policy, kind):
    if kind == 'latency':
        degrade = policy.get('cv_latency_degrade', policy.get('cv_degrade'))
        reject = policy.get('cv_latency_reject', policy.get('cv_reject'))
    else:
        degrade = policy.get('cv_runtime_degrade', policy.get('cv_degrade'))
        reject = policy.get('cv_runtime_reject', policy.get('cv_reject'))
    return degrade, reject


def _variance_reasons(metric, observed, degrade, reject):
    if observed['cv'] is None or degrade is None:
        return []
    if observed['cv'] <= degrade:
        return []
    severity = 'INVALID' if reject is not None and observed['cv'] > reject else 'DEGRADED'
    return [reason('HIGH_RUN_VARIANCE', severity, metric=metric, cv=observed['cv'],
                   degrade=degrade, reject=reject)]


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
        if suite == 'cloudsuite':
            # Fixed offered load: throughput CV is not a quality signal.
            degrade, reject = _cutoffs(policy, 'latency')
            statistical_reasons.extend(_variance_reasons('p99_latency_ms', latency_stats, degrade, reject))
        else:
            degrade, reject = _cutoffs(policy, 'runtime')
            statistical_reasons.extend(_variance_reasons(key, stats, degrade, reject))
        for r in members:
            r = copy.deepcopy(r)
            r['quality_with_stability'] = assemble(r['quality']['reasons'] + statistical_reasons)
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
