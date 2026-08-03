# -*- coding: utf-8 -*-
"""5차 — 사전 없이도 맞게 번역되는 일상어 제거

3차-2 는 "의학 도메인 용어인가"를 물었다. 그런데 이 사전의 목적은 **오역
교정**이므로, 물어야 할 것은 "사전 없이 번역하면 틀리는가"다.
Ability → 능력 은 의료 문서에 나오긴 하지만 사전이 없어도 맞게 번역된다.

  [제거] Ability|능력  /minute|분당  Baby|아기  Gold|금  Position change|체위변경
  [채택] Discharge|퇴원  Sinus|굴  Cardiac ventricle|심실  HIV|사람면역결핍바이러스

■ 판정은 반드시 **(영문명, 한글명) 쌍 단위**로 한다.
  영문명 단위로 하면 한 단어의 한글 후보를 전부 살리거나 전부 죽여야 한다.
  쌍 단위라서 Toe 는 '발가락'만 빠지고 '지'는 남았다.
  Discharge 는 유출량·방출·방전·분비물·유리·퇴원·귀가가 전부 남았다.

  86,425 → 77,497
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filter_common as fc

SYSTEM = """너는 EN→KO 의료 번역용 용어사전을 정제한다.
이 사전의 목적은 **번역 LLM이 사전 없이 번역하면 틀리는 용어를 교정**하는 것이다.
따라서 사전 없이도 자명하게 맞게 번역되는 항목은 넣을 가치가 없다.

각 "영어 | 한국어표준어" 쌍을 판정하라.

m=0 (사전 불필요 → 제거):
- 일상 어휘이고 표준 대응어도 그 일상적 번역과 같은 것
  (Ability|능력, /minute|분당, Access|접근, Baby|아기, Toe|발가락, Gold|금, Smoke|연기)
- 숫자·단위·시간·색상·방향·정도 표현
- 행정/사무/서식 용어 (Death certificate number|사망진단서번호)
- 영어를 그대로 직역한 일반명사구 (Position change|체위변경, Low salt|저염)

m=1 (사전 필요 → 유지):
- 전문 의학용어: 해부·질병·시술·검사·약물·기기·간호진단·미생물·치과·한의학
- 의학 약어와 그 풀네임 (HIV, ERCP, TIPS)
- 라틴어/그리스어 어근 및 결합형 (Massa, Thrix, Cellular|세포-)
- 일상 단어지만 의료 맥락의 표준 대응어가 일반 번역과 **다른** 것
  (Discharge|퇴원, Delivery|분만, Impression|인상, Presentation|태위, Culture|배양, Sinus|굴)
- 한국어 표준어가 일반인이 떠올릴 표현과 달라 오역 위험이 있는 것
  (Cardiac ventricle|심실, Nares|비공, Tingling|저림)

애매하면 m=1.
출력은 JSON 배열만: [{"i":번호,"m":0또는1}]"""


def main():
    d = pd.read_csv(fc.w("stage4.csv"), dtype=str, keep_default_na=False)
    print(f"[5차] 입력 {len(d):,}행")

    pairs = [tuple(p) for p in d[["영문명", "한글명"]].drop_duplicates().values.tolist()]
    lo, hi = fc.slice_args(sys.argv)
    v = fc.judge_pairs(pairs, SYSTEM, fc.w("verdicts_stage5.jsonl"), lo, hi)

    key = list(zip(d["영문명"], d["한글명"]))
    d["5차판정"] = ["제거:사전불필요" if v.get(k, 1) == 0 else "보존" for k in key]

    rm = d[d["5차판정"] == "제거:사전불필요"]
    keep = d[d["5차판정"] == "보존"]
    rm.to_csv(fc.w("removed_stage5_trivial.csv"), index=False, encoding="utf-8-sig")
    keep.to_csv(fc.w("stage5.csv"), index=False, encoding="utf-8-sig")
    print(f"\n  5차 통과(최종): {len(keep):,}행 (제거 {len(rm):,})")


if __name__ == "__main__":
    main()
