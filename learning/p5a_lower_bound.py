"""P5a -- obj1(지각)의 면적완화 cumulative 하한.

천장 측정용 오프라인 분석. 제출 알고리즘을 건드리지 않는다.

하한의 논리
-----------
진짜 제약은 각 bay-layer에서 블록 footprint가 겹치지 않고 크레인(j>=k)이 통하는 것.
이를 한 차원으로 완화한다 -- "어느 시각에도 존재하는 블록들의 바닥(layer 0) footprint
면적 합은 전 베이 바닥면적 C 를 넘을 수 없다." 블록은 전부 바닥에 닿고(layer 0), 같은
바닥 셀을 둘이 못 쓰므로 이는 진짜 배치의 *필요조건*이다 -- nesting(오버행 밑 끼우기)을
허용해도 layer 0 footprint끼리는 안 겹친다. 따라서 이 면적완화만 건 cumulative 스케줄의
최소 지각은 진짜 obj1 의 유효한 하한이다.

  demand_i = floor(layer-0 면적)      (내림 -> demand <= 진짜 면적 -> 완화 유효)
  capacity = C = sum_b W_b * H_b      (정수, 전 베이 바닥면적 합 -- 베이 통합 완화)
  entry_i >= release_i,  exit_i = entry_i + p_i,  tardiness_i = max(0, exit_i - due_i)
  min sum tardiness_i  s.t. AddCumulative(intervals, demands, capacity)

베이를 하나로 통합한 건 의도적 완화다(블록이 어느 베이 면적이든 써도 됨 -> 더 느슨 ->
유효한 하한). 베이별 할당까지 묶으면 더 빡빡하지만 할당을 알아야 해 어렵다.

검증 장치: obj1=0 인 인스턴스에서 이 하한은 반드시 0 이어야 한다(우리 해가 0 을 달성 ->
진짜 opt=0 -> 유효 하한 <= 0). 양수가 나오면 demand 과대계상 버그다.
"""
import csv
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from utils import _poly_from_verts, _resolve_layers  # noqa: E402
from ortools.sat.python import cp_model  # noqa: E402


def _fits_bays(blk, bays):
    """블록이 (어떤 orientation으로든) bbox로 들어가는 베이 인덱스 목록."""
    out = []
    for bi, bay in enumerate(bays):
        W, H = bay["width"], bay["height"]
        for o in blk["shape"]:
            verts = [v for L in _resolve_layers(o["layers"]) for v in L]
            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]
            if (max(xs) - min(xs) <= W) and (max(ys) - min(ys) <= H):
                out.append(bi)
                break
    return out or list(range(len(bays)))  # 어디에도 안 맞으면(이론상無) 전 베이 허용


def instance_data(path):
    d = json.load(open(path))
    bays, blocks = d["bays"], d["blocks"]
    caps = [b["width"] * b["height"] for b in bays]
    C = sum(caps)
    jobs = []
    for blk in blocks:
        layers = _resolve_layers(blk["shape"][0]["layers"])  # 면적은 회전 불변 -> orient 0
        a0 = _poly_from_verts(layers[0]).area
        jobs.append(dict(
            r=int(blk["release_time"]),
            p=int(blk["processing_time"]),
            due=int(blk["due_date"]),
            demand=int(a0),  # floor: demand <= 진짜 면적
            bays=_fits_bays(blk, bays),
        ))
    return C, caps, jobs


def _horizon(jobs):
    return max(max(j["r"] for j in jobs), max(j["due"] for j in jobs)) + sum(j["p"] for j in jobs)


def _solve(m, total, our_obj1, time_limit, workers):
    # 유효 컷: 진짜 해가 our_obj1 을 달성 -> 완화 opt <= our_obj1. 수렴 가속용.
    if our_obj1 is not None and our_obj1 >= 0:
        m.Add(total <= int(our_obj1))
    m.Minimize(total)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_workers = workers
    t0 = time.time()
    status = solver.Solve(m)
    elapsed = time.time() - t0
    best = (solver.ObjectiveValue()
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None)
    return dict(
        status=solver.StatusName(status),
        lb=max(0.0, solver.BestObjectiveBound()),  # 유효 하한 (증명 안 돼도 valid)
        relax_opt=best,
        proven=(status == cp_model.OPTIMAL),
        elapsed=elapsed,
    )


