import tempfile
from pathlib import Path
import json
import unittest
from counterbouncer.report import build_report


class StabilityReport(unittest.TestCase):
    def test_group_variance_separate_from_raw_and_failures_retained(self):
        # Explicit unit-test fixture; never a benchmark artifact.
        with tempfile.TemporaryDirectory() as tmp:
            paths=[]
            for i, value in enumerate([1, 10, None]):
                run={'workload': {'suite':'parsec','name':'fixture','outcome': {'runtime_s':value} if value else None},
                     'condition':'CLEAN','returncode':0 if value else 1,'accepted_returncodes':[0],
                     'metrics':{'ipc':1}, 'quality':{'verdict':'ACCEPT','reasons':[]}}
                path=Path(tmp)/f'{i}.json';path.write_text(json.dumps(run));paths.append(path)
            result=build_report(paths,{'minimum_repeats_parsec':3, 'cv_degrade':.05, 'cv_reject':.2},Path(tmp)/'report.json')
            self.assertEqual(result['groups'][0]['attempts'],3)
            self.assertEqual(result['groups'][0]['outcome_statistics']['n'],2)
            self.assertEqual(result['runs'][0]['quality']['verdict'],'ACCEPT')
            self.assertEqual(result['runs'][0]['quality_with_stability']['verdict'],'REJECT')
            self.assertNotIn('quality_with_stability',json.loads(paths[0].read_text()))
