# c_engine.py
# =============================================================================
# C scan constructor 래퍼 -- Python이 ir.masks()로 래스터화한 마스크+메타를 바이너리로
# 마샬링해 동봉된 정적 C 바이너리(scan_engine)에 넘기고, C가 scan+크레인+occupancy로
# construct한 placement를 받아 검증한다. C는 Python scan 구성기의 *byte-identical 복제*이되
# native u64 비트마스크라 ~19-22× 빠르다(혼잡 900블록 134초 scan → C 7초).
#
# 두 가지 진입점:
#   - run_c_engine: 단일 EDD 순서 1회 construct. 대형-혼잡(n>350)에서 Python scan이 못 끝내던
#     nesting 품질(339M)을 60초 안에 *완주*해 낸다(features/18).
#   - run_portfolio: *수천 개의 다양한 구성 순서*를 C가 한 번 호출로 다 돌려 내부 obj로 best를
#     고른다(시간가드). 소형~중형에서 구성 순서가 obj를 지배하는데 우리 EDD+ALNS는 그 순서
#     공간을 안 봐 거대한 헤드룸을 흘린다 -- 측정: prob_1(n=100) 21,021→4,996(+76%). best는
#     committed로 재구성해 호출부가 ALNS로 polish(features/19).
#
# 안전: 어떤 실패(바이너리 부재·비-0 종료·파싱오류·infeasible·예외)에서도 None을 반환해
# 호출부가 표준 Python 경로/floor로 폴백한다(feasibility-first, best-of). 정적 바이너리라
# 서버서 의존성 0이지만, OS/arch 비호환 시에도 subprocess 실패→None→폴백이라 −1 불가.
# =============================================================================

from __future__ import annotations

import os
import random
import struct
import subprocess
import tempfile
import time

try:  # flat layout (제출/batch_runner)
    from utils import check_feasibility
    from baseline_greedy import _build_operations
    from constructor import _rel_bbox, loads_from_committed
except ImportError:  # IDE package layout
    from ogc2026.baseline.utils import check_feasibility
    from ogc2026.baseline.baseline_greedy import _build_operations
    from ogc2026.src.constructor import _rel_bbox, loads_from_committed

_MAGIC = 0x5343414E
# ★공유 라이브러리(.so)를 ctypes로 in-process 로드한다. ★이전 OGC *우승팀* 자료가 정전 컨벤션을
#   확정했다 — `ctypes.CDLL('./lib_myalgorithm.so')`로 동봉 .so를 algorithm() 안에서 로드해 우승했다
#   (Gurobi까지 동적 링크). ⇒ **서버는 동봉 .so를 ctypes로 잘 로드한다**(제출 폴더 noexec 아님 — 옛
#   noexec/memfd 가설 *폐기*). 우리 v1.4.x가 P3=736M에 머문 건 *우리 일탈* 탓으로 좁혀진다:
#   ① 파일명 `scan_engine.bin`+무SONAME(우승팀은 `lib_*.so`+SONAME), ② import 시점 로드(우승팀은
#   call 시점), ③ os.fork 자식 호출(우승팀은 메인). 수정: 컨벤션에 맞춰 `lib_scan_engine.so`
#   (lib접두+SONAME)를 plain ctypes로 절대·cwd상대 다중경로로 로드하고, 로드 시점은 myalgorithm이
#   call 시점에 lazy 호출한다. 제출 시 Gmail이 .so-in-zip을 막으면 `scan_engine.bin`으로 동봉할 수
#   있게 두 이름을 다 시도한다(로더는 이름-불문, dlopen은 확장자 무관).
_B64_NAME = "scan_engine.b64"   # ★.so를 base64로 동봉(이메일 통과)→런타임 디코딩(조직위 권고)
_LIB_NAMES = ("lib_scan_engine.so", "scan_engine.bin")   # 직접 동봉본 폴백(디코딩본 우선)
_LIB = None         # ctypes.CDLL 핸들(캐시)
_LIB_TRIED = False


