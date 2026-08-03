# -*- coding: utf-8 -*-
"""(b) 문장 단위 — 자연스러운 문장으로 번역, span으로 답 추출

3-mode 교차 실험을 문장 단위로 적용한다.
  none    용어집 없음                      ← baseline
  term    해당 용어의 정답 한글명 제공        ← terminology
  random  다른 용어의 한글명을 잘못 제공      ← random (통제군)

■ random arm이 이 설계의 핵심 통제다.
  틀린 한글명을 줬는데 모델이 그걸 따라가면 = 용어집을 실제로 읽고 있다.
  무시하면 = 용어집이 작동하지 않는 것이고, term arm의 개선도 우연이다.
  즉 random 준수율이 term arm 결과의 인과성을 보증한다. (WMT23 3-mode 설계)

■ 출력은 2필드로 받는다
    KO:    문장 전체 번역
    TERM:  KO에서 해당 용어에 대응하는 부분을 그대로 잘라낸 것
  TERM ⊂ KO 인지 코드로 검증 → **추출 실패와 모델 오답이 섞이지 않는다.**
  (파일럿 실측: 위반 0/200)

■ 조사 처리
  TERM에 조사가 딸려 나온다 (`크립토스포리디움을`). 파괴적으로 떼지 않고
  tcmt_common.grade() 가 뗀 형태도 후보로 인정한다.

실행:
  python3 build_dataset.py --paras 0
  python3 run_b_sentence.py                       # 3 mode 전부
  python3 run_b_sentence.py --modes none,term
  python3 run_b_sentence.py --limit 50
  python3 run_b_sentence.py --no-span             # span 요구 없이 순수 번역 (관찰자효과 대조)

결과: results/b_sent_{mode}.json / b_sent_summary.json / b_sent_rows.csv
"""
import argparse
import json
import os
import random
import re

import tcmt_common as T

BADCH = re.compile(r"[A-Za-z()（）\[\]{}\"']")


def sys_span(term):
    return ("Fill KO with the Korean translation of EN.\n"
            f"Fill TERM by copying, from your KO text, the exact substring "
            f"for \"{term}\".\n"
            "Do not re-translate it — copy it from your translation.\n"
            "Output only the two fields.")


SYS_PLAIN = ("Translate EN into Korean. Output only the Korean translation, "
             "nothing else.")


def glossary_line(mode, item, decoy):
    if mode == "none":
        return ""
    ko = item["rep"] if mode == "term" else decoy
    return f"GLOSSARY: {item['en']} = {ko}\n"


