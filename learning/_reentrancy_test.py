#!/usr/bin/env python3
"""scan_engine.bin(.so) 멀티콜 재진입 검증. 옛 .so는 한 프로세스서 서로 다른 크기 인스턴스를
연속 호출하면 upN(첫 콜 크기 고정) 오버플로로 `free(): invalid pointer` 크래시했다. 이 테스트는
(1) 무크래시(프로세스 생존) (2) 결정성(같은 인스턴스 재호출=같은 obj=상태 무오염)을 확인한다.
production은 fork당 1콜이라 이 경로를 안 타지만(=서버 거동 불변), 멀티콜 성숙도는 측정 편의+방어.
"""
import sys, os, json, copy
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from raster_engine import InstanceRaster
from c_engine import run_c_engine, c_engine_available

assert c_engine_available(), "★.so 로드 실패(ctypes.CDLL)"

def load(name):
    return json.load(open(os.path.join(ROOT, "train", f"{name}.json")))

p1, p20, p5 = load("prob_1"), load("prob_20"), load("prob_5")
big = copy.deepcopy(p20)
big["blocks"] = [copy.deepcopy(b) for _ in range(3) for b in p20["blocks"]]  # 900-혼잡(대형 upN)

# 서로 다른 베이/크기 → upN 크기 변동. 소형→gap→대형(900)→gap→소형: 옛 .so 크래시 시퀀스.
seq = [("prob_1", p1), ("prob_20", p20), ("big900", big),
       ("prob_5", p5), ("prob_20", p20), ("prob_1", p1)]
objs = {}
for i, (name, prob) in enumerate(seq, 1):
    ir = InstanceRaster(prob)
    res = run_c_engine(ir, prob, timeout=12.0)   # deadline 없음 → max_s=0(무제한·4순서 전부·결정적)
    if res is None:
        print(f"  call {i} {name:7}: None (폴백 — 크래시 아님)")
        continue
    obj, _sol = res
    print(f"  call {i} {name:7}: obj={obj:,.0f}")
    objs.setdefault(name, []).append(obj)

ok = True
for name, vals in objs.items():
    uniq = set(vals)
    if len(uniq) > 1:
        print(f"  ★비결정(상태오염) {name}: {vals}"); ok = False
    elif len(vals) > 1:
        print(f"  결정성 {name}: {vals[0]:,.0f} ×{len(vals)} 일치 ✓")
print("PASS — 멀티콜 무크래시 + 재호출 결정성(상태 무오염)" if ok
      else "FAIL — 멀티콜 상태 오염")
sys.exit(0 if ok else 1)
