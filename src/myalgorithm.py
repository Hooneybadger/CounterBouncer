# myalgorithm.py
# =============================================================================
# P1 -- feasibility-first anytime wrapper  (STRATEGY_PLAN B1 / P1)
#
# 설계 의도와 육하원칙은 docs/features/01-feasibility-first-wrapper.md 에 있다.
# 한 줄 요약: 무슨 일이 있어도 제한시간 안에 feasible한 해를 반환한다.
#
# P1은 품질이 아니라 -1 회피가 목적이다. 그래서 '증명 가능한 feasible' 안전망
# (_guaranteed_solution)만 반환한다. 품질을 끌어올리는 강한 구성기(regret-k 등)는
# P3의 일이며, 그 개선 루프는 아래 algorithm()의 표시된 지점에 들어온다.
#
# 베이스라인의 사후 repair는 의도적으로 쓰지 않는다 -- EDD 순서 != 시간 순서라
# 단방향 증분 그리디는 나중 블록이 앞 블록의 크레인 경로를 소급해 막아 infeasible해
# 지고, 그것이 repair가 필요했던 이유다. 우리는 만들 때부터 feasible만 만든다.
# 다만 베이스라인의 *안전한* 기하 헬퍼는 재사용한다.
# =============================================================================

from __future__ import annotations

import bisect
import math
import multiprocessing  # 비-daemon 환경 호환용(현재 경로는 os.fork 사용)
import os
import pickle
import random
import shutil
import signal
import tempfile
import time

try:  # flat layout: evaluation server / batch_runner
    from utils import Bay, Block, check_feasibility
    from baseline_greedy import _empty_bay_entry, _block_bbox, _build_operations
    from raster_engine import InstanceRaster
    from constructor import (
        construct, solution_obj, operations_from_committed,
        pref_polish, pref_swap, loads_from_committed,
    )
    from alns import alns
except ImportError:  # IDE package layout
    from ogc2026.baseline.utils import Bay, Block, check_feasibility
    from ogc2026.baseline.baseline_greedy import (
        _empty_bay_entry, _block_bbox, _build_operations,
    )
    from ogc2026.src.raster_engine import InstanceRaster
    from ogc2026.src.constructor import (
        construct, solution_obj, operations_from_committed,
        pref_polish, pref_swap, loads_from_committed,
    )
    from ogc2026.src.alns import alns

# relax-and-repair 구성기(obj1 전역 스케줄 레버). ortools 미가용·import 실패 시 안전하게
# 비활성(표준 포트폴리오로 폴백). 평가 서버(ogc2026 env)엔 ortools가 있다.
try:
    try:
        from relax_repair import relax_repair, ortools_available
    except ImportError:
        from ogc2026.src.relax_repair import relax_repair, ortools_available
    _RELAX_OK = ortools_available()
except Exception:
    _RELAX_OK = False
    def relax_repair(*a, **k):  # 폴백 스텁
        return None

# obj3(선호) 할당 마스터(B3 외층). gurobi 미가용 시 안전하게 비활성(표준 폴백). obj3-지배
# 인스턴스 전용(util<0.45). 평가 서버엔 후원사 gurobi 라이선스, 로컬엔 academic.
try:
    try:
        from obj3_assign import obj3_assign_repair, gurobi_available
    except ImportError:
        from ogc2026.src.obj3_assign import obj3_assign_repair, gurobi_available
    _OBJ3_OK = gurobi_available()
except Exception:
    _OBJ3_OK = False
    def obj3_assign_repair(*a, **k):  # 폴백 스텁
        return None

# C scan 엔진(대형-혼탑 단축-tl 레버). 동봉 정적 바이너리가 Python scan을 byte-identical·19×로
# 돌려 60초 안에 339M 품질을 완주한다(features/18). 바이너리 부재·실패 시 안전하게 None→폴백.
try:
    try:
        from c_engine import run_c_engine, run_portfolio, c_engine_available
    except ImportError:
        from ogc2026.src.c_engine import run_c_engine, run_portfolio, c_engine_available
    _CENGINE_OK = c_engine_available()
except Exception:
    _CENGINE_OK = False
    def run_c_engine(*a, **k):  # 폴백 스텁
        return None
    def run_portfolio(*a, **k):  # 폴백 스텁
        return None


# -----------------------------------------------------------------------------
# 기하 헬퍼
# -----------------------------------------------------------------------------

def _ceil_int(v) -> int:
    """release/processing time을 정수 entry/exit로 *올림*한다(truncation 아님). 분수 timing이 들어와도
    entry≥release·exit−entry≥proc를 만족시켜 검증기 Stage1을 통과한다(features/17). `int()`는 5.7→5로
    *내려* entry<release를 만들어 −1을 냈다(QA red-team round2 발견). train timing은 전부 정수라
    정수엔 무영향(ceil(5)=5=int(5)) → 무회귀. 숫자가 아니면(malformed) 0으로 안전 폴백."""
    try:
        return math.ceil(v or 0)
    except Exception:
        return 0


def _ref_bbox(blk_data: dict, oi: int):
    """검증기와 동일 기준의 ref 보정 로컬 bbox -- reference point(첫 층 첫 정점)를 원점에 둔 월드
    bbox. 검증기 `Block.__post_init__`이 정점을 `(x-ref_x, y-ref_y)`만큼 옮기므로(`utils.py:308-312`),
    블록을 (0,0)에 놓은 `Block.bounding_rect()`가 곧 ref 보정 bbox다. block_id는 기하 무관이라 0.
    (px,py) 코너 계산에만 쓰고, 최종 경계 판정은 `_placed_corner`가 placed Block으로 한다.)"""
    return Block(0, blk_data, 0, 0, oi).bounding_rect()


