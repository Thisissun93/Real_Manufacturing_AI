"""관리도 산출 모듈.

관리한계(Control Limit)와 규격한계(Specification Limit)를 구분한다.

- 규격한계(LSL/USL)는 설계와 고객이 정한 값이다. 데이터로부터 계산되지 않는다.
- 관리한계(LCL/UCL)는 공정 자체의 변동으로부터 추정한 값이다.

관리한계를 전체 표준편차(overall sigma)로 계산하면 부분군 간 변동까지
한계 폭에 포함되어 한계가 넓어지고, 정작 검출해야 할 이상을 감춘다.
따라서 관리한계는 부분군 내 변동(within-subgroup variation)으로 추정한다.

- I-MR 관리도: sigma_hat = MR_bar / d2(2)
- X-bar-R 관리도: sigma_hat = R_bar / d2(n)
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.quality.constants import (
    E2_INDIVIDUAL,
    MOVING_RANGE_SUBGROUP_SIZE,
    get_a2,
    get_d2,
    get_range_limit_factors,
)


@dataclass
class ControlChart:
    """관리도 계산 결과.

    Attributes
    ----------
    chart_type : 관리도 종류. "I", "MR", "X-bar", "R"
    values : 관리도에 타점되는 값
    center_line : 중심선
    lower_limit : 관리하한
    upper_limit : 관리상한
    sigma_within : 부분군 내 변동으로 추정한 표준편차
    subgroup_size : 부분군 크기
    """

    chart_type: str
    values: np.ndarray
    center_line: float
    lower_limit: float
    upper_limit: float
    sigma_within: float
    subgroup_size: int
    labels: list[str] = field(default_factory=list)

    # p 관리도처럼 부분군 크기가 달라 타점마다 한계선이 변하는 경우에만 채운다.
    variable_lower_limits: np.ndarray | None = None
    variable_upper_limits: np.ndarray | None = None

    @property
    def sigma_zone_edges(self) -> dict[str, float]:
        """1/2/3 시그마 구역 경계를 반환한다.

        Nelson 판정 규칙은 이 구역 경계를 기준으로 판정한다.
        관리도의 시그마는 (UCL - CL) / 3 으로 정의된다.
        """
        one_sigma = (self.upper_limit - self.center_line) / 3.0

        return {
            "minus_3": self.center_line - 3 * one_sigma,
            "minus_2": self.center_line - 2 * one_sigma,
            "minus_1": self.center_line - one_sigma,
            "center": self.center_line,
            "plus_1": self.center_line + one_sigma,
            "plus_2": self.center_line + 2 * one_sigma,
            "plus_3": self.center_line + 3 * one_sigma,
        }

    @property
    def chart_sigma(self) -> float:
        """관리도 1 시그마 폭."""
        return (self.upper_limit - self.center_line) / 3.0

    def points_beyond_limits(self) -> np.ndarray:
        """관리한계를 벗어난 타점의 인덱스."""
        beyond = (self.values < self.lower_limit) | (
            self.values > self.upper_limit
        )

        return np.flatnonzero(beyond)


def _as_clean_array(series: pd.Series | np.ndarray) -> np.ndarray:
    """결측을 제거한 1차원 float 배열로 변환한다."""
    values = pd.Series(series).dropna().to_numpy(dtype=float)

    if values.size < 2:
        raise ValueError(
            "관리도를 계산하려면 결측을 제외한 값이 2개 이상 필요합니다."
        )

    return values


def calculate_moving_ranges(
    series: pd.Series | np.ndarray,
) -> np.ndarray:
    """연속한 두 관측값의 이동범위를 계산한다."""
    values = _as_clean_array(series)

    return np.abs(np.diff(values))


def individual_moving_range_chart(
    series: pd.Series | np.ndarray,
) -> tuple[ControlChart, ControlChart]:
    """I-MR 관리도를 계산한다.

    LOT 단위로 한 개의 측정값만 얻는 공정에 사용한다.
    이 리포지토리의 품질 특성(Peel Strength, 두께 등)이 이 경우에 해당한다.

    Returns
    -------
    (I 관리도, MR 관리도)
    """
    values = _as_clean_array(series)
    moving_ranges = np.abs(np.diff(values))

    mean_value = float(values.mean())
    mean_moving_range = float(moving_ranges.mean())

    sigma_within = mean_moving_range / get_d2(
        MOVING_RANGE_SUBGROUP_SIZE
    )

    individual_chart = ControlChart(
        chart_type="I",
        values=values,
        center_line=mean_value,
        lower_limit=mean_value - E2_INDIVIDUAL * mean_moving_range,
        upper_limit=mean_value + E2_INDIVIDUAL * mean_moving_range,
        sigma_within=sigma_within,
        subgroup_size=1,
    )

    _, d4 = get_range_limit_factors(MOVING_RANGE_SUBGROUP_SIZE)

    moving_range_chart = ControlChart(
        chart_type="MR",
        values=moving_ranges,
        center_line=mean_moving_range,
        lower_limit=0.0,
        upper_limit=d4 * mean_moving_range,
        sigma_within=sigma_within,
        subgroup_size=MOVING_RANGE_SUBGROUP_SIZE,
    )

    return individual_chart, moving_range_chart


def xbar_r_chart(
    dataframe: pd.DataFrame,
    value_column: str,
    subgroup_column: str,
) -> tuple[ControlChart, ControlChart]:
    """X-bar - R 관리도를 계산한다.

    부분군을 형성할 수 있는 경우(설비별, 시간대별 등)에 사용한다.
    모든 부분군의 크기가 같아야 한다.

    Returns
    -------
    (X-bar 관리도, R 관리도)
    """
    if value_column not in dataframe.columns:
        raise ValueError(f"존재하지 않는 컬럼입니다: {value_column}")

    if subgroup_column not in dataframe.columns:
        raise ValueError(f"존재하지 않는 컬럼입니다: {subgroup_column}")

    grouped = dataframe.dropna(subset=[value_column]).groupby(
        subgroup_column,
        sort=True,
    )[value_column]

    sizes = grouped.size()

    if sizes.nunique() != 1:
        raise ValueError(
            "X-bar-R 관리도는 부분군 크기가 모두 같아야 합니다. "
            f"관측된 크기: {sorted(sizes.unique().tolist())}"
        )

    subgroup_size = int(sizes.iloc[0])

    if subgroup_size < 2:
        raise ValueError(
            "부분군 크기가 1이면 X-bar-R 관리도를 쓸 수 없습니다. "
            "individual_moving_range_chart 를 사용하세요."
        )

    subgroup_means = grouped.mean().to_numpy(dtype=float)
    subgroup_ranges = grouped.apply(
        lambda values: values.max() - values.min()
    ).to_numpy(dtype=float)

    labels = [str(label) for label in grouped.groups.keys()]

    grand_mean = float(subgroup_means.mean())
    mean_range = float(subgroup_ranges.mean())

    sigma_within = mean_range / get_d2(subgroup_size)
    a2 = get_a2(subgroup_size)

    xbar = ControlChart(
        chart_type="X-bar",
        values=subgroup_means,
        center_line=grand_mean,
        lower_limit=grand_mean - a2 * mean_range,
        upper_limit=grand_mean + a2 * mean_range,
        sigma_within=sigma_within,
        subgroup_size=subgroup_size,
        labels=labels,
    )

    d3, d4 = get_range_limit_factors(subgroup_size)

    range_chart = ControlChart(
        chart_type="R",
        values=subgroup_ranges,
        center_line=mean_range,
        lower_limit=d3 * mean_range,
        upper_limit=d4 * mean_range,
        sigma_within=sigma_within,
        subgroup_size=subgroup_size,
        labels=labels,
    )

    return xbar, range_chart


def p_chart(
    defect_counts: pd.Series | np.ndarray,
    sample_sizes: pd.Series | np.ndarray,
) -> ControlChart:
    """p 관리도(불량률 관리도)를 계산한다.

    불량 여부처럼 계수형(attribute) 데이터에는 I-MR 관리도를 쓸 수 없다.
    불량률은 이항분포를 따르고 정규분포가 아니기 때문이다.

    수율이나 불량률을 I-MR 관리도에 올리면 정상 LOT 과 불량 LOT 이
    두 개의 봉우리를 만들어, 모든 불량 LOT 이 규칙 1 위반으로 잡힌다.
    이것은 이상 신호가 아니라 차트 선택이 틀린 것이다.

    관리한계는 이항분포의 표준오차로 계산한다.
        sigma_p = sqrt( p_bar * (1 - p_bar) / n )
    부분군 크기 n 이 다르면 한계선도 타점마다 달라진다.
    """
    counts = pd.Series(defect_counts).to_numpy(dtype=float)
    sizes = pd.Series(sample_sizes).to_numpy(dtype=float)

    if counts.size != sizes.size:
        raise ValueError(
            "불량 수와 부분군 크기의 길이가 같아야 합니다."
        )

    if counts.size < 2:
        raise ValueError("p 관리도에는 부분군이 2개 이상 필요합니다.")

    if np.any(sizes <= 0):
        raise ValueError("부분군 크기는 1 이상이어야 합니다.")

    proportions = counts / sizes
    center = float(counts.sum() / sizes.sum())

    standard_error = np.sqrt(center * (1.0 - center) / sizes)

    upper = np.clip(center + 3 * standard_error, 0.0, 1.0)
    lower = np.clip(center - 3 * standard_error, 0.0, 1.0)

    # 부분군 크기가 일정하면 스칼라 한계로, 다르면 평균 한계를 대표값으로
    # 두고 개별 한계는 variable_limits 에 담는다.
    chart = ControlChart(
        chart_type="p",
        values=proportions,
        center_line=center,
        lower_limit=float(lower.mean()),
        upper_limit=float(upper.mean()),
        sigma_within=float(standard_error.mean()),
        subgroup_size=int(round(float(sizes.mean()))),
    )

    chart.variable_lower_limits = lower
    chart.variable_upper_limits = upper

    return chart


def build_defect_rate_subgroups(
    dataframe: pd.DataFrame,
    defect_column: str = "Defect",
    positive_label: str = "Delamination",
    subgroup_size: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """LOT 순서대로 묶어 불량률 부분군을 만든다.

    p 관리도는 부분군 단위로 불량률을 타점한다.
    연속한 subgroup_size 개의 LOT 을 하나의 부분군으로 본다.

    Returns
    -------
    (부분군별 불량 LOT 수, 부분군 크기)
    """
    if defect_column not in dataframe.columns:
        raise ValueError(f"존재하지 않는 컬럼입니다: {defect_column}")

    flags = (
        dataframe[defect_column] == positive_label
    ).to_numpy(dtype=int)

    group_count = flags.size // subgroup_size

    if group_count < 2:
        raise ValueError(
            "부분군이 2개 이상 만들어지지 않습니다. "
            f"관측 {flags.size}건, 부분군 크기 {subgroup_size}."
        )

    trimmed = flags[: group_count * subgroup_size]
    reshaped = trimmed.reshape(group_count, subgroup_size)

    counts = reshaped.sum(axis=1).astype(float)
    sizes = np.full(group_count, float(subgroup_size))

    return counts, sizes


def estimate_sigma_within(
    series: pd.Series | np.ndarray,
) -> float:
    """부분군 내 변동으로 표준편차를 추정한다(I-MR 기준).

    공정능력지수 Cp, Cpk 에 사용한다.
    """
    moving_ranges = calculate_moving_ranges(series)

    return float(
        moving_ranges.mean() / get_d2(MOVING_RANGE_SUBGROUP_SIZE)
    )


def estimate_sigma_overall(
    series: pd.Series | np.ndarray,
) -> float:
    """전체 변동으로 표준편차를 추정한다(표본표준편차).

    공정성능지수 Pp, Ppk 에 사용한다.
    """
    values = _as_clean_array(series)

    return float(values.std(ddof=1))
