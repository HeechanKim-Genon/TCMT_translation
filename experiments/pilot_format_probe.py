# -*- coding: utf-8 -*-
"""용어 단위 번역 테스트 — 200개 파일럿

목적 2가지만 확인한다:
  (1) stop sequence가 실제로 먹는지 (GLM-5.2 게이트웨이가 stop 파라미터를 지원하는지)
  (2) 각 프롬프트 형식의 준수율이 몇 %인지

부수적으로 정답률도 같이 집계한다(정답 집합 = 같은 개념코드의 모든 한글명).

샘플 200개는 전부 KCD 보유 용어에서 뽑는다 → 케이스 1/2/3이 동일 집합에서
돌아가므로 점수 직접 비교가 가능하다. 대신 진단명 편향이 있다.
"""
import collections
import csv
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "..", "01_claim_entry",
                        "보건의료용어표준_V7.0_행단위_파생피처.csv")
OUT = os.path.join(BASE, "pilot")

URL = os.environ.get("GENOS_BASE", "https://genos.genon.ai/api/gateway/rep/serving") \
      + f"/{os.environ.get('GLM_SERVING', '813')}/v1/chat/completions"
KEY = os.environ.get("GLM_KEY", "")
MODEL = "zai-org/glm-5.2"

N = 200
BATCH = 50
SEED = 42
WORKERS = 12

USAGE = {"calls": 0, "cost": 0.0, "out_tokens": 0, "reasoning_tokens": 0,
         "netfail": 0}
USAGE_LOCK = __import__("threading").Lock()


def netguard(stage):
    """네트워크 장애가 섞인 결과는 신뢰할 수 없으므로 즉시 중단한다."""
    if USAGE["netfail"]:
        print(f"\n⛔ [{stage}] 네트워크 장애 {USAGE['netfail']}건 발생 → 중단.\n"
              f"   결과가 오염되므로 네트워크 복구 후 처음부터 재실행할 것.")
        sys.exit(1)

SYS = "Complete the KOR field with the standard Korean medical term. Nothing else."
SYS_BATCH = ("Fill in the KOR column with the standard Korean medical term. "
             "Repeat the ENG column exactly. Output only the table rows.")

STOP = ["\nENG:", "\nEN:", "\n\n"]

os.makedirs(OUT, exist_ok=True)


# ──────────────────────────────────────────── API

