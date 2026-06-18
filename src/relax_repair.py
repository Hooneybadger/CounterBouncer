# relax_repair.py
# =============================================================================
# relax-and-repair 구성기 -- obj1(지각)의 *전역 스케줄* 국소최적을 깬다.
#
# 진단(docs/RESULTS.md 4.1): EDD-greedy 구성 + 독립 repair는 나중 블록이 먼저 블록을
# 밀어내는 *전역 스케줄* 실수를 못 푼다. prob_38의 obj1=5129는 1800초(30배 예산)에도
# 안 움직였으나, 혼잡 코어의 스케줄을 CP로 최적화하면 4583(-10.6%)까지 내려간다.
#
# 방법: bbox(직사각형) 완화를 CP-SAT로 풀어 코어 블록의 (베이, entry)를 *전역 최적*하고,
# 그 스케줄을 래스터 엔진으로 크레인-repair(scan=nesting)한다. bbox >= 다각형이라
# bbox-no-overlap 스케줄은 공간상 진짜로도 feasible(보수적). CP엔 다각형·크레인을 안 실어
# B5(임의-다각형 MIP 금지)를 지킨다 -- 그 둘은 래스터가 처리한다.
#
# ortools는 ogc2026 conda 환경(평가 서버와 동일)에 포함되나, 없을 때도 안전하게 None을
# 반환해 호출부가 표준 구성으로 폴백하도록 optional import 한다.
# =============================================================================

from __future__ import annotations

import math
import time

try:  # flat layout
    from utils import _resolve_layers
    from constructor import _best_in_bay, _rel_bbox, loads_from_committed
except ImportError:  # IDE package layout
    from ogc2026.baseline.utils import _resolve_layers
    from ogc2026.src.constructor import _best_in_bay, _rel_bbox, loads_from_committed

try:
    from ortools.sat.python import cp_model
    _HAS_ORTOOLS = True
except Exception:
    _HAS_ORTOOLS = False


def ortools_available() -> bool:
    return _HAS_ORTOOLS


def _bbox_orients(blk):
    """방향별 정수 (w,h) -- layer0 정점의 bbox를 ceil. bbox >= 진짜 footprint(보수적)."""
    out = set()
    for o in blk["shape"]:
        l0 = _resolve_layers(o["layers"])[0]
        xs = [v[0] for v in l0]; ys = [v[1] for v in l0]
        w = math.ceil(max(xs) - min(xs)); h = math.ceil(max(ys) - min(ys))
        if w > 0 and h > 0:
            out.add((w, h))
    return sorted(out)


