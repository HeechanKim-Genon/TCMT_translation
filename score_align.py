# -*- coding: utf-8 -*-
"""문단 채점 재측정 — LLM 정렬 기반 (contains 방식의 결함 보정)

■ 왜 필요한가
  기존 채점은 `contains_answer()` 로 **번역문 어딘가에 표준 한글명이 있는가**만 본다.
  그 용어의 번역으로 쓰였는지는 보지 않는다. 그래서 이런 오채점이 난다.

    문단 P001 의 채점 대상: case-mix (정답 = 질병구성)
      · case-mix 에게 준 오답        → 인두편도 생검
      · 같은 문단 renal 에게 준 오답  → 질병구성      ← case-mix 의 정답!
    모델은 renal 을 "질병구성"으로 충실히 번역했는데,
    채점기는 그 "질병구성"을 보고 case-mix 가 맞혔다고 집계한다.

  실측: random 모드 채점 대상 중 100규모 30.0%, 1000규모 2.8% 가 이 상황에 걸린다.
  단순히 걸러내면 하한만 얻는다 (모델이 자기 오답을 무시하고 제대로 번역한 정상
  적중까지 함께 버려진다). 위치를 봐야 제대로 채점된다.

■ 방법 — LLM은 정렬만, 채점은 코드가
  1. LLM에게 영어 문단 + 한국어 번역문 + 대상 영어 용어를 준다
  2. **번역문에서 그 용어에 해당하는 부분을 그대로 잘라내게** 한다 (번역 금지)
  3. 잘라낸 span 이 실제로 번역문의 부분문자열인지 코드로 검증
  4. span 을 정답 집합과 대조해 채점 (tcmt_common.grade — exact/nospace/josa)

  LLM에게 정답을 보여주지 않는다. 보여주면 "정답이 있냐"는 질문이 되어 유도된다.
  채점자는 **Qwen3.5-397B** — 번역한 GLM이 자기 답을 채점하면 자기 선호가 낀다.

■ 부분문자열 검증이 응답 교차 탐지도 겸한다
  다른 요청의 응답이 오면 그 span 은 이 번역문의 부분문자열일 수 없다.

실행:
  python3 score_align.py                      # dataset_/results_ 기본 경로
  python3 score_align.py --tag 1000
  python3 score_align.py --tag 100 --modes random
  python3 score_align.py --tag 100 --limit 20  # 문단 20개로 빠른 점검

결과: results_{tag}/c_para_aligned.json / c_para_aligned.csv
"""
import argparse
import json
import os
import re

import tcmt_common as T

SYS = ("You locate the Korean translation of an English medical term inside a "
       "Korean translation of a document.\n"
       "Rules you must follow exactly:\n"
       "- Copy the span VERBATIM from the Korean text. Do not translate anything "
       "yourself.\n"
       "- Copy the SHORTEST span that renders the given English term. Do not "
       "include surrounding modifiers, particles, or neighbouring words.\n"
       "- If the term was dropped from the translation, or you cannot locate it, "
       "output exactly: NONE\n"
       "- Output the span only. No quotes, no explanation, no label.")

NONE_RE = re.compile(r"^\s*(NONE|없음|N/A|-)\s*$", re.I)

PAREN = re.compile(r"\s*[(（][^)）]*[)）]")


def dict_variants(s):
    """사전 표기 관례를 벗긴 형태들을 후보로 추가한다 (파괴적으로 바꾸지 않는다).

    표준 한글명에는 두 가지 관례가 붙는다.
      · 끝 하이픈  `불수의-`      — 의존 형태소 표시
      · 괄호 한자  `합곡(合谷)`   — 한자·이형태 병기
    번역문에는 이 관례가 그대로 나오기도 하고 빠지기도 한다. 어느 쪽이든
    같은 답이므로 둘 다 인정해야 한다.
    (실측: 이 처리가 없어서 `불수의`·`합곡` 이 오답으로 집계됐다)
    """
    out = set()
    for base in (T.norm(s), PAREN.sub("", T.norm(s))):
        b = base.strip().strip("-–—").strip()
        if b:
            out |= T.ko_variants(b)
    return {x for x in out if x}


