# c_engine.py
# =============================================================================
# C scan constructor 래퍼 -- Python이 ir.masks()로 래스터화한 마스크+메타를 바이너리로
# 마샬링해 동봉된 정적 C 바이너리(scan_engine)에 넘기고, C가 EDD+scan+크레인+occupancy로
# construct한 placement를 받아 검증한다. C는 Python scan 구성기의 *byte-identical 복제*이되
# native u64 비트마스크라 ~19-22× 빠르다(혼잡 900블록 134초 scan → C 7초). 그래서 단축-tl
# 대형-혼잡에서 Python scan이 못 끝내던 nesting 품질(339M)을 60초 안에 *완주*해 낸다.
#
# 안전: 어떤 실패(바이너리 부재·비-0 종료·파싱오류·infeasible·예외)에서도 None을 반환해
# 호출부가 표준 Python 경로/floor로 폴백한다(feasibility-first, best-of). 정적 바이너리라
# 서버서 의존성 0이지만, OS/arch 비호환 시에도 subprocess 실패→None→폴백이라 −1 불가.
# =============================================================================

from __future__ import annotations

import os
import struct
import subprocess
import tempfile

try:  # flat layout (제출/batch_runner)
    from utils import check_feasibility
    from baseline_greedy import _build_operations
except ImportError:  # IDE package layout
    from ogc2026.baseline.utils import check_feasibility
    from ogc2026.baseline.baseline_greedy import _build_operations

_MAGIC = 0x5343414E
_BINARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan_engine")


def c_engine_available() -> bool:
    """바이너리가 존재하고 실행 가능한가."""
    return os.path.isfile(_BINARY) and os.access(_BINARY, os.X_OK)


def _marshal(prob_info, ir, path):
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
    with open(path, "wb") as f:
        f.write(buf)


def _parse(path):
    with open(path, "rb") as f:
        data = f.read()
    (n,) = struct.unpack_from("<i", data, 0)
    off = 4
    assignments = []
    for _ in range(n):
        bid, bay, px, py, orient, entry, ex = struct.unpack_from("<7i", data, off)
        off += 28
        assignments.append({
            "block_id": int(bid), "bay_id": int(bay), "x": int(px), "y": int(py),
            "orient_idx": int(orient), "entry_time": int(entry), "exit_time": int(ex),
        })
    return assignments


def run_c_engine(ir, prob_info, timeout=None):
    """C scan 엔진으로 construct → (objective, solution_dict). 실패 시 None(호출부 폴백).

    ir -- InstanceRaster(마스크 캐시). prob_info -- 인스턴스. timeout -- subprocess 벽시계 상한(초).
    반환 solution은 검증기 통과(feasible)만; infeasible/실패는 None.
    """
    if not c_engine_available():
        return None
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="ceng_")
        inp = os.path.join(tmpdir, "in.bin")
        outp = os.path.join(tmpdir, "out.bin")
        _marshal(prob_info, ir, inp)
        r = subprocess.run([_BINARY, inp, outp], capture_output=True, timeout=timeout)
        if r.returncode != 0 or not os.path.exists(outp):
            return None
        assignments = _parse(outp)
        if len(assignments) != len(prob_info["blocks"]):
            return None
        sol = {"operations": _build_operations(assignments)}
        res = check_feasibility(prob_info, sol)
        if not res.get("feasible"):
            return None
        return float(res["objective"]), sol
    except Exception:
        return None
    finally:
        if tmpdir:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
