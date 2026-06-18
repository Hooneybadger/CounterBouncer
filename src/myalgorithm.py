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
    """
    bb = _block_bbox(blk_data, oi)  # (min_x, min_y, max_x, max_y) 로컬 좌표
    px = max(0, math.ceil(-bb[0]))
    py = max(0, math.ceil(-bb[1]))
    if px + bb[2] <= bay.width + 1e-6 and py + bb[3] <= bay.height + 1e-6:
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

def _guaranteed_place(blk_data: dict, bays: list, bay_schedule: list):
    """한 블록의 증명 가능한 feasible 배치를 고른다.

    적합한 모든 (베이, 방향)에 대해 '빈-베이 윈도우'(`_empty_bay_entry`)를 계산하고,
    가장 빨리 비는 곳을 고른다. 빈 윈도우는 그 구간에 같은 베이의 다른 블록이 없음을
    보장하므로 크레인 진입/반출(stage 2/3)과 공간 충돌(stage 4)이 자명히 통과한다.
    베이별 윈도우가 서로 겹치지 않아 stage 5(시간순 재생)도 안전하다.

    반환: (bay_id, orient_idx, x, y, entry, exit_t)
    """
    r_time = int(blk_data["release_time"])
    proc   = int(blk_data["processing_time"])
    n_bays = len(bays)
    prefs  = blk_data.get("bay_preferences", [0.0] * n_bays)

    best = None  # (sort_key, bay_id, oi, px, py, entry)
    for bay_id, bay in enumerate(bays):
        for oi in range(len(blk_data["shape"])):
            fit = _origin_fit(blk_data, oi, bay)
            if fit is None:
                continue
            px, py = fit
            entry = _empty_bay_entry(bay_schedule[bay_id], r_time, proc)
            pref = prefs[bay_id] if bay_id < len(prefs) else 0.0
            sort_key = (entry, -pref)  # 가장 빨리 비는 베이, 동률이면 더 선호하는 베이
            if best is None or sort_key < best[0]:
                best = (sort_key, bay_id, oi, px, py, entry)

    if best is None:
        # 어떤 (베이,방향)도 정수 격자에서 안 맞는 극단적 경우(드묾): 가장 넓은
        # 베이에 orient 0 최소 위치 -- 경계 위반 가능하나 크래시는 피한다.
        bay_id = max(range(n_bays),
                     key=lambda j: bays[j].width * bays[j].height)
        bb = _block_bbox(blk_data, 0)
        entry = _empty_bay_entry(bay_schedule[bay_id], r_time, proc)
        px = max(0, math.ceil(-bb[0]))
        py = max(0, math.ceil(-bb[1]))
        return bay_id, 0, px, py, entry, entry + proc

    _, bay_id, oi, px, py, entry = best
    return bay_id, oi, px, py, entry, entry + proc


def _guaranteed_solution(prob_info: dict) -> dict:
    """모든 블록을 빈-베이 윈도우로 직렬 배치한 feasible 해.

    품질은 낮지만(베이별 직렬화 -> 지각 큼) 전역 검증 없이도 feasible이 보장된다.
    P1의 절대 하한. O(블록수 x 베이수)로 밀리초면 끝난다.
    """
    bays = [Bay.from_dict(d, i) for i, d in enumerate(prob_info["bays"])]
    blocks_data = prob_info["blocks"]
    bay_schedule = [[] for _ in bays]
    assignments = []
    for bi in _edd_order(blocks_data):
        blk_data = blocks_data[bi]
        bay_id, oi, px, py, entry, exit_t = _guaranteed_place(blk_data, bays, bay_schedule)
        bay_schedule[bay_id].append((entry, exit_t))
        assignments.append(_assignment(bi, bay_id, px, py, oi, entry, exit_t))
    return {"operations": _build_operations(assignments)}


# -----------------------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------------------

def _construct_incumbent(ir, prob_info, t0, timelimit):
    """구성기 포트폴리오 -- (순서, 위치후보) best-of. 시드와 무관(결정적)하므로 메인에서
    딱 한 번만 돌리고, 그 incumbent를 fork로 모든 워커에 공유한다. 그래야 큰 인스턴스의
    무거운 구성이 워커 경합에 늦춰져 더 나쁜 base로 추락하는 일을 막는다.

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
    try:
        if time.time() - t0 < timelimit * 0.80:
            rng = random.Random(seed)
            snap, _, _ = alns(prob_info, ir, committed, loads, bw,
                              t0 + timelimit * 0.83, rng, cand="blf")
            committed = snap
            loads = loads_from_committed(committed, blocks_data, len(prob_info["bays"]))
        if time.time() - t0 < timelimit * 0.90:
            pdl = t0 + timelimit * 0.90
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


def _worker_improve(q, ir, prob_info, committed, loads, bw, t0, timelimit, seed):
    """워커 본체: fork로 상속한 incumbent에서 _improve(seed)를 돌리고 결과를 Queue에 넣는다.

    fork 컨텍스트라 함수·인자(무거운 committed·ir 포함)가 피클되지 않고 COW로 상속된다
    (ProcessPoolExecutor는 함수를 qualified-name으로 피클하다 평가 서버의 importlib 로드와
    충돌해 PicklingError가 난다 -- 그래서 fork Process를 쓴다). Queue로 돌려보내는 결과
    (obj, 해)만 피클되며 평범한 dict/list라 안전하다. committed는 COW 복사본이라 이 워커의
    in-place 변형이 메인·다른 워커와 격리된다.
    """
    try:
        r = _improve(ir, prob_info, committed, loads, bw, t0, timelimit, seed)
    except Exception:
        r = None
    try:
        q.put(r)
    except Exception:
        pass


