"""측정시스템 분석(Gage R&R) 검증.

검증 전략
---------
1. 제곱합 분해가 성립하는지 확인한다.
   SS_part + SS_operator + SS_interaction + SS_error = SS_total
   이 항등식이 깨지면 ANOVA 계산이 틀린 것이다.

2. 자유도 합이 총 자유도와 같은지 확인한다.

3. 분산 성분을 알고 있는 데이터를 합성해 회수되는지 확인한다.
   계측기 산포와 부품 산포를 직접 지정해 생성한 뒤,
   EV 와 PV 가 그 값 근처로 복원되는지 본다.

4. 작업자 편향이 없으면 AV 가 0 에 가까워야 하고,
   편향을 넣으면 AV 가 커져야 한다.

5. %GRR, ndc, %P/T 공식이 정의와 일치하는지 확인한다.
"""

import numpy as np
import pandas as pd
import pytest

from src.quality.msa import (
    NDC_CONSTANT,
    bias_and_linearity,
    gage_rnr_anova,
)


def build_study(
    part_sigma: float = 1.0,
    repeatability_sigma: float = 0.1,
    operator_bias: dict[str, float] | None = None,
    interaction_coefficient: dict[str, float] | None = None,
    part_count: int = 10,
    replicate_count: int = 3,
    seed: int = 101,
) -> pd.DataFrame:
    """분산 성분을 지정해 Gage R&R 연구 데이터를 합성한다."""
    rng = np.random.default_rng(seed)

    operators = list(
        (operator_bias or {"OP_A": 0.0, "OP_B": 0.0, "OP_C": 0.0})
    )

    biases = operator_bias or dict.fromkeys(operators, 0.0)
    interactions = interaction_coefficient or dict.fromkeys(
        operators, 0.0
    )

    part_values = rng.normal(100.0, part_sigma, part_count)
    part_centered = part_values - part_values.mean()

    records: list[dict[str, object]] = []

    for index in range(part_count):
        for operator in operators:
            for replicate in range(1, replicate_count + 1):
                measured = (
                    part_values[index]
                    + biases[operator]
                    + interactions[operator] * part_centered[index]
                    + rng.normal(0.0, repeatability_sigma)
                )

                records.append(
                    {
                        "Part": f"P{index + 1:02d}",
                        "Operator": operator,
                        "Replicate": replicate,
                        "Value": float(measured),
                    }
                )

    return pd.DataFrame(records)


class TestAnovaDecomposition:
    def test_sum_of_squares_adds_up(self):
        study = build_study()

        result = gage_rnr_anova(study, "Value")

        table = result.anova_table.set_index("source")

        components = (
            table.loc["부품(Part)", "ss"]
            + table.loc["작업자(Operator)", "ss"]
            + table.loc["부품 x 작업자", "ss"]
            + table.loc["반복(Error)", "ss"]
        )

        assert components == pytest.approx(
            table.loc["합계", "ss"], rel=1e-10
        )

    def test_degrees_of_freedom_add_up(self):
        study = build_study(part_count=10, replicate_count=3)

        result = gage_rnr_anova(study, "Value")

        table = result.anova_table.set_index("source")

        assert table.loc["부품(Part)", "df"] == 9
        assert table.loc["작업자(Operator)", "df"] == 2
        assert table.loc["부품 x 작업자", "df"] == 18
        assert table.loc["반복(Error)", "df"] == 60
        assert table.loc["합계", "df"] == 89

    def test_total_ss_matches_direct_computation(self):
        study = build_study()

        result = gage_rnr_anova(study, "Value")

        values = study["Value"].to_numpy()
        expected = float(((values - values.mean()) ** 2).sum())

        table = result.anova_table.set_index("source")

        assert table.loc["합계", "ss"] == pytest.approx(
            expected, rel=1e-10
        )

    def test_mean_squares_are_ss_over_df(self):
        study = build_study()

        result = gage_rnr_anova(study, "Value")

        table = result.anova_table

        for _, row in table.iterrows():
            if row["source"] == "합계":
                continue

            assert row["ms"] == pytest.approx(
                row["ss"] / row["df"], rel=1e-10
            )


