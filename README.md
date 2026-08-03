# TCMT_translation

**용어사전 기반 의학 번역 테스트 하네스** — 한국 보건의료용어표준(V7.0) 사전을 LLM 번역에 연동했을 때 실제로 효과가 있는지 측정한다.

학술적으로는 **TCMT (Terminology-Constrained Machine Translation)** 영역이며, WMT Terminology Shared Task 의 **3-mode 교차 실험** 설계를 따른다.

```
단어 (a)  →  문장 (b)  →  문단 (c)
                            ↑ 본 실험
```

---

## 무엇을 측정하는가

**"용어사전을 LLM에 연동하면 번역이 좋아지는가"** 를 3개 arm 으로 비교한다.

| mode | 프롬프트 | 역할 |
|---|---|---|
| `none` | 용어집 없음 | **baseline** |
| `term` | 정답 한글명 주입 | **terminology** |
| `random` | 일부러 **틀린** 한글명 주입 | **통제군** |

`random` 이 이 설계의 핵심이다. 틀린 용어집을 줬는데 모델이 그걸 따라가면 **모델이 용어집을 실제로 읽고 있다**는 증거이고, 그래야 `term` 의 개선을 인과로 주장할 수 있다. 무시한다면 `term` 의 개선은 용어집 때문이 아니다.

---

## 빠른 시작

```bash
git clone https://github.com/HeechanKim-Genon/TCMT_translation.git
cd TCMT_translation

cp .env.example .env      # 키와 서빙 번호를 채운다
mkdir -p data             # 사전 CSV 를 넣는다 (아래 참조)

python3 build_dataset.py --dict sample2000 --terms 10 --paras 2 --per-para 5
python3 run_a_word.py --batch 5
python3 run_b_sentence.py
python3 run_c_paragraph.py
```

의존성 없음 — **Python 3.8+ 표준 라이브러리만** 사용한다.

---

## 사전 파일

저작권 문제로 저장소에 포함하지 않는다. `data/` 에 직접 넣는다.

| 경로 | 용도 |
|---|---|
| `data/dictionary.csv` | 최종 번역사전 (약 7.7만 행 / 고유 영문명 5.6만) |
| `data/dictionary_sample2000.csv` | 빠른 점검용 표본 (2,806행 / 영문명 2,000) |

**12컬럼 스펙**

```
용어코드, 개념코드, 영문명, 한글명, KCD, ICD9CM, LOINC, EDI, CCC, ICNP, CDT, SNOMED CT
```

- **정답 집합** = 같은 `개념코드` 를 공유하는 모든 `한글명` (동의어 인정)
- **대표용어** = 파일에서 그 영문명이 처음 나온 행의 한글명
- **코드 컬럼**은 캐리어 문장 유형 판정에 쓴다 (KCD→진단, EDI/CDT→처치, LOINC→검사)

---

## 환경변수

`.env` 파일 또는 셸 환경변수로 준다. `.env` 는 `.gitignore` 되어 있다.

### 필수

| 변수 | 설명 |
|---|---|
| `GLM_KEY` | 번역 모델(측정 대상) API 키 |
| `QWEN_KEY` | 데이터 생성 모델 API 키 |

### 엔드포인트

| 변수 | 기본값 | 설명 |
|---|---|---|
| `GENOS_BASE` | `https://genos.genon.ai/api/gateway/rep/serving` | 게이트웨이 루트 |
| `GLM_SERVING` | `813` | 번역 모델 서빙 번호 |
| `QWEN_SERVING` | `752` | 생성 모델 서빙 번호 |
| `GLM_MODEL` | `zai-org/glm-5.2` | 모델 ID |
| `QWEN_MODEL` | `model` | 모델 ID |

최종 URL은 `{GENOS_BASE}/{SERVING}/v1/chat/completions` 로 조립된다. **서빙을 새로 배포하면 `GLM_SERVING` 만 바꾸면 된다.**

### 동작 설정

