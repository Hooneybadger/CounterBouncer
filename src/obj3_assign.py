# obj3_assign.py
# =============================================================================
# obj3(선호) 할당 마스터 -- STRATEGY_PLAN B3 외층의 수리최적화 구현.
#
# obj1(지각)이 패킹+스케줄에 의존하는 것과 달리 obj2(균형)·obj3(선호)은 *순수 베이-할당의
# 함수*다(측정: 가중 비중 obj3=8%, obj3-지배 인스턴스 21개에서 obj1=0이라 obj3가 순위 결정자).
# 할당 = n×m 작은 MIP라 gurobi가 정확히 잘 맞는다(disjunctive 스케줄과 반대 -- 그건 CP-SAT).
#
# 방법: gurobi가 베이 용량(면적×체류 ≤ 베이면적×horizon×slack) 제약 하에 obj3(+ε·obj2) 최소
# 할당을 풀고, 그 (베이) 할당을 래스터 repair로 실현한다(relax_repair._repair_from_schedule 재사용).
# best-of 포트폴리오의 한 자식이라, 이 결과가 표준보다 나쁘면 메인이 표준을 고른다(무회귀 보장).
#
# gurobi는 평가 서버(후원사 라이선스)·로컬(academic)에 있으나, 없을 때도 안전하게 None을
# 반환해 호출부가 표준 구성으로 폴백하도록 optional import 한다.
# =============================================================================

from __future__ import annotations

import math
import time

try:  # flat layout
    from relax_repair import _bbox_orients, _repair_from_schedule
except ImportError:  # IDE package layout
    from ogc2026.src.relax_repair import _bbox_orients, _repair_from_schedule

try:
    import gurobipy as _gp
    from gurobipy import GRB as _GRB
    _HAS_GUROBI = True
except Exception:
    _HAS_GUROBI = False


def gurobi_available() -> bool:
    """gurobi import 성공 여부만(★import 시 solve를 돌리면 라이선스 체크가 import를 행걸 수 있어
    금지 -- import 깨지면 전체 -1). 실제 라이선스 검증은 fork 자식 안 solve_obj3_assignment의
    try/except가 한다(supervisor가 자식을 보호하고, 실패 시 표준 폴백)."""
    return _HAS_GUROBI


def solve_obj3_assignment(prob_info, cap_slack, time_cap, threads):
    """gurobi 할당 MIP로 obj3(+ε·obj2) 최소 베이 할당을 푼다. 반환: {gid: bay} or None.

    변수: 블록당 (들어갈 수 있는 베이) 택일 z[i,j]. 제약: Σ_j z=1, 베이별 용량(면적×proc 합 ≤
    베이면적×H×slack -- 과밀 방지로 obj1 발생 억제). 목적: Σ 선호페널티 + 1e-6·max불균형.
    """
    if not _HAS_GUROBI:
        return None
    blocks = prob_info["blocks"]; bays = prob_info["bays"]
    nb = len(bays); n = len(blocks)
    if nb < 2 or n == 0:
        return None
    areas = [b["width"] * b["height"] for b in bays]
    avg = sum(areas) / nb
    u = [avg / a for a in areas]
    ors = [_bbox_orients(b) for b in blocks]
    barea = [min((w * h for (w, h) in o), default=0) for o in ors]
    proc = [int(b["processing_time"]) for b in blocks]
    H = max(max(int(b["due_date"]) for b in blocks),
            max(int(b["release_time"]) + int(b["processing_time"]) for b in blocks)) + 1
    pref = [b["bay_preferences"] for b in blocks]

    def fits(i, j):
        W, Hh = bays[j]["width"], bays[j]["height"]
        return any((w <= W and h <= Hh) for (w, h) in ors[i])

    try:
        m = _gp.Model(); m.setParam("OutputFlag", 0)
        m.setParam("TimeLimit", float(time_cap)); m.setParam("Threads", int(threads))
        z = {}
        for i in range(n):
            allowed = [j for j in range(nb) if fits(i, j)] or list(range(nb))
            for j in allowed:
                z[i, j] = m.addVar(vtype=_GRB.BINARY)
            m.addConstr(_gp.quicksum(z[i, j] for j in allowed) == 1)
        load = [_gp.quicksum(barea[i] * proc[i] * z[i, j]
                             for i in range(n) if (i, j) in z) for j in range(nb)]
        for j in range(nb):
            cap = bays[j]["width"] * bays[j]["height"] * H * cap_slack
            m.addConstr(load[j] <= cap)
        wload = [_gp.quicksum(blocks[i]["workload"] * z[i, j]
                              for i in range(n) if (i, j) in z) for j in range(nb)]
        M = m.addVar(lb=0)
        for j1 in range(nb):
            for j2 in range(nb):
                if j1 != j2:
                    m.addConstr(M >= u[j1] * wload[j1] - u[j2] * wload[j2])
        pen = _gp.quicksum((max(pref[i]) - pref[i][j]) * z[i, j] for (i, j) in z)
        m.setObjective(pen + 1e-6 * M, _GRB.MINIMIZE)
        m.optimize()
        if m.SolCount == 0:
            return None
        return {i: j for (i, j) in z if round(z[i, j].X) == 1}
    except Exception:
        return None


def obj3_assign_repair(ir, prob_info, t0, timelimit, cap_slack=0.7, time_cap=5.0, threads=4):
    """gurobi obj3 할당 -> 래스터 repair로 실현. 반환: (committed, loads, bw) or None(폴백).

    cap_slack: 베이 용량 여유. 낮을수록 과밀↓(obj1↓) 선호이득↓. obj3-지배(저혼잡)라 0.7 기본.
    """
    if not _HAS_GUROBI:
        return None
    assign = solve_obj3_assignment(prob_info, cap_slack, time_cap, threads)
    if assign is None:
        return None
    blocks = prob_info["blocks"]
    n_bays = len(prob_info["bays"])
    # 베이만 honor(entry=release, honor_entry=False -> 배치 순서로 스케줄). 코어 밖 개념 없이 전체.
    sched = {gid: (bay, int(blocks[gid]["release_time"])) for gid, bay in assign.items()}
    committed = _repair_from_schedule(prob_info, ir, sched, honor_entry=False)
    try:
        from constructor import loads_from_committed
    except ImportError:
        from ogc2026.src.constructor import loads_from_committed
    loads = loads_from_committed(committed, blocks, n_bays)
    bay_areas = [prob_info["bays"][j]["width"] * prob_info["bays"][j]["height"] for j in range(n_bays)]
    avg = sum(bay_areas) / n_bays
    bw = [avg / a for a in bay_areas]
    return committed, loads, bw