def lower_bound(C, caps, jobs, our_obj1, time_limit, workers=8):
    """베이 통합 면적완화: 자원 1개, 용량 C=sum caps. 가장 느슨한 유효 하한."""
    m = cp_model.CpModel()
    H = _horizon(jobs)
    intervals, tards = [], []
    for i, j in enumerate(jobs):
        entry = m.NewIntVar(j["r"], H, f"e{i}")
        intervals.append(m.NewFixedSizeIntervalVar(entry, j["p"], f"iv{i}"))
        t = m.NewIntVar(0, H, f"t{i}")  # tardiness=max(0,entry+p-due); 목적이 내리눌러 하한이면 충분
        m.Add(t >= entry + j["p"] - j["due"])
        tards.append(t)
    m.AddCumulative(intervals, [j["demand"] for j in jobs], C)
    total = m.NewIntVar(0, sum(j["p"] + H for j in jobs), "total")
    m.Add(total == sum(tards))
    return _solve(m, total, our_obj1, time_limit, workers)


def lower_bound_perbay(C, caps, jobs, our_obj1, time_limit, workers=8):
    """베이별 면적완화 + 할당: 블록이 정확히 한 베이를 골라 그 베이 용량(W*H) cumulative.
    베이 경계를 존중하고 분할을 금해 통합 완화보다 빡빡한 유효 하한."""
    m = cp_model.CpModel()
    H = _horizon(jobs)
    entries, tards = [], []
    per_bay = {b: [] for b in range(len(caps))}      # bay -> (interval, demand)
    for i, j in enumerate(jobs):
        entry = m.NewIntVar(j["r"], H, f"e{i}")
        entries.append(entry)
        t = m.NewIntVar(0, H, f"t{i}")
        m.Add(t >= entry + j["p"] - j["due"])
        tards.append(t)
        allowed = j["bays"]
        pres = []
        for b in allowed:
            lit = m.NewBoolVar(f"x{i}_{b}")
            iv = m.NewOptionalFixedSizeIntervalVar(entry, j["p"], lit, f"iv{i}_{b}")
            per_bay[b].append((iv, j["demand"]))
            pres.append(lit)
        m.AddExactlyOne(pres)  # 정확히 한 베이
    for b, items in per_bay.items():
        if items:
            m.AddCumulative([iv for iv, _ in items], [d for _, d in items], caps[b])
    total = m.NewIntVar(0, sum(j["p"] + H for j in jobs), "total")
    m.Add(total == sum(tards))
    return _solve(m, total, our_obj1, time_limit, workers)


def no_wait_lb(jobs):
    """무대기 하한: 경합 무시, 각 블록 release+proc 즉시. 메모리상 40개 전부 0 추정."""
    return sum(max(0, j["r"] + j["p"] - j["due"]) for j in jobs)


def main():
    our = {}
    with open("results/p4a_60s/summary.csv") as f:
        for row in csv.DictReader(f):
            our[row["instance"]] = float(row["obj1"])

    only = sys.argv[1:] if len(sys.argv) > 1 else None
    tl = float(os.environ.get("P5A_TL", "30.0"))
    mode = os.environ.get("P5A_MODE", "aggregate")
    solve_fn = lower_bound_perbay if mode == "perbay" else lower_bound
    paths = sorted(glob.glob("train/prob_*.json"),
                   key=lambda p: int(p.split("_")[1].split(".")[0]))
    print(f"mode={mode} tl={tl}")
    print(f"{'inst':10} {'nblk':>4} {'nowait':>7} {'our_obj1':>9} {'cumLB':>8} "
          f"{'relaxOpt':>9} {'gap%':>6} {'proven':>6} {'st':>10} {'sec':>5}")
    out = []
    for p in paths:
        name = os.path.basename(p).replace(".json", "")
        if only and name not in only:
            continue
        C, caps, jobs = instance_data(p)
        nw = no_wait_lb(jobs)
        o1 = our.get(name)
        res = solve_fn(C, caps, jobs, o1, tl)
        lb = res["lb"]
        gap = (o1 - lb) / o1 * 100 if o1 and o1 > 0 else 0.0
        print(f"{name:10} {len(jobs):>4} {nw:>7} "
              f"{(o1 if o1 is not None else -1):>9.0f} {lb:>8.0f} "
              f"{(res['relax_opt'] if res['relax_opt'] is not None else -1):>9.0f} "
              f"{gap:>6.1f} {str(res['proven']):>6} {res['status']:>10} {res['elapsed']:>5.1f}")
        out.append(dict(inst=name, nowait=nw, our_obj1=o1, cumLB=lb,
                        relax_opt=res["relax_opt"], proven=res["proven"],
                        status=res["status"]))
    # 검증: obj1=0 인스턴스의 cumLB 가 0 이 아니면 버그
    bad = [r for r in out if (r["our_obj1"] == 0) and r["cumLB"] > 1e-6]
    if bad:
        print("\n!!! VALIDITY VIOLATION (cumLB>0 while our obj1=0):",
              [r["inst"] for r in bad])
    else:
        print("\nvalidity OK: 모든 obj1=0 인스턴스에서 cumLB=0")
    return out


if __name__ == "__main__":
    main()