class TestVarianceComponentRecovery:
    def test_recovers_repeatability_sigma(self):
        study = build_study(
            part_sigma=1.0,
            repeatability_sigma=0.20,
            part_count=15,
            replicate_count=4,
            seed=202,
        )

        result = gage_rnr_anova(study, "Value")

        assert result.repeatability_ev == pytest.approx(
            0.20, rel=0.15
        )

    def test_recovers_part_variation(self):
        study = build_study(
            part_sigma=2.0,
            repeatability_sigma=0.10,
            part_count=20,
            replicate_count=3,
            seed=303,
        )

        result = gage_rnr_anova(study, "Value")

        assert result.part_variation_pv == pytest.approx(
            2.0, rel=0.30
        )

    def test_no_operator_bias_gives_small_av(self):
        study = build_study(
            part_sigma=1.0,
            repeatability_sigma=0.10,
            operator_bias={"OP_A": 0.0, "OP_B": 0.0, "OP_C": 0.0},
            part_count=15,
            seed=404,
        )

        result = gage_rnr_anova(study, "Value")

        assert result.reproducibility_av < result.repeatability_ev

    def test_operator_bias_increases_av(self):
        without_bias = gage_rnr_anova(
            build_study(
                repeatability_sigma=0.10,
                operator_bias={
                    "OP_A": 0.0,
                    "OP_B": 0.0,
                    "OP_C": 0.0,
                },
                seed=505,
            ),
            "Value",
        )

        with_bias = gage_rnr_anova(
            build_study(
                repeatability_sigma=0.10,
                operator_bias={
                    "OP_A": 0.0,
                    "OP_B": 0.3,
                    "OP_C": -0.3,
                },
                seed=505,
            ),
            "Value",
        )

        assert (
            with_bias.reproducibility_av
            > without_bias.reproducibility_av * 3
        )
        assert with_bias.dominant_source == "재현성(작업자)"

    def test_variance_components_are_non_negative(self):
        study = build_study(repeatability_sigma=0.5, seed=606)

        result = gage_rnr_anova(study, "Value")

        assert result.repeatability_ev >= 0
        assert result.reproducibility_av >= 0
        assert result.interaction_sd >= 0
        assert result.part_variation_pv >= 0


class TestInteractionPooling:
    def test_pools_interaction_when_not_significant(self):
        study = build_study(
            interaction_coefficient={
                "OP_A": 0.0,
                "OP_B": 0.0,
                "OP_C": 0.0,
            },
            seed=707,
        )

        result = gage_rnr_anova(study, "Value")

        assert result.interaction_pooled
        assert result.interaction_sd == pytest.approx(0.0)

    def test_keeps_interaction_when_significant(self):
        study = build_study(
            repeatability_sigma=0.05,
            interaction_coefficient={
                "OP_A": 0.0,
                "OP_B": 0.0,
                "OP_C": -0.35,
            },
            part_count=15,
            seed=808,
        )

        result = gage_rnr_anova(study, "Value")

        assert not result.interaction_pooled
        assert result.interaction_p_value < 0.25
        assert result.interaction_sd > 0
        assert "교호작용" in result.diagnosis


class TestIndexFormulas:
    def test_grr_is_root_sum_of_squares(self):
        study = build_study(seed=909)

        result = gage_rnr_anova(study, "Value")

        expected = np.sqrt(
            result.repeatability_ev**2
            + result.reproducibility_av**2
            + result.interaction_sd**2
        )

        assert result.gage_rnr == pytest.approx(expected, rel=1e-10)

    def test_total_variation_is_root_sum_of_grr_and_pv(self):
        study = build_study(seed=1010)

        result = gage_rnr_anova(study, "Value")

        expected = np.sqrt(
            result.gage_rnr**2 + result.part_variation_pv**2
        )

        assert result.total_variation_tv == pytest.approx(
            expected, rel=1e-10
        )

    def test_percentages_are_relative_to_total_variation(self):
        study = build_study(seed=1111)

        result = gage_rnr_anova(study, "Value")

        assert result.percent_grr == pytest.approx(
            100 * result.gage_rnr / result.total_variation_tv,
            rel=1e-10,
        )
        assert result.percent_pv == pytest.approx(
            100 * result.part_variation_pv / result.total_variation_tv,
            rel=1e-10,
        )

    def test_ndc_formula(self):
        study = build_study(seed=1212)

        result = gage_rnr_anova(study, "Value")

        expected = int(
            NDC_CONSTANT
            * result.part_variation_pv
            / result.gage_rnr
        )

        assert result.number_of_distinct_categories == expected

    def test_percent_precision_to_tolerance(self):
        study = build_study(seed=1313)

        result = gage_rnr_anova(study, "Value", tolerance=4.0)

        assert result.percent_precision_to_tolerance == pytest.approx(
            100 * 6 * result.gage_rnr / 4.0, rel=1e-10
        )

    def test_percent_pt_is_none_without_tolerance(self):
        study = build_study(seed=1414)

        result = gage_rnr_anova(study, "Value")

        assert result.percent_precision_to_tolerance is None


