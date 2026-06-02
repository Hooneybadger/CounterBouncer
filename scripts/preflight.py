#!/usr/bin/env python3
"""Read-only environment and perf capability audit; never changes host settings."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

EVENTS = ('cycles', 'instructions', 'branches', 'branch-misses',
          'cache-references', 'cache-misses', 'context-switches',
          'cpu-migrations', 'page-faults')


def command(argv):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=20,
                           env={**os.environ, 'LC_ALL': 'C'})
        return {'command': argv, 'returncode': p.returncode,
                'stdout': p.stdout, 'stderr': p.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'command': argv, 'returncode': None, 'error': str(exc)}


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def sysfiles(pattern):
    return {str(p): read(p) for p in sorted(Path('/sys').glob(pattern))}


def collect(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    lscpu = command(['lscpu', '--json'])
    try:
        cpu = {r['field'].rstrip(':'): r['data']
               for r in json.loads(lscpu['stdout'])['lscpu']}
    except (KeyError, ValueError):
        cpu = {}
    virt = command(['systemd-detect-virt'])
    bare_metal = (virt.get('returncode') == 1 and
                  virt.get('stdout', '').strip() == 'none' and
                  'Hypervisor vendor' not in cpu)
    probes = {}
    for event in EVENTS:
        raw = output.parent / f'{event}.perf.json'
        # perf output is separate from the command's stdout/stderr.
        result = command(['perf', 'stat', '-j', '-o', str(raw.resolve()),
                          '-e', event, '--', 'sleep', '0.1'])
        result['raw_output'] = str(raw)
        payload = read(raw) or ''
        combined = payload + result.get('stderr', '') + result.get('stdout', '')
        if any(message in combined for message in ('No permission', 'Permission denied',
                'Operation not permitted', 'Access to performance monitoring and observability operations is limited')):
            status = 'permission_denied'
        elif result['returncode'] == 0:
            try:
                rows = [json.loads(line) for line in payload.splitlines()
                        if line.strip() and not line.startswith('#')]
                result['records'] = rows
                valid = []
                for row in rows:
                    try:
                        if (row.get('event') and float(row['event-runtime']) > 0
                                and float(row['pcnt-running']) > 0
                                and float(row['counter-value']) >= 0):
                            valid.append(row)
                    except (ValueError, KeyError, TypeError):
                        continue
                if valid:
                    status = 'available' if len(valid) == len(rows) else 'partially_available'
                elif '<not supported>' in payload:
                    status = 'unsupported'
                elif '<not counted>' in payload:
                    status = 'not_counted'
                else:
                    status = 'unverified'
            except (ValueError, KeyError, TypeError):
                status = 'unverified'
        else:
            status = 'probe_failed'
        probes[event] = {**result, 'status': status}
    blockers = []
    if not bare_metal:
        blockers.append('BLOCKED: bare-metal required (or detection inconclusive)')
    if platform.machine() != 'x86_64' or platform.system() != 'Linux':
        blockers.append('BLOCKED: Linux x86-64 required')
    if not any(probes[e]['status'] in ('available', 'partially_available') for e in EVENTS[:6]):
        blockers.append('BLOCKER A: perf hardware event access unavailable')
    docker = command(['docker', 'version', '--format', '{{json .}}'])
    if docker.get('returncode') != 0:
        blockers.append('Docker client/daemon unavailable for CloudSuite')
    memory = dict(line.split(':', 1) for line in (read('/proc/meminfo') or '').splitlines())
    data = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'hostname': platform.node(), 'kernel': platform.release(),
        'architecture': platform.machine(), 'python': platform.python_version(),
        'cpu': cpu, 'lscpu': lscpu, 'logical_cores': os.cpu_count(),
        'physical_core_topology': command(['lscpu', '-p=SOCKET,CORE,ONLINE']),
        'smt_active': read('/sys/devices/system/cpu/smt/active'),
        'smt_siblings': sysfiles('devices/system/cpu/cpu[0-9]*/topology/thread_siblings_list'),
        'numa': command(['lscpu', '-e=CPU,NODE,SOCKET,CORE,ONLINE']),
        'governors': sysfiles('devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor'),
        'boost': sysfiles('devices/system/cpu/cpufreq/boost'),
        'intel_no_turbo': read('/sys/devices/system/cpu/intel_pstate/no_turbo'),
        'affinity': sorted(os.sched_getaffinity(0)),
        'virtualization': virt, 'bare_metal_detected': bare_metal,
        'perf_version': command(['perf', '--version']),
        'perf_event_paranoid': read('/proc/sys/kernel/perf_event_paranoid'),
        'nmi_watchdog': read('/proc/sys/kernel/nmi_watchdog'),
        'perf_capabilities': command(['getcap', shutil.which('perf') or '/usr/bin/perf']),
        'passwordless_sudo': command(['sudo', '-n', 'true']),
        'docker': docker, 'compiler': command(['cc', '--version']),
        'memory': memory, 'disk': shutil.disk_usage(output.parent)._asdict(),
        'events': probes, 'blockers': blockers,
        'status': 'BLOCKED' if blockers else 'READY',
        'evidence_kind': 'preflight_only_not_benchmark',
    }
    output.write_text(json.dumps(data, indent=2) + '\n')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/preflight/system.json'))
    args = parser.parse_args()
    data = collect(args.output)
    print(f"{data['status']}: {args.output}")
    for blocker in data['blockers']:
        print(blocker)
    return 2 if data['blockers'] else 0


if __name__ == '__main__':
    sys.exit(main())
