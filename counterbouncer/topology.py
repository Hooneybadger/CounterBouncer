"""Read hybrid CPU lists and format affinity. Missing sysfs files mean homogeneous CPU."""
from pathlib import Path


def parse_cpu_list(spec):
    if not spec:
        return []
    cpus = []
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start, end = part.split('-', 1)
            cpus.extend(range(int(start), int(end) + 1))
        else:
            cpus.append(int(part))
    return cpus


def format_cpu_list(cpus):
    cpus = sorted(set(cpus))
    if not cpus:
        return ''
    ranges = []
    start = prev = cpus[0]
    for cpu in cpus[1:]:
        if cpu == prev + 1:
            prev = cpu
            continue
        ranges.append(f'{start}-{prev}' if start != prev else str(start))
        start = prev = cpu
    ranges.append(f'{start}-{prev}' if start != prev else str(start))
    return ','.join(ranges)


def apply_thread_affinity(pid, spec):
    """Pin every thread in the process. Does not rewrite Docker cgroup by itself."""
    import os
    cpus = parse_cpu_list(spec) if isinstance(spec, str) else [int(x) for x in spec]
    if not cpus:
        return 0
    mask = set(cpus)
    pinned = 0
    task = Path(f'/proc/{int(pid)}/task')
    if not task.is_dir():
        return 0
    for tid in task.iterdir():
        if not tid.name.isdigit():
            continue
        try:
            os.sched_setaffinity(int(tid.name), mask)
            pinned += 1
        except OSError:
            continue
    return pinned


def _read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def cpu_list_file(path):
    text = _read(path)
    return parse_cpu_list(text) if text else []


def present_cpus():
    return cpu_list_file('/sys/devices/system/cpu/present') or list(range(os_cpu_count()))


def os_cpu_count():
    try:
        return len(Path('/sys/devices/system/cpu').glob('cpu[0-9]*'))
    except OSError:
        return 1


def p_core_cpus():
    return cpu_list_file('/sys/devices/cpu_core/cpus')


def e_core_cpus():
    return cpu_list_file('/sys/devices/cpu_atom/cpus')


def is_hybrid():
    return bool(p_core_cpus()) and bool(e_core_cpus())


def numa_nodes():
    nodes = {}
    root = Path('/sys/devices/system/node')
    if not root.exists():
        return nodes
    for node in sorted(root.glob('node[0-9]*')):
        nodes[node.name] = cpu_list_file(node / 'cpulist')
    return nodes


def thread_siblings(cpu):
    return cpu_list_file(f'/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list')


def smt_siblings_of(cpus):
    extras = []
    for cpu in cpus:
        for sibling in thread_siblings(cpu):
            if sibling not in cpus:
                extras.append(sibling)
    return sorted(set(extras))


def probe():
    present = present_cpus()
    core = p_core_cpus()
    atom = e_core_cpus()
    return {
        'present_cpus': present,
        'core_cpus': core,
        'atom_cpus': atom,
        'hybrid': bool(core) and bool(atom),
        'numa_nodes': numa_nodes(),
        'present_spec': format_cpu_list(present),
        'core_spec': format_cpu_list(core),
        'atom_spec': format_cpu_list(atom),
    }


def affinity_for(condition, pin_spec):
    """Return a cpuset string, or None when the run is allowed on every CPU."""
    if condition in ('HYBRID', 'UNPINNED'):
        return None
    if condition == 'PCORE':
        core = p_core_cpus()
        return format_cpu_list(core) if core else pin_spec
    return pin_spec


def hybrid_exposed(affinity_spec, topo=None):
    topo = topo or probe()
    if not topo['hybrid']:
        return False
    if affinity_spec is None:
        return True
    requested = set(parse_cpu_list(affinity_spec))
    return bool(requested & set(topo['atom_cpus']))
