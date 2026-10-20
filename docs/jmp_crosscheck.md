# JMP 교차검증 — `src/quality` 결과를 JMP 19 와 대조

`src/quality` 는 현업에서 JMP 로 하던 통계 분석을 코드로 옮긴 모듈입니다.
코드가 맞는지 확인하는 가장 직접적인 방법은 **같은 데이터를 JMP 표준 플랫폼에 넣어 같은 숫자가 나오는지** 보는 것입니다.
scipy 대조(`tests/test_quality_*.py`)에 더해 JMP 를 기준값으로 삼았습니다.

## 결과 요약

같은 합성 CSV 3개로 비교한 결과, **164개 항목이 모두 일치**했습니다.
29개 항목에서 상대 차이가 1e-6 을 넘었고(최대 0.034%), 원인을 하나로 특정했습니다(아래 확인 사항 1).

| 영역 | JMP 플랫폼 | 항목 수 | 최대 상대 차이 | 판정 |
|---|---|---:|---:|---|
| 설비 간 분산분석 | Oneway (Means/Anova, UnEqual Variances) | 30 | 1.7e-11 | 일치 |
| Tukey-Kramer 다중비교 | Oneway › All Pairs, Ordered Differences | 54 | 4.1e-07 | 일치 |
| 공정능력 Cp/Cpk/Pp/Ppk | Process Capability (평균 이동범위) | 26 | 3.4e-04 | 일치 (Cp·Cpk·Within σ 11개는 d2 반올림 차이) |
| Gage R&R | Variability Chart › Gauge R&R (Crossed) | 14 | 1.0e-11 | 일치 |
| 편향·선형성 | Fit Model(절편 t검정), Bivariate | 4 | 7.8e-14 | 일치 |
| 설비별 I-MR 관리한계 | Control Chart Builder | 36 | 4.2e-05 | 일치 (UCL·LCL 18개는 d2 반올림 차이) |

대표 항목:

| 항목 | Python | JMP | 상대 차이 |
|---|---:|---:|---:|
| Press2_Pressure 설비 간 F | 507.909 | 507.909 | 2.5e-14 |
| Press2_Pressure Welch p | 5.06e-163 | 5.06e-163 | 0 |
| Cure_Temp PRESS_01−PRESS_03 차이 | 1.64437 | 1.64437 | 1.6e-14 |
| Total_Thickness Ppk | 2.51715 | 2.51715 | 1.5e-14 |
| Total_Thickness Cpk | 2.51211 | 2.51296 | 3.4e-04 |
| Gage R&R %StudyVar | 21.6374 | 21.6374 | 3.0e-13 |
| ndc | 6 | 6 | 0 |
| 편향 t검정 p | 0.031962 | 0.031962 | 3.0e-15 |
| 측정값~기준값 기울기 | 0.981084 | 0.981084 | 2.5e-15 |
| PRESS_03 Cure_Temp UCL | 152.065 | 152.063 | 8.3e-06 |

전체 표: [`tools/jmp_crosscheck/results/crosscheck_table.csv`](../tools/jmp_crosscheck/results/crosscheck_table.csv)

## 대조하면서 확인한 것

### 1. d2 상수 반올림 — Within σ 가 0.034% 다름

Cp, Cpk, Within σ 와 I-MR 관리한계만 미세하게 달랐습니다. 차이 비율이 모든 특성에서 같았습니다(3.36e-4).
특성마다 같은 비율로 어긋나면 데이터가 아니라 상수가 원인입니다.

- Python: `constants.py` 의 관리도 계수표 값 `d2(2) = 1.128`
- JMP: 이론값 `d2(2) = 2/√π = 1.128379`
- 확인: `8.206757 × 1.128 / 1.128379 = 8.20400` → JMP Within σ `8.204000` 과 일치

관리한계도 같은 이유로 차이가 납니다(`2.660 × MR̄` 대 `3/d2 × MR̄ = 2.6587 × MR̄`).
판정에 영향은 없습니다. Cpk 1.33 같은 기준선 근처에서 소수 셋째 자리가 바뀔 수 있는 정도입니다.
표 값을 쓰는 방식(현장 양식, AIAG 표)과 JMP 중 어느 쪽에 맞출지는 정하기 나름이며, 지금은 표 값을 유지했습니다.

### 2. 등분산 검정 이름 — 코드의 "Levene" 은 JMP 의 Brown-Forsythe

`anova.py` 는 `scipy.stats.levene(center="median")` 을 씁니다. 편차를 중앙값 기준으로 잡는 방식이고, JMP 는 이를 **Brown-Forsythe** 로 표시합니다.
JMP 의 **Levene** 은 평균 기준입니다. p 값은 Brown-Forsythe 쪽과 소수점 이하까지 일치했습니다
(Peel_Strength: Brown-Forsythe 0.33145 = Python, JMP Levene 0.33118).
계산은 맞습니다. 다만 JMP 사용자가 보고서를 읽을 때 헷갈리지 않도록 표시 이름을 Brown-Forsythe 로 바꾸는 편이 정확합니다.

### 3. Gage R&R 재현성(AV)의 범위 — 정의 차이

| 구분 | Python `msa.py` | JMP Gauge R&R |
|---|---|---|
| 재현성(AV) | 작업자 성분만 (13.05%) | 작업자 + 작업자×부품 (15.88%) |
| 교호작용 | 따로 표시 (9.06%) | AV 아래 하위 행으로 표시 |
| %GRR | 21.64% | 21.64% |

분산 성분 하나하나와 %GRR 은 같습니다. 다른 것은 "재현성"이라는 이름에 교호작용을 포함하느냐입니다.
어느 쪽이 틀린 것이 아니라 묶는 방식의 차이입니다. 다만 같은 데이터를 두고 "재현성 13%"와 "재현성 16%"가 함께 돌아다니면
현장에서는 다른 결과로 받아들이기 쉬우므로, 보고서에는 교호작용 포함 여부를 함께 적어야 합니다.

## 재현 방법

```
# 1) Python 기준값
python -m tools.jmp_crosscheck.python_reference

# 2) JMP: crosscheck.jsl 과 Data/*.csv 3개를 한 폴더에 두고 JMP 에서 실행(Ctrl+R)
#    Gauge R&R 단계에서 MSA 공차 확인 창이 뜨면 OK (30~34 가 미리 들어가 있음)
#    결과 jmp_dump.csv 를 tools/jmp_crosscheck/results/ 로 복사

# 3) 비교
python -m tools.jmp_crosscheck.compare
```

`crosscheck.jsl` 은 플랫폼별 리포트 구조를 하드코딩하지 않습니다. 리포트 안의 숫자 열(NumberColBox)을 모두
`(outline 경로, 열 제목, 행 이름, 값)` 으로 펼쳐 저장하고, 매칭은 `compare.py` 에서 합니다.
JMP 버전이 바뀌어 리포트 배치가 달라져도 추출 단계는 그대로 동작합니다.

- 확인 환경: JMP 19 (Windows), Python 3.12
- 데이터: `Data/` 의 합성 데이터(실제 양산 데이터 아님)
- Nelson 판정 규칙 위반 건수는 이번 대조에 포함하지 않았습니다. 관리한계가 일치하므로 규칙 판정 입력은 같지만,
  규칙 3·4 의 판정 시점 정의는 별도로 확인해야 합니다.
