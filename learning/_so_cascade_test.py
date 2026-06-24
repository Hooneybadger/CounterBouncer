#!/usr/bin/env python3
"""_so_cascade_test.py — 디코딩-쓰기 위치 실패를 *완전히* 닫았는지 증명하는 적대 테스트.

진단으로 서버서 .so 미로드(로딩 문제)가 확정됐고, base64 동봉→런타임 디코딩이 수정이다. 그러나
디코딩한 .so를 *어디에 쓰느냐*가 새 실패면(실행폴더 RO·/tmp noexec)이다. c_engine._load_lib는
실행폴더→cwd→/dev/shm→/tmp→/run/user를 *쓰고 로드까지* 시도하고, 그 어디도 안 되면 memfd_create로
익명 메모리에 올려 dlopen한다. 이 테스트가 각 보루가 실제로 작동함을 증명한다:

  A. memfd_create 로드가 이 호스트(≈서버 Ubuntu 24.04)서 *실제로* 된다(최종 폴백이 이론 아님).
  B. 정상 경로(무방해)서 캐스케이드가 실행폴더 .so로 로드된다(회귀 없음).
  C. *모든 디스크 타깃을 비우면* 캐스케이드가 memfd까지 내려가 로드되고, 그 memfd 엔진이 900-혼잡을
     실제로 construct한다(obj << 폴백 736M) — 쓰기-위치가 통째로 막혀도 C가 켜진다.
  D. *실제 noexec 마운트*(unshare 마운트네임스페이스 + noexec tmpfs over /tmp)서 디스크 dlopen은
     실패하고 memfd는 성공한다 — 서버 실패 메커니즘(noexec)에 직접 대조. unshare 불가 호스트면 skip.

종료코드 0=전부 통과. learning/ 스크래치(제출·게이트 무관)지만 'How/Verify' 근거가 된다(features/18)."""
import contextlib
import copy
import ctypes
import io
import json
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import c_engine  # noqa
from utils import check_feasibility  # noqa

LARGE_FALLBACK = 736453961
_FAILS = []


def _cleanup_disk():
    """이전 시도가 남긴 디코딩 산물(import용 scan_engine_ext.abi3.so + ctypes용 lib_scan_engine.so)을
    모든 쓰기 후보에서 제거(잔재가 다음 테스트를 오염시키지 않게)."""
    for d in (SRC, os.path.abspath("."), "/dev/shm", "/tmp"):
        for n in ("lib_scan_engine.so", "scan_engine_ext.abi3.so"):
            try:
                os.remove(os.path.join(d, n))
            except OSError:
                pass


def _reset():
    c_engine._ENGINE = None
    c_engine._ENGINE_TRIED = False
    import sys as _sys
    _sys.modules.pop("scan_engine_ext", None)   # import 경로 재시도 가능하게


def _check(cond, label):
    print(("  ok  " if cond else "  FAIL") + "  " + label)
    if not cond:
        _FAILS.append(label)


def test_A_memfd_real():
    raw = c_engine._b64_raw(c_engine._PLAIN_B64_NAME)   # 평문 .so(ctypes/memfd 폴백용)
    _check(raw is not None and len(raw) > 1000, "A1 평문 .b64 디코딩 → raw .so 바이트")
    lib = c_engine._load_from_memfd(raw, ctypes)
    _check(lib is not None, "A2 memfd_create 로드가 이 호스트서 실제로 됨(ctypes 폴백의 최종보루)")
    _check(lib is not None and hasattr(lib, "scan_run"), "A3 memfd 로드본에 scan_run 심볼 존재")


def test_B_normal_path():
    """정상 경로 — 1순위 import(DMS 메커니즘)로 로드되어야 한다."""
    import sys
    _cleanup_disk(); _reset()
    ok = c_engine.c_engine_available()
    _check(ok, "B1 정상(무방해) 엔진 로드 — 회귀 없음")
    _check("scan_engine_ext" in sys.modules, "B2 *import 경로*로 로드됨(DMS 입증 1순위, ctypes 아님)")


