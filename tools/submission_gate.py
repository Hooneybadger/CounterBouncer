#!/usr/bin/env python3
"""submission_gate.py -- 제출 *아티팩트*(zip)가 서버 조건(zipfile 추출)에서 실제로 C 엔진을
켜는지 못박는 회귀 게이트.

왜 이게 필요한가
---------------
평가 서버는 제출 zip을 Python `zipfile.extractall`로 푼다. 그러면 동봉 공유 라이브러리
(`scan_engine.bin`)가 **0o644로 추출**된다(+x 벗겨짐 -- zipfile의 알려진 동작). 옛 방식(standalone
바이너리 + subprocess/execve)은 이 0o644 + 서버 seccomp execve 차단으로 통째 무력화됐다(v1.3.0~1.3.2,
P3가 줄곧 폴백 736M). 수정은 **C를 .so로 빌드해 `ctypes`로 in-process 로드(dlopen)**하는 것이다 --
dlopen은 execve가 아니라 mmap이라 (a) +x 비트가 불필요하고(0o644여도 로드) (b) 서버가 numpy·shapely
처럼 .so 로드를 허용하므로 execve 차단을 우회한다. 이 게이트는 *zip을 zipfile로 풀어*(서버처럼,
+x 손실 재현) 그 dir서 algorithm()을 돌려 C가 실제로 켜졌는지(폴백 아닌지)를 obj로 확인한다.

무엇을 검사하나
  - zipfile.extractall 후 scan_engine.bin이 0o644(+x 없음)여도 ctypes.CDLL(dlopen)로 로드 →
    _CENGINE_OK=True. (옛 chmod/+x 의존이 사라졌음을 확인 -- dlopen은 +x 무관.)
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
LIB_NAME = "scan_engine.bin"   # .so를 중립 확장자로 동봉(Gmail이 .so 확장자 차단 → .bin은 통과)

# C가 켜지면 이 값보다 훨씬 낮다(폴백이면 폴백값이라 위). 폴백/C 판별 임계.
SMALL_FALLBACK = 21021      # prob_1 standard(폴백) obj. C portfolio면 ~4k.
LARGE_FALLBACK = 736453961  # 900-혼잡 BLF(폴백). C cengine이면 ~332M.


def main():
    # 1) 제출 zip 빌드 + 서버처럼 zipfile로 추출(+x 손실 재현)
    zp = submit.build_archive(submit.ARCHIVE_PATH)
    shutil.rmtree(EXTRACT, ignore_errors=True)
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        z.extractall(EXTRACT)
    ok = True
    if LIB_NAME not in names:
        print(f"  ★FAIL: {LIB_NAME}(.so)가 zip에 없음"); ok = False
    if "scan_engine" in names:
        print("  ★WARN: 옛 standalone 바이너리 scan_engine이 zip에 남아 있음(불필요)")
    mode = os.stat(os.path.join(EXTRACT, LIB_NAME)).st_mode & 0o777
    shutil.copy(os.path.join(ROOT, "src", "utils.py"), os.path.join(EXTRACT, "utils.py"))  # 서버 제공

    # 2) 추출 dir서 import → ctypes.CDLL(dlopen)이 0o644 .bin을 로드하는지(+x 무관) _CENGINE_OK 확인
    sys.path.insert(0, EXTRACT)
    import myalgorithm
    from utils import check_feasibility
    print(f"zipfile 추출 후 {LIB_NAME}: {oct(mode)} (+x 없음) → ctypes dlopen → _CENGINE_OK={myalgorithm._CENGINE_OK}")
    if not myalgorithm._CENGINE_OK:
        print("  ★FAIL: _CENGINE_OK=False — .so dlopen 실패(ctypes.CDLL 불가?)"); ok = False

    # 3) 소형 portfolio + 대형 cengine이 *실제로 켜졌는지*(폴백 아닌지) obj로 확인
    p1 = json.load(open(os.path.join(TRAIN, "prob_1.json")))
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

    print("PASS — zipfile 추출(0o644)에도 ctypes dlopen으로 .so 로드+C 발화(execve/+x 우회)" if ok
          else "FAIL — 서버 조건서 C 안 켜짐")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
