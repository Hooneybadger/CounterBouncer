import sys, os, time, json, multiprocessing as mp
sys.path.insert(0, "src")

def run_algo(inst_path, tl, q):
    from myalgorithm import algorithm
    from utils import check_feasibility
    prob = json.load(open(inst_path))
    t0 = time.time(); sol = algorithm(prob, tl); el = time.time() - t0
    res = check_feasibility(prob, sol)
    q.put((os.path.basename(inst_path), len(prob["blocks"]), el, bool(res.get("feasible")), res.get("objective")))

def main():
    tl = float(sys.argv[1]); insts = [f"train/{a}.json" for a in sys.argv[2:]]
    print(f"=== DAEMON 스폿 tl={tl}s: {[os.path.basename(i) for i in insts]} ===")
    procs = []
    for ip in insts:
        q = mp.Queue()
        p = mp.Process(target=run_algo, args=(ip, tl, q), daemon=True)  # ★daemon=서버조건
        p.start(); procs.append((p, q, ip))
    for p, q, ip in procs:
        p.join(timeout=tl + 60)
        if p.is_alive():
            p.terminate(); print(f"  {os.path.basename(ip)}: ★HUNG"); continue
        try:
            nm, nb, el, feas, obj = q.get(timeout=3)
            ov = "★OVERTIME" if el > tl else "ok"
            print(f"  {nm} ({nb}블록): el={el:.2f}s/{tl:.0f} feas={feas} {ov} obj={obj}")
        except Exception as e:
            print(f"  {os.path.basename(ip)}: ★결과없음 {e!r}")

if __name__ == "__main__":
    main()
