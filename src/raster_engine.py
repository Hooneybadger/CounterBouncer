# raster_engine.py
# =============================================================================
# P2 -- 정수 격자 래스터 기하 엔진  (STRATEGY_PLAN B2 / P2)
#
# 설계 의도와 육하원칙은 docs/features/02-raster-engine.md 에 있다.
# 한 줄 요약: 베이스라인이 블록 쌍마다 부르던 Shapely 다각형 교집합을, 정수
# 좌표라는 사실을 이용해 '비트맵 AND 한 번'으로 바꾼다.
#
# 핵심 불변식 (보수성):
#   각 (블록,방향,레이어) 다각형을 '셀과 양(+)의 면적으로 겹칠 때만' 1로 칠한다.
#   - 모서리 접촉(면적 0)은 칠하지 않으므로 밀착 패킹이 보존되고,
#   - 양의 면적 겹침 셀은 반드시 superset으로 칠해지므로,
#   두 마스크가 한 셀도 공유하지 않으면 두 다각형은 절대로 양의 면적으로 겹치지
#   않는다(= 래스터-feasible 이면 진짜 feasible). 판정은 안전한 방향으로만 틀린다.
#   최종 판정은 언제나 Shapely(utils.check_feasibility)가 한다 -- 엔진은 탐색용.
#
# 표현 (속도의 원천):
#   한 베이의 레이어별 점유를 '단일 Python 정수'로 둔다. 셀 (X,Y)는 비트 Y*R + X 에
#   대응하고, R = 베이 너비(행 stride)다. 정수 배치는 어차피 X < W <= R 이라 행이
#   서로 침범하지 않는다. 그러면 한 블록을 (px,py)에 놓는 일은 '마스크 정수를 한 번
#   left-shift 해 OR', feasibility 질의는 '(마스크<<shift) & occ != 0' 한 번이다.
#   Python 큰정수의 shift/and 는 C 레벨이라, 베이스라인의 블록쌍 Shapely 교집합보다
#   수백 배 빠르다. numba 는 이 환경에서 깨져 있어(numpy 2.2 vs <=2.1) 쓰지 않는다.
#
# 충돌 의미론은 utils 와 정확히 일치:
#   - 충돌 = intersection.area > 0
#   - 크레인 j >= k: 내려오는 새 layer k 는 기존 layer j>=k 전부와 무충돌이어야.
#   - 경계 검사는 래스터가 아니라 '실좌표 bbox'로(utils.Bay.contains_block 정확 복제).
# =============================================================================

from __future__ import annotations

import math
import os

# feasible_positions 차등검증 스위치(기본 OFF). 켜면 행단위 결과를 원본(big-int) ref와
# 대조해 불일치 시 AssertionError -- 채택 전 등가 증명용(OGC_ALNS_VERIFY와 같은 관례).
_FP_VERIFY = bool(os.environ.get("OGC_FP_VERIFY"))

try:  # flat layout: evaluation server / batch_runner
    from utils import _poly_from_verts, _resolve_layers
except ImportError:  # IDE package layout
    from ogc2026.baseline.utils import _poly_from_verts, _resolve_layers

# Shapely 는 utils 가 항상 들여오므로 서버에도 존재한다. 빌드(전처리)에서만 쓴다.
from shapely.geometry import box as _box


# -----------------------------------------------------------------------------
# 보수적 래스터화 -- (블록,방향,레이어) 다각형 -> 행별 비트 정수
# -----------------------------------------------------------------------------

