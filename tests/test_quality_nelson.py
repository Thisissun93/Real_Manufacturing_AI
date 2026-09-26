"""Nelson 판정 규칙 검증.

검증 전략
---------
1. 각 규칙마다 '반드시 걸려야 하는 데이터'와 '걸리면 안 되는 데이터'를
   직접 만들어 확인한다. 규칙 정의를 코드가 정확히 구현했는지 본다.
2. 관리상태 정규 데이터에서의 오경보율을 몬테카를로로 확인해,
   IN_CONTROL_ALARM_PROBABILITY 상수가 실제 구현과 맞는지 검증한다.
   규칙 1 의 이론값 0.0027 과 실측값이 일치하면 시뮬레이션 자체가 검증된다.
"""

import numpy as np
import pytest

from src.quality.control_charts import individual_moving_range_chart
from src.quality.nelson_rules import (
    IN_CONTROL_ALARM_PROBABILITY,
    RULE_DESCRIPTIONS,
    RULE_FUNCTIONS,
    RULE_SEVERITY,
    evaluate_all_rules,
    evaluate_chart,
    expected_false_alarms,
    rule_1_beyond_three_sigma,
    rule_2_nine_on_one_side,
    rule_3_six_trending,
    rule_4_fourteen_alternating,
    rule_5_two_of_three_beyond_two_sigma,
    rule_6_four_of_five_beyond_one_sigma,
    rule_7_fifteen_within_one_sigma,
    rule_8_eight_beyond_one_sigma,
    summarize_violations,
)


CENTER = 0.0
SIGMA = 1.0


def _quiet(length: int, value: float = 0.5) -> list[float]:
    """규칙에 걸리지 않도록 중심선 양쪽을 번갈아 채운다.

    부호를 번갈아 두면 규칙 2(한쪽 연속)를 피할 수 있고,
    크기를 1 시그마 안에 두면 규칙 1, 5, 6, 8 을 피할 수 있다.
    규칙 7(15점 연속 1시그마 안)을 피하려고 길이는 짧게 쓴다.
    """
    return [value if index % 2 == 0 else -value for index in range(length)]


class TestRuleDefinitions:
    def test_all_eight_rules_registered(self):
        assert sorted(RULE_FUNCTIONS) == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_every_rule_has_description_and_severity(self):
        for rule_number in RULE_FUNCTIONS:
            assert rule_number in RULE_DESCRIPTIONS
            assert rule_number in RULE_SEVERITY
            assert RULE_SEVERITY[rule_number] in {
                "WATCH",
                "WARNING",
                "CRITICAL",
            }

    def test_rule_one_is_critical(self):
        assert RULE_SEVERITY[1] == "CRITICAL"


class TestRule1:
    def test_detects_point_beyond_three_sigma(self):
        values = np.array(_quiet(10) + [3.5] + _quiet(10))

        violations = rule_1_beyond_three_sigma(values, CENTER, SIGMA)

        assert len(violations) == 1
        assert violations[0].start_index == 10
        assert violations[0].end_index == 10

    def test_detects_negative_side(self):
        values = np.array([0.0, -4.0, 0.0])

        violations = rule_1_beyond_three_sigma(values, CENTER, SIGMA)

        assert len(violations) == 1

    def test_exactly_three_sigma_is_not_a_violation(self):
        values = np.array([0.0, 3.0, 0.0])

        assert rule_1_beyond_three_sigma(values, CENTER, SIGMA) == []

    def test_no_violation_within_limits(self):
        values = np.array(_quiet(12, 2.5))

        assert rule_1_beyond_three_sigma(values, CENTER, SIGMA) == []


class TestRule2:
    def test_detects_nine_consecutive_above_center(self):
        values = np.array([0.5] * 9)

        violations = rule_2_nine_on_one_side(values, CENTER, SIGMA)

        assert len(violations) == 1
        assert violations[0].start_index == 0
        assert violations[0].end_index == 8

    def test_detects_nine_consecutive_below_center(self):
        values = np.array([-0.5] * 9)

        assert len(rule_2_nine_on_one_side(values, CENTER, SIGMA)) == 1

    def test_eight_consecutive_is_not_enough(self):
        values = np.array([0.5] * 8 + [-0.5])

        assert rule_2_nine_on_one_side(values, CENTER, SIGMA) == []

    def test_long_run_reported_once_not_many_times(self):
        """20점 연속이면 겹치는 창 12개가 아니라 1건으로 보고한다."""
        values = np.array([0.5] * 20)

        violations = rule_2_nine_on_one_side(values, CENTER, SIGMA)

        assert len(violations) == 1
        assert violations[0].length == 20

    def test_alternating_signs_do_not_trigger(self):
        values = np.array(_quiet(30))

        assert rule_2_nine_on_one_side(values, CENTER, SIGMA) == []


