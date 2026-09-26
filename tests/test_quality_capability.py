"""공정능력 분석 검증.

검증 전략
---------
Cp, Cpk, Pp, Ppk 는 정의가 명확한 공식이므로 손으로 계산한 값과 대조한다.
특히 다음 두 가지를 확인한다.

1. Cp/Cpk 는 부분군 내 변동(sigma_within), Pp/Ppk 는 전체 변동을 쓴다.
   같은 시그마를 쓰면 네 지표가 항상 같아져 비교 의미가 사라진다.
2. 한쪽 규격만 있으면 Cp 는 정의되지 않고(None) Cpk 만 계산된다.
"""

import numpy as np
import pandas as pd
import pytest

from src.quality.capability import (
    analyze_capability,
    analyze_capability_table,
)


def _controlled_series(
    mean: float,
    sigma: float,
    size: int = 3000,
    seed: int = 77,
) -> np.ndarray:
    """평균과 표준편차를 정확히 맞춘 표본을 만든다.

    난수 표본을 표준화한 뒤 다시 스케일링해, 표본평균과 표본표준편차가
    지정한 값과 정확히 일치하게 한다. 손 계산과 대조하기 위한 장치다.
    """
    rng = np.random.default_rng(seed)
    raw = rng.normal(0.0, 1.0, size)

    standardized = (raw - raw.mean()) / raw.std(ddof=1)

    return mean + sigma * standardized


class TestTwoSidedSpecification:
    def test_centered_process_cp_equals_cpk(self):
        values = _controlled_series(mean=100.0, sigma=1.0)

        result = analyze_capability(
            series=values,
            characteristic="Test",
            lower_spec=94.0,
            upper_spec=106.0,
        )

        assert result.cp == pytest.approx(result.cpk, rel=1e-6)
        assert result.centering_gap == pytest.approx(0.0, abs=1e-6)

    def test_pp_matches_hand_calculation(self):
        """Pp = (USL - LSL) / (6 * sigma_overall)"""
        values = _controlled_series(mean=100.0, sigma=1.0)

        result = analyze_capability(
            series=values,
            characteristic="Test",
            lower_spec=94.0,
            upper_spec=106.0,
        )

        assert result.sigma_overall == pytest.approx(1.0, rel=1e-9)
        assert result.pp == pytest.approx(12.0 / 6.0, rel=1e-6)
        assert result.pp == pytest.approx(2.0, rel=1e-6)

    def test_offset_process_cpk_is_lower_than_cp(self):
        """평균이 규격 중심에서 벗어나면 Cpk < Cp 가 된다."""
        values = _controlled_series(mean=103.0, sigma=1.0)

        result = analyze_capability(
            series=values,
            characteristic="Test",
            lower_spec=94.0,
            upper_spec=106.0,
        )

        assert result.cpk < result.cp
        assert result.centering_gap > 0.5

        # 상한 쪽이 가까우므로 Cpu 가 최소값이 된다.
        assert result.cpk == pytest.approx(result.cpu, rel=1e-9)
        assert result.cpu < result.cpl

    def test_ppk_uses_overall_sigma(self):
        values = _controlled_series(mean=103.0, sigma=1.0)

        result = analyze_capability(
            series=values,
            characteristic="Test",
            lower_spec=94.0,
            upper_spec=106.0,
        )

        expected_ppk = min(
            (106.0 - 103.0) / (3 * result.sigma_overall),
            (103.0 - 94.0) / (3 * result.sigma_overall),
        )

        assert result.ppk == pytest.approx(expected_ppk, rel=1e-6)

    def test_diagnosis_mentions_centering_when_offset(self):
        values = _controlled_series(mean=103.0, sigma=1.0)

        result = analyze_capability(
            series=values,
            characteristic="Test",
            lower_spec=94.0,
            upper_spec=106.0,
        )

        assert "중심" in result.diagnosis


class TestWithinVersusOverallSigma:
    def test_trend_makes_cp_much_larger_than_pp(self):
        """추세가 있으면 단기 능력은 좋고 장기 성능은 나쁘다.

        Cp 와 Pp 의 차이가 부분군 간 변동을 드러낸다.
        이 구분이 없으면 '산포를 줄여라'는 잘못된 처방이 나온다.
        """
        rng = np.random.default_rng(5)

        # 느린 드리프트 + 작은 단기 산포
        drift = np.linspace(-3.0, 3.0, 1000)
        values = 100.0 + drift + rng.normal(0.0, 0.2, 1000)

        result = analyze_capability(
            series=values,
            characteristic="Drifting",
            lower_spec=90.0,
            upper_spec=110.0,
        )

        assert result.sigma_within < result.sigma_overall / 3
        assert result.cp > result.pp * 3
        assert result.between_subgroup_gap > 0.30
        assert "부분군 간" in result.diagnosis

    def test_random_data_has_similar_cp_and_pp(self):
        values = _controlled_series(mean=50.0, sigma=2.0, size=4000)

        result = analyze_capability(
            series=values,
            characteristic="Stable",
            lower_spec=38.0,
            upper_spec=62.0,
        )

        assert result.cp == pytest.approx(result.pp, rel=0.10)