class LayerMask:
    """한 (블록,방향,레이어)의 placement-relative 보수적 비트맵.

    reference point(= layers[0][0], 로컬 (0,0))를 월드 (px,py)에 놓으면, 이 마스크의
    로컬 셀 (cx,cy)는 월드 셀 (px+cx, py+cy)를 점유한다.

    필드:
      my0, mx0   : 마스크 좌하단 셀의 로컬 인덱스(음수 가능 -- 정점이 ref 아래/왼쪽).
      h, w       : 셀 높이/너비.
      row_ints   : 길이 h 의 Python int 리스트. row_ints[ri] 의 비트 b 가 1이면
                   로컬 셀 x = mx0+b, y = my0+ri 가 점유된다.
      empty      : 퇴화(점/선) 다각형이면 True.
    """

    __slots__ = ("my0", "mx0", "h", "w", "row_ints", "empty", "_int_by_R")

    def __init__(self, layer_verts):
        self._int_by_R = {}
        poly = _poly_from_verts(layer_verts)
        if poly is None or poly.is_empty or poly.area <= 0.0:
            self.empty = True
            self.my0 = self.mx0 = self.h = self.w = 0
            self.row_ints = []
            return
        self.empty = False
        minx, miny, maxx, maxy = poly.bounds
        mx0 = math.floor(minx)
        mx1 = math.ceil(maxx)
        my0 = math.floor(miny)
        my1 = math.ceil(maxy)
        h = my1 - my0
        row_ints = [0] * h
        # 행(=정수 y밴드)마다 다각형을 strip 으로 클립하고, 연결 조각의 x-범위 셀을 칠한다.
        # 조각의 x-bbox 전체를 칠하는 것은 양의-면적 셀의 superset 이므로 보수적이며,
        # 어떤 양의-면적 셀도 빠뜨리지 않는다(조각이 그 셀에 존재하므로 x-bbox 안).
        for ri in range(h):
            cy = my0 + ri
            strip = poly.intersection(_box(mx0 - 1, cy, mx1 + 1, cy + 1))
            if strip.is_empty:
                continue
            geoms = getattr(strip, "geoms", None)
            pieces = geoms if geoms is not None else [strip]
            acc = 0
            for piece in pieces:
                if piece.area <= 0.0:
                    continue
                pminx, _, pmaxx, _ = piece.bounds
                c0 = math.floor(pminx) - mx0
                c1 = math.ceil(pmaxx) - mx0
                # 비트 [c0, c1) 세팅
                acc |= ((1 << (c1 - c0)) - 1) << c0
            row_ints[ri] = acc
        self.my0 = my0
        self.mx0 = mx0
        self.h = h
        self.w = mx1 - mx0
        self.row_ints = row_ints

    def int_for_R(self, R: int) -> int:
        """행 stride 가 R(=베이 너비)인 단일 정수 표현. 비트(ri*R + b) = 로컬셀(mx0+b, my0+ri).

        (px,py)에 놓을 때 occ 에 OR 할 값은 int_for_R(R) << ((py+my0)*R + (px+mx0)).
        R 별로 캐시한다(베이 너비는 인스턴스당 2~5종).
        """
        v = self._int_by_R.get(R)
        if v is None:
            v = 0
            for ri, rint in enumerate(self.row_ints):
                if rint:
                    v |= rint << (ri * R)
            self._int_by_R[R] = v
        return v

    def bit_at(self, cx: int, cy: int) -> int:
        """로컬 셀 (cx,cy) 점유 비트(검증용)."""
        ri = cy - self.my0
        b = cx - self.mx0
        if 0 <= ri < self.h and b >= 0:
            return (self.row_ints[ri] >> b) & 1
        return 0


# -----------------------------------------------------------------------------
# 인스턴스 단위 마스크 캐시 + 블록 메타
# -----------------------------------------------------------------------------

