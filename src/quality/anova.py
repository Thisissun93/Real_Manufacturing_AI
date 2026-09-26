"""분산분석과 다중비교.

설비 간 차이, 모델 간 차이, 자재 LOT 간 차이를 판정한다.

왜 t 검정을 반복하면 안 되는가
------------------------------
설비가 3대면 쌍별 비교가 3번, 5대면 10번이다. 각 비교를 유의수준 5%로
하면 '어느 하나라도 유의하게 나올' 확률이 3번일 때 14%, 10번일 때 40%까지
올라간다. 실제로는 차이가 없는데 있다고 판정하게 된다.

그래서 순서를 지킨다.
1. 일원분산분석(ANOVA)으로 "어딘가 차이가 있는가"를 먼저 판정한다.
2. 유의하면 Tukey HSD 로 "어느 쌍이 다른가"를 찾는다.
   Tukey HSD 는 모든 쌍을 비교하면서 전체 유의수준을 5%로 유지한다.
3. 등분산 가정이 깨지면 Welch ANOVA 를 쓴다.

Tukey HSD 통계량
----------------
q = |mean_i - mean_j| / sqrt( (MSE / 2) * (1/n_i + 1/n_j) )
p = studentized_range.sf(q, k, df_error)

표본 수가 같으면 분모가 sqrt(MSE / n) 으로 정리되며,
다르면 위 식이 Tukey-Kramer 확장이 된다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class AnovaResult:
    """일원분산분석 결과."""

    response: str
    factor: str
    group_count: int
    total_count: int

    sum_of_squares_between: float
    sum_of_squares_within: float
    degrees_of_freedom_between: int
    degrees_of_freedom_within: int
    mean_square_between: float
    mean_square_within: float

    f_statistic: float
    p_value: float
    eta_squared: float
    omega_squared: float

    levene_p_value: float
    welch_f_statistic: float
    welch_p_value: float

    group_summary: pd.DataFrame

    @property
    def equal_variance_assumed(self) -> bool:
        """Levene 검정으로 등분산 가정을 판정한다."""
        return self.levene_p_value >= 0.05

    @property
    def significant(self) -> bool:
        """등분산 여부에 따라 적절한 검정의 유의성을 반환한다."""
        if self.equal_variance_assumed:
            return self.p_value < 0.05

        return self.welch_p_value < 0.05

    @property
    def effect_size_label(self) -> str:
        """eta squared 기준 효과 크기."""
        if self.eta_squared >= 0.14:
            return "큼"

        if self.eta_squared >= 0.06:
            return "중간"

        if self.eta_squared >= 0.01:
            return "작음"

        return "무시할 수준"

    @property
    def diagnosis(self) -> str:
        """판정 결과를 문장으로 제시한다."""
        test_name = (
            "일원분산분석" if self.equal_variance_assumed else "Welch ANOVA"
        )
        p_value = (
            self.p_value
            if self.equal_variance_assumed
            else self.welch_p_value
        )

        if not self.equal_variance_assumed:
            prefix = (
                f"Levene 검정 p={self.levene_p_value:.4f}로 등분산 가정이 "
                "기각되어 Welch ANOVA 로 판정했다. "
            )
        else:
            prefix = ""

        if not self.significant:
            return (
                f"{prefix}{test_name} p={p_value:.4f}로 "
                f"{self.factor} 간 {self.response} 평균 차이는 "
                "통계적으로 유의하지 않다."
            )

        return (
            f"{prefix}{test_name} p={p_value:.4g}로 "
            f"{self.factor} 간 {self.response} 평균에 차이가 있다. "
            f"효과 크기는 eta^2={self.eta_squared:.3f}"
            f"({self.effect_size_label}). "
            "어느 수준이 다른지는 Tukey HSD 로 확인한다."
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "response": self.response,
            "factor": self.factor,
            "groups": self.group_count,
            "n": self.total_count,
            "df_between": self.degrees_of_freedom_between,
            "df_within": self.degrees_of_freedom_within,
            "ms_between": self.mean_square_between,
            "ms_within": self.mean_square_within,
            "f": self.f_statistic,
            "p_value": self.p_value,
            "eta_squared": self.eta_squared,
            "omega_squared": self.omega_squared,
            "levene_p": self.levene_p_value,
            "equal_variance": self.equal_variance_assumed,
            "welch_f": self.welch_f_statistic,
            "welch_p": self.welch_p_value,
            "significant": self.significant,
            "effect_size": self.effect_size_label,
            "diagnosis": self.diagnosis,
        }


@dataclass
class TukeyComparison:
    """Tukey HSD 쌍별 비교 1건."""

    group_a: str
    group_b: str
    mean_difference: float
    standard_error: float
    q_statistic: float
    p_value: float
    confidence_lower: float
    confidence_upper: float

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    def to_dict(self) -> dict[str, object]:
        return {
            "group_a": self.group_a,
            "group_b": self.group_b,
            "mean_difference": self.mean_difference,
            "std_error": self.standard_error,
            "q_statistic": self.q_statistic,
            "p_value": self.p_value,
            "ci_lower": self.confidence_lower,
            "ci_upper": self.confidence_upper,
            "significant": self.significant,
        }


def _grouped_values(
    dataframe: pd.DataFrame,
    response: str,
    factor: str,
) -> dict[str, np.ndarray]:
    """수준별 관측값을 모은다."""
    for column in (response, factor):
        if column not in dataframe.columns:
            raise ValueError(f"존재하지 않는 컬럼입니다: {column}")

    data = dataframe[[response, factor]].dropna()

    groups: dict[str, np.ndarray] = {}

    for level, subset in data.groupby(factor, sort=True):
        values = subset[response].to_numpy(dtype=float)

        if values.size >= 2:
            groups[str(level)] = values

    if len(groups) < 2:
        raise ValueError(
            "분산분석에는 관측값이 2개 이상인 수준이 2개 이상 필요합니다. "
            f"인자: {factor}"
        )

    return groups


def one_way_anova(
    dataframe: pd.DataFrame,
    response: str,
    factor: str,
) -> AnovaResult:
    """일원분산분석을 수행한다.

    등분산 검정(Levene)과 Welch ANOVA 를 함께 계산해,
    가정이 깨졌을 때 어떤 결론을 써야 하는지 알 수 있게 한다.
    """
    groups = _grouped_values(dataframe, response, factor)

    group_values = list(groups.values())
    all_values = np.concatenate(group_values)

    grand_mean = float(all_values.mean())
    total_count = int(all_values.size)
    group_count = len(groups)

    ss_between = float(
        sum(
            values.size * (values.mean() - grand_mean) ** 2
            for values in group_values
        )
    )

    ss_within = float(
        sum(
            ((values - values.mean()) ** 2).sum()
            for values in group_values
        )
    )

    df_between = group_count - 1
    df_within = total_count - group_count

    ms_between = ss_between / df_between
    ms_within = ss_within / df_within if df_within > 0 else np.nan

    f_statistic = (
        ms_between / ms_within
        if ms_within and ms_within > 0
        else np.nan
    )

    p_value = (
        float(stats.f.sf(f_statistic, df_between, df_within))
        if np.isfinite(f_statistic)
        else np.nan
    )

    ss_total = ss_between + ss_within

    eta_squared = ss_between / ss_total if ss_total > 0 else np.nan

    omega_numerator = ss_between - df_between * ms_within
    omega_denominator = ss_total + ms_within
    omega_squared = (
        omega_numerator / omega_denominator
        if omega_denominator > 0
        else np.nan
    )

    levene = stats.levene(*group_values, center="median")
    welch = stats.f_oneway(*group_values, equal_var=False)

    summary = pd.DataFrame(
        [
            {
                "level": level,
                "n": values.size,
                "mean": float(values.mean()),
                "std_dev": float(values.std(ddof=1)),
                "min": float(values.min()),
                "max": float(values.max()),
            }
            for level, values in groups.items()
        ]
    ).sort_values("mean", ascending=False, ignore_index=True)

    return AnovaResult(
        response=response,
        factor=factor,
        group_count=group_count,
        total_count=total_count,
        sum_of_squares_between=ss_between,
        sum_of_squares_within=ss_within,
        degrees_of_freedom_between=df_between,
        degrees_of_freedom_within=df_within,
        mean_square_between=ms_between,
        mean_square_within=float(ms_within),
        f_statistic=float(f_statistic),
        p_value=float(p_value),
        eta_squared=float(eta_squared),
        omega_squared=float(max(omega_squared, 0.0)),
        levene_p_value=float(levene.pvalue),
        welch_f_statistic=float(welch.statistic),
        welch_p_value=float(welch.pvalue),
        group_summary=summary,
    )


def tukey_hsd(
    dataframe: pd.DataFrame,
    response: str,
    factor: str,
    alpha: float = 0.05,
) -> list[TukeyComparison]:
    """Tukey HSD 로 모든 쌍을 비교한다.

    표본 수가 다르면 Tukey-Kramer 확장이 자동 적용된다.
    전체 유의수준(family-wise error rate)이 alpha 로 유지된다.
    """
    groups = _grouped_values(dataframe, response, factor)

    group_values = list(groups.values())
    levels = list(groups.keys())

    total_count = sum(values.size for values in group_values)
    group_count = len(groups)
    df_within = total_count - group_count

    if df_within <= 0:
        raise ValueError("오차 자유도가 0 이하입니다.")

    ms_within = (
        sum(
            ((values - values.mean()) ** 2).sum()
            for values in group_values
        )
        / df_within
    )

    if ms_within <= 0:
        raise ValueError(
            "군내 분산이 0입니다. Tukey HSD 를 계산할 수 없습니다."
        )

    critical_q = float(
        stats.studentized_range.ppf(
            1 - alpha,
            group_count,
            df_within,
        )
    )

    comparisons: list[TukeyComparison] = []

    for first in range(group_count):
        for second in range(first + 1, group_count):
            values_a = group_values[first]
            values_b = group_values[second]

            difference = float(values_a.mean() - values_b.mean())

            standard_error = float(
                np.sqrt(
                    (ms_within / 2.0)
                    * (1.0 / values_a.size + 1.0 / values_b.size)
                )
            )

            q_statistic = abs(difference) / standard_error

            p_value = float(
                stats.studentized_range.sf(
                    q_statistic,
                    group_count,
                    df_within,
                )
            )

            margin = critical_q * standard_error

            comparisons.append(
                TukeyComparison(
                    group_a=levels[first],
                    group_b=levels[second],
                    mean_difference=difference,
                    standard_error=standard_error,
                    q_statistic=q_statistic,
                    p_value=p_value,
                    confidence_lower=difference - margin,
                    confidence_upper=difference + margin,
                )
            )

    return sorted(comparisons, key=lambda item: item.p_value)


def tukey_hsd_table(
    dataframe: pd.DataFrame,
    response: str,
    factor: str,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Tukey HSD 결과를 데이터프레임으로 반환한다."""
    comparisons = tukey_hsd(
        dataframe=dataframe,
        response=response,
        factor=factor,
        alpha=alpha,
    )

    return pd.DataFrame(
        [comparison.to_dict() for comparison in comparisons]
    )


def compare_factor_across_responses(
    dataframe: pd.DataFrame,
    factor: str,
    responses: list[str],
    alpha: float = 0.05,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """하나의 인자에 대해 여러 품질 특성을 한 번에 검정한다.

    설비(Machine) 간 차이를 모든 품질 특성에 대해 훑을 때 사용한다.

    Returns
    -------
    (ANOVA 요약표, 유의한 쌍별 비교표)
    """
    anova_rows: list[dict[str, object]] = []
    pairwise_rows: list[dict[str, object]] = []

    for response in responses:
        if response not in dataframe.columns:
            continue

        if not pd.api.types.is_numeric_dtype(dataframe[response]):
            continue

        try:
            result = one_way_anova(
                dataframe=dataframe,
                response=response,
                factor=factor,
            )
        except ValueError:
            continue

        anova_rows.append(result.to_dict())

        if not result.significant:
            continue

        for comparison in tukey_hsd(
            dataframe=dataframe,
            response=response,
            factor=factor,
            alpha=alpha,
        ):
            if not comparison.significant:
                continue

            row = comparison.to_dict()
            row["response"] = response
            row["factor"] = factor
            pairwise_rows.append(row)

    return pd.DataFrame(anova_rows), pd.DataFrame(pairwise_rows)
