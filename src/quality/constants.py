"""관리도 계수 표.

부분군 크기(n)에 따른 관리도 계수를 정의한다.
값은 ASTM / AIAG SPC 매뉴얼의 표준 계수표를 따른다.

용어
----
d2 : 부분군 범위(R)의 기댓값을 모표준편차로 환산하는 계수.
     sigma_hat = R_bar / d2
d3 : 부분군 범위의 표준편차 계수.
c4 : 부분군 표준편차(s)의 편향 보정 계수. sigma_hat = s_bar / c4
A2 : X-bar 관리한계 계수. UCL = X_bar_bar +- A2 * R_bar
D3, D4 : R 관리도 한계 계수. LCL = D3 * R_bar, UCL = D4 * R_bar
B3, B4 : s 관리도 한계 계수.
"""

from typing import Final


# 부분군 범위 -> 표준편차 환산 계수
D2: Final[dict[int, float]] = {
    2: 1.128,
    3: 1.693,
    4: 2.059,
    5: 2.326,
    6: 2.534,
    7: 2.704,
    8: 2.847,
    9: 2.970,
    10: 3.078,
    11: 3.173,
    12: 3.258,
    13: 3.336,
    14: 3.407,
    15: 3.472,
}

D3_RANGE_SIGMA: Final[dict[int, float]] = {
    2: 0.853,
    3: 0.888,
    4: 0.880,
    5: 0.864,
    6: 0.848,
    7: 0.833,
    8: 0.820,
    9: 0.808,
    10: 0.797,
}

# 부분군 표준편차 편향 보정 계수
C4: Final[dict[int, float]] = {
    2: 0.7979,
    3: 0.8862,
    4: 0.9213,
    5: 0.9400,
    6: 0.9515,
    7: 0.9594,
    8: 0.9650,
    9: 0.9693,
    10: 0.9727,
}

# X-bar 관리한계 계수
A2: Final[dict[int, float]] = {
    2: 1.880,
    3: 1.023,
    4: 0.729,
    5: 0.577,
    6: 0.483,
    7: 0.419,
    8: 0.373,
    9: 0.337,
    10: 0.308,
}

# R 관리도 한계 계수
D3_LIMIT: Final[dict[int, float]] = {
    2: 0.0,
    3: 0.0,
    4: 0.0,
    5: 0.0,
    6: 0.0,
    7: 0.076,
    8: 0.136,
    9: 0.184,
    10: 0.223,
}

D4_LIMIT: Final[dict[int, float]] = {
    2: 3.267,
    3: 2.574,
    4: 2.282,
    5: 2.114,
    6: 2.004,
    7: 1.924,
    8: 1.864,
    9: 1.816,
    10: 1.777,
}

# s 관리도 한계 계수
B3: Final[dict[int, float]] = {
    2: 0.0,
    3: 0.0,
    4: 0.0,
    5: 0.0,
    6: 0.030,
    7: 0.118,
    8: 0.185,
    9: 0.239,
    10: 0.284,
}

B4: Final[dict[int, float]] = {
    2: 3.267,
    3: 2.568,
    4: 2.266,
    5: 2.089,
    6: 1.970,
    7: 1.882,
    8: 1.815,
    9: 1.761,
    10: 1.716,
}

# 개별값(I) 관리도 계수. E2 = 3 / d2(2)
E2_INDIVIDUAL: Final[float] = 3.0 / D2[2]

# 이동범위 부분군 크기
MOVING_RANGE_SUBGROUP_SIZE: Final[int] = 2


def get_d2(subgroup_size: int) -> float:
    """부분군 크기에 대한 d2 계수를 반환한다."""
    if subgroup_size not in D2:
        raise ValueError(
            "d2 계수는 부분군 크기 2~15까지만 정의되어 있습니다. "
            f"입력값: {subgroup_size}"
        )

    return D2[subgroup_size]


def get_a2(subgroup_size: int) -> float:
    """부분군 크기에 대한 A2 계수를 반환한다."""
    if subgroup_size not in A2:
        raise ValueError(
            "A2 계수는 부분군 크기 2~10까지만 정의되어 있습니다. "
            f"입력값: {subgroup_size}"
        )

    return A2[subgroup_size]


def get_range_limit_factors(
    subgroup_size: int,
) -> tuple[float, float]:
    """R 관리도의 (D3, D4) 계수를 반환한다."""
    if subgroup_size not in D4_LIMIT:
        raise ValueError(
            "R 관리도 계수는 부분군 크기 2~10까지만 정의되어 있습니다. "
            f"입력값: {subgroup_size}"
        )

    return D3_LIMIT[subgroup_size], D4_LIMIT[subgroup_size]