def _placed_corner(blk_data: dict, oi: int):
    """방향 oi를 leftmost-lowest 정수 위치에 놓은 *검증기 Block*과 그 (px,py). 기하를 못 읽으면 None
    (raise 없음). 이 placed Block을 베이별로 `bay.contains_block(placed)`에 넣으면 floor의 경계 판정이
    *검증기 코드 그대로*가 된다.

    ★왜 placed Block인가 (features/16). features/15는 ref 보정 bbox(`_ref_bbox`, 원점)를 구한 뒤
    floor가 직접 `px+bb[2]≤width`로 판정했다. 그런데 검증기는 placed (px,py)에서 bbox를 *다시* 계산한다
    -- `max(v+(py-ref))` 대 `py+max(v-ref)`는 부동소수 비결합성으로 ~1 ULP 어긋난다. 그래서 블록
    extent가 베이 변과 *정확히* 일치하고 ref가 분수(non-(0,0))면 floor는 통과시키고 검증기는 거절해
    −1을 낸다(QA red-team Grace Hall 발견·재현: 한 블록 fractional re-anchor → orient 2를 베이 변에 1 ULP
    걸쳐 놓고, 깨끗이 드는 orient 6은 안 봄). 해결은 floor도 *placed Block의 bbox*를 쓰는 것 -- 같은
    float 연산 순서라 판정이 정의상 검증기와 일치한다. 좌·하 경계는 베이 무관이라 여기서 placed bbox로
    확인해 ULP 미달 시 1 올려 보정하고(분수 ref에서만 발생), 우·상은 호출부가 베이별 contains_block로 본다."""
    try:
        bb = _ref_bbox(blk_data, oi)
        px = max(0, math.ceil(-bb[0]))
        py = max(0, math.ceil(-bb[1]))
        placed = Block(0, blk_data, px, py, oi)
        pbb = placed.bounding_rect()
        if pbb[0] < 0:                       # 좌 경계 FP 미달 -- 1 올려 보정(베이 무관, 분수 ref edge)
            px += 1; placed = Block(0, blk_data, px, py, oi); pbb = placed.bounding_rect()
        if pbb[1] < 0:                       # 하 경계 FP 미달
            py += 1; placed = Block(0, blk_data, px, py, oi)
        return placed, px, py
    except Exception:
        return None


def _orient_corners(blk_data: dict):
    """블록의 읽히는 모든 방향에 대해 `(oi, placed, px, py)`를 한 번만 계산한다 -- placed=검증기 Block을
    leftmost-lowest 정수 코너에 놓은 것(베이 무관). 호출부는 `bay.contains_block(placed)`로 베이별 fit을
    판정한다(검증기 코드 그대로 = 어떤 fractional ref·경계 ULP에도 일치). 기하 불가 방향은 건너뛴다."""
    out = []
    for oi in range(len(blk_data.get("shape") or [])):
        pc = _placed_corner(blk_data, oi)
        if pc is not None:
            out.append((oi, pc[0], pc[1], pc[2]))
    return out


def _min_overflow_place(corners, bays):
    """어떤 (베이,방향)도 코너에 안 들 때의 best-effort: placed Block의 검증기 bbox로 잰 경계 *초과가
    가장 작은* (bay_id, oi, px, py)를 고른다(초과 0이면 실제 feasible). placed bbox라 검증기와 일치.

    ★(0,0)을 쓰지 않는다 -- (0,0) 고정은 음수 min-corner 블록을 경계 밖에 놓아 −1을 내던 옛 버그의
    근원이었다(features/15). 기하를 *전혀* 못 읽어 corners가 빈 블록(=표현 불가)에만 (0,0)으로 떨어지는데,
    그건 어떤 알고리즘도 못 푸는 본질적 infeasible이라 (0,0)이 손해를 더 키우지 않는다."""
    best = None  # (overflow, bay_id, oi, px, py)
    for oi, placed, px, py in corners:
        bb = placed.bounding_rect()
        for bay_id, bay in enumerate(bays):
            ov = max(0.0, bb[2] - bay.width) + max(0.0, bb[3] - bay.height)
            if best is None or ov < best[0]:
                best = (ov, bay_id, oi, px, py)
    if best is None:
        return 0, 0, 0, 0          # 모든 방향 기하 불가 -- 표현 불가 블록(인스턴스 본질적 infeasible)
    _, bay_id, oi, px, py = best
    return bay_id, oi, px, py


def _assignment(block_id, bay_id, x, y, oi, entry, exit_t) -> dict:
    return {
        "block_id": int(block_id), "bay_id": int(bay_id),
        "x": int(x), "y": int(y), "orient_idx": int(oi),
        "entry_time": int(entry), "exit_time": int(exit_t),
    }


def _edd_order(blocks_data: list) -> list:
    """Earliest Due Date 정렬 (동률은 처리시간 짧은 순)."""
    return sorted(
        range(len(blocks_data)),
        key=lambda i: (blocks_data[i]["due_date"], blocks_data[i]["processing_time"]),
    )


# -----------------------------------------------------------------------------
# 증명 가능한 feasible 안전망
# -----------------------------------------------------------------------------

def _empty_bay_entry_fast(sorted_slots, r_time: int, proc: int) -> int:
    """`_empty_bay_entry`와 *동일한 값*을 O(m)에 돌려준다 -- 단, slots가 시작시각 오름차순
    정렬돼 있어야 한다. baseline의 while-changed 재시작(O(m·passes))을 정렬 단일 패스로 바꾼다.

    왜: floor가 블록마다·베이마다 이 함수를 부르는데, 원본이 O(m²)라 floor 전체가 블록수에
    초선형(O(n³)에 근접)으로 폭발한다. 측정: 300블록 0.5s·600블록 4.4s·900블록 15s(>0.93*10s
    → 메인의 마지막 무경계 작업이 스케일에서 −1을 낸다). 정렬을 호출부가 bisect.insort로 유지하면
    여기선 한 패스로 같은 결과를 낸다. 정렬 단일 패스가 원본과 일치하는 이유: slots가 시작순이라
    entry를 앞으로만 밀며 한 번 훑으면, 최종 윈도우와 겹칠 수 있는 모든 slot을 이미 본다.
    """
    entry = int(r_time)
    for a, e in sorted_slots:
        if a >= entry + proc:
            break                 # 정렬됐으니 이후 slot도 윈도우 오른쪽 -- 더 볼 것 없다
        if entry < e:             # [entry, entry+proc)가 [a,e)와 겹침 -> 슬롯 끝으로 민다
            entry = e
    return entry