| 변수 | 기본값 | 설명 |
|---|---|---|
| `TCMT_WORKERS` | `12` | 동시 요청 수. 서빙의 최대 동시실행에 맞춰 올린다 |
| `TCMT_DICT` | `data/dictionary.csv` | 사전 경로 |
| `TCMT_DICT_SAMPLE` | `data/dictionary_sample2000.csv` | 표본 사전 경로 |
| `TCMT_OUT` | `results/` | 결과 저장 위치 |
| `TCMT_DATA` | `dataset/` | 데이터셋 저장 위치 |

---

## 스크립트

| 파일 | 역할 | 호출 모델 |
|---|---|---|
| `tcmt_common.py` | 공통 모듈 (직접 실행 안 함) | — |
| `build_dataset.py` | **STEP 0** 데이터셋 생성 | Qwen |
| `run_a_word.py` | **(a)** 단어 단위 | GLM |
| `run_b_sentence.py` | **(b)** 문장 단위 | GLM |
| `run_c_paragraph.py` | **(c)** 문단 단위 | GLM |
| `experiments/pilot_format_probe.py` | 형식 준수율 · `stop` 지원 조사 | GLM |
| `experiments/match_precision_test.py` | 매칭 정밀도 향상 기법 비교 | Qwen |

### STEP 0 — `build_dataset.py`

a/b/c 가 **같은 용어 집합**을 쓰도록 한 번에 만든다. 그래야 세 단계 점수를 직접 비교할 수 있다.

```bash
python3 build_dataset.py --terms 200 --paras 20 --per-para 8 --words 180
python3 build_dataset.py --dict sample2000 --terms 10 --paras 2 --per-para 5   # 빠른 점검
python3 build_dataset.py --paras 0                                            # a·b만 준비
```

| 인자 | 기본 | 설명 |
|---|---|---|
| `--terms` | 200 | 평가 용어 수 |
| `--paras` | 20 | 문단 수 (0이면 문단 생략) |
| `--per-para` | 8 | 문단당 심을 용어 수 |
| `--words` | 180 | 문단 목표 단어수 |
| `--attempts` | 4 | 검증 실패 시 재생성 횟수 |
| `--dict` | 전체 | `sample2000` 지정 가능 |
| `--seed` | 42 | 재현용 |

**문단 생성은 Qwen 으로 한다.** GLM 이 만든 문장을 GLM 이 번역하면 자기 선호 편향이 생긴다. 호출을 분리해도 가중치가 같으므로 **모델 자체를 분리**해야 한다.

생성 후 4가지를 검증하고 하나라도 실패하면 재생성한다 — 용어 원문 유지 / 한글 없음 / **동격 설명 없음**(정답 유출 방지) / 길이 범위.

### (a) — `run_a_word.py`

```bash
python3 run_a_word.py                    # 전체 arm
python3 run_a_word.py --arms 1c,2C       # 일부만
python3 run_a_word.py --limit 50         # 앞 50개 용어만
python3 run_a_word.py --batch 10         # 배치 크기 (품질-비용 곡선)
python3 run_a_word.py --candidates 5     # 2C 후보 개수
```

| arm | 내용 |
|---|---|
| `1c` | 단어 1개 = 호출 1개 (**기준선**) |
| `1a` | 사전순 인접 N개 배치 |
| `1b` | 무작위 N개 배치 |
| `2A` | `NOTE: standardized medical term` 힌트 추가 |
| `2C` | **후보 N개 제시 → 택일** (사전 참조 arm) |

`2C` 는 정답 1개 + 무작위 오답 4개를 섞는다. 정답만 주면 복사라서 자명하게 100%가 되므로, 실제 검색이 부정확한 상황을 모사한 것이다.

### (b) — `run_b_sentence.py`

```bash
python3 run_b_sentence.py
python3 run_b_sentence.py --modes none,term
python3 run_b_sentence.py --no-span       # span 요구 없이 순수 번역 (관찰자 효과 대조)
```

