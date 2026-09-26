"""측정시스템 분석(MSA) 데이터 생성기.

Gage R&R 연구의 표준 설계를 따른다.

  시료(Part) 10개 x 작업자(Operator) 3명 x 반복(Replicate) 3회 = 90회 측정

현장에서 계측기 검교정과 설비 간 비교를 할 때 확인하는 항목이
이 설계로 분리된다.

  - 같은 작업자가 같은 시료를 반복 측정했을 때의 산포 -> 반복성(EV)
  - 작업자가 바뀔 때 생기는 산포                       -> 재현성(AV)
  - 시료 자체가 실제로 다른 정도                       -> 부품 변동(PV)

심어 놓은 구조
-------------
1. OP_C 는 측정값이 계통적으로 낮게 나온다(작업자 편향).
   재현성(AV)이 검출되도록 하는 요인이다.
2. OP_B 는 반복 측정 산포가 크다(측정 자세 불안정).
3. 두꺼운 시료에서 OP_C 의 편향이 더 커진다(부품 x 작업자 교호작용).
   교호작용이 유의하게 나와 오차항에 통합되지 않는 경우를 보여준다.
4. %GRR 이 10%와 30% 사이에 들어오도록 조정했다.
   '적합' 또는 '부적합'으로 자동 판정되는 값보다,
   '조건부 적합'이 나와야 판정 근거를 설명할 일이 생긴다.

기준값 데이터
------------
편향(Bias)과 선형성(Linearity) 평가를 위해 기준값이 알려진
표준 시료 측정 데이터도 함께 생성한다. 계측기 검교정에서 실제로
확인하는 항목이다.
"""

from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from src.config import CONFIG
from src.process_spec import OPERATORS, PROCESS_SPEC


RANDOM_SEED: Final[int] = CONFIG["data"]["random_state"]

MSA_CONFIG: Final[dict] = CONFIG.get("msa", {})

PART_COUNT: Final[int] = int(MSA_CONFIG.get("part_count", 10))
OPERATOR_COUNT: Final[int] = int(MSA_CONFIG.get("operator_count", 3))
REPLICATE_COUNT: Final[int] = int(
    MSA_CONFIG.get("replicate_count", 3)
)
CHARACTERISTIC: Final[str] = str(
    MSA_CONFIG.get("characteristic", "Total_Thickness")
)

# 시료 간 실제 두께 차이의 표준편차 [um]
PART_VARIATION_SIGMA: Final[float] = 0.62

# 계측기 반복성 표준편차 [um]
BASE_REPEATABILITY_SIGMA: Final[float] = 0.105

# 작업자별 계통 편향 [um]
OPERATOR_BIAS: Final[dict[str, float]] = {
    "OP_A": 0.000,
    "OP_B": 0.035,
    "OP_C": -0.115,
}

# 작업자별 반복성 배율
OPERATOR_REPEATABILITY_MULTIPLIER: Final[dict[str, float]] = {
    "OP_A": 1.00,
    "OP_B": 1.55,
    "OP_C": 1.05,
}

# 부품 x 작업자 교호작용 계수.
# 시료가 두꺼울수록 OP_C 의 편향이 커진다.
INTERACTION_COEFFICIENT: Final[dict[str, float]] = {
    "OP_A": 0.000,
    "OP_B": 0.010,
    "OP_C": -0.075,
}