def _guaranteed_place(blk_data: dict, bays: list, sorted_sched: list):
    """한 블록의 증명 가능한 feasible 배치를 고른다.

    적합한 모든 베이에 대해 '빈-베이 윈도우'(`_empty_bay_entry_fast`)를 계산하고, 가장 빨리
    비는 곳을 고른다. 빈 윈도우는 그 구간에 같은 베이의 다른 블록이 없음을 보장하므로 크레인
    진입/반출(stage 2/3)과 공간 충돌(stage 4)이 자명히 통과한다. 베이별 윈도우가 서로 겹치지
    않아 stage 5(시간순 재생)도 안전하다.

    빈-베이 entry는 *방향과 무관*하므로 베이당 한 번만 계산한다(원본은 방향마다 중복 계산해
    n_orient배 낭비했다). 적합한 첫 방향을 쓰되, entry·sort_key가 방향 무관이라 결과는
    원본과 동일하다(원본도 strict `<`라 첫 적합 방향이 그 베이의 대표였다).

    sorted_sched[bay] -- 시작시각 오름차순 정렬된 (entry,exit) 리스트(호출부가 유지).
    반환: (bay_id, orient_idx, x, y, entry, exit_t). 절대 raise하지 않는다.

    경계(stage 4-a)는 ref 보정된 코너(`_orient_corners`)가 검증기 `contains_block`과 *정확히*
    같은 판정을 줘 보장한다 -- 방향별 bbox·코너는 베이 무관이라 블록당 한 번만 계산한다.
    """
    r_time = _ceil_int(blk_data.get("release_time", 0))
    # proc=0이면 entry==exit가 돼 _build_operations가 같은 시각 EXIT를 ENTRY보다 앞에 놓고
    # (Stage5: "EXIT before present") floor가 −1을 낸다. max(1,·)로 1단위 점유시켜 표현 가능하게
    # 만든다 -- proc≥1엔 무영향(no-op), 윈도우·exit·bay_tail이 같은 proc로 일관.
    proc    = max(1, _ceil_int(blk_data.get("processing_time", 0)))
    prefs   = blk_data.get("bay_preferences") or [0.0] * len(bays)
    corners = _orient_corners(blk_data)         # [(oi, placed, px, py)] -- placed=검증기 Block, 베이 무관

    best = None  # (sort_key, bay_id, oi, px, py, entry)
    for bay_id, bay in enumerate(bays):
        fit = None
        for oi, placed, px, py in corners:
            if bay.contains_block(placed):      # 검증기 코드 그대로 -- FP까지 일치(features/16)
                fit = (oi, px, py)              # 첫 적합 방향 -- entry는 방향 무관
                break
        if fit is None:
            continue
        entry = _empty_bay_entry_fast(sorted_sched[bay_id], r_time, proc)
        pref = prefs[bay_id] if bay_id < len(prefs) else 0.0
        sort_key = (entry, -pref)               # 가장 빨리 비는 베이, 동률이면 더 선호하는 베이
        if best is None or sort_key < best[0]:
            best = (sort_key, bay_id, fit[0], fit[1], fit[2], entry)

    if best is None:
        # 어떤 (베이,방향)도 정수 격자 코너에 안 듦 = 블록이 본질적으로 배치 불가(인스턴스 infeasible).
        # −1을 줄이는 최선으로 경계 초과가 가장 작은 배치를 고른다(초과 0이면 실제 feasible).
        bay_id, oi, px, py = _min_overflow_place(corners, bays)
        entry = _empty_bay_entry_fast(sorted_sched[bay_id], r_time, proc)
        return bay_id, oi, px, py, entry, entry + proc

    _, bay_id, oi, px, py, entry = best
    return bay_id, oi, px, py, entry, entry + proc


def _safe_finish_place(blk_data: dict, bays: list, bay_tail: list):
    """시간이 모자라거나(fast-finish) 정상 배치가 터졌을 때의 '값싸지만 *feasible*한' 직렬 배치.
    절대 raise하지 않으며, 읽히는 블록엔 (0,0)을 쓰지 않는다(features/15).

    ref 보정된 `_orient_corners`로 *실제로 베이에 드는* 방향·코너를 찾는다 -- 판정이 검증기
    `contains_block`과 정확히 같다. (옛 코드는 ref 보정을 빠뜨린 `_block_bbox`라 첫 정점이 (0,0)이
    아닌 방향을 경계 밖에 놓아 −1을 냈다 -- train은 전부 ref=(0,0)이라 못 드러낸 사각. features/15.)
    entry는 베이 tail(그 베이 마지막 exit) 이후라 빈-베이 윈도우 → 무충돌·크레인 자유가 자명.
    가장 빨리 비는 베이부터 보고, 드는 첫 (베이,방향)을 쓴다(스케줄 스캔이 없어 정상 경로보다도 싸다).
    반환: (bay_id, oi, px, py, entry, exit_t), 전부 검증기와 일치하는 feasible 값.
    """
    r_time = _ceil_int(blk_data.get("release_time", 0))
    proc = max(1, _ceil_int(blk_data.get("processing_time", 0)))  # proc=0 봉인
    corners = _orient_corners(blk_data)
    for bay_id in sorted(range(len(bays)), key=lambda j: max(bay_tail[j], r_time)):
        bay = bays[bay_id]
        for oi, placed, px, py in corners:
            if bay.contains_block(placed):      # 검증기 코드 그대로 -- FP까지 일치(features/16)
                entry = max(bay_tail[bay_id], r_time)
                return bay_id, oi, px, py, entry, entry + proc
    # 어느 (베이,방향)에도 안 듦 = 본질적 infeasible. 경계 초과 최소 배치(초과 0이면 feasible).
    bay_id, oi, px, py = _min_overflow_place(corners, bays)
    entry = max(bay_tail[bay_id], r_time)
    return bay_id, oi, px, py, entry, entry + proc


