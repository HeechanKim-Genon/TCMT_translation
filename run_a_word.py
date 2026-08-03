# -*- coding: utf-8 -*-
"""(a) 단어 단위 — ENG/KOR 채움 형식

arm 구성
  1c    단어 1개 = 호출 1개                        ← 상한선(기준선)
  1a    사전순 인접 50개 배치                        묶음이 도움인가 오염인가
  1b    무작위 50개 배치                            묶음 위치 효과만
  2A    + NOTE: standardized medical term          도메인 힌트만의 효과
  2C    후보 N개 제시 → 택일                        ★ '사전 참조' arm

※ KCD 코드 힌트 arm(구 2B)은 제외했다. 파일럿에서 2-A와 차이가 없었고
  (McNemar χ²=0.16), 최종 사전에서 KCD 보유는 390/1,970(약 20%)뿐이라
  다른 arm과 대상 집합이 달라져 직접 비교가 성립하지 않는다.

■ 2C가 이 스크립트의 핵심이다.
  정답 1개를 그냥 주면 복사라서 자명하게 100%다. 실제 검색은 부정확하고
  `discharge`처럼 후보가 7개 나오는 경우가 있으므로, **후보 N개를 주고
  표준 대표용어를 고르게 하는 것**이 실제 환경에 대응한다.
  후보는 (정답 1개 + 무작위 오답 N-1개)를 섞어 만들고 순서를 고정 시드로 섞는다.

실행:
  python3 build_dataset.py --paras 0        # 먼저 데이터셋
  python3 run_a_word.py                     # 전체 arm
  python3 run_a_word.py --arms 1c,2C        # 일부만
  python3 run_a_word.py --limit 50          # 앞 50개 용어로만 (빠른 점검)
  python3 run_a_word.py --batch 10          # 배치 크기 변경 (품질-비용 곡선)

결과: results/a_word_*.json / a_word_summary.json / a_word_rows.csv
"""
import argparse
import json
import os
import random
import re

import tcmt_common as T

SYS = "Complete the KOR field with the standard Korean medical term. Nothing else."
SYS_BATCH = ("Fill in the KOR column with the standard Korean medical term. "
             "Repeat the ENG column exactly. Output only the table rows.")
SYS_PICK = ("Choose the single standard Korean medical term from the given "
            "candidates. Output only the chosen Korean term, nothing else.")

BADCH = re.compile(r"[A-Za-z()（）\[\]{}\"']")
HEDGE = re.compile(r"또는|혹은|입니다|여러|번역|의미|참고")


def clean(raw):
    """응답에서 KOR 값 추출. (값, 이슈목록)"""
    iss = []
    t = (raw or "").strip()
    if t.startswith("```"):
        iss.append("code_fence")
        t = re.sub(r"^```[a-zA-Z]*\n?|```$", "", t).strip()
    if re.search(r"\bENG\s*:", t):
        iss.append("extra_pair")
    t = re.sub(r"(?im)^\s*ENG\s*:.*$", "", t)
    t = re.sub(r"(?im)^\s*KOR\s*:\s*", "", t)
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    if len(lines) > 1:
        iss.append("multiline")
    v = lines[0] if lines else ""
    if not v:
        iss.append("empty")
    else:
        if BADCH.search(v):
            iss.append("bad_chars")
        if HEDGE.search(v):
            iss.append("hedge")
    return T.norm(v), iss


def rec(item, val, iss, raw, fin, extra=None):
    g, lv = T.grade(val, item)
    return {"en": item["en"], "pred": val, "rep": item["rep"],
            "answers": item["answers"], "kcd": item.get("kcd"),
            "words": item["words"], "grade": g, "level": lv,
            "issues": iss, "finish": fin, "raw": raw, **(extra or {})}


# ────────────────────────────────────────── 단건 arm

