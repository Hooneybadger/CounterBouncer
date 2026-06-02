#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts/setup
cc -O2 -fno-if-conversion -fno-if-conversion2 -Wall -Wextra calibration/kernel.c -o calibration/kernel
cc --version > artifacts/setup/calibration-compiler.txt
sha256sum calibration/kernel > artifacts/setup/calibration-binary-sha256.txt
