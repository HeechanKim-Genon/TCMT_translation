# -*- coding: utf-8 -*-
"""(c) 문단 단위 — 매칭 → 주입 → 번역 (본 실험)

파이프라인 3단계
  1. 매칭   문단에서 사전 표제어를 최장일치로 찾는다 (끝기능어 배제)
  2. 주입   걸린 것만 용어집으로 프롬프트에 넣는다
  3. 번역   **문단 전체를 번역한다** (용어만 뽑아 번역하는 게 아니다)

3-mode
  none    용어집 없음                              ← baseline
  term    매칭된 용어의 정답 한글명 주입              ← terminology
  random  매칭된 용어에 다른 용어의 한글명을 주입      ← 통제군

■ 채점은 문단 전체 BLEU가 아니라 Term%(용어 준수율)다.
  180단어 문단에 용어 8개면 문서 전체 지표에는 묻힌다. WMT 용어 태스크가
  Term%/TSR을 쓰는 이유가 이것이다. 대상 용어별로 "표준 한글명이 번역문에
  등장했는가"를 센다.

■ random arm 추종률이 인과성을 보증한다.
  틀린 용어집을 따라가면 = 모델이 용어집을 읽고 있다.
  안 따라가면 = term arm의 개선은 용어집 때문이 아니다.

■ 매칭 자체도 같이 평가된다.
  build_dataset.py 가 심은 용어(target)와 매칭기가 찾은 것(matched)을 비교해
  재현율을 낸다. 심지 않았는데 걸린 것(extra)은 오탐 후보다.

실행:
  python3 build_dataset.py                      # 문단까지 생성
  python3 run_c_paragraph.py                    # 3 mode 전부
  python3 run_c_paragraph.py --modes none,term
  python3 run_c_paragraph.py --limit 5          # 문단 5개로 빠른 점검
  python3 run_c_paragraph.py --inject-target    # 매칭 대신 심은 용어를 그대로 주입
                                                #  (매칭 오차를 제거한 상한 측정)

결과: results/c_para_{mode}.json / c_para_summary.json
      c_para_terms.csv (용어별) / c_para_translations.csv (번역문 전문)
"""
import argparse
import json
import os
import random

import tcmt_common as T

SYS_NONE = ("You are a professional medical translator. "
            "Translate the English clinical paragraph into Korean. "
            "Output only the Korean translation.")
SYS_GLOSS = ("You are a professional medical translator. "
             "Translate the English clinical paragraph into Korean.\n"
             "Use the given standard Korean terms EXACTLY as provided. "
             "Do not paraphrase them.\n"
             "Output only the Korean translation.")


