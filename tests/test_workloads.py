from pathlib import Path
import tempfile
import unittest
from counterbouncer.workloads.cloudsuite import parse
from counterbouncer.workloads.parsec import parse_output


class Adapters(unittest.TestCase):
    def test_cloudsuite_intervals_and_startup(self):
        line = '1788846021,1.0,100,100,80,20,80,0,0.1,0.2,0.3,0.4,0.1,0.01,2.0,1000'
        result = parse('\n'.join([line] * 7))
        self.assertEqual(result['throughput_rps'], 100)
        self.assertEqual(result['p99_latency_ms'], .4)
        self.assertEqual(result['interval_count'], 5)
        self.assertIsNone(parse(line))

    def test_parsec_error_not_an_outcome(self):
        self.assertIsNone(parse_output('blackscholes', 'Error opening input'))
        self.assertIsNone(parse_output('canneal', 'PARSEC Benchmark Suite\nusage'))
        self.assertIsNone(parse_output(
            'streamcluster',
            'PARSEC Benchmark Suite\npoints will be randomly generated instead of reading from infile.\n'))
        self.assertIsNone(parse_output(
            'dedup',
            'PARSEC Benchmark Suite\n-w \t\t\tcompression type: gzip/bzip2/none\n'))
        self.assertIsNotNone(parse_output(
            'dedup', 'PARSEC Benchmark Suite\nEffective compression factor:  2.00x\n'))
        banner = 'PARSEC Benchmark Suite\n' + ''.join(f'read {n} points\n' for n in [200000] * 5)
        self.assertIsNotNone(parse_output('streamcluster', banner))
        self.assertIsNone(parse_output('streamcluster', banner + 'error reading data!\n'))
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp)
            self.assertIsNone(parse_output('streamcluster', banner, missing))
            (missing / 'output.txt').write_text('centers\n')
            self.assertIsNotNone(parse_output('streamcluster', banner, missing))