def span_grade(span, answers, rep):
    """정렬된 span 을 정답 집합과 대조한다. (판정, 수준)

    ■ span 경계 오차만 흡수한다 — 방향이 중요하다
      채점자가 수식어까지 넓게 자르는 일이 있다 (`proctoscope` → `소아 직장경`).
      **표준명이 span 안에 들어있는 경우만** 정답으로 본다.

      반대 방향은 인정하지 않는다. span 이 표준명보다 짧으면 형태소가 빠진
      것이고, 그건 대개 다른 뜻이다.
          `혈흡충`      vs `주혈흡충`     ← 속(屬)이 다르다
          `신경정신과`   vs `신경정신과학` ← 진료과 vs 학문
          `종양 분류`    vs `종양분류법`
      (실측: 양방향을 허용했더니 none 모드에서 이 세 유형이 정답으로 집계됐다)

      문단 전체가 아니라 정렬된 span 안만 보므로, 위치를 무시하던 기존 방식의
      결함은 되살아나지 않는다.
    """
    if not span:
        return "미검출", "-"
    sv = dict_variants(span)
    for a in answers:
        av = dict_variants(a)
        if sv & av:
            lvl = "exact" if T.norm(span) == T.norm(a) else "variant"
            return ("정답(대표)" if a == rep else "정답(동의어)"), lvl
    sn = T.norm(span).replace(" ", "")
    for a in answers:
        for av in dict_variants(a):
            an = av.replace(" ", "")
            if len(an) >= 2 and an in sn:      # span 이 더 넓은 경우만
                return ("정답(대표)" if a == rep else "정답(동의어)"), "partial"
    return "오답", "-"


# 추종률용 — 위치만 묻는다. 의미가 맞는지는 묻지 않는다.
#   SYS 로는 추종률을 못 잰다. 모델이 그 자리에 엉뚱한 용어를 써 넣으면
#   "이 용어를 옮긴 부분"이 없으므로 채점자가 NONE 을 반환한다.
#   (실측: random 287건 중 207건이 NONE → 추종률이 9.4%로 과소 측정됐다)
SYS_POS = ("You locate the position of an English medical term in a Korean "
           "translation of a document.\n"
           "Rules you must follow exactly:\n"
           "- Find where the English term occurs in the English document, then "
           "copy the Korean text standing at that same position.\n"
           "- Copy it VERBATIM even if it looks like a mistranslation or an "
           "unrelated term. Do not judge, do not correct, do not translate.\n"
           "- If that position was dropped from the translation, output exactly: "
           "NONE\n"
           "- Output the span only. No quotes, no explanation, no label.")


def build_user(en, src, ko, positional=False):
    tail = ("Korean text standing at the position of this term:" if positional
            else "Span from the Korean translation that renders this term:")
    return (f"English document:\n{src}\n\n"
            f"Korean translation:\n{ko}\n\n"
            f"English term: {en}\n{tail}")