def parse_two(txt):
    t = (txt or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?|```$", "", t).strip()
    mk = re.search(r"(?im)^\s*KO\s*:\s*(.+)$", t)
    mt = re.search(r"(?im)^\s*TERM\s*:\s*(.+)$", t)
    ko = T.norm(mk.group(1)) if mk else ""
    tm = T.norm(mt.group(1)) if mt else ""
    iss = []
    if not mk:
        iss.append("no_KO")
    if not mt:
        iss.append("no_TERM")
    if tm and ko and tm not in ko:
        iss.append("span_not_substring")      # 추출 실패 — 오답과 분리
    if tm and BADCH.search(tm):
        iss.append("bad_chars")
    return ko, tm, iss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="none,term,random")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-span", action="store_true",
                    help="span 요구 없이 순수 번역만 (관찰자 효과 대조군)")
    a = ap.parse_args()

    sp = os.path.join(T.DATA_DIR, "sentences.json")
    if not os.path.exists(sp):
        raise SystemExit("먼저 실행: python3 build_dataset.py --paras 0")
    sents = json.load(open(sp, encoding="utf-8"))
    if a.limit:
        sents = sents[:a.limit]
    modes = [m.strip() for m in a.modes.split(",") if m.strip()]

    # random arm용 오답 한글명 — 시드 고정으로 재현 가능
    rnd = random.Random(a.seed + 3)
    pool = [s["rep"] for s in sents]
    decoy = {}
    for s in sents:
        while True:
            c = rnd.choice(pool)
            if c != s["rep"] and c not in s["answers"]:
                decoy[s["en"]] = c
                break

    print(f"(b) 문장 단위 · {len(sents)}건 · mode {modes} · 모델 {T.GLM['name']}")
    print(f"    span 추출 {'끔(순수번역)' if a.no_span else '켬(2필드)'}\n")

    summary, allrows = [], []
    for mode in modes:
        print(f"── mode={mode}")

        def f(it, mode=mode):
            gl = glossary_line(mode, it, decoy.get(it["en"], ""))
            if a.no_span:
                user = f"{gl}EN: {it['sentence']}"
                sysm = SYS_PLAIN
            else:
                user = f"{gl}EN: {it['sentence']}\nKO:\nTERM:"
                sysm = sys_span(it["en"])
            txt, fin, err = T.call(T.GLM,
                                   [{"role": "system", "content": sysm},
                                    {"role": "user", "content": user}],
                                   max_tokens=900)
            base = {"en": it["en"], "rep": it["rep"], "answers": it["answers"],
                    "kcd": it.get("kcd"), "words": it["words"],
                    "carrier": it["carrier"], "sentence": it["sentence"],
                    "mode": mode, "glossary_given": gl.strip() or None,
                    "decoy": decoy.get(it["en"]) if mode == "random" else None,
                    "finish": fin, "raw": txt}
            if err and not txt:
                return {**base, "ko": "", "term": "", "issues": ["api_error"],
                        "grade": "형식실패", "level": "-", "error": err}
            if a.no_span:
                ko, tm, iss = T.norm(txt), "", []
                # span 없이는 문장 안에 정답이 들어있는지로 채점
                hit, which = T.contains_answer(ko, it)
                g = "정답(대표)" if which == T.norm(it["rep"]) else (
                    "정답(동의어)" if hit else "오답")
                lv = "contains" if hit else "-"
            else:
                ko, tm, iss = parse_two(txt)
                g, lv = T.grade(tm, it)
            r = {**base, "ko": ko, "term": tm, "issues": iss,
                 "grade": g, "level": lv}
            if mode == "random":
                # 틀린 용어집을 따라갔는가 = 용어집을 읽고 있는가
                d = T.norm(decoy.get(it["en"], ""))
                r["followed_decoy"] = bool(d) and (
                    d in T.norm(tm or ko) or
                    d.replace(" ", "") in T.norm(tm or ko).replace(" ", ""))
            return r

        rows = T.pmap(sents, f, desc=f"{mode} ")
        T.netguard(f"b:{mode}")
        T.print_tally(f"mode={mode}", rows)
        iss = {}
        for r in rows:
            for i in r.get("issues", []):
                iss[i] = iss.get(i, 0) + 1
        if iss:
            print(f"   이슈: {iss}")
        sub = sum(1 for r in rows if "span_not_substring" in r.get("issues", []))
        if not a.no_span:
            print(f"   span이 KO의 부분문자열 아님: {sub}/{len(rows)}  ← 추출실패로 분리")
        fol = None
        if mode == "random":
            fol = sum(1 for r in rows if r.get("followed_decoy"))
            print(f"   ★ 오답 용어집 추종률 {fol}/{len(rows)} "
                  f"({fol/len(rows)*100:.1f}%)  ← 높아야 용어집이 작동 중이라는 증거")
        corr = sum(1 for r in rows if r["grade"].startswith("정답"))
        summary.append({"mode": mode, "n": len(rows),
                        "correct_pct": round(corr / len(rows) * 100, 1),
                        "grades": T.tally(rows), "issues": iss,
                        "span_violation": sub,
                        "followed_decoy_pct": (round(fol / len(rows) * 100, 1)
                                               if fol is not None else None)})
        T.save(f"b_sent_{mode}.json", rows)
        allrows += rows

    print("\n" + "=" * 72)
    print(f"{'mode':<10}{'n':>5}{'정답':>8}{'오답용어집추종':>14}")
    for s in summary:
        fd = f"{s['followed_decoy_pct']}%" if s["followed_decoy_pct"] is not None else "-"
        print(f"{s['mode']:<10}{s['n']:>5}{s['correct_pct']:>7.1f}%{fd:>14}")

    # 페어 비교 — 같은 용어에 대해 mode별 결과가 어떻게 바뀌는지
    if len(summary) > 1:
        print("\n■ 페어 비교 (기준: none)")
        bym = {}
        for r in allrows:
            bym.setdefault(r["mode"], {})[r["en"]] = r["grade"].startswith("정답")
        base = bym.get("none", {})
        for m, d in bym.items():
            if m == "none":
                continue
            win = sum(1 for k in d if d[k] and not base.get(k))
            los = sum(1 for k in d if not d[k] and base.get(k))
            print(f"   none→{m:<8} 개선 {win:>4}  악화 {los:>4}  순증 {win-los:+d}")

    print(f"\n{T.usage_report()}")
    T.save("b_sent_summary.json", {"summary": summary, "usage": T.USAGE,
                                   "config": vars(a)})
    T.save_csv("b_sent_rows.csv", allrows,
               ["mode", "en", "rep", "term", "ko", "grade", "level",
                "followed_decoy", "decoy", "issues", "finish", "sentence"])


if __name__ == "__main__":
    main()
