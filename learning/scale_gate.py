"""B6 합성 스케일·엣지 강건성 게이트 (CLAUDE.md §6 과적합 금지의 상시 검증).

train은 100~300블록·2~5베이가 최대다. private는 "비슷한 난이도"라지만 같지 않으므로,
train 범위를 넘긴 합성 인스턴스에서 −1(infeasible·시간초과·크래시)이 나는지 선제로 본다.
이 게이트가 v1.0.2의 floor 스케일 −1(900블록 15s)을 처음 잡았다 -- 다시 회귀하지 않게 박는다.

  python learning/scale_gate.py            # 기본: prob_20 복제 2~6× + 엣지, 10초
  python learning/scale_gate.py -t 5       # 제한시간 바꿔서

판정 지표는 평균 obj가 아니라 *반환시각 < timelimit*·*feasible*·*무크래시*다(feasibility-first).
oversized-block(베이보다 큰 블록)은 본질적으로 해가 없어 infeasible이 정답이므로 -1로 세지 않는다.
"""
import argparse
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from myalgorithm import algorithm           # noqa: E402
from utils import check_feasibility          # noqa: E402

TRAIN = os.path.join(os.path.dirname(__file__), "..", "train")


def _dup_blocks(prob, factor):
    p = copy.deepcopy(prob)
    p["blocks"] = [copy.deepcopy(b) for _ in range(factor) for b in prob["blocks"]]
    return p


def _dup_bays(prob, nbays):
    p = copy.deepcopy(prob)
    base_bays = prob["bays"]
    p["bays"] = [copy.deepcopy(base_bays[i % len(base_bays)]) for i in range(nbays)]
    import random
    rng = random.Random(0)
    for b in p["blocks"]:
        if "bay_preferences" in b:
            b["bay_preferences"] = [float(rng.randint(0, 100)) for _ in range(nbays)]
    return p


def _cases(base):
    """(name, prob, expect_feasible). expect_feasible=False는 본질 infeasible(정답이 -1)."""
    cases = []
    for f in (2, 3, 4, 6):
        cases.append((f"blocks_x{f}", _dup_blocks(base, f), True))
    cases.append(("bays_10", _dup_bays(base, 10), True))
    # 엣지
    p = copy.deepcopy(base); p["blocks"] = p["blocks"][:1]
    cases.append(("blocks_1", p, True))
    p = copy.deepcopy(base); p["blocks"] = []
    cases.append(("blocks_0", p, True))
    p = copy.deepcopy(base)
    for b in p["blocks"]:
        b["due_date"] = 0
    cases.append(("due_date_all_0", p, True))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-t", "--timelimit", type=float, default=10.0)
    ap.add_argument("-b", "--base", default="prob_20")  # 가장 넓은 베이
    args = ap.parse_args()

    base = json.load(open(os.path.join(TRAIN, f"{args.base}.json")))
    tl = args.timelimit
    print(f"scale gate: base={args.base} timelimit={tl}s")
    print(f"{'case':18} {'nblk':>5} {'feasible':>9} {'elapsed':>9} {'verdict':>8}")
    print("-" * 56)
    failures = []
    for name, prob, expect in _cases(base):
        prob = dict(prob); prob["name"] = name
        nblk = len(prob["blocks"])
        t = time.time()
        try:
            sol = algorithm(prob, tl)
            dt = time.time() - t
            res = check_feasibility(prob, sol)
            feas = res["feasible"]
        except Exception as e:                       # 크래시 = 게이트 실패
            dt = time.time() - t
            feas = False
            print(f"{name:18} {nblk:>5} {'CRASH':>9} {dt:>8.2f}s   FAIL ({e!r})")
            failures.append(name)
            continue
        overtime = dt > tl
        # 판정: 시간 내 반환 + (기대 feasible이면 feasible)
        ok = (not overtime) and (feas or not expect)
        verdict = "OK" if ok else "FAIL"
        if not ok:
            failures.append(name)
        note = "" if expect else " (infeasible 정답)"
        print(f"{name:18} {nblk:>5} {str(feas):>9} {dt:>8.2f}s {verdict:>8}{note}")
    print("-" * 56)
    if failures:
        print(f"★ 게이트 실패: {failures}")
        sys.exit(1)
    print("★ 게이트 통과: 모든 합성 스케일·엣지에서 -1 0건, 시간 초과 0건")


if __name__ == "__main__":
    main()
