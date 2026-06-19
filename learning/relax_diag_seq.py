import sys, os, time, json, multiprocessing as mp
sys.path.insert(0, "src")

def run_algo(inst, tl, no_relax, q):
    if no_relax: os.environ["OGC_NO_RELAX"] = "1"
    else: os.environ.pop("OGC_NO_RELAX", None)
    if "OGC_NW" in sys.argv: pass
    from myalgorithm import algorithm
    from utils import check_feasibility
    prob = json.load(open(f"train/{inst}.json"))
    t0 = time.time(); sol = algorithm(prob, tl); el = time.time() - t0
    res = check_feasibility(prob, sol)
    q.put((el, bool(res.get("feasible")), res.get("objective")))

def one(inst, tl, no_relax):
    # ★한 번에 한 인스턴스만 (서버 조건). 단일 daemon 프로세스 = 4자식만.
    q = mp.Queue()
    p = mp.Process(target=run_algo, args=(inst, tl, no_relax, q), daemon=True)
    p.start(); p.join(timeout=tl + 60)
    if p.is_alive(): p.terminate(); return None
    try: return q.get(timeout=3)
    except Exception: return None

def main():
    tl = float(sys.argv[1]); insts = sys.argv[2:]
    print(f"=== 순차(1개씩) tl={tl}s, relax ON vs OFF ===")
    for inst in insts:
        on = one(inst, tl, False)
        off = one(inst, tl, True)
        if on and off:
            d = (on[2] - off[2]) / off[2] * 100 if off[2] else 0
            tag = "relax helps" if d < -1 else ("relax HURTS" if d > 1 else "동일")
            print(f"  {inst}: ON={on[2]:.0f}({on[0]:.1f}s) OFF={off[2]:.0f}({off[0]:.1f}s) → {d:+.1f}% [{tag}]")
        else:
            print(f"  {inst}: ON={on} OFF={off}")

if __name__ == "__main__":
    main()