class InstanceRaster:
    """인스턴스 하나에 대한 마스크 캐시와 블록 기하 메타.

    마스크는 (block_id, orient) 단위로 게으르게 빌드해 캐시한다. 실제 탐색은 블록당
    소수의 방향만 시도하므로, 모든 방향을 미리 빌드하지 않고 쓰는 것만 빌드한다.
    """

    def __init__(self, prob_info: dict):
        self.prob = prob_info
        self.blocks = prob_info["blocks"]
        self.bays = prob_info["bays"]
        self.n_bays = len(self.bays)
        self.bay_w = [int(b["width"]) for b in self.bays]
        self.bay_h = [int(b["height"]) for b in self.bays]
        self.max_layers = 0
        for blk in self.blocks:
            for orient in blk["shape"]:
                self.max_layers = max(self.max_layers, len(orient["layers"]))
        self._mask_cache: dict = {}
        self._bbox_cache: dict = {}
        self._ref_cache: dict = {}

    def _ref(self, block_id: int, orient: int):
        key = (block_id, orient)
        r = self._ref_cache.get(key)
        if r is None:
            layers = self.blocks[block_id]["shape"][orient]["layers"]
            r = tuple(layers[0][0]) if layers and layers[0] else (0.0, 0.0)
            self._ref_cache[key] = r
        return r

    def local_bbox(self, block_id: int, orient: int):
        """방향의 로컬 bbox (min_x,min_y,max_x,max_y), 레이어 합집합. 실수 좌표."""
        key = (block_id, orient)
        bb = self._bbox_cache.get(key)
        if bb is None:
            layers = _resolve_layers(self.blocks[block_id]["shape"][orient]["layers"])
            verts = [v for l in layers for v in l]
            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]
            bb = (min(xs), min(ys), max(xs), max(ys))
            self._bbox_cache[key] = bb
        return bb

    def fits_in_bay(self, block_id: int, orient: int, bay_id: int, px: int, py: int) -> bool:
        """utils.Bay.contains_block 정확 복제 -- 실좌표 bbox 가 베이 안에 드는가.

        월드 bbox = 로컬 bbox + (px - ref_x, py - ref_y). ref=(0,0) 보장이지만 안전하게
        layers[0][0] 을 빼서 일반화한다.
        """
        bb = self.local_bbox(block_id, orient)
        ref = self._ref(block_id, orient)
        dx = px - ref[0]
        dy = py - ref[1]
        W = self.bay_w[bay_id]
        H = self.bay_h[bay_id]
        return (bb[0] + dx >= 0 and bb[1] + dy >= 0
                and bb[2] + dx <= W and bb[3] + dy <= H)

    def masks(self, block_id: int, orient: int):
        """방향의 레이어별 LayerMask 리스트(placement-relative). 캐시된다.

        LayerMask 는 정점을 ref(=layers[0][0])에 상대화한 좌표로 래스터화한다 -- utils
        의 Block 이 (x - ref_x) 로 옮기는 것과 동일하게 만들어 px,py 시프트를 일치시킨다.
        """
        key = (block_id, orient)
        m = self._mask_cache.get(key)
        if m is None:
            raw = _resolve_layers(self.blocks[block_id]["shape"][orient]["layers"])
            ref = raw[0][0] if raw and raw[0] else (0.0, 0.0)
            rel_layers = [[[x - ref[0], y - ref[1]] for x, y in layer] for layer in raw]
            m = [LayerMask(layer) for layer in rel_layers]
            self._mask_cache[key] = m
        return m


# -----------------------------------------------------------------------------
# 베이 점유 누적기 -- 레이어별 단일 정수, j>=k 상부맵
# -----------------------------------------------------------------------------

class BayOccupancy:
    """한 베이의 (특정 시점에 공존하는 블록들의) 레이어별 점유.

    occ[j] = 그 시점 존재 블록들의 layer j footprint OR (단일 Python 정수, 행 stride=R).
    upper[k] = OR_{j>=k} occ[j]  (suffix-OR). j>=k 크레인 검사를 마스크당 AND 한 번으로.

    BLF 식 사용: 한 베이 상태를 고정하고 여러 후보 위치를 질의할 때, occ 를 한 번 세우고
    위치마다 shift+AND 만 한다 -- 베이스라인 대비 가속의 원천.
    """

    __slots__ = ("W", "H", "R", "nlayers", "occ", "_upper", "_upper_rows")

    def __init__(self, width: int, height: int, nlayers: int):
        self.W = int(width)
        self.H = int(height)
        self.R = int(width)  # 행 stride = 너비 (월드 X < W <= R 이라 행 침범 없음)
        self.nlayers = max(1, int(nlayers))
        self.occ = [0] * self.nlayers
        self._upper = None
        self._upper_rows = None

    def clear(self):
        self.occ = [0] * self.nlayers
        self._upper = None
        self._upper_rows = None

    def add(self, masks, px: int, py: int):
        """블록(레이어별 LayerMask 리스트)을 (px,py)에 OR-누적."""
        R = self.R
        for j, lm in enumerate(masks):
            if lm.empty or j >= self.nlayers:
                continue
            shift = (py + lm.my0) * R + (px + lm.mx0)
            self.occ[j] |= lm.int_for_R(R) << shift
        self._upper = None
        self._upper_rows = None

    def upper(self):
        """upper[k] = OR_{j>=k} occ[j]. 게으른 캐시."""
        if self._upper is None:
            up = [0] * self.nlayers
            acc = 0
            for k in range(self.nlayers - 1, -1, -1):
                acc |= self.occ[k]
                up[k] = acc
            self._upper = up
        return self._upper

    def upper_rows(self):
        """upper[k]를 레이어별 H개 행 정수(각 W비트)로 분해한 것. 게으른 캐시 -- 같은 occ에
        feasible_positions를 방향마다 부를 때 행 추출을 한 번만 한다(방향당 재추출 제거)."""
        if self._upper_rows is None:
            up = self.upper()
            R = self.R
            Rmask = (1 << R) - 1
            rows = []
            for k in range(self.nlayers):
                v = up[k]
                rk = []
                for _y in range(self.H):
                    rk.append(v & Rmask)
                    v >>= R
                rows.append(rk)
            self._upper_rows = rows
        return self._upper_rows

    # -- 질의 -----------------------------------------------------------------
    def _overlap_any(self, layer_maps, masks, px: int, py: int) -> bool:
        """블록 layer k 마스크가 layer_maps[k] 와 한 비트라도 겹치면 True.

        layer_maps 가 upper 이면 j>=k 크레인 검사(entry/exit), occ 이면 동일 레이어
        충돌(stage 4). 둘이 같은 비트연산이라 한 곳으로 묶는다.
        """
        R = self.R
        nmaps = len(layer_maps)
        for k, lm in enumerate(masks):
            if lm.empty or k >= nmaps:
                continue
            shift = (py + lm.my0) * R + (px + lm.mx0)
            if (lm.int_for_R(R) << shift) & layer_maps[k]:
                return True
        return False

    def _crane_blocked(self, masks, px: int, py: int) -> bool:
        """크레인 막힘(j>=k): 새/대상 layer k 가 upper[k] 와 겹치면 True."""
        return self._overlap_any(self.upper(), masks, px, py)

    def _collide_same_layer(self, masks, px: int, py: int) -> bool:
        """동일 레이어 충돌(stage 4): layer k 가 occ[k] 와 겹치면 True."""
        return self._overlap_any(self.occ, masks, px, py)


