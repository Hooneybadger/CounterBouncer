import re
from pathlib import Path
from .base import Workload


def parse(text):
    match = re.search(r'CALIBRATION runtime_s=([0-9.]+) checksum=([0-9]+)', text)
    return {'runtime_s': float(match[1]), 'checksum': int(match[2])} if match else None


def make(name, mode):
    root = Path(__file__).resolve().parents[2]
    return Workload('calibration', name, mode, [str(root / 'calibration/kernel'), name, mode],
                    str(root), 'local-source-recorded-by-git', parse,
                    metadata={'evidence_scope': 'calibration_only'})
