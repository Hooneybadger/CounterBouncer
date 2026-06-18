# constructor.py
# =============================================================================
# P3 -- 강한 공존 구성기 (STRATEGY_PLAN B3 / P3)
#
# 설계 의도와 육하원칙은 docs/features/03-coexistence-constructor.md 에 있다.
# 한 줄 요약: P1 안전망은 베이를 '한 번에 한 블록'으로 직렬화해 지각이 폭발한다.
# 이 구성기는 같은 베이에 여러 블록을 '동시에' 패킹해 블록을 release 즈음에 일찍
# 넣는다 -- w1(지각)이 압도적이므로 이것이 obj의 거의 전부다.
#
# 핵심 불변식 (만들 때부터 feasible):
#   한 블록 X를 (베이,방향,위치,[entry,exit))에 넣을 때, 이미 놓인 블록 C 전부에
#   대해 '양방향' 크레인 검사를 한다 --
#     (1) forward : X가 들어오고 나갈 때, 그 순간 베이에 있는 블록들이 X의 크레인
#         경로(j>=k)를 막지 않아야 한다.
#     (2) reverse : X가 베이에 있는 동안 들어오거나 나가는 C가, 새로 생긴 X 때문에
#         크레인 경로가 막히지 않아야 한다.
#   크레인/충돌 판정은 블록 쌍마다 독립이고(check_entry/exit/collisions가 ANY로
#   판정), 우리는 placed 블록을 절대 옮기지 않으므로, 매 삽입에서 겹치는 모든 C와
#   양방향을 보면 최종 해는 stage 2/3/4를 전부 통과한다. baseline이 단방향만 봐서
#   생기던 '소급 막힘(repair 실패)'을 reverse 검사가 구조적으로 제거한다.
#
# 완결성 (fallback이 따로 필요 없는 이유):
#   후보 entry 시각 집합은 {release} ∪ {겹칠 수 있는 exit들}이고 오름차순으로 본다.
#   베이가 X의 체류구간 동안 완전히 비는 시각([빈-베이 윈도우], P1과 동일)은 이 집합의
#   원소이고, 그 시각엔 공존 블록이 없어 X가 자명히 feasible하다. 따라서 탐색은 늦어도
#   그 시각엔 반드시 자리를 찾는다 -- 즉 P1의 보장이 이 탐색의 '최악의 경우'로 포함된다.
#
# 최종 안전망:
#   그래도 구성기 전체 출력은 myalgorithm.py가 utils.check_feasibility로 1회 중재하고,
#   혹시라도 통과하지 못하면 P1 guaranteed 해로 되돌린다. -1은 어떤 경우에도 없다.
# =============================================================================

from __future__ import annotations

import math
import time

try:  # flat layout: evaluation server / batch_runner
    from utils import Bay
    from baseline_greedy import _empty_bay_entry, _block_bbox, _build_operations
    from raster_engine import (
        InstanceRaster, BayOccupancy, entry_feasible, exit_feasible,
        feasible_positions,
    )
except ImportError:  # IDE package layout
    from ogc2026.baseline.utils import Bay
    from ogc2026.baseline.baseline_greedy import (
        _empty_bay_entry, _block_bbox, _build_operations,
    )
    from ogc2026.src.raster_engine import (
        InstanceRaster, BayOccupancy, entry_feasible, exit_feasible,
        feasible_positions,
    )

_EPS = 1e-6


# -----------------------------------------------------------------------------
# 정적 메타 -- (block, orient)별 reference-상대 bbox, 캐시
# -----------------------------------------------------------------------------

def _rel_bbox(ir: InstanceRaster, bid: int, orient: int):
    """방향의 로컬 bbox를 reference point(layers[0][0]) 기준으로 옮긴 (x0,y0,x1,y1).

    reference를 월드 (px,py)에 놓으면 월드 bbox = (px+x0, py+y0, px+x1, py+y1).
    fits/anchor 계산이 모두 이 상대 bbox 위에서 돈다(raster_engine 의 위치 산식과 동일).
    """
    bb = ir.local_bbox(bid, orient)
    rx, ry = ir._ref(bid, orient)
    return (bb[0] - rx, bb[1] - ry, bb[2] - rx, bb[3] - ry)


# -----------------------------------------------------------------------------
# 베이 점유 누적기 빌드 -- 주어진 committed 레코드들의 footprint OR
# -----------------------------------------------------------------------------

def _occ_of(ir: InstanceRaster, W: int, H: int, records: list) -> BayOccupancy:
    """records(committed 레코드 리스트)의 레이어별 점유를 한 BayOccupancy로 OR-누적."""
    occ = BayOccupancy(W, H, ir.max_layers)
    for c in records:
        occ.add(c["masks"], c["px"], c["py"])
    return occ


# -----------------------------------------------------------------------------
# 후보 위치 생성 -- BLF(bottom-left fill) 앵커
# -----------------------------------------------------------------------------

