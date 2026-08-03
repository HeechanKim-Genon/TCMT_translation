# -*- coding: utf-8 -*-
"""필터링 파이프라인 공통 모듈 — 경로 · 구조유형 분류 · LLM 배치 판정기

이 파일은 직접 실행하지 않는다. stage*.py 가 import 한다.

■ 반드시 알아야 할 실측 사실
1. GLM-5.2 는 thinking 모델이다. 판정처럼 짧은 출력만 필요한 작업에서는
   `reasoning_effort: "none"` 을 줘야 한다. 안 주면 항목 5개 판정에 추론
   토큰 700개를 쓰고 20초가 걸린다. 주면 추론 0 · 3초 · 결과 동일.
   (tcmt_common 의 `reasoning: {"enabled": false}` 와 둘 다 먹는다.)
2. 배치 50 · 동시 12 기준 처리량이 약 0.15 배치/초다. 8.8만 쌍(1,754배치)이
   프로세스 1개로 30분, 4개로 나누면 8분 걸린다. 슬라이스로 나눠 돌린다.
3. 응답이 잘리거나 깨지는 배치가 있다. 체크포인트(jsonl)에 배치 단위로
   append 하고, 재실행 시 완료된 배치를 건너뛴다. 중단해도 이어서 돌린다.
"""
import json
import os
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(BASE)


# ════════════════════════════════════════════════ 설정

def _load_dotenv(path=os.path.join(REPO, ".env")):
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

GENOS_BASE = os.environ.get(
    "GENOS_BASE", "https://genos.genon.ai/api/gateway/rep/serving")
GLM = {
    "url": f"{GENOS_BASE}/{os.environ.get('GLM_SERVING', '813')}/v1/chat/completions",
    "key": os.environ.get("GLM_KEY", ""),
    "model": os.environ.get("GLM_MODEL", "zai-org/glm-5.2"),
}

# 보건의료용어표준 V7.0 원본 엑셀 (시트명 "V7.0", 13컬럼)
SRC_XLSX = os.environ.get("KOSTOM_XLSX", "")

WORK = os.environ.get("FILTER_WORK", os.path.join(BASE, "work"))
OUT = os.environ.get("FILTER_OUT", os.path.join(BASE, "out"))
WORKERS = int(os.environ.get("FILTER_WORKERS", "12"))
BATCH = int(os.environ.get("FILTER_BATCH", "50"))

for _d in (WORK, OUT):
    os.makedirs(_d, exist_ok=True)

# 원본 13컬럼 중 참조코드 8개 (영문명·한글명·용어코드·개념코드 제외)
REF_COLS = ["UMLS", "ICD9CM", "LOINC", "EDI", "CCC", "ICNP", "CDT", "SNOMED CT"]
# 최종 사전 스펙 12컬럼 — 원본 컬럼명 그대로. UMLS 는 뺀다.
DICT_COLS = ["용어코드", "개념코드", "영문명", "한글명",
             "KCD", "ICD9CM", "LOINC", "EDI", "CCC", "ICNP", "CDT", "SNOMED CT"]


def w(name):
    return os.path.join(WORK, name)


def o(name):
    return os.path.join(OUT, name)


# ════════════════════════════════════════════════ 구조유형 분류
# 영문명의 생김새로 33.9만 행을 7가지로 나눈다. 1차 필터가 이 라벨을 쓴다.

TYPE_A = "A. 콜론(:) 축 조합 (임상검사/LOINC)"
TYPE_B = "B. 세미콜론(;) 축 조합 (방사선)"
TYPE_C = "C. 반점(,) 포함 구문/문장"
TYPE_D = "D. 단일 단어 (1단어)"
TYPE_E = "E. 복합어 (2단어)"
TYPE_F = "F. 복합어 (3단어)"
TYPE_G = "G. 구/문장 (4단어 이상, 구분자 없음)"

# 1차 필터가 남기는 유형. 결과적으로 1~3단어만 채택된다.
KEEP_TYPES = {TYPE_D, TYPE_E, TYPE_F}


