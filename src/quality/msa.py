"""측정시스템 분석(MSA) - Gage R&R, 편향, 안정성.

현장에서 계측기 검교정과 설비 간 비교를 할 때 평가하는 항목이
통계적으로는 다음에 대응한다.

- 반복성(Repeatability, EV) : 같은 작업자가 같은 시료를 반복 측정할 때의 산포.
                              계측기 자체의 산포다.
- 재현성(Reproducibility, AV): 작업자가 바뀔 때 생기는 산포.
                              작업자 간 편차다.
- GRR                        : 반복성과 재현성을 합친 측정시스템 전체 산포.
- 부품 변동(PV)              : 시료 자체가 실제로 다른 정도.
- 총 변동(TV)                : GRR 과 PV 를 합친 전체 산포.

핵심 판정
---------
%GRR = 100 * GRR / TV
  10% 미만      : 적합
  10% ~ 30%     : 조건부 적합 (용도와 비용을 고려해 판단)
  30% 초과      : 부적합. 이 계측기로는 공정 판정을 할 수 없다.

ndc(구별 가능 범주 수) = 1.41 * PV / GRR
  5 이상이어야 공정 산포를 구간으로 나눠 판정할 수 있다.

%P/T = 100 * 6 * GRR / 공차
  규격 공차 대비 측정시스템이 잡아먹는 비율. 규격이 좁은 특성에서는
  %GRR 이 양호해도 %P/T 가 불합격일 수 있다. 두 지표를 함께 본다.

계산 방식
---------
AIAG MSA 4판의 ANOVA 법을 사용한다.
범위법(X-bar & R 법)보다 정확하고, 부품과 작업자의 교호작용을 분리할 수 있다.
교호작용이 유의하지 않으면(p > 0.25) 오차항에 통합해 재계산한다.
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
from scipy import stats


# 교호작용을 오차항에 통합할 유의수준 (AIAG MSA 4판)
INTERACTION_POOLING_ALPHA: Final[float] = 0.25

# ndc 계산 상수. 1.41 = 6 / 4.25
NDC_CONSTANT: Final[float] = 1.41


@dataclass
class VarianceComponent:
    """분산 성분 1개."""

    name: str
    variance: float
    standard_deviation: float
    percent_of_total_variation: float
    percent_contribution: float


@dataclass
class GageRnRResult:
    """Gage R&R 분석 결과."""

    characteristic: str
    part_count: int
    operator_count: int
    replicate_count: int

    anova_table: pd.DataFrame
    interaction_pooled: bool
    interaction_p_value: float | None

    repeatability_ev: float
    reproducibility_av: float
    interaction_sd: float
    gage_rnr: float
    part_variation_pv: float
    total_variation_tv: float

    percent_ev: float
    percent_av: float
    percent_interaction: float
    percent_grr: float
    percent_pv: float

    number_of_distinct_categories: int
    tolerance: float | None
    percent_precision_to_tolerance: float | None

    @property
    def verdict(self) -> str:
        """%GRR 기준 AIAG 판정."""
        if self.percent_grr < 10.0:
            return "적합"

        if self.percent_grr <= 30.0:
            return "조건부 적합"

        return "부적합"

    @property
    def dominant_source(self) -> str:
        """측정 산포의 주된 원인."""
        if self.repeatability_ev >= self.reproducibility_av:
            return "반복성(계측기)"

        return "재현성(작업자)"

    @property
    def diagnosis(self) -> str:
        """조치 방향을 문장으로 제시한다."""
        messages: list[str] = [
            f"%GRR {self.percent_grr:.1f}%로 {self.verdict} 수준이다."
        ]

        if self.dominant_source.startswith("반복성"):
            messages.append(
                f"반복성(EV {self.repeatability_ev:.4f})이 "
                f"재현성(AV {self.reproducibility_av:.4f})보다 크다. "
                "계측기 자체의 산포가 주 원인이므로 검교정, 고정구 개선, "
                "측정 위치 규정, 계측기 교체를 검토한다."
            )
        else:
            messages.append(
                f"재현성(AV {self.reproducibility_av:.4f})이 "
                f"반복성(EV {self.repeatability_ev:.4f})보다 크다. "
                "작업자 간 편차가 주 원인이므로 측정 절차 표준화와 "
                "교육, 판정 기준 통일이 우선이다."
            )

        if not self.interaction_pooled:
            messages.append(
                "부품과 작업자의 교호작용이 유의하다. 특정 작업자가 "
                "특정 시료에서만 다르게 측정한다는 뜻이므로, 시료 형상이나 "
                "측정 자세에 따라 해석이 갈리는 지점을 찾는다."
            )

        if self.number_of_distinct_categories < 5:
            messages.append(
                f"ndc {self.number_of_distinct_categories}로 5 미만이다. "
                "이 계측기로는 공정 산포를 구간으로 나눠 판정할 수 없다."
            )

        if (
            self.percent_precision_to_tolerance is not None
            and self.percent_precision_to_tolerance > 30.0
        ):
            messages.append(
                f"%P/T {self.percent_precision_to_tolerance:.1f}%로 "
                "공차 대비 측정 산포가 과도하다. 규격이 좁은 특성에서는 "
                "%GRR 보다 %P/T 가 실제 판정 능력을 더 잘 나타낸다."
            )

        return " ".join(messages)

    def variance_components(self) -> pd.DataFrame:
        """분산 성분 표를 반환한다."""
        total_variance = self.total_variation_tv**2

        rows = [
            ("반복성(EV)", self.repeatability_ev, self.percent_ev),
            ("재현성(AV)", self.reproducibility_av, self.percent_av),
            (
                "교호작용",
                self.interaction_sd,
                self.percent_interaction,
            ),
            ("측정시스템(GRR)", self.gage_rnr, self.percent_grr),
            ("부품(PV)", self.part_variation_pv, self.percent_pv),
            ("총 변동(TV)", self.total_variation_tv, 100.0),
        ]

        return pd.DataFrame(
            [
                {
                    "source": name,
                    "std_dev": sd,
                    "variance": sd**2,
                    "percent_study_variation": percent,
                    "percent_contribution": (
                        100.0 * sd**2 / total_variance
                        if total_variance > 0
                        else np.nan
                    ),
                }
                for name, sd, percent in rows
            ]
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "characteristic": self.characteristic,
            "parts": self.part_count,
            "operators": self.operator_count,
            "replicates": self.replicate_count,
            "ev": self.repeatability_ev,
            "av": self.reproducibility_av,
            "grr": self.gage_rnr,
            "pv": self.part_variation_pv,
            "tv": self.total_variation_tv,
            "percent_ev": self.percent_ev,
            "percent_av": self.percent_av,
            "percent_grr": self.percent_grr,
            "percent_pv": self.percent_pv,
            "ndc": self.number_of_distinct_categories,
            "tolerance": self.tolerance,
            "percent_pt": self.percent_precision_to_tolerance,
            "interaction_pooled": self.interaction_pooled,
            "interaction_p_value": self.interaction_p_value,
            "verdict": self.verdict,
            "dominant_source": self.dominant_source,
            "diagnosis": self.diagnosis,
        }


def _validate_crossed_design(
    dataframe: pd.DataFrame,
    part_column: str,
    operator_column: str,
    value_column: str,
) -> tuple[int, int, int]:
    """교차 설계(crossed design)의 균형을 검증한다.

    모든 작업자가 모든 부품을 같은 횟수로 측정해야 한다.
    """
    for column in (part_column, operator_column, value_column):
        if column not in dataframe.columns:
            raise ValueError(f"존재하지 않는 컬럼입니다: {column}")

    counts = dataframe.groupby(
        [part_column, operator_column],
        sort=False,
    )[value_column].count()

    part_count = dataframe[part_column].nunique()
    operator_count = dataframe[operator_column].nunique()

    if counts.size != part_count * operator_count:
        raise ValueError(
            "교차 설계가 아닙니다. 모든 작업자가 모든 부품을 측정해야 "
            f"합니다. 기대 조합 {part_count * operator_count}개, "
            f"실제 {counts.size}개."
        )

    if counts.nunique() != 1:
        raise ValueError(
            "불균형 설계입니다. 반복 측정 횟수가 모든 조합에서 같아야 "
            f"합니다. 관측된 횟수: {sorted(counts.unique().tolist())}"
        )

    replicate_count = int(counts.iloc[0])

    if replicate_count < 2:
        raise ValueError(
            "반복성을 분리하려면 반복 측정이 2회 이상 필요합니다."
        )

    if part_count < 2 or operator_count < 2:
        raise ValueError(
            "부품과 작업자가 각각 2 수준 이상이어야 합니다."
        )

    return part_count, operator_count, replicate_count


def _sum_of_squares(
    dataframe: pd.DataFrame,
    part_column: str,
    operator_column: str,
    value_column: str,
    part_count: int,
    operator_count: int,
    replicate_count: int,
) -> dict[str, float]:
    """이원배치 교차 설계의 제곱합을 계산한다."""
    values = dataframe[value_column].to_numpy(dtype=float)
    grand_mean = float(values.mean())

    part_means = dataframe.groupby(part_column)[value_column].mean()
    operator_means = dataframe.groupby(operator_column)[
        value_column
    ].mean()
    cell_means = dataframe.groupby(
        [part_column, operator_column]
    )[value_column].mean()

    ss_total = float(((values - grand_mean) ** 2).sum())

    ss_part = float(
        operator_count
        * replicate_count
        * ((part_means - grand_mean) ** 2).sum()
    )

    ss_operator = float(
        part_count
        * replicate_count
        * ((operator_means - grand_mean) ** 2).sum()
    )

    interaction_sum = 0.0

    for (part, operator), cell_mean in cell_means.items():
        interaction_sum += (
            cell_mean
            - part_means[part]
            - operator_means[operator]
            + grand_mean
        ) ** 2

    ss_interaction = float(replicate_count * interaction_sum)

    ss_error = ss_total - ss_part - ss_operator - ss_interaction

    return {
        "part": ss_part,
        "operator": ss_operator,
        "interaction": ss_interaction,
        "error": max(ss_error, 0.0),
        "total": ss_total,
    }


def gage_rnr_anova(
    dataframe: pd.DataFrame,
    value_column: str,
    part_column: str = "Part",
    operator_column: str = "Operator",
    tolerance: float | None = None,
    characteristic: str | None = None,
) -> GageRnRResult:
    """ANOVA 법으로 Gage R&R 을 계산한다.

    Parameters
    ----------
    dataframe : 측정 데이터. 부품 x 작업자 x 반복의 균형 교차 설계여야 한다.
    value_column : 측정값 컬럼
    part_column : 부품(시료) 컬럼
    operator_column : 작업자 컬럼
    tolerance : 규격 공차(USL - LSL). 주면 %P/T 를 함께 계산한다.
    characteristic : 특성 이름. 생략하면 value_column 을 사용한다.
    """
    # 컬럼 존재 검증을 pandas 인덱싱보다 먼저 한다.
    # 순서가 바뀌면 KeyError 가 먼저 나서 원인을 알기 어렵다.
    for column in (part_column, operator_column, value_column):
        if column not in dataframe.columns:
            raise ValueError(f"존재하지 않는 컬럼입니다: {column}")

    data = dataframe[
        [part_column, operator_column, value_column]
    ].dropna()

    part_count, operator_count, replicate_count = (
        _validate_crossed_design(
            dataframe=data,
            part_column=part_column,
            operator_column=operator_column,
            value_column=value_column,
        )
    )

    sum_squares = _sum_of_squares(
        dataframe=data,
        part_column=part_column,
        operator_column=operator_column,
        value_column=value_column,
        part_count=part_count,
        operator_count=operator_count,
        replicate_count=replicate_count,
    )

    df_part = part_count - 1
    df_operator = operator_count - 1
    df_interaction = df_part * df_operator
    df_error = part_count * operator_count * (replicate_count - 1)

    ms_part = sum_squares["part"] / df_part
    ms_operator = sum_squares["operator"] / df_operator
    ms_interaction = (
        sum_squares["interaction"] / df_interaction
        if df_interaction > 0
        else 0.0
    )
    ms_error = (
        sum_squares["error"] / df_error if df_error > 0 else 0.0
    )

    interaction_p_value: float | None = None

    if df_interaction > 0 and df_error > 0 and ms_error > 0:
        f_interaction = ms_interaction / ms_error
        interaction_p_value = float(
            stats.f.sf(f_interaction, df_interaction, df_error)
        )

    pool_interaction = (
        interaction_p_value is None
        or interaction_p_value > INTERACTION_POOLING_ALPHA
    )

    if pool_interaction:
        pooled_df = df_interaction + df_error
        pooled_ms = (
            (sum_squares["interaction"] + sum_squares["error"])
            / pooled_df
            if pooled_df > 0
            else 0.0
        )

        variance_repeatability = pooled_ms
        variance_interaction = 0.0
        variance_operator = max(
            (ms_operator - pooled_ms) / (part_count * replicate_count),
            0.0,
        )
        variance_part = max(
            (ms_part - pooled_ms) / (operator_count * replicate_count),
            0.0,
        )
    else:
        variance_repeatability = ms_error
        variance_interaction = max(
            (ms_interaction - ms_error) / replicate_count,
            0.0,
        )
        variance_operator = max(
            (ms_operator - ms_interaction)
            / (part_count * replicate_count),
            0.0,
        )
        variance_part = max(
            (ms_part - ms_interaction)
            / (operator_count * replicate_count),
            0.0,
        )

    ev = float(np.sqrt(variance_repeatability))
    av = float(np.sqrt(variance_operator))
    interaction_sd = float(np.sqrt(variance_interaction))
    pv = float(np.sqrt(variance_part))

    grr = float(
        np.sqrt(
            variance_repeatability
            + variance_operator
            + variance_interaction
        )
    )

    tv = float(np.sqrt(grr**2 + variance_part))

    def as_percent(value: float) -> float:
        return 100.0 * value / tv if tv > 0 else float("nan")

    ndc = (
        int(NDC_CONSTANT * pv / grr) if grr > 0 else 0
    )

    percent_pt = (
        100.0 * 6.0 * grr / tolerance
        if tolerance is not None and tolerance > 0
        else None
    )

    anova_rows = [
        {
            "source": "부품(Part)",
            "df": df_part,
            "ss": sum_squares["part"],
            "ms": ms_part,
        },
        {
            "source": "작업자(Operator)",
            "df": df_operator,
            "ss": sum_squares["operator"],
            "ms": ms_operator,
        },
        {
            "source": "부품 x 작업자",
            "df": df_interaction,
            "ss": sum_squares["interaction"],
            "ms": ms_interaction,
        },
        {
            "source": "반복(Error)",
            "df": df_error,
            "ss": sum_squares["error"],
            "ms": ms_error,
        },
        {
            "source": "합계",
            "df": df_part
            + df_operator
            + df_interaction
            + df_error,
            "ss": sum_squares["total"],
            "ms": np.nan,
        },
    ]

    return GageRnRResult(
        characteristic=characteristic or value_column,
        part_count=part_count,
        operator_count=operator_count,
        replicate_count=replicate_count,
        anova_table=pd.DataFrame(anova_rows),
        interaction_pooled=pool_interaction,
        interaction_p_value=interaction_p_value,
        repeatability_ev=ev,
        reproducibility_av=av,
        interaction_sd=interaction_sd,
        gage_rnr=grr,
        part_variation_pv=pv,
        total_variation_tv=tv,
        percent_ev=as_percent(ev),
        percent_av=as_percent(av),
        percent_interaction=as_percent(interaction_sd),
        percent_grr=as_percent(grr),
        percent_pv=as_percent(pv),
        number_of_distinct_categories=ndc,
        tolerance=tolerance,
        percent_precision_to_tolerance=percent_pt,
    )


def bias_and_linearity(
    dataframe: pd.DataFrame,
    measured_column: str,
    reference_column: str,
) -> dict[str, float]:
    """편향(Bias)과 선형성(Linearity)을 평가한다.

    기준값이 알려진 표준 시료를 측정한 데이터에 사용한다.
    계측기 검교정에서 실제로 확인하는 항목이다.

    - bias        : 측정값 평균 - 기준값 평균
    - slope       : 기준값에 대한 측정값 회귀 기울기. 1에서 벗어나면 선형성 문제
    - linearity   : |slope - 1| * 기준값 범위
    - r_squared   : 회귀 설명력
    """
    for column in (measured_column, reference_column):
        if column not in dataframe.columns:
            raise ValueError(f"존재하지 않는 컬럼입니다: {column}")

    data = dataframe[[measured_column, reference_column]].dropna()

    if len(data) < 3:
        raise ValueError("편향 분석에는 3개 이상의 관측값이 필요합니다.")

    measured = data[measured_column].to_numpy(dtype=float)
    reference = data[reference_column].to_numpy(dtype=float)

    bias_values = measured - reference
    bias = float(bias_values.mean())

    regression = stats.linregress(reference, measured)

    reference_range = float(reference.max() - reference.min())

    _, p_value = stats.ttest_1samp(bias_values, 0.0)

    return {
        "bias": bias,
        "bias_p_value": float(p_value),
        "bias_significant": bool(p_value < 0.05),
        "slope": float(regression.slope),
        "intercept": float(regression.intercept),
        "r_squared": float(regression.rvalue**2),
        "linearity": float(
            abs(regression.slope - 1.0) * reference_range
        ),
        "sample_size": int(len(data)),
    }