class TestRule3:
    def test_detects_six_increasing(self):
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

        violations = rule_3_six_trending(values, CENTER, SIGMA)

        assert len(violations) == 1
        assert violations[0].start_index == 0
        assert violations[0].end_index == 5

    def test_detects_six_decreasing(self):
        values = np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0])

        assert len(rule_3_six_trending(values, CENTER, SIGMA)) == 1

    def test_five_increasing_is_not_enough(self):
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        assert rule_3_six_trending(values, CENTER, SIGMA) == []

    def test_plateau_breaks_the_trend(self):
        values = np.array([1.0, 2.0, 3.0, 3.0, 4.0, 5.0, 6.0])

        assert rule_3_six_trending(values, CENTER, SIGMA) == []

    def test_long_trend_merged_into_one_violation(self):
        values = np.arange(20, dtype=float)

        violations = rule_3_six_trending(values, CENTER, SIGMA)

        assert len(violations) == 1
        assert violations[0].start_index == 0
        assert violations[0].end_index == 19


class TestRule4:
    def test_detects_fourteen_alternating(self):
        values = np.array(
            [1.0 if index % 2 == 0 else -1.0 for index in range(14)]
        )

        violations = rule_4_fourteen_alternating(
            values, CENTER, SIGMA
        )

        assert len(violations) == 1
        assert violations[0].length == 14

    def test_thirteen_alternating_is_not_enough(self):
        values = np.array(
            [1.0 if index % 2 == 0 else -1.0 for index in range(13)]
        )

        assert (
            rule_4_fourteen_alternating(values, CENTER, SIGMA) == []
        )

    def test_monotone_data_does_not_trigger(self):
        values = np.arange(40, dtype=float)

        assert (
            rule_4_fourteen_alternating(values, CENTER, SIGMA) == []
        )

    def test_repeated_value_breaks_alternation(self):
        """같은 값이 연속되면 차분이 0 이 되어 교대가 끊긴다.

        중간에 값이 반복되는 8번째 지점에서 패턴이 끊기므로,
        가장 긴 교대 구간이 14점에 미치지 못한다.
        """
        first_half = [
            1.0 if index % 2 == 0 else -1.0 for index in range(7)
        ]
        second_half = [
            1.0 if index % 2 == 0 else -1.0 for index in range(8)
        ]

        # first_half 의 마지막이 1.0, second_half 의 처음도 1.0 이므로
        # 이어붙이면 차분이 0 인 지점이 생긴다.
        values = np.array(first_half + second_half)

        assert first_half[-1] == second_half[0]
        assert (
            rule_4_fourteen_alternating(values, CENTER, SIGMA) == []
        )


class TestRule5:
    def test_detects_two_of_three_beyond_two_sigma(self):
        values = np.array([2.5, 0.1, 2.4])

        violations = rule_5_two_of_three_beyond_two_sigma(
            values, CENTER, SIGMA
        )

        assert len(violations) == 1

    def test_requires_same_side(self):
        values = np.array([2.5, 0.1, -2.4])

        assert (
            rule_5_two_of_three_beyond_two_sigma(
                values, CENTER, SIGMA
            )
            == []
        )

    def test_one_of_three_is_not_enough(self):
        values = np.array([2.5, 0.1, 0.2, 0.3])

        assert (
            rule_5_two_of_three_beyond_two_sigma(
                values, CENTER, SIGMA
            )
            == []
        )


