"""Nelson 판정 규칙 8종.

관리도를 '그리는' 것과 규칙으로 '판정하는' 것은 다른 일이다.
관리한계를 벗어난 점(규칙 1)만 보면 공정 평균 이동, 추세, 층별 등
관리한계 안에서 일어나는 이상을 놓친다.

규칙 정의 (Nelson, Journal of Quality Technology, 1984)
-------------------------------------------------------
1. 1점이 중심선에서 3시그마를 벗어남          -> 급격한 이상
2. 9점이 연속으로 중심선 한쪽에 위치           -> 공정 평균 이동
3. 6점이 연속으로 증가 또는 감소               -> 추세(공구 마모, 약액 열화)
4. 14점이 연속으로 교대로 증감                 -> 층별 요인 혼입
5. 3점 중 2점이 같은 쪽 2시그마를 벗어남       -> 평균 이동 조기 신호
6. 5점 중 4점이 같은 쪽 1시그마를 벗어남       -> 작은 평균 이동
7. 15점이 연속으로 1시그마 안에 위치           -> 산포 과소(층별, 데이터 조작)
8. 8점이 연속으로 1시그마 밖에 위치(양쪽 무관) -> 이봉 분포, 두 모집단 혼입

각 규칙은 위반이 시작된 타점 인덱스와 구간을 함께 반환한다.
현장에서는 '몇 번째 LOT부터 이상인가'가 조치의 출발점이기 때문이다.
"""

from dataclasses import dataclass
from typing import Callable, Final

import numpy as np

from src.quality.control_charts import ControlChart


RULE_DESCRIPTIONS: Final[dict[int, str]] = {
    1: "1점이 3시그마를 벗어남",
    2: "9점 연속 중심선 한쪽",
    3: "6점 연속 증가 또는 감소",
    4: "14점 연속 교대 증감",
    5: "3점 중 2점이 같은 쪽 2시그마 밖",
    6: "5점 중 4점이 같은 쪽 1시그마 밖",
    7: "15점 연속 1시그마 안",
    8: "8점 연속 1시그마 밖",
}

RULE_INTERPRETATIONS: Final[dict[int, str]] = {
    1: "급격한 단일 이상. 설비 이벤트, 측정 오류, 자재 교체 시점을 확인한다.",
    2: "공정 평균이 이동했다. 조건 변경, 자재 LOT 교체, 설비 정비 이력을 본다.",
    3: "추세가 있다. 공구 마모, 약액 농도 저하, 필터 막힘 같은 점진적 열화를 본다.",
    4: "교대 패턴. 두 설비 또는 두 작업조가 번갈아 투입되는 층별 요인을 본다.",
    5: "평균 이동의 조기 신호. 규칙 2보다 빠르게 잡힌다.",
    6: "작은 평균 이동이 지속되고 있다.",
    7: "산포가 비정상적으로 작다. 부분군 층별 오류나 데이터 가공을 의심한다.",
    8: "중심 부근이 비어 있다. 서로 다른 두 모집단이 섞였을 가능성이 크다.",
}

RULE_SEVERITY: Final[dict[int, str]] = {
    1: "CRITICAL",
    2: "WARNING",
    3: "WARNING",
    4: "WATCH",
    5: "WARNING",
    6: "WATCH",
    7: "WATCH",
    8: "WARNING",
}


@dataclass(frozen=True)
class RuleViolation:
    """판정 규칙 위반 1건."""

    rule_number: int
    description: str
    severity: str
    start_index: int
    end_index: int
    interpretation: str

    @property
    def length(self) -> int:
        return self.end_index - self.start_index + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_number": self.rule_number,
            "rule_name": f"NELSON_RULE_{self.rule_number}",
            "description": self.description,
            "severity": self.severity,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "point_count": self.length,
            "interpretation": self.interpretation,
        }


def _violation(
    rule_number: int,
    start_index: int,
    end_index: int,
) -> RuleViolation:
    return RuleViolation(
        rule_number=rule_number,
        description=RULE_DESCRIPTIONS[rule_number],
        severity=RULE_SEVERITY[rule_number],
        start_index=int(start_index),
        end_index=int(end_index),
        interpretation=RULE_INTERPRETATIONS[rule_number],
    )


def rule_1_beyond_three_sigma(
    values: np.ndarray,
    center: float,
    sigma: float,
) -> list[RuleViolation]:
    """1점이 3시그마를 벗어남."""
    deviation = np.abs(values - center)
    hits = np.flatnonzero(deviation > 3 * sigma)

    return [_violation(1, index, index) for index in hits]