def run_single(terms, build_user, sysmsg=SYS, label=""):
    def f(it):
        txt, fin, err = T.call(T.GLM,
                               [{"role": "system", "content": sysmsg},
                                {"role": "user", "content": build_user(it)}],
                               max_tokens=400)
        if err and not txt:
            return rec(it, "", ["api_error"], None, None, {"error": err})
        v, iss = clean(txt)
        return rec(it, v, iss, txt, fin)
    return T.pmap(terms, f, desc=f"{label} ")


# ────────────────────────────────────────── 배치 arm

def parse_batch(txt, items):
    got, iss = {}, []
    t = (txt or "").strip()
    if t.startswith("```"):
        iss.append("code_fence")
        t = re.sub(r"^```[a-zA-Z]*\n?|```$", "", t).strip()
    for line in t.splitlines():
        line = line.strip().strip("|").strip()
        if not line or re.match(r"^ENG\b", line, re.I):
            continue
        parts = re.split(r"\t+|\s*\|\s*", line)
        if len(parts) < 2:
            parts = re.split(r"\s{2,}", line)
        if len(parts) < 2:
            iss.append("unsplittable")
            continue
        got[T.norm(parts[0]).lower()] = T.norm(parts[1])
    want = {i["en"] for i in items}
    miss = want - set(got)
    if miss:
        iss.append(f"missing_{len(miss)}")
    return got, iss, sorted(miss)


def run_batch(terms, order, size, label):
    items = order(terms)
    batches = [items[i:i + size] for i in range(0, len(items), size)]

    def f(bt):
        rows = "\n".join(f"{i['en']}\t" for i in bt)
        # 배치는 max_tokens를 넉넉히. 4000으로 돌렸을 때 4개 중 1개가 잘려
        # 36행이 소실된 적이 있다.
        txt, fin, err = T.call(T.GLM,
                               [{"role": "system", "content": SYS_BATCH},
                                {"role": "user", "content": f"ENG\tKOR\n{rows}"}],
                               max_tokens=max(2000, size * 90))
        if err and not txt:
            return {"items": bt, "got": {}, "issues": ["api_error"],
                    "miss": [i["en"] for i in bt], "finish": None, "error": err}
        got, iss, miss = parse_batch(txt, bt)
        return {"items": bt, "got": got, "issues": iss, "miss": miss,
                "finish": fin, "raw": txt}

    bres = T.pmap(batches, f, desc=f"{label} ")
    rows = []
    for b in bres:
        for it in b["items"]:
            v = b["got"].get(it["en"], "")
            iss = [] if v else ["missing_row"]
            if v:
                if BADCH.search(v):
                    iss.append("bad_chars")
                if HEDGE.search(v):
                    iss.append("hedge")
            rows.append(rec(it, v, iss, None, b.get("finish"),
                            {"batch_issues": b["issues"]}))
    trunc = sum(1 for b in bres if b.get("finish") == "length")
    print(f"      배치 {len(bres)}개 · 잘림(length) {trunc}개 · "
          f"누락행 {sum(len(b['miss']) for b in bres)}개")
    return rows, [{k: v for k, v in b.items() if k != "items"} for b in bres]


# ────────────────────────────────────────── 2C 후보 택일

def make_candidates(terms, n_cand, seed):
    """정답 1개 + 무작위 오답 n-1개. 실제 검색이 부정확한 상황을 모사."""
    rnd = random.Random(seed)
    allko = [t["rep"] for t in terms]
    out = []
    for t in terms:
        wrong = []
        while len(wrong) < n_cand - 1:
            c = rnd.choice(allko)
            if c != t["rep"] and c not in wrong and c not in t["answers"]:
                wrong.append(c)
        cands = [t["rep"]] + wrong
        rnd.shuffle(cands)
        out.append({**t, "candidates": cands})
    return out


def run_pick(terms, n_cand, seed):
    tc = make_candidates(terms, n_cand, seed)

    def f(it):
        cl = "\n".join(f"- {c}" for c in it["candidates"])
        user = f"ENG: {it['en']}\nCANDIDATES:\n{cl}\nKOR:"
        txt, fin, err = T.call(T.GLM,
                               [{"role": "system", "content": SYS_PICK},
                                {"role": "user", "content": user}],
                               max_tokens=400)
        if err and not txt:
            return rec(it, "", ["api_error"], None, None,
                       {"error": err, "candidates": it["candidates"]})
        v, iss = clean(txt)
        if v and v not in {T.norm(c) for c in it["candidates"]}:
            iss.append("off_list")      # 후보에 없는 답을 냄
        return rec(it, v, iss, txt, fin, {"candidates": it["candidates"]})
    return T.pmap(tc, f, desc="2C ")


