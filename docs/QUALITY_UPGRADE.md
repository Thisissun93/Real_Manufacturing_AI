# 품질 분석 고도화 변경 내역

작업일: 2026-09-26

## 1. 왜 이 작업을 했는가

수정 전 상태를 먼저 측정했다.

### 모델이 불량을 거의 검출하지 못했다

`report/confusion_matrix.csv` 에 저장되어 있던 결과다.

| | 예측 Delamination | 예측 Normal |
| --- | --- | --- |
| **실제 Delamination** | 4 | 132 |
| **실제 Normal** | 12 | 852 |

박리 136건 중 4건만 검출했다. 재현율 2.9%. 품질 관점에서 미검(유출) 97%이며
가장 나쁜 실패다. 그런데 보고된 지표는 accuracy 85.6% 뿐이었고, 이 값은
Normal 기저율 86.4%와 거의 같다. 즉 아무것도 학습하지 않은 것과 구분되지 않았다.

### 원인은 모델이 아니라 데이터였다

14개 공정 인자에 대해 정상군과 박리군의 효과 크기(Cohen's d)를 측정했다.

| 인자 | Cohen's d |
| --- | --- |
| CZ_Concentration | -0.32 |
| Anneal_Temp | 0.15 |
| Anneal_Time | 0.14 |
| 나머지 11개 | 0.09 이하 |

인과 경로는 코드에 있었으나 각 품질 단계에 더해지는 측정 노이즈가
인자 변동보다 커서 신호가 사라졌다. 예를 들어 Cure_Temp 의 Peel_Strength
기여는 계수 -2.0 에 인자 표준편차 약 1.0 이라 폭이 ±2.0 인데,
Peel_Strength 에 더해지는 노이즈는 표준편차 12 였다.

### 설비와 모델이 품질에 아무 영향을 주지 않았다

Machine(PRESS_01/02/03)과 Model(MODEL_A/B/C)이 무작위로 배정되고
품질 특성과 무관했다. 설비 간 비교(ANOVA, Tukey HSD)를 붙여도 찾아낼 차이가
없는 상태였다.

### 수율이 불량 라벨의 결정론적 함수였다

Delamination LOT 의 수율이 전부 정확히 0.00, Normal LOT 은 평균 98.48.
수율 관리도와 공정능력 분석이 아무 정보를 담을 수 없었다.

---

## 2. 데이터 생성기 재설계

`src/data/generate_process_data.py`

### 인과 경로에 신호를 넣었다

```
CZ 농도        -> 표면조도 -> 접착력 -> 박리
Press2 온도/압력 -> 보이드 --------> 박리
Cure 온도/시간   -> 경화도 -> 접착력
Anneal 온도/시간 -> 잔류응력 ------> 박리
```

수정 후 효과 크기다.

| 인자 | 수정 전 | 수정 후 |
| --- | --- | --- |
| Press2_Pressure | -0.04 | **-0.79** |
| Press2_Temp | -0.01 | **-0.62** |
| CZ_Concentration | -0.32 | **-0.47** |
| Anneal_Temp | 0.15 | -0.22 |

Press1, Press3 는 박리에 관여하지 않는 인자로 두었다. 모든 인자가 유의하면
변수 선택 분석이 의미를 잃는다.

### 목표 Cpk 를 1.67 에서 1.33 으로 낮췄다

1.67 은 실제 양산 라인보다 지나치게 안정적이어서 인자 변동이 거의 없었다.
1.33 은 자동차·반도체 업계의 일반적인 관리 수준이다.

### 교호작용을 넣었다

Press2 온도와 압력이 동시에 부족할 때 위험이 각각의 합보다 커진다.
선형 모델로 완전히 잡히지 않고 트리 모델이 이득을 보는 구조이며,
JMP Interaction Analysis 로 확인할 수 있는 형태다.

### 설비별 고유 특성을 넣었다

| 설비 | 심은 구조 | 검출 도구 |
| --- | --- | --- |
| PRESS_02 | Press2 압력 -0.22, 온도 -0.55 오프셋 / 산포 1.45배, 1.25배 | ANOVA + Tukey HSD, Levene |
| PRESS_03 | Cure 온도가 기간에 걸쳐 -3.4°C 선형 하강 | Nelson 규칙 2, 3, 5, 6, 8 |

PRESS_03 의 드리프트는 규격한계(145~155) 안에서 진행되므로 규칙 1(3시그마
이탈)로는 잡히지 않는다. 관리도를 그리는 것과 판정하는 것이 다른 일임을
보여주는 구조다.

결과 불량률: PRESS_01 7.18%, PRESS_02 21.05%, PRESS_03 10.46%

### 모델 민감도를 넣었다

MODEL_C 는 층수가 많아 동일 조건에서 박리에 더 민감하다.
결과: MODEL_A 10.25%, MODEL_B 11.18%, MODEL_C 17.18%

### 수율을 연속화했다

박리 패널 수에 비례해 감소한다(패널당 1.35% 손실, 인접 손실 반영).
0% 에서 바닥이 잡힌다.

### 불량률을 설정값으로 관리한다

`TARGET_LOT_DEFECT_RATE` 에 맞춰 로짓 절편을 이분법으로 자동 보정한다.
계수를 조정할 때마다 불량률이 흔들리는 것을 막는다.

### 시간축을 추가했다

`Timestamp` 컬럼. LOT 간격 20분. 드리프트와 관리도 순서 개념의 기반이다.

### 표본 수를 5,000에서 8,000으로 늘렸다

설비별로 나눠도 부분군당 2,600 LOT 이상 확보된다.

---

## 3. 새 측정시스템 데이터

`src/data/generate_msa_data.py` (신규)

- Gage R&R: 시료 10개 x 작업자 3명 x 반복 3회 = 90회 균형 교차 설계
- 편향·선형성: 기준값이 알려진 표준 시료 12종 x 5회 = 60회

심은 구조: OP_C 계통 편향 -0.115, OP_B 반복성 1.55배,
두꺼운 시료에서 OP_C 편향 확대(부품 x 작업자 교호작용),
계측기 편향 +0.045, 기울기 0.978

---

## 4. 잘못된 코드 수정

### 규격한계와 관리한계를 구분했다

`src/process_spec.py` 가 규격한계를 `lcl`/`ucl` 키에 담고 있었다.
두 개념을 같은 이름으로 부르면 "관리한계를 벗어났다"(공정 변화 신호)와
"규격을 벗어났다"(불량)가 구분되지 않는다. 조치가 다르다.

`lsl`/`usl` 로 바로잡고, 소비 모듈 6개를 함께 수정했다.
`get_spec_limits()`, `get_tolerance()`, `get_target()`, `get_unit()`,
`build_capability_specifications()` 헬퍼를 추가했다.

### 관리한계 산출 방식을 바로잡았다

`src/analysis/spc.py` 가 `mean ± 3 * std(전체)` 로 계산했다.
전체 표준편차는 부분군 간 변동까지 포함하므로, 공정에 평균 이동이나 추세가
있으면 그 변동이 한계를 넓혀 정작 검출해야 할 신호를 감춘다.

이동범위 기반으로 바꿨다.
```
sigma_hat = MR_bar / d2(2) = MR_bar / 1.128
UCL = X_bar + 2.660 * MR_bar
```

### 이미지 저장 경로 버그

`Path(__file__).resolve().parent.parent` 는 `src/` 디렉터리다.
`spc.py`, `trend.py`, `defect.py`, `correlation.py` 4개 파일이
`src/images/` 에 저장하고 있었다. `parents[2]` 로 바로잡았다.

### 파이프라인 안의 plt.show()

헤드리스 환경과 CI 에서 멈춘다. `matplotlib.use("Agg")` 와 함께 제거했다.

### 패키지 초기화 파일 오타

`src/pipeline/__init__py` → `__init__.py` (밑줄 하나 누락)

### 사용하지 않는 모듈 정리

- `src/visualization/` 전체 (4개 파일, 모두 0바이트, 참조 없음) 삭제
- `src/report/report_generator.py` (0바이트, 참조 없음) 삭제
- `src/ml/random_forest.py` 삭제. `train_model.py` 와 중복이며 지표가
  accuracy 뿐이었다. permutation importance 기능은 `train_model.py` 의
  변수 중요도와 L1 로지스틱 비교로 대체된다.

### 불량 예측 평가 기준 교체

`src/ml/train_model.py`

| 항목 | 수정 전 | 수정 후 |
| --- | --- | --- |
| 헤드라인 지표 | accuracy | PR-AUC + 재현율 |
| 베이스라인 | 없음 | DummyClassifier 항상 함께 학습 |
| 판정 임계값 | 0.5 고정 | 목표 검출률에서 결정 |
| 오류 구분 | 없음 | 과검률 / 미검률 분리 |
| 비교군 | 없음 | L1 규제 로지스틱 회귀 |
| 검증 | 단일 분할 | 5겹 계층 교차검증 PR-AUC |
| 운전점 | 없음 | 목표 검출률별 선택표 |

수정 후 결과 (테스트 1,600 LOT, 양성 205건)

| 모델 | PR-AUC | 재현율 | 정밀도 | 과검률 | 미검률 |
| --- | --- | --- | --- | --- | --- |
| RandomForest (임계값 0.098) | 0.4996 | 90.2% | 16.6% | 66.5% | 9.8% |
| LogisticRegression(L1) | 0.4972 | 91.7% | 15.5% | 73.5% | 8.3% |
| RandomForest (임계값 0.5) | 0.4996 | 38.5% | 59.4% | 3.9% | 61.5% |
| Dummy (전부 정상) | 0.1281 | 0.0% | 0.0% | 0.0% | 100.0% |

더미 대비 PR-AUC 3.90배. 5겹 교차검증 0.4758 ± 0.0353.

임계값 0.5 를 쓰면 재현율이 38.5% 로 떨어진다. 임계값을 모델과 함께
`joblib` 패키지에 저장하도록 바꿨고, `batch_predict.py` 가 `model.predict()`
대신 저장된 임계값을 사용하게 수정했다.

L1 로지스틱이 Random Forest 와 거의 동등하다. 신호가 대체로 가법적이라는
증거이며, 트리 모델이 필요한지 판단할 근거가 된다.

### 옛 테스트 교체

`tests/test_data_pipeline.py::test_delamination_yield_is_zero` 는
"박리 LOT 의 수율이 전부 0" 이라는 버그를 요구하고 있었다. 3개 테스트로 교체했다.

- `test_delamination_yield_is_not_a_constant`
- `test_yield_decreases_with_delaminated_panel_count`
- `test_yield_stays_within_physical_bounds`

---

## 5. 신규 품질 분석 모듈

`src/quality/` (신규 패키지, 6개 모듈)

| 모듈 | 내용 |
| --- | --- |
| `constants.py` | 관리도 계수표 d2, d3, c4, A2, D3, D4, B3, B4 |
| `control_charts.py` | I-MR, X-bar-R, p 관리도. 시그마 추정(within/overall) |
| `nelson_rules.py` | Nelson 판정 규칙 8종, 기대 오경보, 신호 판별 |
| `capability.py` | Cp/Cpk/Pp/Ppk, CPU/CPL, ppm 추정, 정규성, 진단 문장 |
| `msa.py` | Gage R&R(ANOVA 법), 편향, 선형성 |
| `anova.py` | 일원분산분석, Levene, Welch ANOVA, Tukey HSD |
| `run_quality_analysis.py` | 통합 실행 |

### Nelson 판정 규칙의 오경보 보정

판정 규칙은 관리상태에서도 오경보를 낸다. 8,000 타점이면 규칙 1 하나로도
우연히 20건 이상 나온다. 건수만 세면 모든 특성이 CRITICAL 로 보고된다.

관측 건수를 관리상태 기대값과 비교해, 기대치의 2배 이상인 규칙만 신호로
분류한다. 기대 확률은 이항분포 공식이 아니라 몬테카를로로 실측했다.

규칙 3, 4 는 연속 차분의 부호를 보는데, i.i.d. 정규 데이터에서도 인접 차분끼리
상관계수 -0.5 의 음의 상관을 가진다. 독립을 가정하면 규칙 4 의 확률이
2/2^12 = 0.000244 로 나오지만 실측값은 0.001655 로 약 7배다.

| 규칙 | 실측 확률 | 8,000점당 기대 |
| --- | --- | --- |
| 1 | 0.002688 | 21.5 |
| 2 | 0.001901 | 15.2 |
| 3 | 0.002387 | 19.1 |
| 4 | 0.001655 | 13.2 |
| 5 | 0.001984 | 15.9 |
| 6 | 0.003432 | 27.5 |
| 7 | 0.001089 | 8.7 |
| 8 | 0.000057 | 0.5 |

검증 조건: 표준정규 4,000점 x 250회 = 1,000,000 타점.
규칙 1 의 실측값 0.002688 이 이론값 P(|z|>3) = 0.0027 과 일치하는 것으로
시뮬레이션 자체를 검증했다.

### 계수형 데이터 분리

수율과 불량률은 이항분포를 따른다. I-MR 관리도에 올리면 정상 LOT 과 불량 LOT 이
두 봉우리를 만들어 모든 불량 LOT 이 규칙 1 위반으로 잡힌다. 이상 신호가 아니라
차트 선택이 틀린 것이다. `p_chart` 를 추가하고 Yield 를 계량형 감시에서 제외했다.

### 실행 결과 — 심은 구조가 검출되는가

설비 층별 관리도, 상위 신호:

| 설비 | 특성 | 규칙 | 관측 | 기대 | 배수 |
| --- | --- | --- | --- | --- | --- |
| PRESS_03 | Cure_Temp | 규칙 8 | 3 | 0.15 | 20.2 |
| PRESS_03 | Cure_Temp | 규칙 2 | 54 | 4.96 | 10.9 |
| PRESS_03 | Cure_Temp | 규칙 5 | 50 | 5.18 | 9.7 |
| PRESS_03 | Cure_Temp | 규칙 6 | 75 | 8.96 | 8.4 |
| PRESS_03 | Cure_Temp | 규칙 1 | 43 | 7.02 | 6.1 |

심어 놓은 드리프트가 규칙 2, 5, 6, 8 로 잡혔다. 규칙 1 의 배수가 가장 낮다.
관리한계를 벗어나지 않으면서 진행되는 이상을 규칙 1 만으로는 놓친다는 것을
데이터가 보여준다.

ANOVA 결과 (Machine 인자, 유의한 특성):

| 특성 | F | eta^2 | 효과 크기 | 등분산 |
| --- | --- | --- | --- | --- |
| Cure_Temp | 1304.58 | 0.2460 | 큼 | 아니오 |
| Press2_Pressure | 507.91 | 0.1127 | 중간 | 아니오 |
| Press2_Temp | 376.98 | 0.0862 | 중간 | 아니오 |
| Peel_Strength | 149.79 | 0.0361 | 작음 | 예 |

Levene 검정이 PRESS_02 의 산포 확대를 잡아내 Welch ANOVA 로 전환했다.

Tukey HSD 가 Press2_Pressure 에서 PRESS_01 vs PRESS_02 (+0.226),
PRESS_02 vs PRESS_03 (-0.221) 을 유의하게 분리했다. 심어 놓은 구조와 일치한다.

Gage R&R 결과:

| 항목 | 값 |
| --- | --- |
| EV (반복성) | 0.0869 |
| AV (재현성) | 0.0771 |
| GRR | 0.1279 |
| PV (부품) | 0.5771 |
| %GRR | 21.6% (조건부 적합) |
| ndc | 6 |
| %P/T | 19.2% |
| 부품 x 작업자 교호작용 | p = 0.0147 (유의, 오차항에 통합하지 않음) |

편향 +0.0280 (p = 0.032, 유의), 기울기 0.9811, 선형성 0.0530, R² 0.9877.

---

## 6. 테스트

신규 5개 파일, 152개 테스트.

| 파일 | 개수 | 검증 방법 |
| --- | --- | --- |
| `test_quality_anova.py` | 22 | `scipy.stats.f_oneway`, `tukey_hsd`, `levene` 와 대조 |
| `test_quality_control_charts.py` | 30 | 계수표 값, 손 계산 예제, 추세 데이터에서 within/overall 분리 |
| `test_quality_capability.py` | 22 | 표본 평균·표준편차를 정확히 맞춘 데이터로 공식 대조 |
| `test_quality_msa.py` | 30 | 제곱합 분해 항등식, 자유도 합, 분산 성분 회수 |
| `test_quality_nelson.py` | 48 | 규칙별 발동/미발동 데이터, 몬테카를로 오경보율 |

Tukey HSD 는 p값, 평균차, 신뢰구간 모두 `scipy.stats.tukey_hsd` 와
일치하는지 확인한다. 직접 구현을 독립 구현과 대조하는 방식이다.

전체 실행 결과: 200 passed.

---

## 7. 파이프라인 변경

```
 1. Generate Process Data
 2. Generate MSA Data            (신규)
 3. Update SQLite Database
 4. Validate Process Data
 5. Generate Trend Analysis
 6. Generate SPC Analysis
 7. Run Quality Analysis Suite   (신규)
 8. Generate Correlation Analysis
 9. Generate Defect Analysis
10. Detect Spec Outliers
11. Train and Save Model
12. Run SHAP Analysis
13. Run Batch Prediction
14. Generate PDF Report
```

`Run Random Forest Analysis` 단계는 중복이므로 제거했다.

## 8. 새 리포트 산출물

| 파일 | 내용 |
| --- | --- |
| `report/process_capability.csv` | 특성별 Cp/Cpk/Pp/Ppk, 진단 |
| `report/nelson_rule_violations.csv` | 규칙 위반 목록 (시작·종료 LOT 포함) |
| `report/quality_capability.csv` | 공정능력 요약 |
| `report/quality_stratified_rule_signals.csv` | 설비 층별 신호 |
| `report/quality_anova.csv` | ANOVA 결과 |
| `report/quality_tukey_hsd.csv` | Tukey HSD 쌍별 비교 |
| `report/quality_machine_summary.csv` | 설비별 불량률과 인자 평균 |
| `report/quality_defect_rate_p_chart.csv` | p 관리도 요약 |
| `report/quality_msa_variance_components.csv` | Gage R&R 분산 성분 |
| `report/model_comparison.csv` | 모델 비교 |
| `report/model_operating_points.csv` | 목표 검출률별 운전점 |

## 9. 설정 파일 변경

`config.yaml` 에 두 섹션을 추가했다.

```yaml
quality:
  target_recall: 0.90
  nelson_rules: [1, 2, 3, 4, 5, 6, 7, 8]
  subgroup_size: 5

msa:
  part_count: 10
  operator_count: 3
  replicate_count: 3
  characteristic: Total_Thickness
```

`data.sample_size` 를 5000 에서 8000 으로 변경했다.

## 10. 확인이 필요한 변경

규격값 일부를 조정했다. 원래 값으로 되돌리려면 `src/process_spec.py` 를 수정한다.

| 특성 | 항목 | 이전 | 변경 | 이유 |
| --- | --- | --- | --- | --- |
| CZ_Roughness | 단위 | um | nm | 350 um 표면조도는 물리적으로 맞지 않음 |
| ABF_Roughness | 단위 | um | nm | 동일 |
| Peel_Strength | 단위 | kgf/10mm | gf/cm | 값 범위(500)에 맞는 단위 |
| Peel_Strength | LSL | 350 | 400 | 재설계된 분포에서 Cpk 1.46 이 되도록 |
| Yield | LSL | 85 | 95 | 수율 연속화 후 의미 있는 Cpk 가 되도록 |

## 11. 이 환경에서 검증하지 못한 항목

`shap`, `streamlit`, `altair` 는 이 작업 환경에 설치할 수 없어
해당 단계(SHAP 분석, 대시보드, UI 테스트)는 실행 검증하지 못했다.
`requirements.txt` 에 이미 포함되어 있으므로 로컬에서는 동작한다.
대시보드(`src/dashboard/app.py`)는 `PROCESS_SPEC` 키 변경에 맞춰
`lsl`/`usl` 참조로 수정했으나 화면 확인은 하지 못했다.