def _blf_candidates(rel, W: int, H: int, anchors: list):
    """reference-point 후보 (px,py) 목록. 베이 좌하단 + 각 앵커 블록의 우/상단 모서리.

    rel = X의 reference-상대 bbox. anchors = 공존 가능한 committed 블록들의 월드 bbox.
    bottom-left 우선이 되도록 (px,py) 오름차순 정렬해 돌려준다 -- 호출부가 첫 feasible을
    취하면 그게 가장 바닥-왼쪽 자리다.
    """
    x0, y0, x1, y1 = rel
    xs = {max(0, math.ceil(-x0))}
    ys = {max(0, math.ceil(-y0))}
    for (wx0, wy0, wx1, wy1) in anchors:
        xs.add(math.ceil(wx1 - x0))  # X 왼쪽 모서리(px+x0)를 앵커 오른쪽(wx1)에 붙임
        ys.add(math.ceil(wy1 - y0))  # X 아래 모서리(py+y0)를 앵커 위(wy1)에 붙임
    out = []
    for px in sorted(xs):
        if px < 0 or px + x1 > W + _EPS or px + x0 < -_EPS:
            continue
        for py in sorted(ys):
            if py < 0 or py + y1 > H + _EPS or py + y0 < -_EPS:
                continue
            out.append((px, py))
    out.sort(key=lambda p: (p[0], p[1]))
    return out


# -----------------------------------------------------------------------------
# 한 베이에서 블록 X의 '가장 빠른 entry + 그때의 최선 위치'를 찾는다
# -----------------------------------------------------------------------------

def _best_in_bay(ir: InstanceRaster, bay_id: int, committed: list,
                 bid: int, r_time: int, proc: int, cand: str = "blf"):
    """반환: (entry, px, py, orient, top_y) 또는 None.

    후보 entry 시각을 오름차순으로 보고, 어떤 시각이든 하나라도 feasible한 위치가
    나오면 그 시각이 이 베이의 '가장 빠른 entry'다(지각 = max(0, entry+proc-due)가
    entry에 단조이므로 최적). 그 시각의 여러 방향 중 top_y(상단 모서리)가 가장 낮은
    -- 가장 빽빽한 -- 자리를 고른다.

    cand -- 위치 후보 생성. "blf"는 코너 앵커(빠름), "scan"은 래스터 전 위치 스캔
    (`feasible_positions`)으로 오버행 아래 [temporal nesting] 자리까지 포함(느림).
    """
    W = ir.bay_w[bay_id]
    H = ir.bay_h[bay_id]
    n_orient = len(ir.blocks[bid]["shape"])
    R = W                      # occ 행 stride(=베이 너비). int_for_R(R)에 쓴다.
    R_nlayers = ir.max_layers  # occ 레이어 수(상부맵 길이). k>=R_nlayers 마스크는 무시.

    # 후보 entry: release, 그리고 release 이후에 끝나는 committed exit들.
    cand_t = {r_time}
    for c in committed:
        if c["exit"] > r_time:
            cand_t.add(c["exit"])
    cand_t = sorted(cand_t)

    for t in cand_t:
        te = t + proc

        # 이 윈도우 [t, te)와 시간상 겹치는 committed (앵커 + 검사 대상)
        overlap = [c for c in committed if c["entry"] < te and t < c["exit"]]

        # forward: X의 entry/exit 순간에 '존재하는' 블록 (동시각은 보수적으로 포함)
        present_entry = [c for c in overlap
                         if (c["entry"] < t < c["exit"]) or c["entry"] == t]
        present_exit = [c for c in overlap
                        if (c["entry"] < te < c["exit"]) or c["exit"] == te]
        # reverse: X가 있는 동안 entry/exit 하는 C (동시각 포함) -- C의 크레인 vs X
        reverse = [c for c in overlap
                   if (t < c["entry"] < te) or c["entry"] == t
                   or (t < c["exit"] < te) or c["exit"] == te]

        occ_entry = _occ_of(ir, W, H, present_entry)
        occ_exit = _occ_of(ir, W, H, present_exit)

        anchors = [c["wbb"] for c in overlap]

        # entry/exit 크레인 상부맵을 t당 한 번 고정(위치 무관). occ.R == W(스트라이드).
        up_e = occ_entry.upper()
        up_x = occ_exit.upper()

        best = None  # (top_y, px, py, orient)
        for orient in range(n_orient):
            rel = _rel_bbox(ir, bid, orient)
            r0, r1, r2, r3 = rel
            if cand == "scan":
                # 전 위치 스캔: entry 크레인까지 통과한 모든 (px,py). 오버행 아래
                # nesting 자리를 포함한다. 바닥 우선(py,px)으로 정렬해 가장 빽빽한
                # 자리를 먼저 본다.
                cands = sorted(feasible_positions(ir, occ_entry, bay_id, bid, orient),
                               key=lambda p: (p[1], p[0]))
            else:
                cands = _blf_candidates(rel, W, H, anchors)

            # 위치 무관 stamp: (layer 마스크 정수, 오프셋, k). int_for_R(R)·my0·mx0은
            # (bid,orient,layer)에만 의존하므로 위치 루프 밖에서 한 번 계산한다.
            # entry/exit 검사를 entry_feasible/exit_feasible 인라인으로 동일 비트연산.
            masks = ir.masks(bid, orient)
            stamp = []
            for k, lm in enumerate(masks):
                if lm.empty or k >= R_nlayers:
                    continue
                stamp.append((lm.int_for_R(R), lm.my0 * R + lm.mx0, k))

            for (px, py) in cands:
                # forward 경계(fits_in_bay 정확 복제): rel+px/py 가 [0,W]·[0,H] 안.
                if not (r0 + px >= 0 and r1 + py >= 0
                        and r2 + px <= W and r3 + py <= H):
                    continue
                base = py * R + px
                # entry 크레인(occ_entry 상부맵 vs X layer k): j>=k 막힘이면 skip.
                blk = False
                for (bint, off, k) in stamp:
                    if (bint << (base + off)) & up_e[k]:
                        blk = True
                        break
                if blk:
                    continue
                # exit 크레인(occ_exit 상부맵)
                blk = False
                for (bint, off, k) in stamp:
                    if (bint << (base + off)) & up_x[k]:
                        blk = True
                        break
                if blk:
                    continue
                # reverse: 새 X가 C들의 크레인 경로를 막지 않는가(변경 없음)
                if reverse:
                    occ_x = BayOccupancy(W, H, ir.max_layers)
                    occ_x.add(masks, px, py)
                    blocked = False
                    for c in reverse:
                        if occ_x._crane_blocked(c["masks"], c["px"], c["py"]):
                            blocked = True
                            break
                    if blocked:
                        continue
                top_y = py + r3
                if best is None or top_y < best[0]:
                    best = (top_y, px, py, orient)
                break  # BLF: 이 방향의 첫(=가장 바닥-왼쪽) feasible 위치면 충분
        if best is not None:
            return (t, best[1], best[2], best[3], best[0])
    return None


