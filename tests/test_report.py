import tempfile
from pathlib import Path
import json
import unittest
from counterbouncer.report import build_report


class StabilityReport(unittest.TestCase):
    def test_group_variance_separate_from_raw_and_failures_retained(self):
        # Explicit unit-test fixture; never a benchmark artifact.
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, value in enumerate([1, 10, None]):
                run = {'workload': {'suite': 'parsec', 'name': 'fixture', 'outcome': {'runtime_s': value} if value else None},
                       'condition': 'CLEAN', 'returncode': 0 if value else 1, 'accepted_returncodes': [0],
                       'metrics': {'ipc': 1}, 'quality': {'verdict': 'ACCEPT', 'reasons': []}}
                path = Path(tmp) / f'{i}.json'
                path.write_text(json.dumps(run))
                paths.append(path)
            result = build_report(paths, {'minimum_repeats_parsec': 3, 'cv_degrade': .05, 'cv_reject': .2}, Path(tmp) / 'report.json')
            self.assertEqual(result['groups'][0]['attempts'], 3)
            self.assertEqual(result['groups'][0]['outcome_statistics']['n'], 2)
            self.assertEqual(result['runs'][0]['quality']['verdict'], 'ACCEPT')
            self.assertEqual(result['runs'][0]['quality_with_stability']['verdict'], 'REJECT')
            self.assertNotIn('quality_with_stability', json.loads(paths[0].read_text()))

    def test_cloudsuite_uses_latency_not_throughput_cv(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, rps in enumerate([100000, 100000, 100000, 100000, 100000]):
                run = {'workload': {'suite': 'cloudsuite', 'name': 'data-caching',
                                    'outcome': {'throughput_rps': rps, 'p99_latency_ms': 0.02}},
                       'condition': 'CLEAN', 'returncode': 0, 'accepted_returncodes': [0],
                       'metrics': {'ipc': 1}, 'quality': {'integrity': 'VALID', 'context': 'CONTROLLED',
                                                          'verdict': 'ACCEPT', 'reasons': []}}
                path = Path(tmp) / f'{i}.json'
                path.write_text(json.dumps(run))
                paths.append(path)
            policy = {'minimum_repeats_cloudsuite': 5, 'cv_runtime_degrade': .05, 'cv_runtime_reject': .2,
                      'cv_latency_degrade': .10, 'cv_latency_reject': .25}
            result = build_report(paths, policy, Path(tmp) / 'report.json')
            codes = [e['code'] for e in result['groups'][0]['statistical_reasons']]
            self.assertNotIn('HIGH_RUN_VARIANCE', codes)

    def test_cloudsuite_flags_p99_dispersion(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, p99 in enumerate([0.02, 0.02, 0.02, 0.02, 0.2]):
                run = {'workload': {'suite': 'cloudsuite', 'name': 'data-caching',
                                    'outcome': {'throughput_rps': 100000, 'p99_latency_ms': p99}},
                       'condition': 'CLEAN', 'returncode': 0, 'accepted_returncodes': [0],
                       'metrics': {'ipc': 1}, 'quality': {'integrity': 'VALID', 'context': 'CONTROLLED',
                                                          'verdict': 'ACCEPT', 'reasons': []}}
                path = Path(tmp) / f'{i}.json'
                path.write_text(json.dumps(run))
                paths.append(path)
            policy = {'minimum_repeats_cloudsuite': 5, 'cv_runtime_degrade': .05, 'cv_runtime_reject': .2,
                      'cv_latency_degrade': .10, 'cv_latency_reject': .25}
            result = build_report(paths, policy, Path(tmp) / 'report.json')
            codes = [e['code'] for e in result['groups'][0]['statistical_reasons']]
            self.assertIn('HIGH_RUN_VARIANCE', codes)
            self.assertEqual(result['groups'][0]['statistical_reasons'][0]['evidence']['metric'], 'p99_latency_ms')
