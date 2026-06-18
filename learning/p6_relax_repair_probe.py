"""Probe 1 -- relax-and-repair 도약의 go/no-go.

가설: 정체된 obj1(prob_38=5129)은 크레인 물리 한계가 아니라 EDD-greedy의 *전역 스케줄*
실수다(나중 블록이 먼저 블록을 밀어냄). 그렇다면 bbox 완화를 CP로 *전역 최적*해 더 나은
(베이, entry) 스케줄을 얻고, 그걸 래스터 엔진으로 크레인-repair하면 5129를 깰 수 있다.

bbox(직사각형) >= 다각형이라 bbox-no-overlap 해는 공간상 진짜로도 feasible(보수적 완화).
CP는 크레인(j>=k)만 무시 -> 그 부분을 래스터가 고친다. 솔버엔 다각형·크레인을 안 실어
B5 준수. ortools는 *로컬 분석 전용*(제출 코드 아님) -- 이 probe는 헤드룸이 닿는지만 본다.

  python learning/p6_relax_repair_probe.py prob_38 -t 120
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ortools.sat.python import cp_model                       # noqa: E402
from raster_engine import InstanceRaster                       # noqa: E402
from constructor import construct, solution_obj, loads_from_committed, _best_in_bay, _rel_bbox  # noqa: E402
from utils import check_feasibility                            # noqa: E402
sys.path.insert(0, os.path.dirname(__file__))
from p6_geom_lb import block_orients                           # noqa: E402


def solve_schedule(prob, time_limit, workers, shape="bbox", congest_n=None):
    """bbox 완화 CP로 (베이, entry) 전역 스케줄을 푼다. 반환: per-block dict(bay, entry) 또는 None.

    congest_n: 주어지면 release 이른 N개만 CP로 최적화(혼잡 코어), 나머지는 repair가 EDD로.
    """
    bays = prob["bays"]
    blocks = prob["blocks"]
    nb = len(bays)
    jobs = []
    for blk in blocks:
        jobs.append(dict(r=int(blk["release_time"]), p=int(blk["processing_time"]),
                         due=int(blk["due_date"]), orients=block_orients(blk, shape)))
    order = sorted(range(len(jobs)), key=lambda i: (jobs[i]["r"], jobs[i]["due"]))
    sel = order if congest_n is None else order[:congest_n]
    sub = [(i, jobs[i]) for i in sel]

    m = cp_model.CpModel()
    H = max(max(j["due"] for _, j in sub), max(j["r"] for _, j in sub)) + sum(j["p"] for _, j in sub)
    B = {}
    for gi, j in sub:
        entry = m.NewIntVar(j["r"], H, f"e{gi}")
        exit_ = m.NewIntVar(j["r"], H + j["p"], f"x{gi}")
        m.Add(exit_ == entry + j["p"])
        tard = m.NewIntVar(0, H, f"t{gi}")
        m.Add(tard >= exit_ - j["due"])
        opts = []
        for b in range(nb):
            W, Hh = bays[b]["width"], bays[b]["height"]
            for (w, h) in j["orients"]:
                if w > W or h > Hh:
                    continue
                lit = m.NewBoolVar(f"a{gi}_{b}_{w}_{h}")
                px = m.NewIntVar(0, W - w, f"px{gi}_{b}_{w}_{h}")
                py = m.NewIntVar(0, Hh - h, f"py{gi}_{b}_{w}_{h}")
                opts.append(dict(lit=lit, bay=b, w=w, h=h, px=px, py=py))
        if not opts:
            return None
        m.AddExactlyOne([o["lit"] for o in opts])
        Wm = max(o["w"] for o in opts); Hm = max(o["h"] for o in opts); Bm = max(o["bay"] for o in opts)
        X = m.NewIntVar(0, max(bays[b]["width"] for b in range(nb)), f"X{gi}")
        Y = m.NewIntVar(0, max(bays[b]["height"] for b in range(nb)), f"Y{gi}")
        Wv = m.NewIntVar(1, Wm, f"W{gi}"); Hv = m.NewIntVar(1, Hm, f"H{gi}")
        Bv = m.NewIntVar(0, Bm, f"B{gi}")
        for o in opts:
            m.Add(X == o["px"]).OnlyEnforceIf(o["lit"])
            m.Add(Y == o["py"]).OnlyEnforceIf(o["lit"])
            m.Add(Wv == o["w"]).OnlyEnforceIf(o["lit"])
            m.Add(Hv == o["h"]).OnlyEnforceIf(o["lit"])
            m.Add(Bv == o["bay"]).OnlyEnforceIf(o["lit"])
        B[gi] = dict(entry=entry, exit=exit_, tard=tard, X=X, Y=Y, Wv=Wv, Hv=Hv, Bv=Bv)

    gids = [gi for gi, _ in sub]
    for a in range(len(gids)):
        for c in range(a + 1, len(gids)):
            i, k = gids[a], gids[c]
            bi, bk = B[i], B[k]
            sb = m.NewBoolVar(f"sb{i}_{k}")
            m.Add(bi["Bv"] == bk["Bv"]).OnlyEnforceIf(sb)
            m.Add(bi["Bv"] != bk["Bv"]).OnlyEnforceIf(sb.Not())
            ti = m.NewBoolVar(""); tk = m.NewBoolVar(""); L = m.NewBoolVar("")
            R = m.NewBoolVar(""); Dn = m.NewBoolVar(""); Up = m.NewBoolVar("")
            m.Add(bi["exit"] <= bk["entry"]).OnlyEnforceIf(ti)
            m.Add(bk["exit"] <= bi["entry"]).OnlyEnforceIf(tk)
            m.Add(bi["X"] + bi["Wv"] <= bk["X"]).OnlyEnforceIf(L)
            m.Add(bk["X"] + bk["Wv"] <= bi["X"]).OnlyEnforceIf(R)
            m.Add(bi["Y"] + bi["Hv"] <= bk["Y"]).OnlyEnforceIf(Dn)
            m.Add(bk["Y"] + bk["Hv"] <= bi["Y"]).OnlyEnforceIf(Up)
            m.AddBoolOr([ti, tk, L, R, Dn, Up]).OnlyEnforceIf(sb)

    m.Minimize(sum(B[gi]["tard"] for gi in gids))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_workers = workers
    _t0=time.time()
    st = solver.Solve(m)
    _el=time.time()-_t0
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return dict(status=solver.StatusName(st), sched=None,
                    cp_tard=None, proven=False)
    sched = {gi: dict(bay=int(solver.Value(B[gi]["Bv"])),
                      entry=int(solver.Value(B[gi]["entry"]))) for gi in gids}
    return dict(status=solver.StatusName(st), sched=sched,
                cp_tard=solver.ObjectiveValue(), proven=(st == cp_model.OPTIMAL), cp_elapsed=_el)


def crane_repair(prob, ir, sched, honor_entry=True):
    """CP 스케줄(베이+entry)을 래스터 엔진으로 크레인-feasible하게 repair. committed 반환.

    CP entry 오름차순으로 각 블록을 CP-베이에 _best_in_bay로 배치(가장 빠른 크레인-feasible
    자리). honor_entry면 release 대신 CP entry를 하한으로 써 CP 타이밍을 존중. CP에 없는
    블록(congest_n 모드)은 마지막에 EDD로 둘러 배치.
    """
    blocks = prob["blocks"]
    nb = len(prob["bays"])
    committed = [[] for _ in range(nb)]
    bay_loads = [0.0] * nb
    # CP 스케줄 있는 블록: entry 오름차순
    order = sorted(sched.keys(), key=lambda gi: sched[gi]["entry"])
    rest = [i for i in range(len(blocks)) if i not in sched]
    rest.sort(key=lambda i: (blocks[i]["due_date"], blocks[i]["processing_time"]))
    placed = 0
    for gi in order + rest:
        blk = blocks[gi]
        proc = int(blk["processing_time"])
        bay = sched[gi]["bay"] if gi in sched else None
        lo = int(blk["release_time"])
        if gi in sched and honor_entry:
            lo = max(lo, sched[gi]["entry"])
        if bay is not None:
            res = _best_in_bay(ir, bay, committed[bay], gi, lo, proc, "scan")
            target_bays = [bay] if res is not None else list(range(nb))
        else:
            target_bays = list(range(nb))
        best = None  # (entry, bay, res)
        for b in target_bays:
            r = _best_in_bay(ir, b, committed[b], gi, lo, proc, "scan")
            if r is not None and (best is None or r[0] < best[0]):
                best = (r[0], b, r)
        if best is None:
            # 어떤 베이도 안 되면 release 하한으로 재시도(honor_entry 완화)
            for b in (target_bays if bay is None else [bay] + list(range(nb))):
                r = _best_in_bay(ir, b, committed[b], gi, int(blk["release_time"]), proc, "scan")
                if r is not None and (best is None or r[0] < best[0]):
                    best = (r[0], b, r)
        if best is None:
            continue  # 배치 실패(드묾) -- probe라 skip
        entry, b, (e, px, py, orient, _ty) = best
        rel = _rel_bbox(ir, gi, orient)
        committed[b].append(dict(bay=b, bid=gi, orient=orient, px=px, py=py,
                                 entry=e, exit=e + proc, masks=ir.masks(gi, orient),
                                 wbb=(px + rel[0], py + rel[1], px + rel[2], py + rel[3])))
        bay_loads[b] += blk["workload"]
        placed += 1
    return committed, bay_loads, placed


def obj1_of(committed, blocks):
    return sum(max(0, r["exit"] - blocks[r["bid"]]["due_date"]) for bay in committed for r in bay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inst")
    ap.add_argument("-t", "--timelimit", type=float, default=120.0)
    ap.add_argument("-w", "--workers", type=int, default=8)
    ap.add_argument("-c", "--congest", type=int, default=None, help="혼잡 코어 N개만 CP")
    args = ap.parse_args()
    prob = json.load(open(os.path.join(os.path.dirname(__file__), "..", "train", f"{args.inst}.json")))
    prob["name"] = args.inst
    blocks = prob["blocks"]
    w = prob.get("weights", {}); w1, w2, w3 = w.get("w1", 1.0), w.get("w2", 1.0), w.get("w3", 1.0)
    ir = InstanceRaster(prob)

    # 기준선: 우리 construct(edd/scan) obj1
    t = time.time()
    c0, l0, bw0 = construct(prob, time.time(), 300.0, ir=ir, order="edd", cand="scan", return_state=True)
    base_obj1 = obj1_of(c0, blocks)
    print(f"[base] our construct(edd/scan) obj1={base_obj1} elapsed={time.time()-t:.1f}s  (post-ALNS ref=5129 for prob_38)")

    # relax: bbox-CP 전역 스케줄
    print(f"[relax] bbox-CP solve (t={args.timelimit}s, congest={args.congest}) ...")
    r = solve_schedule(prob, args.timelimit, args.workers, congest_n=args.congest)
    if r is None or r["sched"] is None:
        print(f"  CP no solution (status={r['status'] if r else 'NONE'}) -- congest 줄여 재시도 권장")
        return
    print(f"  CP status={r['status']} proven={r['proven']} cp_tard(크레인無 낙관)={r['cp_tard']:.0f} "
          f"n_sched={len(r['sched'])} cp_elapsed={r.get('cp_elapsed',0):.1f}s")

    # repair: 크레인-feasible로
    for honor in (True, False):
        ir2 = InstanceRaster(prob)
        comm, loads, placed = crane_repair(prob, ir2, r["sched"], honor_entry=honor)
        rep_obj1 = obj1_of(comm, blocks)
        from constructor import operations_from_committed
        res = check_feasibility(prob, operations_from_committed(comm))
        tag = "honor_entry" if honor else "release_only"
        print(f"[repair:{tag}] placed={placed}/{len(blocks)} feasible={res['feasible']} "
              f"obj1={rep_obj1}  vs base {base_obj1} / ref 5129 -> "
              f"{'★깸' if rep_obj1 < base_obj1 else '못깸'}")


if __name__ == "__main__":
    main()
