# TCMT_translation

용어사전 기반 의학 번역 테스트 하네스. 한국 보건의료용어표준(V7.0) 사전을 LLM 번역에 연동했을 때 효과가 있는지 **단어 → 문장 → 문단** 3단계로 측정한다.

각 단계에서 `none`(용어집 없음) · `term`(정답 주입) · `random`(오답 주입) 3-mode 를 비교한다.

> ## 📘 설계·실험 결과·개념 설명은 Notion 문서 참고
> **https://app.notion.com/p/3b11420e0205813ca2f0f33e27b65636**
>
> 이 README 는 **실행 방법만** 다룬다.

---

## 준비

의존성 없음 — **Python 3.8+ 표준 라이브러리만** 쓴다.

```bash
git clone https://github.com/HeechanKim-Genon/TCMT_translation.git
cd TCMT_translation

cp .env.example .env      # 키·서빙 번호 입력
mkdir -p data             # 사전 CSV 배치
```

### 사전 파일

저작권 문제로 저장소에 포함하지 않는다. `data/` 에 직접 넣는다.

| 경로 | 설명 |
|---|---|
| `data/dictionary.csv` | 최종 번역사전 (약 7.7만 행) |
| `data/dictionary_sample2000.csv` | 빠른 점검용 표본 (2,806행) |

컬럼 스펙은 [`data/README.md`](data/README.md) 참고.

이 두 CSV 를 **만드는 코드**는 [`filtering/`](filtering/) 에 있다.
보건의료용어표준 V7.0 원본 339,181행 → 77,497행으로 줄이는 5단계 필터다.

### 환경변수 (`.env`)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `GLM_KEY` | — | **필수.** 번역 모델 API 키 |
| `QWEN_KEY` | — | **필수.** 데이터 생성 모델 API 키 |
| `GENOS_BASE` | `https://genos.genon.ai/api/gateway/rep/serving` | 게이트웨이 루트 |
| `GLM_SERVING` | `813` | 번역 모델 서빙 번호 |
| `QWEN_SERVING` | `752` | 생성 모델 서빙 번호 |
| `GLM_MODEL` | `zai-org/glm-5.2` | 모델 ID |
| `QWEN_MODEL` | `model` | 모델 ID |
| `TCMT_WORKERS` | `12` | 동시 요청 수 |
| `TCMT_DICT` | `data/dictionary.csv` | 사전 경로 |
| `TCMT_OUT` | `results/` | 결과 저장 위치 |
| `TCMT_DATA` | `dataset/` | 데이터셋 저장 위치 |

최종 URL 은 `{GENOS_BASE}/{GLM_SERVING}/v1/chat/completions` 로 조립된다.
**서빙을 새로 배포하면 `GLM_SERVING` 만 바꾸면 된다.**

---

## 실행

순서대로 실행한다. `build_dataset.py` 를 먼저 돌려야 나머지가 동작한다.

```bash
# STEP 0 — 데이터셋 생성
python3 build_dataset.py --terms 100 --paras 12 --per-para 8

# (a) 단어 단위
python3 run_a_word.py

# (b) 문장 단위
python3 run_b_sentence.py

# (c) 문단 단위
python3 run_c_paragraph.py
```

빠른 점검:

```bash
python3 build_dataset.py --dict sample2000 --terms 10 --paras 2 --per-para 5
python3 run_a_word.py --batch 5
python3 run_b_sentence.py
python3 run_c_paragraph.py --limit 2
```

### `build_dataset.py`

a/b/c 가 같은 용어 집합을 쓰도록 한 번에 만든다.

| 인자 | 기본 | 설명 |
|---|---|---|
| `--terms` | 200 | 평가 용어 수 |
| `--paras` | 20 | 문단 수 (`0` 이면 문단 생략) |
| `--per-para` | 8 | 문단당 용어 수 |
| `--words` | 180 | 문단 목표 단어수 |
| `--attempts` | 4 | 검증 실패 시 재생성 횟수 |
| `--dict` | 전체 사전 | `sample2000` 지정 가능 |
| `--seed` | 42 | 재현용 |

### `run_a_word.py`

| 인자 | 기본 | 설명 |
|---|---|---|
| `--arms` | 전체 | `1c,1a,1b,2A,2C` 중 선택 |
| `--batch` | 50 | 배치 arm 크기 |
| `--limit` | 0 | 앞 N개 용어만 (0=전체) |
| `--candidates` | 5 | `2C` 후보 개수 |