def _decode_so():
    """★진단 확정(서버서 scan_engine.bin _CENGINE_OK=False=*미로드*) + 조직위 권고의 수정:
    문제 파일(.so)을 base64로 동봉해 이메일 서비스(Gmail이 .so-in-zip 차단)를 통과시키고, *런타임에
    원래 .so로 디코딩*해 디스크에 쓴 뒤 로드한다. 서버가 *.so 확장자만 mmap-exec 허용(우리 .bin이
    데이터 취급돼 미로드된 추정 원인)이라 **진짜 `lib_scan_engine.so` 확장자**로 재구성한다.
    쓰기 위치: 실행폴더(1등팀 './lib_*.so' 위치) 우선, 실패 시 /tmp. 디코딩·쓰기 실패면 None(폴백)."""
    import base64
    here = os.path.dirname(os.path.abspath(__file__))
    b64p = os.path.join(here, _B64_NAME)
    if not os.path.isfile(b64p):
        return None
    try:
        raw = base64.b64decode(open(b64p, "rb").read())
    except Exception:
        return None
    for d in (here, tempfile.gettempdir()):
        try:
            p = os.path.join(d, "lib_scan_engine.so")
            with open(p, "wb") as f:
                f.write(raw)
            if os.path.getsize(p) == len(raw):
                return p
        except Exception:
            continue
    return None


def _candidate_paths():
    """로드 후보 — ★base64 동봉본을 런타임 디코딩한 *진짜 .so*를 최우선, 그다음 직접 동봉본
    (각 이름을 절대 dirname·cwd상대)."""
    here = os.path.dirname(os.path.abspath(__file__))
    out = []
    try:
        dec = _decode_so()    # ★scan_engine.b64 → lib_scan_engine.so 디코딩(진짜 .so 확장자)
    except Exception:
        dec = None
    if dec:
        out.append(dec)
    for n in _LIB_NAMES:
        out.append(os.path.join(here, n))   # 절대(robust)
        out.append(os.path.join(".", n))    # cwd-상대(서버 cwd=실행폴더 가정, 우승팀 방식)
    return out


def _load_lib():
    """동봉 .so를 plain `ctypes.CDLL`로 로드. ★base64 동봉본을 런타임 디코딩한 *진짜 lib_scan_engine.so*를
    최우선 시도(조직위 권고·.bin 서버 미로드 수정), 그다음 직접 동봉본 폴백. 실패 시 None→호출부 폴백
    (−1 불가). 호출 시점은 myalgorithm이 call 시점에 lazy 호출(우승팀 컨벤션)."""
    global _LIB, _LIB_TRIED
    if _LIB_TRIED:
        return _LIB
    _LIB_TRIED = True
    import ctypes
    for p in _candidate_paths():
        try:
            if not os.path.isfile(p):
                continue
            lib = ctypes.CDLL(p)
            lib.scan_run.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_double]
            lib.scan_run.restype = ctypes.c_int
            _LIB = lib
            return _LIB
        except Exception:
            continue
    return _LIB


def c_engine_available() -> bool:
    """C 엔진 .so가 이 호스트에서 dlopen 가능한가(=ctypes.CDLL 성공). 실패 시 False→폴백(−1 불가)."""
    return _load_lib() is not None


def _edd_order(blocks):
    return sorted(range(len(blocks)),
                  key=lambda i: (blocks[i]["due_date"], blocks[i]["processing_time"]))


def _gen_orders(prob_info, ir, n_orders, seed):
    """다양한 구성 순서 n_orders개. 결정적 4개(EDD/edd_area/slack/release) + perturbed-EDD.
    perturbation 강도를 due-span에 비례해 폭넓게 섞어 순서 공간을 넓게 표본한다(features/19)."""
    b = prob_info["blocks"]; n = len(b); rng = random.Random(seed)
    due = [b[i]["due_date"] for i in range(n)]
    proc = [b[i]["processing_time"] for i in range(n)]
    rel = [b[i]["release_time"] for i in range(n)]

    def area(i):
        bb = ir.local_bbox(i, 0); return (bb[2] - bb[0]) * (bb[3] - bb[1])

    orders = [
        sorted(range(n), key=lambda i: (due[i], proc[i])),                    # EDD
        sorted(range(n), key=lambda i: (due[i], -area(i))),                   # edd_area
        sorted(range(n), key=lambda i: (due[i] - rel[i] - proc[i], due[i])),  # slack
        sorted(range(n), key=lambda i: (rel[i], due[i])),                     # release
    ]
    span = (max(due) - min(due) + 1) if n else 1
    while len(orders) < n_orders:
        temp = span * (0.03 + 0.7 * rng.random())
        noisy = [(due[i] + rng.uniform(-temp, temp), proc[i]) for i in range(n)]
        orders.append(sorted(range(n), key=lambda i: noisy[i]))
    return orders[:max(1, n_orders)]