출력을 2필드로 받는다. `TERM` 이 `KO` 의 **부분문자열인지 코드로 검증**하므로 추출 실패와 모델 오답이 섞이지 않는다.

```
KO:   보고서에는 이 환자의 손목굴증후군이 기록되었다.
TERM: 손목굴증후군
```

캐리어 문장은 **용어 유형별로 다르다**. 유형이 안 맞는 문장은 없는 것보다 나쁘다 — `Delivery record`(분만기록)를 환자 소견 문장에 넣으면 **투여 기록**, 차트 문장에 넣으면 **배달 기록**으로 오역된다.

### (c) — `run_c_paragraph.py`

```bash
python3 run_c_paragraph.py
python3 run_c_paragraph.py --inject-target    # 매칭 대신 심은 용어를 주입 (매칭 오차 제거한 상한)
python3 run_c_paragraph.py --no-tail-filter   # 끝기능어 필터 끄고 비교
python3 run_c_paragraph.py --limit 5
```

**매칭 → 주입 → 번역** 3단계. 용어만 뽑아 번역하는 게 아니라 **문단 전체를 번역**한다.

채점은 문단 전체 BLEU가 아니라 **Term%(용어 준수율)** 다. 180단어 문단에 용어 8개면 전체 지표에는 묻히기 때문이다. WMT 용어 태스크가 Term%/TSR을 쓰는 이유가 같다.

---

## ★ 용어 매칭 — `tcmt_common.py` 의 `match_terms()`

파이프라인에서 **가장 중요하고 가장 취약한 단계**다. WMT 벤치마크는 문장별 용어 목록을 이미 제공하므로 이 단계가 존재하지 않지만, 실제 환경에서는 우리가 직접 해야 한다.

```python
hits = T.match_terms(paragraph_text, D,
                     use_tail_filter=True,    # 끝 기능어 배제
                     include_single=False,    # 단일어 포함 여부
                     max_n=5)                 # 최대 n-gram
# → [{"term": "carpal tunnel syndrome", "start": 41, "end": 63,
#     "rep": "손목굴증후군", "answers": [...]}, ...]
```

### 알고리즘

1. NFKC 정규화 → 소문자화 → 단어 토큰화
2. `n=5` 부터 내려가며 n-gram 대조 (**최장일치 우선**)
3. 이미 쓰인 토큰 재사용 금지 → `carpal tunnel` 이 `carpal tunnel syndrome` 안에서 중복 매칭되지 않는다
4. 끝 기능어(`to`/`of`/`with`/`than`/…)로 끝나는 표제어 제거

### 실측 정밀도 (MTSamples 영문 5개 문서, 후보 77개)

| 방법 | 정밀도 | 재현율 | 판정 |
|---|---|---|---|
| 최장일치만 | 88.3% | 100% | 기준선 |
| **+ 끝기능어 배제** | **93.2%** | **100%** | **기본값. 손실 없는 개선** |
| **+ LLM 분류기** | **97.1%** | **100%** | 사전에 1회 오프라인 적용 |
| 일반어 전량 배제 | 100% | 45.6% | ❌ 재현율 붕괴 |
| 코드 컬럼 보유만 | 100% | 16.2% | ❌ 재현율 붕괴 |

`back pain`, `blood pressure`, `bone scan` 같은 정상 용어가 전부 흔한 영어 단어로 이뤄져 있어 **"일반어면 버린다" 규칙은 쓰면 안 된다.** 코드 컬럼 유무도 마찬가지다.

#### 끝 기능어 배제

용어가 전치사·접속사로 **끝나면** 버린다. 공짜로 얻는 개선이다.

```
❌ secondary to  ·  no evidence of  ·  contact with     (기능어로 끝남)
✅ shortness of breath  ·  incision and drainage        (중간이라 안전)
```

#### LLM 분류기 필터

**사전 항목을 하나씩 LLM에게 물어보고 의학 용어가 아닌 것을 지운다.**

```
"secondary to" 는 임상 번역 용어집에 들어갈 의학 용어인가?   → NO   삭제
"carpal tunnel syndrome" 은?                              → YES  유지
```