def _fire_900(label):
    """현재 캐시된 _LIB로 900-혼잡 construct → feasible + obj << 폴백이면 C가 실제로 켜진 것."""
    p20 = json.load(open(os.path.join(ROOT, "train", "prob_20.json")))
    big = copy.deepcopy(p20)
    big["blocks"] = [copy.deepcopy(b) for _ in range(3) for b in p20["blocks"]]
    import myalgorithm
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sol = myalgorithm.algorithm(big, 60.0)
    chk = check_feasibility(big, sol)
    feas = chk["feasible"]
    obj = chk["objective"] if feas else -1
    fired = feas and obj < LARGE_FALLBACK * 0.9
    _check(fired, f"{label} feasible={feas} obj={obj:,.0f} (폴백 {LARGE_FALLBACK:,}) → C 발화")


def test_C_force_memfd():
    """모든 디스크 쓰기 타깃을 비워 캐스케이드가 memfd까지 내려가게 강제. ①(직접 .so/.bin) 무효화
    위해 디스크 정리 후, _write_dirs를 []로 막는다 → ② 디스크 루프 0회 → ③ memfd만 남는다."""
    _cleanup_disk(); _reset()
    orig = c_engine._write_dirs
    c_engine._write_dirs = lambda: []   # 디스크 타깃 전무 → memfd 강제
    try:
        ok = c_engine.c_engine_available()
        _check(ok, "C1 디스크 타깃 전무 → 캐스케이드가 memfd로 로드")
        # 캐시된 _LIB이 memfd 핸들. 실제 construct까지 되는지(로드만이 아니라 계산):
        if ok:
            _fire_900("C2")
    finally:
        c_engine._write_dirs = orig
        _cleanup_disk()


def test_D_real_noexec():
    """실제 noexec 마운트서 디스크 dlopen 실패·memfd 성공을 자식 프로세스(unshare 마운트ns)서 증명."""
    child = r'''
import os, sys, ctypes
sys.path.insert(0, %r)
import c_engine
raw = c_engine._b64_raw(c_engine._PLAIN_B64_NAME)
p = "/tmp/lib_scan_engine.so"
open(p, "wb").write(raw)
disk = c_engine._try_cdll(p, ctypes)         # /tmp가 noexec면 dlopen(mmap PROT_EXEC) 실패
mem  = c_engine._load_from_memfd(raw, ctypes)  # 익명 메모리 → noexec 마운트 무관
print("DISK", disk is not None)
print("MEMFD", mem is not None)
''' % SRC
    # unshare -Urm: 사용자+마운트 네임스페이스(rootless). 그 안에서 /tmp에 noexec tmpfs 덮어쓰기.
    wrapped = ("mount -t tmpfs -o noexec tmpfs /tmp && "
               "python -c \"$CHILD\"")
    env = dict(os.environ, CHILD=child)
    try:
        r = subprocess.run(["unshare", "-Urm", "bash", "-c", wrapped],
                           capture_output=True, text=True, env=env, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"  skip  D unshare 불가({type(e).__name__}) — A/C가 memfd 능력·도달을 이미 증명")
        return
    out = r.stdout
    if "DISK" not in out or "MEMFD" not in out:
        print(f"  skip  D unshare 환경 제약(rc={r.returncode}): {r.stderr.strip()[:200]}")
        return
    disk_loaded = "DISK True" in out
    mem_loaded = "MEMFD True" in out
    _check(not disk_loaded, "D1 실제 noexec /tmp서 디스크 dlopen *실패*(서버 실패 메커니즘 재현)")
    _check(mem_loaded, "D2 같은 noexec 환경서 memfd 로드 *성공*(최종 폴백이 진짜 우회)")


if __name__ == "__main__":
    print("=== A. memfd 실로드 능력 ==="); test_A_memfd_real()
    print("=== B. 정상 경로 회귀 ==="); test_B_normal_path()
    print("=== C. 디스크 전무 → memfd 강제 + 발화 ==="); test_C_force_memfd()
    print("=== D. 실제 noexec 마운트 대조 ==="); test_D_real_noexec()
    _cleanup_disk()
    print("\n" + ("PASS — 디코딩-쓰기 위치 실패면 완전 봉인(디스크 캐스케이드 + memfd)"
                  if not _FAILS else f"FAIL — {_FAILS}"))
    sys.exit(0 if not _FAILS else 1)