def _guaranteed_solution(prob_info: dict, deadline: float | None = None) -> dict:
    """모든 블록을 빈-베이 윈도우로 직렬 배치한 feasible 해.

    품질은 낮지만(베이별 직렬화 -> 지각 큼) 전역 검증 없이도 feasible이 보장된다. P1의 절대
    하한. 베이별 스케줄을 시작시각 정렬로 유지하고(`bisect.insort`) 빈-베이 윈도우를
    `_empty_bay_entry_fast`로 구해, baseline의 초선형 floor를 거의 선형으로 낮춘다 -- 큰
    인스턴스(블록 600·900)에서도 메인이 시간 안에 반환한다(스케일 −1 차단).

    deadline: 벽시계 마감(없으면 무제한). 넘기면 *남은 블록을 즉시 단순 직렬 윈도우로 마감*해
    무슨 일이 있어도 완전한 feasible operations를 시간 안에 낸다 -- 메인의 마지막 무경계 작업을
    제거한다(supervisor가 construct에 한 것과 같은 정신).

    ★ 예외에 강건하다: 블록 하나가 망가져도(shape 누락 등) 그 블록만 자명한 기본 배치로
    떨어뜨려 *항상 모든 블록에 대한 완전한* operations를 만든다. 빈 operations는 곧
    infeasible(Stage1: 미배치 블록)이므로, floor가 발동하는 비상 상황에서 절대 빈 dict를
    내선 안 된다 -- 이 함수가 빈 결과를 내지 않게 막는 것이 feasibility-first의 마지막 보루다.
    """
    bays = [Bay.from_dict(d, i) for i, d in enumerate(prob_info["bays"])]
    blocks_data = prob_info["blocks"]
    # 베이별 스케줄을 시작시각 오름차순 정렬로 유지 -- _empty_bay_entry_fast의 전제.
    bay_schedule = [[] for _ in bays]
    # 각 베이의 '마지막 exit'만 추적하면, fast-finish가 O(1)로 직렬 윈도우를 만들 수 있다.
    bay_tail = [0 for _ in bays]
    assignments = []
    try:
        order = _edd_order(blocks_data)
    except Exception:
        order = list(range(len(blocks_data)))   # due_date/proc 누락 등 -- 입력 순서로

    n = len(order)
    # deadline 체크 빈도(매 블록 time.time()은 큰 인스턴스서 비용) -- 64블록마다.
    check_every = 64
    fast_finish = False
    for idx, bi in enumerate(order):
        blk_data = blocks_data[bi]
        if (deadline is not None and not fast_finish
                and idx % check_every == 0 and time.time() > deadline):
            fast_finish = True      # 시간 부족 -- 남은 블록은 아래 단순 경로로 즉시 마감
        if fast_finish:
            # 빈-베이 윈도우에 *드는 위치로* 직렬 배치(0,0 고정이 아니라 -- 그게 −1의 원인이었다).
            try:
                bay_id, oi, px, py, entry, exit_t = _safe_finish_place(blk_data, bays, bay_tail)
            except Exception:
                # _safe_finish_place는 raise하지 않지만 만일의 방어선 -- (0,0)이 아니라 ref 보정된
                # min-overflow로 떨어진다(읽히는 블록엔 절대 (0,0) 금지, features/15).
                r_time = _ceil_int(blk_data.get("release_time", 0))
                proc = max(1, _ceil_int(blk_data.get("processing_time", 0)))
                bay_id, oi, px, py = _min_overflow_place(_orient_corners(blk_data), bays)
                entry = max(bay_tail[bay_id], r_time)
                exit_t = entry + proc
            if exit_t > bay_tail[bay_id]:
                bay_tail[bay_id] = exit_t
            assignments.append(_assignment(bi, bay_id, px, py, oi, entry, exit_t))
            continue
        try:
            bay_id, oi, px, py, entry, exit_t = _guaranteed_place(blk_data, bays, bay_schedule)
        except Exception:
            # _guaranteed_place는 raise하지 않지만 만일의 방어선 -- (0,0) 금지, ref 보정 경로로만
            # 떨어진다(_safe_finish_place → min-overflow). features/15.
            try:
                bay_id, oi, px, py, entry, exit_t = _safe_finish_place(blk_data, bays, bay_tail)
            except Exception:
                r_time = _ceil_int(blk_data.get("release_time", 0))
                proc = max(1, _ceil_int(blk_data.get("processing_time", 0)))
                bay_id, oi, px, py = _min_overflow_place(_orient_corners(blk_data), bays)
                entry = max(bay_tail[bay_id], r_time)
                exit_t = entry + proc
        bisect.insort(bay_schedule[bay_id], (entry, exit_t))  # 정렬 유지
        if exit_t > bay_tail[bay_id]:
            bay_tail[bay_id] = exit_t
        assignments.append(_assignment(bi, bay_id, px, py, oi, entry, exit_t))
    return {"operations": _build_operations(assignments)}


# -----------------------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------------------

def _construct_incumbent(ir, prob_info, t0, timelimit):
    """구성기 포트폴리오 -- (순서, 위치후보) best-of-3. 결정적(시드 무관)이라 모든 자식이
    같은 최고 base를 얻고, 그 위에서 시드별 ALNS가 분산을 낸다(= v1.0.0 포트폴리오).

    v1.0.0은 이 best-of-3를 메인에서 한 번만 돌려 fork로 공유했으나, 그 구성이 메인을
    묶어 짧은 제한시간에 overrun했다(P3). v1.1은 *각 자식이* 이 함수를 독립으로 돌린다 --
    결정적이라 결과 base는 모든 자식이 동일하고(품질은 v1.0.0과 일치), 무거운 구성이
    종료 가능한 자식 안에 있어 메인은 hard-bounded로 남는다. 전용 4코어에선 4중 중복 구성이
    병렬이라 벽시계 손해가 없다(메인 단독 구성 때 놀던 코어를 쓰는 것뿐).

    반환: (committed, loads, bw, obj) 또는 None.
    """
    blocks_data = prob_info["blocks"]
    w = prob_info.get("weights", {})
    w1, w2, w3 = w.get("w1", 1.0), w.get("w2", 1.0), w.get("w3", 1.0)
    best = None
    for od, cd in (("edd", "blf"), ("edd", "scan"), ("edd_area", "scan")):
        if time.time() - t0 > timelimit * 0.72:
            break
        committed, loads, bw = construct(
            prob_info, t0, timelimit, ir=ir, order=od, cand=cd, return_state=True)
        obj = solution_obj(committed, blocks_data, bw, loads, w1, w2, w3)
        if best is None or obj < best[3]:
            best = (committed, loads, bw, obj)
    return best


