"""분산분석과 Tukey HSD 검증.

검증 전략
---------
직접 구현한 계산을 scipy 의 검증된 구현과 대조한다.
- one_way_anova 의 F, p -> scipy.stats.f_oneway
- tukey_hsd 의 p -> scipy.stats.tukey_hsd
- Welch ANOVA -> scipy.stats.f_oneway(equal_var=False)
- Levene -> scipy.stats.levene

값을 눈으로 확인하는 것보다, 독립 구현과 일치하는지 확인하는 편이
회귀(regression)를 잡는 데 유용하다.
"""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from src.quality.anova import (
    compare_factor_across_responses,
    one_way_anova,
    tukey_hsd,
    tukey_hsd_table,
)


@pytest.fixture
def three_group_frame() -> pd.DataFrame:
    """평균이 서로 다른 3개 집단. 불균형 표본."""
    rng = np.random.default_rng(20260926)

    groups = {
        "PRESS_01": rng.normal(100.0, 2.0, 60),
        "PRESS_02": rng.normal(103.5, 2.0, 45),
        "PRESS_03": rng.normal(100.4, 2.0, 55),
    }

    records = [
        {"Machine": name, "Value": float(value)}
        for name, values in groups.items()
        for value in values
    ]

    return pd.DataFrame(records)


@pytest.fixture
def equal_means_frame() -> pd.DataFrame:
    """평균이 같은 3개 집단."""
    rng = np.random.default_rng(11)

    records = [
        {"Machine": name, "Value": float(value)}
        for name in ("A", "B", "C")
        for value in rng.normal(50.0, 3.0, 40)
    ]

    return pd.DataFrame(records)


def _group_arrays(
    frame: pd.DataFrame,
) -> list[np.ndarray]:
    return [
        subset["Value"].to_numpy(dtype=float)
        for _, subset in frame.groupby("Machine", sort=True)
    ]


