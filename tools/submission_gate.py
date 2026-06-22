#!/usr/bin/env python3
"""submission_gate.py -- 제출 *아티팩트*(zip)가 서버 조건(zipfile 추출)에서 실제로 C 엔진을
켜는지 못박는 회귀 게이트. v1.3.0 무력화의 사각을 봉인한다.

왜 이게 필요한가
---------------
평가 서버는 제출 zip을 Python `zipfile.extractall`로 푼다. 그러면 동봉 바이너리(scan_engine)가
**0o644로 추출**돼(+x 벗겨짐 -- zipfile의 알려진 동작) `os.access(X_OK)=False`로 c_engine_available()
이 False가 되고, cengine·portfolio가 통째로 standard로 폴백한다. **v1.3.0 제출이 직전과 obj 완전
동일**(P3 736M·portfolio 무효)했던 게 이 버그다. 로컬 검증이 못 잡은 이유: `batch_runner -a src`
(직접)·`unzip` CLI는 +x를 보존해 서버 조건을 재현하지 않는다. 수정은 c_engine_available()이 런타임에
`os.chmod(0o755)`로 +x를 복원하는 것(commit 5c64068). 이 게이트는 *zip을 zipfile로 풀어* 그 dir서
algorithm()을 돌려 C가 실제로 켜졌는지(폴백 아닌지)를 obj로 확인한다.

무엇을 검사하나
  - zipfile.extractall 후 scan_engine이 0o644여도 import 시 chmod로 +x 복원 → _CENGINE_OK=True
  - 소형(prob_1): portfolio 발화 → obj << standard 폴백(21k). C 안 켜지면 폴백값이라 즉시 실패.
  - 대형(prob_20 ×3 = 900-혼잡): cengine 발화 → obj << BLF 폴백(736M).
  - 둘 다 feasible(검증기 통과).

종료코드: 통과 0, 실패 1. 제출 전 게이트로 쓴다(floor_gate·scale_gate와 함께).
"""
import contextlib
import copy
import io
import json
import os
import shutil
import sys
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import submit  # noqa  (build_archive)

TRAIN = os.path.join(ROOT, "train")
EXTRACT = "/tmp/ogc_submission_gate"

# C가 켜지면 이 값보다 훨씬 낮다(폴백이면 폴백값이라 위). 폴백/C 판별 임계.
SMALL_FALLBACK = 21021      # prob_1 standard(폴백) obj. C portfolio면 ~4k.
LARGE_FALLBACK = 736453961  # 900-혼잡 BLF(폴백). C cengine이면 ~332M.


def main():
    # 1) 제출 zip 빌드 + 서버처럼 zipfile로 추출(+x 손실 재현)
    zp = submit.build_archive(submit.ARCHIVE_PATH)
    shutil.rmtree(EXTRACT, ignore_errors=True)
    with zipfile.ZipFile(zp) as z:
        z.extractall(EXTRACT)
    mode = os.stat(os.path.join(EXTRACT, "scan_engine")).st_mode & 0o777
    shutil.copy(os.path.join(ROOT, "src", "utils.py"), os.path.join(EXTRACT, "utils.py"))  # 서버 제공

    # 2) 추출 dir서 import(c_engine_available의 런타임 chmod 발동) → _CENGINE_OK 확인
    sys.path.insert(0, EXTRACT)
    import myalgorithm
    from utils import check_feasibility
    new_mode = os.stat(os.path.join(EXTRACT, "scan_engine")).st_mode & 0o777
    print(f"zipfile 추출 후 scan_engine: {oct(mode)} → import 후: {oct(new_mode)}  _CENGINE_OK={myalgorithm._CENGINE_OK}")
    ok = True
    if not myalgorithm._CENGINE_OK:
        print("  ★FAIL: _CENGINE_OK=False — 바이너리 실행 불가(chmod 미작동?)"); ok = False

    # 3) 소형 portfolio + 대형 cengine이 *실제로 켜졌는지*(폴백 아닌지) obj로 확인
    p1 = json.load(open(os.path.join(TRAIN, "prob_1.json")))
    big = copy.deepcopy(p1)  # placeholder
    p20 = json.load(open(os.path.join(TRAIN, "prob_20.json")))
    big = copy.deepcopy(p20); big["blocks"] = [copy.deepcopy(b) for _ in range(3) for b in p20["blocks"]]

    for name, prob, tl, fb, lbl in [
        ("prob_1", p1, 60.0, SMALL_FALLBACK, "portfolio"),
        ("900-혼잡", big, 60.0, LARGE_FALLBACK, "cengine"),
    ]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sol = myalgorithm.algorithm(prob, tl)
        chk = check_feasibility(prob, sol)
        feas = chk["feasible"]; obj = chk["objective"] if feas else -1
        fired = feas and obj < fb * 0.9   # 폴백값보다 충분히 낮으면 C 켜진 것
        tag = "OK" if (feas and fired) else "FAIL"
        if not (feas and fired):
            ok = False
        print(f"  {name:8} tl={tl:.0f} {lbl}: feasible={feas} obj={obj:,.0f} (폴백={fb:,}) "
              f"C발화={fired} -> {tag}")

    print("PASS — zipfile 추출 후에도 C 엔진 작동(chmod 복원)" if ok
          else "FAIL — 서버 조건서 C 안 켜짐(v1.3.0 회귀)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
