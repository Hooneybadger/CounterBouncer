#!/usr/bin/env python3
"""v2.0.0 S3-mini — 시간축 relax-resolve GLS de-risk (v2 전체 빌드의 결정 게이트).

질문: 겹침완화+가중 GLS가 *시간이동(entry)+공간(x,y)*으로 충돌·크레인을 해소하면서 지각(obj1)을
v1 아래로 내리는가? (정적 프록시는 시간축 자유가 없어 가치를 과소평가 — 여기가 진짜 시험.)

설계: v1 construct 해에서 출발(feasible). bay·orient 고정, (x,y,entry)를 GLS로 움직인다. 점수 =
BIGW·(공간충돌 + 크레인 j≥k 위반) + w1·지각. 위반 쌍 가중치↑(sparrow). entry를 당기면 지각↓이나
충돌·크레인↑ → trade-off를 GLS가 푼다. 위반 0인 최선 해를 check_feasibility로 검증, v1과 obj1 비교.

충돌·크레인은 raster_engine 비트마스크로(§5.3 재사용). 공동존재 집합은 stage2/3/4 의미와 일치:
  공간(stage4): 같은 베이, 구간겹침, 레이어 k끼리.
  크레인 entry(stage2): aj < ai < ej 인 j들의 upper-OR와 i 마스크 겹침.
  크레인 exit(stage3): aj < ei < ej 인 j들의 upper-OR와 i 마스크 겹침.
"""
from __future__ import annotations
import json, math, random, sys, os, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from raster_engine import InstanceRaster
from constructor import construct, operations_from_committed, solution_obj, loads_from_committed
from utils import check_feasibility


def layer_ints(ir, bid, orient, R, px, py):
    """블록을 (px,py)에 놓을 때 레이어별 점유 정수 리스트(없는 레이어=0)."""
    out = []
    for lm in ir.masks(bid, orient):
        if lm.empty:
            out.append(0)
        else:
            out.append(lm.int_for_R(R) << ((py + lm.my0) * R + (px + lm.mx0)))
    return out


def upper_or(layer_list, nlayers):
    """suffix-OR: up[k] = OR_{j>=k} layer_list[j]. 크레인 j>=k 검사용."""
    up = [0] * nlayers
    acc = 0
    for k in range(nlayers - 1, -1, -1):
        acc |= layer_list[k] if k < len(layer_list) else 0
        up[k] = acc
    return up


def xy_range(ir, bid, orient, bay_id):
    bb = ir.local_bbox(bid, orient); ref = ir._ref(bid, orient)
    W, H = ir.bay_w[bay_id], ir.bay_h[bay_id]
    xlo = max(0, math.ceil(-(bb[0] - ref[0]))); xhi = math.floor(W - (bb[2] - ref[0]))
    ylo = max(0, math.ceil(-(bb[1] - ref[1]))); yhi = math.floor(H - (bb[3] - ref[1]))
    return xlo, xhi, ylo, yhi


