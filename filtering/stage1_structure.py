# -*- coding: utf-8 -*-
"""1차 — A/B/C/G 유형 제거 → 1~3단어만 채택

원본 엑셀(33.9만 행)을 읽어 영문명을 A~G 로 분류하고, 사전 엔트리로 쓸 수
없는 유형을 뺀다. 판정 기준 컬럼은 **영문명**이다.

  [제거] A Ab:Pr:Pt:Ser/Plas:Ord                              ← A. 콜론 축 조합
  [제거] Endarterectomy with temporary bypass during procedure ← G. 4단어 이상
  [채택] Cardiac ventricle → 심실

A·B(축 조합 108,462행)는 버린 게 아니라 **별도 로직 대상**이다. LOINC 6축을
기계적으로 이어붙인 좌표 문자열이라 통짜 사전 엔트리로 만들면 안 된다.
GLM-5.2 실측: 사전 없이 번역하면 표준 완전일치 0/10, 사전을 주면 10/10.

  339,181 → 119,914
"""
import os
import sys

import openpyxl
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filter_common as fc


def main():
    if not fc.SRC_XLSX or not os.path.exists(fc.SRC_XLSX):
        sys.exit("KOSTOM_XLSX 환경변수에 보건의료용어표준 V7.0 엑셀 경로를 지정하라.")

    print(f"[1차] 원본 로드 — {fc.SRC_XLSX}")
    wb = openpyxl.load_workbook(fc.SRC_XLSX, read_only=True, data_only=True)
    it = wb["V7.0"].iter_rows(values_only=True)
    header = list(next(it))
    idx = {c: i for i, c in enumerate(header)}
    cols = ["용어코드", "개념코드", "영문명", "한글명", "KCD"] + fc.REF_COLS
    rows = []
    for r in it:
        if r[0] is None:
            continue
        rows.append([("" if r[idx[c]] is None else str(r[idx[c]]).strip()) for c in cols])
    wb.close()

    df = pd.DataFrame(rows, columns=cols)
    df["구조유형"] = df["영문명"].map(fc.classify)
    df.to_csv(fc.w("stage0_all.csv"), index=False, encoding="utf-8-sig")

    print(f"  전체 {len(df):,}행")
    for t, n in df["구조유형"].value_counts().items():
        mark = "채택" if t in fc.KEEP_TYPES else "제거"
        print(f"    [{mark}] {t}: {n:,}")

    keep = df[df["구조유형"].isin(fc.KEEP_TYPES)].copy()
    keep.to_csv(fc.w("stage1.csv"), index=False, encoding="utf-8-sig")
    print(f"\n  1차 통과: {len(keep):,}행")


if __name__ == "__main__":
    main()
