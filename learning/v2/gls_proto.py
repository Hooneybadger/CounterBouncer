#!/usr/bin/env python3
"""v2.0.0 프로토타입 — sparrow식 겹침완화+가중 GLS 정적 패커 vs BLF (S2 게이트).

목적: v2 thesis의 첫 결정적 검증 — "비중첩을 *완화*하고(겹침 허용) 가중 Guided Local
Search로 밀어내며 해소"가 구성적 BLF보다 *우리 도형*을 더 조밀하게 채우는가?
정적·단일 베이·orient 0·회전 없음(필요조건 — 못 이기면 시간·크레인 확장 무의미).

설계 출처(§5.3): jagua-rs CDE(STRtree broad phase + 실제 교차 narrow), sparrow(겹침완화→
가중 GLS, 샘플 divergence/focus, 충돌쌍 가중치↑·비충돌↓). 충돌 정량화는 교차 면적(프로토).
"""
from __future__ import annotations
import json, math, random, sys, os, time
from shapely.geometry import Polygon
from shapely import STRtree
from shapely.affinity import translate

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import _resolve_layers


def block_local_poly(blk, oi=0):
    l0 = _resolve_layers(blk["shape"][oi]["layers"])[0]
    p = Polygon([(v[0], v[1]) for v in l0])
    return p if p.is_valid else p.buffer(0)


def _xy_range(poly, W, H):
    """이 도형이 베이 [0,W]x[0,H]에 들어가는 (x,y) 정수 범위. 안 들면 None."""
    minx, miny, maxx, maxy = poly.bounds
    xlo, xhi = math.ceil(-minx), math.floor(W - maxx)
    ylo, yhi = math.ceil(-miny), math.floor(H - maxy)
    if xhi < xlo or yhi < ylo:
        return None
    return xlo, xhi, ylo, yhi


# ---------------------------------------------------------------- BLF 베이스라인
def blf_pack(polys, W, H):
    """구성적 BLF: 각 도형을 좌하단 우선 첫 feasible 정수 자리에. 못 들면 건너뜀. 반환 {i:(x,y)}."""
    placed, pgeoms = {}, []
    tree = None
    for i, poly in enumerate(polys):
        rng = _xy_range(poly, W, H)
        if rng is None:
            continue
        xlo, xhi, ylo, yhi = rng
        done = False
        for y in range(ylo, yhi + 1):
            for x in range(xlo, xhi + 1):
                cand = translate(poly, x, y)
                hit = False
                if tree is not None:
                    for j in tree.query(cand):
                        if cand.intersection(pgeoms[j]).area > 1e-9:
                            hit = True
                            break
                if not hit:
                    placed[i] = (x, y)
                    pgeoms.append(cand)
                    tree = STRtree(pgeoms)
                    done = True
                    break
            if done:
                break
    return placed


