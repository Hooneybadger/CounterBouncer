import sys, os, time, json, multiprocessing as mp
sys.path.insert(0, "src")

def run_algo(inst, tl, q):
    from myalgorithm import algorithm
    from utils import check_feasibility
    prob = json.load(open(f"train/{inst}.json"))
    t0 = time.time(); sol = algorithm(prob, tl); el = time.time() - t0
    res = check_feasibility(prob, sol)
    q.put((el, bool(res.get("feasible")), res.get("objective")))

def main():
    tl = float(sys.argv[1]); insts = sys.argv[2:]
    label = f"NW={os.environ.get('OGC_NW','4')} CPW={os.environ.get('OGC_CP_WORKERS','nw')}"
    print(f"=== {label}, tl={tl}s (1개씩=서버조건) ===")
    for inst in insts:
        q = mp.Queue()
        p = mp.Process(target=run_algo, args=(inst, tl, q), daemon=True)
        p.start(); p.join(timeout=tl + 60)
        if p.is_alive(): p.terminate(); print(f"  {inst}: HUNG"); continue
        try:
            el, feas, obj = q.get(timeout=3)
            print(f"  {inst}: obj={obj:.0f} ({el:.1f}s) feas={feas}")
        except Exception as e:
            print(f"  {inst}: 결과없음 {e!r}")

if __name__ == "__main__":
    main()
