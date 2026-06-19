#!/usr/bin/env python3
"""v2.0.0 S1 — 래스터 백엔드 CDE 위의 겹침완화 GLS (속도 게이트).

S2(gls_proto.py)가 메커니즘을 실증했으나 shapely 교차로 느렸다(한 베이 32~36블록 12~48초).
여기선 충돌 정량화를 *래스터 비트마스크*로 바꾼다 — 두 블록의 레이어별 점유 정수를 shift+AND
하고 .bit_count()(popcount)로 겹친 셀 수를 센다. 검증된 raster_engine 재사용(§5.3), C레벨 bigint
연산이라 shapely보다 수백 배 빠르다. 목표: 같은 +6~10% 밀도를 *훨씬 빠르게* 내는지.

충돌 = stage4와 동일(레이어 k끼리). 경계는 fits_in_bay(검증기 정확 복제)로 범위에서 보장.
"""
from __future__ import annotations
import json, math, random, sys, os, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from raster_engine import InstanceRaster, BayOccupancy, no_collision


def stamps_for(ir, bid, orient, R):
    """블록의 레이어별 (base_int, offset) 리스트. 위치 (px,py)의 레이어 점유 = base<<(py*R+px+off)."""
    out = []
    for lm in ir.masks(bid, orient):
        if lm.empty:
            out.append(None)
        else:
            out.append((lm.int_for_R(R), lm.my0 * R + lm.mx0))
    return out


def overlap_cells(st_i, pi, st_j, pj, R):
    """두 블록의 레이어별 same-layer 겹침 셀 수 합(stage4 충돌 정량). pi=(px,py)."""
    bxi = pi[1] * R + pi[0]
    bxj = pj[1] * R + pj[0]
    tot = 0
    n = min(len(st_i), len(st_j))
    for k in range(n):
        a = st_i[k]; b = st_j[k]
        if a is None or b is None:
            continue
        ov = (a[0] << (bxi + a[1])) & (b[0] << (bxj + b[1]))
        if ov:
            tot += ov.bit_count()
    return tot


def xy_range(ir, bid, orient, bay_id):
    bb = ir.local_bbox(bid, orient); ref = ir._ref(bid, orient)
    W, H = ir.bay_w[bay_id], ir.bay_h[bay_id]
    xlo = max(0, math.ceil(-(bb[0] - ref[0]))); xhi = math.floor(W - (bb[2] - ref[0]))
    ylo = max(0, math.ceil(-(bb[1] - ref[1]))); yhi = math.floor(H - (bb[3] - ref[1]))
    if xhi < xlo or yhi < ylo:
        return None
    return xlo, xhi, ylo, yhi


def blf_raster(ir, bids, bay_id):
    """래스터 BLF: 좌하단 우선 첫 무충돌 자리. 반환 {bid:(px,py)}."""
    occ = BayOccupancy(ir.bay_w[bay_id], ir.bay_h[bay_id], ir.max_layers)
    placed = {}
    for bid in bids:
        rng = xy_range(ir, bid, 0, bay_id)
        if rng is None:
            continue
        xlo, xhi, ylo, yhi = rng
        masks = ir.masks(bid, 0)
        done = False
        for py in range(ylo, yhi + 1):
            for px in range(xlo, xhi + 1):
                if no_collision(ir, occ, bay_id, bid, 0, px, py):
                    occ.add(masks, px, py); placed[bid] = (px, py); done = True; break
            if done:
                break
    return placed


