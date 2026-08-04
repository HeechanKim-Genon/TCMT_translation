# -*- coding: utf-8 -*-
"""(a) 단어 · (b) 문장 재채점 — API 호출 없음

■ 왜
  문단(c) 채점을 고치면서 **표준 한글명의 표기 관례**를 정답으로 인정하게 했다.
      끝 하이픈  `불수의-`
      괄호       `합곡(合谷)` · `해마경화(증)`
  a/b 는 그 전 기준으로 채점돼 있어서, 세 단계를 같은 기준으로 비교할 수 없다.

  모델 응답 원문(`raw`/`pred`/`term`)이 결과 JSON 에 그대로 저장돼 있으므로
  **재호출 없이** 다시 채점할 수 있다. 새 기준은 tcmt_common.ko_variants 에 있다.

■ 원본을 덮어쓰지 않는다
  `a_word_{arm}.json` 은 그대로 두고 `*_v2.json` / `*_summary_v2.json` 을 새로 쓴다.
  실행 기록은 있는 그대로 남아야 한다.

실행:
  python3 rescore_ab.py               # 100 · 1000 둘 다
  python3 rescore_ab.py --tags 1000
"""
import argparse
import json
import os

import tcmt_common as T

ARMS = ["1c", "1a", "1b", "2A", "2C"]
MODES = ["none", "term", "random"]


def regrade(rows, pred_key):
    """저장된 응답을 새 기준으로 다시 채점한다. (rows, 바뀐건수)"""
    flipped = []
    for r in rows:
        before = r.get("grade")
        g, lv = T.grade(r.get(pred_key) or "", r)
        r["grade_old"], r["level_old"] = before, r.get("level")
        r["grade"], r["level"] = g, lv
        if before != g:
            flipped.append(r)
    return rows, flipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default="100,1000")
    a = ap.parse_args()

    for tag in [t.strip() for t in a.tags.split(",") if t.strip()]:
        rdir = f"results_{tag}"
        if not os.path.isdir(rdir):
            print(f"⛔ {rdir} 없음 — 건너뜀")
            continue
        T.OUT_DIR = rdir
        print(f"\n{'='*66}\n{tag}규모  ({rdir})")

        # ── (a) 단어
        asum = []
        print("\n(a) 단어 단위")
        for arm in ARMS:
            p = f"{rdir}/a_word_{arm}.json"
            if not os.path.exists(p):
                continue
            rows = json.load(open(p, encoding="utf-8"))
            n = len(rows)
            old = sum(1 for r in rows if r["grade"].startswith("정답"))
            rows, flip = regrade(rows, "pred")
            new = sum(1 for r in rows if r["grade"].startswith("정답"))
            print(f"   {arm}: {old}/{n} ({old/n*100:.1f}%) → "
                  f"{new}/{n} ({new/n*100:.1f}%)   변경 {len(flip)}건")
            asum.append({"arm": arm, "n": n,
                         "correct_pct_old": round(old / n * 100, 1),
                         "correct_pct": round(new / n * 100, 1),
                         "flipped": len(flip), "grades": T.tally(rows)})
            T.save(f"a_word_{arm}_v2.json", rows)
        T.save("a_word_summary_v2.json", {"summary": asum})

        # ── (b) 문장
        bsum = []
        print("\n(b) 문장 단위")
        for mode in MODES:
            p = f"{rdir}/b_sent_{mode}.json"
            if not os.path.exists(p):
                continue
            rows = json.load(open(p, encoding="utf-8"))
            n = len(rows)
            old = sum(1 for r in rows if r["grade"].startswith("정답"))
            # span 채점이므로 TERM 을 쓴다 (없으면 ko)
            rows, flip = regrade(rows, "term")
            new = sum(1 for r in rows if r["grade"].startswith("정답"))
            fol = sum(1 for r in rows if r.get("followed_decoy"))
            print(f"   {mode}: {old}/{n} ({old/n*100:.1f}%) → "
                  f"{new}/{n} ({new/n*100:.1f}%)   변경 {len(flip)}건"
                  + (f"   오답추종 {fol}/{n} ({fol/n*100:.1f}%)"
                     if mode == "random" else ""))
            bsum.append({"mode": mode, "n": n,
                         "correct_pct_old": round(old / n * 100, 1),
                         "correct_pct": round(new / n * 100, 1),
                         "flipped": len(flip), "grades": T.tally(rows),
                         "followed_decoy_pct": (round(fol / n * 100, 1)
                                                if mode == "random" else None)})
            T.save(f"b_sent_{mode}_v2.json", rows)

        # 페어 비교 — 같은 용어에 대해 mode별 결과가 어떻게 바뀌는지
        bym = {}
        for mode in MODES:
            p = f"{rdir}/b_sent_{mode}_v2.json"
            if os.path.exists(p):
                for r in json.load(open(p, encoding="utf-8")):
                    bym.setdefault(mode, {})[r["en"]] = \
                        r["grade"].startswith("정답")
        base = bym.get("none", {})
        pair = []
        for m, d in bym.items():
            if m == "none":
                continue
            win = sum(1 for k in d if d[k] and not base.get(k))
            los = sum(1 for k in d if not d[k] and base.get(k))
            b = win + los
            chi = ((abs(win - los) - 1) ** 2) / b if b else 0
            print(f"   none→{m:<7} 개선 {win:>4}  악화 {los:>4}"
                  f"   McNemar χ²={chi:.2f} {'(p<0.05)' if chi >= 3.84 else ''}")
            pair.append({"vs": m, "win": win, "lose": los, "chi2": round(chi, 2)})
        T.save("b_sent_summary_v2.json", {"summary": bsum, "pair": pair})


if __name__ == "__main__":
    main()
