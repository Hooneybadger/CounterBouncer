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
import multiprocessing
import os
import random
import time

try:  # flat layout: evaluation server / batch_runner
    from utils import Bay, check_feasibility
    from baseline_greedy import _empty_bay_entry, _block_bbox, _build_operations
    from raster_engine import InstanceRaster
    from constructor import (
        construct, solution_obj, operations_from_committed,
        pref_polish, pref_swap, loads_from_committed,
    )
    from alns import alns
except ImportError:  # IDE package layout
    from ogc2026.baseline.utils import Bay, check_feasibility
    from ogc2026.baseline.baseline_greedy import (
        _empty_bay_entry, _block_bbox, _build_operations,
    )
    from ogc2026.src.raster_engine import InstanceRaster
    from ogc2026.src.constructor import (
        construct, solution_obj, operations_from_committed,
        pref_polish, pref_swap, loads_from_committed,
    )
    from ogc2026.src.alns import alns


# -----------------------------------------------------------------------------
# 기하 헬퍼
# -----------------------------------------------------------------------------

def _origin_fit(blk_data: dict, oi: int, bay: Bay):
    """방향 oi를 베이의 최소 정수 위치에 놓을 때의 (px, py). 정수 격자에서 경계를
    벗어나면 None.

    px=ceil(-min_x), py=ceil(-min_y)로 월드 좌하단을 베이 모서리에 맞춘다. 실수
    bbox가 베이에 들어가도(bw<=width) ceil 반올림이 오른쪽/위 경계를 넘길 수 있어
    (꽉 찬 블록), 정수 위치에서의 월드 bbox를 직접 검사해야 경계 위반을 막는다.
    bbox가 베이 안이면 모든 정점도 안이므로 이 검사로 boundary가 보장된다.

    ★ 경계 검사를 검증기 `Bay.contains_block`(`bb[2] <= width`, 무허용)과 *정확히* 맞춘다.
    px+bb[2]는 검증기의 bounding_rect[2]와 같은 값이라(둘 다 모든 층·같은 ref 평행이동),
    `+1e-6` 과대 허용을 두면 경계에 sub-eps 걸치는 블록을 floor가 통과시키고 검증기는
    거절해 floor가 −1을 낸다. 허용을 제거해 floor의 판정 = 검증기 판정으로 만든다.
    """
    bb = _block_bbox(blk_data, oi)  # (min_x, min_y, max_x, max_y) 로컬 좌표
    px = max(0, math.ceil(-bb[0]))
    py = max(0, math.ceil(-bb[1]))
    if px + bb[2] <= bay.width and py + bb[3] <= bay.height:
        return px, py
    return None


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
    반환: (bay_id, orient_idx, x, y, entry, exit_t)
    """
    r_time = int(blk_data["release_time"])
    proc   = int(blk_data["processing_time"])
    n_bays = len(bays)
    prefs  = blk_data.get("bay_preferences", [0.0] * n_bays)
    n_orient = len(blk_data["shape"])

    best = None  # (sort_key, bay_id, oi, px, py, entry)
    for bay_id, bay in enumerate(bays):
        fit_oi = fit_pos = None
        for oi in range(n_orient):
            fit = _origin_fit(blk_data, oi, bay)
            if fit is not None:
                fit_oi, fit_pos = oi, fit
                break                       # entry는 방향 무관 -- 첫 적합 방향이면 충분
        if fit_oi is None:
            continue
        entry = _empty_bay_entry_fast(sorted_sched[bay_id], r_time, proc)
        pref = prefs[bay_id] if bay_id < len(prefs) else 0.0
        sort_key = (entry, -pref)           # 가장 빨리 비는 베이, 동률이면 더 선호하는 베이
        if best is None or sort_key < best[0]:
            best = (sort_key, bay_id, fit_oi, fit_pos[0], fit_pos[1], entry)

    if best is None:
        # 어떤 (베이,방향)도 정수 격자에서 안 맞음 = 이 블록은 사실상 배치 불가(인스턴스가
        # 본질적으로 infeasible). 그래도 −1을 피하려는 최선으로 *경계 초과가 가장 작은*
        # (베이,방향)을 고른다 -- orient 0 고정보다 엄밀히 낫고, 초과가 0이면 실제 feasible.
        best_ov = None  # (overflow, bay_id, oi, px, py)
        for bay_id, bay in enumerate(bays):
            for oi in range(n_orient):
                bb = _block_bbox(blk_data, oi)
                px = max(0, math.ceil(-bb[0]))
                py = max(0, math.ceil(-bb[1]))
                ov = (max(0.0, px + bb[2] - bay.width)
                      + max(0.0, py + bb[3] - bay.height))
                if best_ov is None or ov < best_ov[0]:
                    best_ov = (ov, bay_id, oi, px, py)
        _, bay_id, oi, px, py = best_ov
        entry = _empty_bay_entry_fast(sorted_sched[bay_id], r_time, proc)
        return bay_id, oi, px, py, entry, entry + proc

    _, bay_id, oi, px, py, entry = best
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
            # 가장 빨리 비는 베이(가장 작은 tail)에 release 이후 직렬로. O(베이).
            r_time = int(blk_data.get("release_time", 0) or 0)
            proc = int(blk_data.get("processing_time", 0) or 0)
            bay_id = min(range(len(bays)), key=lambda j: max(bay_tail[j], r_time))
            entry = max(bay_tail[bay_id], r_time)
            oi, px, py, exit_t = 0, 0, 0, entry + proc
            bay_tail[bay_id] = exit_t
            assignments.append(_assignment(bi, bay_id, px, py, oi, entry, exit_t))
            continue
        try:
            bay_id, oi, px, py, entry, exit_t = _guaranteed_place(blk_data, bays, bay_schedule)
        except Exception:
            # 망가진 블록: 베이 0, orient 0, 원점, release~release+proc의 자명 배치.
            r_time = int(blk_data.get("release_time", 0) or 0)
            proc = int(blk_data.get("processing_time", 0) or 0)
            try:
                entry = _empty_bay_entry_fast(bay_schedule[0], r_time, proc)
            except Exception:
                entry = r_time
            bay_id, oi, px, py, exit_t = 0, 0, 0, 0, entry + proc
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


def _improve(ir, prob_info, committed, loads, bw, t0, timelimit, seed, verbose=False):
    """주어진 incumbent에서 ALNS(seed) + 선호 polish + 교환 swap + 중재.

    feasible하면 (obj, solution_dict), 아니면 None. committed/loads를 in-place로 변형하므로
    호출자(메인/워커)마다 자기 복사본이어야 한다 -- 워커는 fork COW가 그 격리를 보장한다.
    모든 마감은 공유 벽시계 t0 기준이라 시드마다 같은 절대 예산을 쓴다. 시드로 갈리는
    유일한 단계는 ALNS이고, 거기서 best-of-seeds의 분산이 난다.
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
        if time.time() - t0 < timelimit * 0.83:
            rng = random.Random(seed)
            snap, _, _ = alns(prob_info, ir, committed, loads, bw,
                              t0 + timelimit * 0.83, rng, cand="blf")
            committed = snap
            loads = loads_from_committed(committed, blocks_data, len(prob_info["bays"]))
        if time.time() - t0 < timelimit * 0.88:
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


