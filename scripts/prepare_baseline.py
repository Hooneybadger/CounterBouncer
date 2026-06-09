#!/usr/bin/env python3
"""Stop CounterBouncer CloudSuite containers. Do not touch unrelated lab Docker."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from counterbouncer.host import docker_names, project_containers_running, stop_project_containers
from counterbouncer.model import now, save

root = Path(__file__).resolve().parents[1]
before = docker_names()
stopped = stop_project_containers()
after = docker_names()
payload = {
    'timestamp': now(),
    'stopped': stopped,
    'project_still_running': project_containers_running(),
    'docker_before': before,
    'docker_after': after,
    'note': 'Unrelated lab containers are left running and recorded, not stopped.',
}
out = root / 'artifacts/setup/baseline-v2.json'
save(out, payload)
print(json.dumps(payload, indent=2))
if payload['project_still_running']:
    raise SystemExit('Project containers still running after docker stop')