def _n_workers():
    """이 프로세스에 허용된 코어 수(taskset 핀을 존중). 평가 서버는 4코어를 핀한다.
    포트폴리오 크기를 여기에 맞춰, 메인 1개 in-process + 나머지를 워커로 돌린다."""
    try:
        n = len(os.sched_getaffinity(0))   # taskset/affinity 존중(서버에서 4)
    except (AttributeError, OSError):
        n = os.cpu_count() or 1
    return max(1, min(n, 4))               # 서버 구성(4코어)에 맞춰 캡


_BASE_SEED = 20260617


def algorithm(prob_info, timelimit=60):
    """무슨 일이 있어도 제한시간 안에 feasible한 해를 반환한다(feasibility-first anytime).

      1) floor: 증명 가능한 안전망(_guaranteed_solution). 절대 실패하지 않는 하한.
      2) 4코어 포트폴리오: 메인이 시드 0을 in-process로 돌리고, 남는 코어에 시드 1~N-1
         워커를 병렬로 띄워 best-of-seeds를 취한다. ALNS는 시드마다 다른 궤적을 그리고,
         그 분산이 커서(측정: prob_16 spread 37.7%) best-of가 단일을 크게 이긴다(p4c).
      3) best feasible obj를 채택. 워커가 다 실패해도 메인 시드 0(=옛 단일 실행)이 남고,
         멀티프로세싱 자체가 깨져도 floor가 남는다 -- -1은 어떤 경우에도 없다.

    구성은 _construct_incumbent가 메인에서 한 번만(시드 무관) 돌고, 시드별 ALNS+선호 개선은
    _improve가 한다(메인 in-process, 워커는 fork로 incumbent를 COW 상속받아 병렬로).
    """
    t0 = time.time()
    name = prob_info.get("name", "?")
    n = len(prob_info.get("blocks", []))

    try:
        floor = _guaranteed_solution(prob_info)
    except Exception as e:
        print(f"[P1] {name}: guaranteed FAILED ({e!r})", flush=True)
        return {"operations": {}}

    run_idx = int(os.environ.get("OGC_RUN_INDEX", "0") or "0")
    nw = _n_workers()
    base = _BASE_SEED + 100 * run_idx          # --repeat가 포트폴리오 전체를 흔들 여지
    results = []

    # 2) 구성: 메인이 한 번만(시드 무관·결정적). 워커 경합이 시작되기 전에 끝나, 큰
    #    인스턴스의 무거운 scan 구성이 늦춰져 더 나쁜 base로 추락하는 일을 막는다.
    try:
        ir = InstanceRaster(prob_info)
        incumbent = _construct_incumbent(ir, prob_info, t0, timelimit)
    except Exception as e:
        print(f"[P3] {name}: construct FAILED ({e!r}) -- floor 반환", flush=True)
        incumbent = None

    if incumbent is not None:
        committed, loads, bw, _ = incumbent

        # 3) 워커: 시드 1..nw-1. fork로 incumbent(committed·ir)를 COW 상속받아 ALNS+선호
        #    개선만 병렬화한다. fork Process라 (1) 무거운 인자가 피클 안 됨(평가 서버의
        #    importlib 로드와 무관), (2) daemon이라 메인 종료 시 자동으로 죽어 행이 불가능
        #    하다 -- feasibility-first의 절대선. 워커는 committed의 COW 복사본을 변형하므로
        #    메인·다른 워커와 격리된다.
        procs, q = [], None
        if nw > 1 and time.time() - t0 < timelimit * 0.80:
            try:
                ctx = multiprocessing.get_context("fork")
                q = ctx.Queue()
                for i in range(1, nw):
                    p = ctx.Process(
                        target=_worker_improve,
                        args=(q, ir, prob_info, committed, loads, bw, t0, timelimit,
                              base + i),
                        daemon=True)
                    p.start()
                    procs.append(p)
            except Exception as e:  # fork 불가 등 -- 메인 단독으로 진행
                print(f"[P4c] {name}: worker spawn FAILED ({e!r}) -- 단독 실행", flush=True)
                procs, q = [], None

        # 메인: 시드 0(=옛 단일 실행)을 in-process로. 워커가 다 죽어도 이게 남는다. 워커는
        # 이미 fork로 incumbent를 snapshot했으므로, 메인이 committed를 in-place 변형해도 무관.
        r0 = _improve(ir, prob_info, committed, loads, bw, t0, timelimit, base,
                      verbose=True)
        if r0 is not None:
            results.append(r0)

        # 워커 수확(best-effort, 0.95*timelimit 안에서만). 워커마다 정확히 한 번 put.
        collect_dl = t0 + timelimit * 0.95
        got = 0
        while q is not None and got < len(procs) and time.time() < collect_dl:
            try:
                r = q.get(timeout=max(0.01, collect_dl - time.time()))
            except Exception:        # queue.Empty(타임아웃) 등 -- 더 안 기다린다
                break
            got += 1
            if r is not None:
                results.append(r)

        # 안전벨트: 남은 워커를 즉시 종료(daemon이라 종료는 보장되나 명시적으로). 메인이
        # 종료에서 멈추는 것 = timelimit 초과 = -1 이라 무슨 일이 있어도 막는다.
        for p in procs:
            try:
                if p.is_alive():
                    p.terminate()
            except Exception:
                pass

    if results:
        best_obj, best_sol = min(results, key=lambda r: r[0])
        print(f"[P4c] {name}: n={n} seeds={len(results)}/{nw} best_obj={best_obj:.0f} "
              f"elapsed={time.time()-t0:.3f}s/{timelimit:.0f}s", flush=True)
        return best_sol

    print(f"[P1] {name}: n={n} tier=guaranteed(floor) "
          f"elapsed={time.time()-t0:.3f}s/{timelimit:.0f}s", flush=True)
    return floor