class TestRule6:
    def test_detects_four_of_five_beyond_one_sigma(self):
        values = np.array([1.2, 1.3, 0.1, 1.4, 1.5])

        violations = rule_6_four_of_five_beyond_one_sigma(
            values, CENTER, SIGMA
        )

        assert len(violations) == 1

    def test_requires_same_side(self):
        values = np.array([1.2, 1.3, -1.4, 1.5, 0.1])

        assert (
            rule_6_four_of_five_beyond_one_sigma(
                values, CENTER, SIGMA
            )
            == []
        )

    def test_three_of_five_is_not_enough(self):
        values = np.array([1.2, 1.3, 0.1, 1.4, 0.2])

        assert (
            rule_6_four_of_five_beyond_one_sigma(
                values, CENTER, SIGMA
            )
            == []
        )


class TestRule7:
    def test_detects_fifteen_within_one_sigma(self):
        values = np.array(_quiet(15, 0.3))

        violations = rule_7_fifteen_within_one_sigma(
            values, CENTER, SIGMA
        )

        assert len(violations) == 1
        assert violations[0].length == 15

    def test_fourteen_is_not_enough(self):
        values = np.array(_quiet(14, 0.3) + [2.0])

        assert (
            rule_7_fifteen_within_one_sigma(values, CENTER, SIGMA)
            == []
        )

    def test_one_excursion_breaks_the_run(self):
        values = np.array(
            _quiet(8, 0.3) + [1.5] + _quiet(8, 0.3)
        )

        assert (
            rule_7_fifteen_within_one_sigma(values, CENTER, SIGMA)
            == []
        )


class TestRule8:
    def test_detects_eight_beyond_one_sigma_both_sides(self):
        values = np.array([1.5, -1.5, 1.6, -1.6, 1.7, -1.7, 1.8, -1.8])

        violations = rule_8_eight_beyond_one_sigma(
            values, CENTER, SIGMA
        )

        assert len(violations) == 1
        assert violations[0].length == 8

    def test_seven_is_not_enough(self):
        values = np.array([1.5, -1.5, 1.6, -1.6, 1.7, -1.7, 1.8])

        assert (
            rule_8_eight_beyond_one_sigma(values, CENTER, SIGMA) == []
        )

    def test_central_point_breaks_the_run(self):
        values = np.array(
            [1.5, -1.5, 1.6, 0.2, 1.7, -1.7, 1.8, -1.8]
        )

        assert (
            rule_8_eight_beyond_one_sigma(values, CENTER, SIGMA) == []
        )


class TestEvaluateAllRules:
    def test_applies_every_rule_by_default(self):
        rng = np.random.default_rng(42)
        values = rng.normal(0.0, 1.0, 2000)

        violations = evaluate_all_rules(values, CENTER, SIGMA)
        found_rules = {item.rule_number for item in violations}

        # 2000점이면 여러 규칙이 우연히 발동한다.
        assert len(found_rules) >= 5

    def test_rule_subset_is_respected(self):
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 9.0])

        violations = evaluate_all_rules(
            values, CENTER, SIGMA, rules=[3]
        )

        assert all(item.rule_number == 3 for item in violations)

    def test_results_sorted_by_start_index(self):
        rng = np.random.default_rng(1)
        values = rng.normal(0.0, 1.0, 500)

        violations = evaluate_all_rules(values, CENTER, SIGMA)
        indices = [item.start_index for item in violations]

        assert indices == sorted(indices)

    def test_rejects_unknown_rule(self):
        with pytest.raises(ValueError, match="정의되지 않은"):
            evaluate_all_rules(
                np.zeros(10), CENTER, SIGMA, rules=[99]
            )

    def test_evaluate_chart_uses_chart_geometry(self):
        values = [10.0] * 30 + [40.0] + [10.0] * 30
        chart, _ = individual_moving_range_chart(values)

        violations = evaluate_chart(chart, rules=[1])

        assert any(item.start_index == 30 for item in violations)