def _marshal(prob_info, ir, path, orders):
    """인스턴스 기하 + 구성 순서들(orders)을 바이너리로. orders=[순서1, 순서2, ...]
    (각 순서는 block_id 순열). C는 N_ORD개를 배치로 돌려 best를 낸다."""
    bays = prob_info["bays"]
    blocks = prob_info["blocks"]
    n_bays = len(bays)
    max_w = max(int(b["width"]) for b in bays)
    words = (max_w + 63) // 64 + 1   # +1 시프트 헤드룸
    w = prob_info.get("weights", {})
    buf = bytearray()
    buf += struct.pack("<5i3d", _MAGIC, n_bays, len(blocks), ir.max_layers, words,
                       w.get("w1", 1.0), w.get("w2", 1.0), w.get("w3", 1.0))
    for b in bays:
        buf += struct.pack("<2i", int(b["width"]), int(b["height"]))
    for bid, blk in enumerate(blocks):
        prefs = blk.get("bay_preferences") or [0.0] * n_bays
        prefs = (list(prefs) + [0.0] * n_bays)[:n_bays]
        buf += struct.pack("<3id", int(blk["release_time"]), int(blk["processing_time"]),
                           int(blk["due_date"]), float(blk.get("workload", 0.0)))
        buf += struct.pack(f"<{n_bays}d", *prefs)
        n_orient = len(blk["shape"])
        buf += struct.pack("<i", n_orient)
        for o in range(n_orient):
            bb = ir.local_bbox(bid, o)
            ref = ir._ref(bid, o)
            buf += struct.pack("<4d", bb[0] - ref[0], bb[1] - ref[1],
                               bb[2] - ref[0], bb[3] - ref[1])
            masks = ir.masks(bid, o)
            buf += struct.pack("<i", len(masks))
            for lm in masks:
                if lm.empty:
                    buf += struct.pack("<3i", 0, 0, 0)
                    continue
                buf += struct.pack("<3i", lm.my0, lm.mx0, lm.h)
                for ri in range(lm.h):
                    v = lm.row_ints[ri] if ri < len(lm.row_ints) else 0
                    for k in range(words):
                        buf += struct.pack("<Q", (v >> (64 * k)) & 0xFFFFFFFFFFFFFFFF)
    # 구성 순서들 (N_ORD, 각 len(blocks))
    buf += struct.pack("<i", len(orders))
    for od in orders:
        buf += struct.pack(f"<{len(od)}i", *od)
    with open(path, "wb") as f:
        f.write(buf)


def _parse(path):
    """C 출력: best 내부 obj(double) + n(int) + n개 placement(7 int). (c_obj, assignments)."""
    with open(path, "rb") as f:
        data = f.read()
    (c_obj,) = struct.unpack_from("<d", data, 0)
    (n,) = struct.unpack_from("<i", data, 8)
    off = 12
    assignments = []
    for _ in range(n):
        bid, bay, px, py, orient, entry, ex = struct.unpack_from("<7i", data, off)
        off += 28
        assignments.append({
            "block_id": int(bid), "bay_id": int(bay), "x": int(px), "y": int(py),
            "orient_idx": int(orient), "entry_time": int(entry), "exit_time": int(ex),
        })
    return c_obj, assignments