# -----------------------------------------------------------------------------
# 메인 구성기
# -----------------------------------------------------------------------------

def _placement_cost(w1, w2, w3, bay_weights, bay_loads,
                    bay_id, tardiness, workload, pref_pen, top_y):
    """베이 선택 비교용 비용(낮을수록 좋음). baseline _placement_score 와 동형:
    w1*지각 + w2*부하불균형근사 + w3*선호페널티 + 미세 packing tiebreak."""
    new_load = bay_loads[bay_id] + workload
    new_obj2 = max(
        (abs(bay_weights[bay_id] * new_load - bay_weights[j] * bay_loads[j])
         for j in range(len(bay_loads)) if j != bay_id),
        default=0.0,
    )
    return w1 * tardiness + w2 * new_obj2 + w3 * pref_pen + 1e-4 * top_y


# -----------------------------------------------------------------------------
# area-완화 추정 -- regret 순서 결정용 (값싼 하한, 기하 없음)
# -----------------------------------------------------------------------------
#
# ⚠ [실험·기각 — production 미사용] 아래 area-완화 추정과 _construct_regret(동적 regret-2
# 순서)는 측정에서 EDD에 전패해 채택하지 않은 경로다(기각 근거: docs/features/04-insertion-
# order-portfolio.md, GLOSSARY "regret-k 삽입"). construct(order="regret2")로만 도달하는데
# 실제 파이프라인(myalgorithm)은 "edd"/"edd_area"만 쓴다. 참고·재현용으로 남겨 둔다.
# 예외: _block_area는 _static_order의 "edd_area" tie-break이 실제로 쓰므로 production 라이브.
#
# 정확한 "가장 빠른 entry"는 기하 탐색이 필요해 비싸다(_best_in_bay). regret은 N개
# 미배치 블록을 매 스텝 평가해야 하므로(O(N^2)) 그 비싼 탐색을 못 쓴다. 대신 베이를
# '시간에 따른 점유 면적' 1차원 저수지로 보고, 블록이 들어갈 면적이 빌 때를 추정한다 --
# 이는 진짜 entry의 하한(면적은 충돌의 필요조건)이라 순서 proxy로 충분하고, 기하 없이
# O(세그먼트)로 빠르다. 최종 배치는 여전히 full 기하 탐색(_place_block)이 한다.

def _block_area(ir: InstanceRaster, bid: int) -> float:
    """블록의 면적 proxy -- 방향별 bbox 면적의 최솟값(가장 빽빽한 방향)."""
    best = None
    for orient in range(len(ir.blocks[bid]["shape"])):
        bb = ir.local_bbox(bid, orient)
        a = (bb[2] - bb[0]) * (bb[3] - bb[1])
        if best is None or a < best:
            best = a
    return best if best is not None else 0.0


def _bay_area_steps(area_iv: list):
    """committed (entry,exit,area) 목록에서 점유면적 계단함수를 만든다.

    반환 (bt, seg): bt[k]는 정렬된 분기점, seg[k]는 [bt[k], bt[k+1]) 구간의 총 점유면적.
    bt[0] 이전과 bt[-1] 이후는 면적 0.
    """
    if not area_iv:
        return ([], [])
    deltas: dict = {}
    for (e, x, a) in area_iv:
        deltas[e] = deltas.get(e, 0.0) + a
        deltas[x] = deltas.get(x, 0.0) - a
    bt = sorted(deltas)
    seg = []
    cur = 0.0
    for t in bt:
        cur += deltas[t]
        seg.append(cur)
    return (bt, seg)


def _area_earliest_step(bt: list, seg: list, release: int, proc: int,
                        thresh: float):
    """면적 임계 thresh 아래로 [t, t+proc) 전체가 유지되는 가장 빠른 t>=release.

    면적이 임계를 넘는 '금지 구간'을 만나면 그 구간 끝으로 윈도우를 민다(t는 전진만).
    thresh<0(블록이 베이보다 큼)이면 None.
    """
    if thresh < 0:
        return None
    t = float(release)
    m = len(bt)
    if m == 0:
        return t
    moved = True
    while moved:
        moved = False
        te = t + proc
        for k in range(m):
            seg_e = bt[k + 1] if k + 1 < m else float("inf")
            if seg_e <= t:
                continue                 # 세그먼트가 윈도우 이전
            if bt[k] >= te:
                break                    # 세그먼트가 윈도우 이후 -> 통과
            if seg[k] > thresh:          # 금지 세그먼트가 윈도우와 겹침
                t = seg_e
                moved = True
                break
    return t


