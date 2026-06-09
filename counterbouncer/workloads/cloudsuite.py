import csv
import math
from pathlib import Path
import statistics
import subprocess
from .base import Workload
from ..host import server_container, client_container
from ..placement import descendant_pids
from ..topology import affinity_for, apply_thread_affinity, probe


def _comm(pid):
    try:
        return Path(f'/proc/{int(pid)}/comm').read_text().strip()
    except OSError:
        return ''


def server_host_pid(container):
    pid = int(subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Pid}}', container], text=True))
    if _comm(pid) == 'memcached':
        return pid
    for kid in descendant_pids(pid):
        if _comm(kid) == 'memcached':
            return kid
    return pid


def bind_server(container, cpus):
    subprocess.run(['docker', 'update', '--cpuset-cpus', cpus, container], check=True, capture_output=True)
    pid = server_host_pid(container)
    pinned = apply_thread_affinity(pid, cpus)
    for kid in descendant_pids(pid):
        if kid != pid:
            pinned += apply_thread_affinity(kid, cpus)
    return pid, pinned


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


def make(condition, seconds=15, rps=100000, cpus=None):
    root = Path(__file__).resolve().parents[2]
    server = server_container()
    client = client_container()
    if not server or not client:
        raise FileNotFoundError('CloudSuite containers are not installed; run scripts/setup_cloudsuite.sh')
    if cpus is None:
        cpus = affinity_for(condition, '2,4,6,8')
    if cpus is None:
        cpus = probe()['present_spec'] or '0-31'
    pid, pinned = bind_server(server, cpus)
    version = subprocess.check_output(['docker', 'inspect', '-f', '{{.Image}}', server], text=True).strip()
    command = ['docker', 'exec', '-t', client, 'timeout', '--signal=TERM', str(seconds),
               '/bin/bash', '/entrypoint.sh', '--m=RPS', '--S=28', '--g=0.8', '--c=200', '--w=8', '--T=1', f'--r={rps}']
    return Workload('cloudsuite', 'data-caching', 'twitter-28x', command, str(root), version, parse,
                    accepted_returncodes=[0, 124], attach_pid=pid,
                    metadata={'server_threads': 4, 'server_memory_mb': 10240, 'client_cpus': '16-23',
                              'target_rps': rps, 'duration_s': seconds, 'server_cpus': cpus,
                              'server_container': server, 'client_container': client,
                              'measurement_target': 'host PID of memcached, not Docker CLI',
                              'thread_affinity_applied': pinned,
                              'network': 'single-host dedicated Docker bridge'})