def _run_binary(prob_info, ir, orders, max_s, timeout, deadline=None):
    """marshal → subprocess(scan_engine in out [max_s]) → parse. (c_obj, assignments) 또는 None.

    deadline(벽시계 절대시각)을 주면 *마샬 직후* 남은 시간으로 max_s를 정한다 -- 마샬(대형 Shapely
    래스터화)이 가변이라, 여러 순서를 시도할 때 마샬+배치가 deadline을 넘지 않게 한다. C는 정밀
    시간가드(순서마다 체크+다음순서 예측)로 max_s를 지키고, EDD가 첫 순서라 1개만 들어도 안전."""
    lib = _load_lib()
    if lib is None:
        return None
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="ceng_")
        inp = os.path.join(tmpdir, "in.bin")
        outp = os.path.join(tmpdir, "out.bin")
        _marshal(prob_info, ir, inp, orders)
        if max_s is None and deadline is not None:
            max_s = max(1.0, deadline - time.time() - 1.5)   # 마샬 후 남은 배치 예산
        # ctypes 직접 호출(in-process, dlopen) — subprocess(execve) 대체. timeout은 in-process라
        # Python서 강제 못 함(스레드 블록); C 내부 max_s 시간가드가 벽시계 상한을 지키고, 그래도
        # 넘기면 supervisor가 return_cap에 자식째 SIGKILL(=옛 subprocess timeout 역할). (void)timeout.
        rc = lib.scan_run(inp.encode(), outp.encode(),
                          float(max_s if max_s is not None else 0.0))
        if rc != 0 or not os.path.exists(outp):
            return None
        c_obj, assignments = _parse(outp)
        if len(assignments) != len(prob_info["blocks"]):
            return None
        return c_obj, assignments
    except Exception:
        return None
    finally:
        if tmpdir:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


def run_c_engine(ir, prob_info, timeout=None, deadline=None):
    """C scan 엔진으로 *4개 결정 순서*(EDD·edd_area·slack·release) best-of construct →
    (objective, solution_dict). 실패 시 None(호출부 폴백).

    대형(n>350)서도 구성 순서가 obj를 가른다 -- 측정 900-혼잡 EDD단일 338.7M vs 4순서 best
    332.2M(−1.9%, features/18·19). 각 construct가 비싸(900블록 ~5s) deadline-적응 max_s + C 정밀
    시간가드로 든 만큼만 돌고(EDD가 첫 순서라 1개만 들어도 = 옛 단일 EDD와 동일 = 무회귀), 시간이
    남으면 더 나은 순서를 찾는다. deadline -- 벽시계 절대 마감(없으면 무제한, 호출부가 줘 overrun 차단).
    반환 solution은 검증기 통과(feasible)만; infeasible/실패는 None.
    """
    res = _run_binary(prob_info, ir, _gen_orders(prob_info, ir, 4, 0),
                      max_s=None, timeout=timeout, deadline=deadline)
    if res is None:
        return None
    try:
        _c_obj, assignments = res
        sol = {"operations": _build_operations(assignments)}
        chk = check_feasibility(prob_info, sol)
        if not chk.get("feasible"):
            return None
        return float(chk["objective"]), sol
    except Exception:
        return None


def run_portfolio(ir, prob_info, port_s, n_orders, seed, timeout):
    """*수천 개 구성 순서*를 C가 한 번 호출로 배치 처리해 best를 committed 상태로 재구성한다.
    (committed, loads, bw) 또는 None. 호출부(_portfolio_body)가 그 위에서 ALNS polish.

    port_s -- C 배치 루프의 벽시계 상한(초, 그 안에 든 순서만 평가). n_orders -- 생성할 순서 수
    (C가 시간가드로 일부만 돌 수 있음). 재구성 committed는 constructor와 동일 포맷이라 ALNS/
    operations_from_committed가 그대로 소비한다(bay,bid,orient,px,py,entry,exit,masks,wbb)."""
    try:
        orders = _gen_orders(prob_info, ir, n_orders, seed)
    except Exception:
        return None
    res = _run_binary(prob_info, ir, orders, max_s=port_s, timeout=timeout)
    if res is None:
        return None
    try:
        _c_obj, assignments = res
        nb = len(prob_info["bays"])
        committed = [[] for _ in range(nb)]
        for a in assignments:
            bid = a["block_id"]; o = a["orient_idx"]; px = a["x"]; py = a["y"]
            rel = _rel_bbox(ir, bid, o)
            committed[a["bay_id"]].append({
                "bay": a["bay_id"], "bid": bid, "orient": o, "px": px, "py": py,
                "entry": a["entry_time"], "exit": a["exit_time"], "masks": ir.masks(bid, o),
                "wbb": (px + rel[0], py + rel[1], px + rel[2], py + rel[3])})
        loads = loads_from_committed(committed, prob_info["blocks"], nb)
        ba = [prob_info["bays"][j]["width"] * prob_info["bays"][j]["height"] for j in range(nb)]
        avg = sum(ba) / nb if nb else 1.0
        bw = [avg / a if a else 0.0 for a in ba]
        return committed, loads, bw
    except Exception:
        return None
