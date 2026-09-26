"""관리도 계산 검증.

검증 전략
---------
관리도 계수는 표준 계수표의 값이므로, 손으로 계산할 수 있는 작은 예제로
공식이 맞는지 확인한다. 특히 관리한계가 전체 표준편차가 아니라
부분군 내 변동으로 계산되는지를 확인한다. 이것이 이전 버전의 오류였다.
"""

import numpy as np
import pandas as pd
import pytest

from src.quality.constants import (
    D2,
    E2_INDIVIDUAL,
    get_a2,
    get_d2,
    get_range_limit_factors,
)
from src.quality.control_charts import (
    build_defect_rate_subgroups,
    calculate_moving_ranges,
    estimate_sigma_overall,
    estimate_sigma_within,
    individual_moving_range_chart,
    p_chart,
    xbar_r_chart,
)


class TestConstants:
    def test_d2_for_subgroup_size_two(self):
        """이동범위 기반 시그마 추정의 핵심 계수."""
        assert get_d2(2) == pytest.approx(1.128)

    def test_e2_is_three_over_d2(self):
        assert E2_INDIVIDUAL == pytest.approx(3.0 / 1.128, rel=1e-9)
        assert E2_INDIVIDUAL == pytest.approx(2.66, abs=0.005)

    def test_d2_increases_with_subgroup_size(self):
        sizes = sorted(D2)
        values = [D2[size] for size in sizes]

        assert values == sorted(values)

    def test_a2_decreases_with_subgroup_size(self):
        values = [get_a2(size) for size in range(2, 11)]

        assert values == sorted(values, reverse=True)

    def test_range_limit_factors(self):
        d3, d4 = get_range_limit_factors(2)

        assert d3 == pytest.approx(0.0)
        assert d4 == pytest.approx(3.267)

    def test_rejects_unsupported_subgroup_size(self):
        with pytest.raises(ValueError, match="d2 계수"):
            get_d2(99)

        with pytest.raises(ValueError, match="A2 계수"):
            get_a2(99)


class TestMovingRanges:
    def test_moving_ranges_are_absolute_differences(self):
        values = [10.0, 12.0, 9.0, 9.0, 14.0]

        result = calculate_moving_ranges(values)

        np.testing.assert_allclose(
            result,
            [2.0, 3.0, 0.0, 5.0],
        )

    def test_length_is_one_less_than_input(self):
        values = np.arange(20, dtype=float)

        assert calculate_moving_ranges(values).size == 19

    def test_drops_missing_values(self):
        series = pd.Series([1.0, np.nan, 3.0, 4.0])

        result = calculate_moving_ranges(series)

        np.testing.assert_allclose(result, [2.0, 1.0])

    def test_requires_at_least_two_values(self):
        with pytest.raises(ValueError, match="2개 이상"):
            calculate_moving_ranges([5.0])


