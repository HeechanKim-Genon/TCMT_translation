# -*- coding: utf-8 -*-
"""매칭 정밀도 향상 방법 테스트

MTSamples 영문 5개 문서에서 최장일치로 매칭된 다어절 용어 77개를 대상으로,
문헌에서 보고된 정밀도 향상 기법들을 적용해 precision/recall 변화를 측정한다.

라벨 기준 (명시):
  "이 용어의 표준 한글명을 번역에 강제하면 임상 번역이 **좋아지는가**"
  - 좋아짐  → 유용(1)
  - 무의미하거나 오히려 어색해짐 → 불용(0)
  ※ 라벨은 필자(Claude)의 판단이며 임상 전문가 검증을 받지 않았다.
    `left hand`(왼손), `alcoholic beverages`(알코올성 음료) 등 경계 사례가 있다.

문헌 근거:
  - 끝 기능어 배제        : 관행 (본 조사에서 명시적 선례 확인 못함)
  - 일반어 전량 배제      : DiPMT(arXiv:2302.07856) 최빈 500단어 제외 계열
  - IDF 필터              : Tilde WMT21 (2021.wmt-1.81)
  - 코드 보유 요구        : 우리 자체 발상
  - LLM 분류기            : 우리 자체 발상 (사전 1회 오프라인 처리)
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
CAND = os.path.join(BASE, "pilot", "match_candidates.json")

# Qwen3.5-397B (빠름: 1~2초). GLM 엔드포인트는 12건에 240초라 부적합.
URL = os.environ.get("GENOS_BASE", "https://genos.genon.ai/api/gateway/rep/serving") \
      + f"/{os.environ.get('QWEN_SERVING', '752')}/v1/chat/completions"
KEY = os.environ.get("QWEN_KEY", "")
MODEL = "model"

# ── 라벨: 불용으로 판정한 것 (나머지는 전부 유용)
BAD = {
    "ability to perform",   # 일반어
    "alcoholic beverages",  # 일반어 (술→알코올성 음료 강제가 개선 아님)
    "contact with",         # 기능 연결어
    "daily living",         # ADL의 파편
    "greater than",         # 일반 비교어
    "health services",      # 일반어
    "left hand",            # 자명한 일반 어휘 (왼손)
    "no evidence of",       # 기능 부정어
    "secondary to",         # 기능 연결어 (이차적으로 속발하여 → 어색)
}

# ── 필터 1: 끝 기능어
TAIL_FUNC = {
    "to", "of", "with", "than", "from", "for", "in", "on", "at", "by",
    "and", "or", "as", "into", "onto", "per", "the", "a", "an",
}

# ── 필터 2: 일반어 목록 (DiPMT 계열 — 전부 일반어면 배제)
COMMON = {
    "ability", "perform", "alcoholic", "beverages", "contact", "with", "daily",
    "living", "greater", "than", "health", "services", "left", "right", "hand",
    "no", "evidence", "of", "secondary", "to", "early", "regular", "room", "air",
    "social", "worker", "signs", "symptoms", "follow", "up", "by", "mouth",
    "back", "pain", "chest", "blood", "loss", "weight", "care", "wound",
    "muscle", "strength", "upper", "lower", "total", "normal", "severe",
    "acute", "chronic", "history", "family", "past", "medical", "physical",
    "surgical", "site", "heart", "neck", "foot", "breast", "bone", "white",
    "cell", "oral", "intake", "diet", "and", "review", "systems", "present",
    "illness", "complaint", "chief", "emergency", "vital", "distress", "scan",
    "examination", "therapy", "intervention", "movement", "bowel", "sounds",
    "pressure", "tenderness", "calf", "diagnosis", "cancer", "spasm",
}


def load():
    d = json.load(open(CAND, encoding="utf-8"))
    terms = sorted(d["matches"])
    return terms, d["matches"], set(d["kcd"]), d["ko"]


def f_tail(t):
    return t.split()[-1] not in TAIL_FUNC


def f_common(t):
    return not all(w in COMMON for w in t.split())


def f_kcd(t, kcd):
    return t in kcd


def score(name, kept, terms, counts):
    good = [t for t in terms if t not in BAD]
    tp = [t for t in kept if t not in BAD]
    fp = [t for t in kept if t in BAD]
    prec = len(tp) / len(kept) * 100 if kept else 0
    rec = len(tp) / len(good) * 100
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    occ_tp = sum(counts[t] for t in tp)
    occ_all = sum(counts[t] for t in kept)
    occ_prec = occ_tp / occ_all * 100 if occ_all else 0
    print(f"{name:<30}{len(kept):>4}{prec:>8.1f}%{rec:>8.1f}%{f1:>8.1f}{occ_prec:>9.1f}%"
          f"   놓친유용 {len(good)-len(tp)}")
    return {"name": name, "kept": len(kept), "precision": round(prec, 1),
            "recall": round(rec, 1), "f1": round(f1, 1),
            "occ_precision": round(occ_prec, 1),
            "false_positives": sorted(fp),
            "lost_good": sorted(set(good) - set(tp))}


# ── 필터 3: LLM 분류기
SYS = ("You judge whether an English phrase is a MEDICAL TERM that belongs in a "
       "clinical translation glossary.\n"
       "Answer YES if forcing a standardized Korean rendering would help a clinical translator.\n"
       "Answer NO if it is general-purpose English, a grammatical connective, "
       "a comparison, or a trivially obvious word.\n"
       "Clinical documentation terms (chief complaint, review of systems, status post, "
       "past medical history) count as YES.\n"
       "Output exactly one word: YES or NO.")


def llm_call(t, retries=3):
    b = {"model": MODEL, "temperature": 0, "max_tokens": 6,
         "messages": [{"role": "system", "content": SYS},
                      {"role": "user", "content": f"Phrase: {t}\nAnswer:"}]}
    for a in range(retries):
        try:
            r = urllib.request.Request(URL, data=json.dumps(b).encode(), headers={
                "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=120) as f:
                d = json.loads(f.read())
            txt = (d["choices"][0]["message"].get("content") or "").strip().upper()
            return t, ("YES" in txt), d["usage"].get("cost", 0)
        except Exception:
            if a == retries - 1:
                return t, None, 0
            time.sleep(3)


def main():
    terms, counts, kcd, ko = load()
    good = [t for t in terms if t not in BAD]
    print(f"후보 {len(terms)}개 · 유용 {len(good)} · 불용 {len(BAD & set(terms))}")
    print(f"기준선 정밀도  {len(good)/len(terms)*100:.1f}% (고유)  "
          f"{sum(counts[t] for t in good)/sum(counts.values())*100:.1f}% (출현)\n")
    print(f"{'필터':<30}{'남김':>4}{'정밀도':>9}{'재현율':>8}{'F1':>8}{'출현정밀도':>10}")
    print("-" * 84)
    res = []
    res.append(score("① 필터없음 (최장일치만)", terms, terms, counts))
    res.append(score("② 끝 기능어 배제", [t for t in terms if f_tail(t)], terms, counts))
    res.append(score("③ 일반어 전량 배제", [t for t in terms if f_common(t)], terms, counts))
    res.append(score("④ KCD 보유만", [t for t in terms if f_kcd(t, kcd)], terms, counts))
    res.append(score("⑤ ②+③", [t for t in terms if f_tail(t) and f_common(t)], terms, counts))

    print("\nLLM 분류기 실행 중 (Qwen3.5-397B)...", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=12) as ex:
        out = list(ex.map(llm_call, terms))
    cost = sum(c for _, _, c in out)
    err = [t for t, v, _ in out if v is None]
    yes = {t for t, v, _ in out if v is True}
    print(f"  {time.time()-t0:.1f}s · 오류 {len(err)}건 · ${cost:.5f} "
          f"(용어당 ${cost/max(1,len(terms)-len(err)):.6f})")
    if err:
        print(f"  오류 용어: {err[:5]}")
    res.append(score("⑥ LLM 분류기", sorted(yes), terms, counts))
    res.append(score("⑦ ②+LLM", sorted(t for t in yes if f_tail(t)), terms, counts))

    print("\n" + "=" * 84)
    for r in res:
        if r["false_positives"]:
            print(f"[{r['name']}] 남은 오탐 {len(r['false_positives'])}: {r['false_positives']}")
        if r["lost_good"] and len(r["lost_good"]) <= 12:
            print(f"[{r['name']}] 잃은 유용어: {r['lost_good']}")
        elif r["lost_good"]:
            print(f"[{r['name']}] 잃은 유용어 {len(r['lost_good'])}개 (예: {r['lost_good'][:8]})")
    json.dump({"labels_bad": sorted(BAD), "results": res,
               "llm_yes": sorted(yes), "llm_errors": err, "llm_cost": cost},
              open(os.path.join(BASE, "pilot", "precision_test.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
