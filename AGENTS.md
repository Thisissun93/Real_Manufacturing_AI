# AGENTS.md

ABF 적층(FC-BGA 기판) 제조 이력 조사·통계·예방보전 검토를 시연하는 Streamlit 앱입니다. 데이터는 모두 합성 데이터이며 실제 제조사·장비 형식·사내 정보를 포함하지 않습니다.

## 구조

- `src/investigation/`: LOT 조사(`core.investigate`), 합성 시나리오(`demo`, `scenarios`), 종합·예방보전(`predictive`), 보고서, 시료 이력
- `src/quality/`: 공정능력, I-MR·p 관리도, Nelson 규칙, ANOVA·Tukey, Gage R&R, 8D
- `src/ml/`: 불량 예측 모델과 운전점
- `tools/jmp_crosscheck/`: JMP 19 결과와의 대조
- `src/dashboard/app.py`: 앱 진입점

## 확인 명령

```bash
python -m pytest -q
python -m src.investigation.evaluate_scenarios   # 시나리오 수용 검증 27건
python -m src.investigation.benchmark            # 업무 시나리오 측정 (약 1.5분)
```

## Review guidelines

- 조사 결과는 원인 후보와 확인 순서만 제시합니다. 원인 확정, 원인 확률, 인과 기여율, 부품 잔여 수명을 말하는 문구나 계산은 지적하세요.
- 조사 규칙이 시나리오 정답(`CASES`, 사례 이름)을 읽으면 안 됩니다.
- `as_of` 이후에 확정된 기록이 조사·학습에 들어가면 안 됩니다(시간 누출). 결측 대체값은 학습 구간에서만 계산합니다.
- 결측을 정상으로 대체하지 않습니다. 단위가 다른 인자를 절대값으로 비교하지 않습니다.
- 관리한계(부분군 내 변동)와 규격한계를 섞지 않습니다. Cp/Cpk는 군내 σ, Pp/Ppk는 전체 σ입니다.
- '검증 완료' 기록에는 담당자·실제 결과·증거·확인시험이 필요합니다. 이 검사를 약하게 만드는 변경은 지적하세요.
- 8D 문서는 실행하지 않은 조치를 완료로, 확인하지 않은 원인을 확인됨으로 표시하면 안 됩니다.
- 사용자 입력 API 키는 세션에만 두고 로그·파일·보고서에 남기지 않습니다.
- 계산 로직을 바꾸면 테스트와 검증 문서(`docs/`)를 함께 갱신해야 합니다.

- README 맨 위의 영어 요약(English summary)에 있는 수치는 한국어 본문·docs와 같아야 합니다. 수치를 바꾸는 PR에서 영어 요약이 갱신되지 않았으면 지적하세요.
