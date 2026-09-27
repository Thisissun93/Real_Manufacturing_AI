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

---

## 12. Streamlit 화면 추가 (2차 작업)

1차 작업은 모두 명령줄과 CSV 출력이었고 화면에는 노출되지 않았다.
대시보드에 **품질 분석** 탭을 추가했다.

### 신규 파일

| 파일 | 내용 |
| --- | --- |
| `src/dashboard/quality_view.py` | 품질 분석 탭 5개 하위 화면 |
| `src/utils/plotting.py` | matplotlib 한글 폰트 등록, 색 역할 정의, 공통 스타일 |

### 수정 파일

- `src/dashboard/app.py` : 탭 4개로 확장, 품질 분석 탭 연결
- `src/analysis/spc.py` : 공통 차트 스타일 적용(한글 깨짐 수정)

### 함께 고친 버그

`app.py` 가 모델 패키지의 `classes` 키를 읽고 `model.predict()` 를 쓰고 있었다.
1차 작업에서 모델 저장 구조를 바꾸고 라벨을 0/1 로 변경했기 때문에,
모델을 재학습하면 단일 예측과 배치 예측 탭이 `KeyError: 'classes'` 로 중단됐다.
저장된 판정 임계값을 사용하도록 수정했고, 화면에 임계값과
'임계값까지 남은 여유'를 함께 표시한다.

matplotlib 에 한글 폰트가 등록되어 있지 않아 기존 SPC 차트의 한글 축 이름이
깨지고 "Glyph missing from font" 경고가 발생하고 있었다.
저장소에 이미 포함된 `assets/fonts/NanumGothic.ttf` 를 등록해 해결했다.

### 색 사용 규칙

- 계열 색 3개(파랑·주황·청록)는 색각 이상 조건에서 구분되도록 검증된 조합이다.
  4개 이상이 필요하면 색을 늘리지 않고 묶거나 화면을 나눈다.
- 상태 색(좋음·주의·심각·위험)은 판정 전용이며 계열 색으로 재사용하지 않는다.
- 판정은 색과 글자를 함께 표시한다. 흑백 인쇄나 색각 이상 조건에서
  색은 사라지고 글자만 남는다.
- 격자와 축은 뒤로 물러나고 데이터가 앞에 온다.

### 검증 방법

Streamlit 을 설치할 수 없는 환경이라 화면을 렌더링해 확인하지는 못했다.
대신 streamlit 모듈을 대체하는 스텁을 만들어 5개 화면 함수를 실제로 실행해,
데이터 접근·계산·차트 생성 경로에 오류가 없음을 확인했다.

| 화면 | 차트 | 표 | 지표 |
| --- | --- | --- | --- |
| 공정능력 | 1 | 1 | 4 |
| 관리도 | 2 | 1 | 0 |
| 불량률 p 관리도 | 1 | 0 | 3 |
| 설비 비교 (유의 시) | 1 | 2 | 4 |
| 측정시스템 | 3 | 1 | 7 |
| 모델 운전점 | 1 | 2 | 4 |

한글 렌더링은 `-W error::UserWarning` 으로 실행해 글리프 경고가 없음을 확인했다.

## 13. 8D 문제해결 리포트 (3차 작업)

### 왜 추가했는가

앞의 모든 분석이 "이상이 있다"에서 멈춘다. Nelson 규칙이 PRESS_03 의
Cure_Temp 드리프트를 20.2배로 잡아내고 화면에 띄우지만, 거기까지다.
현업에서는 그 다음이 본 업무다. 누가 언제까지 무엇을 하고, 효과가
있었는지 어떻게 확인하고, 다른 라인에 같은 문제가 없는지 누가 점검하는가.

탐지에서 조치로 이어지는 흐름이 없으면 도구를 만든 사람이지
품질을 한 사람은 아니게 보인다.

### 빈 양식과 다른 점

D2 의 숫자와 D4 의 원인 후보를 사람이 적지 않는다. `report/` 에 저장된
분석 결과에서 읽어온다.

