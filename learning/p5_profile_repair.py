"""#3 -- 큰 인스턴스 repair 병목 프로파일.

scan-edd 구성기로 큰 인스턴스의 committed 상태를 만든 뒤 ALNS를 고정 벽시계로 돌려
cProfile로 cumulative time 상위 함수를 본다. 추측 대신 핫스팟을 먼저 측정한다.

사용: python learning/p5_profile_repair.py prob_38 20
"""
import cProfile
import io
import pstats
import sys
import os
import time

sys.path.insert(0, os.environ.get(
    "P5_SRC", os.path.join(os.path.dirname(__file__), "..", "src")))
import json
from raster_engine import InstanceRaster
from constructor import construct, solution_obj
from alns import alns
import random


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "prob_38"
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    prob = json.load(open(f"train/{inst}.json"))
    w = prob.get("weights", {})
    w1, w2, w3 = w.get("w1", 1.0), w.get("w2", 1.0), w.get("w3", 1.0)
    ir = InstanceRaster(prob)

    # scan-edd 베이스(실 알고리즘이 ALNS에 주는 incumbent와 같은 종류)
    t0 = time.time()
    committed, bay_loads, bw = construct(
        prob, t0, 9999, ir=ir, order="edd", cand="scan", return_state=True)
    base_obj = solution_obj(committed, prob["blocks"], bw, bay_loads, w1, w2, w3)
    print(f"{inst}: construct(scan-edd) {time.time()-t0:.1f}s, base obj={base_obj:.0f}")

    rng = random.Random(20260617)
    stats = {}
    pr = cProfile.Profile()
    pr.enable()
    snap, a_obj, iters = alns(prob, ir, committed, bay_loads, bw,
                              time.time() + secs, rng, cand="blf", stats=stats)
    pr.disable()
    print(f"ALNS {secs}s: iters={iters} obj {base_obj:.0f}->{a_obj:.0f} "
          f"({(base_obj-a_obj)/max(1,base_obj)*100:.1f}%)  "
          f"iters/s={iters/secs:.1f}")

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(25)
    print(s.getvalue())
    # tottime 기준도 (자체 시간 큰 함수 = 진짜 핫스팟)
    s2 = io.StringIO()
    pstats.Stats(pr, stream=s2).sort_stats("tottime").print_stats(15)
    print("=== by tottime ===")
    print(s2.getvalue())


if __name__ == "__main__":
    main()
