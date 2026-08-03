# filtering/ — 사전 구축 파이프라인

이 실험에 쓰는 `data/dictionary.csv` 를 **어떻게 만들었는지**에 대한 코드다.
보건의료용어표준 V7.0 원본 **339,181행 → 77,497행**으로 줄이는 5단계 필터.

> ## 📘 각 단계의 근거·실측치·판단 이유는 Notion 문서 참고
> **https://app.notion.com/p/V7-0-EN-KO-3b11420e0205818eb1dcedd866b7fb24**
>
> 이 README 는 **실행 방법만** 다룬다.

---

## 왜 거르는가

사전은 **번역 LLM이 사전 없이 번역하면 틀리는 용어**만 담아야 한다.
사전 없이도 맞게 번역되는 항목은 넣을 이유가 없다 — 검색 노이즈만 늘린다.

설계 원칙 4개:

- 사전 없이도 맞는 건 뺀다 (`Ability → 능력`)
- 1:N 은 **버리지 않는다.** N개를 다 노출하고 LLM이 문맥으로 고르게 한다
- 판정 기준 컬럼은 기본적으로 **영문명**. 단 4·5차는 `(영문명, 한글명)` 쌍 단위
- **애매하면 남긴다.** 실수로 빠뜨리는 것보다 사전이 조금 커지는 게 낫다

## 5단계

| 단계 | 기준 | 잔존 | 증감 |
|---|---|---:|---:|
| 원본 | 보건의료용어표준 V7.0 전체 | 339,181 | — |
| 1차 | A/B/C/G 유형 제거 → 1~3단어만 채택 | 119,914 | −219,267 |
| 2차 | 합성어인 경우 (구성단어 조합으로 재현되는 것) | 91,937 | −27,977 |
| 3차-1 | KCD 코드로 필터링 (V01~Y98) | 91,715 | −222 |
| 3차-2 | 비의학용어를 LLM으로 필터링 | 87,741 | −3,974 |
| 4차 | 한글명이 긴 설명문·EDI 수가명인 경우 | 86,425 | −1,316 |
| 5차 | 사전 없이도 맞게 번역되는 일상어 제거 | **77,497** | −8,928 |

최종 77,497행 / 고유 영문명 55,988 / 고유 한글명 68,122 / 1:N 영문명 16,701

### 구조유형 A~G

1차가 쓰는 라벨이다. **영문명의 생김새**로만 나눈다.

| 유형 | 설명 | 예시 |
|---|---|---|
| A | 콜론(:) 축 조합 — 임상검사 LOINC | `A Ab:Pr:Pt:Ser/Plas:Ord` |
| B | 세미콜론(;) 축 조합 — 방사선 | `CT;Abdomen;With contrast` |
| C | 반점(,) 포함 구문·문장 | `Skin vasculitis, chronic` |
| D | 단일 단어 | `Discharge` |
| E | 복합어 (2단어) | `Cardiac ventricle` |
| F | 복합어 (3단어) | `Chronic gouty nephropathy` |
| G | 구·문장 (4단어 이상) | `Endarterectomy with temporary bypass during procedure` |

**A·B(108,462행)는 버린 게 아니라 별도 로직 대상이다.** LOINC 6축을 기계적으로
이어붙인 좌표 문자열이라 통짜 사전 엔트리로 만들면 안 된다. 처리 방식은 미결.

---

## 준비

파이프라인만 **pandas · openpyxl 이 필요하다** (하네스 본체는 표준 라이브러리만 쓴다).

```bash
pip install pandas openpyxl

export KOSTOM_XLSX=/path/to/보건의료용어표준_V7.0_분야전체.xlsx
```

LLM 단계(3차-2 · 4차 · 5차)는 저장소 루트의 `.env` 를 그대로 쓴다 —
`GLM_KEY` · `GENOS_BASE` · `GLM_SERVING` · `GLM_MODEL`.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `KOSTOM_XLSX` | — | **필수.** 원본 엑셀 경로 (시트명 `V7.0`) |
| `FILTER_WORK` | `filtering/work` | 단계별 중간 산출물 |
| `FILTER_OUT` | `filtering/out` | 최종 CSV·엑셀 |
| `FILTER_WORKERS` | `12` | 동시 요청 수 |
| `FILTER_BATCH` | `50` | 배치당 판정 항목 수 |

## 실행

순서대로 돌린다. 각 단계가 앞 단계의 CSV 를 읽는다.

```bash
python3 filtering/stage1_structure.py     # 원본 로드 + 구조유형 분류 + 1차
python3 filtering/stage2_compose.py       # 2차 합성어
python3 filtering/stage3_kcd.py           # 3차-1 KCD
python3 filtering/stage3b_medical.py      # 3차-2 LLM   (약 30분)
python3 filtering/stage4_korean.py        # 4차 LLM     (약 5분)
python3 filtering/stage5_trivial.py       # 5차 LLM     (약 30분)
python3 filtering/export.py               # CSV 3종 + 감사용 엑셀
```

LLM 단계는 **배치 단위로 체크포인트**를 쌓는다(`work/verdicts_*.jsonl`).
중단해도 같은 명령을 다시 치면 완료된 배치를 건너뛰고 이어서 돈다.

배치를 나눠 여러 프로세스로 돌리면 그만큼 빨라진다:

```bash
python3 filtering/stage5_trivial.py --slice 0    440 &
python3 filtering/stage5_trivial.py --slice 440  880 &
python3 filtering/stage5_trivial.py --slice 880  1320 &
python3 filtering/stage5_trivial.py --slice 1320 1754 &
wait
python3 filtering/stage5_trivial.py       # 남은 배치 정리 + CSV 확정
```

## 산출물

```
filtering/out/
├── dictionary.csv                    → data/dictionary.csv 로 복사
├── dictionary_sample2000.csv         → data/dictionary_sample2000.csv 로 복사
├── dictionary_sample2000_one.csv     영문명당 1행 (2,000행)
└── filtering_audit.xlsx              퍼널·분포·단계별 제거내역 전량

filtering/work/                       중간 산출물 + LLM 체크포인트
```

CSV 는 **원본과 같은 12컬럼 스펙**이다. 파생 컬럼은 감사용 엑셀에만 있다.

```
용어코드, 개념코드, 영문명, 한글명, KCD, ICD9CM, LOINC, EDI, CCC, ICNP, CDT, SNOMED CT
```

`work/` 와 `out/` 은 `.gitignore` 되어 있다. **사전 데이터는 저장소에 넣지 않는다.**

---

## 주의

- **길이 기준으로 자르지 마라.** 4차에서 "영문 대비 한글 3배 이상"으로 자르면
  잘리는 게 전부 약어다 — `HIV → 사람면역결핍바이러스`, `TIPS → 경정맥경유간내문맥전신순환션트`.
  룰은 후보만 뽑고 판정은 LLM 이 한다.
- **KCD 외인 필터는 ALL 기준이다.** 하나라도 V~Y 면 제거(ANY)하면
  `Asphyxiation → 질식`(KCD `T71|W84`)처럼 정상 용어가 죽는다.
- **4·5차 판정은 쌍 단위다.** 영문명 단위로 하면 한 단어의 한글 후보를
  전부 살리거나 전부 죽여야 한다.
- 2차에서 구성 단어를 사전에서 못 찾으면 **보존**한다(28,644행, `보존:분해불가`).
- 표본 추출은 시드 고정(`SEED = 20260803`)이라 재현 가능하다.
