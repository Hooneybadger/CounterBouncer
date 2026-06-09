"""Sample which CPUs a process tree used. Summary only; not a scheduler trace."""
from collections import Counter
from pathlib import Path
import os
import threading


def _stat_ppid_and_cpu(text):
    close = text.rfind(')')
    if close < 0:
        return None, None
    rest = text[close + 2:].split()
    if len(rest) < 37:
        return None, None
    return int(rest[1]), int(rest[36])


def _read_stat(path):
    try:
        return path.read_text()
    except OSError:
        return None


def _cgroup(pid):
    try:
        return Path(f'/proc/{pid}/cgroup').read_text()
    except OSError:
        return None


def _children_of(pid):
    children_path = Path(f'/proc/{pid}/task/{pid}/children')
    if children_path.exists():
        try:
            kids = [int(x) for x in children_path.read_text().split() if x.isdigit()]
        except OSError:
            kids = []
        if kids:
            return kids
    return _scan_children({pid})


def descendant_pids(root):
    root = int(root)
    found = {root}
    frontier = [root]
    group = _cgroup(root)
    while frontier:
        pid = frontier.pop()
        for kid in _children_of(pid):
            if kid in found:
                continue
            if group is not None and _cgroup(kid) != group:
                continue
            found.add(kid)
            frontier.append(kid)
    return found


def _scan_children(parents):
    extra = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        text = _read_stat(entry / 'stat')
        if not text:
            continue
        ppid, _ = _stat_ppid_and_cpu(text)
        if ppid in parents:
            extra.append(int(entry.name))
    return extra


def observed_cpus(root_pid):
    cpus = []
    for pid in descendant_pids(root_pid):
        task = Path(f'/proc/{pid}/task')
        if not task.is_dir():
            continue
        for tid in task.iterdir():
            text = _read_stat(tid / 'stat')
            if not text:
                continue
            _, cpu = _stat_ppid_and_cpu(text)
            if cpu is None:
                continue
            try:
                allowed = os.sched_getaffinity(int(tid.name))
            except OSError:
                allowed = None
            # Last-run CPU in stat can be stale from before a cpuset change.
            if allowed is not None and cpu not in allowed:
                continue
            cpus.append(cpu)
    return cpus


class PlacementSampler:
    def __init__(self, interval_s=0.05):
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread = None
        self.counts = Counter()
        self.samples = 0
        self.pid = None

    def start(self, pid):
        self.pid = int(pid)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                for cpu in observed_cpus(self.pid):
                    self.counts[cpu] += 1
                self.samples += 1
            except OSError:
                pass
            self._stop.wait(self.interval_s)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def summary(self):
        observed = sorted(self.counts)
        return {
            'pid': self.pid,
            'interval_s': self.interval_s,
            'sample_count': self.samples,
            'observed_cpus': observed,
            'counts_by_cpu': {str(cpu): int(self.counts[cpu]) for cpu in observed},
        }

