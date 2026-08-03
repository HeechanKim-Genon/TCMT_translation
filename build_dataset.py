# -*- coding: utf-8 -*-
"""STEP 0 — 가상 데이터셋 생성

세 단계(a 단어 / b 문장 / c 문단)가 **같은 용어 집합**을 쓰도록 한 번에 만든다.
그래야 a/b/c 점수를 직접 비교할 수 있다.

생성물 (dataset/)
  terms.json        평가 용어 N개 (정답 한글명 집합 포함)
  sentences.json    b용 — 용어 1개가 든 캐리어 문장
  paragraphs.json   c용 — 용어 K개가 든 임상 문단 (Qwen 생성 + 검증 통과분)

■ 문단 생성은 Qwen3.5-397B로 한다 (GLM이 아님)
  GLM이 만든 문장을 GLM이 번역하면 자기 선호 편향이 생긴다. 호출을 분리해도
  가중치는 같으므로 모델 자체를 분리해야 한다.

■ 문단 검증 4종 (하나라도 실패하면 재생성)
  1. 대상 용어가 원문 그대로 등장하는가
  2. 한글이 섞이지 않았는가
  3. 용어 뒤에 동격 설명이 붙지 않았는가  ← 정답을 흘리면 번역이 쉬워짐
  4. 길이가 목표 범위인가

실행:
  python3 build_dataset.py                     # 기본: 용어 200, 문단 20
  python3 build_dataset.py --terms 300 --paras 30 --per-para 8
  python3 build_dataset.py --paras 0           # 문단 생략 (a·b만 준비)
"""
import argparse
import json
import os
import random
import re

import tcmt_common as T

# ── b용 캐리어. 관사를 쓰지 않는다 (`a vulvodynia`는 비문)
#    용어 유형이 안 맞는 캐리어는 오역을 유도한다
#    (실측: `Delivery record`를 환자 소견 캐리어에 넣으면 '투여 기록'/'배달 기록')
#    유형은 사전의 코드 컬럼으로 판정 (tcmt_common.term_type)
CARRIERS = {
    "dx":      "The report documented {T} in this patient.",
    "proc":    "{T} was performed on this patient.",
    "lab":     "The laboratory result for {T} was reviewed.",
    "generic": "The doctor's document mentioned {T}.",
}

GEN_SYS = (
    "You write short, realistic English clinical note paragraphs.\n"
    "Rules you must follow exactly:\n"
    "- Use every given term VERBATIM, spelled exactly as provided.\n"
    "- Do NOT explain, define, gloss, or appose any term "
    "(never write 'X, which is ...' or 'X (a type of ...)').\n"
    "- Write English only. No Korean, no other language.\n"
    "- Plain prose. No bullet points, no headings, no markdown.\n"
    "- Output the paragraph only, nothing else."
)

APPOS = re.compile(r",\s*(a|an|the|which|that)\b", re.I)
HANGUL = re.compile(r"[가-힣]")


def gen_paragraph(terms, target_words):
    lst = "\n".join(f"- {t['en']}" for t in terms)
    user = (f"Write ONE clinical note paragraph of about {target_words} words.\n"
            f"It must contain all of these terms verbatim:\n{lst}\n\n"
            f"Paragraph:")
    txt, _, err = T.call(T.QWEN, [{"role": "system", "content": GEN_SYS},
                                  {"role": "user", "content": user}],
                         max_tokens=900, temperature=0.7)
    return txt, err