def rule_2_nine_on_one_side(
    values: np.ndarray,
    center: float,
    sigma: float,
) -> list[RuleViolation]:
    """9점 연속 중심선 한쪽."""
    return _consecutive_same_sign(
        values=values,
        center=center,
        run_length=9,
        rule_number=2,
    )


def rule_3_six_trending(
    values: np.ndarray,
    center: float,
    sigma: float,
) -> list[RuleViolation]:
    """6점 연속 증가 또는 감소.

    연속 6점이 단조 증가 또는 단조 감소하는 경우를 찾는다.
    (차분 5개가 모두 같은 방향)
    """
    violations: list[RuleViolation] = []

    if values.size < 6:
        return violations

    differences = np.diff(values)

    for start in range(differences.size - 4):
        window = differences[start : start + 5]

        if np.all(window > 0) or np.all(window < 0):
            violations.append(_violation(3, start, start + 5))

    # 단조 구간이 6점보다 길면 겹치는 창이 여러 개 잡힌다.
    # 같은 추세를 여러 건으로 보고하지 않도록 구간을 합친다.
    return _merge_overlapping(violations)


def rule_4_fourteen_alternating(
    values: np.ndarray,
    center: float,
    sigma: float,
) -> list[RuleViolation]:
    """14점 연속 교대 증감."""
    violations: list[RuleViolation] = []

    if values.size < 14:
        return violations

    differences = np.diff(values)
    signs = np.sign(differences)

    for start in range(signs.size - 12):
        window = signs[start : start + 13]

        if np.any(window == 0):
            continue

        alternating = np.all(window[:-1] * window[1:] < 0)

        if alternating:
            violations.append(_violation(4, start, start + 13))

    return _merge_overlapping(violations)


def rule_5_two_of_three_beyond_two_sigma(
    values: np.ndarray,
    center: float,
    sigma: float,
) -> list[RuleViolation]:
    """3점 중 2점이 같은 쪽 2시그마 밖."""
    return _k_of_n_beyond_zone(
        values=values,
        center=center,
        sigma=sigma,
        zone_multiplier=2,
        window_size=3,
        required_count=2,
        rule_number=5,
    )


def rule_6_four_of_five_beyond_one_sigma(
    values: np.ndarray,
    center: float,
    sigma: float,
) -> list[RuleViolation]:
    """5점 중 4점이 같은 쪽 1시그마 밖."""
    return _k_of_n_beyond_zone(
        values=values,
        center=center,
        sigma=sigma,
        zone_multiplier=1,
        window_size=5,
        required_count=4,
        rule_number=6,
    )


def rule_7_fifteen_within_one_sigma(
    values: np.ndarray,
    center: float,
    sigma: float,
) -> list[RuleViolation]:
    """15점 연속 1시그마 안."""
    within = np.abs(values - center) < sigma

    return _consecutive_true(
        flags=within,
        run_length=15,
        rule_number=7,
    )


def rule_8_eight_beyond_one_sigma(
    values: np.ndarray,
    center: float,
    sigma: float,
) -> list[RuleViolation]:
    """8점 연속 1시그마 밖(양쪽 구분 없음)."""
    beyond = np.abs(values - center) > sigma

    return _consecutive_true(
        flags=beyond,
        run_length=8,
        rule_number=8,
    )


def _consecutive_same_sign(
    values: np.ndarray,
    center: float,
    run_length: int,
    rule_number: int,
) -> list[RuleViolation]:
    """중심선 기준 같은 쪽에 run_length 점이 연속인 구간을 찾는다."""
    violations: list[RuleViolation] = []

    above = values > center
    below = values < center

    for flags in (above, below):
        violations.extend(
            _consecutive_true(
                flags=flags,
                run_length=run_length,
                rule_number=rule_number,
            )
        )

    return sorted(violations, key=lambda item: item.start_index)


def _consecutive_true(
    flags: np.ndarray,
    run_length: int,
    rule_number: int,
) -> list[RuleViolation]:
    """불리언 배열에서 True가 run_length 이상 연속인 구간을 찾는다.

    연속 구간이 run_length 보다 길면, 겹치는 위반을 모두 보고하지 않고
    구간 전체를 1건으로 보고한다. 현장 보고서에서 같은 원인의
    위반이 수십 건으로 부풀는 것을 막는다.
    """
    violations: list[RuleViolation] = []

    if flags.size < run_length:
        return violations

    run_start = None

    for index, flag in enumerate(flags):
        if flag and run_start is None:
            run_start = index
            continue

        if not flag and run_start is not None:
            if index - run_start >= run_length:
                violations.append(
                    _violation(rule_number, run_start, index - 1)
                )

            run_start = None

    if run_start is not None and flags.size - run_start >= run_length:
        violations.append(
            _violation(rule_number, run_start, flags.size - 1)
        )

    return violations


