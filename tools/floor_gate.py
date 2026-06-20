#!/usr/bin/env python3
"""floor_gate.py -- floor(안전망)의 *미검증 경로*를 강제로 실행해 feasibility를 못박는 회귀 게이트.

왜 이게 필요한가
---------------
`algorithm()`이 반환하는 해는 둘 중 하나다 -- (1) 자식 결과: `_improve`에서 `check_feasibility`를
통과한 *바로 그 바이트*라 서버(동일 utils.py)에서도 feasible이 보장된다. (2) **floor**
(`_guaranteed_solution`): −1을 막는 마지막 안전망이지만 *검증을 거치지 않고* 반환된다. 그래서
floor가 infeasible하면 곧 −1인데, 로컬 게이트(`batch_runner`)는 throttle 없는 핀 환경이라 floor가
너무 빨라(300블록 5ms) `return_cap`을 절대 안 넘긴다 → floor의 **fast-finish 경로가 한 번도
실행되지 않는다**. 바로 이 사각이 fast-finish의 `(0,0)` 배치 버그를 v1.0.0~v1.2.0 세 버전 동안
숨겼다(features/13). 이 게이트는 그 경로를 *강제로* 켜서(데드라인을 과거로) 모든 인스턴스의 floor를
검증기로 때린다. floor 회귀는 여기서 즉시 잡힌다.

무엇을 검사하나 (인스턴스마다)
  - normal floor   (deadline=None)        : check_feasibility == feasible, 좌표·시각 전부 정수
  - fast-finish floor (deadline=과거)      : 〃 (전 블록이 fast-finish 경로를 탄다)
  - proc==0 합성    : 한 블록의 processing_time=0으로 바꿔 두 모드 모두 feasible (clamp 확인)

종료코드: 모두 통과 0, 하나라도 실패 1. CI/제출 전 게이트로 쓴다.

실행:  conda activate ogc2026 && python tools/floor_gate.py
"""
from __future__ import annotations

import copy
import glob
import json
import os
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "src"))

from utils import check_feasibility            # noqa: E402  (제공 검증기 = 서버 검증기)
import myalgorithm as M                          # noqa: E402


def _all_integer(sol: dict) -> bool:
    """제출 형식 불변식: 시각 키와 좌표·인덱스가 전부 정수여야 서버 포맷 검증을 통과한다.
    check_feasibility는 float x/y를 허용하므로(정수 강제 안 함), 여기서 별도로 막는다."""
    for tk, ops in sol.get("operations", {}).items():
        if str(int(tk)) != str(tk):
            return False
        for op in ops:
            if op.get("type") == "ENTRY":
                for k in ("x", "y", "orient_idx", "bay_id", "block_id"):
                    if not isinstance(op[k], int):
                        return False
    return True


def _check_floor(prob_info: dict, deadline):
    """floor 하나를 만들어 (feasible, stage, all_int, first_violation)을 돌려준다."""
    sol = M._guaranteed_solution(prob_info, deadline=deadline)
    res = check_feasibility(prob_info, sol)
    allint = _all_integer(sol)
    viol = res["violations"][0] if (not res["feasible"] and res["violations"]) else ""
    return res["feasible"], res["stage"], allint, viol


def _complete(prob_info: dict, sol: dict) -> bool:
    """모든 블록이 정확히 한 번 ENTRY로 배치됐는지(Stage1 완전성). floor는 비상시에도 *모든*
    블록에 완전한 operations를 내야 한다 -- 빈/누락은 곧 infeasible이다."""
    ids = [op["block_id"] for ops in sol.get("operations", {}).values()
           for op in ops if op.get("type") == "ENTRY"]
    return sorted(ids) == list(range(len(prob_info["blocks"])))


