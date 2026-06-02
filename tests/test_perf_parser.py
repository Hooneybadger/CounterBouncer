"""Artificial parser inputs are test cases only, never benchmark evidence."""
import unittest
from counterbouncer.perf_parser import parse_perf, PerfParseError


class PerfParserTests(unittest.TestCase):
    def test_preserves_hybrid_pmus_and_unavailable_values(self):
        result = parse_perf('''{"event":"cpu_atom/instructions/","counter-value":"123","event-runtime":1000000,"pcnt-running":100}
{"event":"cpu_core/instructions/","counter-value":"<not counted>","event-runtime":0,"pcnt-running":0}''')
        self.assertEqual(len(result.events), 2)
        self.assertEqual(result.events[0].event_runtime_ms, 1)
        self.assertEqual(result.events[1].name, 'cpu_core/instructions/')
        self.assertIsNone(result.events[1].value)
        self.assertEqual(result.events[1].status, 'not_counted')

    def test_unsupported_is_not_zero(self):
        event = parse_perf('{"event":"cycles","counter-value":"<not supported>"}').events[0]
        self.assertIsNone(event.value)
        self.assertIsNone(event.pcnt_running)
        self.assertEqual(event.status, 'unsupported')

    def test_preserves_metadata_and_variance(self):
        result = parse_perf('''# started on date
WARNING: events were regrouped to match PMUs
{"event":"cycles","counter-value":"0","variance":1.5}
{"elapsed":0.2}''')
        self.assertEqual(result.events[0].value, 0)
        self.assertEqual(result.events[0].raw['variance'], 1.5)
        self.assertEqual(result.metadata, [{'elapsed': .2}])
        self.assertEqual(len(result.diagnostics), 1)

    def test_malformed_is_not_silently_dropped(self):
        for data in ['broken', '[]', '{"counter-value":4}',
                     '{"event":"cycles","counter-value":"NaN"}',
                     '{"event":"cycles","counter-value":true}',
                     '{"event":"cycles","pcnt-running":101}']:
            with self.subTest(data=data), self.assertRaises(PerfParseError):
                parse_perf(data)

    def test_empty_is_no_events(self):
        self.assertEqual(parse_perf('').events, [])


if __name__ == '__main__':
    unittest.main()
