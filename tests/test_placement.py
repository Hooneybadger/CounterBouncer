import os
import subprocess
import unittest
from counterbouncer.topology import apply_thread_affinity, parse_cpu_list
from counterbouncer.placement import descendant_pids


class Affinity(unittest.TestCase):
    def test_pin_child_process(self):
        proc = subprocess.Popen(['sleep', '8'])
        try:
            n = apply_thread_affinity(proc.pid, '2')
            self.assertGreater(n, 0)
            self.assertEqual(os.sched_getaffinity(proc.pid), {2})
        finally:
            proc.kill()
            proc.wait()

    def test_descendants_include_self(self):
        self.assertIn(os.getpid(), descendant_pids(os.getpid()))

    def test_stale_last_cpu_outside_mask_is_ignored(self):
        proc = subprocess.Popen(['sleep', '8'])
        try:
            apply_thread_affinity(proc.pid, '2')
            from counterbouncer.placement import observed_cpus
            self.assertTrue(set(observed_cpus(proc.pid)).issubset({2}))
        finally:
            proc.kill()
            proc.wait()

    def test_parse_list(self):
        self.assertEqual(parse_cpu_list('2,4,6,8'), [2, 4, 6, 8])
