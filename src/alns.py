# alns.py
# =============================================================================
# P4 -- ALNS 개선 루프 (STRATEGY_PLAN B3 / P4)
#
# 설계 의도와 육하원칙은 docs/features/06-alns.md 에 있다.
# 한 줄 요약: P3 구성기는 한 번에 한 블록을 '놓고 끝'이라 greedy 국소 최적에 갇힌다.
# ALNS는 이미 놓은 블록 일부를 '뜯어내고(destroy) 다시 채워(repair)' 경합을 풀어,
# 같은 예산에서 obj를 더 깎는다. 헤드룸 측정(features/04)이 가리킨 마지막 손잡이다.
#
# 핵심 불변식: destroy는 블록을 빼기만 하므로 feasibility를 깨지 않고, repair는 P3a의
# 양방향 크레인 검사(_place_block)로 다시 넣으므로 '만들 때부터 feasible'이 유지된다.
# 그래서 ALNS는 매 반복 check_feasibility를 부르지 않고 obj만 직접 세고(solution_obj),
# 최종 incumbent만 myalgorithm.py가 1회 중재한다. -1은 어떤 경우에도 없다.
#
# 수락 규칙은 SA: 더 좋으면 받고, 나빠도 exp(-Δ/T) 확률로 받아 국소 최적을 탈출한다.
# 거절 시 O(k)로 되돌린다(뺀 k개를 다시 넣고, repair가 넣은 k개를 뺀다).
# =============================================================================

from __future__ import annotations

import math
import os
import time

try:  # flat layout
    from constructor import _place_block, solution_obj
except ImportError:  # IDE package layout
    from ogc2026.src.constructor import _place_block, solution_obj


# -----------------------------------------------------------------------------
# 상태 조작 -- 레코드 제거/복원
# -----------------------------------------------------------------------------

def _all_records(committed):
    return [(bay, r) for bay in range(len(committed)) for r in committed[bay]]


def _remove(committed, bay_loads, blocks_data, victims):
    saved = []
    for (bay, r) in victims:
        committed[bay].remove(r)
        bay_loads[bay] -= blocks_data[r["bid"]]["workload"]
        saved.append((bay, r))
    return saved


def _undo(committed, bay_loads, blocks_data, added, saved):
    """repair가 넣은 added를 빼고, destroy가 뺀 saved를 원래대로 되돌린다(O(k))."""
    for (bay, r) in added:
        committed[bay].remove(r)
        bay_loads[bay] -= blocks_data[r["bid"]]["workload"]
    for (bay, r) in saved:
        committed[bay].append(r)
        bay_loads[bay] += blocks_data[r["bid"]]["workload"]


# -----------------------------------------------------------------------------
# destroy 연산자
# -----------------------------------------------------------------------------

def destroy_random(committed, bay_loads, blocks_data, rng, k):
    """무작위 k개 제거 -- 다양성의 기본기."""
    recs = _all_records(committed)
    k = min(k, len(recs))
    return _remove(committed, bay_loads, blocks_data, rng.sample(recs, k))


def destroy_worst(committed, bay_loads, blocks_data, rng, k):
    """지각이 큰 블록 우선 제거 -- 재배치 이득이 가장 클 후보. 상위 풀에서 무작위로
    뽑아 결정적 고착을 피한다."""
    recs = _all_records(committed)
    if not recs:
        return []
    recs.sort(key=lambda br: max(0, br[1]["exit"]
                                 - blocks_data[br[1]["bid"]]["due_date"]),
              reverse=True)
    k = min(k, len(recs))
    pool = recs[:min(len(recs), k * 3)]
    victims = rng.sample(pool, k) if len(pool) > k else pool[:k]
    return _remove(committed, bay_loads, blocks_data, victims)


def destroy_window(committed, bay_loads, blocks_data, rng, k):
    """시간상 가까운 블록 한 묶음 제거 -- 한 시간대의 경합을 통째로 다시 푼다."""
    recs = _all_records(committed)
    if not recs:
        return []
    _, anchor = rng.choice(recs)
    center = anchor["entry"]
    recs.sort(key=lambda br: abs(br[1]["entry"] - center))
    return _remove(committed, bay_loads, blocks_data, recs[:min(k, len(recs))])


def destroy_tardy_window(committed, bay_loads, blocks_data, rng, k):
    """지각 큰 블록을 앵커로 그 시간대 묶음을 제거 -- B3의 EXIT-지연/congestion 재분배 연산자.

    destroy_worst는 지각 블록만 빼서 repair가 *같은 늦은 슬롯*에 도로 넣기 쉽다(앞을 막는
    blocker가 그대로라). destroy_window는 무작위 앵커라 지각과 무관할 수 있다. 이 연산자는
    지각 블록 주변(그 앞을 막는 비-지각 blocker 포함) 시간대를 통째로 걷어, repair(EDD=납기
    이른 순=지각 우선)가 지각 블록을 더 이른 슬롯에 넣고 blocker는 자기 슬랙 안에서 뒤로
    밀리게 한다. 지각이 슬랙으로 재분배될 때만 obj가 줄고, SA 수락이라 무회귀다."""
    recs = _all_records(committed)
    if not recs:
        return []
    by_tard = sorted(recs, key=lambda br: max(0, br[1]["exit"]
                     - blocks_data[br[1]["bid"]]["due_date"]), reverse=True)
    if max(0, by_tard[0][1]["exit"] - blocks_data[by_tard[0][1]["bid"]]["due_date"]) == 0:
        return destroy_window(committed, bay_loads, blocks_data, rng, k)  # 지각 없으면 일반 윈도우
    _, anchor = rng.choice(by_tard[:max(1, min(len(by_tard), k))])  # 지각 상위 풀서 앵커
    center = anchor["entry"]
    recs.sort(key=lambda br: abs(br[1]["entry"] - center))
    return _remove(committed, bay_loads, blocks_data, recs[:min(k, len(recs))])


