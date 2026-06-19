"""obj2(균형) 헤드룸 probe — gurobi 할당 MIP로 균형-최적 obj2를 구해 현재값과 비교.

obj2 = floor(max_{j1!=j2} |u_j1*load_j1 - u_j2*load_j2|), load_j=베이 j 블록 workload 합, u_j=평균면적/베이면적.
순수 할당 함수(스케줄·위치 무관) → min-max 할당 MIP = gurobi가 정확히 맞음. 공간 feasibility 무시 = obj2 LB.
gap(현재-LB) 크면 obj2가 큰 v1.2.0 레버. obj3도 함께(joint w2*obj2+w3*obj3) 옵션.
"""
import argparse, json, math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from relax_repair import _bbox_orients  # 방향별 (w,h)

def load(inst):
    return json.load(open(os.path.join(os.path.dirname(__file__), "..", "train", f"{inst}.json")))

def solve(prob, w2=0.0, w3=1.0, tcap=20.0, threads=4, cap_slack=1.0):
    """gurobi 할당 MIP로 w2*obj2 + w3*obj3 최소화. 용량 제약(util<=cap_slack)으로 LB가 너무 낙관 안 되게."""
    import gurobipy as gp
    from gurobipy import GRB
    blocks = prob["blocks"]; bays = prob["bays"]; nb = len(bays); n = len(blocks)
    areas = [b["width"] * b["height"] for b in bays]; avg = sum(areas) / nb
    u = [avg / a for a in areas]
    wl = [b["workload"] for b in blocks]
    ors = [_bbox_orients(b) for b in blocks]           # 방향별 (w,h)
    barea = [min(w * h for (w, h) in o) for o in ors]   # 최선 footprint 면적
    proc = [b["processing_time"] for b in blocks]
    H = max(max(b["due_date"] for b in blocks), max(b["release_time"] + b["processing_time"] for b in blocks))
    def fits(i, j):
        W, Hh = bays[j]["width"], bays[j]["height"]
        return any((w <= W and h <= Hh) for (w, h) in ors[i])
    m = gp.Model(); m.setParam("OutputFlag", 0); m.setParam("TimeLimit", float(tcap)); m.setParam("Threads", threads)
    z = {}
    for i in range(n):
        allowed = [j for j in range(nb) if fits(i, j)] or list(range(nb))
        for j in allowed: z[i, j] = m.addVar(vtype=GRB.BINARY)
        m.addConstr(gp.quicksum(z[i, j] for j in allowed) == 1)
    load = [gp.quicksum(wl[i] * z[i, j] for i in range(n) if (i, j) in z) for j in range(nb)]
    # 용량 제약: 베이 j의 (면적*proc) 합 <= 면적*H*cap_slack  (시공간 점유 근사)
    for j in range(nb):
        cap = bays[j]["width"] * bays[j]["height"] * H * cap_slack
        m.addConstr(gp.quicksum(barea[i] * proc[i] * z[i, j] for i in range(n) if (i, j) in z) <= cap)
    M = m.addVar(lb=0)  # obj2 (max 불균형)
    for j1 in range(nb):
        for j2 in range(nb):
            if j1 != j2: m.addConstr(M >= u[j1] * load[j1] - u[j2] * load[j2])
    pref_pen = gp.quicksum(
        (max(blocks[i]["bay_preferences"]) - blocks[i]["bay_preferences"][j]) * z[i, j]
        for (i, j) in z)
    m.setObjective(w2 * M + w3 * pref_pen, GRB.MINIMIZE)
    m.optimize()
    if m.SolCount == 0: return None
    obj2 = math.floor(M.X)
    obj3 = sum((max(blocks[i]["bay_preferences"]) - blocks[i]["bay_preferences"][j]) * round(z[i, j].X) for (i, j) in z)
    assign = {i: j for (i, j) in z if round(z[i, j].X) == 1}
    return dict(obj2=obj2, obj3=int(obj3), status=m.status, proven=m.status == GRB.OPTIMAL, assign=assign)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("insts", nargs="+")
    ap.add_argument("--w2", type=float, default=1.0); ap.add_argument("--w3", type=float, default=0.0)
    ap.add_argument("-t", type=float, default=20.0)
    a = ap.parse_args()
    for inst in a.insts:
        prob = load(inst)
        r = solve(prob, a.w2, a.w3, a.t)
        if r is None: print(f"{inst}: no solution"); continue
        print(f"{inst}: balance-opt obj2={r['obj2']} obj3={r['obj3']} proven={r['proven']} (w2={a.w2} w3={a.w3})")

if __name__ == "__main__":
    main()
