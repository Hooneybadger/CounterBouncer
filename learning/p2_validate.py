#!/usr/bin/env python
# =============================================================================
# P2 검증 하니스 -- 래스터 엔진 vs Shapely(utils) 판정 일치 + 속도
#
# 종료 기준(STRATEGY B2/P2):
#   (1) 비보수 불일치 0건: 래스터가 feasible 이라 한 배치는 utils 도 반드시 feasible.
#       (역방향, 즉 래스터 infeasible / utils feasible 은 '보수적 손실'로 허용·계측.)
#   (2) 배치 1회 feasibility 판정이 베이스라인(Shapely) 대비 100배 이상 빠름.
#   (3) 보강: 각 마스크가 per-cell 진리값(양의 면적 셀)의 superset 인지 직접 확인.
#
# 실행: ~/miniforge3/envs/ogc2026/bin/python learning/p2_validate.py
# =============================================================================
import glob
import json
import math
import os
import random
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import raster_engine as re  # noqa: E402
from utils import (  # noqa: E402
    Bay, Block, check_entry, check_exit, check_collisions, _poly_from_verts,
)
from shapely.geometry import box as sbox  # noqa: E402

SEED = 12345
INSTANCES = sorted(glob.glob(os.path.join(HERE, "..", "train", "prob_*.json")),
                   key=lambda p: int(os.path.basename(p)[5:-5]))


# -----------------------------------------------------------------------------
# 보조: IFP 정수 범위 (block,orient 이 bay 안에 드는 (px,py) 구간)
# -----------------------------------------------------------------------------
def ifp_range(ir, bay_id, bid, orient):
    bb = ir.local_bbox(bid, orient)
    layers = ir.blocks[bid]["shape"][orient]["layers"]
    ref = layers[0][0] if layers and layers[0] else (0.0, 0.0)
    W, H = ir.bay_w[bay_id], ir.bay_h[bay_id]
    px_lo = max(0, math.ceil(-(bb[0] - ref[0])))
    px_hi = math.floor(W - (bb[2] - ref[0]))
    py_lo = max(0, math.ceil(-(bb[1] - ref[1])))
    py_hi = math.floor(H - (bb[3] - ref[1]))
    return px_lo, px_hi, py_lo, py_hi


def rand_pos_near(rng, lo, hi, anchor, spread):
    if hi < lo:
        return None
    a = min(max(anchor + rng.randint(-spread, spread), lo), hi)
    return a


# -----------------------------------------------------------------------------
# 마스크 superset 검증: 양의-면적 진리 셀 ⊆ 래스터 마스크
# -----------------------------------------------------------------------------
def validate_masks_superset(ir, sample, rng):
    viol = 0
    total_truth = 0
    total_marked = 0
    for (bid, orient) in sample:
        raw = re._resolve_layers(ir.blocks[bid]["shape"][orient]["layers"])
        ref = raw[0][0] if raw and raw[0] else (0.0, 0.0)
        rel_layers = [[[x - ref[0], y - ref[1]] for x, y in L] for L in raw]
        masks = ir.masks(bid, orient)
        for k, lm in enumerate(masks):
            poly = _poly_from_verts(rel_layers[k])
            if poly is None or poly.is_empty or poly.area <= 0:
                continue
            minx, miny, maxx, maxy = poly.bounds
            for cy in range(math.floor(miny), math.ceil(maxy)):
                for cx in range(math.floor(minx), math.ceil(maxx)):
                    inter = poly.intersection(sbox(cx, cy, cx + 1, cy + 1))
                    if inter.is_empty or inter.area <= 0:
                        continue
                    total_truth += 1
                    if lm.bit_at(cx, cy) == 0:
                        viol += 1
            total_marked += sum(bin(r).count("1") for r in lm.row_ints)
    return viol, total_truth, total_marked