def _construct_regret(ir, blocks_data, bays_data, bay_areas, bay_weights,
                      committed, bay_loads, w1, w2, w3, deadline, cand="blf"):
    """area-완화 추정 위의 동적 regret-2 순서로 블록을 배치한다.

    매 스텝, 미배치 블록마다 '베이별 값싼 비용'(area 추정 지각 + 선호)을 보고 regret =
    (2등 비용 − 1등 비용)이 가장 큰 블록 -- 좋은 자리를 놓치면 가장 손해인 블록 -- 을
    골라 full 기하 탐색으로 배치한다. 배치한 베이의 면적 프로파일만 갱신하므로
    재평가가 그 베이 열에 한정돼 O(N^2/n_bays)로 떨어진다. w1이 압도적이라 값싼 비용에
    obj2는 빼고(전 베이 재계산 회피) w1·지각 + w3·선호만 쓴다 -- 최종 비용은 _place_block
    이 obj2까지 정확히 본다.
    """
    n = len(blocks_data)
    n_bays = len(bays_data)
    block_area = [_block_area(ir, i) for i in range(n)]
    rel_t = [int(b["release_time"]) for b in blocks_data]
    proc_t = [int(b["processing_time"]) for b in blocks_data]
    due_t = [b["due_date"] for b in blocks_data]
    prefs_t = [b.get("bay_preferences", [0.0] * n_bays) for b in blocks_data]
    smax_t = [max(p) if p else 0.0 for p in prefs_t]

    area_iv = [[] for _ in range(n_bays)]
    steps = [([], []) for _ in range(n_bays)]

    def cheap(i, bay):
        thresh = bay_areas[bay] - block_area[i]
        bt, seg = steps[bay]
        t_est = _area_earliest_step(bt, seg, rel_t[i], proc_t[i], thresh)
        if t_est is None:
            return None
        tard = max(0.0, t_est + proc_t[i] - due_t[i])
        pref_pen = smax_t[i] - (prefs_t[i][bay] if bay < len(prefs_t[i]) else 0.0)
        return w1 * tard + w3 * pref_pen

    rows = {i: [cheap(i, b) for b in range(n_bays)] for i in range(n)}
    unplaced = set(range(n))
    assignments = []

    def regret_key(i):
        finite = sorted(c for c in rows[i] if c is not None)
        if not finite:
            reg = -1.0                    # 어느 베이에도 면적상 안 맞음(드묾)
        elif len(finite) == 1:
            reg = float("inf")            # 갈 곳이 하나뿐 -> 최우선
        else:
            reg = finite[1] - finite[0]   # regret-2
        return (reg, -due_t[i], -proc_t[i])  # 동률은 EDD/SPT로 결정적 tie-break

    while unplaced:
        if time.time() > deadline:
            for bi in sorted(unplaced, key=lambda i: (due_t[i], proc_t[i])):
                _, _, _, asgn = _place_block(ir, bi, blocks_data, bays_data,
                    committed, bay_loads, bay_weights, w1, w2, w3, True, cand)
                assignments.append(asgn)
            break
        bi = max(unplaced, key=regret_key)
        bay_id, entry, exit_t, asgn = _place_block(
            ir, bi, blocks_data, bays_data, committed, bay_loads,
            bay_weights, w1, w2, w3, False, cand)
        assignments.append(asgn)
        unplaced.discard(bi)
        area_iv[bay_id].append((entry, exit_t, block_area[bi]))
        steps[bay_id] = _bay_area_steps(area_iv[bay_id])
        for i in unplaced:
            rows[i][bay_id] = cheap(i, bay_id)
    return assignments


def _place_block(ir, bi, blocks_data, bays_data, committed, bay_loads,
                 bay_weights, w1, w2, w3, out_of_time, cand="blf"):
    """블록 bi를 모든 베이에서 full 기하 탐색해 가장 싼 자리에 커밋한다.

    feasible 자리가 없거나 시간이 초과되면 빈-베이 윈도우로 보장 배치한다. 상태
    (committed·bay_loads)를 제자리에서 갱신하고, (bay_id, entry, exit, assignment)를
    돌려준다 -- regret 경로가 area 프로파일을 갱신하는 데 entry/exit가 쓰인다.
    """
    blk = blocks_data[bi]
    r_time = int(blk["release_time"])
    proc = int(blk["processing_time"])
    due = blk["due_date"]
    workload = blk["workload"]
    n_bays = len(bays_data)
    prefs = blk.get("bay_preferences", [0.0] * n_bays)
    s_max = max(prefs) if prefs else 0.0

    chosen = None  # (cost, bay_id, px, py, orient, entry, exit)
    if not out_of_time:
        for bay_id in range(n_bays):
            res = _best_in_bay(ir, bay_id, committed[bay_id], bi, r_time, proc, cand)
            if res is None:
                continue
            entry, px, py, orient, top_y = res
            exit_t = entry + proc
            tardiness = max(0.0, exit_t - due)
            pref_pen = s_max - (prefs[bay_id] if bay_id < len(prefs) else 0.0)
            cost = _placement_cost(w1, w2, w3, bay_weights, bay_loads,
                                   bay_id, tardiness, workload, pref_pen, top_y)
            if chosen is None or cost < chosen[0]:
                chosen = (cost, bay_id, px, py, orient, entry, exit_t)

    if chosen is None:
        bay_id, px, py, orient, entry, exit_t = _fallback_place(
            ir, blk, bays_data, committed, prefs, r_time, proc)
    else:
        _, bay_id, px, py, orient, entry, exit_t = chosen

    rel = _rel_bbox(ir, bi, orient)
    committed[bay_id].append({
        "bay": bay_id, "bid": bi, "orient": orient, "px": px, "py": py,
        "entry": entry, "exit": exit_t,
        "masks": ir.masks(bi, orient),
        "wbb": (px + rel[0], py + rel[1], px + rel[2], py + rel[3]),
    })
    bay_loads[bay_id] += workload
    asgn = {
        "block_id": int(bi), "bay_id": int(bay_id),
        "x": int(px), "y": int(py), "orient_idx": int(orient),
        "entry_time": int(entry), "exit_time": int(exit_t),
    }
    return bay_id, entry, exit_t, asgn