**문서마다 하는 게 아니라 사전에 딱 한 번만 한다.** 용어당 약 `$0.000075` 이므로 표제어 전체를 돌려도 1만 원 남짓이고, 그 뒤로는 계속 그 사전을 쓰면 된다.

구현은 `experiments/match_precision_test.py` 참고.

### 실측 재현율 (합성 문단 2개, 심은 용어 10개)

| 용어 유형 | 재현율 |
|---|---|
| 다어절 | **7/7 = 100%** |
| 단일어 | **0/3 = 0%** |
| 합계 | **7/10 = 70%** |

놓친 3개는 전부 단일어였다 — `ruminations`, `cardiorrhexis`, `styrene`. `include_single=True` 로 켜면 10/10(100%)이 되고 오탐은 1→2개뿐이지만, **이 문단은 사전 용어로 만든 합성 데이터라 단일어 정밀도가 부풀려져 있다.** 실제 임상 문서에서는 `from`, `mass`, `room`, `air`, `history`, `culture` 가 전부 사전 표제어라 오탐이 급증한다.

→ 권장: `include_single=True` 로 켜되 **LLM 분류기로 걸러낸 사전**을 쓸 것.

### 아직 처리하지 못한 재현율 손실

| 유형 | 예 | 필요한 것 |
|---|---|---|
| 굴절형 | `ruminations` vs 표제어 `rumination` | lemmatize |
| 약어 | 문서는 `IVP`, 사전은 완전형 | 약어 확장 (Schwartz-Hearst) |
| 복합어 | — | SAP(EAMT 2020)은 lemma+2문자 fuzzy 로도 **미인식률 45%** 보고 |
| 어순·삽입 | `pain in the abdomen` vs `abdominal pain` | 어순 허용 매칭 |

### 중의성은 매칭으로 못 푼다

`discharge` 는 사전에 **귀가 / 방전 / 방출 / 분비물 / 유리 / 유출량 / 퇴원** 7개가 있다. Discharge Summary 문서에서 `퇴원` 을 고르려면 문맥이 필요하므로 **문자 매칭으로는 원리적으로 불가능**하다.

→ 후보 N개를 그대로 LLM 에 넘겨 고르게 한다. `run_a_word.py` 의 `2C` arm 이 이 방식을 측정한다.

---

## 채점

`tcmt_common.grade()` 가 4분류한다.

| 분류 | 의미 |
|---|---|
| `정답(대표)` | 대표 한글명과 일치 |
| `정답(동의어)` | 같은 개념코드의 다른 한글명과 일치 |
| `오답` | 정답 집합에 없음 |
| `형식실패` | 누락 · 다중 출력 · 파싱 불가 |

**형식실패를 오답에 합치지 않는다.** 배치 arm에서는 형식실패가 주된 실패 모드이고, 그게 곧 "묶어서 번역하면 안 된다"는 결론의 근거가 된다.

### 정규화 3단계

정규화 없이는 개선폭이 노이즈에 묻힌다. 캐리어 비교 24개 조합에서 **정확 일치가 0개**였고 절반이 띄어쓰기만 달랐다.

| 수준 | 예 |
|---|---|
| `exact` | `AC글로불린결핍` |
| `nospace` | `AC 글로불린 결핍` — 사전은 붙여쓰고 모델은 띄어쓴다 |
| `josa` | `AC글로불린결핍을` — 문장 단위에서 조사가 딸려 나온다 |

**조사는 파괴적으로 떼지 않는다.** `소화기내과` 의 `과` 처럼 실제 어미와 구분이 불가능하므로, 뗀 형태를 *후보로 추가*해 둘 중 하나라도 맞으면 정답으로 본다.

> 이 지표는 *번역 정확도*가 아니라 **표준 라벨 준수율**이다. `AIDS-Associated Nephropathy` 를 모델은 `후천성면역결핍증 관련 신증`, 사전은 `후천면역결핍증 관련 콩팥질환` 으로 적는다. 둘 다 의학적으로 맞지만 사전이 순화어를 쓴다.