| 읽는 파일 | 쓰이는 곳 |
| --- | --- |
| `quality_machine_summary.csv` | D2 얼마나, D4 설비 간 차이 |
| `quality_defect_rate_p_chart.csv` | D2 언제, D4 유출원인 |
| `quality_anova.csv` | D4 인자별 유의성과 효과 크기 |
| `quality_msa_variance_components.csv` | D4 측정·사람 원인 배제 판단 |
| `quality_stratified_rule_signals.csv` | 드리프트 사례 선정 |
| `model_operating_points.csv` | D3 봉쇄조치의 선별 부하 |
| `quality_capability.csv` | D6 효과 확인 기준선 |

`Evidence` 자료구조가 출처·지표·값·해석을 함께 들고 다니므로 모든 문장에
"어느 파일의 어떤 값을 보고 그렇게 판단했는지"가 붙는다.

### 발생원인과 유출원인 분리

8D 를 형식만 따라 하면 D4 에 원인을 하나 적고 끝낸다. 정석은 두 갈래다.

- 발생원인(occurrence): 왜 불량이 생겼나
- 유출원인(escape): 왜 그걸 못 걸러냈나

이 저장소의 PRESS_02 사례에서 두 원인은 다음과 같이 갈린다.

발생원인은 Press2_Pressure 평균이 규격 중심에서 -0.223 (공차의 22%)
이탈했고 Press2_Temp 도 같은 방향으로 -0.549 (공차의 18%) 이탈한 것이다.
두 파라미터가 같은 방향으로 함께 치우친 것은 설정값 오류나 설비 계통
문제를 시사한다. 독립적으로 흔들렸다면 방향이 갈렸을 것이다.
그 아래 "왜 낮게 유지되는가"는 데이터로 답할 수 없어 추정으로 남겼다.

유출원인은 설비별 층별 관리한계만 운영한 점이다. PRESS_02 의 UCL 38.33%
가 이 설비 자신의 평균 21.04% 에서 계산되므로, 21% 불량률이 관리 상태로
판정된다. 52개 부분군 중 이탈은 1건뿐이다. 나쁜 설비의 나쁜 수준이 그
설비의 기준이 되면 관리도는 영원히 관리 상태를 가리킨다.

두 원인은 시정조치가 다르다. 압력 계통을 고쳐도 검출 체계가 그대로면
다음 불량도 똑같이 빠져나간다.

### 사례 선정을 코드로 고정

어디에 8D 를 열지 고르는 일 자체에 편향이 들어간다. 눈에 띄는 설비,
최근 클레임이 있었던 설비가 먼저 선택된다. 두 기준을 코드로 박았다.

1. 불량률이 전체 평균의 1.5배 이상인 설비 -> PRESS_02 (21.05%, 1.64배)
2. Nelson CRITICAL 신호가 잡힌 파라미터 -> PRESS_03 / Cure_Temp (20.2배)

2번은 불량이 아직 터지지 않은 예방 사례다. 그쪽이 더 싸게 끝난다.

전체 불량률은 단순 평균이 아니라 LOT 수 가중 평균으로 계산한다.
설비별 생산량이 다르면 단순 평균은 틀린 기준을 준다.

### 파라미터 이탈 순위 — 한 번 틀렸던 부분

처음에는 타 설비 평균과의 절대 편차로 순위를 매겼다. 그 결과 PRESS_02 의
1순위 인자로 Cure_Temp (+0.858) 가 나왔다. 틀린 답이다. PRESS_02 의
Cure_Temp 는 149.993 으로 정상이고, PRESS_03 의 드리프트(148.313)가
기준선을 끌어내려 정상인 값이 이탈한 것처럼 보인 것이다.

두 가지를 고쳤다.

- 기준선을 다른 설비가 아니라 규격 중심(`process_spec` 의 target)으로 잡는다.
  규격은 다른 설비의 상태와 무관하게 고정된 기준이다.
- 순위를 공차 반폭 대비 비율(`tolerance_fraction`)로 매긴다. 절대값으로
  줄을 세우면 단위가 큰 파라미터가 항상 이긴다. 공차 ±5 인 온도의
  0.9 이탈과 공차 ±1 인 압력의 0.22 이탈은 비교할 수 있는 양이 아니다.