# -----------------------------------------------------------------------------
# 메인 일치 검증
# -----------------------------------------------------------------------------
def run():
    rng = random.Random(SEED)
    tally = {
        "entry": {"agree_T": 0, "agree_F": 0, "cons_loss": 0, "VIOL": 0},
        "exit":  {"agree_T": 0, "agree_F": 0, "cons_loss": 0, "VIOL": 0},
        "coll":  {"agree_T": 0, "agree_F": 0, "cons_loss": 0, "VIOL": 0},
    }
    viol_examples = []
    mask_viol_total = 0
    mask_truth_total = 0
    mask_marked_total = 0

    TRIALS_PER_INST = 120  # 인스턴스당 시나리오 수
    POS_PER_TRIAL = 12     # 시나리오마다 새 블록 후보 위치 수

    for path in INSTANCES:
        prob = json.load(open(path))
        name = prob.get("name", os.path.basename(path))
        ir = re.InstanceRaster(prob)
        nblk = len(prob["blocks"])

        # 마스크 superset 표본 (전 방향 포함)
        sample = []
        for _ in range(min(8, nblk)):
            b = rng.randrange(nblk)
            no = len(prob["blocks"][b]["shape"])
            sample.append((b, rng.randrange(no)))
        v, tt, mm = validate_masks_superset(ir, sample, rng)
        mask_viol_total += v
        mask_truth_total += tt
        mask_marked_total += mm

        for _ in range(TRIALS_PER_INST):
            bay_id = rng.randrange(ir.n_bays)
            W, H = ir.bay_w[bay_id], ir.bay_h[bay_id]
            anchor_x = rng.randrange(W)
            anchor_y = rng.randrange(H)
            spread = rng.choice([2, 4, 8])

            # 기존 K개 + 새 블록 1개: 모두 '서로 다른 block_id'.
            # (중복 id 면 check_collisions/check_exit 가 id 로 자타를 구분 못 해
            #  하니스가 오판한다 -- 엔진이 아니라 검증 코드의 함정.)
            K = rng.randint(1, 4)
            ids = rng.sample(range(nblk), min(K + 1, nblk))
            new_id = ids[-1]
            placed = []   # (bid, orient, px, py)
            for bid in ids[:-1]:
                no = len(prob["blocks"][bid]["shape"])
                orient = rng.randrange(no)
                lo_x, hi_x, lo_y, hi_y = ifp_range(ir, bay_id, bid, orient)
                px = rand_pos_near(rng, lo_x, hi_x, anchor_x, spread)
                py = rand_pos_near(rng, lo_y, hi_y, anchor_y, spread)
                if px is None or py is None:
                    continue
                placed.append((bid, orient, px, py))
            if not placed:
                continue

            bay = Bay(W, H, bay_id)
            placed_blocks = [Block(bid, prob["blocks"][bid], px, py, orient)
                             for (bid, orient, px, py) in placed]

            # 기존 점유 누적
            occ_all = re.BayOccupancy(W, H, ir.max_layers)
            for (bid, orient, px, py) in placed:
                occ_all.add(ir.masks(bid, orient), px, py)

            # ---- ENTRY: 새 블록을 여러 위치에 ----
            nbid = new_id
            nno = len(prob["blocks"][nbid]["shape"])
            norient = rng.randrange(nno)
            lo_x, hi_x, lo_y, hi_y = ifp_range(ir, bay_id, nbid, norient)
            for _ in range(POS_PER_TRIAL):
                px = rand_pos_near(rng, lo_x, hi_x, anchor_x, spread)
                py = rand_pos_near(rng, lo_y, hi_y, anchor_y, spread)
                if px is None or py is None:
                    continue
                rv = re.entry_feasible(ir, occ_all, bay_id, nbid, norient, px, py)
                newb = Block(nbid, prob["blocks"][nbid], px, py, norient)
                sv = (len(check_entry(bay, placed_blocks, newb, fast=True)) == 0)
                cell = tally["entry"]
                if rv and sv:
                    cell["agree_T"] += 1
                elif (not rv) and (not sv):
                    cell["agree_F"] += 1
                elif (not rv) and sv:
                    cell["cons_loss"] += 1
                else:  # rv and not sv -> 비보수 위반
                    cell["VIOL"] += 1
                    if len(viol_examples) < 10:
                        viol_examples.append(("entry", name, bay_id, nbid, norient, px, py))

            # ---- EXIT & COLLISION: 군집 안의 한 블록을 대상으로 ----
            # 모든 블록 공존 가정. 대상 = placed 중 하나.
            ti = rng.randrange(len(placed))
            tbid, torient, tpx, tpy = placed[ti]
            others = [p for i, p in enumerate(placed) if i != ti]
            occ_others = re.BayOccupancy(W, H, ir.max_layers)
            for (bid, orient, px, py) in others:
                occ_others.add(ir.masks(bid, orient), px, py)
            target_block = placed_blocks[ti]

            # EXIT
            rv = re.exit_feasible(ir, occ_others, bay_id, tbid, torient, tpx, tpy)
            sv = (len(check_exit(bay, placed_blocks, target_block, fast=True)) == 0)
            cell = tally["exit"]
            if rv and sv:
                cell["agree_T"] += 1
            elif (not rv) and (not sv):
                cell["agree_F"] += 1
            elif (not rv) and sv:
                cell["cons_loss"] += 1
            else:
                cell["VIOL"] += 1
                if len(viol_examples) < 10:
                    viol_examples.append(("exit", name, bay_id, tbid, torient, tpx, tpy))

            # COLLISION (stage 4, same layer): 대상 vs others
            rv = re.no_collision(ir, occ_others, bay_id, tbid, torient, tpx, tpy)
            cols = check_collisions(bay, placed_blocks)
            sv = not any(c.block_a.block_id == tbid or c.block_b.block_id == tbid
                         for c in cols)
            cell = tally["coll"]
            if rv and sv:
                cell["agree_T"] += 1
            elif (not rv) and (not sv):
                cell["agree_F"] += 1
            elif (not rv) and sv:
                cell["cons_loss"] += 1
            else:
                cell["VIOL"] += 1
                if len(viol_examples) < 10:
                    viol_examples.append(("coll", name, bay_id, tbid, torient, tpx, tpy))

    # ---- 결과 ----
    print("=" * 72)
    print("P2 일치 검증  (40 인스턴스, seed=%d)" % SEED)
    print("=" * 72)
    hdr = f"{'check':6} {'agree_T':>9} {'agree_F':>9} {'cons_loss':>10} {'VIOL':>6} {'total':>8}"
    print(hdr)
    total_viol = 0
    for k in ("entry", "exit", "coll"):
        c = tally[k]
        tot = c["agree_T"] + c["agree_F"] + c["cons_loss"] + c["VIOL"]
        total_viol += c["VIOL"]
        print(f"{k:6} {c['agree_T']:9} {c['agree_F']:9} {c['cons_loss']:10} "
              f"{c['VIOL']:6} {tot:8}")
    print("-" * 72)
    print(f"마스크 superset 검증: 누락(진리셀인데 마스크 0) = {mask_viol_total}  "
          f"진리셀 {mask_truth_total}  마스크셀 {mask_marked_total}  "
          f"(over-mark x{mask_marked_total/max(1,mask_truth_total):.2f})")
    if viol_examples:
        print("VIOLATION 예시:", viol_examples)
    print("=" * 72)
    ok = (total_viol == 0 and mask_viol_total == 0)
    print("판정:", "PASS (비보수 불일치 0)" if ok else "FAIL")
    return ok


