import os
import platform
from pathlib import Path


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def snapshot():
    paths = Path('/sys/devices/system/cpu')
    return {
        'hostname': platform.node(), 'kernel': platform.release(),
        'cpu_model': next((line.split(':', 1)[1].strip() for line in
            (read('/proc/cpuinfo') or '').splitlines() if line.startswith('model name')), None),
        'affinity': sorted(os.sched_getaffinity(0)),
        'smt': read(paths / 'smt/active'),
        'governors': {str(p.parent.parent.name): read(p) for p in
                      paths.glob('cpu[0-9]*/cpufreq/scaling_governor')},
        'boost_disabled': read(paths / 'intel_pstate/no_turbo'),
        'loadavg': list(os.getloadavg()),
        'pressure_cpu': read('/proc/pressure/cpu'),
        'pressure_memory': read('/proc/pressure/memory'),
        'perf_event_paranoid': read('/proc/sys/kernel/perf_event_paranoid'),
        'nmi_watchdog': read('/proc/sys/kernel/nmi_watchdog'),
    }
