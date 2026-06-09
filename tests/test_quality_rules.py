import unittest
from counterbouncer.quality.rules import analyze, HARDWARE, SOFTWARE
from counterbouncer.quality.verdict import assemble, collapse
from counterbouncer.topology import format_cpu_list, parse_cpu_list

POLICY = {'running_reject_pct': 50, 'running_degrade_pct': 90}


def sample():
    return {'returncode': 0, 'git_commit': 'test-fixture-only', 'condition': 'CLEAN',
            'workload': {'suite': 'parsec', 'outcome': {'runtime_s': 1}},
            'events': [{'name': n, 'status': 'counted', 'value': 0 if n == 'cpu-migrations' else 10,
                        'event_runtime_ns': 100, 'pcnt_running': 100} for n in HARDWARE + SOFTWARE],
            'system': {}, 'environment_after': {}, 'wall_runtime_s': 1,
            'requested_cpus': [2, 4, 6, 8], 'atom_cpus': [16, 17],
            'placement': {'observed_cpus': [2, 4, 6, 8]}}


class Rules(unittest.TestCase):
    def test_clean(self):
        q, m = analyze(sample(), POLICY)
        self.assertEqual(q['integrity'], 'VALID')
        self.assertEqual(q['context'], 'CONTROLLED')
        self.assertEqual(q['verdict'], 'ACCEPT')
        self.assertEqual(m['ipc'], 1)

    def test_missing_and_unsupported_rejected(self):
        for change in ['missing', 'unsupported']:
            r = sample()
            if change == 'missing':
                r['events'].pop(0)
            else:
                r['events'][0].update(status='unsupported', value=None)
            q, m = analyze(r, POLICY)
            self.assertEqual(q['integrity'], 'INVALID')
            self.assertEqual(q['verdict'], 'REJECT')
            self.assertIsNone(m['ipc'])

    def test_group_mismatch_and_zero_denominator(self):
        r = sample()
        r['events'][1]['event_runtime_ns'] = 80
        q, m = analyze(r, POLICY)
        self.assertIsNone(m['ipc'])
        self.assertIn('EVENT_GROUP_MISMATCH', [r['code'] for r in q['reasons']])
        r = sample()
        r['events'][0]['value'] = 0
        q, metrics = analyze(r, POLICY)
        self.assertIsNone(metrics['ipc'])
        self.assertEqual(q['integrity'], 'INVALID')
        self.assertIn('ZERO_METRIC_DENOMINATOR', [e['code'] for e in q['reasons']])

    def test_low_ratio_not_condition_label(self):
        r = sample()
        r['condition'] = 'MULTIPLEX'
        self.assertEqual(analyze(r, POLICY)[0]['integrity'], 'VALID')
        r['events'][0]['pcnt_running'] = 49
        self.assertEqual(analyze(r, POLICY)[0]['integrity'], 'INVALID')

    def test_run_failure(self):
        r = sample()
        r['returncode'] = 1
        self.assertEqual(analyze(r, POLICY)[0]['integrity'], 'INVALID')

    def test_within_pin_migration_is_not_integrity_failure(self):
        r = sample()
        next(e for e in r['events'] if e['name'] == 'cpu-migrations')['value'] = 40
        q, _ = analyze(r, POLICY)
        self.assertEqual(q['integrity'], 'VALID')
        self.assertEqual(q['context'], 'CONTROLLED')
        self.assertNotIn('CPU_MIGRATION', [e['code'] for e in q['reasons']])

    def test_smt_is_contaminated_even_when_counters_are_valid(self):
        r = sample()
        r['condition'] = 'SMT'
        q, _ = analyze(r, POLICY)
        self.assertEqual(q['integrity'], 'VALID')
        self.assertEqual(q['context'], 'CONTAMINATED')
        self.assertEqual(q['usability'], 'VALID_BUT_CONTAMINATED')
        self.assertEqual(q['verdict'], 'DEGRADED')

    def test_hybrid_coverage_is_invalid(self):
        r = sample()
        r['condition'] = 'HYBRID'
        r['hybrid_unpinned'] = True
        r['hybrid_exposed'] = True
        r['requested_cpus'] = []
        q, _ = analyze(r, POLICY)
        codes = [e['code'] for e in q['reasons']]
        self.assertIn('PARTIAL_HYBRID_PMU_COVERAGE', codes)
        self.assertEqual(q['integrity'], 'INVALID')
        self.assertEqual(q['context'], 'UNKNOWN')

    def test_affinity_escape_and_cross_core_type(self):
        r = sample()
        r['placement'] = {'observed_cpus': [2, 4, 6, 8, 17]}
        q, _ = analyze(r, POLICY)
        codes = [e['code'] for e in q['reasons']]
        self.assertIn('AFFINITY_ESCAPE', codes)
        self.assertIn('CROSS_CORE_TYPE', codes)
        self.assertEqual(q['integrity'], 'INVALID')
        self.assertEqual(q['context'], 'CONTAMINATED')

    def test_ipc_profile_does_not_require_branch_events(self):
        r = sample()
        r['event_profile'] = 'ipc'
        r['events'] = [e for e in r['events'] if e['name'] in ['cycles', 'instructions'] + SOFTWARE]
        q, m = analyze(r, POLICY)
        self.assertEqual(q['integrity'], 'VALID')
        self.assertEqual(m['ipc'], 1)
        self.assertIsNone(m['branch_miss_rate'])

    def test_project_server_contaminates_parsec_only(self):
        r = sample()
        r['project_containers'] = ['counterbouncer-dc-server']
        q, _ = analyze(r, POLICY)
        self.assertEqual(q['context'], 'CONTAMINATED')
        self.assertIn('PROJECT_SERVER_RESIDENT', [e['code'] for e in q['reasons']])

    def test_legacy_reject_reason_still_assembles(self):
        q = assemble([{'code': 'OLD', 'severity': 'REJECT', 'evidence': {}}])
        self.assertEqual(q['integrity'], 'INVALID')
        self.assertEqual(q['verdict'], 'REJECT')

    def test_cpu_list_roundtrip(self):
        self.assertEqual(parse_cpu_list('2,4,6,8'), [2, 4, 6, 8])
        self.assertEqual(format_cpu_list([0, 1, 2, 4, 15]), '0-2,4,15')
        self.assertEqual(collapse('VALID', 'CONTROLLED'), 'ACCEPT')
        self.assertEqual(collapse('VALID', 'CONTAMINATED'), 'DEGRADED')
