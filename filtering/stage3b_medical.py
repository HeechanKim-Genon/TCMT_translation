# -*- coding: utf-8 -*-
"""3차-2 — 비의학용어를 LLM으로 필터링

의료와 상관없는 사무·행정 용어를 뺀다.

  [제거] Accounting, Absentee, 1st classification, 24 hours, 3D
  [채택] Abomasum, Abortifacient, Aboral

판정 단위는 **영문명**이다(한글 후보는 문맥으로만 붙여 준다). 애매하면 보존.

  91,715 → 87,741

여러 프로세스로 나눠 돌리려면:  python3 stage3b_medical.py --slice 0 340
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filter_common as fc

SYSTEM = """너는 한국 보건의료용어표준(KOSTOM) 사전을 정제하는 의학 용어 심사관이다.
입력으로 "영어용어 | 한국어대응어" 목록이 번호와 함께 주어진다.
각 항목이 **의료 도메인 전문용어**인지 판정하라.

m=1 (전문용어 → 사전에 유지):
- 해부구조, 질병/증상/징후, 진단명, 수술/시술/처치, 임상검사, 약물/성분, 의료기기/재료,
  간호행위/간호진단, 미생물/병원체, 치과/한의학 용어, 의학 약어(AML, ABO 등)
- 일반 영어 단어라도 의료 맥락에서 특수한 표준 한국어 대응어를 갖는 경우
  (예: Discharge|퇴원, Delivery|분만, Impression|인상)

m=0 (전문용어 아님 → 제거):
- 순수 일반 어휘/사무 용어: Table, Yes, No, Total, Monday, Blue, Other, Unknown, Report, Name, Number
- 행정/서식/시스템 용어로 의학적 내용이 없는 것
- 단순 수량·단위·색상·방향·시간 표현 자체
- 사람 이름/지명/기관명 단독
- 한국어 대응어가 용어가 아니라 문장/설명인 경우

애매하면 m=1 (보존 우선).
출력은 JSON 배열만. 설명 금지. 형식: [{"i":번호,"m":0또는1}]
모든 번호를 빠짐없이 포함하라."""


def main():
    d = pd.read_csv(fc.w("stage3.csv"), dtype=str, keep_default_na=False)
    print(f"[3차-2] 입력 {len(d):,}행")

    # 영문명 단위 판정. 한글 후보는 최대 4개까지 문맥으로 붙인다.
    g = d.groupby("영문명")["한글명"].apply(
        lambda s: ";".join(list(dict.fromkeys(s))[:4]))
    pairs = [(en, ko) for en, ko in g.items()]

    lo, hi = fc.slice_args(sys.argv)
    v = fc.judge_pairs(pairs, SYSTEM, fc.w("verdicts_stage3b.jsonl"), lo, hi)

    by_en = {en: m for (en, _ko), m in v.items()}
    d["3차2판정"] = d["영문명"].map(lambda e: "제거:비의학용어" if by_en.get(e, 1) == 0 else "보존")

    rm = d[d["3차2판정"] == "제거:비의학용어"]
    keep = d[d["3차2판정"] == "보존"]
    rm.to_csv(fc.w("removed_stage3b_medical.csv"), index=False, encoding="utf-8-sig")
    keep.to_csv(fc.w("stage3b.csv"), index=False, encoding="utf-8-sig")
    print(f"\n  3차-2 통과: {len(keep):,}행 (제거 {len(rm):,})")


if __name__ == "__main__":
    main()
