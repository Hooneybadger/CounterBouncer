"""P3 infeasible 진단:
  (1) floor(_guaranteed_solution)를 40개 전부에 대해 계산 → check_feasibility로 검증.
      거의 실행 안 되는 fallback이라 미검증 — 정말 항상 feasible한가?
  (2) check_feasibility 비용 측정 — 마지막 검증이 timelimit을 넘길 위험.
"""
import sys, os, time, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils import check_feasibility
from myalgorithm import _guaranteed_solution

insts = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "train", "prob_*.json")),
               key=lambda p: int(os.path.basename(p).split("_")[1].split(".")[0]))

print(f"{'instance':12} {'nblk':>5} {'floor_ms':>9} {'check_s':>9} {'feasible':>9} {'stage':>5} {'obj':>14}")
print("-" * 75)
any_infeasible = False
max_check = 0.0
for p in insts:
    name = os.path.basename(p).replace(".json", "")
    prob = json.load(open(p))
    prob["name"] = name
    nblk = len(prob["blocks"])

    t = time.time()
    floor = _guaranteed_solution(prob)
    floor_ms = (time.time() - t) * 1000

    t = time.time()
    res = check_feasibility(prob, floor)
    check_s = time.time() - t
    max_check = max(max_check, check_s)

    feas = res["feasible"]
    if not feas:
        any_infeasible = True
    obj = res["objective"] if feas else None
    objs = f"{obj:,.0f}" if obj is not None else "INFEASIBLE"
    print(f"{name:12} {nblk:>5} {floor_ms:>9.1f} {check_s:>9.3f} {str(feas):>9} {res['stage']:>5} {objs:>14}")
    if not feas:
        for v in res["violations"][:3]:
            print(f"             !! {v}")

print("-" * 75)
print(f"floor 전부 feasible: {not any_infeasible}")
print(f"check_feasibility 최대 비용: {max_check:.3f}s")
print()
print("해석: max_check가 timelimit의 큰 비율이면, 마지막 검증이 overrun을 유발.")
print("  10s 제한 기준 위험비율:", f"{max_check/10*100:.1f}%")