def _improve(ir, prob_info, committed, loads, bw, t0, timelimit, seed, verbose=False,
             light=False):
    """주어진 incumbent에서 ALNS(seed) + 선호 polish + 교환 swap + 중재.

    feasible하면 (obj, solution_dict), 아니면 None. committed/loads를 in-place로 변형하므로
    호출자(메인/워커)마다 자기 복사본이어야 한다 -- 워커는 fork COW가 그 격리를 보장한다.
    모든 마감은 공유 벽시계 t0 기준이라 시드마다 같은 절대 예산을 쓴다. 시드로 갈리는
    유일한 단계는 ALNS이고, 거기서 best-of-seeds의 분산이 난다.

    light=True면 ALNS·polish를 건너뛰고 incumbent를 바로 마감(operations+check)한다. 대형
    relax 자식 전용 -- relax_repair가 늦게(~0.74·tl) 끝나는데 ALNS·polish·900블록 check 꼬리가
    return_cap(0.93·tl)을 넘겨 자식이 *결과 쓰기 직전에 죽던* 버그(측정: 381M 만들고도 56.7s>56s에
    소멸)를 막는다. 대형서 ALNS는 inert(+0.2%)라 잃는 품질은 무시 가능하고, 얻는 건 relax가
    실제로 −42%를 *전달*하는 것이다(features/14 후속).
    """
    name = prob_info.get("name", "?")
    blocks_data = prob_info["blocks"]
    w = prob_info.get("weights", {})
    w1, w2, w3 = w.get("w1", 1.0), w.get("w2", 1.0), w.get("w3", 1.0)
    # 예산: ALNS 0.83 / polish 0.88. 그 뒤 최종 check(중단 불가능 tail)가 보통 ~0.89-0.90에
    # 끝나, 메인 supervisor의 수집 cap(0.93*tl)이 거둔다. 못 거두면 메인은 floor를 반환한다
    # (feasibility-first). 이 함수는 (fork 가능한 환경에선) 항상 자식 프로세스에서 돈다 --
    # 그래서 여기서 어떤 tail이 지연돼도 메인의 벽시계는 묶이지 않는다.
    try:
        if not light and time.time() - t0 < timelimit * 0.83:
            rng = random.Random(seed)
            snap, _, _ = alns(prob_info, ir, committed, loads, bw,
                              t0 + timelimit * 0.83, rng, cand="blf")
            committed = snap
            loads = loads_from_committed(committed, blocks_data, len(prob_info["bays"]))
        if not light and time.time() - t0 < timelimit * 0.88:
            pdl = t0 + timelimit * 0.88
            pref_polish(ir, prob_info, committed, loads, bw, w1, w2, w3, pdl)
            pref_swap(ir, prob_info, committed, loads, bw, w1, w2, w3, pdl)
    except Exception as e:
        if verbose:
            print(f"[improve] {name}: seed={seed} FAILED ({e!r}) -- 현 incumbent 중재",
                  flush=True)
    cand_sol = operations_from_committed(committed)
    res = check_feasibility(prob_info, cand_sol)
    if res["feasible"]:
        if verbose:
            print(f"[seed {seed}] {name}: obj={res['objective']:.0f} "
                  f"elapsed={time.time()-t0:.3f}s", flush=True)
        return (float(res["objective"]), cand_sol)
    return None


def _full_body(ir, prob_info, t0, timelimit, seed):
    """표준 워커 본체: best-of-3 구성 + _improve(seed). feasible (obj, 해) 또는 None.
    *구성까지 워커가 한다* -- 이것이 메인을 hard-bounded로 만드는 핵심이다(메인은 수집만).
    구성은 결정적이라 모든 워커가 같은 최고 base를 얻고, 시드만 ALNS에서 갈린다."""
    incumbent = _construct_incumbent(ir, prob_info, t0, timelimit)
    if incumbent is None:
        return None
    committed, loads, bw, _ = incumbent
    return _improve(ir, prob_info, committed, loads, bw, t0, timelimit, seed)


def _relax_body(ir, prob_info, t0, timelimit, seed, cp_cap, cp_workers):
    """relax-repair 워커: CP 코어 스케줄 → 크레인-repair base 위에서 _improve. relax_repair가
    None이면(ortools無·CP실패) 표준 구성으로 폴백 -- relax는 *순수 추가*(best-of가 무회귀 보장)."""
    # 대형(n>350, train≤300 무영향): CP workers=1로 oversubscription 완화. 4자식×4워커=16스레드가
    # 4코어를 넘겨 CP를 굶기고 blf repair를 늦췄다(측정 full-algo 658→568M). 작은 인스턴스는
    # nw(=4) 그대로 -- train-튜닝 cp=4 최적([[quality-levers-measured-ceiling]])을 보존한다.
    big = len(prob_info.get("blocks", [])) > 350
    default_w = 1 if big else cp_workers
    cpw = int(os.environ.get("OGC_CP_WORKERS", "0") or "0") or default_w  # 실험 노브(기본 0=auto)
    rr = relax_repair(ir, prob_info, t0, timelimit, cp_cap=cp_cap, workers=cpw)
    if rr is None:
        return _full_body(ir, prob_info, t0, timelimit, seed)
    committed, loads, bw = rr
    # 대형서 relax_repair는 늦게 끝나(blf ~0.74·tl) ALNS·polish 꼬리가 return_cap을 넘긴다 --
    # light로 base를 바로 마감해 relax가 결과를 *제때 쓰게* 한다(ALNS 대형서 inert).
    return _improve(ir, prob_info, committed, loads, bw, t0, timelimit, seed, light=big)


def _obj3_body(ir, prob_info, t0, timelimit, seed, cp_cap, cp_workers):
    """obj3 워커: gurobi 선호-최소 할당 → 래스터 repair base 위에서 _improve. 할당 실패 시 표준
    폴백 -- obj3 자식도 *순수 추가*(best-of가 무회귀 보장). obj3-지배(저혼잡) 인스턴스 전용."""
    rr = obj3_assign_repair(ir, prob_info, t0, timelimit, time_cap=cp_cap, threads=cp_workers)
    if rr is None:
        return _full_body(ir, prob_info, t0, timelimit, seed)
    committed, loads, bw = rr
    return _improve(ir, prob_info, committed, loads, bw, t0, timelimit, seed)


def _cengine_body(ir, prob_info, t0, timelimit, seed):
    """C scan 엔진 자식: 동봉 정적 바이너리가 native 비트마스크로 scan 구성을 ~19× 빠르게 완주해
    (obj, solution) 반환. 대형-혼잡서 Python scan이 못 끝내던 339M 품질을 60초 안에 낸다
    (features/18). C는 Python scan의 byte-identical 복제(train 10개 확인). 실패(바이너리 부재·
    파싱·infeasible·예외) 시 표준 Python 경로로 폴백 -- *순수 추가*(best-of 무회귀, floor 최후보루)."""
    res = run_c_engine(ir, prob_info, timeout=max(5.0, timelimit))
    if res is None:
        return _full_body(ir, prob_info, t0, timelimit, seed)
    return res  # (objective, solution_dict) -- 대형서 ALNS inert이라 base를 바로 쓴다