# ---------------------------------------------------------------- GLS 패커
def gls_pack(polys, W, H, rng_seed=0, max_iter=400, k_div=8, k_foc=8):
    """겹침완화 + 가중 GLS. 주어진 *전체* polys를 한 베이에 욱여넣어 겹침 0으로 해소 시도.
    반환: (positions{i:(x,y)}, success, final_overlap, iters)."""
    rnd = random.Random(rng_seed)
    n = len(polys)
    ranges = [_xy_range(p, W, H) for p in polys]
    if any(r is None for r in ranges):
        return None, False, float("inf"), 0  # 베이보다 큰 도형 — 정적 불가
    pos = {}
    for i in range(n):
        xlo, xhi, ylo, yhi = ranges[i]
        pos[i] = (rnd.randint(xlo, xhi), rnd.randint(ylo, yhi))  # 정수 무작위(겹침 허용)
    w = {}  # (i,j)->weight, i<j

    def at(i, x, y):
        return translate(polys[i], x, y)

    def pair_overlap(i, gi, j):
        return gi.intersection(geoms[j]).area

    geoms = [at(i, *pos[i]) for i in range(n)]
    for it in range(max_iter):
        tree = STRtree(geoms)
        # 현재 충돌 집합 + 총 겹침
        colliding = set()
        total = 0.0
        for i in range(n):
            for j in tree.query(geoms[i]):
                if j <= i:
                    continue
                a = geoms[i].intersection(geoms[j]).area
                if a > 1e-9:
                    colliding.add(i); colliding.add(j)
                    total += a
        if total < 1e-6:
            return {i: (int(round(pos[i][0])), int(round(pos[i][1]))) for i in range(n)}, True, 0.0, it
        # 가중치 갱신: 충돌쌍 ↑, 그 외 ↓(1.0로 감쇠)
        for i in range(n):
            for j in tree.query(geoms[i]):
                if j <= i:
                    continue
                key = (i, j)
                a = geoms[i].intersection(geoms[j]).area
                if a > 1e-9:
                    w[key] = min(w.get(key, 1.0) * 1.5, 1e6)
        for key in list(w.keys()):
            if w[key] > 1.0:
                w[key] = max(1.0, w[key] * 0.97)
        # 충돌 블록을 무작위 순서로 재배치(샘플 divergence+focus, 가중 겹침 최소 자리)
        order = list(colliding); rnd.shuffle(order)
        for i in order:
            xlo, xhi, ylo, yhi = ranges[i]
            cands = [(rnd.randint(xlo, xhi), rnd.randint(ylo, yhi)) for _ in range(k_div)]
            cx, cy = pos[i]
            sx = max(1.0, (xhi - xlo) * 0.15); sy = max(1.0, (yhi - ylo) * 0.15)
            for _ in range(k_foc):
                nx = min(xhi, max(xlo, int(round(rnd.gauss(cx, sx)))))
                ny = min(yhi, max(ylo, int(round(rnd.gauss(cy, sy)))))
                cands.append((nx, ny))
            cands.append(pos[i])  # 현 위치도 후보
            def score(x, y):
                gi = at(i, x, y)
                s = 0.0
                for j in tree.query(gi):
                    if j == i:
                        continue
                    a = gi.intersection(geoms[j]).area
                    if a > 1e-9:
                        key = (i, j) if i < j else (j, i)
                        s += w.get(key, 1.0) * a
                return s
            best_s, best_p = None, pos[i]
            for (x, y) in cands:
                s = score(x, y)
                if best_s is None or s < best_s:
                    best_s, best_p = s, (x, y)
            # sparrow식 좌표하강 정밀화(정수 격자): 최선 샘플에서 축별 정수 스텝으로 감소 방향 탐색
            bx, by = best_p; xlo, xhi, ylo, yhi = ranges[i]
            stepx = max(1, int((xhi - xlo) * 0.1)); stepy = max(1, int((yhi - ylo) * 0.1))
            for _ in range(10):
                improved = False
                for dx, dy in ((stepx, 0), (-stepx, 0), (0, stepy), (0, -stepy)):
                    nx = min(xhi, max(xlo, bx + dx)); ny = min(yhi, max(ylo, by + dy))
                    s = score(nx, ny)
                    if s < best_s - 1e-9:
                        best_s, bx, by = s, nx, ny; improved = True
                if not improved:
                    if stepx == 1 and stepy == 1:
                        break
                    stepx = max(1, stepx // 2); stepy = max(1, stepy // 2)
            pos[i] = (bx, by)
            geoms[i] = at(i, bx, by)
    return {i: (int(round(pos[i][0])), int(round(pos[i][1]))) for i in range(n)}, False, total, max_iter


def _verify(polys, pos, W, H):
    """정수 위치에서 실제 겹침/경계 위반 면적(0이면 진짜 feasible 패킹)."""
    geoms = [translate(polys[i], x, y) for i, (x, y) in pos.items()]
    ov = 0.0
    for a in range(len(geoms)):
        cb = geoms[a].bounds
        if cb[0] < -1e-6 or cb[1] < -1e-6 or cb[2] > W + 1e-6 or cb[3] > H + 1e-6:
            ov += 1e9
        for b in range(a + 1, len(geoms)):
            ov += geoms[a].intersection(geoms[b]).area
    return ov


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "../train/prob_27.json"
    bay_id = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    pi = json.load(open(inst))
    bay = pi["bays"][bay_id]; W, H = bay["width"], bay["height"]
    polys_all = [block_local_poly(b) for b in pi["blocks"]]
    polys_all = [p for p in polys_all if _xy_range(p, W, H) is not None]  # 베이에 드는 것만
    polys_all.sort(key=lambda p: p.area)                 # 작은 것부터(많은 블록 → 패킹 결정 많음)
    bay_area = W * H
    TARGET = 0.80
    cum, take = 0.0, 0
    for p in polys_all:
        if cum + p.area > TARGET * bay_area:
            break
        cum += p.area; take += 1
    cand = polys_all[:take]
    print(f"=== {os.path.basename(inst)} bay{bay_id} {W}x{H}(area {bay_area}) | 후보 {take}개 area합 {cum:.0f}({cum/bay_area*100:.0f}%) ===")

    t = time.time(); blf = blf_pack(cand, W, H); tb = time.time() - t
    print(f"BLF: {len(blf)}/{take} 배치  ({tb:.2f}s)")

    # GLS: BLF가 채운 수(M)부터 시작해 +1씩, 어디까지 겹침0으로 해소하나
    M = len(blf)
    best_gls = 0
    for target in range(max(1, M - 1), min(take, M + 6) + 1):
        t = time.time()
        pos, ok, ov, iters = gls_pack(cand[:target], W, H, rng_seed=1)
        tg = time.time() - t
        vov = _verify(cand[:target], pos, W, H) if pos else float("inf")
        real_ok = ok and vov < 1e-6
        if real_ok:
            best_gls = target
        print(f"GLS target={target:>2}: resolve={ok} verify_overlap={vov:.3f} real_fit={real_ok} iters={iters} ({tg:.2f}s)")
    print(f"\n==> BLF {M}개 vs GLS {best_gls}개  ({'GLS 우세' if best_gls > M else 'BLF 동등/우세'})")


if __name__ == "__main__":
    main()
