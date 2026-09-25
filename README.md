# Real Manufacturing Intelligence — Ver1.0

[![앱 바로 실행](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://realmanufacturingai-gqmhke2ybcjhdrsndjsh2e.streamlit.app/)

제작자: 김태양. ABF 제조 이력 조사·통계·예방보전 검토를 연결하는 공개용 합성 데이터 시연 프로그램입니다. 실제 제조사·장비 형식과 사내 양산 정보를 포함하지 않습니다.

> 현재 로컬 검토판입니다. GitHub 업데이트 및 온라인 재배포는 보류 중입니다. 아래 실행 버튼은 기존 공개판으로 연결됩니다.

## 시작하기

위 **앱 바로 실행** 버튼을 누릅니다. 기존 배포 주소이므로 이 업데이트를 반영한 뒤 새 기능을 확인할 수 있습니다.

1. 왼쪽 **LOT ID 직접 검색**에서 `DEMO-0046`을 검색합니다.
2. 약액·공정 이력에서 기준 이탈과 Pre-bake·Cure·고온 Baking 온도 음영을 확인합니다.
3. AOI에서 Quad A–D와 유닛을 선택해 불량 위치를 확인합니다.
4. **6 · 종합·예방보전 → 종합·예방보전 분석 실행**을 누릅니다.
5. 설비별 불량 집계, 기준 이탈 관계, 시간순 검증·SHAP, 다음 3 LOT 추세를 확인합니다.
6. 조사 PDF 메뉴에서 현재 조사 결과와 실행한 종합 분석을 함께 내려받습니다.

앱은 처음 실행할 때 120 LOT의 합성 데이터를 생성합니다. 큰 JSON 파일을 별도로 업로드할 필요가 없습니다.

## 주요 기능

- LOT ID 검색과 동일 모델·개정·층·면·검사 회차 비교
- 약액 보충·전체 교체, 모델 지정 자재와 개체별 6 LOT/3회 해동 추적
- 1초 간격 제품 온도 프로파일, Zone별 저온·고온 노출 강조
- Quad 유닛 PASS/FAIL 지도, 대표 불량 위치, 단면 확인 기록
- PANEL 시료 불출 요청 → 검사자 불출 → 엔지니어 수령 → 반납 이력
- 원인 후보별 점검 부품·확인시험·효과 확인과 편집 가능한 HTML/PDF 보고서
- 설비별 ABF 대표 불량 집계 및 이탈군/기준 내 군의 관찰 비교
- Random Forest 회귀의 시간순 검증, 검증 LOT의 SHAP 기여도
- 최근 8 LOT 추세를 이용한 다음 3 LOT 기준 접근 시나리오와 예방보전 점검 우선순위

- 개선 사례 SQLite 저장·전후 효과 그래프·HTML 보고서
- 등록 기술자료와 검토 완료 사례의 출처 기반 발췌 검색
- 선택 근거 기반 OpenAI 검토 초안·전송 미리보기·세션 API 키
- 도면 부품 좌표 Mapping·동일 형식 설비 사례 연결·측정 JSON 재생

## 분석을 읽는 기준

목표는 LOT의 **ABF 대표 불량 비율**입니다. 전체 스캔 후 최초 대표 코드만 저장하는 조건이므로 다른 코드 유닛의 ABF 동반 여부는 알 수 없습니다. 같은 LOT이 여러 공정 설비를 거치므로 공정 간 불량 PCS를 합산하지 않습니다.

SHAP는 모델 예측을 설명합니다. 실제 원인 확률·인과 기여율·부품 고장 확률·잔여 수명을 뜻하지 않습니다. 초기 40% LOT 이후를 3개 시간 구간으로 나눠 검증하며 각 구간 시작 이후에 확인된 검사 결과를 해당 학습에서 제외합니다. 결측 대체값은 학습 구간에서만 계산합니다.

모델 MAE가 단순 평균 기준보다 10% 이상 개선되고 검증 불량/정상 LOT이 각각 3건 이상일 때만 우선순위의 보조 근거로 채택합니다. 이는 시연용 내부 채택 기준이며 외부 현장 검증을 대신하지 않습니다.

점검 우선순위: P1 현재 기준 이탈 → P2 추세 접근 → P3 기준 이탈과 ABF 대표 불량 반복 이력. 추세는 기준 경계 지수=1, 최근 8 LOT, R²≥0.6, 최대 3 LOT 연장 조건의 시나리오입니다. 점검·교체 주기는 제조사 근거가 없으면 수명으로 만들지 않습니다.

## 로컬 실행

Python 3.12에서 확인했습니다. 프로젝트 루트에서 실행합니다.

```bash
python -m pip install -r requirements.txt
python -m streamlit run src/dashboard/app.py
```

## 검증

```bash
python -m pytest -q
python -m src.investigation.evaluate_scenarios
```

합성 데이터 검증 결과는 `docs/predictive_validation.json`에 수록했습니다. 모델의 실공정 정확도나 인과성을 주장하지 않습니다. 기존 통계·ML 학습용 화면은 별도 모드로 보존했습니다.

## 저장·공개 범위

- 엔지니어 검토 기록은 브라우저 세션에 보관됩니다. 종료 전 JSON 백업을 받으세요.
- 시료 이력의 로컬 SQLite DB는 `instance/`에 저장되며 Git에 포함하지 않습니다.
- 공개 데모에서는 가상 이름·가상 시료만 사용하세요. 처리자 이름 입력은 로그인 인증이 아닙니다.
- 임시 디스크 기반 호스팅에서는 시료 DB가 재배포 후 보존되지 않을 수 있습니다. 실제 공동 운영에는 인증과 영구 DB가 필요합니다.
- 실제 제조사/형식, 사내 문서, 개인 이름이 포함된 운영 자료를 공개 저장소에 업로드하지 않습니다.

## 구현 범위

Library는 누적 사례를 검색·재사용합니다. 외부 AI는 OpenAI API 키·모델 설정 후 선택 근거를 확인하고 요청할 때만 호출합니다. 외부 논문 자동 수집, 자동 재학습, PLC 실시간 연결·제어는 아직 연결하지 않았습니다. 설비 비교는 관찰 자료이며 자동 배정 기능이 아닙니다.

## 문서

- [개선·지식·설비 Library 사용법](docs/LEARNING_LIBRARY.md)
- [업데이트·배포 절차](docs/DEPLOY_ONE_TAKE.md)
- [종합 분석 설계·해석 범위](docs/PREDICTIVE_AND_PRIVACY.md)
- [LOT 검색·온도·부품 점검](docs/PREDEPLOY_SEARCH_THERMAL_MAINTENANCE.md)
- [자재·PDF·시료 관리](docs/MATERIAL_REPORT_CUSTODY.md)

## 참고

[SHAP 인과 해석 주의](https://shap.readthedocs.io/en/latest/example_notebooks/overviews/Be%20careful%20when%20interpreting%20predictive%20models%20in%20search%20of%20causal%20insights.html), [시간순 교차검증](https://sklearn.org/stable/modules/cross_validation.html).
한글 PDF 글꼴은 NanumGothic을 사용하며 라이선스는 `assets/fonts/OFL.txt`에 포함했습니다. 프로젝트 전체의 공개 라이선스 부여 여부는 별도로 결정해야 합니다.
