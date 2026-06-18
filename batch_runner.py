#!/usr/bin/env python
"""
batch_runner.py -- OGC2026 headless batch experiment runner.

The official alg_tester GUI is great for visually debugging a single solution,
but it cannot run experiments.  This tool fills the gaps that matter for the
leaderboard:

  * Runs an algorithm over many instances in parallel, each in an isolated
    subprocess (a crash/hang in one instance never affects the others).
  * ENFORCES the time limit: the solver process is killed at
    timelimit + grace seconds and recorded as "timeout" (= what the server
    does, where exceeding the limit scores -1).  A run that finishes but took
    longer than the time limit is recorded as "overtime" (also -1 on the
    server, even though a solution exists).
  * Mimics the evaluation server: pins each solver to N CPU cores (taskset)
    and caps its memory (RLIMIT_AS), like firejail/cpulimit do server-side.
  * Checks feasibility with the official src/utils.py checker (the same
    code the server uses) in a separate process with its own timeout.
  * Saves everything under results/<run-name>/: summary.csv, per-instance
    solution JSON, per-instance solver logs, and run metadata.
  * `compare` mode: side-by-side objective table for several result dirs,
    plus a leaderboard simulation using the competition scoring rule
    (per instance: -1 if invalid, else R - nb).

Usage examples
--------------
  # Run the src on all training instances, 60s limit, server-like limits
  python batch_runner.py run --alg src --timelimit 60 --name base60

  # Quick smoke test on two instances
  python batch_runner.py run -a src -i train/prob_1.json train/prob_2.json -t 30

  # Compare two (or more) runs: regression report + rank-score simulation
  python batch_runner.py compare results/base60 results/myalg_v2

Statuses in summary.csv
-----------------------
  ok          feasible solution within the time limit
  infeasible  solution returned in time but fails check_feasibility
  overtime    feasible/checked, but wall-clock exceeded the time limit (-1 on server)
  timeout     solver killed at timelimit + grace (-1 on server)
  crash       solver raised an exception or died (-1 on server)
  check_error feasibility checker itself failed/timed out (investigate!)
"""

from __future__ import annotations

import argparse
import csv
import datetime
import glob
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent
UTILS_DIR = ROOT / "src"          # canonical utils.py (identical to alg_tester's)
DEFAULT_INSTANCES = sorted(
    glob.glob(str(ROOT / "train" / "prob_*.json")),
    key=lambda p: int(re.search(r"(\d+)", pathlib.Path(p).stem).group(1)),
)

# Statuses that the evaluation server scores as -1
INVALID_STATUSES = {"infeasible", "overtime", "timeout", "crash", "check_error"}


def _json_fallback(o):
    """Allow numpy ints/floats etc. in solution dicts."""
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


# =============================================================================
# Hidden child entry points (run in subprocesses)
# =============================================================================

def _solve_main(args) -> int:
    """Child process: load myalgorithm.py, run it, write {elapsed, solution}."""
    mem_gb = float(os.environ.get("OGC_MEM_GB", "0"))
    if mem_gb > 0:
        try:
            import resource
            cap = int(mem_gb * 2**30)
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        except Exception as e:
            print(f"[runner] warning: could not set memory limit: {e}")

    alg_dir = pathlib.Path(args.alg_dir).resolve()
    inst_path = pathlib.Path(args.instance).resolve()
    out_path = pathlib.Path(args.out).resolve()
    sys.path.insert(0, str(alg_dir))
    os.chdir(alg_dir)

    import importlib.util
    spec = importlib.util.spec_from_file_location("myalgorithm", alg_dir / "myalgorithm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with open(inst_path, encoding="utf-8") as f:
        prob_info = json.load(f)

    t0 = time.time()
    solution = mod.algorithm(prob_info, float(args.timelimit))
    elapsed = time.time() - t0

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"elapsed": elapsed, "solution": solution}, f, default=_json_fallback)
    return 0


def _check_main(args) -> int:
    """Child process: run the official feasibility checker on a saved solution."""
    sys.path.insert(0, str(UTILS_DIR))
    from utils import check_feasibility  # official checker

    with open(args.instance, encoding="utf-8") as f:
        prob_info = json.load(f)
    with open(args.solution, encoding="utf-8") as f:
        solution = json.load(f)["solution"]

    r = check_feasibility(prob_info, solution)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({
            "feasible": r["feasible"], "stage": r["stage"],
            "objective": r["objective"], "obj1": r["obj1"],
            "obj2": r["obj2"], "obj3": r["obj3"],
            "violations": r["violations"][:10],
        }, f)
    return 0


# =============================================================================
# Parent-side job execution
# =============================================================================

