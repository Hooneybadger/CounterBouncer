"""P6 -- 기하-인지(2D no-overlap) obj1 *유효 하한* + 헤드룸 프로브.

P5a 면적완화 cumulative 하한은 40개 전부 ~0(non-binding) 이었다. "어느 시각 면적 합
<= 베이면적"이 너무 느슨해서다 -- 블록을 시간상 어긋내면 면적상 다 들어간다. P5a 의
진단은 진짜 병목이 *면적*이 아니라 *2D 모양 + 크레인*이라는 것이었다. 이 스크립트는
그 다음 칸을 *유효 하한*으로 잰다.

[유효성의 핵심] 진짜 footprint(다각형) F_i 는 쌍쌍이 안 겹친다. 각 블록을 그 안에
들어가는 *내접 축정렬 사각형* r_i ⊆ F_i 로 줄이면, r_i 들도 쌍쌍이 안 겹친다(안 겹치는
집합의 부분집합). 따라서 "내접 사각형들의 2D no-overlap"은 진짜 배치의 *필요조건* =
유효한 완화다. 내접 사각형은 면적보다 *모양*을 더 담으므로 면적완화보다 빡빡하다.
크레인은 무시(완화 유효 방향). => 이 모델의 (증명된) 하한은 진짜 obj1 의 유효 하한.

[부분집합 단조성] 블록을 빼면 지각은 늘지 않는다(공간 경합이 줄어 각자 더 일찍/같이
들어감). 그러므로 *부분집합 S 의 최적 지각 <= 전체 최적 지각 중 S 가 받는 몫 <= 전체
obj1*. 즉 가장 빡빡한(release 이른·동시경합 큰) N개 부분집합의 유효 하한은 전체
obj1 의 유효 하한이다. N개로 줄여 CP-SAT 가 OPTIMAL/하한을 받게 한다.

bbox 모드(--shape bbox)는 반대로 footprint 를 *과대*(bbox >= 진짜) 잡아 no-overlap 을
강화 -- 하한이 아니라 '오버행 nesting 없이 같은 블록을 패킹할 때의 최적' 참조점이다.
두 값(inscribed=유효하한, bbox=nesting無 최적)이 우리 해를 위아래로 감싼다.
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from utils import _resolve_layers, _poly_from_verts  # noqa: E402
from ortools.sat.python import cp_model  # noqa: E402
from shapely.geometry import box  # noqa: E402


def _largest_inscribed_rect(poly):
    """다각형 안에 들어가는 최대 면적 축정렬 정수 사각형 (w,h). 코스 그리드 스캔.

    내접이므로 진짜 footprint 의 부분집합 -> no-overlap 유효성 보존. 정수 격자에서
    가능한 (x0,y0,x1,y1) 사각형이 poly 에 완전히 포함되는지를 검사해 면적 최대를 찾는다.
    O((W*H)^2) 라 작은 블록에만 쓴다(블록 bbox 가 보통 <=15x15).
    """
    minx, miny, maxx, maxy = poly.bounds
    x0i, y0i = int(math.floor(minx)), int(math.floor(miny))
    x1i, y1i = int(math.ceil(maxx)), int(math.ceil(maxy))
    # 포함 여부를 픽셀 마스크로: 셀 (x,y)..(x+1,y+1) 중심이 poly 안인가
    W = x1i - x0i
    H = y1i - y0i
    if W <= 0 or H <= 0:
        return (0, 0)
    inside = [[False] * W for _ in range(H)]
    for yy in range(H):
        for xx in range(W):
            cx = x0i + xx + 0.5
            cy = y0i + yy + 0.5
            if poly.contains(box(x0i + xx, y0i + yy, x0i + xx + 1, y0i + yy + 1).centroid):
                # 더 엄격히: 셀 전체가 poly 안인지 (내접 보장)
                if poly.contains(box(x0i + xx, y0i + yy, x0i + xx + 1, y0i + yy + 1)):
                    inside[yy][xx] = True
    # 최대 직사각형 (모두 inside) -- 히스토그램 기반 O(W*H)
    best_area = 0
    best_wh = (0, 0)
    heights = [0] * W
    for yy in range(H):
        for xx in range(W):
            heights[xx] = heights[xx] + 1 if inside[yy][xx] else 0
        # 이 행 기준 최대 직사각형
        stack = []
        for xx in range(W + 1):
            cur = heights[xx] if xx < W else 0
            start = xx
            while stack and stack[-1][1] >= cur:
                s, h = stack.pop()
                area = h * (xx - s)
                if area > best_area:
                    best_area = area
                    best_wh = (xx - s, h)
                start = s
            stack.append((start, cur))
    return best_wh


def block_orients(blk, shape):
    """방향별 (w,h) 정수. shape='inscribed' 유효하한, 'bbox' nesting無 상한참조."""
    out = []
    for o in blk["shape"]:
        l0 = _resolve_layers(o["layers"])[0]
        if shape == "bbox":
            xs = [v[0] for v in l0]
            ys = [v[1] for v in l0]
            w = math.ceil(max(xs) - min(xs))
            h = math.ceil(max(ys) - min(ys))
        else:
            p = _poly_from_verts(l0)
            w, h = _largest_inscribed_rect(p)
        if w > 0 and h > 0:
            out.append((w, h))
    return sorted(set(out))


def solve_geom(bays, jobs, our_obj1, time_limit, workers, single_bay=None):
    m = cp_model.CpModel()
    nb = len(bays)
    bay_ids = [single_bay] if single_bay is not None else list(range(nb))
    H = max(max(j["r"] for j in jobs), max(j["due"] for j in jobs)) + sum(j["p"] for j in jobs)

    B = []
    for i, j in enumerate(jobs):
        entry = m.NewIntVar(j["r"], H, f"e{i}")
        exit_ = m.NewIntVar(j["r"], H + j["p"], f"x{i}")
        m.Add(exit_ == entry + j["p"])
        tard = m.NewIntVar(0, H, f"t{i}")
        m.Add(tard >= exit_ - j["due"])
        opts = []
        for b in bay_ids:
            W, Hh = bays[b]["width"], bays[b]["height"]
            for (w, h) in j["orients"]:
                if w > W or h > Hh:
                    continue
                lit = m.NewBoolVar(f"a{i}_{b}_{w}_{h}")
                px = m.NewIntVar(0, W - w, f"px{i}_{b}_{w}_{h}")
                py = m.NewIntVar(0, Hh - h, f"py{i}_{b}_{w}_{h}")
                opts.append(dict(lit=lit, bay=b, w=w, h=h, px=px, py=py))
        if not opts:
            return dict(status="NO_FIT", lb=0.0, opt=None, proven=False, elapsed=0.0,
                        note=f"block {i} fits no bay")
        m.AddExactlyOne([o["lit"] for o in opts])
        B.append(dict(entry=entry, exit=exit_, tard=tard, opts=opts, j=j))

    # 쌍별 5-way 분리 disjunction (2D no-overlap + 시간축). 두 블록이 *같은 베이*면
    # (시간분리 i<k) OR (시간분리 k<i) OR (x분리 L/R) OR (y분리 D/U) 중 하나가 반드시
    # 성립해야 한다. 다른 베이면 공간 무관. 이 disjunction 을 'same-bay 일 때만' 켜되,
    # x/y 분리는 두 블록이 같은 베이의 같은 (방향) 후보를 골랐을 때의 위치변수에 대해
    # 건다. 정합성 위해 블록당 '실효 위치' 변수(선택된 후보의 px/py/w/h)를 하나로 모은다.
    n = len(B)
    # 블록별 실효 폭/높이/위치/베이 (선택된 후보로 channel)
    for b in B:
        Wmax = max(o["w"] for o in b["opts"]); Hmax = max(o["h"] for o in b["opts"])
        baymax = max(o["bay"] for o in b["opts"])
        b["X"] = m.NewIntVar(0, max(bays[bb]["width"] for bb in bay_ids), f"X{id(b)%99999}")
        b["Y"] = m.NewIntVar(0, max(bays[bb]["height"] for bb in bay_ids), f"Y{id(b)%99999}")
        b["Wv"] = m.NewIntVar(1, Wmax, f"W{id(b)%99999}")
        b["Hv"] = m.NewIntVar(1, Hmax, f"H{id(b)%99999}")
        b["Bv"] = m.NewIntVar(0, baymax, f"B{id(b)%99999}")
        for o in b["opts"]:
            m.Add(b["X"] == o["px"]).OnlyEnforceIf(o["lit"])
            m.Add(b["Y"] == o["py"]).OnlyEnforceIf(o["lit"])
            m.Add(b["Wv"] == o["w"]).OnlyEnforceIf(o["lit"])
            m.Add(b["Hv"] == o["h"]).OnlyEnforceIf(o["lit"])
            m.Add(b["Bv"] == o["bay"]).OnlyEnforceIf(o["lit"])

    for i in range(n):
        for k in range(i + 1, n):
            bi, bk = B[i], B[k]
            same_bay = m.NewBoolVar(f"sb{i}_{k}")
            m.Add(bi["Bv"] == bk["Bv"]).OnlyEnforceIf(same_bay)
            m.Add(bi["Bv"] != bk["Bv"]).OnlyEnforceIf(same_bay.Not())
            ti = m.NewBoolVar(f"ti{i}_{k}")   # i exit <= k entry (시간 i 먼저)
            tk = m.NewBoolVar(f"tk{i}_{k}")   # k exit <= i entry
            L = m.NewBoolVar(f"L{i}_{k}")     # i 왼쪽
            R = m.NewBoolVar(f"R{i}_{k}")
            Dn = m.NewBoolVar(f"D{i}_{k}")
            Up = m.NewBoolVar(f"U{i}_{k}")
            m.Add(bi["exit"] <= bk["entry"]).OnlyEnforceIf(ti)
            m.Add(bk["exit"] <= bi["entry"]).OnlyEnforceIf(tk)
            m.Add(bi["X"] + bi["Wv"] <= bk["X"]).OnlyEnforceIf(L)
            m.Add(bk["X"] + bk["Wv"] <= bi["X"]).OnlyEnforceIf(R)
            m.Add(bi["Y"] + bi["Hv"] <= bk["Y"]).OnlyEnforceIf(Dn)
            m.Add(bk["Y"] + bk["Hv"] <= bi["Y"]).OnlyEnforceIf(Up)
            # same_bay => 최소 하나의 분리. 다른 베이면 제약 없음.
            m.AddBoolOr([ti, tk, L, R, Dn, Up]).OnlyEnforceIf(same_bay)

    total = m.NewIntVar(0, n * H, "total")
    m.Add(total == sum(b["tard"] for b in B))
    if our_obj1 is not None and our_obj1 >= 0:
        m.Add(total <= int(our_obj1))
    m.Minimize(total)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_workers = workers
    t0 = time.time()
    st = solver.Solve(m)
    el = time.time() - t0
    opt = (solver.ObjectiveValue()
           if st in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None)
    return dict(
        status=solver.StatusName(st),
        lb=max(0.0, solver.BestObjectiveBound()),
        opt=opt,
        proven=(st == cp_model.OPTIMAL),
        elapsed=el,
        note="",
    )


def load(name, shape):
    d = json.load(open(os.path.join(os.path.dirname(__file__), "..", "train", f"{name}.json")))
    bays = d["bays"]
    jobs = []
    for blk in d["blocks"]:
        jobs.append(dict(
            r=int(blk["release_time"]),
            p=int(blk["processing_time"]),
            due=int(blk["due_date"]),
            orients=block_orients(blk, shape),
        ))
    return bays, jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inst")
    ap.add_argument("-n", "--nblocks", type=int, default=12)
    ap.add_argument("-t", "--timelimit", type=float, default=60.0)
    ap.add_argument("-w", "--workers", type=int, default=8)
    ap.add_argument("--bay", type=int, default=None)
    ap.add_argument("--shape", choices=["inscribed", "bbox"], default="inscribed")
    args = ap.parse_args()

    bays, jobs = load(args.inst, args.shape)
    order = sorted(range(len(jobs)), key=lambda i: (jobs[i]["r"], jobs[i]["due"]))
    sel = order[:args.nblocks]
    sub = [jobs[i] for i in sel]
    kind = "VALID-LB(내접)" if args.shape == "inscribed" else "참조(bbox,nesting無)"
    print(f"{args.inst} [{kind}]: full={len(jobs)} nbay={len(bays)} -> N={len(sub)} bay={args.bay}")
    print(f"  due range: {min(j['due'] for j in sub)}..{max(j['due'] for j in sub)}; "
          f"sum(proc)={sum(j['p'] for j in sub)}; no-wait-tard={sum(max(0,j['r']+j['p']-j['due']) for j in sub)}")
    res = solve_geom(bays, sub, None, args.timelimit, args.workers, single_bay=args.bay)
    tag = "유효하한" if args.shape == "inscribed" else "참조최적"
    print(f"  status={res['status']} proven={res['proven']} opt={res['opt']} "
          f"{tag}(LB)={res['lb']:.0f} elapsed={res['elapsed']:.1f}s {res['note']}")


if __name__ == "__main__":
    main()
