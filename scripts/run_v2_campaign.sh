#!/usr/bin/env bash
# Unattended v2 campaign. v1 freeze/holdout are not touched.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts/setup
log=artifacts/setup/v2-campaign.log
PYTHON=python3
if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
fi
exec > >(tee -a "$log") 2>&1
echo "=== v2 campaign $(date -Is) python=$PYTHON ==="
"$PYTHON" scripts/prepare_baseline.py
"$PYTHON" scripts/calibrate.py --policy configs/experiment_v2.yaml --output artifacts/calibration-v2 --seed 202609082 --cpus 2
"$PYTHON" scripts/run_matrix.py --manifest experiments/manifest_v2.yaml --suite parsec --require-clean-host
"$PYTHON" scripts/run_matrix.py --manifest experiments/manifest_reference.yaml --suite parsec --require-clean-host
"$PYTHON" scripts/run_matrix.py --manifest experiments/manifest_v2.yaml --suite cloudsuite
"$PYTHON" analysis/analyze.py --manifest experiments/manifest_v2.yaml
"$PYTHON" analysis/reference.py
"$PYTHON" analysis/plots_v2.py
"$PYTHON" scripts/audit_results.py --manifest experiments/manifest_v2.yaml
"$PYTHON" scripts/audit_results.py --manifest experiments/manifest_reference.yaml
echo "=== v2 campaign finished $(date -Is) ==="
