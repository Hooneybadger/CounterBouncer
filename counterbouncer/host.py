"""Project-owned Docker names. Do not stop unrelated lab containers."""
import subprocess

PROJECT_CONTAINERS = (
    'counterbouncer-dc-server',
    'counterbouncer-dc-client',
    'metrictrust-dc-server',
    'metrictrust-dc-client',
)
SERVER_CONTAINERS = ('counterbouncer-dc-server', 'metrictrust-dc-server')
CLIENT_CONTAINERS = ('counterbouncer-dc-client', 'metrictrust-dc-client')


def docker_names(all_containers=False):
    argv = ['docker', 'ps', '--format', '{{.Names}}']
    if all_containers:
        argv = ['docker', 'ps', '-a', '--format', '{{.Names}}']
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def project_containers_running():
    names = set(docker_names())
    return [name for name in PROJECT_CONTAINERS if name in names]


def first_existing(candidates):
    names = set(docker_names(all_containers=True))
    for name in candidates:
        if name in names:
            return name
    return None


def server_container():
    return first_existing(SERVER_CONTAINERS)


def client_container():
    return first_existing(CLIENT_CONTAINERS)


def stop_project_containers():
    stopped = []
    for name in project_containers_running():
        proc = subprocess.run(['docker', 'stop', name], capture_output=True, text=True, timeout=60)
        stopped.append({'name': name, 'returncode': proc.returncode, 'stderr': proc.stderr.strip()})
    return stopped


def start_named_containers(names):
    started = []
    for name in names:
        if not name:
            continue
        proc = subprocess.run(['docker', 'start', name], capture_output=True, text=True, timeout=60)
        started.append({'name': name, 'returncode': proc.returncode, 'stderr': proc.stderr.strip()})
        if proc.returncode != 0:
            raise RuntimeError(f'docker start {name} failed: {proc.stderr.strip()}')
    return started
