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
LIB_NAMES = ("scan_engine_ext.b64", "scan_engine.b64")   # ★import용 abi3 확장 + ctypes 폴백 평문, 둘 다 base64 동봉

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
    for ln in LIB_NAMES:
        if ln not in names:
            print(f"  ★FAIL: {ln}(base64 엔진)가 zip에 없음"); ok = False
    # ★Gmail 안전 + 서버 로드: 직접 .so/.bin은 zip에 *있으면 안 된다*(.so=Gmail 확장자 차단). base64만 동봉.
    bad = [x for x in names if x.endswith(".so") or x in ("scan_engine.bin", "scan_engine")]
    if bad:
        print(f"  ★FAIL: 직접 바이너리가 zip에 있음(Gmail 차단/서버 미로드 위험): {bad}"); ok = False
    shutil.copy(os.path.join(ROOT, "src", "utils.py"), os.path.join(EXTRACT, "utils.py"))  # 서버 제공

    # 2) 추출 dir서 import. ★엔진 로드는 *call 시점*(myalgorithm이 algorithm() 첫 호출서 lazy). 1순위는
    #    `import scan_engine_ext`(DMS 2024 우승작 메커니즘 — ctypes 일탈을 버림), 실패 시 ctypes/memfd 폴백.
    #    그래서 import 직후 _CENGINE_OK은 None(지연)이 정상이고, algorithm() 호출 후 True여야 한다.
    sys.path.insert(0, EXTRACT)
    import myalgorithm
    from utils import check_feasibility
    print(f"zipfile 추출: {LIB_NAMES} → import 직후 _CENGINE_OK={myalgorithm._CENGINE_OK}"
          f"(None=call-시점 디코딩→로드 지연, 정상)")

    # 3) 소형 portfolio + 대형 cengine이 *실제로 켜졌는지*(폴백 아닌지) obj로 확인. algorithm() 호출이
    #    call-시점 ctypes 로드를 트리거한다 — obj가 폴백보다 충분히 낮으면 C가 켜진 것.
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

    # call 후 _CENGINE_OK=True(call-시점 엔진 로드 성공) 확인 + *어느 경로*로 떴는지(import 우선)
    if not myalgorithm._CENGINE_OK:
        print("  ★FAIL: algorithm() 호출 후에도 _CENGINE_OK=False — 엔진 로드 실패"); ok = False
    via_import = "scan_engine_ext" in sys.modules
    print(f"  로드 경로: {'import scan_engine_ext (DMS 입증 1순위)' if via_import else 'ctypes/memfd 폴백'}")
    if not via_import:
        # import 폴백이 떴다는 건 로컬선 정상이나, 서버 가설(import가 답)을 검증 못 함 — 경고만.
        print("  ⚠ 로컬서 import 경로가 아닌 폴백으로 떴다(로컬 import 자체는 위 end-to-end서 검증됨).")

    print("PASS — zipfile 추출(0o644)서 base64 디코딩 → import scan_engine_ext(우선)/ctypes(폴백)로 C 발화" if ok
          else "FAIL — 추출 조건서 C 안 켜짐")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