def _worker_full(q, ir, prob_info, t0, timelimit, seed):
    """워커 본체(v1.1): best-of-3 구성 + _improve(seed)를 통째로 돌려 결과를 Queue에 넣는다.
    *구성까지 자식이 한다* -- 이것이 메인을 hard-bounded로 만드는 핵심이다.

    구성은 deadline을 넘기면 남은 블록을 빠른 경로로 마감하느라 ~floor_time(300블록≈0.6s)
    overrun할 수 있다. v1.0.0은 이 구성을 메인에서 돌려, 짧은 제한시간에 메인이 그 overrun에
    묶여 floor를 제때 못 냈다(P3 -1의 한 갈래). 이제 그 무거운 일은 전부 여기, 종료 가능한
    자식 안에 있다 -- 메인은 timeout-bounded 큐 수집만 한다. 구성은 결정적이라 모든 자식이
    같은 최고 base를 얻고(품질 v1.0.0과 일치), 시드만 ALNS에서 갈린다.

    fork 컨텍스트라 함수·인자(ir 포함)가 피클되지 않고 COW로 상속된다. ir은 읽기 전용으로
    공유되고(메인이 만든 immutable 인스턴스 데이터), 구성이 만드는 committed는 자식 고유라
    격리된다. Queue로 돌려보내는 결과(obj, 해)만 피클되며 평범한 dict/list라 안전하다.
    """
    try:
        incumbent = _construct_incumbent(ir, prob_info, t0, timelimit)
        if incumbent is None:
            r = None
        else:
            committed, loads, bw, _ = incumbent
            r = _improve(ir, prob_info, committed, loads, bw, t0, timelimit, seed)
    except Exception:
        r = None
    try:
        q.put(r)
    except Exception:
        pass


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
    try:
        floor = _guaranteed_solution(prob_info, deadline=return_cap)
    except Exception as e:
        print(f"[P1] {name}: guaranteed FAILED ({e!r})", flush=True)
        floor = {"operations": {}}

    run_idx = int(os.environ.get("OGC_RUN_INDEX", "0") or "0")
    nw = _n_workers()
    base = _BASE_SEED + 100 * run_idx
    results = []

    # 전역 가드: 아래 어디서 무엇이 터져도 floor를 반환한다.
    try:
        if time.time() > return_cap:
            return floor

        # 2) ir 빌드(≈3ms, hard-bounded). 구성은 *메인에서 하지 않는다* -- 자식이 한다.
        ir = InstanceRaster(prob_info)

        # 3) 자식 nw개를 fork. 각 자식은 best-of-3 구성(결정적·동일 base)을 짓고 그 위에서
        #    ALNS(base+i)+선호 개선을 돌려 결과를 큐에 넣는다(= v1.0.0 포트폴리오, 시드 분산).
        #    ir은 읽기 전용으로 COW 공유된다. 메인은 _worker_full을 직접 호출하지 않는다 --
        #    이것이 메인을 hard-bounded로 만든다.
        procs, q = [], None
        try:
            ctx = multiprocessing.get_context("fork")
            q = ctx.Queue()
            for i in range(nw):
                p = ctx.Process(
                    target=_worker_full,
                    args=(q, ir, prob_info, t0, tl, base + i),
                    daemon=True)
                p.start()
                procs.append(p)
        except Exception as e:  # fork 불가(seccomp 등) -- 자식 없이 진행
            print(f"[P4c] {name}: fork FAILED ({e!r}) -- 메인 단독(degraded)", flush=True)
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass
            procs, q = [], None

        if procs:
            # 메인 = supervisor. return_cap까지 timeout-bounded로 수집만 한다.
            got = 0
            while got < len(procs) and time.time() < return_cap:
                try:
                    r = q.get(timeout=max(0.01, return_cap - time.time()))
                except Exception:   # queue.Empty(타임아웃) 등 -- 더 안 기다린다
                    break
                got += 1
                if r is not None:
                    results.append(r)
            # 남은 자식 즉시 종료(daemon이라 보장되나 명시적으로). terminate는 비동기라 tail 없음.
            for p in procs:
                try:
                    if p.is_alive():
                        p.terminate()
                except Exception:
                    pass
            try:
                q.cancel_join_thread()   # 인터프리터 종료 시 feeder thread join 회피
            except Exception:
                pass
        else:
            # fork 불가 환경에서만(degraded): 메인에서 구성 하나 + 시드 하나를 best-effort로.
            # 이 경로만 메인이 무거운 일을 하나, fork가 없으니 달리 방법이 없다. 짧은 제한시간엔
            # overrun 위험이 있으나 floor가 이미 손에 있어 -1로 가진 않는다(반환 직전 가드).
            if time.time() < t0 + tl * 0.5:
                try:
                    committed, loads, bw = construct(
                        prob_info, t0, tl, ir=ir, order="edd", cand="scan", return_state=True)
                    if time.time() < return_cap:
                        r0 = _improve(ir, prob_info, committed, loads, bw, t0, tl, base,
                                      verbose=True)
                        if r0 is not None:
                            results.append(r0)
                except Exception as e:
                    print(f"[P3] {name}: degraded construct FAILED ({e!r})", flush=True)
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