def _static_order(blocks_data, ir, mode: str):
    """삽입 순서를 정적으로 정한다(블록 인덱스 리스트)."""
    n = len(blocks_data)
    if mode == "edd_area":   # 같은 납기면 면적 큰(=배치 어려운) 블록 먼저
        return sorted(range(n), key=lambda i: (blocks_data[i]["due_date"],
                                               -_block_area(ir, i)))
    if mode == "slack":      # 여유(slack) 적은 블록 먼저, 동률은 납기
        return sorted(range(n), key=lambda i: (
            blocks_data[i]["due_date"] - blocks_data[i]["release_time"]
            - blocks_data[i]["processing_time"], blocks_data[i]["due_date"]))
    # 기본 EDD (동률은 SPT)
    return sorted(range(n), key=lambda i: (blocks_data[i]["due_date"],
                                           blocks_data[i]["processing_time"]))


def construct(prob_info: dict, t_start: float, timelimit: float,
              ir: InstanceRaster | None = None, order: str = "edd",
              cand: str = "blf", return_state: bool = False):
    """공존 패킹 구성기. 완전한 feasible 해(operations dict)를 만들어 돌려준다.

    feasibility는 만들 때부터(양방향 크레인 검사 + 빈-베이 윈도우 최악경우 포함)
    보장된다. 시간 가드: timelimit*0.80을 넘기면 남은 블록을 빠르게 마감해 항상
    완전한 해를 반환한다.

    order -- 삽입 순서 전략. "edd"(기본)·"edd_area"·"slack"은 정적 정렬,
    "regret2"는 area-완화 추정 위의 동적 regret-2(`_construct_regret`).
    """
    if ir is None:
        ir = InstanceRaster(prob_info)

    bays_data = prob_info["bays"]
    blocks_data = prob_info["blocks"]
    n_bays = len(bays_data)
    weights = prob_info.get("weights", {})
    w1 = weights.get("w1", 1.0)
    w2 = weights.get("w2", 1.0)
    w3 = weights.get("w3", 1.0)

    bay_areas = [bays_data[j]["width"] * bays_data[j]["height"] for j in range(n_bays)]
    avg_area = sum(bay_areas) / n_bays
    bay_weights = [avg_area / a for a in bay_areas]
    bay_loads = [0.0] * n_bays

    committed: list[list] = [[] for _ in range(n_bays)]

    # 내부 탐색 마감을 0.80*timelimit로 잡는다. 남는 0.20은 myalgorithm.py가 반환 직전
    # 돌리는 check_feasibility(floor·candidate 2회) 비용까지 0.93*timelimit 안에 들도록
    # 한 예산이다(짧은 제한시간에서 시간 초과를 구조적으로 막음). 큰 인스턴스의 검증이
    # ~1초라 큰 베이가 많은 prob_40(300블록·5베이)에서도 여유가 남는다.
    deadline = t_start + timelimit * 0.80

    if order == "regret2":
        assignments = _construct_regret(
            ir, blocks_data, bays_data, bay_areas, bay_weights,
            committed, bay_loads, w1, w2, w3, deadline, cand)
    else:
        seq = _static_order(blocks_data, ir, order)
        assignments = []
        for bi in seq:
            _, _, _, asgn = _place_block(
                ir, bi, blocks_data, bays_data, committed, bay_loads,
                bay_weights, w1, w2, w3, time.time() > deadline, cand)
            assignments.append(asgn)

    if return_state:
        # ALNS(P4)가 destroy/repair로 개선할 수 있게 가변 상태를 그대로 돌려준다.
        return committed, bay_loads, bay_weights
    return {"operations": _build_operations(assignments)}


def operations_from_committed(committed):
    """committed 상태(베이별 레코드)를 제출 형식 operations 딕트로 변환."""
    assignments = [{
        "block_id": int(r["bid"]), "bay_id": int(r["bay"]),
        "x": int(r["px"]), "y": int(r["py"]), "orient_idx": int(r["orient"]),
        "entry_time": int(r["entry"]), "exit_time": int(r["exit"]),
    } for bay in committed for r in bay]
    return {"operations": _build_operations(assignments)}


