#!/usr/bin/env python3
"""Pack campaign evidence for the v0.2.1 GitHub Release. Does not rewrite artifacts."""
from collections import Counter
from pathlib import Path
import csv
import json
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'artifacts/release/counterbouncer-v0.2.1-results'
ARCHIVE = ROOT / 'artifacts/release/counterbouncer-v0.2.1-results.tar.zst'
EXPERIMENTS = (
    'native-holdout-v2',
    'native-reference-v2',
    'native-cloudsuite-v2.1',
    'native-holdout-v1',
)


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def slim_provenance(payload):
    images = {}
    for name, image in (payload.get('images') or {}).items():
        images[name] = {
            'Id': image.get('Id'),
            'RepoTags': image.get('RepoTags'),
            'RepoDigests': image.get('RepoDigests'),
            'Created': image.get('Created'),
        }
    return {
        'timestamp': payload.get('timestamp'),
        'repositories': payload.get('repositories'),
        'binaries': payload.get('binaries'),
        'images': images,
        'compiler': payload.get('compiler'),
        'compiler_flags': payload.get('compiler_flags'),
    }


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True)


def write_git_commits():
    campaigns = {}
    for experiment in EXPERIMENTS:
        commits = Counter()
        dirty = Counter()
        for path in sorted((ROOT / 'artifacts/experiments' / experiment).glob('*/run.json')):
            run = json.loads(path.read_text())
            commits[run.get('git_commit') or '?'] += 1
            dirty[bool(run.get('git_dirty'))] += 1
        campaigns[experiment] = {
            'runs': sum(commits.values()),
            'git_dirty': dict(dirty),
            'git_commit': dict(commits),
        }
    (STAGE / 'git-commits.json').write_text(json.dumps(campaigns, indent=2) + '\n')


def write_patch():
    note = '''# Recorded HEAD SHAs and git_dirty=true

The dirty working tree was not snapshotted at run time. This file
reconstructs published trees that later landed those changes.

native-holdout-v2 and native-reference-v2 recorded docs-only HEADs
(mostly c7e58b0 / d2d3987) with git_dirty=true. The two-axis gate was
committed later as 6fa6121.

native-cloudsuite-v2.1 recorded 6fa6121 with git_dirty=true. Thread
pinning landed as 7579783.

Do not treat this as byte-identical to the uncommitted tree.

'''
    parts = [note]
    pairs = [
        ('v2 two-axis gate vs recorded v2 HEAD',
         'c7e58b0d4e2b180f61d745f0e25effdf1657870c',
         '6fa612170c64e8dc3ca89a30ab24a74ee2c4a80a'),
        ('v2.1 thread pin vs recorded v2.1 HEAD',
         '6fa612170c64e8dc3ca89a30ab24a74ee2c4a80a',
         '75797832cf3a051bc8c524e0524e5b7b178f4dc0'),
    ]
    for title, old, new in pairs:
        parts.append(f'## {title}\n')
        parts.append(f'# git diff {old} {new}\n')
        parts.append(git('diff', old, new, '--',
                         'counterbouncer', 'tests', 'scripts', 'analysis',
                         'configs', 'experiments'))
    (STAGE / 'experiment-code.patch').write_text(''.join(parts))


