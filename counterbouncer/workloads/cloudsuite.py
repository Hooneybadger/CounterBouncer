import csv
import math
from pathlib import Path
import statistics
import subprocess
from .base import Workload


def parse(text):
    rows = []
    for line in text.splitlines():
        try:
            fields = [float(x.strip()) for x in next(csv.reader([line]))]
        except (ValueError, StopIteration):
            continue
        if len(fields) == 16 and fields[0] > 1_000_000_000 and fields[1] > 0:
            if all(math.isfinite(fields[i]) and fields[i] >= 0 for i in [2, 3, 8, 11]):
                rows.append(fields)
    # Exclude the first two emitted intervals (client ramp-up). Keep every subsequent interval.
    steady = rows[2:]
    if len(steady) < 5:
        return None
    duration = sum(r[1] for r in steady)
    return {'throughput_rps': sum(r[3] for r in steady) / duration,
            'p99_latency_ms': statistics.median(r[11] for r in steady),
            'p99_summary': 'median of interval p99; not pooled request p99',
            'qos_violating_interval_fraction': sum(r[11] >= 1 for r in steady) / len(steady),
            'interval_count': len(steady), 'intervals': steady}


def make(condition, seconds=15, rps=100000):
    root = Path(__file__).resolve().parents[2]
    cpus = '0-31' if condition == 'UNPINNED' else '2,4,6,8'
    subprocess.run(['docker', 'update', '--cpuset-cpus', cpus, 'counterbouncer-dc-server'], check=True, capture_output=True)
    pid = int(subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Pid}}', 'counterbouncer-dc-server'], text=True))
    version = subprocess.check_output(['docker', 'inspect', '-f', '{{.Image}}', 'counterbouncer-dc-server'], text=True).strip()
    command = ['docker', 'exec', '-t', 'counterbouncer-dc-client', 'timeout', '--signal=TERM', str(seconds),
               '/bin/bash', '/entrypoint.sh', '--m=RPS', '--S=28', '--g=0.8', '--c=200', '--w=8', '--T=1', f'--r={rps}']
    return Workload('cloudsuite', 'data-caching', 'twitter-28x', command, str(root), version, parse,
                    accepted_returncodes=[0, 124], attach_pid=pid,
                    metadata={'server_threads': 4, 'server_memory_mb': 10240, 'client_cpus': '16-23',
                              'target_rps': rps, 'duration_s': seconds, 'server_cpus': cpus,
                              'measurement_target': 'host PID of server, not Docker CLI',
                              'network': 'single-host dedicated Docker bridge'})