def solution_obj(committed, blocks_data, bay_weights, bay_loads, w1, w2, w3):
    """committed 상태의 가중 목적값. utils.check_feasibility의 obj 계산을 정확히 복제한다
    (ALNS가 판정기와 다른 obj를 최적화하지 않도록). feasibility는 구성에서 보장되므로
    여기선 obj만 빠르게 센다."""
    n_bays = len(bay_loads)
    obj1 = 0.0
    obj3 = 0.0
    for bay in committed:
        for r in bay:
            bd = blocks_data[r["bid"]]
            obj1 += max(0.0, r["exit"] - bd["due_date"])
            prefs = bd.get("bay_preferences")
            if prefs:
                obj3 += max(prefs) - prefs[r["bay"]]
    if n_bays >= 2:
        obj2 = math.floor(max(
            abs(bay_weights[a] * bay_loads[a] - bay_weights[b] * bay_loads[b])
            for a in range(n_bays) for b in range(n_bays) if a != b))
    else:
        obj2 = 0.0
    return w1 * obj1 + w2 * obj2 + w3 * obj3


def loads_from_committed(committed, blocks_data, n_bays):
    """committed 레코드에서 베이별 workload 합을 다시 센다.

    ALNS는 bay_loads를 in-place로 변형하다 끝나므로 반환한 best snapshot과 어긋나 있다.
    polish에 넘기기 전 snapshot 기준으로 재계산한다."""
    loads = [0.0] * n_bays
    for bay in range(n_bays):
        for r in committed[bay]:
            loads[bay] += blocks_data[r["bid"]]["workload"]
    return loads


# -----------------------------------------------------------------------------
# 선호 재배치 polish -- obj3를 겨냥하는 결정적 국소탐색 (P4b / STRATEGY #12)
# -----------------------------------------------------------------------------
#
# 왜: obj1=0 인스턴스 18/40에서 선호 페널티(obj3)가 목적의 거의 전부지만(w3가 obj2의
# ~20배), ALNS의 destroy 연산자는 tardiness만 겨냥해(`destroy_worst`) 잘못 앉은 블록을
# 못 건드린다. 균일가중 destroy_pref를 ALNS에 섞어 봤더니 RNG 궤적 전체가 흔들려 rank가
# 67->62로 퇴보하는 고분산 wash였다(features/09 Alternatives에 측정 기록). 그래서 ALNS는
# 그대로 두고, 그 best snapshot 위에서 '엄밀 개선만 수락하는' 결정적 패스를 따로 돌린다.
#
# 무엇: 선호 페널티가 있는 블록을 더 선호하는 베이로 옮겨 본다. solution_obj(판정기 obj
# 정확 복제)가 strictly 줄 때만 이동을 확정하고 아니면 원복하므로, 입력 incumbent를 절대
# 나빠지게 하지 않는다 -- 무회귀가 구조적으로 보장된다(분산 0). feasibility는 _best_in_bay
# 의 양방향 크레인 검사가 보장하고, src에서 빼는 것은 제약을 풀기만 해 항상 feasible이다.

def pref_polish(ir, prob_info, committed, bay_loads, bay_weights,
                w1, w2, w3, deadline):
    """선호 페널티 블록을 더 선호하는 베이로 옮겨 obj를 깎는 결정적 hill-climb.

    매 스윕 페널티 큰 블록부터(이득 큰 순) 본다. 더 선호하는 베이마다 _best_in_bay로
    가장 빠른 feasible 자리를 찾아 넣어 보고, 총 obj가 strictly 줄면 그 중 최선을 확정한다.
    더 선호하는 베이로만 옮기므로 그 블록의 obj3는 항상 줄지만, 수락 기준이 '총 obj 엄밀
    감소'라 그 이동으로 obj2(부하 불균형)나 obj1(체류가 밀려 지각)이 더 나빠지면 거절된다 --
    즉 obj3 이득이 obj1/obj2 손해보다 클 때만 옮긴다. 개선이 없는 스윕이면 멈춘다.
    반환: 확정한 이동 횟수.
    """
    blocks_data = prob_info["blocks"]
    n_bays = len(prob_info["bays"])
    cur = solution_obj(committed, blocks_data, bay_weights, bay_loads, w1, w2, w3)
    moves = 0
    improved = True
    while improved and time.time() < deadline:
        improved = False
        # 페널티 큰 블록부터. 이동이 페널티를 바꾸므로 스윕마다 새로 만든다.
        cand_recs = []
        for bay in range(n_bays):
            for r in committed[bay]:
                prefs = blocks_data[r["bid"]].get("bay_preferences")
                if not prefs:
                    continue
                pen = max(prefs) - (prefs[bay] if bay < len(prefs) else 0.0)
                if pen > _EPS:
                    cand_recs.append((pen, bay, r))
        cand_recs.sort(key=lambda t: t[0], reverse=True)

        for _pen, src_bay, r in cand_recs:
            if time.time() >= deadline:
                break
            bid = r["bid"]
            blk = blocks_data[bid]
            prefs = blk["bay_preferences"]
            proc = int(blk["processing_time"])
            r_time = int(blk["release_time"])
            workload = blk["workload"]
            cur_pref = prefs[src_bay] if src_bay < len(prefs) else 0.0
            targets = sorted(
                (b for b in range(n_bays)
                 if b != src_bay and b < len(prefs) and prefs[b] > cur_pref + _EPS),
                key=lambda b: -prefs[b])
            if not targets:
                continue
            # src에서 임시 제거(제약 완화 -- feasible 유지)
            committed[src_bay].remove(r)
            bay_loads[src_bay] -= workload
            best_move = None  # (newobj, tgt, record)
            for tgt in targets:
                res = _best_in_bay(ir, tgt, committed[tgt], bid, r_time, proc, "blf")
                if res is None:
                    continue
                entry, px, py, orient, _top_y = res
                exit_t = entry + proc
                rel = _rel_bbox(ir, bid, orient)
                newr = {
                    "bay": tgt, "bid": bid, "orient": orient, "px": px, "py": py,
                    "entry": entry, "exit": exit_t,
                    "masks": ir.masks(bid, orient),
                    "wbb": (px + rel[0], py + rel[1], px + rel[2], py + rel[3]),
                }
                committed[tgt].append(newr)
                bay_loads[tgt] += workload
                newobj = solution_obj(committed, blocks_data, bay_weights,
                                      bay_loads, w1, w2, w3)
                committed[tgt].remove(newr)
                bay_loads[tgt] -= workload
                if newobj < cur - _EPS and (best_move is None or newobj < best_move[0]):
                    best_move = (newobj, tgt, newr)
            if best_move is not None:
                _, tgt, newr = best_move
                committed[tgt].append(newr)
                bay_loads[tgt] += workload
                cur = best_move[0]
                moves += 1
                improved = True
            else:
                committed[src_bay].append(r)  # 원복
                bay_loads[src_bay] += workload
    return moves