class TestIndividualMovingRangeChart:
    def test_limits_use_moving_range_not_overall_sigma(self):
        """관리한계가 MR_bar 기반이어야 한다.

        이전 버전은 mean +- 3 * std(전체) 로 계산했다.
        추세가 있는 데이터에서는 두 방식의 결과가 크게 다르다.
        """
        # 선형 추세가 있는 데이터. 전체 표준편차는 크지만
        # 인접 관측값 차이(이동범위)는 일정하게 작다.
        values = np.arange(50, dtype=float)

        chart, _ = individual_moving_range_chart(values)

        expected_center = values.mean()
        expected_half_width = E2_INDIVIDUAL * 1.0  # MR 이 모두 1.0

        assert chart.center_line == pytest.approx(expected_center)
        assert chart.upper_limit == pytest.approx(
            expected_center + expected_half_width
        )

        # 전체 표준편차로 계산했다면 한계 폭이 훨씬 넓어진다.
        overall_half_width = 3 * values.std(ddof=1)

        assert expected_half_width < overall_half_width / 10

    def test_hand_computed_example(self):
        values = [10.0, 12.0, 11.0, 13.0, 12.0]

        chart, moving_range_chart = individual_moving_range_chart(
            values
        )

        mean_value = np.mean(values)
        moving_ranges = [2.0, 1.0, 2.0, 1.0]
        mean_moving_range = np.mean(moving_ranges)

        assert chart.center_line == pytest.approx(mean_value)
        assert chart.upper_limit == pytest.approx(
            mean_value + E2_INDIVIDUAL * mean_moving_range
        )
        assert chart.lower_limit == pytest.approx(
            mean_value - E2_INDIVIDUAL * mean_moving_range
        )
        assert chart.sigma_within == pytest.approx(
            mean_moving_range / 1.128
        )

        assert moving_range_chart.center_line == pytest.approx(
            mean_moving_range
        )
        assert moving_range_chart.lower_limit == pytest.approx(0.0)
        assert moving_range_chart.upper_limit == pytest.approx(
            3.267 * mean_moving_range
        )

    def test_chart_sigma_is_one_third_of_limit_width(self):
        rng = np.random.default_rng(3)
        chart, _ = individual_moving_range_chart(
            rng.normal(0, 1, 200)
        )

        assert chart.chart_sigma == pytest.approx(
            (chart.upper_limit - chart.center_line) / 3.0
        )

    def test_sigma_zone_edges_are_ordered(self):
        rng = np.random.default_rng(4)
        chart, _ = individual_moving_range_chart(
            rng.normal(100, 5, 300)
        )

        zones = chart.sigma_zone_edges
        ordered = [
            zones["minus_3"],
            zones["minus_2"],
            zones["minus_1"],
            zones["center"],
            zones["plus_1"],
            zones["plus_2"],
            zones["plus_3"],
        ]

        assert ordered == sorted(ordered)

    def test_points_beyond_limits_detects_outlier(self):
        values = [10.0] * 30 + [100.0] + [10.0] * 30

        chart, _ = individual_moving_range_chart(values)
        beyond = chart.points_beyond_limits()

        assert 30 in beyond.tolist()


