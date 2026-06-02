"""Repeat real calibration processes until the runner terminates the process group."""
from pathlib import Path
import subprocess
import sys
kernel = Path(__file__).resolve().parents[1] / 'calibration/kernel'
while True:
    subprocess.run([str(kernel), *sys.argv[1:]], check=True)