class CoreSlots:
    """Hand out disjoint CPU core ranges to concurrent jobs (server mimicry).

    Job slot k gets cores [k*cores, (k+1)*cores) modulo the machine's CPU
    count, so parallel jobs do not steal each other's 4 cores."""

    def __init__(self, n_slots: int, cores_per_job: int):
        self._lock = threading.Lock()
        self._free = list(range(n_slots))
        self._cores = cores_per_job
        self._ncpu = os.cpu_count() or 1

    def acquire(self) -> tuple[int, list[int]]:
        with self._lock:
            slot = self._free.pop()
        base = (slot * self._cores) % self._ncpu
        cores = [(base + i) % self._ncpu for i in range(self._cores)]
        return slot, sorted(set(cores))

    def release(self, slot: int):
        with self._lock:
            self._free.append(slot)


def run_one(inst_path: str, rep: int, cfg: argparse.Namespace,
            out_dir: pathlib.Path, slots: CoreSlots | None) -> dict:
    """Run solver + checker for one (instance, repetition). Returns a CSV row."""
    inst = pathlib.Path(inst_path).stem
    tag = inst if cfg.repeat == 1 else f"{inst}#r{rep}"
    sol_file = out_dir / "solutions" / f"{tag}.json"
    log_file = out_dir / "logs" / f"{tag}.log"
    chk_file = out_dir / "solutions" / f"{tag}.check.json"

    with open(inst_path, encoding="utf-8") as f:
        prob = json.load(f)
    row = {
        "instance": inst, "rep": rep, "status": "crash",
        "feasible": False, "stage": "", "objective": "", "obj1": "", "obj2": "",
        "obj3": "", "elapsed_sec": "", "timelimit_sec": cfg.timelimit,
        "n_blocks": len(prob.get("blocks", [])), "n_bays": len(prob.get("bays", [])),
        "error": "",
    }

    slot = None
    cores: list[int] = []
    if slots is not None:
        slot, cores = slots.acquire()
    try:
        # ---- Phase 1: solve (hard-killed at timelimit + grace) --------------
        cmd = [sys.executable, "-u", str(pathlib.Path(__file__).resolve()),
               "_solve", "--alg-dir", str(cfg.alg_dir), "--instance", str(inst_path),
               "--timelimit", str(cfg.timelimit), "--out", str(sol_file)]
        if cores and cfg.cores > 0:
            cmd = ["taskset", "-c", ",".join(map(str, cores))] + cmd
        env = dict(os.environ,
                   OGC_MEM_GB=str(cfg.mem),
                   OGC_RUN_INDEX=str(rep))

        t0 = time.time()
        with open(log_file, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
            try:
                rc = proc.wait(timeout=cfg.timelimit + cfg.grace)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                row.update(status="timeout", elapsed_sec=round(time.time() - t0, 2),
                           error=f"killed at timelimit+{cfg.grace}s grace")
                return row

        if rc != 0 or not sol_file.exists():
            row.update(status="crash", elapsed_sec=round(time.time() - t0, 2),
                       error=f"solver exit code {rc}; see logs/{tag}.log")
            return row

        with open(sol_file, encoding="utf-8") as f:
            envelope = json.load(f)
        elapsed = envelope["elapsed"]
        row["elapsed_sec"] = round(elapsed, 2)

        # ---- Phase 2: official feasibility check (own timeout) --------------
        chk_cmd = [sys.executable, str(pathlib.Path(__file__).resolve()),
                   "_check", "--instance", str(inst_path),
                   "--solution", str(sol_file), "--out", str(chk_file)]
        try:
            chk = subprocess.run(chk_cmd, capture_output=True, text=True,
                                 timeout=cfg.check_timeout)
        except subprocess.TimeoutExpired:
            row.update(status="check_error", error="feasibility check timed out")
            return row
        if chk.returncode != 0 or not chk_file.exists():
            row.update(status="check_error",
                       error=(chk.stderr or "checker failed").strip()[-300:])
            return row

        with open(chk_file, encoding="utf-8") as f:
            r = json.load(f)
        row.update(feasible=r["feasible"], stage=r["stage"])
        if r["feasible"]:
            row.update(objective=round(r["objective"], 2), obj1=round(r["obj1"], 2),
                       obj2=round(r["obj2"], 2), obj3=round(r["obj3"], 2))
            # Server measures wall clock: finishing late = crash even if feasible.
            row["status"] = "overtime" if elapsed > cfg.timelimit + 0.5 else "ok"
            if row["status"] == "overtime":
                row["error"] = f"elapsed {elapsed:.1f}s > timelimit {cfg.timelimit}s"
        else:
            row.update(status="infeasible",
                       error="; ".join(r["violations"][:3])[:300])
        return row

    except Exception as e:  # never let one job kill the batch
        row.update(status="crash", error=repr(e)[:300])
        return row
    finally:
        if slots is not None and slot is not None:
            slots.release(slot)


# =============================================================================
# `run` command
# =============================================================================

def cmd_run(cfg: argparse.Namespace) -> int:
    cfg.alg_dir = pathlib.Path(cfg.alg).resolve()
    if not (cfg.alg_dir / "myalgorithm.py").exists():
        print(f"error: {cfg.alg_dir}/myalgorithm.py not found", file=sys.stderr)
        return 2

    instances = cfg.instances or DEFAULT_INSTANCES
    if not instances:
        print("error: no instances found", file=sys.stderr)
        return 2

    name = cfg.name or f"{cfg.alg_dir.name}_{datetime.datetime.now():%Y%m%d-%H%M%S}"
    out_dir = pathlib.Path(cfg.out) / name
    (out_dir / "solutions").mkdir(parents=True, exist_ok=True)
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)

    use_taskset = cfg.cores > 0 and os.name == "posix" and \
        subprocess.run(["which", "taskset"], capture_output=True).returncode == 0
    ncpu = os.cpu_count() or 1
    if cfg.jobs <= 0:
        cfg.jobs = max(1, ncpu // max(1, cfg.cores)) if cfg.cores > 0 else 4
    slots = CoreSlots(cfg.jobs, cfg.cores) if use_taskset else None

    meta = {
        "name": name, "alg_dir": str(cfg.alg_dir), "timelimit": cfg.timelimit,
        "grace": cfg.grace, "cores": cfg.cores if use_taskset else "unlimited",
        "mem_gb": cfg.mem, "jobs": cfg.jobs, "repeat": cfg.repeat,
        "instances": [str(p) for p in instances],
        "started": datetime.datetime.now().isoformat(timespec="seconds"),
        "host_cpus": ncpu,
    }
    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"run    : {name}")
    print(f"alg    : {cfg.alg_dir}")
    print(f"limits : timelimit={cfg.timelimit}s (+{cfg.grace}s grace)  "
          f"cores={'%d (taskset)' % cfg.cores if use_taskset else 'unlimited'}  "
          f"mem={cfg.mem}GB  jobs={cfg.jobs}")
    print(f"out    : {out_dir}")
    print("-" * 78)

    jobs = [(p, r) for p in instances for r in range(cfg.repeat)]
    rows: list[dict] = []
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=cfg.jobs) as ex:
        futs = {ex.submit(run_one, p, r, cfg, out_dir, slots): (p, r) for p, r in jobs}
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            obj = f"obj={row['objective']}" if row["objective"] != "" else row["error"][:48]
            print(f"  [{len(rows):2d}/{len(jobs)}] {row['instance']:<10s} "
                  f"{row['status']:<11s} t={row['elapsed_sec']:>7}s  {obj}")

    rows.sort(key=lambda r: (int(re.search(r"(\d+)", r["instance"]).group(1)), r["rep"]))
    csv_path = out_dir / "summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n_ok = sum(r["status"] == "ok" for r in rows)
    n_bad = len(rows) - n_ok
    tot_obj = sum(float(r["objective"]) for r in rows if r["status"] == "ok")
    print("-" * 78)
    print(f"done in {time.time()-t_start:.0f}s  |  ok={n_ok}/{len(rows)}"
          f"  invalid={n_bad}  |  sum(objective over ok)={tot_obj:,.0f}")
    if n_bad:
        for r in rows:
            if r["status"] != "ok":
                print(f"  !! {r['instance']:<10s} {r['status']}: {r['error'][:90]}")
    print(f"summary: {csv_path}")
    return 0 if n_bad == 0 else 1