class TestVerdict:
    def test_good_gage_is_acceptable(self):
        study = build_study(
            part_sigma=3.0,
            repeatability_sigma=0.05,
            part_count=15,
            seed=1515,
        )

        result = gage_rnr_anova(study, "Value")

        assert result.percent_grr < 10.0
        assert result.verdict == "적합"

    def test_bad_gage_is_unacceptable(self):
        study = build_study(
            part_sigma=0.5,
            repeatability_sigma=0.8,
            part_count=10,
            seed=1616,
        )

        result = gage_rnr_anova(study, "Value")

        assert result.percent_grr > 30.0
        assert result.verdict == "부적합"

    def test_low_ndc_is_reported_in_diagnosis(self):
        study = build_study(
            part_sigma=0.4,
            repeatability_sigma=0.5,
            part_count=10,
            seed=1717,
        )

        result = gage_rnr_anova(study, "Value")

        assert result.number_of_distinct_categories < 5
        assert "ndc" in result.diagnosis

    def test_variance_components_table_shape(self):
        study = build_study(seed=1818)

        result = gage_rnr_anova(study, "Value")
        table = result.variance_components()

        assert len(table) == 6
        assert {
            "source",
            "std_dev",
            "variance",
            "percent_study_variation",
            "percent_contribution",
        }.issubset(set(table.columns))


class TestDesignValidation:
    def test_rejects_unbalanced_replicates(self):
        study = build_study(seed=1919)
        unbalanced = study.iloc[:-1]

        with pytest.raises(ValueError, match="불균형 설계"):
            gage_rnr_anova(unbalanced, "Value")

    def test_rejects_single_replicate(self):
        study = build_study(replicate_count=1, seed=2020)

        with pytest.raises(ValueError, match="반복 측정이 2회 이상"):
            gage_rnr_anova(study, "Value")

    def test_rejects_missing_column(self):
        study = build_study(seed=2121)

        with pytest.raises(ValueError, match="존재하지 않는"):
            gage_rnr_anova(study, "NoSuchColumn")

    def test_rejects_non_crossed_design(self):
        """작업자가 서로 다른 부품만 측정하면 교차 설계가 아니다."""
        study = build_study(seed=2222)

        first_half = study[
            (study["Operator"] == "OP_A")
            & (study["Part"].isin(["P01", "P02", "P03"]))
        ]
        second_half = study[
            (study["Operator"] == "OP_B")
            & (study["Part"].isin(["P04", "P05", "P06"]))
        ]

        nested = pd.concat([first_half, second_half])

        with pytest.raises(ValueError, match="교차 설계가 아닙니다"):
            gage_rnr_anova(nested, "Value")


class TestBiasAndLinearity:
    def test_detects_systematic_bias(self):
        rng = np.random.default_rng(31)

        reference = np.repeat(np.linspace(30.0, 34.0, 10), 5)
        measured = reference + 0.25 + rng.normal(0.0, 0.05, len(reference))

        frame = pd.DataFrame(
            {"Reference": reference, "Measured": measured}
        )

        result = bias_and_linearity(frame, "Measured", "Reference")

        assert result["bias"] == pytest.approx(0.25, abs=0.03)
        assert result["bias_significant"]
        assert result["slope"] == pytest.approx(1.0, abs=0.05)

    def test_no_bias_is_not_flagged(self):
        rng = np.random.default_rng(32)

        reference = np.repeat(np.linspace(30.0, 34.0, 10), 5)
        measured = reference + rng.normal(0.0, 0.05, len(reference))

        frame = pd.DataFrame(
            {"Reference": reference, "Measured": measured}
        )

        result = bias_and_linearity(frame, "Measured", "Reference")

        assert not result["bias_significant"]

    def test_detects_linearity_deviation(self):
        rng = np.random.default_rng(33)

        reference = np.repeat(np.linspace(30.0, 34.0, 10), 5)
        # 기울기 0.9 -> 구간에 따라 편향이 달라진다
        measured = (
            0.9 * reference
            + 3.2
            + rng.normal(0.0, 0.03, len(reference))
        )

        frame = pd.DataFrame(
            {"Reference": reference, "Measured": measured}
        )

        result = bias_and_linearity(frame, "Measured", "Reference")

        assert result["slope"] == pytest.approx(0.9, abs=0.02)
        assert result["linearity"] == pytest.approx(
            0.1 * 4.0, abs=0.05
        )

    def test_requires_minimum_observations(self):
        frame = pd.DataFrame(
            {"Reference": [1.0, 2.0], "Measured": [1.1, 2.1]}
        )

        with pytest.raises(ValueError, match="3개 이상"):
            bias_and_linearity(frame, "Measured", "Reference")

    def test_rejects_missing_column(self):
        frame = pd.DataFrame(
            {"Reference": [1.0, 2.0, 3.0], "Measured": [1.0, 2.0, 3.0]}
        )

        with pytest.raises(ValueError, match="존재하지 않는"):
            bias_and_linearity(frame, "Absent", "Reference")