def generate_gage_rnr_data(
    part_count: int = PART_COUNT,
    operator_count: int = OPERATOR_COUNT,
    replicate_count: int = REPLICATE_COUNT,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """Gage R&R 연구용 균형 교차 설계 데이터를 생성한다."""
    rng = np.random.default_rng(seed)

    operators = OPERATORS[:operator_count]
    target = float(PROCESS_SPEC[CHARACTERISTIC]["target"])

    # 시료의 참값
    part_true_values = target + rng.normal(
        0.0,
        PART_VARIATION_SIGMA,
        part_count,
    )

    part_centered = part_true_values - part_true_values.mean()

    records: list[dict[str, object]] = []

    for part_index in range(part_count):
        part_id = f"PART_{part_index + 1:02d}"
        true_value = float(part_true_values[part_index])

        for operator in operators:
            bias = OPERATOR_BIAS.get(operator, 0.0)

            interaction = INTERACTION_COEFFICIENT.get(
                operator, 0.0
            ) * float(part_centered[part_index])

            repeatability_sigma = (
                BASE_REPEATABILITY_SIGMA
                * OPERATOR_REPEATABILITY_MULTIPLIER.get(operator, 1.0)
            )

            for replicate in range(1, replicate_count + 1):
                measured = (
                    true_value
                    + bias
                    + interaction
                    + rng.normal(0.0, repeatability_sigma)
                )

                records.append(
                    {
                        "Part": part_id,
                        "Operator": operator,
                        "Replicate": replicate,
                        "TrueValue": round(true_value, 4),
                        CHARACTERISTIC: round(measured, 4),
                    }
                )

    return pd.DataFrame(records)


def generate_bias_study_data(
    standard_count: int = 12,
    repeats: int = 5,
    seed: int = RANDOM_SEED + 1,
) -> pd.DataFrame:
    """편향과 선형성 평가용 표준 시료 측정 데이터를 생성한다.

    기준값(Reference)이 알려진 표준 시료를 반복 측정한다.
    계측기가 전 구간에서 일정하게 치우쳐 있는지(편향),
    구간에 따라 치우침이 달라지는지(선형성)를 본다.

    심어 놓은 구조: 측정값이 전 구간에서 +0.045 um 높게 나오고(편향),
    두꺼운 쪽에서 기울기가 1보다 작아진다(선형성 이탈).
    """
    rng = np.random.default_rng(seed)

    lower, upper = 30.6, 33.4

    reference_values = np.linspace(lower, upper, standard_count)

    systematic_bias = 0.045
    slope = 0.978

    records: list[dict[str, object]] = []

    for standard_index, reference in enumerate(reference_values, 1):
        for repeat in range(1, repeats + 1):
            measured = (
                systematic_bias
                + slope * reference
                + (1.0 - slope) * float(reference_values.mean())
                + rng.normal(0.0, BASE_REPEATABILITY_SIGMA)
            )

            records.append(
                {
                    "Standard": f"STD_{standard_index:02d}",
                    "Repeat": repeat,
                    "Reference": round(float(reference), 4),
                    CHARACTERISTIC: round(float(measured), 4),
                }
            )

    return pd.DataFrame(records)


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def save_msa_data(
    gage_data: pd.DataFrame,
    bias_data: pd.DataFrame,
) -> tuple[Path, Path]:
    """MSA 데이터를 CSV로 저장한다."""
    data_dir = get_project_root() / "Data"
    data_dir.mkdir(parents=True, exist_ok=True)

    gage_path = data_dir / "msa_gage_rnr_data.csv"
    bias_path = data_dir / "msa_bias_study_data.csv"

    gage_data.to_csv(gage_path, index=False, encoding="utf-8-sig")
    bias_data.to_csv(bias_path, index=False, encoding="utf-8-sig")

    return gage_path, bias_path


def main() -> None:
    gage_data = generate_gage_rnr_data()
    bias_data = generate_bias_study_data()

    gage_path, bias_path = save_msa_data(gage_data, bias_data)

    print("=" * 62)
    print("MSA Data Generation Completed")
    print("=" * 62)
    print(f"측정 특성      : {CHARACTERISTIC}")
    print(
        f"Gage R&R 설계  : 시료 {PART_COUNT} x "
        f"작업자 {OPERATOR_COUNT} x 반복 {REPLICATE_COUNT} = "
        f"{len(gage_data)}회"
    )
    print(f"편향 연구      : {len(bias_data)}회")
    print()

    print("작업자별 측정 평균")
    print(
        gage_data.groupby("Operator")[CHARACTERISTIC]
        .agg(["mean", "std"])
        .round(4)
        .to_string()
    )
    print()

    print(f"Gage R&R 저장  : {gage_path}")
    print(f"편향 연구 저장 : {bias_path}")


if __name__ == "__main__":
    main()