class TestOneWayAnova:
    def test_f_and_p_match_scipy(self, three_group_frame):
        result = one_way_anova(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        reference = stats.f_oneway(*_group_arrays(three_group_frame))

        assert result.f_statistic == pytest.approx(
            reference.statistic, rel=1e-10
        )
        assert result.p_value == pytest.approx(
            reference.pvalue, rel=1e-8
        )

    def test_sum_of_squares_decomposition(self, three_group_frame):
        """SS_between + SS_within = SS_total 이 성립해야 한다."""
        result = one_way_anova(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        values = three_group_frame["Value"].to_numpy(dtype=float)
        total = float(((values - values.mean()) ** 2).sum())

        assert (
            result.sum_of_squares_between
            + result.sum_of_squares_within
        ) == pytest.approx(total, rel=1e-10)

    def test_degrees_of_freedom(self, three_group_frame):
        result = one_way_anova(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        assert result.degrees_of_freedom_between == 2
        assert result.degrees_of_freedom_within == 160 - 3

    def test_welch_matches_scipy(self, three_group_frame):
        result = one_way_anova(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        reference = stats.f_oneway(
            *_group_arrays(three_group_frame),
            equal_var=False,
        )

        assert result.welch_f_statistic == pytest.approx(
            reference.statistic, rel=1e-10
        )
        assert result.welch_p_value == pytest.approx(
            reference.pvalue, rel=1e-8
        )

    def test_levene_matches_scipy(self, three_group_frame):
        result = one_way_anova(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        reference = stats.levene(
            *_group_arrays(three_group_frame),
            center="median",
        )

        assert result.levene_p_value == pytest.approx(
            reference.pvalue, rel=1e-8
        )

    def test_detects_real_difference(self, three_group_frame):
        result = one_way_anova(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        assert result.significant
        assert result.p_value < 0.001

    def test_does_not_detect_absent_difference(
        self, equal_means_frame
    ):
        result = one_way_anova(
            dataframe=equal_means_frame,
            response="Value",
            factor="Machine",
        )

        assert not result.significant

    def test_eta_squared_within_unit_interval(
        self, three_group_frame
    ):
        result = one_way_anova(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        assert 0.0 <= result.eta_squared <= 1.0
        assert 0.0 <= result.omega_squared <= 1.0
        assert result.omega_squared <= result.eta_squared

    def test_group_summary_is_sorted_by_mean(
        self, three_group_frame
    ):
        result = one_way_anova(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        means = result.group_summary["mean"].tolist()

        assert means == sorted(means, reverse=True)

    def test_rejects_single_group(self):
        frame = pd.DataFrame(
            {"Machine": ["A"] * 10, "Value": range(10)}
        )

        with pytest.raises(ValueError, match="2개 이상"):
            one_way_anova(
                dataframe=frame,
                response="Value",
                factor="Machine",
            )

    def test_rejects_missing_column(self, three_group_frame):
        with pytest.raises(ValueError, match="존재하지 않는"):
            one_way_anova(
                dataframe=three_group_frame,
                response="NoSuchColumn",
                factor="Machine",
            )


class TestTukeyHsd:
    def test_p_values_match_scipy(self, three_group_frame):
        """직접 구현한 Tukey HSD p값이 scipy 와 일치해야 한다."""
        comparisons = tukey_hsd(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        arrays = _group_arrays(three_group_frame)
        levels = sorted(three_group_frame["Machine"].unique())

        reference = stats.tukey_hsd(*arrays)

        index_of = {name: position for position, name in enumerate(levels)}

        for comparison in comparisons:
            first = index_of[comparison.group_a]
            second = index_of[comparison.group_b]

            assert comparison.p_value == pytest.approx(
                reference.pvalue[first, second],
                abs=1e-9,
            )

    def test_mean_differences_match_scipy(self, three_group_frame):
        comparisons = tukey_hsd(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        arrays = _group_arrays(three_group_frame)
        levels = sorted(three_group_frame["Machine"].unique())
        reference = stats.tukey_hsd(*arrays)

        index_of = {name: position for position, name in enumerate(levels)}

        for comparison in comparisons:
            first = index_of[comparison.group_a]
            second = index_of[comparison.group_b]

            assert comparison.mean_difference == pytest.approx(
                reference.statistic[first, second],
                rel=1e-10,
            )

    def test_confidence_intervals_match_scipy(
        self, three_group_frame
    ):
        comparisons = tukey_hsd(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
            alpha=0.05,
        )

        arrays = _group_arrays(three_group_frame)
        levels = sorted(three_group_frame["Machine"].unique())
        reference = stats.tukey_hsd(*arrays).confidence_interval(
            confidence_level=0.95
        )

        index_of = {name: position for position, name in enumerate(levels)}

        for comparison in comparisons:
            first = index_of[comparison.group_a]
            second = index_of[comparison.group_b]

            assert comparison.confidence_lower == pytest.approx(
                reference.low[first, second], abs=1e-8
            )
            assert comparison.confidence_upper == pytest.approx(
                reference.high[first, second], abs=1e-8
            )

    def test_all_pairs_are_compared(self, three_group_frame):
        comparisons = tukey_hsd(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        # 3개 집단 -> 3개 쌍
        assert len(comparisons) == 3

        pairs = {
            frozenset((item.group_a, item.group_b))
            for item in comparisons
        }
        assert len(pairs) == 3

    def test_results_sorted_by_p_value(self, three_group_frame):
        comparisons = tukey_hsd(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        p_values = [item.p_value for item in comparisons]

        assert p_values == sorted(p_values)

    def test_identifies_the_deviating_group(
        self, three_group_frame
    ):
        """평균이 다르게 설정된 PRESS_02 가 양쪽과 유의하게 달라야 한다."""
        comparisons = tukey_hsd(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        significant_pairs = {
            frozenset((item.group_a, item.group_b))
            for item in comparisons
            if item.significant
        }

        assert frozenset(("PRESS_01", "PRESS_02")) in significant_pairs
        assert frozenset(("PRESS_02", "PRESS_03")) in significant_pairs
        # 평균이 비슷한 두 설비는 유의하지 않아야 한다.
        assert (
            frozenset(("PRESS_01", "PRESS_03"))
            not in significant_pairs
        )

    def test_confidence_interval_excludes_zero_when_significant(
        self, three_group_frame
    ):
        for comparison in tukey_hsd(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        ):
            contains_zero = (
                comparison.confidence_lower
                <= 0.0
                <= comparison.confidence_upper
            )

            assert comparison.significant != contains_zero

    def test_table_has_expected_columns(self, three_group_frame):
        table = tukey_hsd_table(
            dataframe=three_group_frame,
            response="Value",
            factor="Machine",
        )

        expected = {
            "group_a",
            "group_b",
            "mean_difference",
            "std_error",
            "q_statistic",
            "p_value",
            "ci_lower",
            "ci_upper",
            "significant",
        }

        assert expected.issubset(set(table.columns))


class TestCompareFactorAcrossResponses:
    def test_skips_non_numeric_and_missing_columns(
        self, three_group_frame
    ):
        frame = three_group_frame.assign(
            Label=lambda item: item["Machine"],
            Other=lambda item: item["Value"] * 2,
        )

        anova_table, pairwise_table = (
            compare_factor_across_responses(
                dataframe=frame,
                factor="Machine",
                responses=["Value", "Other", "Label", "Absent"],
            )
        )

        assert set(anova_table["response"]) == {"Value", "Other"}
        assert not pairwise_table.empty

    def test_pairwise_only_contains_significant_rows(
        self, three_group_frame
    ):
        _, pairwise_table = compare_factor_across_responses(
            dataframe=three_group_frame,
            factor="Machine",
            responses=["Value"],
        )

        assert pairwise_table["significant"].all()

    def test_returns_empty_pairwise_when_no_difference(
        self, equal_means_frame
    ):
        anova_table, pairwise_table = (
            compare_factor_across_responses(
                dataframe=equal_means_frame,
                factor="Machine",
                responses=["Value"],
            )
        )

        assert not anova_table.empty
        assert pairwise_table.empty
