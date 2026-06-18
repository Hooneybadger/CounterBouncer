#!/usr/bin/env python
"""p4b_obj3_breakdown.py -- destroy_pref(obj3 타깃)의 효과를 obj 성분별로 본다.

batch_runner의 compare는 가중 objective만 보여줘서, 개선이 obj3(선호) 덕인지 obj2(부하)
덕인지 가린다. 이 스크립트는 두 결과 디렉터리의 summary.csv를 읽어 인스턴스별
obj1/obj2/obj3 raw 값을 나란히 찍고, 특히 obj1=0 집합(선호가 목적의 거의 전부인 곳)의
obj3 합계 변화를 따로 집계한다.

사용: python learning/p4b_obj3_breakdown.py results/<base> results/<dev>
"""
import csv
import sys
import pathlib


def load(d):
    rows = {}
    with open(pathlib.Path(d) / "summary.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["status"] != "ok":
                rows[r["instance"]] = None
                continue
            rows[r["instance"]] = {
                "objective": float(r["objective"]),
                "obj1": float(r["obj1"]), "obj2": float(r["obj2"]),
                "obj3": float(r["obj3"]),
            }
    return rows


def main():
    base_dir, dev_dir = sys.argv[1], sys.argv[2]
    base, dev = load(base_dir), load(dev_dir)
    insts = sorted(set(base) & set(dev),
                   key=lambda s: int("".join(c for c in s if c.isdigit())))

    print(f"{'inst':<9}{'obj1':>8}{'obj2_b':>8}{'obj2_d':>8}"
          f"{'obj3_b':>8}{'obj3_d':>8}{'d_obj3':>8}{'d_obj%':>8}")
    print("-" * 65)
    z_o3b = z_o3d = 0.0       # obj1=0 집합 obj3 합
    all_o3b = all_o3d = 0.0   # 전체 obj3 합
    n_zero = 0
    for i in insts:
        b, d = base[i], dev[i]
        if b is None or d is None:
            print(f"{i:<9}  (invalid in base or dev)")
            continue
        do3 = d["obj3"] - b["obj3"]
        pct = (do3 / b["obj3"] * 100) if b["obj3"] else 0.0
        zero = b["obj1"] == 0
        mark = "*" if zero else " "
        print(f"{i:<9}{b['obj1']:>8.0f}{b['obj2']:>8.0f}{d['obj2']:>8.0f}"
              f"{b['obj3']:>8.0f}{d['obj3']:>8.0f}{do3:>8.0f}{pct:>7.1f}%{mark}")
        all_o3b += b["obj3"]; all_o3d += d["obj3"]
        if zero:
            z_o3b += b["obj3"]; z_o3d += d["obj3"]; n_zero += 1

    print("-" * 65)
    print(f"obj1=0 집합({n_zero}개)  obj3: {z_o3b:.0f} -> {z_o3d:.0f}  "
          f"(Δ {z_o3d - z_o3b:+.0f}, {(z_o3d/z_o3b - 1)*100 if z_o3b else 0:+.1f}%)")
    print(f"전체           obj3: {all_o3b:.0f} -> {all_o3d:.0f}  "
          f"(Δ {all_o3d - all_o3b:+.0f}, {(all_o3d/all_o3b - 1)*100 if all_o3b else 0:+.1f}%)")
    print("(* = obj1=0 인스턴스: 선호가 목적의 거의 전부)")


if __name__ == "__main__":
    main()