class TestExpectedFalseAlarms:
    def test_scales_linearly_with_point_count(self):
        small = expected_false_alarms(1000)
        large = expected_false_alarms(2000)

        for key in small:
            assert large[key] == pytest.approx(2 * small[key])

    def test_covers_all_rules(self):
        expected = expected_false_alarms(1000)

        assert len(expected) == 8

    def test_rule_one_matches_normal_theory(self):
        """규칙 1 의 상수가 P(|z| > 3) = 0.0027 과 일치해야 한다.

        이 값이 맞으면 나머지 상수를 구한 시뮬레이션도 신뢰할 수 있다.
        """
        assert IN_CONTROL_ALARM_PROBABILITY[1] == pytest.approx(
            0.0027, abs=0.0002
        )

    def test_monte_carlo_matches_stored_constants(self):
        """저장된 오경보 상수가 실제 구현과 일치하는지 확인한다.

        관리상태 표준정규 데이터로 각 규칙의 발동 빈도를 측정한다.
        상수는 4,000점 x 250회로 구했고, 여기서는 실행시간을 위해
        더 작은 표본을 쓰므로 허용 오차를 넓게 둔다.
        """
        rng = np.random.default_rng(2026)

        point_count = 3000
        replications = 12

        totals = {rule: 0 for rule in RULE_FUNCTIONS}

        for _ in range(replications):
            values = rng.normal(0.0, 1.0, point_count)

            for rule, function in RULE_FUNCTIONS.items():
                totals[rule] += len(function(values, 0.0, 1.0))

        denominator = point_count * replications

        for rule, total in totals.items():
            observed = total / denominator
            stored = IN_CONTROL_ALARM_PROBABILITY[rule]

            # 희소한 규칙(8번)은 표본이 작으면 변동이 크다.
            tolerance = max(0.4 * stored, 3.0 / denominator)

            assert observed == pytest.approx(stored, abs=tolerance), (
                f"규칙 {rule}: 실측 {observed:.6f} vs 상수 {stored:.6f}"
            )


class TestSummarizeViolations:
    def test_counts_by_rule(self):
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        violations = evaluate_all_rules(
            values, CENTER, SIGMA, rules=[3]
        )

        summary = summarize_violations(violations)

        assert summary["total_violations"] == 1
        assert summary["by_rule"]["NELSON_RULE_3"] == 1

    def test_without_point_count_escalates_on_any_violation(self):
        values = np.array([0.0, 5.0, 0.0])
        violations = evaluate_all_rules(
            values, CENTER, SIGMA, rules=[1]
        )

        summary = summarize_violations(violations)

        assert summary["overall_severity"] == "CRITICAL"

    def test_with_point_count_chance_level_is_normal(self):
        """우연 수준의 위반은 NORMAL 로 분류되어야 한다."""
        rng = np.random.default_rng(9)
        values = rng.normal(0.0, 1.0, 4000)

        violations = evaluate_all_rules(values, CENTER, SIGMA)

        summary = summarize_violations(
            violations,
            point_count=values.size,
        )

        assert summary["total_violations"] > 0
        assert summary["overall_severity"] == "NORMAL"
        assert summary["signal_rules"] == {}

    def test_with_point_count_real_signal_is_flagged(self):
        """실제 이상은 기대 오경보를 크게 초과해야 한다."""
        rng = np.random.default_rng(10)

        # 후반부에 평균이 이동한 데이터
        values = np.concatenate(
            [
                rng.normal(0.0, 1.0, 1000),
                rng.normal(1.6, 1.0, 1000),
            ]
        )

        violations = evaluate_all_rules(values, CENTER, SIGMA)

        summary = summarize_violations(
            violations,
            point_count=values.size,
        )

        assert summary["overall_severity"] in {
            "WARNING",
            "CRITICAL",
        }
        assert summary["signal_rules"]

    def test_signal_rules_report_ratio(self):
        rng = np.random.default_rng(12)
        values = np.concatenate(
            [
                rng.normal(0.0, 1.0, 500),
                rng.normal(2.2, 1.0, 500),
            ]
        )

        summary = summarize_violations(
            evaluate_all_rules(values, CENTER, SIGMA),
            point_count=values.size,
        )

        for statistics in summary["signal_rules"].values():
            assert statistics["ratio"] >= 2.0
            assert statistics["observed"] > statistics["expected"]


class TestRuleViolation:
    def test_length_and_dict_conversion(self):
        values = np.array([0.5] * 12)
        violation = rule_2_nine_on_one_side(values, CENTER, SIGMA)[0]

        assert violation.length == 12

        payload = violation.to_dict()

        assert payload["rule_name"] == "NELSON_RULE_2"
        assert payload["point_count"] == 12
        assert "interpretation" in payload
        assert payload["severity"] == RULE_SEVERITY[2]
