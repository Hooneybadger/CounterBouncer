#!/usr/bin/env python
"""p4c_seedvar.py -- ALNS 시드 다양성의 best-of-N 헤드룸을 잰다.

4코어 포트폴리오(P4c)를 짓기 전에 전제를 측정한다. batch_runner를 --repeat N으로 돌리고
시드를 OGC_RUN_INDEX로 흔들면, 한 인스턴스의 N개 독립 ALNS 실행이 생긴다. rep 0(시드
20260617 = 현재 production)을 단일로, N개 중 최소를 best-of-N으로 보고, 그 차이가 곧
"4코어를 best-of로 쓰면 얻는 obj"다.

사용: python learning/p4c_seedvar.py results/<repeatN-run>
"""
import csv
import sys
import pathlib
from collections import defaultdict


def main():
    d = pathlib.Path(sys.argv[1])
    by_inst = defaultdict(dict)   # inst -> {rep: (obj, ok)}
    with open(d / "summary.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ok = r["status"] == "ok"
            obj = float(r["objective"]) if ok and r["objective"] != "" else None
            by_inst[r["instance"]][int(r["rep"])] = (obj, ok)

    insts = sorted(by_inst, key=lambda s: int("".join(c for c in s if c.isdigit())))
    print(f"{'inst':<9}{'single(r0)':>14}{'best-of-N':>14}{'gain':>10}{'gain%':>8}"
          f"{'spread%':>9}{'N_ok':>6}")
    print("-" * 70)
    n_better = 0
    tot_single = tot_best = 0.0
    sum_gainpct = 0.0
    for i in insts:
        reps = by_inst[i]
        single = reps.get(0, (None, False))[0]
        objs = [o for (o, ok) in reps.values() if ok and o is not None]
        if not objs or single is None:
            print(f"{i:<9}  (rep0 invalid or no feasible rep)")
            continue
        best = min(objs)
        gain = single - best
        gainpct = gain / single * 100 if single else 0.0
        spread = (max(objs) - min(objs)) / min(objs) * 100 if min(objs) else 0.0
        if best < single - 1e-9:
            n_better += 1
        tot_single += single
        tot_best += best
        sum_gainpct += gainpct
        print(f"{i:<9}{single:>14,.0f}{best:>14,.0f}{gain:>10,.0f}"
              f"{gainpct:>7.2f}%{spread:>8.1f}%{len(objs):>6}")
    print("-" * 70)
    n = len([i for i in insts if by_inst[i].get(0, (None, False))[0] is not None])
    print(f"best-of-N이 단일을 이긴 인스턴스: {n_better}/{n}")
    print(f"평균 gain%: {sum_gainpct / max(1, n):.2f}%   "
          f"합계 obj: single {tot_single:,.0f} -> best {tot_best:,.0f} "
          f"({(tot_best/tot_single - 1)*100 if tot_single else 0:+.2f}%)")
    print("spread% = 같은 인스턴스 N개 시드의 (max-min)/min, ALNS 분산 크기")


if __name__ == "__main__":
    main()
