# -*- coding: utf-8 -*-
"""공통 모듈 — API 호출 · 사전 로드 · 매칭 · 채점

이 파일은 직접 실행하지 않는다. run_a / run_b / run_c 가 import한다.

■ 반드시 알아야 할 실측 사실
1. GLM-5.2는 thinking 모델이다. `reasoning: {"enabled": false}` 가 없으면
   max_tokens를 전부 추론에 쓰고 content가 None으로 온다.
   이 형식만 먹는다 (thinking.type / chat_template_kwargs / reasoning.exclude 는 무시됨).
2. 껐어도 약 3.5%는 새어나온다 → finish_reason=="length" 또는 빈 응답이면 재시도.
3. 엔드포인트 성능이 극단적으로 다르다:
     813 (GLM-5.2)      : 12건 240초, 2건 실패      ← 측정 대상 모델
     752 (Qwen3.5-397B) : 12건 2.6초, 전건 성공     ← 데이터 생성용
   752는 model 파라미터를 무시하고 항상 Qwen을 서빙한다.
4. stop 시퀀스는 수용되지만 효과가 없다 (폭주 0/20). 쓰지 않는다.
"""
import collections
import csv
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))


# ════════════════════════════════════════════════ 설정
# 저장소에 비밀값을 두지 않는다. .env 파일 또는 셸 환경변수로 준다.

