import argparse
import json
from pathlib import Path
from .runner import measure
from .workloads.calibration import make


def main():
    parser = argparse.ArgumentParser(description='Bouncer for Linux PMU measurements')
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run')
    run.add_argument('suite', choices=['calibration'])
    run.add_argument('name', choices=['branch', 'cache', 'memory'])
    run.add_argument('--mode', required=True)
    run.add_argument('--condition', default='CLEAN',
                     choices=['CLEAN', 'MULTIPLEX', 'SMT', 'MEMORY', 'UNPINNED', 'PCORE', 'HYBRID', 'REFERENCE'])
    run.add_argument('--run-id', required=True)
    run.add_argument('--output', default='artifacts/calibration')
    run.add_argument('--policy', default='configs/experiment.yaml')
    args = parser.parse_args()
    result = measure(make(args.name, args.mode), args.condition, args.run_id, args.output, args.policy)
    print(json.dumps({'run_id': result['run_id'], 'quality': result['quality'], 'metrics': result['metrics']}, indent=2))
    return 0 if result['returncode'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