def run(inst, tl_v1=20.0, gls_iter=300, seed=1, verbose=True):
    pi = json.load(open(inst)); ir = InstanceRaster(pi)
    blocks = pi["blocks"]; n = len(blocks)
    w = pi.get("weights", {}); w1, w2, w3 = w.get("w1", 1.), w.get("w2", 1.), w.get("w3", 1.)
    nbays = len(pi["bays"]); nl = ir.max_layers
    R = [ir.bay_w[b] for b in range(nbays)]

    # --- v1 base: construct (feasible) ---
    t = time.time()
    committed, loads, bw = construct(pi, t, tl_v1, ir=ir, order="edd", cand="scan", return_state=True)
    v1_sol = operations_from_committed(committed)
    v1 = check_feasibility(pi, v1_sol)
    if verbose:
        print(f"v1 construct: feasible={v1['feasible']} obj1={v1['obj1']:.0f} obj={v1['objective']:.0f}")

    # --- 상태 추출: 블록당 bay·orient 고정, (x,y,entry) 가변 ---
    bay = [0] * n; ori = [0] * n; X = [0] * n; Y = [0] * n; E = [0] * n
    proc = [int(b["processing_time"]) for b in blocks]
    rel = [int(b["release_time"]) for b in blocks]
    due = [int(b["due_date"]) for b in blocks]
    for b in range(nbays):
        for r in committed[b]:
            i = r["bid"]; bay[i] = b; ori[i] = r["orient"]; X[i] = r["px"]; Y[i] = r["py"]; E[i] = r["entry"]

    def exit_of(i):
        return E[i] + proc[i]

    by_bay = [[] for _ in range(nbays)]
    for i in range(n):
        by_bay[bay[i]].append(i)

    def block_viol(i):
        """블록 i의 공간충돌(stage4)+크레인(stage2/3) 위반 셀 수. 0이면 i는 feasible 기여."""
        bi = bay[i]; Ri = R[bi]; ei, xi = E[i], exit_of(i)
        li = layer_ints(ir, i, ori[i], Ri, X[i], Y[i])
        # 공간(stage4): 같은 베이·구간겹침·레이어 k끼리
        sp = 0
        for j in by_bay[bi]:
            if j == i:
                continue
            if ei < exit_of(j) and E[j] < xi:   # 구간 겹침
                lj = layer_ints(ir, j, ori[j], Ri, X[j], Y[j])
                for k in range(min(len(li), len(lj))):
                    ov = li[k] & lj[k]
                    if ov:
                        sp += ov.bit_count()
        # 크레인(stage2 entry: aj<ei<ej / stage3 exit: aj<xi<ej): 공동존재 upper-OR vs i layer k
        cr = 0
        ent_set = [j for j in by_bay[bi] if j != i and E[j] < ei < exit_of(j)]
        ext_set = [j for j in by_bay[bi] if j != i and E[j] < xi < exit_of(j)]
        for S in (ent_set, ext_set):
            if not S:
                continue
            agg = [0] * nl
            for j in S:
                lj = layer_ints(ir, j, ori[j], Ri, X[j], Y[j])
                for k in range(min(len(lj), nl)):
                    agg[k] |= lj[k]
            up = upper_or(agg, nl)
            for k in range(min(len(li), nl)):
                ov = li[k] & up[k]
                if ov:
                    cr += ov.bit_count()
        return sp, cr

    def total_obj1():
        return sum(max(0, exit_of(i) - due[i]) for i in range(n))

    def total_viol():
        s = c = 0
        for i in range(n):
            sp, cr = block_viol(i)
            s += sp; c += cr
        return s // 2, c  # 공간은 쌍마다 2번 셈

    s0, c0 = total_viol()
    if verbose:
        print(f"init(=v1) viol: spatial={s0} crane={c0} obj1={total_obj1()}  (feasible해야 0,0)")

    # --- relax-resolve GLS (sparrow): tardy entry 당김(위반 허용) → 위반-최소 해소 → 진짜 검증 ---
    from baseline_greedy import _build_operations
    rnd = random.Random(seed)

    def snapshot():
        return (X[:], Y[:], E[:])

    def restore(st):
        X[:], Y[:], E[:] = st[0][:], st[1][:], st[2][:]

    def real_check():
        asg = [{"block_id": i, "bay_id": bay[i], "x": int(X[i]), "y": int(Y[i]),
                "orient_idx": ori[i], "entry_time": int(E[i]), "exit_time": int(E[i] + proc[i])}
               for i in range(n)]
        return check_feasibility(pi, {"operations": _build_operations(asg)})

    def resolve(max_it):
        """위반만 최소화하는 해소(x,y는 자유, entry는 늦춤만 허용 — 당김은 tighten의 몫)."""
        for _ in range(max_it):
            vb = [i for i in range(n) if block_viol(i) != (0, 0)]
            if not vb:
                return True
            rnd.shuffle(vb)
            for i in vb:
                bi = bay[i]; xlo, xhi, ylo, yhi = xy_range(ir, i, ori[i], bi)
                cands = [(X[i], Y[i], E[i])]
                for _ in range(8):
                    cands.append((rnd.randint(xlo, xhi), rnd.randint(ylo, yhi), E[i]))
                for de in (1, 2, 4):                     # 늦춰서 해소(지각↑ 감수)
                    cands.append((X[i], Y[i], E[i] + de))

                def vscore(p):
                    ox, oy, oe = X[i], Y[i], E[i]; X[i], Y[i], E[i] = p
                    sp, cr = block_viol(i); X[i], Y[i], E[i] = ox, oy, oe
                    return sp + cr
                X[i], Y[i], E[i] = min(cands, key=vscore)
        return total_viol() == (0, 0)

    best_obj1 = v1["obj1"]; best_state = snapshot()
    rounds = 0
    for rd in range(gls_iter):
        restore(best_state)
        tardy = sorted((i for i in range(n) if exit_of(i) > due[i]),
                       key=lambda i: exit_of(i) - due[i], reverse=True)
        if not tardy:
            break
        # TIGHTEN: 지각 큰 블록들 entry를 release 쪽으로 당김(위반 허용)
        for i in tardy[:max(1, len(tardy) // 4)]:
            if E[i] > rel[i]:
                E[i] = max(rel[i], E[i] - max(1, (E[i] - rel[i] + 1) // 2))
        ok = resolve(50)
        rounds += 1
        if ok:
            r = real_check()
            if r["feasible"] and r["obj1"] < best_obj1:
                best_obj1 = r["obj1"]; best_state = snapshot()
        if verbose and rd % 20 == 0:
            print(f"  round{rd}: resolved={ok} cur_obj1={total_obj1()} best_feasible_obj1={best_obj1:.0f}")

    restore(best_state); fin = real_check()
    print(f"\n==> v1 obj1={v1['obj1']:.0f}  |  v2 temporal-GLS best obj1={best_obj1:.0f}  "
          f"({'GLS 우세' if best_obj1 < v1['obj1'] else '동등/v1'})  rounds={rounds}")
    print(f"    best 검증: feasible={fin['feasible']} stage={fin['stage']} "
          f"obj1={fin['obj1'] if fin['feasible'] else 'NA'}")


if __name__ == "__main__":
    inst = sys.argv[1] if len(sys.argv) > 1 else "../train/prob_27.json"
    run(inst, gls_iter=int(sys.argv[2]) if len(sys.argv) > 2 else 200)
