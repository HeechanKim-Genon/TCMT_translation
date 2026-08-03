# 생성된 합성 문단 예시

`build_dataset.py` 가 만든 문단과 `run_c_paragraph.py` 의 3-mode 번역 결과다.

문단 생성은 **Qwen3.5-397B**, 번역은 **GLM-5.2** — 서로 다른 모델이라 자기 선호 편향이 없다.

전체 99개 문단 중 앞 3개만 실었다. 설계 설명은 [Notion 문서](https://app.notion.com/p/3b11420e0205813ca2f0f33e27b65636) 참고.


> **주입 용어가 3개가 아니라 40개인 이유**
>
> 문단에 *의도적으로 심은* 용어는 3개다. 하지만 매칭은 5.5만 표제어 사전 전체를
> 대조하므로, 심지 않은 사전 표제어가 문단당 평균 34개 더 걸린다 (`vital signs`,
> `physical examination` 처럼 임상 문서에 자연히 등장하는 것들). 그것들도 용어집에
> 함께 주입되므로 실제 주입량은 문단당 40.6개다. 아래 표는 **심은 3개만** 보여준다.


---

## P001

단어수 181 · 심은 용어 3개 · 용어집 주입 45개 (심은 것 + 자연발생)


### 심어둔 용어

| 영문 표제어 | 표준 한글명 | 어절 | 매칭 |
|---|---|---|---|
| `hammerhead ribozyme` | 망치머리형리보자임 | 2 | ✅ |
| `case-mix` | 질병구성 | 1 | ✅ |
| `psgn` | 연쇄구균감염후 사구체신염 | 1 | ✅ |

### 생성된 영어 문단

```
The patient presented with acute nephritic syndrome characterized by hematuria, hypertension, and mild edema following a recent streptococcal throat infection. Initial laboratory evaluation strongly suggested psgn as the primary etiology, supported by elevated anti-streptolysin O titers and depressed complement levels. While managing fluid balance and blood pressure, the care team reviewed the hospital quarterly report regarding case-mix indices to ensure appropriate resource allocation for this complex renal presentation. Concurrently, the research division requested a small urine sample for an investigational study involving a novel hammerhead ribozyme designed to target specific viral RNA sequences, though this experimental protocol remains separate from the standard therapeutic regimen for the current glomerulonephritis. The patient responded well to supportive care, with gradual improvement in renal function over the subsequent forty-eight hours. Discharge planning included strict sodium restriction and follow-up monitoring to track resolution of the inflammatory process. No immediate indications for biopsy were noted given the classic clinical picture and serological findings. The interdisciplinary team emphasized the importance of adherence to medication schedules and outpatient nephrology appointments to prevent long-term complications associated with post-infectious glomerular injury.
```

### `none` — 용어집 없음

심은 용어 Term% = 0/3

```
최근 연쇄상구균 인두 감염 이후, 환자는 혈뇨, 고혈압 및 경미한 부종을 특징으로 하는 급성 신염 증후군으로 내원하였다. 초기 검사실 평가에서는 상승된 항연쇄구균용혈소 O 역가와 감소된 보체 수치가 뒷받침하여, PSGN이 주요 원인일 가능성이 매우 높은 것으로 시사되었다. 의료진은 체액 균형과 혈압을 관리하는 동시에, 이러한 복잡한 신장 질환 사례에 대한 적절한 자원 배분을 보장하기 위해 병원의 분기별 케이스믹스 지수 보고서를 검토하였다. 이와 동시에, 연구 부서에서는 특정 바이러스 RNA 서열을 표적으로 하도록 고안된 새로운 해머헤드 리보자임을 활용한 연구용 시험을 위해 소량의 소변 샘플을 요청하였으나, 이 실험적 프로토콜은 현재 사구체신염의 표준 치료 요법과는 별개로 진행된다. 환자는 보존적 치료에 잘 반응하였으며, 이후 48시간 동안 신기능이 점진적으로 호전되었다. 퇴원 계획에는 엄격한 나트륨 제한과 염증 과정의 소실을 추적하기 위한 추적 모니터링이 포함되었다. 전형적인 임상 양상과 혈청학적 소견을 고려할 때 즉각적인 생검의 적응증은 없었다. 다학제 진료팀은 감염 후 사구체 손상과 관련된 장기적 합병증을 예방하기 위해 약물 복용 일정과 외래 신장내과 진료 예약을 준수하는 것의 중요성을 강조하였다.
```

놓친 용어: `hammerhead ribozyme`(망치머리형리보자임), `case-mix`(질병구성), `psgn`(연쇄구균감염후 사구체신염)

### `term` — 정답 용어집 주입

심은 용어 Term% = 3/3

```
환자는 최근의 사슬알균- 인두 감염에 이어 혈뇨, 고압 및 경미한 부종을 특징으로 하는 급성 신염증후군으로 태아위치되었다. 초기 기공의 평가는 높은 항스트렙톨리신 O 역가와 함몰- 도움체 수치에 의해 뒷받침되어 연쇄구균감염후 사구체신염을 원발- 병인으로 강하게 시사했다. 액 저울과 혈압을 관리하는 동안, 진료 팀은 이 복잡한 콩팥- 태아위치에 대한 적절한 자원 할당을 보장하기 위해 질병구성 지수에 관한 병원 분기별 보고서를 검토했다. 동시에, 연구 부서는 현재 사구체신염에 대한 원기 치료- 양생법과는 별개로 이 실험적 연구계획서가 남아 있지만, 종- 바이러스- RNA 서열을 표적세포로 하도록 설계된 새로운 망치머리형리보자임을 포함하는 조사 검사를 위해 소량의 요 표본인구를 요청했다. 환자는 보조 치료에 잘 반응했으며, 이후 48시간 동안 콩팥- 기능의 점진적 개선을 보였다. 유출량 계획에는 염증- 과정의 분해능을 추적하기 위한 엄격한 나트륨 제한과 추구관리 모니터링이 포함되었다. 전형적인 진료- 양상과 혈청학적- 소견을 고려할 때 생검에 대한 즉각적인 적응증은 없었다. 학제간 팀은 감염 후 토리- 손상과 관련된 장기적 합병증을 예방하기 위해 약물 처치 일정과 외래환자 신장학 예약에 대한 이행의 중요성을 강조했다.
```

### `random` — 오답 용어집 주입

준 오답: `hammerhead ribozyme` → 알레르기혈청, `case-mix` → 인두편도 생검, `psgn` → 유전감염

심은 용어 Term% = 1/3 · 오답 추종 3/3

```
환자는 최근 무균실험대 음압 감염에 이어 무릎뼈의 장애, 후두기관협착(증) 및 경미한 부종을 특징으로 하는 디스트로피성 수포성 표피박리증으로 나타났다. 초기 구안지 증후군 평가는 높은 항스트렙톨리신 O 역가와 수막뇌류 구순증 수치에 의해 뒷받침되어 유전감염이 수막뇌류 음악이라고 강력히 시사했다. 합곡(合谷) 중간수근골(관절)의 탈구 및 혈압을 관리하는 동안, 판막이동수술 팀은 이 복잡한 질병구성 녹내장성백내장에 적절한 자원 배분을 보장하기 위해 질병구성 지수에 관한 병원 분기 보고서를 검토했다. 동시에, 연구 부서는 현재 자색반 발진에 대한 크립토콕쿠스수막대뇌염 욕조 발바닥쪽 굽힘과는 별개로 이 실험적 종양분류법이 유지되지만, 불수의- 신경정신과학 자궁수축 변화 RNA 서열을 표적으로 설계된 새로운 알레르기혈청을 포함하는 조사 해마경화(증)를 위해 소량의 귀속- 인어다리 증후군을 요청했다. 환자는 직장경에 잘 반응했으며, 이후 48시간 동안 질병구성 기능이 점진적으로 수막뇌류되었다. 헌혈 계획에는 엄격한 나트륨 제한과 통풍관절염 노르메타네프린의 직장경을 추적하기 위한 왕복진탕기 모니터링이 포함되었다. 전형적인 심장마비- 양상과 과도흥분 소견을 고려할 때 중간형 지중해빈혈의 즉각적인 적응증은 없었다. 다학제 팀은 감염 후 인어다리 증후군 손상과 관련된 장기적 합병증을 예방하기 위해 인두편도 생검 일정과 무릎뼈의 장애 바깥귀길위오목 예약에 바깥귀길위오목의 중요성을 강조했다.
```


---

## P002

단어수 178 · 심은 용어 3개 · 용어집 주입 37개 (심은 것 + 자연발생)


### 심어둔 용어

| 영문 표제어 | 표준 한글명 | 어절 | 매칭 |
|---|---|---|---|
| `cheilosis` | 구순증 | 1 | ✅ |
| `hippocampal sclerosis` | 해마경화(증) | 2 | ✅ |
| `surgical staging` | 외과적시기결정 | 2 | ✅ |

### 생성된 영어 문단

```
The patient presented with persistent cheilosis affecting the lower lip vermilion, characterized by fissuring and mild erythema that failed to resolve with topical emollients. Concurrent neurological evaluation revealed significant memory deficits, prompting advanced imaging which confirmed unilateral hippocampal sclerosis with associated volume loss and signal hyperintensity on T2-weighted sequences. Given the refractory nature of the seizures and the clear structural lesion, the multidisciplinary team recommended surgical staging to delineate the epileptogenic zone precisely. This comprehensive surgical staging included prolonged video-EEG monitoring, high-resolution MRI volumetry, and neuropsychological testing to assess functional reserve prior to any potential resection. The cheilosis was managed supportively while the primary focus remained on the intricate planning required for the upcoming surgical staging protocol. Careful coordination between dermatology and neurology ensured that systemic factors were ruled out before proceeding. The patient tolerated the initial phases of surgical staging well, showing no adverse reactions to the invasive electrode placement. Final decisions regarding therapeutic intervention will depend entirely on the data gathered during this critical surgical staging period, aiming to maximize seizure freedom while preserving cognitive function.
```

### `none` — 용어집 없음

심은 용어 Term% = 0/3

```
환자는 국소 보습제로 호전되지 않는 갈라짐과 경도 홍반을 특징으로 하는 하순 vermilion 부위의 지속성 구순염을 주소로 내원하였다. 동반된 신경학적 평가에서 유의한 기억 결손이 확인되어 시행한 고급 영상 검사에서 T2 강조 영상序列에서 과신호 강도와 동반된 용적 감소를 보이는 편측 해마 경화증이 확인되었다. 난치성 간질 발작의 특성과 명확한 구조적 병변을 고려하여, 다학제 팀은 간질 발생 영역을 정확히 규명하기 위해 수술적 병기 설정을 권고하였다. 이 포괄적인 수술적 병기 설정에는 장시간 비디오-EEG 모니터링, 고해상도 MRI 용적 측정 및 잠재적 절제 전 기능적 예비력을 평가하기 위한 신경심리학적 검사가 포함되었다. 향후 수술적 병기 설정 프로토콜에 필요한 복잡한 계획 수립에 주안점을 둔 상태에서 구순염은 대증적으로 관리되었다. 피부과와 신경과 간의 긴밀한 조율을 통해 진행 전 전신적 요인이 배제되었다. 환자는 수술적 병기 설정의 초기 단계를 잘 견뎠으며, 침습적 전극 삽입에 대한 이상 반응을 보이지 않았다. 인지 기능 보존과 함께 간질 발작으로부터의 자유를 최대화하는 것을 목표로, 치료적 중재와 관련된 최종 결정은 이 중요한 수술적 병기 설정 기간 동안 수집된 데이터에 전적으로 좌우될 것이다.
```

놓친 용어: `cheilosis`(구순증), `hippocampal sclerosis`(해마경화(증)), `surgical staging`(외과적시기결정)

### `term` — 정답 용어집 주입

심은 용어 Term% = 3/3

```
환자는 하순 vermilion에 영향을 미치는 잔류- 구순증으로 내원하였으며, 국소- emollients로 해결되지 않는 균열과 경미한 홍반이 특징이었다. 동시- 신경학적 평가에서 유의한 기억 결손이 나타나 고급 조영을 시행하였으며, 이를 통해 편측 해마경화(증)과 관련된 -량 소실 및 T2 강조 영상에서의 신호 고강도가 확인되었다. 간질발작의 불응- 성격과 명확한 구조적 병소를 고려하여, 다학제 팀은 뇌전증유발- 영역을 정확히 규명하기 위해 외과적시기결정을 권장하였다. 이 포괄적인 외과적시기결정에는 장시간의 video-EEG 모니터링, 고해상도 MRI 용적측정 및 잠재적 절제(술) 전에 기능적 예비력을 평가하기 위한 신경심리학적 검사가 포함되었다. 구순증은 보존적으로 관리되는 동안, 다가오는 외과적시기결정 연구계획서에 필요한 복잡한 계획에 원발- 병터가 계속 집중되었다. 피부과와 신경학 간의 면밀한 협응 덕분에 진행하기 전에 전신성- 요인들이 배제될 수 있었다. 환자는 외과적시기결정의 초기 단계를 잘 견디었으며, 침습적 전극 배치에 대한 예방접종후 이상반응을 보이지 않았다. 치료- 중재적시술에 관한 최종 결정은 인지 기능을 보존하면서 간질발작 자유를 최대화하는 것을 목표로, 이 고비- 외과적시기결정 기간 동안 수집된 데이터에 전적으로 좌우될 것이다.
```

### `random` — 오답 용어집 주입

준 오답: `cheilosis` → 후두기관협착(증), `hippocampal sclerosis` → 위팔, `surgical staging` → 대망탈장

심은 용어 Term% = 0/3 · 오답 추종 3/3

```
환자는 파울러자유아메바 후두기관협착(증)이 심장마비- 입술 홍색부를 불수의- 하여 나타났으며, 국소통증 연화제로도 해결되지 않는 균열과 경미한 폐의 무발생이 특징이었다. 욕조 신경학적 평가에서 합곡(合谷) 기억 결핍이 드러나 진행된 융합꼭지돌기염을 시행하였고, 이를 통해 정균작용 위팔에서 T2 강조 영상에서 신경정신과학 근육의 결여 및 신호 고강도를 동반한 것이 확인되었다. 발작의 부고환관 성격과 명확한 구조적 제3뇌구조를 고려하여, 다학제 팀은 제3뇌구조 영역을 정확히 규명하기 위해 대망탈장을 권장하였다. 이 포괄적인 대망탈장에는 진성당뇨병 망치머리형리보자임 전에 기능적 예비력을 평가하기 위한 장시간의 비디오-EEG 모니터링, 고해상도 MRI 용적측정 및 신경심리검사가 포함되었다. 후두기관협착(증)은 보존적으로 관리되는 동안 수막뇌류 섬경화증은 다가오는 대망탈장 종양분류법에 필요한 복잡한 계획에 맞춰져 있었다. 피부과와 내시경 이용 눈물주머니코안 연결 간의 신중한 불수의- 통해 유전감염 요인이 배제되었음을 확인하였다. 환자는 대망탈장의 초기 단계를 잘 견뎌내며, 중간형 지중해빈혈 온등세모근 삽입에 대한 위팔을 보이지 않았다. 혈압측정(법)에 관한 최종 결정은 이 주혈흡충 대망탈장 기간 동안 수집된 데이터에 전적으로 좌우될 것이며, 인지 기능을 보존하면서 온등세모근 자유를 최대화하는 것을 목표로 한다.
```


---

## P003

단어수 173 · 심은 용어 3개 · 용어집 주입 30개 (심은 것 + 자연발생)


### 심어둔 용어

| 영문 표제어 | 표준 한글명 | 어절 | 매칭 |
|---|---|---|---|
| `bidiscoidal placenta` | 두원반태반 | 2 | ✅ |
| `reciprocal shaker` | 왕복진탕기 | 2 | ✅ |
| `high quality-hcv ab` | 정밀면역검사-C형간염항체 | 3 | ✅ |

### 생성된 영어 문단

```
The patient presented for routine obstetric evaluation with a history suggestive of placental anomalies. Ultrasound imaging confirmed the presence of a bidiscoidal placenta, characterized by two distinct lobes connected by fetal vessels, which requires careful monitoring throughout the remainder of the gestation to prevent potential complications such as vasa previa or retained placental tissue post-delivery. Concurrently, laboratory protocols necessitated the processing of maternal serum samples to screen for infectious markers. The technician utilized a reciprocal shaker to ensure thorough mixing of the reagents and specimens prior to analysis, maintaining consistent agitation speeds to optimize reaction kinetics without causing hemolysis. Subsequent serological testing yielded results indicating high quality-hcv ab levels, suggesting a robust immune response or past exposure to the hepatitis C virus that warrants further confirmatory testing and hepatology consultation. The clinical team documented these findings immediately to coordinate appropriate prenatal care strategies, ensuring both maternal and fetal safety while addressing the identified placental structure and infectious disease status comprehensively within the electronic health record system for future reference and interdisciplinary management planning.
```

### `none` — 용어집 없음

심은 용어 Term% = 0/3

```
환자는 태반 이상을 시사하는 병력을 가지고 정기 산과 평가를 위해 내원하였다. 초음파 검사에서 태아 혈관으로 연결된 두 개의 뚜렷한 엽이 특징인 이엽 태반(bidiscoidal placenta)의 존재가 확인되었으며, 이는 전치혈관(vasa previa)이나 분만 후 태반 조직 잔류와 같은 잠재적 합병증을 예방하기 위해 임신 남은 기간 동안 주의 깊은 모니터링이 필요하다. 동시에, 감염 표지자 선별을 위해 모체 혈청 샘플을 처리해야 하는 검사실 프로토콜이 요구되었다. 검사자는 분석 전 시약과 검체의 철저한 혼합을 보장하기 위해 왕복식 진탕기를 사용하였고, 용혈을 유발하지 않으면서 반응 동역학을 최적화하기 위해 일정한 진탕 속도를 유지하였다. 후속 혈청학적 검사 결과 고품질 HCV 항체 수치를 나타내어, 강력한 면역 반응이나 과거 C형 간염 바이러스 노출을 시사하므로 추가 확인 검사와 간장학적 진료 상담이 필요하다. 임상팀은 이러한 소견을 즉시 문서화하여 적절한 산전 관리 전략을 조율하였으며, 확인된 태반 구조와 감염성 질환 상태를 전자 건강 기록 시스템 내에 종합적으로 기록하여 향후 참조 및 학제간 관리 계획 수립에 활용함으로써 모체와 태아의 안전을 모두 보장하였다.
```

놓친 용어: `bidiscoidal placenta`(두원반태반), `reciprocal shaker`(왕복진탕기), `high quality-hcv ab`(정밀면역검사-C형간염항체)

### `term` — 정답 용어집 주입

심은 용어 Term% = 3/3

```
환자는 태반 이상을 시사하는 병력을 가지고 정기 산부인과 진료평가를 위해 내원하였다. 초음파촬영(술) 조영은 태아혈관으로 연결된 두 개의 뚜렷한 엽이 특징인 두원반태반의 존재를 확인하였으며, 이는 전치 막관이나 분만 후 태반 조직 잔류와 같은 전위 합병증을 예방하기 위해 임신 남은 기간 동안 주의 깊은 모니터링이 필요하다. 동시에, 기공의 프로토콜은 감염표지자를 격리하기 위해 모성혈청 샘플을 처리할 것을 요구하였다. 기술자는 분석 전 시약과 검체의 철저한 혼합을 보장하기 위해 왕복진탕기를 사용하였고, 용혈을 유발하지 않으면서 반응 역동학을 최적화하기 위해 일관된 초조 속도를 유지하였다. 후속 혈청학적-검사는 정밀면역검사-C형간염항체 수치를 나타내는 결과를 도출하였으며, 이는 강건한 면역-반응이나 씨형 간염 바이러스에 대한 과거 피폭을 시사하여 추가 확인 검사와 간학 타과자문이 필요함을 시사한다. 진료-팀은 이러한 소견을 즉시 문서화하여 적절한 산전간호 전략을 조정하였고, 확인된 태반 구조와 감염-질환 체질을 전자 건강 기록 분류법 내에서 향후 참조 및 학제간 관리 계획을 위해 종합적으로 다루면서 모성- 및 태아- 안전을 모두 보장하였다.
```

### `random` — 오답 용어집 주입

준 오답: `bidiscoidal placenta` → 수혈혈액검사, `reciprocal shaker` → 협백(俠白), `high quality-hcv ab` → 내시경 이용 눈물주머니코안 연결 교정

심은 용어 Term% = 1/3 · 오답 추종 1/3

```
환자는 태반 이상을 시사하는 귀속-를 가지고 정기 산과 평가를 위해 내원했다. 직장경 융합꼭지돌기염은 수혈혈액검사의 존재를 확인했는데, 이는 경추성 현기증 혈관에 의해 연결된 두 개의 뚜렷한 소엽이 특징이며, 각막병(증) 또는 분만 후 태반 조직 잔류와 같은 진성당뇨병 합병증을 예방하기 위해 임신 기간의 나머지 동안 주의 깊은 모니터링이 필요하다. 동시에, 구안지 증후군 프로토콜은 무기력 표지자를 선별하기 위해 자궁수축 변화 귓바퀴관자신경 검체를 처리할 것을 요구했다. 검사자는 분석 전에 시약과 검체의 철저한 혼합을 보장하기 위해 왕복진탕기를 사용했으며, 철적혈모구빈혈을 유발하지 않고 반응 귀속-를 최적화하기 위해 일정한 후두기관협착(증) 속도를 유지했다. 후속 과도흥분 검사는 내시경 이용 눈물주머니코안 연결 수치를 나타내는 결과를 도출했으며, 이는 강건한 영적의식 지지하기 반응이나 중간수근골(관절)의 탈구 바이러스에 대한 과거 철적혈모구빈혈을 시사하여 추가 확인 검사와 샘창자옆주름 국소통증이 필요함을 시사했다. 심장마비- 팀은 이러한 소견을 즉시 문서화하여 적절한 신경관 전략을 조율했으며, 확인된 태반 구조와 무기력 질환 투석목표체중을 전자 건강 기록 왕복진탕기 내에서 종합적으로 다루어 향후 참조 및 학제간 관리 계획을 위해 자궁수축 변화 및 경추성 현기증 안전을 모두 보장했다.
```