def solve_core_schedule(prob_info, core_ids, time_cap, workers):
    """혼잡 코어 블록(core_ids)의 (베이, entry)를 bbox 완화 CP로 전역 최적. 반환: {gid:(bay,entry)} or None.

    솔버 변수: 블록당 (베이·방향·위치) 택일 + entry. 제약: bbox 2D no-overlap(같은 베이·시간겹침
    시 x/y/시간 5-way 분리) + entry>=release + exit=entry+proc. 목적: Σ 지각 최소화. 크레인·다각형은
    여기서 빼고(완화) repair가 처리한다.
    """
    if not _HAS_ORTOOLS or not core_ids:
        return None
    bays = prob_info["bays"]
    blocks = prob_info["blocks"]
    nb = len(bays)
    sub = [(gid, dict(r=int(blocks[gid]["release_time"]),
                      p=int(blocks[gid]["processing_time"]),
                      due=int(blocks[gid]["due_date"]),
                      orients=_bbox_orients(blocks[gid]))) for gid in core_ids]
    m = cp_model.CpModel()
    H = max(max(j["due"] for _, j in sub), max(j["r"] for _, j in sub)) + sum(j["p"] for _, j in sub)
    B = {}
    for gid, j in sub:
        entry = m.NewIntVar(j["r"], H, "")
        exit_ = m.NewIntVar(j["r"], H + j["p"], "")
        m.Add(exit_ == entry + j["p"])
        tard = m.NewIntVar(0, H, "")
        m.Add(tard >= exit_ - j["due"])
        opts = []
        for b in range(nb):
            W, Hh = bays[b]["width"], bays[b]["height"]
            for (w, h) in j["orients"]:
                if w > W or h > Hh:
                    continue
                lit = m.NewBoolVar("")
                px = m.NewIntVar(0, W - w, ""); py = m.NewIntVar(0, Hh - h, "")
                opts.append(dict(lit=lit, bay=b, w=w, h=h, px=px, py=py))
        if not opts:
            return None  # 코어에 안 맞는 블록 -- 폴백
        m.AddExactlyOne([o["lit"] for o in opts])
        Wm = max(o["w"] for o in opts); Hm = max(o["h"] for o in opts); Bm = max(o["bay"] for o in opts)
        X = m.NewIntVar(0, max(bays[b]["width"] for b in range(nb)), "")
        Y = m.NewIntVar(0, max(bays[b]["height"] for b in range(nb)), "")
        Wv = m.NewIntVar(1, Wm, ""); Hv = m.NewIntVar(1, Hm, ""); Bv = m.NewIntVar(0, Bm, "")
        for o in opts:
            m.Add(X == o["px"]).OnlyEnforceIf(o["lit"])
            m.Add(Y == o["py"]).OnlyEnforceIf(o["lit"])
            m.Add(Wv == o["w"]).OnlyEnforceIf(o["lit"])
            m.Add(Hv == o["h"]).OnlyEnforceIf(o["lit"])
            m.Add(Bv == o["bay"]).OnlyEnforceIf(o["lit"])
        B[gid] = dict(entry=entry, exit=exit_, tard=tard, X=X, Y=Y, Wv=Wv, Hv=Hv, Bv=Bv)

    gids = [g for g, _ in sub]
    for a in range(len(gids)):
        for c in range(a + 1, len(gids)):
            i, k = gids[a], gids[c]
            bi, bk = B[i], B[k]
            sb = m.NewBoolVar("")
            m.Add(bi["Bv"] == bk["Bv"]).OnlyEnforceIf(sb)
            m.Add(bi["Bv"] != bk["Bv"]).OnlyEnforceIf(sb.Not())
            sep = [m.NewBoolVar("") for _ in range(6)]
            m.Add(bi["exit"] <= bk["entry"]).OnlyEnforceIf(sep[0])
            m.Add(bk["exit"] <= bi["entry"]).OnlyEnforceIf(sep[1])
            m.Add(bi["X"] + bi["Wv"] <= bk["X"]).OnlyEnforceIf(sep[2])
            m.Add(bk["X"] + bk["Wv"] <= bi["X"]).OnlyEnforceIf(sep[3])
            m.Add(bi["Y"] + bi["Hv"] <= bk["Y"]).OnlyEnforceIf(sep[4])
            m.Add(bk["Y"] + bk["Hv"] <= bi["Y"]).OnlyEnforceIf(sep[5])
            m.AddBoolOr(sep).OnlyEnforceIf(sb)

    m.Minimize(sum(B[g]["tard"] for g in gids))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_cap)
    solver.parameters.num_workers = int(workers)
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return {g: (int(solver.Value(B[g]["Bv"])), int(solver.Value(B[g]["entry"]))) for g in gids}