def _portfolio_body(ir, prob_info, t0, timelimit, seed):
    """순서 포트폴리오 자식: C가 수천 개 구성 순서를 배치로 돌려 내부 obj best를 고르고, 그
    best 위에서 _improve(ALNS+polish). 소형~중형서 구성 순서가 obj를 지배하는데 EDD+ALNS는 그
    공간을 안 봐 헤드룸을 흘린다 -- prob_1(n=100) 21,021→2,884(+86%, 포트폴리오 4,996 후 ALNS).
    실패(바이너리·infeasible·예외) 시 표준 Python 경로로 폴백 -- *순수 추가*(best-of 무회귀).
    feasibility는 _improve의 check_feasibility가 보증한다(infeasible이면 None→best-of가 무시)."""
    n = len(prob_info.get("blocks", []))
    port_s = max(2.0, timelimit * 0.45)          # C 배치 벽시계 -- 나머지는 _improve의 ALNS(≤0.83·tl)
    n_orders = 8000 if timelimit >= 45 else (3000 if timelimit >= 20 else 1000)
    if n > 200:
        n_orders = min(n_orders, 4000)           # 큰 인스턴스는 순서당 construct가 비싸 적게
    rr = run_portfolio(ir, prob_info, port_s=port_s, n_orders=n_orders, seed=seed,
                       timeout=max(5.0, port_s + 30.0))
    if rr is None:
        return _full_body(ir, prob_info, t0, timelimit, seed)
    committed, loads, bw = rr
    return _improve(ir, prob_info, committed, loads, bw, t0, timelimit, seed)


def _child_body(i, ir, prob_info, t0, tl, base, specials, cp_cap, nw):
    """자식 i가 실행할 본체. specials[i]가 있으면 그 전용 경로, 아니면 표준 best-of-3+ALNS.
    specials는 {자식인덱스: 'portfolio'/'cengine'/'relax'/'obj3'} (인스턴스 통계로 게이트).
    여러 자식이 서로 다른 special을 동시에 돌 수 있다(예: 0=portfolio, 1=relax) -- best-of가
    무회귀를 보장하므로 special은 모두 *순수 추가*다. 예외엔 None."""
    try:
        sp = specials.get(i)
        if sp == "portfolio":
            return _portfolio_body(ir, prob_info, t0, tl, base + i)
        if sp == "cengine":
            return _cengine_body(ir, prob_info, t0, tl, base + i)
        if sp == "relax":
            return _relax_body(ir, prob_info, t0, tl, base + i, cp_cap, nw)
        if sp == "obj3":
            return _obj3_body(ir, prob_info, t0, tl, base + i, cp_cap, nw)
        return _full_body(ir, prob_info, t0, tl, base + i)
    except Exception:
        return None


def _run_forked(ir, prob_info, t0, tl, base, nw, specials, cp_cap, return_cap):
    """raw os.fork() supervisor -- nw 자식을 띄워 결과를 임시파일로 수집. ★서버(daemon 프로세스)
    에서도 동작한다: multiprocessing.Process는 'daemonic processes are not allowed to have
    children'으로 막히지만 os.fork()는 OS 직접호출이라 통과한다(v1.1.0 P3 -1의 근본 수정 --
    그땐 fork 실패→메인 단독 construct가 큰 인스턴스서 overrun→-1).

    자식은 ir/prob_info를 COW로 상속(피클 불필요), 결과만 임시파일에 피클(원자적 rename으로
    '존재=완전기록' 보장). 메인=supervisor는 return_cap까지 *종료한* 자식 결과만 비차단 수집하고
    (heavy work 없음=bounded), 미완 자식은 SIGKILL+reap한다. os.fork 자체가 불가(seccomp 등)면
    OSError를 올려 호출부가 in-process 폴백하게 한다. 반환: results 리스트."""
    children = []
    tmpdir = tempfile.mkdtemp(prefix="ogc_")
    try:
        for i in range(nw):
            path = os.path.join(tmpdir, f"r{i}.pkl")
            pid = os.fork()
            if pid == 0:
                # ---- CHILD ---- COW 상속. 결과만 임시파일에. 파이썬 정리 건너뛰어(os._exit)
                # 부모 상태(열린 fd·락) 오염 방지.
                try:
                    r = _child_body(i, ir, prob_info, t0, tl, base, specials, cp_cap, nw)
                    if r is not None:
                        with open(path + ".tmp", "wb") as f:
                            pickle.dump(r, f)
                        os.rename(path + ".tmp", path)  # 원자적: 존재하면 완전기록
                except Exception:
                    pass
                os._exit(0)
            else:
                children.append((pid, path))
    except OSError:
        _kill_all(children)
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

    results = []
    done = set()
    while len(done) < len(children) and time.time() < return_cap:
        progressed = False
        for pid, path in children:
            if pid in done:
                continue
            try:
                wpid, _st = os.waitpid(pid, os.WNOHANG)
            except OSError:
                wpid = pid  # 이미 reap됨
            if wpid == pid:
                done.add(pid); progressed = True
                try:
                    if os.path.exists(path):
                        with open(path, "rb") as f:
                            r = pickle.load(f)
                        if r is not None:
                            results.append(r)
                except Exception:
                    pass
        if not progressed and len(done) < len(children):
            time.sleep(0.01)  # busy-wait 방지 -- return_cap이 상한
    _kill_all([(pid, path) for pid, path in children if pid not in done])
    shutil.rmtree(tmpdir, ignore_errors=True)
    return results


def _kill_all(children):
    """남은 자식을 SIGKILL + reap(좀비 방지). terminate가 아니라 KILL이라 C 확장(CP-SAT·
    Shapely)에 묶인 자식도 확실히 죽는다."""
    for pid, _path in children:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
        try:
            os.waitpid(pid, 0)
        except Exception:
            pass


class _MainTimeout(BaseException):
    """SIGALRM 시간초과 신호. ★BaseException 상속 -- construct 등 내부의 `except Exception`에
    삼켜지지 않고 _in_process_bounded까지 전파돼야 알람이 실제로 work를 끊는다."""
    pass


def _raise_main_timeout(signum, frame):
    raise _MainTimeout()


def _in_process_bounded(ir, prob_info, t0, tl, base, return_cap):
    """os.fork 자체가 불가(seccomp 등)한 극단 환경의 폴백 -- 메인에서 단일 구성+개선을 SIGALRM으로
    hard-bound한다. construct가 deadline을 무시하고 overrun해도(900블록 16s 실측) return_cap에
    알람이 _MainTimeout을 올려 中斷→ 호출부가 floor를 반환한다(-1 차단). 알람을 못 걸면(비-메인
    스레드) overrun 위험을 피해 빈 결과(floor만)를 준다. 반환: results 리스트."""
    budget = return_cap - time.time()
    if budget <= 0.1:
        return []
    try:
        old = signal.signal(signal.SIGALRM, _raise_main_timeout)
    except Exception:
        return []  # 비-메인 스레드: 알람 불가 -> overrun 위험 피해 floor만
    results = []
    signal.setitimer(signal.ITIMER_REAL, budget)
    try:
        r = _full_body(ir, prob_info, t0, tl, base)
        if r is not None:
            results.append(r)
    except _MainTimeout:
        pass  # 알람 = return_cap 도달, construct overrun을 끊음 -> floor 폴백
    except Exception:
        pass
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            signal.signal(signal.SIGALRM, old)
        except Exception:
            pass
    return results