def gls_raster(ir, bids, bay_id, seed=0, max_iter=400, k_div=8, k_foc=8):
    """겹침완화 + 가중 GLS(래스터 충돌). 반환 (pos, success, total_cells, iters)."""
    rnd = random.Random(seed)
    R = ir.bay_w[bay_id]
    ranges = {b: xy_range(ir, b, 0, bay_id) for b in bids}
    if any(v is None for v in ranges.values()):
        return None, False, 1 << 30, 0
    st = {b: stamps_for(ir, b, 0, R) for b in bids}
    pos = {b: (rnd.randint(*ranges[b][:2]), rnd.randint(*ranges[b][2:])) for b in bids}
    w = {}
    bl = list(bids)

    def pair_w(i, j):
        return w.get((i, j) if i < j else (j, i), 1.0)

    for it in range(max_iter):
        # 충돌 집합 + 총 겹침 (전 쌍 비트-AND)
        colliding = set(); total = 0
        for a in range(len(bl)):
            for c in range(a + 1, len(bl)):
                i, j = bl[a], bl[c]
                ov = overlap_cells(st[i], pos[i], st[j], pos[j], R)
                if ov:
                    colliding.add(i); colliding.add(j); total += ov
                    key = (i, j)
                    w[key] = min(w.get(key, 1.0) * 1.5, 1e6)
        if total == 0:
            return pos, True, 0, it
        for key in list(w.keys()):
            if w[key] > 1.0:
                w[key] = max(1.0, w[key] * 0.97)
        order = list(colliding); rnd.shuffle(order)
        for i in order:
            xlo, xhi, ylo, yhi = ranges[i]
            cx, cy = pos[i]
            sx = max(1.0, (xhi - xlo) * 0.15); sy = max(1.0, (yhi - ylo) * 0.15)
            cands = [(rnd.randint(xlo, xhi), rnd.randint(ylo, yhi)) for _ in range(k_div)]
            for _ in range(k_foc):
                cands.append((min(xhi, max(xlo, int(round(rnd.gauss(cx, sx))))),
                              min(yhi, max(ylo, int(round(rnd.gauss(cy, sy)))))))
            cands.append(pos[i])

            def score(p):
                s = 0.0
                for j in bl:
                    if j == i:
                        continue
                    ov = overlap_cells(st[i], p, st[j], pos[j], R)
                    if ov:
                        s += pair_w(i, j) * ov
                return s
            best_p = min(cands, key=score); best_s = score(best_p)
            bx, by = best_p
            stepx = max(1, int((xhi - xlo) * 0.1)); stepy = max(1, int((yhi - ylo) * 0.1))
            for _ in range(10):
                improved = False
                for dx, dy in ((stepx, 0), (-stepx, 0), (0, stepy), (0, -stepy)):
                    nx = min(xhi, max(xlo, bx + dx)); ny = min(yhi, max(ylo, by + dy))
                    s = score((nx, ny))
                    if s < best_s - 1e-9:
                        best_s, bx, by = s, nx, ny; improved = True
                if not improved:
                    if stepx == 1 and stepy == 1:
                        break
                    stepx = max(1, stepx // 2); stepy = max(1, stepy // 2)
            pos[i] = (bx, by)
    # 잔여 총겹침 재계산
    total = sum(overlap_cells(st[bl[a]], pos[bl[a]], st[bl[c]], pos[bl[c]], R)
                for a in range(len(bl)) for c in range(a + 1, len(bl)))
    return pos, total == 0, total, max_iter


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "../train/prob_27.json"
    bay_id = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    pi = json.load(open(inst)); ir = InstanceRaster(pi)
    W, H = ir.bay_w[bay_id], ir.bay_h[bay_id]
    n = len(pi["blocks"])
    # 베이에 드는 블록을 면적 오름차순(작은 것부터), ~80% area까지
    fit = [b for b in range(n) if xy_range(ir, b, 0, bay_id) is not None]
    def area(b):
        bb = ir.local_bbox(b, 0); return (bb[2] - bb[0]) * (bb[3] - bb[1])
    fit.sort(key=area)
    cum, take = 0.0, 0
    for b in fit:
        if cum + area(b) > 0.80 * W * H:
            break
        cum += area(b); take += 1
    cand = fit[:take]
    print(f"=== {os.path.basename(inst)} bay{bay_id} {W}x{H} | 후보 {take}개 area합 {cum:.0f}({cum/(W*H)*100:.0f}%) [RASTER CDE] ===")
    t = time.time(); blf = blf_raster(ir, cand, bay_id); tb = time.time() - t
    M = len(blf); print(f"BLF: {M}/{take}  ({tb:.2f}s)")
    best = 0
    for target in range(max(1, M - 1), min(take, M + 8) + 1):
        t = time.time(); fit_any = False; best_resid = 1 << 30
        for s in range(6):                 # best-of-6 재시작(sparrow exploration의 disruption 대용)
            pos, ok, tot, iters = gls_raster(ir, cand[:target], bay_id, seed=s, max_iter=600)
            best_resid = min(best_resid, tot)
            if ok:
                fit_any = True; break
        tg = time.time() - t
        if fit_any:
            best = target
        print(f"GLS target={target:>2}: fit={fit_any} best_resid={best_resid} ({tg:.2f}s, best-of-6)")
    print(f"\n==> BLF {M} vs GLS {best}  ({'GLS 우세' if best > M else '동등/BLF'})")


if __name__ == "__main__":
    main()
