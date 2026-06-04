#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for package in blackscholes canneal dedup streamcluster; do
  (cd vendor/parsec && bin/parsecmgmt -a clean -p "$package" -c gcc && \
    CFLAGS='-O3 -g' CXXFLAGS='-O3 -g' bin/parsecmgmt -a build -p "$package" -c gcc -n 4) \
    > "artifacts/setup/parsec-optimized-$package.log" 2>&1
done