def _utilization(prob_info) -> float:
    """혼잡도 = Σ(블록 bbox면적 × 체류) / (Σ베이면적 × horizon). obj1(지각) 발생의 물리 신호.

    높을수록 베이가 시간상 빽빽 → 경합으로 지각이 forced. relax-repair가 이득인 영역을 가르는
    *인스턴스 통계*다(번호·결과가 아니라 면적·시간만 봐 과적합 금지). 예외엔 0(=relax off)."""
    try:
        bays = prob_info["bays"]; blocks = prob_info["blocks"]
        if not blocks or not bays:
            return 0.0
        horizon = max(int(b["due_date"]) for b in blocks) + 1
        bt = 0.0
        for b in blocks:
            l0 = b["shape"][0]["layers"][0] if b.get("shape") else None
            if not l0:
                continue
            xs = [v[0] for v in l0]; ys = [v[1] for v in l0]
            bt += (max(xs) - min(xs)) * (max(ys) - min(ys)) * int(b["processing_time"])
        cap = sum(by["width"] * by["height"] for by in bays) * horizon
        return bt / cap if cap > 0 else 0.0
    except Exception:
        return 0.0


def _n_workers():
    """이 프로세스에 허용된 코어 수(taskset 핀을 존중). 평가 서버는 4코어를 핀한다.
    포트폴리오 크기를 여기에 맞춘다(자식 nw개, 메인은 감독자로 0개)."""
    try:
        n = len(os.sched_getaffinity(0))   # taskset/affinity 존중(서버에서 4)
    except (AttributeError, OSError):
        n = os.cpu_count() or 1
    return max(1, min(n, 4))               # 서버 구성(4코어)에 맞춰 캡


_BASE_SEED = 20260617