class TestOneSidedSpecification:
    def test_lower_only_leaves_cp_undefined(self):
        values = _controlled_series(mean=500.0, sigma=20.0)

        result = analyze_capability(
            series=values,
            characteristic="Peel",
            lower_spec=400.0,
            upper_spec=None,
        )

        assert result.cp is None
        assert result.pp is None
        assert result.cpk is not None
        assert result.cpl is not None
        assert result.cpu is None
        assert result.centering_gap is None

    def test_lower_only_cpk_matches_hand_calculation(self):
        values = _controlled_series(mean=500.0, sigma=20.0)

        result = analyze_capability(
            series=values,
            characteristic="Peel",
            lower_spec=400.0,
            upper_spec=None,
        )

        expected = (500.0 - 400.0) / (3 * result.sigma_within)

        assert result.cpk == pytest.approx(expected, rel=1e-6)

    def test_upper_only(self):
        values = _controlled_series(mean=10.0, sigma=1.0)

        result = analyze_capability(
            series=values,
            characteristic="Particle",
            lower_spec=None,
            upper_spec=16.0,
        )

        assert result.cp is None
        assert result.cpl is None
        assert result.cpu is not None
        assert result.cpk == pytest.approx(result.cpu, rel=1e-9)

    def test_requires_at_least_one_limit(self):
        with pytest.raises(ValueError, match="규격 상한 또는 하한"):
            analyze_capability(
                series=[1.0, 2.0, 3.0],
                characteristic="NoSpec",
                lower_spec=None,
                upper_spec=None,
            )


class TestVerdict:
    def test_verdict_thresholds(self):
        cases = [
            (1.80, "우수"),
            (1.45, "양호"),
            (1.10, "개선 필요"),
            (0.80, "부적합"),
        ]

        for target_cpk, expected_verdict in cases:
            # Cpk = (USL - mean) / (3 * sigma) 가 되도록 규격을 역산
            sigma = 1.0
            half_width = 3 * sigma * target_cpk

            values = _controlled_series(mean=0.0, sigma=sigma)

            result = analyze_capability(
                series=values,
                characteristic="Test",
                lower_spec=-half_width,
                upper_spec=half_width,
            )

            assert result.verdict == expected_verdict, (
                f"Cpk {result.cpk:.3f} -> {result.verdict}, "
                f"기대 {expected_verdict}"
            )


class TestOutOfSpecEstimates:
    def test_observed_count_matches_manual_count(self):
        values = np.array(
            [1.0] * 10 + [50.0] * 5 + [99.0] * 3,
            dtype=float,
        )

        result = analyze_capability(
            series=values,
            characteristic="Test",
            lower_spec=10.0,
            upper_spec=90.0,
        )

        assert result.observed_out_of_spec_count == 13

    def test_expected_ppm_is_small_for_capable_process(self):
        values = _controlled_series(mean=100.0, sigma=1.0)

        result = analyze_capability(
            series=values,
            characteristic="Test",
            lower_spec=94.0,
            upper_spec=106.0,
        )

        # Cpk 2.0 -> 양측 합계가 ppb 수준
        assert result.expected_ppm_out_of_spec < 1.0

    def test_expected_ppm_is_large_for_incapable_process(self):
        values = _controlled_series(mean=100.0, sigma=4.0)

        result = analyze_capability(
            series=values,
            characteristic="Test",
            lower_spec=96.0,
            upper_spec=104.0,
        )

        assert result.expected_ppm_out_of_spec > 100_000


class TestNormality:
    def test_normal_data_is_not_rejected(self):
        values = _controlled_series(mean=0.0, sigma=1.0, size=500)

        result = analyze_capability(
            series=values,
            characteristic="Test",
            lower_spec=-5.0,
            upper_spec=5.0,
        )

        assert result.normality_p_value is not None
        assert result.normality_p_value > 0.05

    def test_bimodal_data_is_rejected_and_flagged(self):
        rng = np.random.default_rng(3)

        values = np.concatenate(
            [
                rng.normal(-5.0, 0.5, 400),
                rng.normal(5.0, 0.5, 400),
            ]
        )

        result = analyze_capability(
            series=values,
            characteristic="Bimodal",
            lower_spec=-20.0,
            upper_spec=20.0,
        )

        assert result.normality_p_value < 0.05
        assert "정규성" in result.diagnosis

    def test_tiny_sample_returns_none(self):
        result = analyze_capability(
            series=[1.0, 2.0, 3.0],
            characteristic="Tiny",
            lower_spec=0.0,
            upper_spec=5.0,
        )

        assert result.normality_p_value is None


class TestCapabilityTable:
    def test_builds_row_per_characteristic(self):
        frame = pd.DataFrame(
            {
                "A": _controlled_series(100.0, 1.0, size=200),
                "B": _controlled_series(50.0, 2.0, size=200),
            }
        )

        table = analyze_capability_table(
            dataframe=frame,
            specifications={
                "A": {"lsl": 94.0, "usl": 106.0, "target": 100.0},
                "B": {"lsl": 40.0, "usl": 60.0, "target": 50.0},
            },
        )

        assert len(table) == 2
        assert set(table["characteristic"]) == {"A", "B"}

    def test_skips_characteristics_without_specification(self):
        frame = pd.DataFrame(
            {"A": _controlled_series(100.0, 1.0, size=200)}
        )

        table = analyze_capability_table(
            dataframe=frame,
            specifications={
                "A": {"lsl": None, "usl": None, "target": 100.0}
            },
        )

        assert table.empty

    def test_skips_missing_columns(self):
        frame = pd.DataFrame(
            {"A": _controlled_series(100.0, 1.0, size=200)}
        )

        table = analyze_capability_table(
            dataframe=frame,
            specifications={
                "A": {"lsl": 94.0, "usl": 106.0, "target": 100.0},
                "Absent": {"lsl": 0.0, "usl": 1.0, "target": 0.5},
            },
        )

        assert len(table) == 1

    def test_table_contains_diagnosis_column(self):
        frame = pd.DataFrame(
            {"A": _controlled_series(100.0, 1.0, size=200)}
        )

        table = analyze_capability_table(
            dataframe=frame,
            specifications={
                "A": {"lsl": 94.0, "usl": 106.0, "target": 100.0}
            },
        )

        assert "diagnosis" in table.columns
        assert "verdict" in table.columns
