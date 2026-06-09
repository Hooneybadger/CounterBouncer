import unittest
from counterbouncer.quality.verdict import assemble, reason
from counterbouncer.quality.stability import summarize


class Verdict(unittest.TestCase):
    def test_severity_and_reason_preservation(self):
        reasons = [reason('X', 'DEGRADED'), reason('Y', 'INVALID')]
        result = assemble(reasons)
        self.assertEqual(result['integrity'], 'INVALID')
        self.assertEqual(result['verdict'], 'REJECT')
        self.assertEqual(result['reasons'][0]['code'], 'X')

    def test_context_does_not_collapse_valid_measurement(self):
        reasons = [reason('INTENTIONAL_INTERFERENCE', 'CONTAMINATED', axis='context')]
        result = assemble(reasons)
        self.assertEqual(result['integrity'], 'VALID')
        self.assertEqual(result['context'], 'CONTAMINATED')
        self.assertEqual(result['usability'], 'VALID_BUT_CONTAMINATED')

    def test_small_sample_and_constant(self):
        self.assertIsNone(summarize([])['cv'])
        self.assertIsNone(summarize([1])['cv'])
        self.assertEqual(summarize([2, 2, 2])['cv'], 0)
        self.assertEqual(summarize([1, 2, 3])['mad'], 1)
        self.assertAlmostEqual(summarize([1, 2, 3])['cv'], .5)