def write_cloudsuite_csv():
    report = json.loads((ROOT / 'artifacts/analysis/report-native-cloudsuite-v2.1.json').read_text())
    rows = []
    for run in report['runs']:
        outcome = run['workload'].get('outcome') or {}
        quality = run.get('quality_with_stability') or run.get('quality') or {}
        ratios = [
            event['pcnt_running'] for event in run.get('events') or []
            if event.get('name', '').startswith('cpu_core/') and event.get('pcnt_running') is not None
        ]
        rows.append({
            'workload': run['workload']['name'],
            'suite': run['workload']['suite'],
            'condition': run['condition'],
            'integrity': quality.get('integrity'),
            'context': quality.get('context'),
            'usability': quality.get('usability'),
            'runtime_s': outcome.get('runtime_s'),
            'throughput_rps': outcome.get('throughput_rps'),
            'p99_latency_ms': outcome.get('p99_latency_ms'),
            'ipc': (run.get('metrics') or {}).get('ipc'),
            'running_pct': min(ratios) if ratios else None,
        })
    path = STAGE / 'cloudsuite-v2.1.csv'
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def copy_raw():
    for experiment in EXPERIMENTS:
        src = ROOT / 'artifacts/experiments' / experiment
        dst = STAGE / 'raw' / experiment
        for run_dir in sorted(p for p in src.iterdir() if p.is_dir()):
            target = dst / run_dir.name
            target.mkdir(parents=True, exist_ok=True)
            for name in ('run.json', 'perf.jsonl'):
                src_file = run_dir / name
                if src_file.exists():
                    copy_file(src_file, target / name)


def sha256sums():
    digest = subprocess.check_output(
        ['bash', '-c', 'find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum'],
        cwd=STAGE, text=True)
    (STAGE / 'SHA256SUMS').write_text(digest)


def readme():
    (STAGE / 'README.txt').write_text(
        '''CounterBouncer v0.2.1 campaign evidence

Aggregates and raw perf JSONL for native-holdout-v2, native-reference-v2,
native-cloudsuite-v2.1, and native-holdout-v1. Not in git because of size.

git_dirty was true on the v2 campaigns. experiment-code.patch reconstructs
later commits; it is not a snapshot of the uncommitted tree.

provenance.json is a public subset (image digests, binary hashes). Host
Docker overlay paths and unrelated containers are omitted.
'''
    )


def main():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    for name in (
        'experiments/manifest.yaml',
        'experiments/manifest_v2.yaml',
        'experiments/manifest_reference.yaml',
        'experiments/manifest_v2_1_cloudsuite.yaml',
        'configs/experiment.yaml',
        'configs/experiment_v2.yaml',
        'configs/events_generic.yaml',
        'configs/parsec.yaml',
        'configs/cloudsuite.yaml',
        'configs/sources.yaml',
    ):
        copy_file(ROOT / name, STAGE / name)

    provenance = json.loads((ROOT / 'artifacts/setup/provenance.json').read_text())
    (STAGE / 'provenance.json').write_text(json.dumps(slim_provenance(provenance), indent=2) + '\n')
    copy_file(ROOT / 'artifacts/preflight/authorized/system.json', STAGE / 'preflight/system.json')

    for name in (
        'artifacts/analysis/report-native-holdout-v2.json',
        'artifacts/analysis/reference-v2.json',
        'artifacts/analysis/report-native-cloudsuite-v2.1.json',
        'artifacts/analysis/report.json',
        'artifacts/analysis/runs-v2.csv',
        'artifacts/analysis/runs.csv',
        'artifacts/completion-audit-native-holdout-v2.json',
        'artifacts/completion-audit-native-reference-v2.json',
        'artifacts/completion-audit-native-cloudsuite-v2.1.json',
        'artifacts/completion-audit.json',
    ):
        copy_file(ROOT / name, STAGE / Path(name).name)

    write_cloudsuite_csv()
    write_git_commits()
    write_patch()
    copy_raw()
    readme()
    sha256sums()

    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    tar_path = ARCHIVE.with_suffix('')
    if tar_path.exists():
        tar_path.unlink()
    if ARCHIVE.exists():
        ARCHIVE.unlink()
    with tarfile.open(tar_path, 'w') as tar:
        tar.add(STAGE, arcname=STAGE.name)
    subprocess.check_call(['zstd', '-f', '-19', str(tar_path)])
    tar_path.unlink(missing_ok=True)
    print(ARCHIVE, ARCHIVE.stat().st_size)


if __name__ == '__main__':
    main()