| arm | 내용 |
|---|---|
| `1c` | 단어 1개 = 호출 1개 (기준선) |
| `1a` | 사전순 인접 N개 배치 |
| `1b` | 무작위 N개 배치 |
| `2A` | 도메인 힌트 추가 |
| `2C` | 후보 N개 제시 → 택일 |

### `run_b_sentence.py`

| 인자 | 기본 | 설명 |
|---|---|---|
| `--modes` | `none,term,random` | 실행할 mode |
| `--limit` | 0 | 앞 N개만 |
| `--no-span` | off | span 요구 없이 순수 번역 (대조군) |

### `run_c_paragraph.py`

| 인자 | 기본 | 설명 |
|---|---|---|
| `--modes` | `none,term,random` | 실행할 mode |
| `--limit` | 0 | 앞 N개 문단만 |
| `--inject-target` | off | 매칭 대신 심은 용어를 주입 (매칭 오차 제거) |
| `--no-tail-filter` | off | 끝기능어 필터 끄고 비교 |

### 부속 실험 (`experiments/`)

```bash
python3 experiments/pilot_format_probe.py       # 형식 준수율·stop 지원 조사
python3 experiments/match_precision_test.py     # 매칭 정밀도 향상 기법 비교
```

---

## 결과

```
dataset/
├── terms.json          평가 용어 (정답 한글명 집합 포함)
├── sentences.json      b용 캐리어 문장
├── paragraphs.json     c용 문단 + 매칭 결과
└── meta.json           사용한 사전 경로

results/
├── a_word_*.json           arm별 전체 기록 (raw 응답 포함)
├── a_word_summary.json
├── a_word_rows.csv
├── b_sent_*.json / b_sent_summary.json / b_sent_rows.csv
├── c_para_*.json / c_para_summary.json
├── c_para_terms.csv        용어별 Term% 판정
└── c_para_translations.csv 번역문 전문
```

`.json` 이 원본이고 `.csv` 는 엑셀 확인용이다.

---

## 코드 구성

| 파일 | 역할 |
|---|---|
| `tcmt_common.py` | API 호출 · 사전 로드 · **용어 매칭** · 채점 |
| `build_dataset.py` | 데이터셋 생성 (문단은 번역 모델과 **다른 모델**로 생성) |
| `run_a_word.py` | (a) 단어 단위 |
| `run_b_sentence.py` | (b) 문장 단위 |
| `run_c_paragraph.py` | (c) 문단 단위 |

용어 매칭 로직은 `tcmt_common.py` 의 **`match_terms()`** 에 있다. 알고리즘 설명과 정밀도·재현율 실측치는 함수 docstring 에 정리되어 있다.

### `filtering/` — 사전 구축 파이프라인

`data/dictionary.csv` 를 만드는 코드. 실험 본체와 독립적으로 돌아간다.
자세한 실행법은 [`filtering/README.md`](filtering/README.md) 참고.

| 파일 | 역할 |
|---|---|
| `filtering/filter_common.py` | 경로 · 구조유형 분류 · **LLM 배치 판정기** |
| `filtering/stage1_structure.py` | 1차 — A/B/C/G 유형 제거 → 1~3단어만 채택 |
| `filtering/stage2_compose.py` | 2차 — 합성어 (구성단어 조합으로 재현되는 것) |
| `filtering/stage3_kcd.py` | 3차-1 — KCD 코드로 필터링 (V01~Y98) |
| `filtering/stage3b_medical.py` | 3차-2 — 비의학용어를 LLM으로 필터링 |
| `filtering/stage4_korean.py` | 4차 — 한글명이 긴 설명문·EDI 수가명인 경우 |
| `filtering/stage5_trivial.py` | 5차 — 사전 없이도 맞게 번역되는 일상어 제거 |
| `filtering/export.py` | CSV 3종 + 감사용 엑셀 산출 |

| 단계 | 잔존 | 증감 |
|---|---:|---:|
| 원본 | 339,181 | — |
| 1차 | 119,914 | −219,267 |
| 2차 | 91,937 | −27,977 |
| 3차-1 | 91,715 | −222 |
| 3차-2 | 87,741 | −3,974 |
| 4차 | 86,425 | −1,316 |
| 5차 | **77,497** | −8,928 |

---

## 주의

- **키는 `.env` 로만 받는다.** 저장소에 하드코딩된 키가 없고 `.env` 는 `.gitignore` 되어 있다.
- **사전 데이터는 포함하지 않는다.** 코드만 공개한다.
- 네트워크 장애가 감지되면 실행이 즉시 중단된다. 오염된 결과로 결론 내는 것을 막기 위함이다.
- 표본 추출·배치 순서·후보 생성이 전부 시드 고정이라 재현 가능하다.