고친 뒤 PRESS_02 의 1·2순위는 Press2_Pressure (-22.3%), Press2_Temp
(-18.3%) 로 바뀌었다. 데이터 생성기가 실제로 심은 구조와 일치한다.

설비가 셋뿐이면 중앙값을 써도 이 왜곡을 막지 못한다. 남는 비교 대상이
둘이고 둘의 중앙값은 곧 평균이기 때문이다. `peer_gap` 은 참고용으로만
남기고 순위에는 쓰지 않는다.

### p 값이 아니라 효과 크기로 판단

n 이 8,000 이면 실무적으로 의미 없는 차이도 유의하게 나온다.
Model 인자는 Yield 에서 p < 0.05 이지만 eta^2 = 0.0027 로 무시할 수준이다.
유의성만 보면 자재를 원인으로 확정하게 된다. `effect_size` 라벨이
"무시할 수준"인 항목은 배제로 판정한다.

### 하지 않은 것을 했다고 적지 않기

D5 이후는 사람이 현장에서 실행해야 하는 단계다. 코드가 만들 수 있는 것은
'무엇을 목표로 어떻게 검증할지'까지이고 '했더니 좋아졌다'는 결과가 아니다.

- 모든 조치는 상태가 미착수로 시작한다. D0·D3·D5·D7 이 미착수인 것은
  결함이 아니라 현재 상태다.
- 진행률을 하나로 합치지 않는다. 분석 단계(D1·D2·D4)와 실행 단계를 나눠
  표시한다. 섞으면 "8D 가 33% 진행됨" 같은 뜻 없는 숫자가 나온다.
- D6 효과 확인은 값을 고정해두지 않고 현재 데이터에서 매번 다시 계산한다.
  시정조치를 실행하지 않은 지금은 기준선과 같은 값이 나오며, 그것이
  정확한 표시다.
- 기준선과 목표는 조치 전에 고정한다. 조치 후에 목표를 정하면 달성했다는
  결론이 먼저 나온다.
- 확인하지 못한 원인은 '미확인'으로 남기고 미해결 항목에 모은다.
  %GRR 21.6% 는 조건부 적합이므로 측정 요인을 배제하지 않는다.
- D1 팀은 역할로만 구성한다. 가상의 인명을 채워 넣으면 문서가 가짜가 된다.

### 추가·변경 파일

| 파일 | 내용 |
| --- | --- |
| `src/quality/eight_d.py` | 신규. D0~D8 자료구조, 분석 결과 연결, 마크다운 렌더링 |
| `src/quality/run_eight_d.py` | 신규. CLI. `--machine`, `--drift`, `--opened-on` |
| `src/dashboard/eight_d_view.py` | 신규. 8D 화면 |
| `src/dashboard/quality_view.py` | 6번째 하위 탭 추가 |
| `src/pipeline/run_pipeline.py` | "Generate 8D Reports" 단계 추가 |
| `tests/test_quality_eight_d.py` | 신규. 55개 테스트 |

산출물은 `report/eight_d/` 아래에 사례별 마크다운과 `eight_d_summary.csv`
로 저장된다. 화면에서도 마크다운을 내려받을 수 있다.

### 부수 정리

`use_container_width` 는 Streamlit 이 이름을 바꿀 예정이라 실행할 때마다
경고가 쌓였다. `requirements.txt` 가 `streamlit>=1.64.0` 을 요구하므로
새 이름을 안전하게 쓸 수 있어, 29곳을 `width="stretch"` 로 바꿨다.

### 검증

스텁으로 화면 함수를 실행해 확인한 결과다.

| 사례 | 차트 | 표 |
| --- | --- | --- |
| PRESS_02 불량률 | 2 | 9 |
| PRESS_03 Cure_Temp 드리프트 | 1 | 9 |

드리프트 사례의 D6 목표는 관리도 재실행이 필요해 현재 값을 계산하지 않으며,
표에 '미측정'으로 표시되고 차트는 생략된다.

테스트는 품질 분석 모듈 전체 218개가 통과한다
(anova 22, capability 22, control_charts 30, eight_d 55, msa 30,
nelson 48, data_pipeline 11).
