from .verdict import reason, verdict

HARDWARE = ['cycles', 'instructions', 'branches', 'branch-misses', 'cache-references', 'cache-misses']
SOFTWARE = ['context-switches', 'cpu-migrations', 'page-faults']


def canonical(name):
    if '/' in name:
        return name.split('/')[1].split(',')[0]
    return name.split(':')[0]


def analyze(run, policy):
    reasons = []
    if run['returncode'] not in run.get('accepted_returncodes', [0]):
        reasons.append(reason('RUN_FAILED', 'REJECT', returncode=run['returncode']))
    if run.get('timeout'):
        reasons.append(reason('MEASUREMENT_TIMEOUT', 'REJECT'))
    if run.get('parser_error'):
        reasons.append(reason('PERF_PARSER_FAILED', 'REJECT', error=run['parser_error']))
    if not run['workload'].get('outcome'):
        reasons.append(reason('OUTCOME_PARSER_FAILED', 'REJECT'))
    if not run.get('git_commit'):
        reasons.append(reason('MISSING_PROVENANCE', 'REJECT'))
    selected = {}
    for e in run['events']:
        # Keep the explicit main PMU. Alias events only create PMU pressure.
        if ',' not in e['name'] and not e['name'].startswith('cpu_atom/'):
            selected.setdefault(canonical(e['name']), []).append(e)
    for name in HARDWARE + SOFTWARE:
        records = selected.get(name, [])
        if len(records) != 1:
            reasons.append(reason('MISSING_REQUIRED_EVENT' if not records else 'AMBIGUOUS_EVENT',
                                  'REJECT', event=name, count=len(records)))
            continue
        event = records[0]
        if event['status'] != 'counted' or event['value'] is None:
            reasons.append(reason('UNAVAILABLE_REQUIRED_EVENT', 'REJECT', event=name, status=event['status']))
            continue
        if name in HARDWARE:
            ratio = event['pcnt_running']
            runtime = event['event_runtime_ns']
            if ratio is None or runtime is None or runtime <= 0:
                reasons.append(reason('MISSING_SCHEDULING_METADATA', 'REJECT', event=name))
            elif ratio < policy['running_reject_pct']:
                reasons.append(reason('LOW_PMU_RUNNING_RATIO', 'REJECT', event=name, value=ratio,
                                      threshold=policy['running_reject_pct']))
            elif ratio < policy['running_degrade_pct']:
                reasons.append(reason('LOW_PMU_RUNNING_RATIO', 'DEGRADED', event=name, value=ratio,
                                      threshold=policy['running_degrade_pct']))
    events = {k: v[0] for k, v in selected.items() if len(v) == 1}
    migration = events.get('cpu-migrations', {}).get('value')
    if migration is not None and migration > policy['migration_degrade_count']:
        reasons.append(reason('CPU_MIGRATION', 'DEGRADED', count=migration,
                              threshold=policy['migration_degrade_count']))
    before, after = run['system'], run['environment_after']
    for key in ('kernel', 'cpu_model', 'governors', 'smt', 'boost_disabled'):
        if before.get(key) != after.get(key):
            reasons.append(reason('ENVIRONMENT_MISMATCH', 'DEGRADED', field=key))
    if run.get('hybrid_unpinned'):
        reasons.append(reason('PARTIAL_HYBRID_PMU_COVERAGE', 'DEGRADED',
                              detail='cpu_core metrics exclude time on E-cores'))
    if run.get('interference_failed'):
        reasons.append(reason('INTERFERENCE_FAILED', 'REJECT'))
    metrics = {}
    pairs = [('ipc', 'instructions', 'cycles'), ('branch_miss_rate', 'branch-misses', 'branches'),
             ('cache_miss_ratio', 'cache-misses', 'cache-references')]
    for metric, numerator, denominator in pairs:
        n, d = events.get(numerator), events.get(denominator)
        value = None
        if d and d['status'] == 'counted' and d['value'] == 0:
            reasons.append(reason('ZERO_METRIC_DENOMINATOR', 'REJECT', metric=metric, event=denominator))
        if n and d and n['status'] == d['status'] == 'counted' and d['value'] and n['value'] is not None:
            if n['event_runtime_ns'] == d['event_runtime_ns'] and n['pcnt_running'] == d['pcnt_running']:
                value = n['value'] / d['value']
            else:
                reasons.append(reason('EVENT_GROUP_MISMATCH', 'REJECT', metric=metric))
        metrics[metric] = value
    duration = run.get('wall_runtime_s', 0)
    for name in SOFTWARE:
        value = events.get(name, {}).get('value')
        metrics[name.replace('-', '_') + '_per_second'] = value / duration if value is not None and duration > 0 else None
    return verdict(reasons), metrics
