# -*- coding: utf-8 -*-
"""4차 — 한글명이 긴 설명문·EDI 수가명인 경우 제거

영문은 2~3단어로 짧은데 한글 쪽에만 부가설명이 잔뜩 붙은 행. 원인은 사실상
하나다 — 보험 수가(EDI) 명칭이 용어 자리에 들어와 있다.
EDI 코드가 있는 행의 한글명은 평균 19.9자, 없는 행은 5.6자다.

  [제거] Multiplex Group 2 → 핵산증폭-다종그룹2-통합자동진단키트를 이용하여 검사처방부터
                            결과보고까지 4~6시간 이내 신속한 결과보고를 한 경우_
                            뇌수막염/뇌염/수막뇌염 병원체(바이러스, 세균, 진균)   (94자)

■ 길이만 보고 자르면 안 된다. 실측한 것:
    "영문 대비 한글 3배 이상"(173행) → 잘리는 게 전부 약어다.
        HIV → 사람면역결핍바이러스,  CT → 컴퓨터단층촬영(술),
        TIPS → 경정맥경유간내문맥전신순환션트          ← 사전에서 제일 가치 있는 항목
    "한글 4어절 이상"(1,129행) → 이것만 걸리는 749행이 대부분 정상 용어다.
        Mouth-to-mouth resuscitation → 구강 대 구강 인공소생술
    "한글 20자 초과" → 단독으로는 위험하다.
        Waterhouse-Friderichsen syndrome(Meningoccal) → 워터하우스-프리데릭센증후군(수막구균성)

  → 그래서 **2단계**로 간다.
      1) 룰로 후보만 뽑는다 (재현율 우선) — 2,715행
      2) 그 후보 안에서 LLM 이 "용어인가 설명문인가"를 판정한다 (정밀도)

  87,741 → 86,425
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filter_common as fc

SYSTEM = """너는 EN→KO 의료 용어사전을 정제한다.
아래 항목들은 한국어 쪽이 비정상적으로 길어 '용어'가 아닐 가능성이 있어 뽑힌 후보다.
각 "영어 | 한국어" 쌍에서 **한국어가 용어로서 쓸 수 있는 형태인지** 판정하라.

m=1 (유지): 길더라도 정식 표준 용어
- 긴 해부/질환/술기 명칭: 워터하우스-프리데릭센증후군(수막구균성), 추간판절제가 동반된 한쪽척추뼈고리절제술
- '복강경 이용 막창자꼬리 절제'처럼 술기 방식이 용어에 정식으로 포함된 것
- 약어의 풀네임: TIPS|경정맥경유간내문맥전신순환션트
- 괄호 안이 용어의 일부인 것

m=0 (제거): 용어가 아니라 설명문·분류코드 문자열·보험수가(EDI) 명칭
- 수가 명칭 특유의 계층 나열: '기본자기공명영상진단-척추-흉추-제한적(방사선치료범위및위치결정등)'
- 검사법/장비 표기가 덧붙은 것: '헤모글로빈A1C-[정밀분광-질량분석]'
- 산정조건 서술: '…5종목 이상을 실시한 경우에 추가로 실시한 경우 산정'
- 용어가 아니라 정의·부연설명인 것: '좋은 일에 대한 걱정'
- 영어 원문과 대응 범위가 전혀 안 맞고 한국어에만 부가정보가 붙은 것

애매하면 m=1.
출력은 JSON 배열만: [{"i":번호,"m":0또는1}]"""


def candidates(d):
    """LLM 에 물어볼 후보만 뽑는다. 여기서는 재현율만 신경 쓴다."""
    ko = d["한글명"]
    return (ko.str.contains("_", regex=False)          # EDI 세부항목 구분자
            | ko.str.contains(r"\[", regex=True)       # 검사법·장비 표기
            | (ko.str.len() > 20)
            | (ko.str.split().str.len() >= 4)
            | ko.str.contains("하여|한 경우|경우에|이용|위한|실시|산정|등을|동시"))


def main():
    d = pd.read_csv(fc.w("stage3b.csv"), dtype=str, keep_default_na=False)
    print(f"[4차] 입력 {len(d):,}행")

    cand = candidates(d)
    print(f"  룰 기반 후보: {int(cand.sum()):,}행")
    pairs = d[cand][["영문명", "한글명"]].drop_duplicates().values.tolist()
    pairs = [tuple(p) for p in pairs]

    lo, hi = fc.slice_args(sys.argv)
    v = fc.judge_pairs(pairs, SYSTEM, fc.w("verdicts_stage4.jsonl"), lo, hi)

    key = list(zip(d["영문명"], d["한글명"]))
    d["4차판정"] = ["제거:한글명부적합" if v.get(k, 1) == 0 else "보존" for k in key]

    rm = d[d["4차판정"] == "제거:한글명부적합"]
    keep = d[d["4차판정"] == "보존"]
    rm.to_csv(fc.w("removed_stage4_korean.csv"), index=False, encoding="utf-8-sig")
    keep.to_csv(fc.w("stage4.csv"), index=False, encoding="utf-8-sig")
    print(f"\n  4차 통과: {len(keep):,}행 (제거 {len(rm):,})")


if __name__ == "__main__":
    main()