def _load_dotenv(path=os.path.join(BASE, ".env")):
    """의존성 없는 최소 .env 로더. 이미 설정된 환경변수는 덮어쓰지 않는다."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


_load_dotenv()

# GenOS 게이트웨이. 서빙 번호만 바꾸면 다른 배포로 갈아탈 수 있다.
GENOS_BASE = os.environ.get(
    "GENOS_BASE", "https://genos.genon.ai/api/gateway/rep/serving")


def endpoint(serving_id):
    return f"{GENOS_BASE}/{serving_id}/v1/chat/completions"


# 번역 대상 모델 (측정 대상)
GLM = {
    "url": endpoint(os.environ.get("GLM_SERVING", "813")),
    "key": os.environ.get("GLM_KEY", ""),
    "model": os.environ.get("GLM_MODEL", "zai-org/glm-5.2"),
    "name": os.environ.get("GLM_NAME", "GLM-5.2"),
}
# 데이터 생성용 모델 (번역 모델과 반드시 달라야 자기 선호 편향이 없다)
QWEN = {
    "url": endpoint(os.environ.get("QWEN_SERVING", "752")),
    "key": os.environ.get("QWEN_KEY", ""),
    "model": os.environ.get("QWEN_MODEL", "model"),
    "name": os.environ.get("QWEN_NAME", "Qwen3.5-397B"),
}

# 사전 CSV. 12컬럼 스펙:
#   용어코드, 개념코드, 영문명, 한글명, KCD, ICD9CM, LOINC, EDI, CCC, ICNP, CDT, SNOMED CT
DICT_FULL = os.environ.get("TCMT_DICT", os.path.join(BASE, "data", "dictionary.csv"))
DICT_S2000 = os.environ.get("TCMT_DICT_SAMPLE",
                            os.path.join(BASE, "data", "dictionary_sample2000.csv"))
CSV_PATH = DICT_FULL

CODE_COLS = ["KCD", "ICD9CM", "LOINC", "EDI", "CCC", "ICNP", "CDT", "SNOMED CT"]

OUT_DIR = os.environ.get("TCMT_OUT", os.path.join(BASE, "results"))
DATA_DIR = os.environ.get("TCMT_DATA", os.path.join(BASE, "dataset"))

WORKERS = int(os.environ.get("TCMT_WORKERS", "12"))
USAGE = {"calls": 0, "cost": 0.0, "out_tokens": 0, "reasoning_tokens": 0,
         "netfail": 0, "retries": 0}
_LOCK = threading.Lock()

for d in (OUT_DIR, DATA_DIR):
    os.makedirs(d, exist_ok=True)


# ════════════════════════════════════════════════ API

def call(ep, messages, max_tokens=800, retries=4, temperature=0.0):
    """(text, finish_reason, error) 반환.

    빈 응답 / finish_reason=="length" 는 간헐적 결함이므로 재시도한다.
    (실측: 재호출로 5/5 정상 복구)
    """
    if not ep["key"]:
        raise SystemExit(
            f"⛔ {ep['name']} API 키가 없습니다.\n"
            f"   .env 파일을 만들거나 환경변수를 설정하세요 (.env.example 참고).")
    body = {"model": ep["model"], "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
            "reasoning": {"enabled": False}}       # ← 절대 빼지 말 것
    data = json.dumps(body).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(ep["url"], data=data, headers={
                "Authorization": f"Bearer {ep['key']}",
                "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read())
            u = d.get("usage") or {}
            with _LOCK:
                USAGE["calls"] += 1
                USAGE["cost"] += u.get("cost") or 0
                USAGE["out_tokens"] += u.get("completion_tokens") or 0
                USAGE["reasoning_tokens"] += (
                    (u.get("completion_tokens_details") or {})
                    .get("reasoning_tokens") or 0)
            ch = d["choices"][0]
            txt = (ch["message"].get("content") or "").strip()
            fin = ch.get("finish_reason")
            if txt and fin != "length":
                return txt, fin, None
            # 빈 응답 또는 잘림 → 재시도
            with _LOCK:
                USAGE["retries"] += 1
            last = f"empty_or_truncated(finish={fin})"
            if attempt < retries - 1:
                time.sleep(2 + attempt * 2)
                continue
            return txt, fin, last
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
            if e.code in (400, 401, 403, 422):
                return None, None, last
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < retries - 1:
            time.sleep(3 + attempt * 3)
    if last and not last.startswith("HTTP 4"):
        with _LOCK:
            USAGE["netfail"] += 1
    return None, None, last


def pmap(items, fn, desc=""):
    """진행률 출력하며 병렬 실행. 입력 순서를 보존한다."""
    out = [None] * len(items)
    done = [0]
    step = max(1, len(items) // 20)

    def wrap(i_it):
        i, it = i_it
        r = fn(it)
        with _LOCK:
            done[0] += 1
            if done[0] % step == 0 or done[0] == len(items):
                print(f"      {desc}{done[0]}/{len(items)}", flush=True)
        return i, r

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, r in ex.map(wrap, list(enumerate(items))):
            out[i] = r
    return out


CROSS = {"detected": 0, "repaired": 0, "unresolved": 0}


def pmap_verified(items, fn, verify, desc="", rounds=3):
    """pmap 후, 응답이 요청과 짝이 맞지 않는 항목만 **직렬로** 재호출한다.

    ■ 왜 필요한가 — 응답 교차(response crossing)
      동시 실행이 큰 서빙에서 **다른 요청의 응답이 돌아오는** 일이 실측됐다.
      (문단 term 모드 27건 중 2건. src는 P001 문단인데 ko는 P009의 번역)
      클라이언트는 원인이 아니다. pmap은 입력 순서를 보존하고 결과 dict가 같은
      클로저 안에서 만들어지므로 src와 ko가 어긋날 구조가 없다. 서빙 쪽 문제다.

      교차는 예외를 던지지 않고 조용히 '오답'으로 집계된다. **그냥 두면 점수를
      깎는다.** 실제로 이 2건이 문단 term Term%를 ~100% → 77.8%로 떨어뜨렸고,
      "문단이 문장보다 어렵다"는 잘못된 결론까지 만들었다.

    ■ verify(item, result) -> bool
      True  = 응답이 이 요청의 것으로 보인다
      False = 교차 의심 → 재호출
      판정 기준은 스크립트별 make_verifier() 에 있다. 판정을 넓게 잡으면
      오탐으로 멀쩡한 응답을 버리게 되므로, 각 단계마다 좁게 잡는다.

    ■ 재호출은 직렬로 한다. 동시 실행이 원인이므로 병렬 재호출은 같은 실패를
      반복할 수 있다.
    """
    out = pmap(items, fn, desc=desc)
    first = None
    for rd in range(rounds):
        bad = [i for i, (it, r) in enumerate(zip(items, out))
               if not verify(it, r)]
        if first is None:
            first = len(bad)
        if not bad:
            break
        print(f"      ⚠️ {desc}응답 교차 의심 {len(bad)}건 → 직렬 재호출 "
              f"(round {rd+1}/{rounds})", flush=True)
        for i in bad:
            out[i] = fn(items[i])
    left = [i for i, (it, r) in enumerate(zip(items, out)) if not verify(it, r)]
    with _LOCK:
        CROSS["detected"] += first or 0
        CROSS["repaired"] += (first or 0) - len(left)
        CROSS["unresolved"] += len(left)
    if left:
        print(f"      ⛔ {desc}재호출 후에도 교차 의심 {len(left)}건 남음 "
              f"— crossed_suspect 로 표시된다", flush=True)
        for i in left:
            if isinstance(out[i], dict):
                out[i]["crossed_suspect"] = True
    return out


def cross_report():
    return (f"응답 교차 탐지 {CROSS['detected']}건 · 재호출로 복구 "
            f"{CROSS['repaired']}건 · 미해결 {CROSS['unresolved']}건")


def netguard(stage):
    """네트워크 장애가 섞인 결과는 신뢰할 수 없으므로 중단."""
    if USAGE["netfail"]:
        raise SystemExit(
            f"\n⛔ [{stage}] 네트워크 장애 {USAGE['netfail']}건 → 중단.\n"
            f"   결과가 오염되므로 복구 후 처음부터 재실행할 것.")


def usage_report():
    u = USAGE
    per = u["cost"] / u["calls"] if u["calls"] else 0
    return (f"호출 {u['calls']}회 · 재시도 {u['retries']}회 · "
            f"출력 {u['out_tokens']:,}토큰(reasoning {u['reasoning_tokens']:,}) · "
            f"${u['cost']:.4f} · 호출당 ${per:.6f}")


# ════════════════════════════════════════════════ 사전

def norm(s):
    return unicodedata.normalize("NFKC", str(s)).strip()


# 문서에 인라인으로 등장하지 않는 ICD 분류표 루브릭 제외
RUBRIC = re.compile(
    r",|\bnos\b|\bnec\b|unspecified|not elsewhere|other specified|\bother\b|"
    r"sequelae|\bwith\b|\bwithout\b|injured|accident|\d", re.I)

# 끝 기능어 — 실측으로 정밀도 88.3% → 93.2%, 유용어 손실 0
TAIL_FUNC = {"to", "of", "with", "than", "from", "for", "in", "on", "at", "by",
             "and", "or", "as", "into", "onto", "per", "the", "a", "an"}


def load_dict(path=None, verbose=True, min_len=4):
    """최종 번역사전 로드.

    반환 dict:
        path    : 실제로 읽은 파일
        head    : {영문명(lower): {rep, ko:set, codes:set, kcd:set, rows}}
        answers : {영문명(lower): set(허용 한글명)}
                  = 그 영문명의 모든 한글명 ∪ 같은 개념코드를 공유하는 한글명
        multi / single : 매칭용 표제어 집합
    """
    path = path or CSV_PATH
    csv.field_size_limit(10 ** 9)
    concept2ko = collections.defaultdict(set)
    head = {}
    skipped = 0
    with open(path, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames or []
        for row in rd:
            en, ko = norm(row.get("영문명")), norm(row.get("한글명"))
            cc = norm(row.get("개념코드")) or norm(row.get("용어코드"))
            if not en or not ko:
                continue
            if cc:
                concept2ko[cc].add(ko)
            if ":" in en or len(en) < min_len:
                skipped += 1
                continue
            if not re.fullmatch(r"[A-Za-z0-9 \-'/().,]+", en):
                skipped += 1
                continue
            k = en.lower()
            h = head.setdefault(k, {"rep": ko, "ko": set(), "concepts": set(),
                                    "codes": set(), "kcd": set(), "rows": 0})
            h["ko"].add(ko)
            h["rows"] += 1
            if cc:
                h["concepts"].add(cc)
            for c in CODE_COLS:
                v = norm(row.get(c) or "")
                if v:
                    h["codes"].add(c)
                    if c == "KCD":
                        # KCD는 `C96|C96.00` 처럼 다중값일 수 있다
                        h["kcd"].update(x for x in re.split(r"[|;,]", v) if x.strip())
    answers = {}
    for k, v in head.items():
        s = set(v["ko"])
        for c in v["concepts"]:
            s |= concept2ko[c]
        answers[k] = s
    multi = {k for k in head if " " in k}
    single = {k for k in head if " " not in k}
    if verbose:
        print(f"  사전: {os.path.basename(path)}")
        print(f"  표제어 {len(head):,} (다어절 {len(multi):,} / 단일어 {len(single):,})"
              f"  · 제외 {skipped:,}행")
        cc = collections.Counter(c for v in head.values() for c in v["codes"])
        print(f"  코드 보유: {dict(cc.most_common())}")
    return {"path": path, "head": head, "answers": answers,
            "multi": multi, "single": single, "cols": cols}


def term_type(h):
    """캐리어 문장 유형 결정. 유형이 안 맞는 캐리어는 오역을 유도하므로 중요.
    (실측: `Delivery record`를 환자 소견 캐리어에 넣으면 '투여 기록'으로 오역)"""
    c = h.get("codes") or set()
    if "KCD" in c or "ICD9CM" in c:
        return "dx"           # 진단
    if "EDI" in c or "CDT" in c:
        return "proc"         # 검사·처치
    if "LOINC" in c:
        return "lab"          # 검사결과·검체
    return "generic"          # 유형 불명 → 중립 캐리어


def sample_terms(D, n, seed=42, multiword_ratio=0.7, require_kcd=False,
                 unambiguous=True, drop_rubric=True):
    """평가용 용어 표본. 개념 1개(중의성 없음) + 대표용어 확인된 것만 기본."""
    import random
    pool = []
    for en, h in D["head"].items():
        if unambiguous and len(h["concepts"]) > 1:
            continue
        if not h["rep"]:
            continue
        if require_kcd and not h["kcd"]:
            continue
        if drop_rubric and (RUBRIC.search(en) or len(en) > 60):
            continue
        pool.append({
            "en": en, "rep": h["rep"],
            "answers": sorted(D["answers"][en]),
            "kcd": sorted(h["kcd"])[0] if h["kcd"] else None,
            "codes": sorted(h["codes"]),
            "type": term_type(h),
            "words": len(en.split()),
        })
    pool.sort(key=lambda x: x["en"])
    rnd = random.Random(seed)
    mw = [p for p in pool if p["words"] > 1]
    sw = [p for p in pool if p["words"] == 1]
    nm = min(int(n * multiword_ratio), len(mw))
    out = rnd.sample(mw, nm) + rnd.sample(sw, min(n - nm, len(sw)))
    rnd.shuffle(out)
    return out[:n]


# ════════════════════════════════════════════════ 매칭 (문단용)

def match_terms(text, D, use_tail_filter=True, max_n=5, include_single=False):
    """★ 문단에서 사전 용어를 찾는 핵심 함수 (파이프라인 1단계 '매칭')

    반환: [{term, start, end, answers, rep}]   start/end 는 문자 오프셋

    ── 알고리즘
      1. NFKC 정규화 → 소문자화 → 단어 토큰화
      2. n=5부터 2까지 내려가며 n-gram 을 사전 표제어와 대조 (최장일치 우선)
      3. 이미 쓰인 토큰은 재사용 금지 → `carpal tunnel` 이
         `carpal tunnel syndrome` 안에서 중복 매칭되지 않는다
      4. 끝 기능어(to/of/with/than/…)로 끝나는 표제어는 버린다

    ── 실측 정밀도 (MTSamples 영문 5개 문서, 후보 77개. 라벨은 필자 판단)
        최장일치만                88.3%
        + 끝기능어 배제           93.2%   ← 재현율 손실 0. 기본값
        + LLM 분류기              97.1%   ← experiments/match_precision_test.py
        일반어 전량 배제           100%    단 재현율 45.6%로 붕괴 → 사용 금지
        코드 컬럼 보유만           100%    단 재현율 16.2%로 붕괴 → 사용 금지

    ── 실측 재현율 (합성 문단 2개, 심은 용어 10개)
        다어절   7/7  = 100%
        단일어   0/3  =   0%   ← include_single=False 라 구조적으로 못 찾음
        합계     7/10 =  70%
        놓친 3개는 전부 단일어였다: ruminations / cardiorrhexis / styrene

    ── include_single 을 켜야 하는가
      이 표본에서는 켜면 10/10(100%)이 되고 오탐은 1→2개뿐이다. 그러나 이 문단은
      사전 용어로 만든 합성 데이터라 단일어 정밀도가 부풀려져 있다. 실제 임상
      문서(MTSamples)에서는 `from` `mass` `room` `air` `history` `culture` 가
      전부 사전 표제어라 오탐이 급증한다.
      → 권장: include_single=True 로 켜되, LLM 분류기로 걸러낸 사전을 쓸 것.

    ── 아직 처리하지 못한 재현율 손실 (문헌 근거)
      · 굴절형   `ruminations` vs 표제어 `rumination`   → lemmatize 필요
      · 약어     문서는 `IVP`, 사전은 완전형             → 약어 확장 필요
                 (scispaCy 2019 는 Schwartz-Hearst 로 장형 확장 후 재검색)
      · 복합어   SAP(EAMT 2020)은 lemma + 2문자 fuzzy 로도 미인식률 45% 보고
      · 어순     `pain in the abdomen` vs `abdominal pain`
    """
    t = unicodedata.normalize("NFKC", text).lower()
    toks = [(m.group(), m.start(), m.end())
            for m in re.finditer(r"[a-z][a-z0-9\-']*", t)]
    used = [False] * len(toks)
    hits = []
    lo = 1 if include_single else 2
    for n in range(max_n, lo - 1, -1):
        pool = D["multi"] if n > 1 else D["single"]
        for i in range(len(toks) - n + 1):
            if any(used[i:i + n]):
                continue
            g = " ".join(x[0] for x in toks[i:i + n])
            if g not in pool:
                continue
            if use_tail_filter and g.split()[-1] in TAIL_FUNC:
                continue
            hits.append({"term": g, "start": toks[i][1], "end": toks[i + n - 1][2],
                         "answers": sorted(D["answers"][g]),
                         "rep": D["head"][g]["rep"]})
            for j in range(i, i + n):
                used[j] = True
    hits.sort(key=lambda h: h["start"])
    return hits


# ════════════════════════════════════════════════ 채점

# 조사는 파괴적으로 떼지 않는다. 뗀 형태도 후보로 만들어 "둘 중 하나라도 맞으면
# 정답"으로 본다. (`소화기내과`의 `과`처럼 실제 어미와 구분이 불가능하므로)
JOSA = ("을", "를", "이", "가", "은", "는", "의", "에", "로", "으로",
        "와", "과", "도", "만", "에서", "에게", "부터", "까지", "이나", "나")


# 표준 한글명에 붙는 표기 관례. 이것도 파괴적으로 떼지 않고 후보로만 추가한다.
#   끝 하이픈  `불수의-`      의존 형태소 표시
#   괄호       `합곡(合谷)`   한자 병기
#              `해마경화(증)`  생략 가능한 접미
# 이 처리가 없으면 모델이 `합곡`·`불수의`·`해마경화`로 맞게 답해도 오답으로 집계된다.
# (실측: 1000규모 단어 단위에서 arm별 25~27건, baseline 약 +2.5%p)
PAREN = re.compile(r"\s*[(（][^)）]*[)）]")


def ko_variants(s):
    out = set()
    for base in (norm(s), PAREN.sub("", norm(s))):
        b = base.strip().strip("-–—").strip()
        if not b:
            continue
        out |= {b, b.replace(" ", "")}
        for j in JOSA:
            if b.endswith(j) and len(b) > len(j) + 1:
                c = b[: -len(j)]
                out |= {c, c.replace(" ", "")}
    return {x for x in out if x}


def grade(pred, item):
    """4분류 + 어떤 수준에서 맞았는지.

    returns (grade, level)
      grade : 정답(대표) / 정답(동의어) / 오답 / 형식실패
      level : exact / nospace / josa / -
    """
    if not pred:
        return "형식실패", "-"
    p = norm(pred)
    rep = norm(item["rep"])
    ans = {norm(a) for a in item["answers"]}
    if p == rep:
        return "정답(대표)", "exact"
    if p in ans:
        return "정답(동의어)", "exact"
    pv = ko_variants(p)
    if pv & ko_variants(rep):
        lvl = "nospace" if p.replace(" ", "") == rep.replace(" ", "") else "josa"
        return "정답(대표)", lvl
    for a in ans:
        if pv & ko_variants(a):
            lvl = "nospace" if p.replace(" ", "") == a.replace(" ", "") else "josa"
            return "정답(동의어)", lvl
    return "오답", "-"


def contains_answer(text, item):
    """문단 번역문 안에 해당 용어의 표준 한글명이 등장하는가 (Term% 채점용)."""
    t = norm(text)
    tn = t.replace(" ", "")
    for a in [item["rep"]] + list(item["answers"]):
        a = norm(a)
        if a and (a in t or a.replace(" ", "") in tn):
            return True, a
    return False, None


# ════════════════════════════════════════════════ 저장

def save(name, payload):
    p = os.path.join(OUT_DIR, name)
    json.dump(payload, open(p, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"  저장 → {p}")
    return p


def save_csv(name, rows, cols):
    p = os.path.join(OUT_DIR, name)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  저장 → {p}")
    return p


def tally(rows, key="grade"):
    c = collections.Counter(r.get(key) for r in rows)
    n = len(rows) or 1
    return {k: {"n": v, "pct": round(v / n * 100, 1)} for k, v in c.most_common()}


def print_tally(title, rows):
    print(f"\n── {title}   n={len(rows)}")
    for k in ("정답(대표)", "정답(동의어)", "오답", "형식실패"):
        m = [r for r in rows if r.get("grade") == k]
        if m:
            print(f"   {k:<12}{len(m):>5}  ({len(m)/len(rows)*100:5.1f}%)")
    lv = collections.Counter(r.get("level") for r in rows
                             if r.get("grade", "").startswith("정답"))
    if lv:
        print(f"   일치수준: {dict(lv)}")