# -----------------------------------------------------------------------------
# 고수준 질의 -- entry / exit / collision / 전 위치 스캔
# -----------------------------------------------------------------------------

def entry_feasible(ir: InstanceRaster, occ: BayOccupancy, bay_id: int,
                   block_id: int, orient: int, px: int, py: int) -> bool:
    """블록을 (bay_id, px, py, orient)에 크레인으로 내릴 수 있는가(보수적 판정).

    occ 는 진입 시점에 베이에 '이미 있는' 블록들의 점유여야 한다(새 블록 제외).
    True 면 utils.check_entry 도 통과(보수성). False 면 보수적 거절일 수 있다.
    경계 검사는 실좌표로 정확히 한다.
    """
    if not ir.fits_in_bay(block_id, orient, bay_id, px, py):
        return False
    masks = ir.masks(block_id, orient)
    return not occ._crane_blocked(masks, px, py)


def exit_feasible(ir: InstanceRaster, occ: BayOccupancy, bay_id: int,
                  block_id: int, orient: int, px: int, py: int) -> bool:
    """블록을 (px,py)에서 크레인으로 들어 올릴 수 있는가(보수적 판정).

    occ 는 반출 시점에 함께 있는 '주변' 블록들의 점유여야 한다(대상 블록 자신 제외).
    entry 와 동일 기하(j>=k)이므로 같은 질의를 쓴다.
    """
    masks = ir.masks(block_id, orient)
    return not occ._crane_blocked(masks, px, py)


def no_collision(ir: InstanceRaster, occ: BayOccupancy, bay_id: int,
                 block_id: int, orient: int, px: int, py: int) -> bool:
    """동일 레이어 공간 충돌(stage 4)이 없는가(보수적 판정).

    occ 는 체류 구간에 공존하는 다른 블록들의 점유. True 면 utils.check_collisions 도
    충돌 없음. entry/exit(j>=k)와 달리 같은 레이어끼리(j==k)만 본다.
    """
    masks = ir.masks(block_id, orient)
    return not occ._collide_same_layer(masks, px, py)


