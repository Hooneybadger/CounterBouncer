"""#3 차등검증 -- src(구) vs src_dev(신) `_best_in_bay` 인라인이 동작 보존인지.

construct(huge timelimit -> deadline fallback 안 탐) 출력을 인스턴스별 정규 서명으로 찍는다.
두 알고리즘 디렉터리에서 같은 서명이 나오면 인라인이 비트 단위로 동일(=feasibility 보존).

사용: python learning/p5_difftest.py <algdir> <mode:blf|scan> [inst ...]
서명은 stdout 한 줄/인스턴스: "<inst> <md5>"
"""
import hashlib
import importlib.util
import json
import os
import sys
import time


def load_construct(algdir):
    algdir = os.path.abspath(algdir)
    sys.path.insert(0, algdir)
    mods = {}
    for name in ("raster_engine", "constructor"):
        spec = importlib.util.spec_from_file_location(name, os.path.join(algdir, name + ".py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
        mods[name] = m
    return mods["constructor"]


def signature(committed):
    rows = []
    for bay in committed:
        for r in bay:
            rows.append((int(r["bid"]), int(r["bay"]), int(r["orient"]),
                         int(r["px"]), int(r["py"]), int(r["entry"]), int(r["exit"])))
    rows.sort()
    return hashlib.md5(repr(rows).encode()).hexdigest()


def main():
    algdir, mode = sys.argv[1], sys.argv[2]
    order = "edd"
    cand = "scan" if mode == "scan" else "blf"
    insts = sys.argv[3:] or [f"prob_{i}" for i in range(1, 41)]
    construct_mod = load_construct(algdir)
    for inst in insts:
        prob = json.load(open(f"train/{inst}.json"))
        # t_start=now + huge timelimit -> 내부 deadline 절대 안 닿음 -> 전 탐색 결정적
        committed, _, _ = construct_mod.construct(
            prob, time.time(), 1e9, ir=None, order=order, cand=cand, return_state=True)
        print(f"{inst} {signature(committed)}", flush=True)


if __name__ == "__main__":
    main()