def build_prompt(mode, para, inject, decoy):
    """(system, user) 반환. inject = [{term, rep, answers}]"""
    if mode == "none" or not inject:
        return SYS_NONE, f"<document>\n{para['text']}\n</document>"
    lines = []
    for h in inject:
        ko = h["rep"] if mode == "term" else decoy.get(h["term"], h["rep"])
        lines.append(f"{h['term']} → {ko}")
    gl = "\n".join(lines)
    user = (f"Standard Korean terms:\n{gl}\n\n"
            f"Translate the document below into Korean.\n"
            f"<document>\n{para['text']}\n</document>")
    return SYS_GLOSS, user


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="none,term,random")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--inject-target", action="store_true",
                    help="매칭 결과 대신 심은 용어를 주입 (매칭 오차 제거)")
    ap.add_argument("--no-tail-filter", action="store_true",
                    help="끝기능어 필터 끄기 (필터 효과 비교용)")
    a = ap.parse_args()

    pp = os.path.join(T.DATA_DIR, "paragraphs.json")
    if not os.path.exists(pp):
        raise SystemExit("먼저 실행: python3 build_dataset.py")
    paras = json.load(open(pp, encoding="utf-8"))
    if a.limit:
        paras = paras[:a.limit]
    modes = [m.strip() for m in a.modes.split(",") if m.strip()]

    # build_dataset이 쓴 사전과 동일한 것을 쓴다 (매칭 결과가 달라지면 안 됨)
    mp = os.path.join(T.DATA_DIR, "meta.json")
    dpath = json.load(open(mp, encoding="utf-8"))["dict_path"] if os.path.exists(mp) else None
    print("사전 로드 중…", flush=True)
    D = T.load_dict(dpath)
    print(f"\n(c) 문단 단위 · 문단 {len(paras)}개 · mode {modes} · "
          f"모델 {T.GLM['name']}")
    print(f"    주입 대상: {'심은 용어(target)' if a.inject_target else '매칭 결과'}"
          f" · 끝기능어 필터 {'끔' if a.no_tail_filter else '켬'}\n")

    # ── 1단계: 매칭 (모든 mode가 같은 매칭 결과를 쓴다)
    print("── 1단계 매칭")
    tot_t = tot_m = tot_x = 0
    for p in paras:
        hits = T.match_terms(p["text"], D,
                             use_tail_filter=not a.no_tail_filter)
        tgt = {t["en"]: t for t in p["terms"]}
        p["_hits"] = hits
        p["_matched"] = [h["term"] for h in hits]
        p["_target"] = sorted(tgt)
        p["_recall_hit"] = sorted(set(p["_matched"]) & set(tgt))
        p["_recall_miss"] = sorted(set(tgt) - set(p["_matched"]))
        p["_extra"] = sorted(set(p["_matched"]) - set(tgt))
        if a.inject_target:
            p["_inject"] = [{"term": t["en"], "rep": t["rep"],
                             "answers": t["answers"]} for t in p["terms"]]
        else:
            p["_inject"] = [{"term": h["term"], "rep": h["rep"],
                             "answers": h["answers"]} for h in hits]
        tot_t += len(tgt)
        tot_m += len(p["_recall_hit"])
        tot_x += len(p["_extra"])
    print(f"   심은 용어 {tot_t}개 · 매칭 성공 {tot_m}개 "
          f"(재현율 {tot_m/max(1,tot_t)*100:.1f}%)")
    print(f"   심지 않았는데 매칭 {tot_x}개 (오탐 후보 — 문단 자연발생 포함)")
    print(f"   주입 용어 평균 {sum(len(p['_inject']) for p in paras)/len(paras):.1f}개/문단")

    # random arm용 오답 — 문단 내 다른 용어의 한글명을 돌려쓴다
    rnd = random.Random(a.seed + 5)
    allrep = [t["rep"] for p in paras for t in p["terms"]]
    decoy = {}
    for p in paras:
        for h in p["_inject"]:
            while True:
                c = rnd.choice(allrep)
                if c != h["rep"] and c not in h["answers"]:
                    decoy[h["term"]] = c
                    break

    # ── 2·3단계: 주입 + 번역
    summary, term_rows, tr_rows = [], [], []
    for mode in modes:
        print(f"\n── mode={mode}")

        def f(p, mode=mode):
            sysm, user = build_prompt(mode, p, p["_inject"], decoy)
            txt, fin, err = T.call(
                T.GLM, [{"role": "system", "content": sysm},
                        {"role": "user", "content": user}],
                max_tokens=max(2500, len(p["text"].split()) * 14))
            return {"id": p["id"], "mode": mode, "finish": fin,
                    "error": err, "src": p["text"], "ko": T.norm(txt or ""),
                    "injected": [h["term"] for h in p["_inject"]],
                    "n_injected": len(p["_inject"])}

        outs = T.pmap(paras, f, desc=f"{mode} ")
        T.netguard(f"c:{mode}")

        rows = []
        for p, o in zip(paras, outs):
            inj = {h["term"] for h in p["_inject"]}
            for t in p["terms"]:
                hit, which = T.contains_answer(o["ko"], t)
                d = decoy.get(t["en"])
                fol = bool(d) and mode == "random" and (
                    T.norm(d) in o["ko"]
                    or T.norm(d).replace(" ", "") in o["ko"].replace(" ", ""))
                rows.append({
                    "para_id": p["id"], "mode": mode, "en": t["en"],
                    "rep": t["rep"], "matched": t["en"] in p["_matched"],
                    "injected": t["en"] in inj,
                    "term_hit": hit, "hit_form": which,
                    "decoy": d if mode == "random" else None,
                    "followed_decoy": fol if mode == "random" else None,
                })
            tr_rows.append(o)

        n = len(rows) or 1
        hit = sum(1 for r in rows if r["term_hit"])
        inj_rows = [r for r in rows if r["injected"]]
        hit_inj = sum(1 for r in inj_rows if r["term_hit"])
        noinj = [r for r in rows if not r["injected"]]
        hit_noinj = sum(1 for r in noinj if r["term_hit"])
        trunc = sum(1 for o in outs if o["finish"] == "length")
        fail = sum(1 for o in outs if not o["ko"])
        print(f"   Term% 전체        {hit}/{n} ({hit/n*100:.1f}%)")
        if inj_rows:
            print(f"   Term% 주입된 용어  {hit_inj}/{len(inj_rows)} "
                  f"({hit_inj/len(inj_rows)*100:.1f}%)")
        if noinj:
            print(f"   Term% 미주입 용어  {hit_noinj}/{len(noinj)} "
                  f"({hit_noinj/len(noinj)*100:.1f}%)   ← 매칭 실패분")
        if trunc or fail:
            print(f"   ⚠️ 번역 잘림 {trunc}개 · 빈 응답 {fail}개")
        fol = None
        if mode == "random":
            fol = sum(1 for r in rows if r.get("followed_decoy"))
            print(f"   ★ 오답 용어집 추종률 {fol}/{len(inj_rows) or n} "
                  f"({fol/max(1,len(inj_rows))*100:.1f}%)"
                  f"  ← 높아야 용어집이 실제로 읽히고 있다는 증거")
        summary.append({
            "mode": mode, "n_terms": n, "n_paras": len(paras),
            "term_pct_all": round(hit / n * 100, 1),
            "term_pct_injected": (round(hit_inj / len(inj_rows) * 100, 1)
                                  if inj_rows else None),
            "term_pct_not_injected": (round(hit_noinj / len(noinj) * 100, 1)
                                      if noinj else None),
            "followed_decoy_pct": (round(fol / max(1, len(inj_rows)) * 100, 1)
                                   if fol is not None else None),
            "truncated": trunc, "empty": fail,
        })
        T.save(f"c_para_{mode}.json", {"terms": rows, "translations": outs})
        term_rows += rows

    # ── 종합
    print("\n" + "=" * 78)
    print(f"{'mode':<10}{'Term%전체':>11}{'Term%주입':>11}{'Term%미주입':>12}{'오답추종':>10}")
    for s in summary:
        g = lambda v: f"{v}%" if v is not None else "-"
        print(f"{s['mode']:<10}{s['term_pct_all']:>10.1f}%{g(s['term_pct_injected']):>11}"
              f"{g(s['term_pct_not_injected']):>12}{g(s['followed_decoy_pct']):>10}")

    if len(summary) > 1:
        print("\n■ 페어 비교 (용어 단위, 기준: none)")
        bym = {}
        for r in term_rows:
            bym.setdefault(r["mode"], {})[(r["para_id"], r["en"])] = r["term_hit"]
        base = bym.get("none", {})
        for m, d in bym.items():
            if m == "none":
                continue
            win = sum(1 for k in d if d[k] and not base.get(k))
            los = sum(1 for k in d if not d[k] and base.get(k))
            b = win + los
            chi = ((abs(win - los) - 1) ** 2) / b if b else 0
            print(f"   none→{m:<8} 개선 {win:>4}  악화 {los:>4}  순증 {win-los:+d}"
                  f"   McNemar χ²={chi:.2f} {'(p<0.05)' if chi >= 3.84 else ''}")

    print(f"\n{T.usage_report()}")
    T.save("c_para_summary.json", {
        "summary": summary, "usage": T.USAGE, "config": vars(a),
        "matching": {"target": tot_t, "matched": tot_m,
                     "recall_pct": round(tot_m / max(1, tot_t) * 100, 1),
                     "extra": tot_x}})
    T.save_csv("c_para_terms.csv", term_rows,
               ["mode", "para_id", "en", "rep", "matched", "injected",
                "term_hit", "hit_form", "decoy", "followed_decoy"])
    T.save_csv("c_para_translations.csv", tr_rows,
               ["mode", "id", "n_injected", "finish", "src", "ko"])


if __name__ == "__main__":
    main()