def algorithm(prob_info, timelimit=60):
    """무슨 일이 있어도 제한시간 안에 feasible한 해를 반환한다(feasibility-first anytime).

    ★ v1.1 supervisor 구조 (P3 infeasible 회귀 수정의 핵심):
      메인은 '감독자'다. 빠르고 hard-bounded한 일(floor ≤~0.7s, ir 빌드 ≈3ms)만 직접 하고,
      구성(construct)·ALNS·선호 개선·최종 check 같은 *중단 불가능하거나 짧은 제한시간에
      overrun하는 무거운 일*은 전부 fork 자식이 한다. 그래서 어느 자식이 느린 Shapely 호출에
      묶이거나 construct fast-finish로 늦거나 OOM으로 죽어도, 메인의 벽시계는 자식과 무관하게
      흐른다 -- 메인은 timeout으로 묶인 큐 수집만 하다가 return_cap(0.93*tl)에 반드시
      floor-or-best를 반환한다.

      v1.0.0은 구성과 시드 0의 _improve를 메인에서 돌렸다. construct는 deadline을 넘겨도 남은
      블록을 마저 처리하느라 ~floor_time(300블록≈0.6s) overrun하고, 시드 0의 ALNS/최종 check도
      메인을 묶는다. 느린 인스턴스(P3)에서 이 누적 tail이 벽시계를 넘기면 메인이 floor를 제때
      못 내 -1을 받았다(측정: 2s 제한시간에 300블록이 3.1s에 overtime). 이제 그 경로가
      구조적으로 사라진다 -- 메인엔 overrun할 무거운 일이 없다.

      worst case: 자식이 전부 제때 결과를 못 주면 메인은 floor(증명적 feasible)를 반환한다 --
      품질은 낮아도 −1은 아니다. 이것이 feasibility-first의 본령이다.
    """
    # ★ 최외곽 크래시 가드(전역 try/except 정신, 설계 리뷰 패널 발견). prob_info가 dict가 아니면
    #   아래 .get/인덱싱이 floor 계산 *전에* 터져 −1(algo_error)이 된다. 비-dict는 빈 operations로
    #   graceful 반환한다 -- 서버는 항상 dict를 주니 정상 입력·train엔 무영향이고, 키 누락(bays/blocks)은
    #   아래 floor의 try/except가 빈 dict로 흡수한다. feasibility-first는 "무슨 일이 있어도 크래시 금지".
    if not isinstance(prob_info, dict):
        return {"operations": {}}
    t0 = time.time()
    name = prob_info.get("name", "?")
    n = len(prob_info.get("blocks", []))
    tl = float(timelimit)
    # 메인은 무슨 일이 있어도 이 시각까지 반환한다(CLAUDE.md 절대 규칙 0.93*tl). 메인은
    # 여기 이후 무거운 일을 안 하므로(수집·종료·min·반환만, ~ms) 7% 여유가 느린 서버의
    # 직렬화·IPC tail까지 덮는다. 자식 _improve는 polish 0.88 + 최종 check로 ~0.90에 끝나
    # 이 cap이 거둔다.
    return_cap = t0 + tl * 0.93

    # 1) floor: 증명적으로 feasible한 보장 답. 정렬 빈-베이 윈도우로 거의 선형이라 보통 빠르나,
    #    초대형 인스턴스 대비 deadline을 줘 *무조건* return_cap 안에 마치게 한다(스케일 −1 차단).
    #    feasibility는 *구성의 정확성*(ref 보정된 코너 = 검증기 contains_block)으로 보장하고, 그
    #    정확성은 제출 전 `tools/floor_gate.py`가 ref≠(0,0)·malformed·fast-finish를 강제로 때려
    #    검증한다(features/15). 런타임 인라인 check는 두지 않는다 -- 로그뿐이라 서버서 관측 불가하고
    #    (더 나은 폴백도 없다) 메인의 fork 전 시간만 잡아먹는다. 검증의 책임은 게이트에 둔다.
    try:
        floor = _guaranteed_solution(prob_info, deadline=return_cap)
    except Exception as e:
        print(f"[P1] {name}: guaranteed FAILED ({e!r})", flush=True)
        floor = {"operations": {}}

    run_idx = int(os.environ.get("OGC_RUN_INDEX", "0") or "0")
    nw = int(os.environ.get("OGC_NW", "0") or "0") or _n_workers()  # 실험 노브(기본 0=자동 4)
    base = _BASE_SEED + 100 * run_idx
    results = []

    # 전역 가드: 아래 어디서 무엇이 터져도 floor를 반환한다.
    try:
        if time.time() > return_cap:
            return floor

        # 2) ir 빌드(≈3ms, hard-bounded). 구성은 *메인에서 하지 않는다* -- 자식이 한다.
        ir = InstanceRaster(prob_info)

        # 3) 자식 nw개를 raw os.fork()로 띄운다(★daemon 서버서도 동작 -- v1.1.0 P3 -1 근본수정).
        #    표준 자식은 best-of-3 구성 + ALNS(시드 분산, = v1.0.0 포트폴리오). relax 가능하고
        #    제한시간이 충분하면 자식 0을 relax-repair로(obj1 전역 스케줄 레버). relax는 None이면
        #    표준으로 폴백하므로 *순수 추가*다 -- best-of가 무회귀를 보장한다. ir은 COW 상속.
        #    메인은 자식을 직접 호출하지 않고 수집만 해 hard-bounded.
        # relax 게이트: ortools + 충분한 제한시간 + *혼잡 인스턴스*에만. relax는 obj1(지각)을
        # 깎지만 CP가 obj3(선호)를 무시해 비혼잡(obj3-지배) 인스턴스에선 베이 할당을 망쳐 손해다.
        # utilization(블록 면적·체류 합 / 베이 면적·horizon)이 혼잡도의 물리 측정이라, 이 통계로만
        # 게이트한다(인스턴스 번호가 아니라 어떤 인스턴스에도 계산되는 양 -- 과적합 금지). 측정:
        # obj3-지배 util≤0.42 vs obj1-지배 util≥0.42, 0.45가 깨끗한 분리선.
        # 자식 0에 special base를 줄지: 혼잡(obj1-지배)이면 relax, 비혼잡(obj3-지배)이면 obj3.
        # 둘은 상호배타 -- utilization으로 가른다(인스턴스 통계라 과적합 아님, 0.45 분리선).
        # specials -- {자식인덱스: 전용경로}. 여러 자식이 서로 다른 special을 동시에 돌고 best-of가
        # 무회귀를 보장하므로 special은 모두 *순수 추가*다(인스턴스 통계로 게이트, 과적합 금지).
        util = _utilization(prob_info)
        specials = {}
        if nw >= 2 and not os.environ.get("OGC_NO_SPECIAL"):
            if n > 350 and tl >= 30.0 and _CENGINE_OK and not os.environ.get("OGC_NO_CENGINE"):
                specials[0] = "cengine"  # ★대형(train≤300 너머): C scan 엔진이 Python scan을 19× 빠르게
                #   완주해 60초 안에 339M nesting 품질을 낸다(features/18). Python scan이 못 끝내
                #   BLF base(655M)에 묶이던 단축-tl 대형-혼잡을 −48% 깬다. C=Python scan byte-identical
                #   복제라 무회귀, 실패 시 표준/floor 폴백. n>350 게이트로 train(≤300)은 무영향.
                #   대형 경로는 검증된 cengine 단독을 유지한다(포트폴리오는 순서당 construct가 비싸 약함).
            else:
                # ★소형~중형(n≤250): 순서 포트폴리오. C가 수천 개 구성 순서를 배치로 돌려 best를 골라
                #   그 위에 ALNS -- 구성 순서가 obj를 지배하는데 EDD+ALNS는 그 공간을 안 봐 헤드룸을
                #   흘렸다(측정 n=100 +76%, n=150 +3.4%, n=250 +1.9%; features/19). best-of라 순수 추가.
                #   n≤250 게이트: 채점 tl(60초)에 C가 충분한 순서를 도는 상한이 ~250이고, n=300은
                #   순서가 적게 들어 포트폴리오가 자식 슬롯만 차지해 표준 시드를 잃었다(1개씩 측정
                #   prob_19 n=300 −4.9%, n=250까진 승/tie). 기전 게이트라 과적합 아님(블록수로 계산).
                if n <= 250 and _CENGINE_OK and tl >= 10.0 and not os.environ.get("OGC_NO_PORTFOLIO"):
                    specials[0] = "portfolio"
                # 혼잡(obj1-지배)이면 relax도 *별도 자식*에 -- 포트폴리오가 약한 n≈200 혼잡서 무회귀
                # 안전망(포트폴리오 −15%여도 relax가 거둔다). tl≥30(CP가 시간 필요), util≥0.45 게이트.
                if tl >= 30.0:
                    nxt = 1 if 0 in specials else 0
                    if _RELAX_OK and util >= 0.45 and not os.environ.get("OGC_NO_RELAX"):
                        specials[nxt] = "relax"   # obj1(지각) 전역 스케줄 레버(CP 코어 → nesting repair)
                    elif _OBJ3_OK and util < 0.25 and os.environ.get("OGC_USE_OBJ3"):
                        specials[nxt] = "obj3"    # ★기본 OFF(v1.3.0 순위시뮬 재기각, opt-in만)
        cp_cap = min(tl * 0.15, 20.0)                       # 인스턴스 무관 비율 게이트(과적합 금지)
        try:
            results = _run_forked(ir, prob_info, t0, tl, base, nw,
                                  specials, cp_cap, return_cap)
        except OSError as e:
            # os.fork 자체가 불가(seccomp 등 극단 환경)에서만. 메인에서 SIGALRM-bounded 단일
            # 구성+개선 best-effort -- 알람이 return_cap에 overrun을 거두고, 실패하면 floor.
            print(f"[P4c] {name}: os.fork FAILED ({e!r}) -- 메인 SIGALRM-bounded", flush=True)
            results = _in_process_bounded(ir, prob_info, t0, tl, base, return_cap)
    except Exception as e:
        print(f"[P?] {name}: unexpected ({e!r}) -- floor 반환", flush=True)

    # 메인은 return_cap(0.93*tl)에 수집을 끝내므로 여기 도달 시각은 늘 그 부근이다.
    # best_sol·floor 둘 다 이미 만들어진 feasible dict이라 반환은 즉시 -- 시간 가드로 best를
    # floor로 강등할 이유가 없다(둘 다 같은 비용). 있으면 best, 없으면 floor.
    if results:
        best_obj, best_sol = min(results, key=lambda r: r[0])
        print(f"[P11] {name}: n={n} seeds={len(results)}/{nw} best_obj={best_obj:.0f} "
              f"elapsed={time.time()-t0:.3f}s/{tl:.0f}s", flush=True)
        return best_sol

    print(f"[P1] {name}: n={n} tier=floor "
          f"elapsed={time.time()-t0:.3f}s/{tl:.0f}s", flush=True)
    return floor
