"""공정능력 분석 모듈.

Cp/Cpk 와 Pp/Ppk 를 구분해서 계산한다.

- Cp, Cpk : 부분군 내 변동(sigma_within)으로 계산. 단기 능력.
            "이 공정이 안정되면 도달할 수 있는 수준"
- Pp, Ppk : 전체 변동(sigma_overall)으로 계산. 장기 성능.
            "실제로 고객이 받은 수준"

두 값을 나란히 보는 이유
-----------------------
- Cp 와 Cpk 의 차이 -> 공정 평균이 규격 중심에서 치우친 정도(centering)
- Cp 와 Pp 의 차이  -> 부분군 간 변동의 크기(설비 간 차이, 시간에 따른 이동)
  Cp 는 좋은데 Pp 가 나쁘면 개별 배치는 균일하나 배치 간 산포가 크다는 뜻이다.
  이때 필요한 조치는 산포 축소가 아니라 배치 간 조건 정렬이다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from src.quality.control_charts import (
    estimate_sigma_overall,
    estimate_sigma_within,
)


@dataclass
class CapabilityResult:
    """공정능력 분석 결과."""

    characteristic: str
    sample_size: int
    mean: float
    sigma_within: float
    sigma_overall: float
    lower_spec: float | None
    upper_spec: float | None
    target: float | None

    cp: float | None
    cpk: float | None
    cpu: float | None
    cpl: float | None
    pp: float | None
    ppk: float | None

    expected_ppm_out_of_spec: float | None
    observed_out_of_spec_count: int
    normality_p_value: float | None

    @property
    def centering_gap(self) -> float | None:
        """Cp - Cpk. 규격 중심에서 치우친 정도."""
        if self.cp is None or self.cpk is None:
            return None

        return self.cp - self.cpk

    @property
    def between_subgroup_gap(self) -> float | None:
        """Cp - Pp. 부분군 간 변동의 크기."""
        if self.cp is None or self.pp is None:
            return None

        return self.cp - self.pp

    @property
    def verdict(self) -> str:
        """Cpk 기준 판정.

        자동차/반도체 업계에서 통용되는 기준을 따른다.
        1.67 이상: 우수, 1.33 이상: 양호, 1.00 이상: 개선 필요,
        1.00 미만: 부적합
        """
        if self.cpk is None:
            return "판정 불가(규격한계 없음)"

        if self.cpk >= 1.67:
            return "우수"

        if self.cpk >= 1.33:
            return "양호"

        if self.cpk >= 1.00:
            return "개선 필요"

        return "부적합"

    @property
    def diagnosis(self) -> str:
        """개선 방향을 한 문장으로 제시한다."""
        if self.cpk is None:
            return "규격한계가 정의되지 않아 능력 판정을 할 수 없습니다."

        messages: list[str] = []

        centering = self.centering_gap
        between = self.between_subgroup_gap

        if centering is not None and centering > 0.25:
            direction = (
                "규격 상한" if (self.cpu or 9) < (self.cpl or 9) else "규격 하한"
            )
            messages.append(
                f"Cp({self.cp:.2f})와 Cpk({self.cpk:.2f}) 차이가 크다. "
                f"공정 평균이 {direction} 쪽으로 치우쳐 있으므로 "
                "산포 축소보다 중심 조정이 먼저다."
            )

        if between is not None and between > 0.30:
            messages.append(
                f"Cp({self.cp:.2f})는 양호하나 Pp({self.pp:.2f})가 낮다. "
                "부분군 내 산포는 작고 부분군 간 차이가 크다는 뜻이므로, "
                "설비 간 조건 정렬이나 자재 LOT 간 편차를 먼저 본다."
            )

        if self.normality_p_value is not None:
            if self.normality_p_value < 0.05:
                messages.append(
                    "정규성 검정이 기각되었다"
                    f"(p={self.normality_p_value:.4f}). "
                    "정규분포를 전제한 불량률 추정치는 참고용으로만 본다."
                )

        if not messages:
            messages.append(
                f"Cpk {self.cpk:.2f}로 {self.verdict} 수준이며 "
                "중심 이동과 부분군 간 변동 모두 특이점이 없다."
            )

        return " ".join(messages)

    def to_dict(self) -> dict[str, object]:
        return {
            "characteristic": self.characteristic,
            "sample_size": self.sample_size,
            "mean": self.mean,
            "sigma_within": self.sigma_within,
            "sigma_overall": self.sigma_overall,
            "lsl": self.lower_spec,
            "usl": self.upper_spec,
            "target": self.target,
            "cp": self.cp,
            "cpk": self.cpk,
            "cpu": self.cpu,
            "cpl": self.cpl,
            "pp": self.pp,
            "ppk": self.ppk,
            "cp_minus_cpk": self.centering_gap,
            "cp_minus_pp": self.between_subgroup_gap,
            "expected_ppm": self.expected_ppm_out_of_spec,
            "observed_out_of_spec": self.observed_out_of_spec_count,
            "normality_p_value": self.normality_p_value,
            "verdict": self.verdict,
            "diagnosis": self.diagnosis,
        }


def _capability_indices(
    mean: float,
    sigma: float,
    lower_spec: float | None,
    upper_spec: float | None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """(양측지수, 최소지수, 상한지수, 하한지수)를 계산한다.

    양측지수는 Cp 또는 Pp, 최소지수는 Cpk 또는 Ppk 에 해당한다.
    """
    if sigma <= 0:
        return None, None, None, None

    upper_index = (
        (upper_spec - mean) / (3 * sigma)
        if upper_spec is not None
        else None
    )

    lower_index = (
        (mean - lower_spec) / (3 * sigma)
        if lower_spec is not None
        else None
    )

    two_sided = (
        (upper_spec - lower_spec) / (6 * sigma)
        if lower_spec is not None and upper_spec is not None
        else None
    )

    candidates = [
        value
        for value in (upper_index, lower_index)
        if value is not None
    ]

    minimum_index = min(candidates) if candidates else None

    return two_sided, minimum_index, upper_index, lower_index


def _expected_ppm(
    mean: float,
    sigma: float,
    lower_spec: float | None,
    upper_spec: float | None,
) -> float | None:
    """정규분포를 전제한 규격 이탈 추정 ppm."""
    if sigma <= 0:
        return None

    if lower_spec is None and upper_spec is None:
        return None

    probability = 0.0

    if lower_spec is not None:
        probability += float(stats.norm.cdf(lower_spec, mean, sigma))

    if upper_spec is not None:
        probability += float(stats.norm.sf(upper_spec, mean, sigma))

    return probability * 1_000_000


def _normality_p_value(values: np.ndarray) -> float | None:
    """정규성 검정 p-value.

    표본이 5000개를 넘으면 Shapiro-Wilk 대신
    Anderson-Darling 기반 정규성 검정(normaltest)을 사용한다.
    """
    if values.size < 8:
        return None

    try:
        if values.size <= 5000:
            return float(stats.shapiro(values).pvalue)

        return float(stats.normaltest(values).pvalue)
    except ValueError:
        return None


def analyze_capability(
    series: pd.Series | np.ndarray,
    characteristic: str,
    lower_spec: float | None,
    upper_spec: float | None,
    target: float | None = None,
) -> CapabilityResult:
    """단일 품질 특성의 공정능력을 분석한다.

    Parameters
    ----------
    series : 측정값
    characteristic : 특성 이름
    lower_spec : 규격 하한(LSL). 없으면 None
    upper_spec : 규격 상한(USL). 없으면 None
    target : 목표값
    """
    if lower_spec is None and upper_spec is None:
        raise ValueError(
            "공정능력을 계산하려면 규격 상한 또는 하한이 하나는 필요합니다. "
            f"특성: {characteristic}"
        )

    values = pd.Series(series).dropna().to_numpy(dtype=float)

    if values.size < 2:
        raise ValueError(
            f"유효한 측정값이 2개 이상 필요합니다. 특성: {characteristic}"
        )

    mean = float(values.mean())
    sigma_within = estimate_sigma_within(values)
    sigma_overall = estimate_sigma_overall(values)

    cp, cpk, cpu, cpl = _capability_indices(
        mean=mean,
        sigma=sigma_within,
        lower_spec=lower_spec,
        upper_spec=upper_spec,
    )

    pp, ppk, _, _ = _capability_indices(
        mean=mean,
        sigma=sigma_overall,
        lower_spec=lower_spec,
        upper_spec=upper_spec,
    )

    observed = 0

    if lower_spec is not None:
        observed += int((values < lower_spec).sum())

    if upper_spec is not None:
        observed += int((values > upper_spec).sum())

    return CapabilityResult(
        characteristic=characteristic,
        sample_size=int(values.size),
        mean=mean,
        sigma_within=sigma_within,
        sigma_overall=sigma_overall,
        lower_spec=lower_spec,
        upper_spec=upper_spec,
        target=target,
        cp=cp,
        cpk=cpk,
        cpu=cpu,
        cpl=cpl,
        pp=pp,
        ppk=ppk,
        expected_ppm_out_of_spec=_expected_ppm(
            mean=mean,
            sigma=sigma_overall,
            lower_spec=lower_spec,
            upper_spec=upper_spec,
        ),
        observed_out_of_spec_count=observed,
        normality_p_value=_normality_p_value(values),
    )


def analyze_capability_table(
    dataframe: pd.DataFrame,
    specifications: dict[str, dict[str, float | None]],
) -> pd.DataFrame:
    """여러 품질 특성의 공정능력을 표로 정리한다.

    Parameters
    ----------
    dataframe : 측정값이 담긴 데이터프레임
    specifications : {특성명: {"lsl": ..., "usl": ..., "target": ...}}
    """
    rows: list[dict[str, object]] = []

    for characteristic, spec in specifications.items():
        if characteristic not in dataframe.columns:
            continue

        lower = spec.get("lsl")
        upper = spec.get("usl")

        if lower is None and upper is None:
            continue

        result = analyze_capability(
            series=dataframe[characteristic],
            characteristic=characteristic,
            lower_spec=lower,
            upper_spec=upper,
            target=spec.get("target"),
        )

        rows.append(result.to_dict())

    return pd.DataFrame(rows)