# ────────────────────────────────────────── main

ALL_ARMS = ["1c", "1a", "1b", "2A", "2C"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default=",".join(ALL_ARMS))
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--limit", type=int, default=0, help="용어 수 제한 (0=전체)")
    ap.add_argument("--candidates", type=int, default=5, help="2C 후보 개수")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    tp = os.path.join(T.DATA_DIR, "terms.json")
    if not os.path.exists(tp):
        raise SystemExit("먼저 실행: python3 build_dataset.py --paras 0")
    terms = json.load(open(tp, encoding="utf-8"))
    if a.limit:
        terms = terms[:a.limit]
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    print(f"(a) 단어 단위 · 용어 {len(terms)}개 · arm {arms} · 모델 {T.GLM['name']}\n")

    out, summary = {}, []
    for arm in arms:
        print(f"── {arm}")
        if arm == "1c":
            rows = run_single(terms, lambda i: f"ENG: {i['en']}\nKOR:", label="1c")
        elif arm == "1a":
            rows, b = run_batch(terms, lambda s: sorted(s, key=lambda x: x["en"]),
                                a.batch, "1a")
            out["1a_batches"] = b
        elif arm == "1b":
            rows, b = run_batch(terms,
                                lambda s: random.Random(a.seed + 7).sample(s, len(s)),
                                a.batch, "1b")
            out["1b_batches"] = b
        elif arm == "2A":
            rows = run_single(
                terms,
                lambda i: f"ENG: {i['en']}\nNOTE: standardized medical term\nKOR:",
                label="2A")
        elif arm == "2C":
            rows = run_pick(terms, a.candidates, a.seed)
        else:
            print(f"      알 수 없는 arm: {arm}")
            continue

        T.netguard(arm)
        if not rows:
            # 예: 2B/2B2는 KCD 보유 용어가 표본에 없으면 대상이 0건이 된다
            print(f"      ⚠️ 대상 0건 → {arm} 건너뜀")
            continue
        T.print_tally(arm, rows)
        iss = {}
        for r in rows:
            for i in r.get("issues", []):
                iss[i] = iss.get(i, 0) + 1
        if iss:
            print(f"   이슈: {iss}")
        fmt_ok = sum(1 for r in rows if not r.get("issues"))
        print(f"   형식준수 {fmt_ok}/{len(rows)} ({fmt_ok/len(rows)*100:.1f}%)")
        out[arm] = rows
        corr = sum(1 for r in rows if r["grade"].startswith("정답"))
        summary.append({"arm": arm, "n": len(rows),
                        "format_ok_pct": round(fmt_ok / len(rows) * 100, 1),
                        "correct_pct": round(corr / len(rows) * 100, 1),
                        "grades": T.tally(rows), "issues": iss})
        T.save(f"a_word_{arm}.json", rows)

    print("\n" + "=" * 72)
    print(f"{'arm':<8}{'n':>5}{'형식준수':>10}{'정답':>8}")
    for s in summary:
        print(f"{s['arm']:<8}{s['n']:>5}{s['format_ok_pct']:>9.1f}%"
              f"{s['correct_pct']:>7.1f}%")
    print(f"\n{T.usage_report()}")

    T.save("a_word_summary.json", {"summary": summary, "usage": T.USAGE,
                                   "config": vars(a)})
    flat = [{**r, "arm": arm} for arm in out if not arm.endswith("_batches")
            for r in out[arm]]
    T.save_csv("a_word_rows.csv", flat,
               ["arm", "en", "pred", "rep", "grade", "level", "kcd", "words",
                "issues", "finish"])


if __name__ == "__main__":
    main()
