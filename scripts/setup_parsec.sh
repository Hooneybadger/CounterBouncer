#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p vendor/downloads artifacts/setup
if [ ! -d vendor/parsec/.git ]; then
  git clone https://github.com/cirosantilli/parsec-benchmark.git vendor/parsec
fi
# Original PARSEC 3.0 archives mirrored by the setup reference from the spec.
base=https://github.com/cirosantilli/parsec-benchmark/releases/download/3.0
for item in parsec-3.0-core.tar.gz parsec-3.0-input-native.tar.gz.{0..4}; do
  curl --fail --silent --show-error --location --retry 3 --connect-timeout 30 --continue-at - "$base/$item" -o "vendor/downloads/$item"
done
tar -xzf vendor/downloads/parsec-3.0-core.tar.gz -C vendor/parsec --skip-old-files --strip-components=1
cat vendor/downloads/parsec-3.0-input-native.tar.gz.{0..4} > vendor/downloads/parsec-3.0-input-native.tar.gz
tar -xzf vendor/downloads/parsec-3.0-input-native.tar.gz -C vendor/parsec --skip-old-files --strip-components=1
sha256sum vendor/downloads/* > artifacts/setup/parsec-input-sha256.txt
for package in blackscholes canneal dedup streamcluster; do
  (cd vendor/parsec && CFLAGS='-O3 -g' CXXFLAGS='-O3 -g' bin/parsecmgmt -a build -p "$package" -c gcc -n 4) > "artifacts/setup/parsec-build-$package.log" 2>&1
done