def _repair_from_schedule(prob_info, ir, sched, honor_entry):
    """CP 스케줄(코어의 베이+entry)을 래스터 엔진으로 크레인-repair. committed(구성기 형식) 반환.

    CP entry 오름차순으로 코어를 CP-베이에 _best_in_bay(scan=nesting)로 배치. honor_entry면 CP
    entry를 하한으로 써 타이밍 존중. 코어 밖 블록은 EDD로 둘러 배치. 어떤 베이도 안 되면 다른
    베이/release 하한으로 폴백 -- feasibility는 _best_in_bay의 양방향 크레인 검사가 보장한다.
    """
    blocks = prob_info["blocks"]
    nb = len(prob_info["bays"])
    committed = [[] for _ in range(nb)]
    order = sorted(sched.keys(), key=lambda g: sched[g][1])
    rest = [i for i in range(len(blocks)) if i not in sched]
    rest.sort(key=lambda i: (blocks[i]["due_date"], blocks[i]["processing_time"]))
    for gid in order + rest:
        blk = blocks[gid]
        proc = int(blk["processing_time"])
        rel = int(blk["release_time"])
        in_core = gid in sched
        lo = max(rel, sched[gid][1]) if (in_core and honor_entry) else rel
        pref_bay = sched[gid][0] if in_core else None
        bays_try = ([pref_bay] + [b for b in range(nb) if b != pref_bay]) if pref_bay is not None else list(range(nb))
        best = None
        for b in bays_try:
            r = _best_in_bay(ir, b, committed[b], gid, lo, proc, "scan")
            if r is not None and (best is None or r[0] < best[0]):
                best = (r[0], b, r)
            if pref_bay is not None and b == pref_bay and r is not None:
                break  # 선호 베이에 들어가면 그대로(스케줄 존중)
        if best is None and lo > rel:  # honor_entry 완화 재시도
            for b in bays_try:
                r = _best_in_bay(ir, b, committed[b], gid, rel, proc, "scan")
                if r is not None and (best is None or r[0] < best[0]):
                    best = (r[0], b, r)
        if best is None:
            continue  # 배치 실패(극히 드묾) -- 호출부 검증이 거름
        _e, b, (e, px, py, orient, _ty) = best
        rb = _rel_bbox(ir, gid, orient)
        committed[b].append({"bay": b, "bid": gid, "orient": orient, "px": px, "py": py,
                             "entry": e, "exit": e + proc, "masks": ir.masks(gid, orient),
                             "wbb": (px + rb[0], py + rb[1], px + rb[2], py + rb[3])})
    return committed


def relax_repair(ir, prob_info, t0, timelimit, cp_cap=8.0, workers=4, congest_n=60):
    """relax-and-repair 구성: CP 코어 스케줄 → 크레인-repair(두 변형 best). 반환: (committed, loads, bw) or None.

    congest_n -- CP가 다루는 혼잡 코어 크기(release 이른 순). CP-tractable 한계라 train 결과에
    맞춘 값이 아니라 *어떤 인스턴스에도 같은* 상한이다(과적합 금지). nb<congest_n이면 전체.
    """
    if not _HAS_ORTOOLS:
        return None
    blocks = prob_info["blocks"]
    n_bays = len(prob_info["bays"])
    order = sorted(range(len(blocks)), key=lambda i: (blocks[i]["release_time"], blocks[i]["due_date"]))
    core = order[:min(congest_n, len(order))]
    sched = solve_core_schedule(prob_info, core, cp_cap, workers)
    if sched is None:
        return None

    w = prob_info.get("weights", {})
    w1, w2, w3 = w.get("w1", 1.0), w.get("w2", 1.0), w.get("w3", 1.0)
    bay_areas = [prob_info["bays"][j]["width"] * prob_info["bays"][j]["height"] for j in range(n_bays)]
    avg = sum(bay_areas) / n_bays
    bw = [avg / a for a in bay_areas]

    # 두 repair 변형(타이밍 존중 / release 우선)의 best -- CP 최적해가 유일치 않아 변형마다 갈린다.
    from constructor import solution_obj
    best = None
    for honor in (True, False):
        committed = _repair_from_schedule(prob_info, ir, sched, honor)
        loads = loads_from_committed(committed, blocks, n_bays)
        obj = solution_obj(committed, blocks, bw, loads, w1, w2, w3)
        if best is None or obj < best[0]:
            best = (obj, committed, loads)
    return best[1], best[2], bw
