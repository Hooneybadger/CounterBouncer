"""#3 A/B -- 한 알고리즘 디렉터리에서 algorithm(prob,60)을 돌려 obj1/feasible 출력.

서버 모사(taskset로 4코어 핀은 호출부에서)로 src vs src_dev 의 obj1을 직접 비교한다.
큰 인스턴스에서 인라인(반복 ↑)이 obj1을 낮추는지 본다.

사용: P5_SRC=<algdir> python learning/p5_ab60.py <inst> <timelimit>
출력 한 줄: "<inst> feasible=<bool> obj1=<n> obj=<n> elapsed=<s>"
"""
import importlib.util
import json
import os
import sys
import time


def load(algdir, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(algdir, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def main():
    algdir = os.path.abspath(os.environ["P5_SRC"])
    sys.path.insert(0, algdir)
    inst = sys.argv[1]
    tl = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
    myalg = load(algdir, "myalgorithm")
    utils = load(algdir, "utils")
    prob = json.load(open(f"train/{inst}.json"))
    t0 = time.time()
    sol = myalg.algorithm(prob, tl)
    el = time.time() - t0
    res = utils.check_feasibility(prob, sol)
    print(f"{inst} feasible={res['feasible']} obj1={res['obj1']} "
          f"obj={res['objective']} elapsed={el:.1f}", flush=True)


if __name__ == "__main__":
    main()
