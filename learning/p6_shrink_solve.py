"""P6 -- 축소 인스턴스에 우리 실제 솔버(크레인 포함)를 돌려 achievable 지각을 잰다.

목적: bbox CP-SAT(크레인 무시)는 prob_38 앞 60블록을 지각 0으로 패킹했다. 우리 full
솔버는 같은 블록들에 216 지각을 남긴다. 이 격차가 (a) 크레인 제약(우리는 enforce, bbox는
무시) 때문인지 (b) 우리 *전역 탐색*이 다른 블록과의 경합에 져서인지를 가른다.

여기서는 prob_38 의 release 이른 N개만 떼어 *그것만으로* 우리 algorithm 을 돌린다.
- 우리 솔버는 크레인을 완전히 enforce 한다(_best_in_bay 양방향 j>=k).
- 다른 블록과의 경합이 없으므로, 남는 지각은 *순수히 크레인+우리 배치 한계*다.
N개만의 우리 achievable 지각이:
  ~0 이면  -> 격차는 크레인 아님. full 인스턴스의 지각은 전역 경합/탐색 한계 = 헤드룸 있음.
  크면    -> 크레인이 이 블록집합에 지각을 강제 = bbox 하한이 낙관적, 헤드룸 적음.
"""
import argparse
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from myalgorithm import algorithm  # noqa: E402
from utils import check_feasibility  # noqa: E402


def shrink(prob, n):
    blocks = prob["blocks"]
    order = sorted(range(len(blocks)),
                   key=lambda i: (blocks[i]["release_time"], blocks[i]["due_date"]))
    sel = order[:n]
    p = copy.deepcopy(prob)
    p["blocks"] = [copy.deepcopy(blocks[i]) for i in sel]
    return p, sel


def tardiness(prob, sol):
    blocks = prob["blocks"]
    due = [b["due_date"] for b in blocks]
    ops = sol["operations"] if "operations" in sol else sol["solution"]["operations"]
    exit_ = {}
    for t_str, lst in ops.items():
        for op in lst:
            if op["type"] == "EXIT":
                exit_[op["block_id"]] = int(t_str)
    return sum(max(0, exit_.get(i, 0) - due[i]) for i in range(len(blocks)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inst")
    ap.add_argument("-n", "--nblocks", type=int, default=60)
    ap.add_argument("-t", "--timelimit", type=float, default=60.0)
    args = ap.parse_args()

    prob = json.load(open(os.path.join(os.path.dirname(__file__), "..", "train", f"{args.inst}.json")))
    sub, sel = shrink(prob, args.nblocks)
    sub["name"] = f"{args.inst}_first{args.nblocks}"
    t0 = time.time()
    sol = algorithm(sub, args.timelimit)
    dt = time.time() - t0
    res = check_feasibility(sub, sol)
    tard = tardiness(sub, sol) if res["feasible"] else -1
    print(f"{args.inst} first-{args.nblocks}: feasible={res['feasible']} "
          f"OUR_tardiness={tard} elapsed={dt:.1f}s")
    print(f"  (bbox-CPSAT achievable for same set was ~0 at N<=60)")


if __name__ == "__main__":
    main()
