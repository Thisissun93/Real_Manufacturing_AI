"""8D 리포트 테스트.

검증 방향
--------
8D 는 통계 계산이 아니라 문서 생성이므로, 숫자가 맞는지보다
'거짓을 말하지 않는지'를 확인하는 테스트가 중요하다.

    - 실행하지 않은 조치가 완료로 표시되지 않는가
    - 확인하지 않은 원인이 확인됨으로 표시되지 않는가
    - 분석 결과에 없는 숫자를 지어내지 않는가
    - 단위가 다른 파라미터를 절대값으로 비교하지 않는가

마지막 항목은 실제로 한 번 틀렸던 부분이다. 절대 편차로 순위를
매기면 공차 ±5 인 온도의 0.9 이탈이 공차 ±1 인 압력의 0.22 이탈보다
커 보인다. 공정에 위험한 쪽은 후자다.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.quality import eight_d
from src.quality.eight_d import (
    ACTION_DONE,
    ACTION_PENDING,
    DISCIPLINE_TITLES,
    STATUS_CONFIRMED,
    STATUS_EXCLUDED,
    STATUS_UNVERIFIED,
    Action,
    EightDReport,
    Evidence,
    VerificationTarget,
    WhyStep,
    build_defect_rate_case,
    build_drift_case,
    build_recommended_cases,
    build_verification_table,
    missing_reports,
    rank_defect_cases,
    rank_drift_cases,
    render_markdown,
    verify_defect_rate,
)


# =====================================================================
# 테스트용 분석 결과
# =====================================================================


MACHINE_SUMMARY = pd.DataFrame(
    {
        "Machine": ["PRESS_01", "PRESS_02", "PRESS_03"],
        "lot_count": [2743, 2646, 2611],
        "defect_rate_percent": [7.18, 21.05, 10.46],
        "CZ_Concentration_mean": [10.000, 9.999, 9.998],
        "Press2_Pressure_mean": [10.003, 9.777, 9.998],
        "Press2_Temp_mean": [99.988, 99.451, 99.974],
        "Cure_Temp_mean": [149.958, 149.993, 148.313],
        "Anneal_Temp_mean": [199.994, 199.994, 200.016],
    }
)

P_CHART = pd.DataFrame(
    {
        "scope": ["전체", "PRESS_01", "PRESS_02", "PRESS_03"],
        "subgroup_count": [160, 54, 52, 52],
        "p_bar_percent": [12.84, 7.19, 21.04, 10.38],
        "ucl_percent": [27.03, 18.14, 38.33, 23.33],
        "lcl_percent": [0.0, 0.0, 3.75, 0.0],
        "out_of_control_points": [0, 0, 1, 0],
        "out_of_control_percent": [0.0, 0.0, 1.9, 0.0],
    }
)

ANOVA = pd.DataFrame(
    {
        "factor_name": ["Machine", "Machine", "Model", "Model"],
        "response": [
            "Press2_Pressure",
            "Press2_Temp",
            "Yield",
            "Peel_Strength",
        ],
        "eta_squared": [0.112708, 0.086157, 0.002728, 0.000316],
        "effect_size": ["중간", "중간", "무시할 수준", "무시할 수준"],
        "significant": [True, True, True, False],
    }
)

CAPABILITY = pd.DataFrame(
    {
        "characteristic": ["Peel_Strength", "Total_Thickness"],
        "cpk": [1.4636, 2.5121],
    }
)

MSA_COMPONENTS = pd.DataFrame(
    {
        "source": [
            "반복성(EV)",
            "재현성(AV)",
            "교호작용",
            "측정시스템(GRR)",
            "부품(PV)",
        ],
        "percent_study_variation": [14.70, 13.05, 9.06, 21.64, 97.63],
    }
)

RULE_SIGNALS = pd.DataFrame(
    {
        "Machine": ["PRESS_03"] * 3 + ["PRESS_02"],
        "characteristic": ["Cure_Temp"] * 3 + ["Total_Thickness"],
        "rule": [
            "NELSON_RULE_8",
            "NELSON_RULE_2",
            "NELSON_RULE_5",
            "NELSON_RULE_8",
        ],
        "observed": [3, 54, 50, 1],
        "expected_false_alarms": [0.15, 4.96, 5.18, 0.15],
        "ratio": [20.2, 10.9, 9.7, 6.6],
        "severity": ["CRITICAL"] * 3 + ["WARNING"],
        "point_count": [2611, 2611, 2611, 2646],
    }
)

OPERATING_POINTS = pd.DataFrame(
    {
        "target_recall": [0.5, 0.7, 0.9],
        "threshold": [0.3868, 0.2180, 0.0980],
        "achieved_recall": [0.5024, 0.7317, 0.9024],
        "precision": [0.4661, 0.2669, 0.1662],
        "false_alarm_rate": [0.0846, 0.2953, 0.6652],
        "escape_rate": [0.4976, 0.2683, 0.0976],
        "flagged_lots": [221, 562, 1113],
        "missed_defects": [102, 55, 20],
    }
)


@pytest.fixture
def report_dir(tmp_path: Path) -> Path:
    """분석 결과 전부가 갖춰진 임시 report 폴더."""
    files = {
        "quality_machine_summary.csv": MACHINE_SUMMARY,
        "quality_defect_rate_p_chart.csv": P_CHART,
        "quality_anova.csv": ANOVA,
        "quality_capability.csv": CAPABILITY,
        "quality_msa_variance_components.csv": MSA_COMPONENTS,
        "quality_stratified_rule_signals.csv": RULE_SIGNALS,
        "model_operating_points.csv": OPERATING_POINTS,
    }

    for name, frame in files.items():
        frame.to_csv(
            tmp_path / name, index=False, encoding="utf-8-sig"
        )

    return tmp_path


@pytest.fixture
def process_data() -> pd.DataFrame:
    """불량률이 설비별로 다른 최소 데이터셋."""
    rows = []

    for machine, defect_count, total in (
        ("PRESS_01", 7, 100),
        ("PRESS_02", 21, 100),
        ("PRESS_03", 10, 100),
    ):
        for index in range(total):
            rows.append(
                {
                    "Machine": machine,
                    "Defect": (
                        "Delamination"
                        if index < defect_count
                        else "Normal"
                    ),
                }
            )

    return pd.DataFrame(rows)


# =====================================================================
# 사례 선정
# =====================================================================


def test_escalates_only_machines_above_threshold(report_dir):
    ranked = rank_defect_cases(report_dir)

    escalated = set(ranked[ranked["escalate"]]["Machine"])

    assert escalated == {"PRESS_02"}


def test_overall_rate_is_lot_weighted(report_dir):
    """전체 불량률은 단순 평균이 아니라 LOT 수 가중 평균이어야 한다.

    설비별 생산량이 다르면 단순 평균은 틀린 값을 준다.
    """
    ranked = rank_defect_cases(report_dir)
    overall = float(ranked["overall_defect_rate_percent"].iloc[0])

    weighted = (
        MACHINE_SUMMARY["defect_rate_percent"]
        * MACHINE_SUMMARY["lot_count"]
    ).sum() / MACHINE_SUMMARY["lot_count"].sum()

    assert overall == pytest.approx(weighted, abs=0.01)
    assert overall != pytest.approx(
        MACHINE_SUMMARY["defect_rate_percent"].mean(), abs=0.01
    )


def test_drift_ranking_keeps_only_critical(report_dir):
    drifts = rank_drift_cases(report_dir)

    assert len(drifts) == 1
    assert drifts.iloc[0]["Machine"] == "PRESS_03"
    assert drifts.iloc[0]["characteristic"] == "Cure_Temp"
    # WARNING 인 PRESS_02 / Total_Thickness 는 빠져야 한다.
    assert "PRESS_02" not in set(drifts["Machine"])


def test_recommended_cases_cover_both_kinds(report_dir):
    reports = build_recommended_cases(report_dir)

    assert len(reports) == 2
    assert {report.machine for report in reports} == {
        "PRESS_02",
        "PRESS_03",
    }


def test_missing_reports_lists_absent_files(tmp_path):
    missing = missing_reports(tmp_path)

    assert "quality_machine_summary.csv" in missing
    assert "quality_anova.csv" in missing


def test_build_fails_clearly_without_analysis(tmp_path):
    with pytest.raises(FileNotFoundError) as error:
        build_defect_rate_case("PRESS_02", report_dir=tmp_path)

    assert "run_quality_analysis" in str(error.value)


def test_unknown_machine_raises(report_dir):
    with pytest.raises(ValueError) as error:
        build_defect_rate_case("PRESS_99", report_dir=report_dir)

    assert "PRESS_99" in str(error.value)


# =====================================================================
# 파라미터 이탈 — 공차 정규화
# =====================================================================


def test_gap_ranking_uses_tolerance_not_absolute_value(report_dir):
    """공차로 정규화하지 않으면 순위가 뒤집힌다.

    PRESS_02 의 Cure_Temp 는 타 설비 평균 대비 절대 편차가
    Press2_Pressure 보다 크지만, 공차 대비로는 무시할 수준이다.
    """
    gaps = eight_d._machine_parameter_gaps(report_dir, "PRESS_02")

    assert gaps[0].parameter == "Press2_Pressure"
    assert gaps[1].parameter == "Press2_Temp"

    cure = next(
        gap for gap in gaps if gap.parameter == "Cure_Temp"
    )

    assert abs(cure.tolerance_fraction) < 0.01
    assert abs(gaps[0].tolerance_fraction) > 0.2


def test_tolerance_fraction_matches_spec(report_dir):
    gaps = eight_d._machine_parameter_gaps(report_dir, "PRESS_02")
    pressure = gaps[0]

    # Press2_Pressure 규격은 9.0 ~ 11.0, 중심 10.0, 공차 반폭 1.0
    assert pressure.target == pytest.approx(10.0)
    assert pressure.half_tolerance == pytest.approx(1.0)
    assert pressure.deviation == pytest.approx(-0.223, abs=1e-3)
    assert pressure.tolerance_fraction == pytest.approx(
        -0.223, abs=1e-3
    )


def test_ranking_uses_spec_target_not_peer_comparison(report_dir):
    """다른 설비를 기준으로 삼으면 멀쩡한 설비가 이상해 보인다.

    PRESS_03 의 Cure_Temp 가 148.3 으로 드리프트 중이라,
    나머지 설비를 기준으로 잡으면 정상인 PRESS_01 이 +0.8 이탈한
    것처럼 보인다. 설비가 셋뿐이면 중앙값도 이 왜곡을 못 막는다
    (남는 둘의 중앙값은 곧 평균이다).

    순위를 규격 중심 기준으로 매겨야 이 함정을 피한다.
    """
    gaps = eight_d._machine_parameter_gaps(report_dir, "PRESS_01")
    cure = next(gap for gap in gaps if gap.parameter == "Cure_Temp")

    # 다른 설비 기준으로는 크게 벗어난 것처럼 보이지만
    assert abs(cure.peer_gap) > 0.7

    # 규격 중심 기준으로는 사실상 이탈이 없다.
    assert abs(cure.deviation) < 0.05
    assert abs(cure.tolerance_fraction) < 0.02


def test_healthy_machine_has_no_large_deviation(report_dir):
    gaps = eight_d._machine_parameter_gaps(report_dir, "PRESS_01")

    assert all(
        abs(gap.tolerance_fraction) < 0.05 for gap in gaps
    )


# =====================================================================
# D2 문제 기술
# =====================================================================


def test_problem_statement_is_and_is_not_are_disjoint(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    problem = report.d2_problem

    assert problem is not None
    assert set(problem.is_observed) == {"PRESS_02"}
    assert "PRESS_02" not in problem.is_not_observed
    assert set(problem.is_not_observed) == {"PRESS_01", "PRESS_03"}


def test_problem_statement_quotes_real_numbers(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    problem = report.d2_problem

    assert problem is not None
    assert "21.05" in problem.how_many
    assert "2,646" in problem.how_many


def test_every_evidence_names_its_source(report_dir):
    """근거에는 반드시 출처 파일이 붙어야 한다."""
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    collected: list[Evidence] = []
    collected.extend(report.d2_problem.evidence)

    for step in (
        report.d4_occurrence_whys + report.d4_escape_whys
    ):
        collected.extend(step.evidence)

    for action in report.d3_containment:
        collected.extend(action.evidence)

    assert collected

    for item in collected:
        assert item.source.endswith(".csv")
        assert item.value
        assert item.source in item.as_line()


# =====================================================================
# D3 봉쇄조치
# =====================================================================


def test_containment_uses_high_recall_operating_point(report_dir):
    """봉쇄 단계에서는 미검이 과검보다 비싸므로 검출률을 높게 잡는다."""
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    model_actions = [
        action
        for action in report.d3_containment
        if "임계값" in action.description
    ]

    assert len(model_actions) == 1
    assert "0.098" in model_actions[0].description

    evidence = model_actions[0].evidence[0]
    assert "90" in evidence.value
    assert "20" in evidence.interpretation


def test_containment_omitted_without_model_results(report_dir):
    """모델 결과가 없으면 그 조치를 지어내지 않는다."""
    (report_dir / "model_operating_points.csv").unlink()

    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    assert not any(
        "임계값" in action.description
        for action in report.d3_containment
    )
    # 나머지 봉쇄조치는 그대로 남아야 한다.
    assert len(report.d3_containment) == 2


# =====================================================================
# D4 근본원인
# =====================================================================


def test_occurrence_and_escape_are_separate(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    assert report.d4_occurrence_whys
    assert report.d4_escape_whys

    occurrence_text = " ".join(
        step.answer for step in report.d4_occurrence_whys
    )
    escape_text = " ".join(
        step.answer for step in report.d4_escape_whys
    )

    assert "Press2_Pressure" in occurrence_text
    assert "관리한계" in escape_text


def test_why_chain_marks_unverified_steps(report_dir):
    """데이터로 확인되지 않은 단계는 추정으로 표시돼야 한다."""
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    unverified = [
        step
        for step in report.d4_occurrence_whys
        if not step.verified
    ]

    assert len(unverified) == 1
    assert unverified[0].marker == "추정"
    assert "현장에서 확인" in unverified[0].answer


def test_why_depths_are_sequential(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    depths = [step.depth for step in report.d4_occurrence_whys]

    assert depths == list(range(1, len(depths) + 1))


def test_material_excluded_on_negligible_effect_size(report_dir):
    """p 값만 보면 틀린다.

    Model 인자의 Yield 는 유의하지만 eta^2 = 0.0027 로
    무시할 수준이다. n 이 크면 의미 없는 차이도 유의해진다.
    """
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    material = next(
        cause
        for cause in report.d4_causes
        if cause.category == "자재(Material)"
    )

    assert material.status == STATUS_EXCLUDED
    assert "효과 크기" in material.basis


def test_operator_excluded_when_reproducibility_is_small(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    operator = next(
        cause
        for cause in report.d4_causes
        if cause.category == "사람(Man)"
    )

    assert operator.status == STATUS_EXCLUDED
    assert "재현성" in operator.basis


def test_measurement_not_excluded_at_conditional_grr(report_dir):
    """%GRR 21.6% 는 조건부 적합이므로 배제하면 안 된다."""
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    measurement = next(
        cause
        for cause in report.d4_causes
        if cause.category == "측정(Measurement)"
    )

    assert measurement.status == STATUS_UNVERIFIED
    assert "21.6" in measurement.basis


def test_measurement_excluded_when_grr_is_small(report_dir):
    components = MSA_COMPONENTS.copy()
    components.loc[
        components["source"] == "측정시스템(GRR)",
        "percent_study_variation",
    ] = 7.4
    components.to_csv(
        report_dir / "quality_msa_variance_components.csv",
        index=False,
        encoding="utf-8-sig",
    )

    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    measurement = next(
        cause
        for cause in report.d4_causes
        if cause.category == "측정(Measurement)"
    )

    assert measurement.status == STATUS_EXCLUDED


def test_environment_stays_unverified_without_data(report_dir):
    """수집하지 않은 데이터에 대해 결론을 내지 않는다."""
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    environment = next(
        cause
        for cause in report.d4_causes
        if cause.category == "환경(Environment)"
    )

    assert environment.status == STATUS_UNVERIFIED


def test_confirmed_causes_all_cite_a_report(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    assert report.confirmed_causes

    for cause in report.confirmed_causes:
        assert ".csv" in cause.basis


# =====================================================================
# D5 ~ D8 — 실행하지 않은 것을 완료로 적지 않는다
# =====================================================================


def test_action_stages_start_pending(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    status = report.discipline_status

    for code in ("D0", "D3", "D5", "D7"):
        assert status[code] == ACTION_PENDING

    assert status["D8"] == ACTION_PENDING
    assert report.d8_closure == ""


def test_analysis_stages_are_complete(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    status = report.discipline_status

    assert status["D1"] == ACTION_DONE
    assert status["D2"] == ACTION_DONE
    assert status["D4"] == ACTION_DONE
    assert report.analysis_complete


def test_pending_stages_exclude_analysis(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    assert "D2" not in report.pending_stages
    assert "D4" not in report.pending_stages
    assert "D5" in report.pending_stages


def test_team_is_roles_not_invented_names(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    assert len(report.d1_team) >= 4

    for member in report.d1_team:
        assert member.role
        assert member.responsibility
        assert member.discipline_focus


def test_open_questions_include_unverified_causes(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)

    assert report.open_questions

    for cause in report.unverified_causes:
        assert any(
            cause.description in question
            for question in report.open_questions
        )


# =====================================================================
# D6 효과 확인
# =====================================================================


def test_target_direction_and_progress():
    target = VerificationTarget(
        metric="불량률",
        baseline=20.0,
        target=10.0,
        unit="%",
        direction="감소",
        method="재계산",
    )

    assert not target.is_met(20.0)
    assert target.is_met(10.0)
    assert target.is_met(8.0)
    assert target.progress(20.0) == pytest.approx(0.0)
    assert target.progress(15.0) == pytest.approx(50.0)
    assert target.progress(10.0) == pytest.approx(100.0)


def test_increasing_target_direction():
    target = VerificationTarget(
        metric="Cpk",
        baseline=1.2,
        target=1.67,
        unit="",
        direction="증가",
        method="재계산",
    )

    assert not target.is_met(1.2)
    assert target.is_met(1.7)


def test_zero_span_target_is_met():
    target = VerificationTarget(
        metric="동일",
        baseline=1.0,
        target=1.0,
        unit="",
        direction="증가",
        method="재계산",
    )

    assert target.progress(1.0) == pytest.approx(100.0)


def test_baseline_matches_reported_rate(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    primary = report.d6_targets[0]

    assert primary.baseline == pytest.approx(21.05, abs=0.01)
    assert primary.target == pytest.approx(12.84, abs=0.05)
    assert primary.direction == "감소"


def test_verification_recomputes_from_raw_data(
    report_dir, process_data
):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    table = build_verification_table(report, process_data)

    row = table.iloc[0]

    assert row["현재"] == pytest.approx(21.0, abs=0.01)
    assert row["달성"] == "아니오"


def test_verification_reports_unmeasured_without_data(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    table = build_verification_table(report, None)

    assert set(table["달성"]) == {"미측정"}


def test_verification_shows_success_after_improvement(
    report_dir, process_data
):
    """조치가 효과를 내면 달성으로 바뀌어야 한다."""
    improved = process_data.copy()
    mask = improved["Machine"] == "PRESS_02"
    improved.loc[mask, "Defect"] = ["Normal"] * int(mask.sum())

    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    table = build_verification_table(report, improved)

    assert table.iloc[0]["현재"] == pytest.approx(0.0)
    assert table.iloc[0]["달성"] == "예"


def test_verify_defect_rate_requires_columns(process_data):
    with pytest.raises(KeyError):
        verify_defect_rate(
            process_data.drop(columns=["Machine"]), "PRESS_02"
        )

    with pytest.raises(KeyError):
        verify_defect_rate(
            process_data.drop(columns=["Defect"]), "PRESS_02"
        )


def test_verify_defect_rate_rejects_unknown_machine(process_data):
    with pytest.raises(ValueError):
        verify_defect_rate(process_data, "PRESS_99")


# =====================================================================
# 드리프트 사례
# =====================================================================


def test_drift_case_is_preventive(report_dir):
    report = build_drift_case(
        "PRESS_03", "Cure_Temp", report_dir=report_dir
    )

    assert report.severity == "예방"
    assert report.machine == "PRESS_03"


def test_drift_escape_reason_is_shewhart_insensitivity(report_dir):
    report = build_drift_case(
        "PRESS_03", "Cure_Temp", report_dir=report_dir
    )

    escape_text = " ".join(
        step.answer for step in report.d4_escape_whys
    )

    assert "Shewhart" in escape_text
    assert "EWMA" in escape_text or "CUSUM" in escape_text


def test_drift_case_reports_tolerance_consumption(report_dir):
    report = build_drift_case(
        "PRESS_03", "Cure_Temp", report_dir=report_dir
    )

    answers = " ".join(
        step.answer for step in report.d4_occurrence_whys
    )

    # 148.313 vs 150 중심, 공차 반폭 5.0 -> 약 34%
    assert "34%" in answers or "33%" in answers


def test_drift_case_rejects_missing_combination(report_dir):
    with pytest.raises(ValueError):
        build_drift_case(
            "PRESS_01", "Cure_Temp", report_dir=report_dir
        )


def test_drift_case_requires_signal_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_drift_case(
            "PRESS_03", "Cure_Temp", report_dir=tmp_path
        )


# =====================================================================
# 마크다운 출력
# =====================================================================


def test_markdown_contains_all_disciplines(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    text = render_markdown(report)

    for code, title in DISCIPLINE_TITLES.items():
        assert f"{code}." in text or f"| {code} |" in text
        assert title in text


def test_markdown_does_not_claim_completion(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    text = render_markdown(report)

    assert "D6 효과 확인이 끝난 뒤 작성한다" in text
    assert "미해결 항목" in text


def test_markdown_lists_evidence_sources(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    text = render_markdown(report)

    assert "quality_machine_summary.csv" in text
    assert "quality_defect_rate_p_chart.csv" in text
    assert "model_operating_points.csv" in text


def test_markdown_is_stable_for_fixed_date(report_dir):
    """같은 입력이면 같은 문서가 나와야 한다."""
    opened = date(2026, 1, 15)
    first = render_markdown(
        build_defect_rate_case(
            "PRESS_02", report_dir=report_dir, opened_on=opened
        )
    )
    second = render_markdown(
        build_defect_rate_case(
            "PRESS_02", report_dir=report_dir, opened_on=opened
        )
    )

    assert first == second
    assert "2026-01-15" in first


def test_summary_row_shape(report_dir):
    report = build_defect_rate_case("PRESS_02", report_dir=report_dir)
    row = report.summary_row()

    assert row["case_id"] == "8D-PRESS_02-DEFECT-RATE"
    assert row["analysis_complete"] is True
    assert row["confirmed_causes"] >= 1
    assert "D5" in row["pending_stages"]


# =====================================================================
# 구성 요소 단위
# =====================================================================


def test_evidence_line_is_traceable():
    evidence = Evidence(
        source="quality_anova.csv",
        metric="eta^2",
        value="0.113",
        interpretation="효과 크기 중간",
    )

    line = evidence.as_line()

    assert "eta^2" in line
    assert "0.113" in line
    assert "quality_anova.csv" in line


def test_why_step_marker():
    assert (
        WhyStep(1, "q", "a", verified=True).marker == "확인"
    )
    assert (
        WhyStep(1, "q", "a", verified=False).marker == "추정"
    )


def test_empty_report_has_no_completed_action_stages():
    report = EightDReport(
        case_id="X",
        title="빈 사례",
        opened_on=date(2026, 1, 1),
        severity="일반",
    )
    status = report.discipline_status

    assert status["D0"] == ACTION_PENDING
    assert status["D3"] == ACTION_PENDING
    assert not report.analysis_complete


def test_action_status_rolls_up_to_done():
    report = EightDReport(
        case_id="X",
        title="완료 사례",
        opened_on=date(2026, 1, 1),
        severity="일반",
        d3_containment=(
            Action("a", "품질", "확인", ACTION_DONE),
            Action("b", "생산", "확인", ACTION_DONE),
        ),
    )

    assert report.discipline_status["D3"] == ACTION_DONE


def test_action_status_is_ongoing_when_mixed():
    report = EightDReport(
        case_id="X",
        title="혼합 사례",
        opened_on=date(2026, 1, 1),
        severity="일반",
        d3_containment=(
            Action("a", "품질", "확인", ACTION_DONE),
            Action("b", "생산", "확인", ACTION_PENDING),
        ),
    )

    assert report.discipline_status["D3"] != ACTION_DONE


def test_cause_status_vocabulary_is_closed():
    """상태 어휘가 늘어나면 화면 색 대응이 깨진다."""
    assert {
        STATUS_CONFIRMED,
        STATUS_EXCLUDED,
        STATUS_UNVERIFIED,
    } == {"확인됨", "배제됨", "미확인"}