def call(messages, max_tokens=2000, stop=None, retries=3, reasoning=False):
    """returns (text, finish_reason, error)

    GLM-5.2는 thinking 모델이다. reasoning을 끄지 않으면 max_tokens를 전부
    reasoning에 소모하고 content가 None으로 돌아온다. 실측(1건):
      reasoning on  → reasoning 373토큰 / $0.001024
      reasoning off → reasoning   0토큰 / $0.000026   (39배)
    게이트웨이가 실제로 수용하는 형식은 `reasoning: {enabled: false}` 뿐이다.
    (thinking.type / chat_template_kwargs / reasoning.exclude / effort 는 모두 무시됨)
    """
    body = {"model": MODEL, "messages": messages,
            "temperature": 0, "max_tokens": max_tokens,
            "reasoning": {"enabled": bool(reasoning)}}
    if stop:
        body["stop"] = stop
    data = json.dumps(body).encode()
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(URL, data=data, headers={
                "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            u = d.get("usage") or {}
            with USAGE_LOCK:
                USAGE["calls"] += 1
                USAGE["cost"] += u.get("cost") or 0
                USAGE["out_tokens"] += u.get("completion_tokens") or 0
                USAGE["reasoning_tokens"] += (
                    (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
            ch = d["choices"][0]
            return ((ch["message"].get("content") or ""),
                    ch.get("finish_reason"), None)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code}: {detail}"
            if e.code in (400, 401, 403, 422):      # 재시도 무의미
                return None, None, last
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        if a < retries - 1:
            time.sleep(3)
    if last and not last.startswith("HTTP 4"):
        with USAGE_LOCK:
            USAGE["netfail"] += 1
    return None, None, last


def parallel(items, fn):
    out = [None] * len(items)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        done = 0
        for f in futs:
            pass
        for f in list(futs):
            out[futs[f]] = f.result()
            done += 1
            if done % 25 == 0 or done == len(items):
                print(f"      {done}/{len(items)}", flush=True)
    return out


# ──────────────────────────────────────────── 사전 로드

def norm(s):
    return unicodedata.normalize("NFKC", str(s)).strip()


def load_dict():
    csv.field_size_limit(10 ** 9)
    concept2ko = collections.defaultdict(set)      # 개념코드 -> {한글명}
    head = collections.defaultdict(lambda: {
        "concepts": set(), "kcd": set(), "rep": None})
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            en, ko = norm(row["영문명"]), norm(row["한글명"])
            cc = norm(row["개념코드"])
            if not en or not ko or not cc:
                continue
            concept2ko[cc].add(ko)
            if ":" in en or len(en) < 5:
                continue
            if not re.fullmatch(r"[A-Za-z0-9 \-'/().,]+", en):
                continue
            h = head[en.lower()]
            h["concepts"].add(cc)
            if norm(row.get("KCD") or ""):
                h["kcd"].add(norm(row["KCD"]))
            if norm(row.get("대표/동의어") or "") == "대표용어" and not h["rep"]:
                h["rep"] = ko
    return concept2ko, head


# KCD 보유 행에는 ICD 분류표 루브릭이 섞여 있다
# (`ligamentous laxity nos, upper arm`, `passenger of pick-up truck or van injured in…`)
# 이건 실제 문서에 인라인으로 등장하는 용어가 아니므로 제외한다.
RUBRIC = re.compile(
    r",|\bnos\b|\bnec\b|unspecified|not elsewhere|other specified|"
    r"\bother\b|sequelae|\bwith\b|\bwithout\b|injured|accident|\d",
    re.I)


def build_sample():
    concept2ko, head = load_dict()
    pool = []
    for en, h in head.items():
        # 파일럿 조건: KCD 보유 + 개념 1개(중의성 없음) + 대표용어 확인됨
        if len(h["concepts"]) != 1 or not h["kcd"] or not h["rep"]:
            continue
        if RUBRIC.search(en) or len(en) > 60:
            continue
        cc = next(iter(h["concepts"]))
        answers = set(concept2ko[cc])
        pool.append({"en": en, "rep": h["rep"], "answers": sorted(answers),
                     "kcd": sorted(h["kcd"])[0], "concept": cc,
                     "words": len(en.split())})
    pool.sort(key=lambda x: x["en"])
    rnd = random.Random(SEED)
    multi = [p for p in pool if p["words"] > 1]
    single = [p for p in pool if p["words"] == 1]
    # 다어절 140 / 단일어 60 층화
    s = rnd.sample(multi, min(140, len(multi))) + rnd.sample(single, min(60, len(single)))
    rnd.shuffle(s)
    print(f"  후보 풀 {len(pool):,}  (다어절 {len(multi):,} / 단일어 {len(single):,})")
    print(f"  샘플 {len(s)}개 확정")
    return s[:N], head


# ──────────────────────────────────────────── 형식 검사

HANGUL = re.compile(r"[가-힣]")
BAD_CHARS = re.compile(r"[A-Za-z()（）\[\]{}\"']")
HEDGE = re.compile(r"또는|혹은|입니다|여러|다음|번역|의미|즉|참고|또한|/")


def clean_kor(raw):
    """모델 응답에서 KOR 값을 뽑는다. (값, 이슈목록)"""
    issues = []
    t = raw.strip()
    if t.startswith("```"):
        issues.append("code_fence")
        t = re.sub(r"^```[a-zA-Z]*\n?|```$", "", t).strip()
    if re.search(r"\bENG\s*:", t):
        issues.append("extra_pair")          # stop 미작동 신호
    t = re.sub(r"(?im)^\s*ENG\s*:.*$", "", t)
    t = re.sub(r"(?im)^\s*KOR\s*:\s*", "", t)
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    if len(lines) > 1:
        issues.append("multiline")
    val = lines[0] if lines else ""
    if not val:
        issues.append("empty")
    if BAD_CHARS.search(val):
        issues.append("bad_chars")
    if HEDGE.search(val):
        issues.append("hedge")
    if val and not HANGUL.search(val):
        issues.append("no_hangul")
    return norm(val), issues


def graded(val, item):
    if not val:
        return "형식실패"
    if val == norm(item["rep"]):
        return "정답(대표)"
    if val in {norm(a) for a in item["answers"]}:
        return "정답(동의어)"
    return "오답"


def report(name, recs):
    n = len(recs)
    ok = sum(1 for r in recs if not r["issues"])
    g = collections.Counter(r["grade"] for r in recs)
    iss = collections.Counter(i for r in recs for i in r["issues"])
    fin = collections.Counter(r.get("finish") for r in recs)
    print(f"\n── {name}   n={n}")
    print(f"   형식 준수      {ok}/{n}  ({ok/n*100:.1f}%)")
    for k in ("정답(대표)", "정답(동의어)", "오답", "형식실패"):
        if g[k]:
            print(f"   {k:<12} {g[k]:>4}  ({g[k]/n*100:.1f}%)")
    if iss:
        print("   이슈:", dict(iss.most_common()))
    print("   finish_reason:", dict(fin))
    return {"name": name, "n": n, "format_ok": ok,
            "grades": dict(g), "issues": dict(iss), "finish": dict(fin)}


# ──────────────────────────────────────────── STAGE 0 : stop 지원 확인

def stage_stop_probe(sample):
    print("\n" + "=" * 66)
    print("STAGE 0 — stop sequence가 실제로 먹는지")
    print("=" * 66)
    probe = sample[:20]

    def run(stop):
        def f(it):
            txt, fin, err = call(
                [{"role": "system", "content": SYS},
                 {"role": "user", "content": f"ENG: {it['en']}\nKOR:"}],
                max_tokens=200, stop=stop)
            if err:
                return {"en": it["en"], "error": err, "raw": None,
                        "issues": ["api_error"], "grade": "형식실패", "finish": None}
            val, issues = clean_kor(txt)
            return {"en": it["en"], "raw": txt, "val": val, "issues": issues,
                    "grade": graded(val, it), "finish": fin,
                    "runaway": "extra_pair" in issues}
        return parallel(probe, f)

    print("\n  [A] stop 없음")
    no_stop = run(None)
    print("\n  [B] stop 있음", STOP)
    with_stop = run(STOP)

    # stop 미지원은 HTTP 4xx로만 판정한다.
    # 네트워크 장애(URLError/timeout)를 미지원으로 오판하면 안 된다 — 실제로 한 번 겪었다.
    errs = [r["error"] for r in with_stop if r["issues"] == ["api_error"]]
    rejected = [e for e in errs if e and e.startswith("HTTP 4")]
    netfail = [e for e in errs if e and not e.startswith("HTTP 4")]
    if netfail:
        print(f"\n  ⚠️ 네트워크 장애 {len(netfail)}/{len(probe)}건 → {netfail[0]}")
        print("     stop 지원 여부와 무관. 네트워크 복구 후 재실행 필요.")
    if rejected:
        print(f"\n  ❌ stop 파라미터 거부 → {rejected[0]}")
        supported = False
    else:
        supported = True
    if netfail:
        print("\n  ⛔ 네트워크 장애로 결과 신뢰 불가. 중단한다.")
        sys.exit(1)
    ra_n = sum(1 for r in no_stop if r.get("runaway"))
    ra_y = sum(1 for r in with_stop if r.get("runaway"))
    print(f"\n  폭주(추가 ENG: 쌍 생성)   stop없음 {ra_n}/20   stop있음 {ra_y}/20")
    print(f"  stop 파라미터 수용        {'✅ 예' if supported else '❌ 아니오'}")
    json.dump({"no_stop": no_stop, "with_stop": with_stop, "supported": supported},
              open(os.path.join(OUT, "stage0_stop.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return supported


# ──────────────────────────────────────────── STAGE 1 : 단어 1개 (1c)

def stage_1c(sample, stop):
    print("\n" + "=" * 66)
    print("STAGE 1 — 케이스 1c : 단어 1개 = 호출 1개")
    print("=" * 66)

    def f(it):
        txt, fin, err = call(
            [{"role": "system", "content": SYS},
             {"role": "user", "content": f"ENG: {it['en']}\nKOR:"}],
            max_tokens=200, stop=stop)
        if err:
            return {"en": it["en"], "error": err, "issues": ["api_error"],
                    "grade": "형식실패", "finish": None}
        val, issues = clean_kor(txt)
        return {"en": it["en"], "raw": txt, "val": val, "rep": it["rep"],
                "answers": it["answers"], "issues": issues,
                "grade": graded(val, it), "finish": fin}

    recs = parallel(sample, f)
    json.dump(recs, open(os.path.join(OUT, "stage1_1c.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return report("1c 단어 1개", recs), recs


# ──────────────────────────────────────────── STAGE 2 : 배치 (1a / 1b)

def parse_batch(txt, items):
    """TSV 응답을 파싱. 반환: {en_lower: kor}, 이슈"""
    issues = []
    t = txt.strip()
    if t.startswith("```"):
        issues.append("code_fence")
        t = re.sub(r"^```[a-zA-Z]*\n?|```$", "", t).strip()
    got = {}
    for line in t.splitlines():
        line = line.strip()
        if not line or re.match(r"^ENG\b", line, re.I):
            continue
        line = line.strip("|").strip()
        parts = re.split(r"\t+|\s*\|\s*", line)
        if len(parts) < 2:
            parts = re.split(r"\s{2,}", line)
        if len(parts) < 2:
            issues.append("unsplittable_line")
            continue
        en, ko = norm(parts[0]).lower(), norm(parts[1])
        got[en] = ko
    want = {it["en"] for it in items}
    missing = want - set(got)
    extra = set(got) - want
    if missing:
        issues.append(f"missing_{len(missing)}")
    if extra:
        issues.append(f"extra_{len(extra)}")
    return got, issues, missing, extra


def stage_batch(sample, label, order_fn, head):
    print("\n" + "=" * 66)
    print(f"STAGE 2 — 케이스 {label}")
    print("=" * 66)
    items = order_fn(sample)
    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]

    def f(bt):
        rows = "\n".join(f"{it['en']}\t" for it in bt)
        txt, fin, err = call(
            [{"role": "system", "content": SYS_BATCH},
             {"role": "user", "content": f"ENG\tKOR\n{rows}"}],
            max_tokens=4000)
        if err:
            return {"error": err, "items": bt, "got": {},
                    "issues": ["api_error"], "finish": None}
        got, issues, missing, extra = parse_batch(txt, bt)
        return {"raw": txt, "items": bt, "got": got, "issues": issues,
                "missing": sorted(missing), "extra": sorted(extra), "finish": fin}

    bres = parallel(batches, f)
    recs = []
    for b in bres:
        for it in b["items"]:
            val = norm(b["got"].get(it["en"], ""))
            iss = []
            if not val:
                iss.append("missing_row")
            else:
                if BAD_CHARS.search(val):
                    iss.append("bad_chars")
                if HEDGE.search(val):
                    iss.append("hedge")
                if not HANGUL.search(val):
                    iss.append("no_hangul")
            recs.append({"en": it["en"], "val": val, "rep": it["rep"],
                         "answers": it["answers"], "issues": iss,
                         "grade": graded(val, it), "finish": b.get("finish")})
    trunc = sum(1 for b in bres if b.get("finish") == "length")
    print(f"   배치 {len(bres)}개,  finish_reason=length(잘림) {trunc}개")
    for i, b in enumerate(bres):
        if b["issues"]:
            print(f"   배치{i+1} 이슈: {b['issues']}")
    json.dump({"batches": [{k: v for k, v in b.items() if k != "items"} for b in bres],
               "rows": recs},
              open(os.path.join(OUT, f"stage2_{label.replace('/', '_')}.json"),
                   "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return report(f"{label} 배치 {BATCH}개씩", recs), recs


# ──────────────────────────────────────────── STAGE 3 : 힌트 (2-A / 2-B)

def stage_hint(sample, label, build_user, stop):
    print("\n" + "=" * 66)
    print(f"STAGE 3 — 케이스 {label}")
    print("=" * 66)

    def f(it):
        txt, fin, err = call(
            [{"role": "system", "content": SYS},
             {"role": "user", "content": build_user(it)}],
            max_tokens=200, stop=stop)
        if err:
            return {"en": it["en"], "error": err, "issues": ["api_error"],
                    "grade": "형식실패", "finish": None}
        val, issues = clean_kor(txt)
        return {"en": it["en"], "raw": txt, "val": val, "rep": it["rep"],
                "answers": it["answers"], "issues": issues,
                "grade": graded(val, it), "finish": fin}

    recs = parallel(sample, f)
    json.dump(recs, open(os.path.join(OUT, f"stage3_{label}.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)
    return report(label, recs), recs


# ──────────────────────────────────────────── STAGE 4 : 문장 (케이스 3)

CARRIERS = [
    "The report described {A} {T} in this patient.",
    "{A_cap} {T} was noted during the examination.",
]


def article(term):
    return "an" if term[0].lower() in "aeiou" else "a"


def carrier_clean(head):
    """캐리어 문장의 고정 어휘가 사전 표제어와 겹치는지 확인"""
    bad = []
    for c in CARRIERS:
        text = c.replace("{A_cap}", "").replace("{A}", "").replace("{T}", "")
        toks = re.findall(r"[a-z]+", text.lower())
        for n in (1, 2, 3):
            for i in range(len(toks) - n + 1):
                g = " ".join(toks[i:i + n])
                if g in head:
                    bad.append(g)
    return sorted(set(bad))


def stage_sentence(sample, stop, head):
    print("\n" + "=" * 66)
    print("STAGE 4 — 케이스 3 : 임상 문장 + span")
    print("=" * 66)
    bad = carrier_clean(head)
    print(f"   캐리어 오염 검사: {'✅ 사전 표제어 겹침 없음' if not bad else f'⚠️ 겹침 {bad}'}")

    def f(it):
        a = article(it["en"])
        sent = CARRIERS[0].format(A=a, T=it["en"])
        user = (f"EN: {sent}\nKO:\nTERM:")
        txt, fin, err = call(
            [{"role": "system",
              "content": ("Fill KO with the Korean translation of EN. "
                          "Fill TERM by copying, from your KO text, the exact "
                          f"substring for \"{it['en']}\". Output only the two fields.")},
             {"role": "user", "content": user}],
            max_tokens=600, stop=["\nEN:", "\n\n\n"])
        if err:
            return {"en": it["en"], "error": err, "issues": ["api_error"],
                    "grade": "형식실패", "finish": None}
        t = txt.strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z]*\n?|```$", "", t).strip()
        mk = re.search(r"(?im)^\s*KO\s*:\s*(.+)$", t)
        mt = re.search(r"(?im)^\s*TERM\s*:\s*(.+)$", t)
        ko = norm(mk.group(1)) if mk else ""
        term = norm(mt.group(1)) if mt else ""
        issues = []
        if not mk:
            issues.append("no_KO")
        if not mt:
            issues.append("no_TERM")
        if term and ko and term not in ko:
            issues.append("span_not_substring")     # 추출 실패 (오답과 구분)
        if term and BAD_CHARS.search(term):
            issues.append("bad_chars")
        grade = graded(term, it) if term else "형식실패"
        return {"en": it["en"], "sent": sent, "raw": txt, "ko": ko, "term": term,
                "rep": it["rep"], "answers": it["answers"], "issues": issues,
                "grade": grade, "finish": fin}

    recs = parallel(sample, f)
    sub = sum(1 for r in recs if "span_not_substring" in r["issues"])
    print(f"   span이 KO의 부분문자열이 아닌 건: {sub}/{len(recs)}  ← 추출 실패로 분리 집계")
    json.dump(recs, open(os.path.join(OUT, "stage4_sentence.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)
    return report("케이스 3 문장+span", recs), recs


# ──────────────────────────────────────────── main

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    print("사전 로드 중…", flush=True)
    sample, head = build_sample()
    json.dump(sample, open(os.path.join(OUT, "sample_200.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=2)

    if only == "sample":
        print("\n샘플만 생성하고 종료.")
        return

    supported = stage_stop_probe(sample)
    stop = STOP if supported else None
    if only == "stop":
        return

    summary = []
    r, _ = stage_1c(sample, stop)
    netguard("1c")
    summary.append(r)

    r, _ = stage_batch(sample, "1a 사전순", lambda s: sorted(s, key=lambda x: x["en"]), head)
    netguard("1a")
    summary.append(r)
    r, _ = stage_batch(sample, "1b 무작위",
                       lambda s: random.Random(SEED + 1).sample(s, len(s)), head)
    netguard("1b")
    summary.append(r)

    r, _ = stage_hint(sample, "2-A 도메인힌트",
                      lambda it: (f"ENG: {it['en']}\n"
                                  f"NOTE: standardized medical term\nKOR:"), stop)
    netguard("2-A")
    summary.append(r)
    r, _ = stage_hint(sample, "2-B KCD코드",
                      lambda it: (f"ENG: {it['en']}\n"
                                  f"KCD: {it['kcd']}\nKOR:"), stop)
    netguard("2-B")
    summary.append(r)

    r, _ = stage_sentence(sample, stop, head)
    netguard("케이스3")
    summary.append(r)

    print("\n" + "=" * 66)
    print("종합")
    print("=" * 66)
    print(f"{'arm':<24}{'형식준수':>9}{'정답(대표)':>10}{'정답(동의어)':>12}{'오답':>8}")
    for s in summary:
        n = s["n"]
        g = s["grades"]
        print(f"{s['name']:<24}{s['format_ok']/n*100:>8.1f}%"
              f"{g.get('정답(대표)', 0)/n*100:>9.1f}%"
              f"{g.get('정답(동의어)', 0)/n*100:>11.1f}%"
              f"{g.get('오답', 0)/n*100:>7.1f}%")
    print(f"\n총 {USAGE['calls']}회 호출 · 출력 {USAGE['out_tokens']:,}토큰 "
          f"(reasoning {USAGE['reasoning_tokens']:,}) · 비용 ${USAGE['cost']:.4f}")
    if USAGE["calls"]:
        per = USAGE["cost"] / USAGE["calls"]
        print(f"호출당 ${per:.6f}  →  5만 용어 단건 환산 ${per*50000:,.1f}")
    json.dump({"stop_supported": supported, "usage": USAGE, "summary": summary},
              open(os.path.join(OUT, "_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n결과 →", OUT)


if __name__ == "__main__":
    main()