def bench():
    """배치 1회 feasibility 판정: utils.check_entry vs 래스터 질의 속도.

    현실 시나리오(BLF 위치 스캔): 한 베이 상태(기존 N블록)를 고정하고 새 블록을 M개
    후보 위치에 시험. baseline 은 위치마다 check_entry 재호출(매번 Shapely), 래스터는
    occ 한 번 세우고 위치마다 비트 AND.
    """
    print("\n" + "=" * 72)
    print("속도 벤치: 배치 1회 entry 판정 (warm = occ 유지)")
    print("=" * 72)
    rng = random.Random(SEED + 1)
    # 중간 크기 인스턴스 몇 개
    paths = INSTANCES[::8]
    sh_total = 0.0
    rs_total = 0.0
    nq = 0
    for path in paths:
        prob = json.load(open(path))
        ir = re.InstanceRaster(prob)
        nblk = len(prob["blocks"])
        bay_id = 0
        W, H = ir.bay_w[0], ir.bay_h[0]
        bay = Bay(W, H, 0)
        # 기존 N블록 군집
        N = min(20, nblk // 4)
        placed, placed_blocks = [], []
        ax, ay = W // 2, H // 2
        for _ in range(N):
            bid = rng.randrange(nblk)
            orient = 0
            lo_x, hi_x, lo_y, hi_y = ifp_range(ir, bay_id, bid, orient)
            px = rand_pos_near(rng, lo_x, hi_x, ax, max(2, W // 3))
            py = rand_pos_near(rng, lo_y, hi_y, ay, max(2, H // 3))
            if px is None or py is None:
                continue
            placed.append((bid, orient, px, py))
            placed_blocks.append(Block(bid, prob["blocks"][bid], px, py, orient))
        # 후보 위치 M개 (새 블록 1개)
        nbid = rng.randrange(nblk)
        norient = 0
        lo_x, hi_x, lo_y, hi_y = ifp_range(ir, bay_id, nbid, norient)
        cand = []
        for _ in range(200):
            px = rng.randint(lo_x, max(lo_x, hi_x))
            py = rng.randint(lo_y, max(lo_y, hi_y))
            cand.append((px, py))

        # 마스크/occ 워밍업(전처리는 시간에서 제외 -- 인스턴스당 1회, 캐시됨)
        ir.masks(nbid, norient)
        occ = re.BayOccupancy(W, H, ir.max_layers)
        for (bid, orient, px, py) in placed:
            ir.masks(bid, orient)
            occ.add(ir.masks(bid, orient), px, py)
        occ.upper()

        # Shapely
        t0 = time.perf_counter()
        for (px, py) in cand:
            nb = Block(nbid, prob["blocks"][nbid], px, py, norient)
            check_entry(bay, placed_blocks, nb, fast=True)
        sh = time.perf_counter() - t0

        # Raster
        t0 = time.perf_counter()
        for (px, py) in cand:
            re.entry_feasible(ir, occ, bay_id, nbid, norient, px, py)
        rs = time.perf_counter() - t0

        sh_total += sh
        rs_total += rs
        nq += len(cand)
        print(f"{prob['name']:9} N={len(placed):3} M={len(cand):3}  "
              f"shapely={sh*1e3:8.2f}ms  raster={rs*1e3:8.3f}ms  "
              f"x{sh/max(1e-9,rs):8.1f}")
    print("-" * 72)
    print(f"합계  shapely={sh_total*1e3:.1f}ms  raster={rs_total*1e3:.1f}ms  "
          f"질의 {nq}건  평균 가속 x{sh_total/max(1e-9,rs_total):.1f}")
    print(f"질의당: shapely={sh_total/nq*1e6:.1f}us  raster={rs_total/nq*1e6:.2f}us")
    print("=" * 72)
    return sh_total / max(1e-9, rs_total)


if __name__ == "__main__":
    ok = run()
    speedup = bench()
    print(f"\n최종: 일치={'PASS' if ok else 'FAIL'}  속도=x{speedup:.0f}  "
          f"(목표 100x {'달성' if speedup >= 100 else '미달'})")
    sys.exit(0 if ok else 1)