class TestXbarRChart:
    def test_hand_computed_example(self):
        frame = pd.DataFrame(
            {
                "Subgroup": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
                "Value": [
                    10.0, 12.0, 11.0,
                    13.0, 14.0, 12.0,
                    11.0, 11.0, 14.0,
                ],
            }
        )

        xbar, range_chart = xbar_r_chart(
            dataframe=frame,
            value_column="Value",
            subgroup_column="Subgroup",
        )

        subgroup_means = [11.0, 13.0, 12.0]
        subgroup_ranges = [2.0, 2.0, 3.0]

        grand_mean = np.mean(subgroup_means)
        mean_range = np.mean(subgroup_ranges)
        a2 = get_a2(3)

        assert xbar.center_line == pytest.approx(grand_mean)
        assert xbar.upper_limit == pytest.approx(
            grand_mean + a2 * mean_range
        )
        assert xbar.sigma_within == pytest.approx(
            mean_range / get_d2(3)
        )

        d3, d4 = get_range_limit_factors(3)

        assert range_chart.upper_limit == pytest.approx(
            d4 * mean_range
        )
        assert range_chart.lower_limit == pytest.approx(
            d3 * mean_range
        )

    def test_labels_are_preserved(self):
        frame = pd.DataFrame(
            {
                "Subgroup": ["M1", "M1", "M2", "M2"],
                "Value": [1.0, 2.0, 3.0, 4.0],
            }
        )

        xbar, _ = xbar_r_chart(frame, "Value", "Subgroup")

        assert xbar.labels == ["M1", "M2"]

    def test_rejects_unbalanced_subgroups(self):
        frame = pd.DataFrame(
            {
                "Subgroup": ["A", "A", "A", "B", "B"],
                "Value": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        )

        with pytest.raises(ValueError, match="부분군 크기가 모두 같아야"):
            xbar_r_chart(frame, "Value", "Subgroup")

    def test_rejects_subgroup_size_one(self):
        frame = pd.DataFrame(
            {
                "Subgroup": ["A", "B", "C"],
                "Value": [1.0, 2.0, 3.0],
            }
        )

        with pytest.raises(ValueError, match="부분군 크기가 1"):
            xbar_r_chart(frame, "Value", "Subgroup")


class TestSigmaEstimators:
    def test_within_and_overall_agree_for_random_data(self):
        """무작위 데이터에서는 두 추정값이 비슷해야 한다."""
        rng = np.random.default_rng(5)
        values = rng.normal(50.0, 3.0, 4000)

        within = estimate_sigma_within(values)
        overall = estimate_sigma_overall(values)

        assert within == pytest.approx(overall, rel=0.05)
        assert within == pytest.approx(3.0, rel=0.05)

    def test_within_is_much_smaller_when_trend_exists(self):
        """추세가 있으면 전체 시그마만 커진다.

        Cp(단기)와 Pp(장기)의 차이가 생기는 원리다.
        """
        values = np.arange(500, dtype=float) + np.random.default_rng(
            6
        ).normal(0.0, 1.0, 500)

        within = estimate_sigma_within(values)
        overall = estimate_sigma_overall(values)

        assert within < overall / 50


class TestPChart:
    def test_center_line_is_pooled_proportion(self):
        counts = [5, 10, 15]
        sizes = [100, 100, 100]

        chart = p_chart(counts, sizes)

        assert chart.center_line == pytest.approx(30 / 300)

    def test_limits_use_binomial_standard_error(self):
        counts = [10, 10, 10, 10]
        sizes = [100, 100, 100, 100]

        chart = p_chart(counts, sizes)

        center = 0.1
        standard_error = np.sqrt(center * (1 - center) / 100)

        assert chart.upper_limit == pytest.approx(
            center + 3 * standard_error
        )
        assert chart.lower_limit == pytest.approx(
            max(center - 3 * standard_error, 0.0)
        )

    def test_limits_are_clipped_to_unit_interval(self):
        counts = [1, 0, 2]
        sizes = [10, 10, 10]

        chart = p_chart(counts, sizes)

        assert chart.lower_limit >= 0.0
        assert chart.upper_limit <= 1.0

    def test_variable_limits_change_with_subgroup_size(self):
        chart = p_chart([10, 5], [100, 25])

        assert chart.variable_upper_limits is not None
        # 부분군이 작을수록 한계가 넓어진다.
        assert (
            chart.variable_upper_limits[1]
            > chart.variable_upper_limits[0]
        )

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError, match="길이가 같아야"):
            p_chart([1, 2, 3], [100, 100])

    def test_rejects_non_positive_subgroup_size(self):
        with pytest.raises(ValueError, match="1 이상"):
            p_chart([1, 2], [100, 0])


class TestDefectRateSubgroups:
    def test_counts_and_sizes(self):
        frame = pd.DataFrame(
            {
                "Defect": (
                    ["Delamination"] * 3
                    + ["Normal"] * 7
                    + ["Delamination"] * 1
                    + ["Normal"] * 9
                )
            }
        )

        counts, sizes = build_defect_rate_subgroups(
            dataframe=frame,
            subgroup_size=10,
        )

        np.testing.assert_allclose(counts, [3.0, 1.0])
        np.testing.assert_allclose(sizes, [10.0, 10.0])

    def test_drops_incomplete_trailing_subgroup(self):
        frame = pd.DataFrame({"Defect": ["Normal"] * 25})

        counts, sizes = build_defect_rate_subgroups(
            dataframe=frame,
            subgroup_size=10,
        )

        assert counts.size == 2

    def test_requires_two_subgroups(self):
        frame = pd.DataFrame({"Defect": ["Normal"] * 15})

        with pytest.raises(ValueError, match="2개 이상"):
            build_defect_rate_subgroups(
                dataframe=frame,
                subgroup_size=10,
            )
