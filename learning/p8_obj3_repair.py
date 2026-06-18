"""obj3 할당-repair end-to-end 검증 (v1.2.0 프런티어).

p7의 gurobi obj3-최소 할당({gid:bay})을 기존 래스터 repair(_repair_from_schedule)로 feasible
실현 → 실제 obj1/obj2/obj3/feasibility 측정. relax-repair와 같은 패턴(MIP 할당 → 래스터 repair).
질문: 느슨한 용량의 낙관적 obj3 LB가 실제로 feasible하게 얼마나 실현되나(현재값 대비).
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
from raster_engine import InstanceRaster
from relax_repair import _repair_from_schedule
from constructor import operations_from_committed
from utils import check_feasibility
from p7_obj2_balance import solve, load

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("insts", nargs="+")
    ap.add_argument("--w2", type=float, default=0.0); ap.add_argument("--w3", type=float, default=1.0)
    ap.add_argument("-t", type=float, default=20.0); ap.add_argument("--slack", type=float, default=1.0)
    a = ap.parse_args()
    for inst in a.insts:
        prob = load(inst)
        r = solve(prob, a.w2, a.w3, a.t, cap_slack=a.slack)
        if r is None: print(f"{inst}: no assignment"); continue
        ir = InstanceRaster(prob)
        # 베이 할당만 honor (entry=release, honor_entry=False → 배치 순서로 스케줄)
        sched = {gid: (bay, int(prob["blocks"][gid]["release_time"])) for gid, bay in r["assign"].items()}
        committed = _repair_from_schedule(prob, ir, sched, honor_entry=False)
        res = check_feasibility(prob, operations_from_committed(committed))
        if not res["feasible"]:
            print(f"{inst}: ★INFEASIBLE  viol={res.get('violations')}")
            continue
        # 실제 할당이 gurobi 의도대로 됐는지(베이 일치율)
        placed = {c["bid"]: c["bay"] for bay in committed for c in bay}
        match = sum(1 for g, b in r["assign"].items() if placed.get(g) == b)
        print(f"{inst}: feasible obj1={res['obj1']:.0f} obj2={res['obj2']:.0f} obj3={res['obj3']:.0f}  "
              f"(gurobi LB obj3={r['obj3']} proven={r['proven']}) 베이일치={match}/{len(r['assign'])}")

if __name__ == "__main__":
    main()
