import unittest
from counterbouncer.quality.verdict import verdict, reason
from counterbouncer.quality.stability import summarize


class Verdict(unittest.TestCase):
    def test_severity_and_reason_preservation(self):
        reasons = [reason('X', 'DEGRADED'), reason('Y', 'REJECT')]
        self.assertEqual(verdict(reasons), {'verdict': 'REJECT', 'reasons': reasons})

    def test_small_sample_and_constant(self):
        self.assertIsNone(summarize([])['cv'])
        self.assertIsNone(summarize([1])['cv'])
        self.assertEqual(summarize([2, 2, 2])['cv'], 0)
        self.assertEqual(summarize([1, 2, 3])['mad'], 1)
        self.assertAlmostEqual(summarize([1, 2, 3])['cv'], .5)
