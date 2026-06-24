#!/usr/bin/env bash
# tools/build_engine.sh — scan 엔진을 두 형태로 빌드해 base64로 src/에 동봉한다.
#   1) scan_engine.so          (평문 C, Python 의존 0)   → src/scan_engine.b64      : ctypes/memfd 폴백
#   2) scan_engine_ext.abi3.so (CPython 확장, abi3)        → src/scan_engine_ext.b64  : import (DMS 입증 1순위)
# Gmail이 .so 확장자를 차단하므로 base64 텍스트로 인코딩해 동봉(런타임 디코딩).
# abi3(Py_LIMITED_API=3.8)라 서버 Python 3.8+ 어느 버전서도 import된다.
set -euo pipefail
cd "$(dirname "$0")/.."
SRC=src
PYINC=$(python3 -c "import sysconfig; print(sysconfig.get_path('include'))")

echo "[1/4] 평문 C .so (ctypes/memfd 폴백) — Python 의존 없음"
gcc -O2 -fPIC -shared -Wl,-soname,scan_engine.so -o /tmp/scan_engine.so "$SRC/scan_engine.c"

echo "[2/4] CPython 확장 abi3 .so (import 1순위) — PYINC=$PYINC"
gcc -O2 -fPIC -shared -DPy_LIMITED_API=0x03080000 -I"$PYINC" \
    -Wl,-soname,scan_engine_ext.abi3.so -o /tmp/scan_engine_ext.abi3.so \
    "$SRC/scan_engine.c" "$SRC/scan_engine_ext.c"

echo "[3/4] base64 인코딩 → src/"
python3 -c "import base64;open('$SRC/scan_engine.b64','wb').write(base64.b64encode(open('/tmp/scan_engine.so','rb').read()))"
python3 -c "import base64;open('$SRC/scan_engine_ext.b64','wb').write(base64.b64encode(open('/tmp/scan_engine_ext.abi3.so','rb').read()))"

echo "[4/4] 검증"
ls -l /tmp/scan_engine.so /tmp/scan_engine_ext.abi3.so "$SRC/scan_engine.b64" "$SRC/scan_engine_ext.b64"
echo "plain  GLIBC max:  $(objdump -T /tmp/scan_engine.so       | grep -oE 'GLIBC_[0-9.]+' | sort -V | tail -1)  scan_run:$(nm -D /tmp/scan_engine.so | grep -c ' scan_run')"
echo "ext    GLIBC max:  $(objdump -T /tmp/scan_engine_ext.abi3.so | grep -oE 'GLIBC_[0-9.]+' | sort -V | tail -1)  PyInit:$(nm -D /tmp/scan_engine_ext.abi3.so | grep -c PyInit_scan_engine_ext)  scan_run:$(nm -D /tmp/scan_engine_ext.abi3.so | grep -c ' scan_run')"
echo "ext    NEEDED:     $(readelf -d /tmp/scan_engine_ext.abi3.so | grep NEEDED | grep -oE '\[.*\]' | tr '\n' ' ')"
rm -f /tmp/scan_engine.so /tmp/scan_engine_ext.abi3.so
echo "완료 — src/scan_engine.b64 (ctypes/memfd), src/scan_engine_ext.b64 (import)"