# =============================================================================
# `compare` command
# =============================================================================

def _load_summary(dir_path: str) -> tuple[str, dict[str, dict]]:
    """Return (run_name, {instance: best_row}).  With --repeat, keep the best
    valid objective per instance (status 'ok' beats invalid; lower obj wins)."""
    p = pathlib.Path(dir_path)
    name = p.name
    best: dict[str, dict] = {}
    with open(p / "summary.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            inst = row["instance"]
            cur = best.get(inst)
            row_ok = row["status"] == "ok"
            if cur is None:
                best[inst] = row
            else:
                cur_ok = cur["status"] == "ok"
                if (row_ok and not cur_ok) or (
                        row_ok and cur_ok
                        and float(row["objective"]) < float(cur["objective"])):
                    best[inst] = row
    return name, best


def cmd_compare(cfg: argparse.Namespace) -> int:
    runs = [_load_summary(d) for d in cfg.dirs]
    names = [n for n, _ in runs]
    instances = sorted({i for _, d in runs for i in d},
                       key=lambda s: int(re.search(r"(\d+)", s).group(1)))
    R = len(runs)

    def cell(d: dict[str, dict], inst: str) -> tuple[float | None, str]:
        row = d.get(inst)
        if row is None:
            return None, "missing"
        if row["status"] != "ok":
            return None, row["status"]
        return float(row["objective"]), "ok"

    points = [0] * R
    n_valid = [0] * R
    regressions: list[str] = []  # vs first run (reference)

    wname = max(12, max(len(n) for n in names) + 2)
    header = "instance".ljust(11) + "".join(n[:wname-1].rjust(wname) for n in names)
    print(header)
    print("-" * len(header))

    for inst in instances:
        vals = [cell(d, inst) for _, d in runs]
        objs = [v for v, s in vals if v is not None]
        line = inst.ljust(11)
        for k, (v, s) in enumerate(vals):
            if v is None:
                points[k] += -1
                line += ("-1:" + s[:8]).rjust(wname)
            else:
                n_valid[k] += 1
                nb = sum(1 for o in objs if o < v)
                points[k] += R - nb
                mark = "*" if v == min(objs) else " "
                line += f"{v:,.0f}{mark}".rjust(wname)
        print(line)

        # regression check vs reference run (first dir)
        ref_v, ref_s = vals[0]
        for k in range(1, R):
            v, s = vals[k]
            if ref_v is not None and v is None:
                regressions.append(f"{inst}: {names[k]} became {s} (ref ok)")
            elif ref_v is not None and v is not None and v > ref_v * (1 + 1e-9):
                regressions.append(
                    f"{inst}: {names[k]} obj {v:,.0f} worse than {names[0]} {ref_v:,.0f}"
                    f" (+{(v/ref_v-1)*100:.1f}%)")

    print("-" * len(header))
    print("rank pts".ljust(11) + "".join(str(p).rjust(wname) for p in points)
          + f"   (per inst: -1 invalid, else R-nb; R={R})")
    print("valid".ljust(11) + "".join(f"{v}/{len(instances)}".rjust(wname) for v in n_valid))

    if len(runs) > 1:
        print()
        if regressions:
            print(f"REGRESSIONS vs {names[0]} ({len(regressions)}):")
            for r in regressions:
                print(f"  !! {r}")
        else:
            print(f"no regressions vs {names[0]}")
    return 0


# =============================================================================
# CLI
# =============================================================================

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run an algorithm over instances")
    r.add_argument("-a", "--alg", default=str(ROOT / "src"),
                   help="folder containing myalgorithm.py (default: src)")
    r.add_argument("-i", "--instances", nargs="*", default=None,
                   help="instance JSON files (default: all train/prob_*.json)")
    r.add_argument("-t", "--timelimit", type=float, default=60.0,
                   help="per-instance time limit in seconds (default 60)")
    r.add_argument("-j", "--jobs", type=int, default=0,
                   help="parallel jobs (default: cpu_count // cores)")
    r.add_argument("--cores", type=int, default=4,
                   help="CPU cores per solver, 0=unlimited (default 4, like server)")
    r.add_argument("--mem", type=float, default=16.0,
                   help="memory cap in GB per solver, 0=unlimited (default 16)")
    r.add_argument("--grace", type=float, default=10.0,
                   help="seconds past timelimit before hard kill (default 10)")
    r.add_argument("--check-timeout", type=float, default=900.0,
                   help="feasibility checker timeout in seconds (default 900)")
    r.add_argument("--repeat", type=int, default=1,
                   help="repetitions per instance (OGC_RUN_INDEX env tells them apart)")
    r.add_argument("--name", default=None, help="run name (default: alg_timestamp)")
    r.add_argument("--out", default=str(ROOT / "results"), help="results root dir")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("compare", help="compare result dirs + rank simulation")
    c.add_argument("dirs", nargs="+", help="results/<name> dirs; first = reference")
    c.set_defaults(func=cmd_compare)

    s = sub.add_parser("_solve")  # hidden child mode
    s.add_argument("--alg-dir", required=True)
    s.add_argument("--instance", required=True)
    s.add_argument("--timelimit", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(func=_solve_main)

    k = sub.add_parser("_check")  # hidden child mode
    k.add_argument("--instance", required=True)
    k.add_argument("--solution", required=True)
    k.add_argument("--out", required=True)
    k.set_defaults(func=_check_main)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