_BASE_DESTROY = (destroy_random, destroy_worst, destroy_window)
# A4 tardy-window: 측정상 효과가 ALNS 런-간 분산(±3~10%) 아래라 검증 불가 → 기본 OFF(opt-in).
DESTROY_OPS = (_BASE_DESTROY + (destroy_tardy_window,) if os.environ.get("OGC_USE_TARDY_WINDOW")
               else _BASE_DESTROY)


# -----------------------------------------------------------------------------
# repair -- 뺀 블록을 EDD 순으로 다시 삽입
# -----------------------------------------------------------------------------

def _repair(ir, saved, committed, bay_loads, blocks_data, bays_data,
            bay_weights, w1, w2, w3, cand):
    bids = sorted((r["bid"] for (_, r) in saved),
                  key=lambda b: (blocks_data[b]["due_date"],
                                 blocks_data[b]["processing_time"]))
    added = []
    for bid in bids:
        bay_id, _, _, _ = _place_block(
            ir, bid, blocks_data, bays_data, committed, bay_loads,
            bay_weights, w1, w2, w3, False, cand)
        added.append((bay_id, committed[bay_id][-1]))
    return added


# -----------------------------------------------------------------------------
# 메인 루프
# -----------------------------------------------------------------------------

def alns(prob_info, ir, committed, bay_loads, bay_weights, deadline, rng,
         cand="blf", t0_frac=0.002, stats=None):
    """committed 상태를 destroy/repair + SA로 개선한다. 최선 snapshot을 돌려준다.

    snapshot은 베이별 레코드 리스트의 얕은 복사(레코드는 불변이라 ref 공유). 반환 후
    호출부가 operations_from_committed로 제출 형식으로 바꾼다.
    """
    blocks_data = prob_info["blocks"]
    bays_data = prob_info["bays"]
    w = prob_info.get("weights", {})
    w1, w2, w3 = w.get("w1", 1.0), w.get("w2", 1.0), w.get("w3", 1.0)

    n = sum(len(bay) for bay in committed)
    if n == 0:
        return [list(bay) for bay in committed], 0.0, 0

    cur = solution_obj(committed, blocks_data, bay_weights, bay_loads, w1, w2, w3)
    best = cur
    best_snap = [list(bay) for bay in committed]

    t_start = time.time()
    total = max(1e-9, deadline - t_start)
    T0 = max(1.0, cur * t0_frac)
    kmin = max(1, n // 50)
    kmax = max(kmin + 1, n // 15)

    # 적응적 연산자 선택(교과서 ALNS의 'A'): 균일 무작위 대신 최근 성공으로 가중한 roulette.
    # 한 연산자가 어떤 인스턴스서 안 먹히면 가중이 내려가 시간 낭비를 줄이고, 잘 먹히면 올라가
    # 그 인스턴스에 특화된 탐색을 한다 -- A4(tardy-window)가 균일에선 wash(2승2패)였으나, 적응이면
    # 도움 되는 곳만 쓰여 손실을 줄인다. OGC_NO_ADAPTIVE로 끄면 기존 균일(측정 비교용).
    nops = len(DESTROY_OPS)
    adaptive = bool(os.environ.get("OGC_USE_ADAPTIVE"))   # 측정상 노이즈 아래 → 기본 OFF(opt-in)
    w_op = [1.0] * nops; s_op = [0.0] * nops; c_op = [0] * nops
    SIG_BEST, SIG_ACC = 3.0, 1.0; DECAY = 0.8   # 새 best/수락 보상, 반응계수

    iters = accepts = improves = 0
    while time.time() < deadline:
        k = rng.randint(kmin, kmax)
        if adaptive:
            r = rng.random() * sum(w_op); oi = nops - 1
            for j in range(nops):
                r -= w_op[j]
                if r <= 0: oi = j; break
        else:
            oi = rng.randrange(nops)
        op = DESTROY_OPS[oi]; c_op[oi] += 1
        saved = op(committed, bay_loads, blocks_data, rng, k)
        if not saved:
            break
        added = _repair(ir, saved, committed, bay_loads, blocks_data,
                        bays_data, bay_weights, w1, w2, w3, cand)
        new = solution_obj(committed, blocks_data, bay_weights, bay_loads, w1, w2, w3)
        d = new - cur
        frac = min(1.0, max(0.0, (time.time() - t_start) / total))
        T = max(1e-9, T0 * (1.0 - frac))  # 양수 보장(벽시계가 deadline 넘겨도 안전)
        if d < 0 or rng.random() < math.exp(-min(50.0, max(0.0, d) / T)):
            cur = new
            accepts += 1
            if new < best - 1e-9:
                best = new
                best_snap = [list(bay) for bay in committed]
                improves += 1
                s_op[oi] += SIG_BEST
                if stats is not None and "curve" in stats:
                    stats["curve"].append((round(time.time() - t_start, 2), best))
            else:
                s_op[oi] += SIG_ACC
        else:
            _undo(committed, bay_loads, blocks_data, added, saved)
        iters += 1
        if adaptive and iters % 64 == 0:            # 세그먼트마다 가중 갱신
            for j in range(nops):
                if c_op[j]:
                    w_op[j] = max(0.05, (1 - DECAY) * w_op[j] + DECAY * (s_op[j] / c_op[j]))
                s_op[j] = 0.0; c_op[j] = 0

    if stats is not None:
        stats.update(iters=iters, accepts=accepts, improves=improves)
    return best_snap, best, iters