def _k_of_n_beyond_zone(
    values: np.ndarray,
    center: float,
    sigma: float,
    zone_multiplier: int,
    window_size: int,
    required_count: int,
    rule_number: int,
) -> list[RuleViolation]:
    """n점 중 k점이 같은 쪽 특정 시그마 구역을 벗어난 경우를 찾는다."""
    violations: list[RuleViolation] = []

    if values.size < window_size or sigma <= 0:
        return violations

    threshold = zone_multiplier * sigma
    above = values - center > threshold
    below = center - values > threshold

    for start in range(values.size - window_size + 1):
        end = start + window_size

        for flags in (above, below):
            if flags[start:end].sum() >= required_count:
                violations.append(
                    _violation(rule_number, start, end - 1)
                )
                break

    return _merge_overlapping(violations)


def _merge_overlapping(
    violations: list[RuleViolation],
) -> list[RuleViolation]:
    """겹치거나 인접한 동일 규칙 위반을 하나로 합친다."""
    if not violations:
        return []

    ordered = sorted(violations, key=lambda item: item.start_index)
    merged = [ordered[0]]

    for candidate in ordered[1:]:
        last = merged[-1]

        if candidate.start_index <= last.end_index + 1:
            merged[-1] = _violation(
                candidate.rule_number,
                last.start_index,
                max(last.end_index, candidate.end_index),
            )
            continue

        merged.append(candidate)

    return merged


RULE_FUNCTIONS: Final[
    dict[int, Callable[[np.ndarray, float, float], list[RuleViolation]]]
] = {
    1: rule_1_beyond_three_sigma,
    2: rule_2_nine_on_one_side,
    3: rule_3_six_trending,
    4: rule_4_fourteen_alternating,
    5: rule_5_two_of_three_beyond_two_sigma,
    6: rule_6_four_of_five_beyond_one_sigma,
    7: rule_7_fifteen_within_one_sigma,
    8: rule_8_eight_beyond_one_sigma,
}


def evaluate_all_rules(
    values: np.ndarray,
    center_line: float,
    chart_sigma: float,
    rules: list[int] | None = None,
) -> list[RuleViolation]:
    """지정한 판정 규칙을 모두 적용한다.

    Parameters
    ----------
    values : 관리도 타점값
    center_line : 중심선
    chart_sigma : 관리도 1 시그마 폭. (UCL - CL) / 3
    rules : 적용할 규칙 번호. None 이면 8종 전부.
    """
    selected = rules if rules is not None else sorted(RULE_FUNCTIONS)

    violations: list[RuleViolation] = []

    for rule_number in selected:
        if rule_number not in RULE_FUNCTIONS:
            raise ValueError(
                f"정의되지 않은 규칙 번호입니다: {rule_number}"
            )

        violations.extend(
            RULE_FUNCTIONS[rule_number](
                np.asarray(values, dtype=float),
                float(center_line),
                float(chart_sigma),
            )
        )

    return sorted(
        violations,
        key=lambda item: (item.start_index, item.rule_number),
    )


def evaluate_chart(
    chart: ControlChart,
    rules: list[int] | None = None,
) -> list[RuleViolation]:
    """ControlChart 객체에 판정 규칙을 적용한다."""
    return evaluate_all_rules(
        values=chart.values,
        center_line=chart.center_line,
        chart_sigma=chart.chart_sigma,
        rules=rules,
    )


