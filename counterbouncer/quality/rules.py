from .verdict import reason, assemble

HARDWARE = ['cycles', 'instructions', 'branches', 'branch-misses', 'cache-references', 'cache-misses']
SOFTWARE = ['context-switches', 'cpu-migrations', 'page-faults']
IPC_HARDWARE = ['cycles', 'instructions']


def canonical(name):
    if '/' in name:
        return name.split('/')[1].split(',')[0]
    return name.split(':')[0]


def analyze(run, policy):
    reasons = []
    if run['returncode'] not in run.get('accepted_returncodes', [0]):
        reasons.append(reason('RUN_FAILED', 'INVALID', returncode=run['returncode']))
    if run.get('timeout'):
        reasons.append(reason('MEASUREMENT_TIMEOUT', 'INVALID'))
    if run.get('parser_error'):
        reasons.append(reason('PERF_PARSER_FAILED', 'INVALID', error=run['parser_error']))
    if not run['workload'].get('outcome'):
        reasons.append(reason('OUTCOME_PARSER_FAILED', 'INVALID'))
    if not run.get('git_commit'):
        reasons.append(reason('MISSING_PROVENANCE', 'INVALID'))
    selected = {}
    for event in run['events']:
        # Keep the explicit main PMU. Alias events only create PMU pressure.
        if ',' not in event['name'] and not event['name'].startswith('cpu_atom/'):
            selected.setdefault(canonical(event['name']), []).append(event)
    profile = run.get('event_profile', 'full')
    required = IPC_HARDWARE + SOFTWARE if profile == 'ipc' else HARDWARE + SOFTWARE
    for name in required:
        records = selected.get(name, [])
        if len(records) != 1:
            reasons.append(reason('MISSING_REQUIRED_EVENT' if not records else 'AMBIGUOUS_EVENT',
                                  'INVALID', event=name, count=len(records)))
            continue
        event = records[0]
        if event['status'] != 'counted' or event['value'] is None:
            reasons.append(reason('UNAVAILABLE_REQUIRED_EVENT', 'INVALID', event=name, status=event['status']))
            continue
        if name in HARDWARE:
            ratio = event['pcnt_running']
            runtime = event['event_runtime_ns']
            if ratio is None or runtime is None or runtime <= 0:
                reasons.append(reason('MISSING_SCHEDULING_METADATA', 'INVALID', event=name))
            elif ratio < policy['running_reject_pct']:
                reasons.append(reason('LOW_PMU_RUNNING_RATIO', 'INVALID', event=name, value=ratio,
                                      threshold=policy['running_reject_pct']))
            elif ratio < policy['running_degrade_pct']:
                reasons.append(reason('LOW_PMU_RUNNING_RATIO', 'DEGRADED', event=name, value=ratio,
                                      threshold=policy['running_degrade_pct']))
    events = {key: value[0] for key, value in selected.items() if len(value) == 1}
    _context_reasons(run, reasons)
    _placement_reasons(run, reasons)
    before, after = run['system'], run['environment_after']
    for key in ('kernel', 'cpu_model', 'governors', 'smt', 'boost_disabled'):
        if before.get(key) != after.get(key):
            reasons.append(reason('ENVIRONMENT_MISMATCH', 'CONTAMINATED', axis='context', field=key))
    if run.get('hybrid_exposed') or run.get('hybrid_unpinned'):
        reasons.append(reason('PARTIAL_HYBRID_PMU_COVERAGE', 'INVALID',
                              detail='cpu_core metrics exclude time on E-cores'))
    if run.get('interference_failed'):
        reasons.append(reason('INTERFERENCE_FAILED', 'UNKNOWN', axis='context'))
    metrics = {}
    pairs = [('ipc', 'instructions', 'cycles'), ('branch_miss_rate', 'branch-misses', 'branches'),
             ('cache_miss_ratio', 'cache-misses', 'cache-references')]
    for metric, numerator, denominator in pairs:
        top, bottom = events.get(numerator), events.get(denominator)
        value = None
        if bottom and bottom['status'] == 'counted' and bottom['value'] == 0:
            reasons.append(reason('ZERO_METRIC_DENOMINATOR', 'INVALID', metric=metric, event=denominator))
        if top and bottom and top['status'] == bottom['status'] == 'counted' and bottom['value'] and top['value'] is not None:
            if top['event_runtime_ns'] == bottom['event_runtime_ns'] and top['pcnt_running'] == bottom['pcnt_running']:
                value = top['value'] / bottom['value']
            else:
                reasons.append(reason('EVENT_GROUP_MISMATCH', 'INVALID', metric=metric))
        metrics[metric] = value
    duration = run.get('wall_runtime_s', 0)
    for name in SOFTWARE:
        value = events.get(name, {}).get('value')
        metrics[name.replace('-', '_') + '_per_second'] = value / duration if value is not None and duration > 0 else None
    return assemble(reasons), metrics


def _context_reasons(run, reasons):
    condition = run.get('condition')
    if condition in ('SMT', 'MEMORY'):
        reasons.append(reason('INTENTIONAL_INTERFERENCE', 'CONTAMINATED', axis='context', kind=condition))
    elif condition in ('HYBRID', 'UNPINNED'):
        reasons.append(reason('UNCONTROLLED_HYBRID_PLACEMENT', 'UNKNOWN', axis='context'))
    suite = run.get('workload', {}).get('suite')
    resident = run.get('project_containers') or []
    if suite == 'parsec' and any('server' in name for name in resident):
        reasons.append(reason('PROJECT_SERVER_RESIDENT', 'CONTAMINATED', axis='context',
                              containers=resident))


def _placement_reasons(run, reasons):
    requested = set(run.get('requested_cpus') or [])
    placement = run.get('placement') or {}
    observed = set(placement.get('observed_cpus') or [])
    if requested and observed:
        escaped = sorted(observed - requested)
        if escaped:
            reasons.append(reason('AFFINITY_ESCAPE', 'CONTAMINATED', axis='context', cpus=escaped))
    atom = set(run.get('atom_cpus') or [])
    if requested and atom and observed and (observed & atom) and not (requested & atom):
        reasons.append(reason('CROSS_CORE_TYPE', 'INVALID',
                              observed_atom=sorted(observed & atom)))
    nodes = run.get('numa_nodes') or {}
    if len(nodes) > 1 and requested and observed:
        def node_of(cpu):
            for name, cpus in nodes.items():
                if cpu in cpus:
                    return name
            return None
        extra = {node_of(cpu) for cpu in observed} - {node_of(cpu) for cpu in requested}
        extra.discard(None)
        if extra:
            reasons.append(reason('NUMA_MIGRATION', 'CONTAMINATED', axis='context',
                                    nodes=sorted(extra)))