def _place_into(ir, blocks_data, committed, bay_loads, bid, bay):
    """블록 bid를 bay의 가장 빠른 feasible 자리에 넣고 그 레코드를 돌려준다(없으면 None).

    committed[bay]·bay_loads[bay]를 제자리 갱신한다. 입력 상태가 같으면 _best_in_bay가
    결정적이라 같은 자리를 준다 -- swap의 '평가(원복)'와 '확정(재실행)'이 같은 결과를
    내는 근거다. feasibility는 _best_in_bay의 양방향 크레인 검사가 보장한다.
    """
    blk = blocks_data[bid]
    proc = int(blk["processing_time"])
    res = _best_in_bay(ir, bay, committed[bay], bid,
                       int(blk["release_time"]), proc, "blf")
    if res is None:
        return None
    entry, px, py, orient, _top_y = res
    rel = _rel_bbox(ir, bid, orient)
    rec = {
        "bay": bay, "bid": bid, "orient": orient, "px": px, "py": py,
        "entry": entry, "exit": entry + proc,
        "masks": ir.masks(bid, orient),
        "wbb": (px + rel[0], py + rel[1], px + rel[2], py + rel[3]),
    }
    committed[bay].append(rec)
    bay_loads[bay] += blk["workload"]
    return rec


# -----------------------------------------------------------------------------
# 선호 교환(swap) -- polish가 막힌 '선호 베이가 꽉 찬' 경우를 두 블록 맞바꿈으로 푼다
# -----------------------------------------------------------------------------
#
# 왜: pref_polish는 '빈 자리로의 단일 이동'만 한다. 선호 베이가 그 시간대에 꽉 차 있으면
# 옮길 자리가 없어 멈춘다(prob_6·prob_9의 obj3가 그대로인 이유). 두 블록을 맞바꾸면 그 벽을
# 넘는다 -- 선호 페널티가 큰 X(베이 A, B를 원함)를, B에 있던 Y와 교환해 X를 B로 보낸다.
# 역시 엄밀 개선만 수락하므로(무회귀 구조적 보장) X의 obj3 이득이 Y의 손해+obj1/obj2 변화를
# 넘을 때만 바꾼다.

