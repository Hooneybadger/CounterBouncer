"""scan 구성(feasible_positions) 병목 프로파일. P5_SRC=<algdir> python ... <inst>"""
import cProfile, io, pstats, sys, os, time, json
sys.path.insert(0, os.environ.get("P5_SRC", os.path.join(os.path.dirname(__file__), "..", "src")))
from raster_engine import InstanceRaster
from constructor import construct, solution_obj

inst = sys.argv[1] if len(sys.argv) > 1 else "prob_38"
prob = json.load(open(f"train/{inst}.json"))
ir = InstanceRaster(prob)
pr = cProfile.Profile()
t0 = time.time()
pr.enable()
committed, bl, bw = construct(prob, time.time(), 1e9, ir=ir, order="edd", cand="scan", return_state=True)
pr.disable()
print(f"{inst}: construct(scan-edd) {time.time()-t0:.1f}s")
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(12)
print(s.getvalue())
