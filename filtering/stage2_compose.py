# -*- coding: utf-8 -*-
"""2차 — 합성어인 경우 (구성단어 조합으로 재현되는 것) 제거

구성 단어를 따로 번역해 이어붙인 결과와 실제 한글명이 **같으면** 사전에 넣을
정보가 없다. **다르면** 그게 바로 사전이 필요한 이유다.

  cardiac = 심장,  ventricle = 심실,  asthma = 천식
  [채택] Cardiac ventricle → 심실       (심장+심실 = "심장심실" ≠ "심실")
  [제거] Cardiac asthma   → 심장 천식   (심장+천식 = "심장천식" = 실제와 같음)

판정 방식
  · 유니그램 사전 = 1단어(D) 행 / 바이그램 사전 = 2차에서 살아남은 2단어(E) 행
  · 3단어(F)는 (1+1+1), ([2단어]+1), (1+[2단어]) 세 경로로 분해 시도
  · 비교 전 공백·하이픈·중점 제거. 파트 순서 무관.
    파트 사이 접속형태소 성/의/적/형/증/부 삽입 허용. 복수형 폴백 적용.

■ 구성 단어가 사전에 없어 **검증할 수 없으면 보존**한다(28,644행).
  실수로 빠뜨리는 것보다 사전이 조금 커지는 게 낫다. '보존:분해불가' 로 표시된다.

  119,914 → 91,937
"""
import collections
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filter_common as fc

# 단어를 이어붙일 때 한국어에서 흔히 끼어드는 형태소
CONN = ("", "성", "의", "적", "형", "증", "부")


def norm_ko(s):
    return re.sub(r"[\s\-·]", "", s)


def norm_en(t):
    return t.lower().strip(".,;:()[]")


def build_unigrams(d):
    uni = collections.defaultdict(set)
    single = d[d["구조유형"] == fc.TYPE_D]
    for en, ko in zip(single["영문명"], single["한글명"]):
        uni[norm_en(en)].add(norm_ko(ko))
    return uni


def make_cand(uni):
    def cand(tok):
        """영문 토큰 → 가능한 한글 표현 집합. 없으면 None(=분해 불가)."""
        t = norm_en(tok)
        if t in uni:
            return uni[t]
        # ⚠ 순서와 ies 규칙을 바꾸지 말 것 — data/dictionary.csv 가 이 동작으로 만들어졌다.
        #   · -s 를 먼저 본다 (nodes → "nod" 보다 "node" 를 먼저 찾아야 한다)
        #   · ies 규칙은 t[:-2]+"y" 라서 bodies → "bodiy" 가 되어 사실상 안 맞는다.
        #     t[:-3]+"y" 로 고치면 2차 잔존이 91,937 → 91,886 으로 바뀐다.
        #     고칠 거면 3차-2 이후 LLM 단계를 전부 다시 돌리고 문서 수치도 갱신해야 한다.
        alts = []
        if t.endswith("s"):
            alts.append(t[:-1])
        if t.endswith("ies"):
            alts.append(t[:-2] + "y")
        if t.endswith("es"):
            alts.append(t[:-2])
        for a in alts:
            if a in uni:
                return uni[a]
        return None
    return cand


def segments(target, groups, first=True):
    """target 을 groups(파트별 후보집합)로 완전분해할 수 있는가.

    순서 무관 + 파트 사이 접속형태소 허용. 재귀 접두 매칭이라 후보 개수가
    많아도 조합을 전부 생성하지 않는다.
    """
    if not groups:
        return target == ""
    for i, g in enumerate(groups):
        rest = groups[:i] + groups[i + 1:]
        for c in g:
            if not c:
                continue
            for cn in (("",) if first else CONN):
                pref = cn + c
                if target.startswith(pref) and segments(target[len(pref):], rest, False):
                    return True
    return False


def main():
    d = pd.read_csv(fc.w("stage1.csv"), dtype=str, keep_default_na=False)
    print(f"[2차] 입력 {len(d):,}행")

    uni = build_unigrams(d)
    cand = make_cand(uni)

    # ── 2단어(E)
    e = d[d["구조유형"] == fc.TYPE_E].copy()
    flags, evid = [], []
    for en, ko in zip(e["영문명"], e["한글명"]):
        toks = en.split()
        g = [cand(t) for t in toks]
        if any(x is None for x in g):
            flags.append("보존:분해불가")
            evid.append("사전에 없는 구성단어: "
                        + ",".join(t for t, x in zip(toks, g) if x is None))
        elif segments(norm_ko(ko), g):
            flags.append("제거:합성어")
            evid.append(" + ".join(toks))
        else:
            flags.append("보존:비합성")
            evid.append("구성단어 조합으로 재현 안 됨")
    e["2차판정"], e["2차근거"] = flags, evid
    print("  2단어:", dict(collections.Counter(flags)))

    # ── 바이그램 사전은 '보존된' 2단어만 쓴다.
    #    제거된 2단어는 그 자체가 유니그램으로 분해되므로 (1+1+1) 경로가 커버한다.
    bi = collections.defaultdict(set)
    for en, ko in zip(e.loc[e["2차판정"].str.startswith("보존"), "영문명"],
                      e.loc[e["2차판정"].str.startswith("보존"), "한글명"]):
        bi[tuple(norm_en(t) for t in en.split())].add(norm_ko(ko))

    # ── 3단어(F)
    f = d[d["구조유형"] == fc.TYPE_F].copy()
    flags, evid = [], []
    for en, ko in zip(f["영문명"], f["한글명"]):
        t1, t2, t3 = en.split()
        nk = norm_ko(ko)
        paths = []
        g3 = [cand(t1), cand(t2), cand(t3)]
        if all(x is not None for x in g3):
            paths.append((g3, f"{t1} + {t2} + {t3}"))
        b12, b23 = bi.get((norm_en(t1), norm_en(t2))), bi.get((norm_en(t2), norm_en(t3)))
        if b12 is not None and cand(t3) is not None:
            paths.append(([b12, cand(t3)], f"[{t1} {t2}] + {t3}"))
        if b23 is not None and cand(t1) is not None:
            paths.append(([cand(t1), b23], f"{t1} + [{t2} {t3}]"))
        if not paths:
            flags.append("보존:분해불가")
            evid.append("구성요소가 사전에 없음")
            continue
        hit = next((ev for groups, ev in paths if segments(nk, groups)), None)
        if hit:
            flags.append("제거:합성어")
            evid.append(hit)
        else:
            flags.append("보존:비합성")
            evid.append("구성요소 조합으로 재현 안 됨")
    f["2차판정"], f["2차근거"] = flags, evid
    print("  3단어:", dict(collections.Counter(flags)))

    # ── 1단어(D)는 전량 보존. 합성 여부를 따질 대상이 아니다.
    one = d[d["구조유형"] == fc.TYPE_D].copy()
    one["2차판정"], one["2차근거"] = "보존:단일단어", ""

    judged = pd.concat([one, e, f]).sort_index()
    judged.to_csv(fc.w("stage2_judged.csv"), index=False, encoding="utf-8-sig")
    keep = judged[~judged["2차판정"].str.startswith("제거")]
    keep.to_csv(fc.w("stage2.csv"), index=False, encoding="utf-8-sig")
    print(f"\n  2차 통과: {len(keep):,}행 (제거 {len(judged)-len(keep):,})")


if __name__ == "__main__":
    main()
