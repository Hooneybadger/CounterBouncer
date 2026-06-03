import copy
import unittest
from counterbouncer.quality.rules import analyze, HARDWARE, SOFTWARE

POLICY = {'running_reject_pct': 50, 'running_degrade_pct': 90, 'migration_degrade_count': 0}


def sample():
    return {'returncode': 0, 'git_commit': 'test-fixture-only', 'workload': {'outcome': {'runtime_s': 1}},
            'events': [{'name': n, 'status': 'counted', 'value': 0 if n == 'cpu-migrations' else 10,
                        'event_runtime_ns': 100, 'pcnt_running': 100} for n in HARDWARE + SOFTWARE],
            'system': {}, 'environment_after': {}, 'wall_runtime_s': 1}


class Rules(unittest.TestCase):
    def test_clean(self):
        q, m = analyze(sample(), POLICY)
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
        self.assertEqual(q['verdict'], 'REJECT')
        self.assertIn('ZERO_METRIC_DENOMINATOR', [e['code'] for e in q['reasons']])

    def test_low_ratio_not_condition_label(self):
        r = sample()
        r['condition'] = 'MULTIPLEX'
        self.assertEqual(analyze(r, POLICY)[0]['verdict'], 'ACCEPT')
        r['events'][0]['pcnt_running'] = 49
        self.assertEqual(analyze(r, POLICY)[0]['verdict'], 'REJECT')

    def test_run_failure_and_migration(self):
        r = sample()
        r['returncode'] = 1
        self.assertEqual(analyze(r, POLICY)[0]['verdict'], 'REJECT')
        r = sample()
        next(e for e in r['events'] if e['name'] == 'cpu-migrations')['value'] = 2
        self.assertEqual(analyze(r, POLICY)[0]['verdict'], 'DEGRADED')
        r = sample()
        r['hybrid_unpinned'] = True
        codes = [e['code'] for e in analyze(r, POLICY)[0]['reasons']]
        self.assertIn('PARTIAL_HYBRID_PMU_COVERAGE', codes)
