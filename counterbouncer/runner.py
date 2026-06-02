from dataclasses import asdict
import os
from pathlib import Path
import signal
import subprocess
import time
import yaml
from .environment import snapshot
from .model import now, save, sha256, git_state
from .perf_parser import parse_perf, PerfParseError
from .quality.rules import analyze

ROOT = Path(__file__).resolve().parents[1]


def event_spec(condition):
    config = yaml.safe_load((ROOT / 'configs/events_generic.yaml').read_text())
    groups = list(config['groups'])
    if condition == 'MULTIPLEX':
        for i in range(config['multiplex_extra_groups']):
            groups.append('{cpu_core/branches,name=extra_branch_%d/,cpu_core/branch-misses,name=extra_miss_%d/}' % (i, i))
    return ','.join(groups + config['software'])


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def measure(workload, condition, run_id, directory, policy_path, cpus='2,4,6,8', timeout=3600):
    directory = Path(directory).resolve() / run_id
    directory.mkdir(parents=True, exist_ok=False)
    policy_doc = yaml.safe_load(Path(policy_path).read_text())
    if workload.suite != 'calibration' and policy_doc.get('status') != 'frozen':
        raise ValueError('real holdout requires frozen policy')
    raw = directory / 'perf.jsonl'
    stdout_path, stderr_path = directory / 'stdout.txt', directory / 'stderr.txt'
    perf = ['perf', 'stat', '-j', '-o', str(raw), '-e', event_spec(condition)]
    if workload.attach_pid:
        perf += ['-p', str(workload.attach_pid)]
    command = perf + ['--'] + workload.command
    if condition != 'UNPINNED' and not workload.attach_pid:
        command = ['taskset', '-c', cpus] + command
    before = snapshot()
    state = git_state()
    record = {'schema_version': 1, 'run_id': run_id, 'timestamp': now(),
              'git_commit': state['commit'], 'git_dirty': state['dirty'],
              'condition': condition, 'policy_sha256': sha256(policy_path),
              'policy': policy_doc, 'command': command, 'system': before,
              'requested_affinity': None if condition == 'UNPINNED' else cpus,
              'workload': {'suite': workload.suite, 'name': workload.name, 'input': workload.input,
                           'command': workload.command, 'cwd': workload.cwd, 'version': workload.version,
                           'metadata': workload.metadata, 'outcome': None},
              'accepted_returncodes': workload.accepted_returncodes,
              'attach_pid': workload.attach_pid, 'events': [],
              'hybrid_unpinned': condition == 'UNPINNED',
              'phase': 'whole_application' if not workload.attach_pid else 'server_during_client_command',
              'interference': [], 'status': 'running'}
    save(directory / 'run.json', record)
    processes, handles = [], []
    try:
        interference_cpus = ['3', '5', '7', '9'] if condition == 'SMT' else ['24', '25', '26', '27'] if condition == 'MEMORY' else []
        for cpu in interference_cpus:
            kind, mode = ('branch', 'random') if condition == 'SMT' else ('memory', 'stream')
            cmd = ['taskset', '-c', cpu, 'python3', str(ROOT / 'scripts/interference.py'), kind, mode]
            handle = open(directory / f'interference-{cpu}.log', 'w')
            handles.append(handle)
            process = subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(process)
            record['interference'].append({'command': cmd, 'pid': process.pid, 'cpu': cpu})
        if processes:
            time.sleep(1)
        with stdout_path.open('w') as out, stderr_path.open('w') as err:
            start = time.monotonic()
            process = subprocess.Popen(command, cwd=workload.cwd, stdout=out, stderr=err,
                                       env={**os.environ, 'LC_ALL': 'C', 'OMP_NUM_THREADS': '4'}, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                stop(process)
                code = 124
                record['timeout'] = True
            except BaseException:
                stop(process)
                raise
            record['wall_runtime_s'] = time.monotonic() - start
            record['returncode'] = code
        record['interference_failed'] = any(p.poll() is not None for p in processes)
        output = stdout_path.read_text() + '\n' + stderr_path.read_text()
        try:
            record['workload']['outcome'] = workload.outcome_parser(output)
        except (ValueError, KeyError, IndexError) as exc:
            record['outcome_parser_error'] = str(exc)
        # For PARSEC, wall time is independently measured around the direct binary;
        # parser must validate successful program output before accepting the outcome.
        if workload.suite == 'parsec' and record['workload']['outcome'] is not None:
            record['workload']['outcome']['runtime_s'] = record['wall_runtime_s']
        try:
            parsed = parse_perf(raw.read_text() if raw.exists() else '')
            record['events'] = [asdict(e) | {'event_runtime_ms': e.event_runtime_ms} for e in parsed.events]
            record['perf_metadata'] = parsed.metadata
            record['perf_diagnostics'] = parsed.diagnostics
        except PerfParseError as exc:
            record['parser_error'] = str(exc)
        record['environment_after'] = snapshot()
        record['quality'], record['metrics'] = analyze(record, policy_doc['policy'])
        record['status'] = 'complete'
    finally:
        for p in processes:
            stop(p)
        for h in handles:
            h.close()
        record['finished_at'] = now()
        record['raw_files'] = {p.name: sha256(p) for p in directory.iterdir() if p.is_file() and p.name != 'run.json'}
        save(directory / 'run.json', record)
    return record