def pref_swap(ir, prob_info, committed, bay_loads, bay_weights,
              w1, w2, w3, deadline, max_cand=6):
    """선호 페널티 블록 X를 더 선호하는 베이 B의 블록 Y와 맞바꾸는 결정적 hill-climb.

    매 스윕 페널티 큰 X부터 본다. X가 더 선호하는 각 베이 B에서, A로 옮겨도 덜 손해인
    순(prefs_Y[B]-prefs_Y[A] 오름차순)으로 Y 후보를 max_cand개만 본다(가득 찬 베이의 전수
    조사 비용을 막는다). 후보마다 X와 Y를 빼고 X->B, Y->A로 _best_in_bay 재배치해 본 뒤
    solution_obj가 strictly 줄면 그 중 최선을 확정한다. 평가는 항상 원복하고, 확정은
    _place_into가 결정적이라 같은 자리를 재현한다. 개선 없는 스윕이면 멈춘다.
    반환: 확정한 교환 횟수.
    """
    blocks_data = prob_info["blocks"]
    n_bays = len(prob_info["bays"])
    cur = solution_obj(committed, blocks_data, bay_weights, bay_loads, w1, w2, w3)
    swaps = 0
    improved = True
    while improved and time.time() < deadline:
        improved = False
        cand_recs = []
        for bay in range(n_bays):
            for r in committed[bay]:
                prefs = blocks_data[r["bid"]].get("bay_preferences")
                if not prefs:
                    continue
                pen = max(prefs) - (prefs[bay] if bay < len(prefs) else 0.0)
                if pen > _EPS:
                    cand_recs.append((pen, bay, r))
        cand_recs.sort(key=lambda t: t[0], reverse=True)

        # cand_recs는 스윕 시작 시점의 레코드 참조다. 한 swap이 X와 Y '둘'을 committed에서
        # 빼므로(pref_polish는 한 블록만 건드려 안전했다), 빠진 Y가 뒤쪽 후보로 남아 있으면
        # 그 후보를 처리할 때 이미 없는 레코드를 또 빼다 ValueError가 난다. 무효화된 레코드를
        # consumed로 건너뛴다(같은 스윕에서 여러 swap을 허용하되 stale 참조만 막는다).
        consumed = set()
        for _pen, A, rx in cand_recs:
            if time.time() >= deadline:
                break
            if id(rx) in consumed:        # 이전 swap이 Y로 빼간 레코드
                continue
            bx = rx["bid"]
            prefs_x = blocks_data[bx]["bay_preferences"]
            wl_x = blocks_data[bx]["workload"]
            cur_pref_x = prefs_x[A] if A < len(prefs_x) else 0.0
            tgt_bays = [b for b in range(n_bays)
                        if b != A and b < len(prefs_x) and prefs_x[b] > cur_pref_x + _EPS]
            if not tgt_bays:
                continue
            best = None  # (newobj, B, ry)
            for B in tgt_bays:
                # Y 후보: A로 옮겨도 덜 손해인 순으로 max_cand개
                ys = []
                for ry in committed[B]:
                    py = blocks_data[ry["bid"]].get("bay_preferences") or [0.0] * n_bays
                    dy = ((py[B] if B < len(py) else 0.0)
                          - (py[A] if A < len(py) else 0.0))
                    ys.append((dy, ry))
                ys.sort(key=lambda t: t[0])
                for _dy, ry in ys[:max_cand]:
                    if time.time() >= deadline:
                        break
                    wl_y = blocks_data[ry["bid"]]["workload"]
                    # X, Y 임시 제거 -> X를 B로, Y를 A로 재배치해 평가 -> 원복
                    committed[A].remove(rx); bay_loads[A] -= wl_x
                    committed[B].remove(ry); bay_loads[B] -= wl_y
                    newrx = _place_into(ir, blocks_data, committed, bay_loads, bx, B)
                    if newrx is not None:
                        newry = _place_into(ir, blocks_data, committed, bay_loads,
                                            ry["bid"], A)
                        if newry is not None:
                            newobj = solution_obj(committed, blocks_data,
                                                  bay_weights, bay_loads, w1, w2, w3)
                            if newobj < cur - _EPS and (best is None or newobj < best[0]):
                                best = (newobj, B, ry)
                            committed[A].remove(newry); bay_loads[A] -= wl_y
                        committed[B].remove(newrx); bay_loads[B] -= wl_x
                    committed[A].append(rx); bay_loads[A] += wl_x
                    committed[B].append(ry); bay_loads[B] += wl_y
            if best is not None:
                newobj, B, ry = best
                wl_y = blocks_data[ry["bid"]]["workload"]
                committed[A].remove(rx); bay_loads[A] -= wl_x
                committed[B].remove(ry); bay_loads[B] -= wl_y
                _place_into(ir, blocks_data, committed, bay_loads, bx, B)
                _place_into(ir, blocks_data, committed, bay_loads, ry["bid"], A)
                consumed.add(id(rx)); consumed.add(id(ry))  # 두 레코드는 이제 없다
                cur = newobj
                swaps += 1
                improved = True
    return swaps


def _fallback_place(ir, blk, bays_data, committed, prefs, r_time, proc):
    """빈-베이 윈도우 보장 배치(P1 _guaranteed_place 정신). 항상 feasible.

    가장 빨리 비는 (베이,방향)을 골라 그 베이가 X의 체류구간 동안 완전히 빌 때 넣는다.
    체류구간이 다른 어떤 committed와도 겹치지 않으므로 placed 블록과 상호작용이 없다.
    """
    n_bays = len(bays_data)
    schedules = [[(c["entry"], c["exit"]) for c in committed[j]] for j in range(n_bays)]
    blk_data = blk
    best = None  # (key, bay_id, orient, px, py, entry)
    n_orient = len(blk_data["shape"])
    for bay_id in range(n_bays):
        for orient in range(n_orient):
            # _block_bbox 로 로컬 bbox를 직접 잡아 경계 적합과 최소 위치를 구한다.
            bb = _block_bbox(blk_data, orient)
            W = ir.bay_w[bay_id]
            H = ir.bay_h[bay_id]
            if bb[2] - bb[0] > W + _EPS or bb[3] - bb[1] > H + _EPS:
                continue
            px = max(0, math.ceil(-bb[0]))
            py = max(0, math.ceil(-bb[1]))
            if px + bb[2] > W + _EPS or py + bb[3] > H + _EPS:
                continue
            entry = _empty_bay_entry(schedules[bay_id], r_time, proc)
            pref = prefs[bay_id] if bay_id < len(prefs) else 0.0
            key = (entry, -pref)
            if best is None or key < best[0]:
                best = (key, bay_id, orient, px, py, entry)
    if best is None:
        # 어떤 방향도 안 맞는 극단 -- 가장 넓은 베이 orient0 최소 위치(크래시만 회피).
        bay_id = max(range(n_bays), key=lambda j: ir.bay_w[j] * ir.bay_h[j])
        bb = _block_bbox(blk_data, 0)
        px = max(0, math.ceil(-bb[0]))
        py = max(0, math.ceil(-bb[1]))
        entry = _empty_bay_entry(schedules[bay_id], r_time, proc)
        return bay_id, px, py, 0, entry, entry + proc
    _, bay_id, orient, px, py, entry = best
    return bay_id, px, py, orient, entry, entry + proc