# 공정이 관리상태(in-control)이고 정규분포일 때 각 규칙이
# 한 타점 위치에서 우연히 발동할 확률.
#
# 판정 규칙은 원래 오경보를 낸다. 8000점을 평가하면 규칙 1만으로도
# 우연히 20건 이상 나온다. 관측 건수를 이 기대값과 비교하지 않으면
# 우연과 실제 이상을 구분할 수 없고, 모든 특성이 CRITICAL 로 보고된다.
#
# 이 값은 이항분포 공식으로 계산하지 않고 몬테카를로로 실측했다.
# 이유: 규칙 3, 4 는 연속 차분의 부호를 보는데, i.i.d. 정규 데이터에서도
# 인접한 차분끼리 상관계수 -0.5 로 음의 상관을 가진다. 독립을 가정하면
# 규칙 4 의 확률이 2 / 2^12 = 0.000244 로 나오지만, 실제로는 지그재그
# 패턴이 그보다 훨씬 자주 나타나 약 7배 크다.
# 또한 이 구현은 겹치는 구간을 하나로 합쳐 보고하므로, 창 단위 확률과
# 보고 건수가 일치하지 않는다.
#
# 검증 조건: 표준정규 4,000점 x 250회 = 1,000,000 타점 위치.
# 규칙 1 의 실측값 0.002688 이 이론값 0.0027 과 일치하는 것으로
# 시뮬레이션 자체를 검증했다. tests/test_quality_nelson.py 참조.
IN_CONTROL_ALARM_PROBABILITY: Final[dict[int, float]] = {
    1: 0.002688,
    2: 0.001901,
    3: 0.002387,
    4: 0.001655,
    5: 0.001984,
    6: 0.003432,
    7: 0.001089,
    8: 0.000057,
}


def expected_false_alarms(
    point_count: int,
    rules: list[int] | None = None,
) -> dict[str, float]:
    """관리상태 정규공정에서 우연히 발생할 규칙 위반 기대 건수.

    관측 건수가 이 기대값 수준이면 공정 이상으로 해석하지 않는다.
    기대값을 크게 초과하는 규칙만 조치 대상이다.

    주의: 겹치는 구간을 하나로 합쳐 보고하므로 실제 관측 건수는
    이 기대값보다 구조적으로 작게 나온다. 같은 규칙 안에서
    '기대보다 훨씬 많은가'를 판단하는 기준으로만 쓴다.
    """
    selected = rules if rules is not None else sorted(
        IN_CONTROL_ALARM_PROBABILITY
    )

    return {
        f"NELSON_RULE_{rule}": (
            IN_CONTROL_ALARM_PROBABILITY[rule] * point_count
        )
        for rule in selected
        if rule in IN_CONTROL_ALARM_PROBABILITY
    }


# 관측 건수가 기대 오경보의 이 배수를 넘으면 실제 신호로 본다.
SIGNAL_THRESHOLD_RATIO: Final[float] = 2.0


def summarize_violations(
    violations: list[RuleViolation],
    point_count: int | None = None,
) -> dict[str, object]:
    """위반 목록을 요약한다.

    point_count 를 주면 각 규칙의 관측 건수를 관리상태 기대 오경보와
    비교해, 우연 수준을 넘는 규칙만 신호로 분류한다.

    타점이 많으면 판정 규칙은 반드시 오경보를 낸다. 8000점이면 규칙 1만으로도
    우연히 20건 이상 나온다. 기대값과 비교하지 않고 건수만 세면
    모든 특성이 CRITICAL 로 보고되어 판정이 무의미해진다.
    """
    counts: dict[str, int] = {}

    for violation in violations:
        key = f"NELSON_RULE_{violation.rule_number}"
        counts[key] = counts.get(key, 0) + 1

    if point_count is None:
        severities = [
            violation.severity for violation in violations
        ]

        if "CRITICAL" in severities:
            overall = "CRITICAL"
        elif "WARNING" in severities:
            overall = "WARNING"
        elif "WATCH" in severities:
            overall = "WATCH"
        else:
            overall = "NORMAL"

        return {
            "total_violations": len(violations),
            "by_rule": counts,
            "overall_severity": overall,
            "signal_rules": {},
            "expected_false_alarms": {},
        }

    expected = expected_false_alarms(point_count)

    signal_rules: dict[str, dict[str, float]] = {}

    for rule_key, observed in counts.items():
        expected_count = expected.get(rule_key, 0.0)

        ratio = (
            observed / expected_count
            if expected_count > 0
            else float("inf")
        )

        if ratio >= SIGNAL_THRESHOLD_RATIO:
            signal_rules[rule_key] = {
                "observed": float(observed),
                "expected": expected_count,
                "ratio": ratio,
            }

    if not signal_rules:
        overall = "NORMAL"
    else:
        severities = [
            RULE_SEVERITY[int(rule_key.rsplit("_", 1)[1])]
            for rule_key in signal_rules
        ]

        if "CRITICAL" in severities:
            overall = "CRITICAL"
        elif "WARNING" in severities:
            overall = "WARNING"
        else:
            overall = "WATCH"

    return {
        "total_violations": len(violations),
        "by_rule": counts,
        "overall_severity": overall,
        "signal_rules": signal_rules,
        "expected_false_alarms": expected,
    }
