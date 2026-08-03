# -*- coding: utf-8 -*-
"""3차-1 — KCD 코드로 필터링 (V01~Y98)

KCD 제20장 V01~Y98 은 **사고·가해의 원인**을 나타내는 코드다. 진료 문서
번역용 용어로는 쓸모가 적다.

  [제거] Accident NOS     → 사고 NOS        (X59.9)
  [제거] Assault by arson → 방화에 의한 가해  (X97)

■ 코드가 **하나라도** V~Y 면 제거하는 방식(ANY)은 쓰면 안 된다.
  Asphyxiation → 질식 의 KCD 는 T71|W84 인데 T71 은 정상 질병코드다.
  ANY 기준이면 질식·성폭행·육체적 학대 같은 정상 용어 7행이 같이 죽는다.
  → **모든 코드가 V~Y 일 때만(ALL)** 제거한다.

KCD 필드는 다중값이다. 복수매핑 `|`, 범위 `-`, 이중분류(검표†·별표*) `&`.

  91,937 → 91,715
"""
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filter_common as fc

CODE = re.compile(r"^([A-Z])(\d)")
EXTERNAL = re.compile(r"^[VWXY]\d")


def codes(v):
    return [t.strip() for t in re.split(r"[&|\-]", v) if CODE.match(t.strip())]


def classify_kcd(v):
    c = codes(v)
    if not c:
        return "코드없음"
    ext = [bool(EXTERNAL.match(t)) for t in c]
    if all(ext):
        return "전부외인"
    if any(ext):
        return "일부외인"
    return "외인아님"


def main():
    d = pd.read_csv(fc.w("stage2.csv"), dtype=str, keep_default_na=False)
    print(f"[3차-1] 입력 {len(d):,}행")

    d["KCD외인판정"] = d["KCD"].map(classify_kcd)
    print(d["KCD외인판정"].value_counts().to_string())

    part = d[d["KCD외인판정"] == "일부외인"]
    if len(part):
        print("\n  ANY 기준이었으면 잘못 제거됐을 행 (전부 정상 용어):")
        for _, r in part.iterrows():
            print(f"    {r['영문명']} → {r['한글명']}  ({r['KCD']})")

    rm = d[d["KCD외인판정"] == "전부외인"]
    rm.to_csv(fc.w("removed_stage3_kcd.csv"), index=False, encoding="utf-8-sig")
    keep = d[d["KCD외인판정"] != "전부외인"]
    keep.to_csv(fc.w("stage3.csv"), index=False, encoding="utf-8-sig")
    print(f"\n  3차-1 통과: {len(keep):,}행 (제거 {len(rm):,})")


if __name__ == "__main__":
    main()