def validate(text, terms, lo, hi):
    """(ok, 실패이유목록)"""
    bad = []
    if not text:
        return False, ["empty"]
    low = text.lower()
    missing = [t["en"] for t in terms if t["en"].lower() not in low]
    if missing:
        bad.append(f"missing:{len(missing)}")
    if HANGUL.search(text):
        bad.append("hangul_in_source")
    for t in terms:
        i = low.find(t["en"].lower())
        if i >= 0 and APPOS.match(text[i + len(t["en"]):i + len(t["en"]) + 12] or ""):
            bad.append(f"gloss:{t['en']}")
    w = len(text.split())
    if not (lo <= w <= hi):
        bad.append(f"len:{w}")
    if re.search(r"^\s*[-*#]|\n\s*[-*#]", text):
        bad.append("markdown")
    return (not bad), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terms", type=int, default=200, help="평가 용어 수")
    ap.add_argument("--paras", type=int, default=20, help="문단 수 (0이면 생략)")
    ap.add_argument("--per-para", type=int, default=8, help="문단당 용어 수")
    ap.add_argument("--words", type=int, default=180, help="문단 목표 단어수")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--attempts", type=int, default=4, help="문단 재생성 최대 횟수")
    ap.add_argument("--dict", default=None,
                    help="사전 CSV 경로. 생략시 최종번역사전 전체. "
                         "빠른 점검은 --dict sample2000")
    a = ap.parse_args()

    dpath = a.dict
    if dpath in ("sample2000", "s2000"):
        dpath = T.DICT_S2000
    print("사전 로드 중…", flush=True)
    D = T.load_dict(dpath)

    # ── 용어 표본
    terms = T.sample_terms(D, a.terms, seed=a.seed, multiword_ratio=0.7)
    print(f"  용어 {len(terms)}개 "
          f"(다어절 {sum(1 for t in terms if t['words']>1)} / "
          f"단일어 {sum(1 for t in terms if t['words']==1)} / "
          f"KCD보유 {sum(1 for t in terms if t['kcd'])})")
    json.dump(terms, open(os.path.join(T.DATA_DIR, "terms.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  저장 → {os.path.join(T.DATA_DIR, 'terms.json')}")

    # ── b용 문장 (API 호출 없음 — 템플릿). 유형별 캐리어 사용
    sents = []
    for t in terms:
        car = CARRIERS[t.get("type", "generic")]
        sents.append({**t, "carrier": car, "sentence": car.replace("{T}", t["en"])})
    import collections as _c
    print(f"  캐리어 유형 분포: {dict(_c.Counter(t.get('type') for t in terms))}")
    json.dump(sents, open(os.path.join(T.DATA_DIR, "sentences.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  저장 → {os.path.join(T.DATA_DIR, 'sentences.json')}  ({len(sents)}건)")

    json.dump({"dict_path": D["path"], "config": vars(a)},
              open(os.path.join(T.DATA_DIR, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    if a.paras <= 0:
        print("\n문단 생성 생략 (--paras 0)")
        return

    # ── c용 문단 (Qwen 생성 + 검증)
    print(f"\n문단 {a.paras}개 생성 ({T.QWEN['name']}, 문단당 용어 {a.per_para}개)…")
    rnd = random.Random(a.seed + 1)
    pool = terms[:]
    rnd.shuffle(pool)
    groups = [pool[i:i + a.per_para]
              for i in range(0, len(pool), a.per_para)][:a.paras]
    lo, hi = int(a.words * 0.55), int(a.words * 1.9)

    def build(g):
        last = {"terms": g, "attempts": a.attempts, "reject": ["no_response"]}
        for k in range(a.attempts):
            txt, err = gen_paragraph(g, a.words)
            if not txt:
                last = {"terms": g, "attempts": k + 1,
                        "reject": [f"api:{(err or 'empty')[:40]}"]}
                continue
            ok, bad = validate(txt, g, lo, hi)
            if ok:
                return {"terms": g, "text": txt, "attempts": k + 1, "rejected": []}
            last = {"terms": g, "text": txt, "attempts": k + 1, "reject": bad}
        return {**last, "text": None, "failed": True}

    res = T.pmap(groups, build, desc="문단 ")
    T.netguard("문단생성")
    ok = [r for r in res if r and r.get("text")]
    fail = [r for r in res if not (r and r.get("text"))]
    print(f"\n  생성 성공 {len(ok)}/{len(groups)}   재시도 평균 "
          f"{sum(r['attempts'] for r in ok)/max(1,len(ok)):.1f}회")
    if fail:
        print(f"  실패 {len(fail)}건 사유: "
              f"{[r.get('reject') for r in fail][:4]}")

    # 생성된 문단에서 실제 매칭되는 용어도 같이 기록 (c의 매칭 단계 검증용)
    for i, r in enumerate(ok):
        r["id"] = f"P{i+1:03d}"
        r["words"] = len(r["text"].split())
        hits = T.match_terms(r["text"], D)
        r["matched_all"] = [h["term"] for h in hits]
        tgt = {t["en"] for t in r["terms"]}
        r["matched_target"] = sorted(tgt & set(r["matched_all"]))
        r["missed_target"] = sorted(tgt - set(r["matched_all"]))
        r["extra_matched"] = sorted(set(r["matched_all"]) - tgt)

    json.dump(ok, open(os.path.join(T.DATA_DIR, "paragraphs.json"), "w",
                       encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  저장 → {os.path.join(T.DATA_DIR, 'paragraphs.json')}")

    tt = sum(len(r["terms"]) for r in ok)
    mt = sum(len(r["matched_target"]) for r in ok)
    ex = sum(len(r["extra_matched"]) for r in ok)
    print(f"\n  ■ 매칭기 자체 점검 (심은 용어를 다시 찾아내는가)")
    print(f"     심은 용어 {tt}개 중 재매칭 {mt}개 ({mt/max(1,tt)*100:.1f}%)")
    print(f"     심지 않았는데 매칭된 것 {ex}개  ← 문단에 자연발생한 사전 용어")
    print(f"     평균 문단 길이 {sum(r['words'] for r in ok)/max(1,len(ok)):.0f}단어")
    print(f"\n{T.usage_report()}")


if __name__ == "__main__":
    main()