def clean_span(txt, ko):
    """(span, 사유). span 이 ko 의 부분문자열이 아니면 버린다."""
    t = T.norm(txt or "")
    if not t:
        return "", "empty"
    t = t.strip().strip('"\'`').strip()
    t = re.sub(r"^(span|answer|정답|번역)\s*[:：]\s*", "", t, flags=re.I)
    if "\n" in t:
        t = t.splitlines()[0].strip()
    if NONE_RE.match(t):
        return "", "none"
    # 공백 차이는 허용하고, 그래도 없으면 교차/환각으로 본다
    if t in ko:
        return t, "ok"
    if t.replace(" ", "") in ko.replace(" ", ""):
        return t, "ok_nospace"
    return "", "not_substring"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="100", help="규모 태그 (dataset_{tag}/ 를 읽는다)")
    ap.add_argument("--modes", default="none,term,random")
    ap.add_argument("--limit", type=int, default=0, help="앞 N개 문단만")
    a = ap.parse_args()

    ddir, rdir = f"dataset_{a.tag}", f"results_{a.tag}"
    for d in (ddir, rdir):
        if not os.path.isdir(d):
            raise SystemExit(f"⛔ {d} 가 없다.")
    paras = {p["id"]: p for p in json.load(open(f"{ddir}/paragraphs.json",
                                               encoding="utf-8"))}
    modes = [m.strip() for m in a.modes.split(",") if m.strip()]

    print(f"문단 채점 재측정 (LLM 정렬) · 규모 {a.tag} · mode {modes} · "
          f"채점자 {T.QWEN['name']}\n")

    out, summary = [], []
    for mode in modes:
        src = json.load(open(f"{rdir}/c_para_{mode}.json", encoding="utf-8"))
        tr = {t["id"]: t for t in src["translations"]}
        rows = [r for r in src["terms"] if r["injected"]]
        if a.limit:
            keep = sorted(tr)[:a.limit]
            rows = [r for r in rows if r["para_id"] in keep]
        print(f"── mode={mode}  대상 {len(rows)}건")

        def f(r):
            t = tr[r["para_id"]]
            ko = t["ko"]
            txt, fin, err = T.call(
                T.QWEN, [{"role": "system", "content": SYS},
                         {"role": "user", "content":
                          build_user(r["en"], t["src"], ko)}],
                max_tokens=120)
            span, why = clean_span(txt, ko)
            answers = next((x["answers"] for x in paras[r["para_id"]]["terms"]
                            if x["en"] == r["en"]), [r["rep"]])
            grade, level = span_grade(span, answers, r["rep"])
            rec = {**r, "mode": mode, "span": span, "span_why": why,
                   "aligned_grade": grade, "aligned_level": level,
                   "aligned_hit": grade.startswith("정답"),
                   "contains_hit": r["term_hit"], "raw": txt, "finish": fin,
                   "error": err}
            # random 모드는 추종률을 재기 위해 위치만 묻는 질문을 한 번 더 한다
            if mode == "random" and r.get("decoy"):
                txt2, _, _ = T.call(
                    T.QWEN, [{"role": "system", "content": SYS_POS},
                             {"role": "user", "content":
                              build_user(r["en"], t["src"], ko, True)}],
                    max_tokens=120)
                pspan, pwhy = clean_span(txt2, ko)
                rec["pos_span"] = pspan
                rec["pos_why"] = pwhy
                rec["aligned_followed"] = bool(pspan) and bool(
                    dict_variants(pspan) & dict_variants(r["decoy"]))
            return rec

        # span 이 번역문의 부분문자열이어야 한다 → 응답 교차도 같이 걸러진다
        def verify(r, o):
            return isinstance(o, dict) and o["span_why"] != "not_substring"

        res = T.pmap_verified(rows, f, verify, desc=f"{mode} ")
        T.netguard(f"align:{mode}")

        n = len(res)
        al = sum(1 for x in res if x["aligned_hit"])
        co = sum(1 for x in res if x["contains_hit"])
        nd = sum(1 for x in res if x["span_why"] == "none")
        ns = sum(1 for x in res if x["span_why"] == "not_substring")
        # 두 방식이 갈린 건수
        fp = sum(1 for x in res if x["contains_hit"] and not x["aligned_hit"])
        fn = sum(1 for x in res if x["aligned_hit"] and not x["contains_hit"])
        print(f"   정렬 채점 Term%   {al}/{n} ({al/n*100:.1f}%)")
        print(f"   기존 contains     {co}/{n} ({co/n*100:.1f}%)")
        print(f"   기존만 적중(과대) {fp}건 · 정렬만 적중(과소) {fn}건")
        print(f"   span 미검출 {nd}건 · 부분문자열 아님 {ns}건")
        s = {"mode": mode, "n": n,
             "aligned_pct": round(al / n * 100, 1),
             "contains_pct": round(co / n * 100, 1),
             "contains_only": fp, "aligned_only": fn,
             "span_none": nd, "span_bad": ns}
        if mode == "random":
            af = sum(1 for x in res if x.get("aligned_followed"))
            of = sum(1 for x in res if x.get("followed_decoy"))
            pn = sum(1 for x in res if x.get("pos_why") == "none")
            print(f"   ★ 오답 추종률 (정렬) {af}/{n} ({af/n*100:.1f}%)"
                  f"   ← 그 용어 자리에 오답이 있는가")
            print(f"     기존 방식        {of}/{n} ({of/n*100:.1f}%)"
                  f"   ← 문단 어디든 오답 문자열이 있으면 셌다 (과대)")
            print(f"     위치 span 미검출 {pn}건 (번역에서 그 자리가 빠짐)")
            s |= {"aligned_followed_pct": round(af / n * 100, 1),
                  "contains_followed_pct": round(of / n * 100, 1),
                  "pos_none": pn}
        summary.append(s)
        out += res

    print("\n" + "=" * 74)
    print(f"{'mode':<10}{'정렬 Term%':>12}{'기존 Term%':>12}{'과대':>7}{'과소':>7}")
    for s in summary:
        print(f"{s['mode']:<10}{s['aligned_pct']:>11.1f}%{s['contains_pct']:>11.1f}%"
              f"{s['contains_only']:>7}{s['aligned_only']:>7}")
    print(f"\n{T.usage_report()}")
    print(T.cross_report())

    os.environ.setdefault("TCMT_OUT", rdir)
    T.OUT_DIR = rdir
    T.save("c_para_aligned.json", {"summary": summary, "rows": out,
                                   "usage": T.USAGE, "config": vars(a),
                                   "crossing": dict(T.CROSS)})
    T.save_csv("c_para_aligned.csv", out,
               ["mode", "para_id", "en", "rep", "span", "span_why",
                "aligned_grade", "aligned_level", "aligned_hit",
                "contains_hit", "decoy", "followed_decoy"])


if __name__ == "__main__":
    main()