def _reanchor(prob_info: dict, shift):
    """블록의 모든 방향·층 정점에 (dx,dy)를 더해 reference point(첫 층 첫 정점)를 (0,0)에서
    옮긴다. shift(block_idx)->(dx,dy). 형상(상대 기하)은 그대로라 검증기가 ref로 재정렬하면 월드
    배치가 동일 → 인스턴스는 *여전히 feasible*. 하지만 ref≠(0,0)이 되어, ref 보정을 빠뜨린 floor는
    블록을 경계 밖에 놓는다(features/15의 −1 재현). train 57560개 방향은 전부 ref=(0,0)이라 이
    구조를 못 만들어내므로, 이 합성이 사각을 메운다."""
    pi = copy.deepcopy(prob_info)
    for i, b in enumerate(pi["blocks"]):
        dx, dy = shift(i)
        if dx == 0 and dy == 0:
            continue
        for orient in b["shape"]:
            orient["layers"] = [[[x + dx, y + dy] for x, y in layer]
                                for layer in orient["layers"]]
    return pi


def _check_ref_nonzero(files):
    """ref≠(0,0) 합성: 블록을 재정렬해도 floor가 feasible+정수여야 한다(normal & fast-finish).
    이것이 숨김 P3 −1의 직접 재현 테스트다 -- old floor는 여기서 전부 INFEASIBLE."""
    # 인덱스에 따라 다른 shift를 줘 ref가 블록마다 다르게 한다(균일 shift보다 빡세다).
    patterns = [
        ("all+(7,3)",      lambda i: (7, 3)),
        ("all+(250,250)",  lambda i: (250, 250)),
        ("varied",         lambda i: (11 + (i % 13), 5 + (i % 7))),
    ]
    failures = []
    # 작은 것 몇 + 큰 것 몇으로 표본(전체는 느리다). 크기순 정렬돼 있으니 양끝을 본다.
    sample = files[:4] + files[len(files) // 2: len(files) // 2 + 1] + files[-3:]
    for f in sample:
        pi = json.load(open(f))
        name = os.path.basename(f)
        for pname, shift in patterns:
            pim = _reanchor(pi, shift)
            nf, ns, nint, nv = _check_floor(pim, None)
            ff, fs, fint, fv = _check_floor(pim, time.time() - 100.0)
            ok = nf and ff and nint and fint
            tag = "OK" if ok else "FAIL"
            print(f"  {name:13} ref[{pname:14}] normal={'OK' if nf else f'INFEAS(S{ns})'} "
                  f"fast={'OK' if ff else f'INFEAS(S{fs})'} int={nint and fint} -> {tag}")
            if not ok:
                failures.append((f"{name} ref[{pname}]",
                                 f"normal_S{ns} {nv}", f"fast_S{fs} {fv}"))
    return failures


def _check_malformed(files):
    """퇴화·악성 형상: floor가 *crash 없이* 모든 블록에 완전한 정수 operations를 내야 한다(읽히는
    블록엔 (0,0) 금지). feasibility는 강제하지 않는다 -- shape가 비면 본질적으로 배치 불가일 수 있어
    그 자체로 infeasible이 정상이다. 여기서 막는 건 *crash·미완·비정수*다."""
    base = json.load(open(files[0]))
    cases = {}
    c = copy.deepcopy(base); c["blocks"][0].pop("shape", None);                 cases["block0 no-shape"] = c
    c = copy.deepcopy(base); c["blocks"][0]["shape"] = [];                      cases["block0 empty-shape"] = c
    c = copy.deepcopy(base); c["blocks"][0]["shape"][0]["layers"] = [];         cases["block0 empty-layers"] = c
    c = copy.deepcopy(base); c["blocks"][0]["shape"][0]["layers"] = [[]];       cases["block0 empty-polygon"] = c
    c = copy.deepcopy(base); c["blocks"][0].pop("processing_time", None);       cases["block0 no-proc"] = c
    c = copy.deepcopy(base); c["blocks"][0].pop("release_time", None);          cases["block0 no-release"] = c
    failures = []
    for label, pi in cases.items():
        for mode, dl in (("normal", None), ("fast-finish", time.time() - 100.0)):
            try:
                sol = M._guaranteed_solution(pi, deadline=dl)
            except Exception as e:           # crash = 곧 빈 floor = −1. 절대 허용 안 함.
                print(f"  {label:22} {mode:11} -> CRASH {e!r}")
                failures.append((f"{label} ({mode})", "CRASH", repr(e)))
                continue
            done, allint = _complete(pi, sol), _all_integer(sol)
            ok = done and allint
            print(f"  {label:22} {mode:11} complete={done} int={allint} -> {'OK' if ok else 'FAIL'}")
            if not ok:
                failures.append((f"{label} ({mode})", f"complete={done}", f"int={allint}"))
    return failures


def main() -> int:
    files = sorted(glob.glob(os.path.join(_REPO, "train", "*.json")),
                   key=lambda p: int(p.split("_")[-1].split(".")[0]))
    if not files:
        print("no train instances found", file=sys.stderr)
        return 1

    failures = []
    print(f"{'instance':14} {'normal':>16} {'fast-finish':>16} {'all_int':>8}")
    for f in files:
        pi = json.load(open(f))
        name = os.path.basename(f)
        past = time.time() - 100.0                       # 과거 데드라인 → 전 블록 fast-finish
        nf, ns, nint, nv = _check_floor(pi, None)
        ff, fs, fint, fv = _check_floor(pi, past)
        ok = nf and ff and nint and fint
        s = lambda feas, st: "OK" if feas else f"INFEAS(S{st})"
        print(f"{name:14} {s(nf, ns):>16} {s(ff, fs):>16} {str(nint and fint):>8}")
        if not ok:
            failures.append((name, f"normal={s(nf,ns)}/{nint} {nv}", f"fast={s(ff,fs)}/{fint} {fv}"))

    # proc==0 합성: 첫 인스턴스의 한 블록을 proc=0으로 만들어 floor가 여전히 feasible한지(clamp).
    pi0 = copy.deepcopy(json.load(open(files[0])))
    pi0["blocks"][0]["processing_time"] = 0
    z_nf, z_ns, _, z_nv = _check_floor(pi0, None)
    z_ff, z_fs, _, z_fv = _check_floor(pi0, time.time() - 100.0)
    zok = z_nf and z_ff
    print(f"\nproc==0 synthetic ({os.path.basename(files[0])}, block0 proc=0): "
          f"normal={'OK' if z_nf else f'INFEAS(S{z_ns}) {z_nv}'} "
          f"fast={'OK' if z_ff else f'INFEAS(S{z_fs}) {z_fv}'}")
    if not zok:
        failures.append(("proc==0 synthetic", f"normal_S{z_ns} {z_nv}", f"fast_S{z_fs} {z_fv}"))

    # ref≠(0,0) 합성: 숨김 P3 −1의 직접 재현(features/15). train은 전부 ref=(0,0)이라 이 구조를
    # 못 만든다 -- 재정렬로 만들어 floor가 여전히 feasible한지 못박는다.
    print("\nref!=(0,0) re-anchor synthetics (train-invisible -- direct P3 −1 repro):")
    failures += _check_ref_nonzero(files)

    # 퇴화·악성 형상: crash·미완·비정수 없이 완전한 operations를 내는지.
    print("\nmalformed-shape synthetics (no-crash + complete + integer):")
    failures += _check_malformed(files)

    print()
    if failures:
        print(f"FAIL -- {len(failures)} floor case(s) infeasible / non-integer / crashed:")
        for name, a, b in failures:
            print(f"  {name}: {a} | {b}")
        return 1
    print(f"PASS -- {len(files)}/{len(files)} train floors feasible+integer (normal & fast-finish), "
          f"proc==0 sealed, ref!=(0,0) feasible, malformed shapes safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