---

## 실측으로 알게 된 것

### `reasoning` 을 끄지 않으면 답이 오지 않는다

GLM-5.2 는 thinking 모델이다. 끄지 않으면 `max_tokens` 를 전부 추론에 쓰고 `content` 가 비어서 온다.

```json
{"reasoning": {"enabled": false}}
```

**이 형식만 먹는다.** `thinking.type`, `chat_template_kwargs.enable_thinking`, `reasoning.exclude`, `reasoning.effort` 는 전부 무시된다.

| 설정 | reasoning 토큰 | 비용 |
|---|---|---|
| `reasoning.enabled=false` | **0** | **$0.000026** |
| 기본값 | 373 | $0.001024 |

**39배 차이**다. 다만 껐어도 약 3.5%는 새어나오므로 `finish_reason == "length"` 이거나 빈 응답이면 **재시도**한다. (재호출로 5/5 정상 복구 확인)

### `stop` 시퀀스는 필요 없다

수용은 되지만 효과가 0이다 (폭주 0/20). `reasoning` 을 끄면 모델이 추가 `ENG:` 쌍을 지어내지 않는다. 오히려 `\n\n` 같은 stop 이 즉시 발동해 빈 응답을 만들 수 있다.

### 배치는 `finish_reason` 을 반드시 검사한다

`max_tokens=4000` 으로 50개씩 묶었을 때 4개 배치 중 1개가 잘려 **36행이 조용히 사라졌다.** 이 코드는 `max(2000, batch_size * 90)` 으로 자동 계산한다.

### 정렬은 id 가 아니라 영문 echo 로

번호로 맞추면 모델이 한 줄만 빠뜨려도 그 뒤 전부가 밀려 **조용히 오답 처리**된다. 영문을 다시 받아적게 하면 어느 용어가 빠졌는지 정확히 특정된다.

### 서빙에 따라 처리량이 극단적으로 다르다

| 서빙 | 12건 벽시계 | 성공 |
|---|---|---|
| 813 (GLM-5.2) | **240.2초** | 10/12 |
| 752 (Qwen3.5) | **2.6초** | 12/12 |

동시 요청 수는 `TCMT_WORKERS` 로 조절한다. 서빙의 최대 동시실행 설정에 맞춰 올린다.

---

## 결과 파일

```
dataset/
├── terms.json          평가 용어 (정답 한글명 집합 포함)
├── sentences.json      b용 캐리어 문장
├── paragraphs.json     c용 문단 + 매칭 결과
└── meta.json           사용한 사전 경로

results/
├── a_word_{1c,1a,1b,2A,2C}.json    arm별 전체 기록 (raw 응답 포함)
├── a_word_summary.json / a_word_rows.csv
├── b_sent_{none,term,random}.json
├── b_sent_summary.json / b_sent_rows.csv
├── c_para_{none,term,random}.json
├── c_para_summary.json
├── c_para_terms.csv                용어별 Term% 판정
└── c_para_translations.csv         번역문 전문
```

`.csv` 는 엑셀로 눈으로 확인하는 용도이고, `.json` 이 원본이다.

---

## 안전장치

- **네트워크 장애 감지** — `netguard()` 가 장애 발생 시 즉시 중단한다. 오염된 결과로 결론을 내는 것을 막는다
- **비밀값 분리** — 키는 `.env` 로만 받는다. 저장소에 하드코딩된 키가 없다
- **시드 고정** — 표본 추출, 배치 순서, `2C` 후보, `random` arm 오답이 전부 재현 가능하다

---

## 라이선스 / 주의

사전 데이터(보건의료용어표준 V7.0)는 저장소에 포함되지 않는다. 코드만 공개한다.

정밀도 라벨은 **필자 판단**이며 임상 전문가 검증을 받지 않았다. `left hand`, `alcoholic beverages` 같은 경계 사례가 있다.