def _feasible_positions_ref(ir: InstanceRaster, occ: BayOccupancy, bay_id: int,
                            block_id: int, orient: int):
    """원본 big-int 전 위치 스캔(차등검증 기준). 위치마다 베이 크기 정수를 시프트한다.
    `feasible_positions`(행단위)가 이것과 *동일 집합*을 더 빠르게 내는지 OGC_FP_VERIFY로 대조.
    """
    bb = ir.local_bbox(block_id, orient)
    ref = ir._ref(block_id, orient)
    W = ir.bay_w[bay_id]
    H = ir.bay_h[bay_id]
    px_lo = max(0, math.ceil(-(bb[0] - ref[0])))
    px_hi = math.floor(W - (bb[2] - ref[0]))
    py_lo = max(0, math.ceil(-(bb[1] - ref[1])))
    py_hi = math.floor(H - (bb[3] - ref[1]))
    masks = ir.masks(block_id, orient)
    # _crane_blocked 인라인: 위치 무관 stamp(layer 정수·오프셋·상부맵)를 한 번 만들고,
    # 셀마다 비트 AND만 한다. occ._crane_blocked(masks,px,py)와 동일 비트연산.
    R = occ.R
    up = occ.upper()
    nmaps = len(up)
    stamp = []
    for k, lm in enumerate(masks):
        if lm.empty or k >= nmaps:
            continue
        stamp.append((lm.int_for_R(R), lm.my0 * R + lm.mx0, up[k]))
    out = []
    out_append = out.append
    for px in range(px_lo, px_hi + 1):
        for py in range(py_lo, py_hi + 1):
            base = py * R + px
            blocked = False
            for (bint, off, upk) in stamp:
                if (bint << (base + off)) & upk:
                    blocked = True
                    break
            if not blocked:
                out_append((px, py))
    return out


def feasible_positions(ir: InstanceRaster, occ: BayOccupancy, bay_id: int,
                       block_id: int, orient: int):
    """전 위치 스캔(행 단위): 이 (베이,블록,방향)이 entry-feasible 한 모든 (px,py).

    원본(`_feasible_positions_ref`)은 위치마다 베이 크기(W·H비트) 정수를 시프트했는데, 여기선
    occ를 레이어별 H개 행 정수(각 W비트)로 한 번 뽑아 두고, 위치마다 블록의 *행들*만 W-크기로
    시프트-AND 한다. 작은 정수 연산이라 큰정수 할당 비용을 피해 ~1.3× 빠르다(혼잡 베이 측정).
    출력은 원본과 *동일 집합*(차등검증 byte-identical, OGC_FP_VERIFY) -- 가속만 한다.
    """
    bb = ir.local_bbox(block_id, orient)
    ref = ir._ref(block_id, orient)
    W = ir.bay_w[bay_id]
    H = ir.bay_h[bay_id]
    px_lo = max(0, math.ceil(-(bb[0] - ref[0])))
    px_hi = math.floor(W - (bb[2] - ref[0]))
    py_lo = max(0, math.ceil(-(bb[1] - ref[1])))
    py_hi = math.floor(H - (bb[3] - ref[1]))
    if px_hi < px_lo or py_hi < py_lo:
        return []
    masks = ir.masks(block_id, orient)
    up_rows = occ.upper_rows()   # 레이어별 H개 행 정수(캐시 -- 방향마다 재추출 안 함)
    nmaps = len(up_rows)
    # 레이어별: occ 행(W-크기) H개 + 블록의 비어있지 않은 행들[(world-row Δ, row_int)].
    layer_data = []
    for k, lm in enumerate(masks):
        if lm.empty or k >= nmaps:
            continue
        brows = [(lm.my0 + ri, rint) for ri, rint in enumerate(lm.row_ints) if rint]
        if brows:
            layer_data.append((lm.mx0, brows, up_rows[k]))
    out = []
    out_append = out.append
    for px in range(px_lo, px_hi + 1):
        for py in range(py_lo, py_hi + 1):
            blocked = False
            for (mx0, brows, occ_rows) in layer_data:
                sh = px + mx0
                for (dy, rint) in brows:
                    wr = py + dy
                    if 0 <= wr < H and (rint << sh) & occ_rows[wr]:
                        blocked = True
                        break
                if blocked:
                    break
            if not blocked:
                out_append((px, py))
    if _FP_VERIFY:  # 채택 전 등가 증명: 행단위 == 원본 big-int 집합
        ref = _feasible_positions_ref(ir, occ, bay_id, block_id, orient)
        assert sorted(out) == sorted(ref), \
            f"FP mismatch bay={bay_id} blk={block_id} o={orient}: rb={len(out)} ref={len(ref)}"
    return out