def classify(text):
    """영문명 하나를 A~G 로 분류한다. 판정 순서가 곧 우선순위다.

    콜론·세미콜론 축 조합을 먼저 걷어내야 한다. 이들은 단어 수와 무관하게
    LOINC 6축(Component:Property:Time:System:Scale:Method)을 기계적으로
    이어붙인 좌표 문자열이라 자연어 용어와 성격이 다르다.
    """
    if ":" in text:
        return TYPE_A
    if ";" in text:
        return TYPE_B
    if "," in text:
        return TYPE_C
    n = len(text.split())
    if n <= 1:
        return TYPE_D
    if n == 2:
        return TYPE_E
    if n == 3:
        return TYPE_F
    return TYPE_G


# ════════════════════════════════════════════════ LLM 배치 판정기
# 3차-2 · 4차 · 5차가 전부 이걸 쓴다. 프롬프트만 다르다.

_LOCK = threading.Lock()


def _call(system, user, max_tokens=4000, timeout=240):
    body = json.dumps({
        "model": GLM["model"],
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "reasoning_effort": "none",   # ← 없으면 추론에 토큰을 다 쓴다
    }).encode()
    req = urllib.request.Request(GLM["url"], data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + GLM["key"]})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def _parse(text, n):
    """[{"i":번호,"m":0|1}] 배열만 뽑아 dict 로. 90% 미만이면 실패 처리."""
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return None
    out = {}
    for x in arr:
        if isinstance(x, dict) and "i" in x and "m" in x:
            try:
                out[int(x["i"])] = 1 if int(x["m"]) == 1 else 0
            except Exception:
                pass
    return out if len(out) >= n * 0.9 else None


def judge_pairs(pairs, system, ckpt_path, slice_start=0, slice_end=None):
    """(영문명, 한글명) 쌍 목록을 배치로 판정한다.

    m=1 유지 / m=0 제거. 판정 못 한 쌍은 호출부에서 유지로 처리한다.
    체크포인트에 배치 단위로 append 하므로 중단 후 재실행하면 이어서 돈다.
    반환값은 {(en, ko): m}.
    """
    batches = [pairs[i:i + BATCH] for i in range(0, len(pairs), BATCH)]
    done = set()
    if os.path.exists(ckpt_path):
        for line in open(ckpt_path, encoding="utf-8"):
            try:
                done.add(json.loads(line)["b"])
            except Exception:
                pass
    lo, hi = slice_start, (len(batches) if slice_end is None else slice_end)
    todo = [i for i in range(lo, hi) if i not in done]
    print(f"  쌍 {len(pairs):,} / 배치 {len(batches):,} / "
          f"이번에 돌릴 배치 {len(todo):,} (완료 {len(done):,})", flush=True)

    fh = open(ckpt_path, "a", encoding="utf-8")
    prog = {"n": 0, "fail": 0}

    def work(bi):
        b = batches[bi]
        user = "\n".join(f"{j+1}. {en} | {ko}" for j, (en, ko) in enumerate(b))
        for attempt in range(4):
            try:
                v = _parse(_call(system, user), len(b))
                if v is None:
                    raise ValueError("파싱 실패")
                res = [[en, ko, v.get(j + 1, 1)] for j, (en, ko) in enumerate(b)]
                with _LOCK:
                    fh.write(json.dumps({"b": bi, "r": res}, ensure_ascii=False) + "\n")
                    fh.flush()
                    prog["n"] += 1
                    if prog["n"] % 50 == 0:
                        print(f"    ...{prog['n']} 배치 (실패 {prog['fail']})", flush=True)
                return
            except Exception as e:
                if attempt == 3:
                    with _LOCK:
                        prog["fail"] += 1
                        print(f"    [배치 {bi} 실패] {type(e).__name__}: {str(e)[:100]}",
                              flush=True)
                else:
                    time.sleep(2 + attempt * 4)

    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(work, todo))
    fh.close()
    print(f"  완료 {prog['n']} / 실패 {prog['fail']} / {time.time()-t0:.0f}s", flush=True)
    return load_verdicts(ckpt_path)


def load_verdicts(ckpt_path):
    """체크포인트를 {(en, ko): m} 으로 읽는다."""
    d = {}
    if not os.path.exists(ckpt_path):
        return d
    for line in open(ckpt_path, encoding="utf-8"):
        for en, ko, m in json.loads(line)["r"]:
            d[(en, ko)] = m
    return d


def slice_args(argv):
    """--slice A B 로 배치 범위를 나눠 여러 프로세스로 돌릴 때 쓴다."""
    if "--slice" in argv:
        i = argv.index("--slice")
        return int(argv[i + 1]), int(argv[i + 2])
    return 0, None
