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
_BINARY_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan_engine")
_BINARY_CACHE = None   # 실제로 execve 되는 바이너리 경로(필요시 쓰기+exec 위치로 복사). _resolve_binary가 캐시.


def _can_exec(path: str) -> bool:
    """path의 바이너리를 인자 없이 한 번 실제로 execve 해 실행 가능 여부를 본다. 인자 없으면 usage를
    출력하고 종료(returncode 0)하므로 정상종료/usage = '이 호스트서 execve 가능'이다. +x 비트
    (os.access)만으론 noexec 마운트를 못 거르므로 *실제 실행*으로 판정한다. OSError(ENOEXEC·권한·
    seccomp)·timeout이면 False."""
    try:
        r = subprocess.run([path], capture_output=True, timeout=10)
        return r.returncode == 0 or b"usage" in (r.stdout + r.stderr)
    except Exception:
        return False


def _resolve_binary():
    """*실제로 execve 되는* scan_engine 경로를 반환한다(없으면 None, 캐시).

    ★왜 단순 chmod로 부족한가(서버서 C가 통째 무력화된 진짜 원인 후보). 평가 서버는 firejail로 파일
    시스템을 실행 폴더에 가두고("상위 디렉터리 접근 불가", 명세 §3.2) zip을 풀 때 +x를 벗긴다(0o644).
    실행 폴더가 *읽기전용*이면 제자리 `os.chmod`가 except로 조용히 실패→바이너리 0o644 그대로→실행
    불가→`_CENGINE_OK=False`→cengine·portfolio가 라우팅조차 안 돼 폴백(P3=736M 무변). v1.3.1의 제자리
    chmod가 이 경우 무력했다. 그런데 supervisor가 `/tmp`에 pickle로 자식 IPC를 하고 서버서 동작하므로
    (P1~P6 정상값) **`/tmp`는 쓰기가능**임이 확인된다. 그래서 제자리가 안 되면 바이너리를 쓰기가능
    위치로 *복사*해 거기서 +x를 주고 실행한다 -- 읽기전용 실행 폴더를 우회한다.

    순서: (1) 제자리 chmod 후 실제 실행 시험, (2) 실패 시 임시디렉터리/cwd/홈으로 복사+chmod 후 실행
    시험. 각 후보를 *실제 execve*로 판정(noexec 마운트까지 거른다). 전부 실패면 None→폴백(−1 불가).
    execve 자체가 seccomp로 막힌 환경이면 모든 후보가 실패→None→안전 폴백."""
    global _BINARY_CACHE
    if _BINARY_CACHE and _can_exec(_BINARY_CACHE):
        return _BINARY_CACHE
    if not os.path.isfile(_BINARY_SRC):
        return None
    # (1) 제자리: 폴더가 쓰기가능하면 chmod 성공 → 복사 비용 0
    try:
        os.chmod(_BINARY_SRC, 0o755)
    except Exception:
        pass
    if _can_exec(_BINARY_SRC):
        _BINARY_CACHE = _BINARY_SRC
        return _BINARY_CACHE
    # (2) 제자리 실패(비소유 EPERM·ro-mount EROFS) → 쓰기+exec 후보로 복사 후 실행. 후보 순서:
    #   실행폴더(바이너리가 거기서 도니 *exec 보장* — 비소유여도 폴더가 쓰기가능하면 소유 복사본 생성)
    #   → /tmp(supervisor가 쓰기 입증, 단 noexec 마운트 가능) → cwd → 홈. noexec/읽기전용이면 다음 후보로.
    import shutil
    seen = set()
    exec_dir = os.path.dirname(_BINARY_SRC)
    for base in (exec_dir, tempfile.gettempdir(), os.getcwd(), os.path.expanduser("~")):
        if not base or base in seen:
            continue
        seen.add(base)
        try:
            d = tempfile.mkdtemp(prefix="ceng_bin_", dir=base)
            dst = os.path.join(d, "scan_engine")
            shutil.copy2(_BINARY_SRC, dst)
            os.chmod(dst, 0o755)
        except Exception:
            continue
        if _can_exec(dst):
            _BINARY_CACHE = dst
            return _BINARY_CACHE
    return None


def c_engine_available() -> bool:
    """C 엔진 바이너리가 이 호스트에서 *실제로 실행되는가*(_resolve_binary 참조). 실패 시 False→폴백."""
    return _resolve_binary() is not None


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
    binary = _resolve_binary()
    if binary is None:
        return None
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="ceng_")
        inp = os.path.join(tmpdir, "in.bin")
        outp = os.path.join(tmpdir, "out.bin")
        _marshal(prob_info, ir, inp, orders)
        if max_s is None and deadline is not None:
            max_s = max(1.0, deadline - time.time() - 1.5)   # 마샬 후 남은 배치 예산
        cmd = [binary, inp, outp]
        if max_s is not None:
            cmd.append(str(max_s))
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if r.returncode != 0 or not os.path.exists(outp):
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
