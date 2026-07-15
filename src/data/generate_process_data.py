from pathlib import Path

import numpy as np
import pandas as pd

from src.config import CONFIG
from src.process_spec import PROCESS_PARAMETERS, PROCESS_SPEC


RANDOM_SEED = CONFIG["data"]["random_state"]
SAMPLE_SIZE = CONFIG["data"]["sample_size"]

PANEL_COUNT_PER_LOT = 30
TARGET_CPK = 1.67

MODELS = ["MODEL_A", "MODEL_B", "MODEL_C"]
MACHINES = ["PRESS_01", "PRESS_02", "PRESS_03"]


def calculate_sigma(spec: dict) -> float:
    """관리 범위와 목표 Cpk를 이용해 표준편차를 계산합니다."""
    lcl = spec["lcl"]
    ucl = spec["ucl"]

    if lcl is not None and ucl is not None:
        return (ucl - lcl) / (6 * TARGET_CPK)

    return (
        spec["equipment_max"] - spec["equipment_min"]
    ) / 30


def generate_parameter(
    rng: np.random.Generator,
    parameter_name: str,
    sample_size: int,
) -> np.ndarray:
    """Target 중심의 공정 입력 데이터를 생성합니다."""
    spec = PROCESS_SPEC[parameter_name]
    sigma = calculate_sigma(spec)

    values = rng.normal(
        loc=spec["target"],
        scale=sigma,
        size=sample_size,
    )

    values = np.clip(
        values,
        spec["equipment_min"],
        spec["equipment_max"],
    )

    return np.round(values, 3)


def sigmoid(values: np.ndarray) -> np.ndarray:
    """입력값을 0~1 사이의 확률로 변환합니다."""
    return 1 / (1 + np.exp(-values))


def generate_quality_parameters(
    df: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """공정 입력 인자를 기반으로 품질 결과를 생성합니다."""

    df["CZ_Roughness"] = (
        350
        + 55 * (df["CZ_Concentration"] - 10)
        + rng.normal(0, 4, len(df))
    ).clip(
        PROCESS_SPEC["CZ_Roughness"]["equipment_min"],
        PROCESS_SPEC["CZ_Roughness"]["equipment_max"],
    ).round(2)

    press_temp_effect = (
        (df["Press1_Temp"] - 100)
        + (df["Press2_Temp"] - 100)
        + (df["Press3_Temp"] - 100)
    )

    press_time_effect = (
        (df["Press1_Time"] - 30)
        + (df["Press2_Time"] - 60)
        + (df["Press3_Time"] - 30)
    )

    df["Total_Thickness"] = (
        32
        - 0.08 * press_temp_effect
        - 0.025 * press_time_effect
        + rng.normal(0, 0.35, len(df))
    ).clip(
        PROCESS_SPEC["Total_Thickness"]["equipment_min"],
        PROCESS_SPEC["Total_Thickness"]["equipment_max"],
    ).round(3)

    df["Peel_Strength"] = (
        500
        + 2.2 * (df["CZ_Roughness"] - 350)
        - 2.0 * (df["Cure_Temp"] - 150)
        - 0.8 * (df["Cure_Time"] - 60)
        - 0.6 * (df["Anneal_Time"] - 90)
        - 2.0 * (df["Anneal_Temp"] - 200)
        + rng.normal(0, 12, len(df))
    ).clip(
        PROCESS_SPEC["Peel_Strength"]["equipment_min"],
        PROCESS_SPEC["Peel_Strength"]["equipment_max"],
    ).round(2)

    df["ABF_Roughness"] = (
        350
        + 0.22 * (df["Peel_Strength"] - 500)
        + rng.normal(0, 5, len(df))
    ).clip(
        PROCESS_SPEC["ABF_Roughness"]["equipment_min"],
        PROCESS_SPEC["ABF_Roughness"]["equipment_max"],
    ).round(2)

    delamination_score = (
        -5.5
        + 0.018 * (500 - df["Peel_Strength"])
        + 0.025 * (350 - df["ABF_Roughness"])
    )

    panel_delamination_probability = sigmoid(
        delamination_score
    ).clip(0, 1)

    df["Delam_Panel_Count"] = rng.binomial(
        n=PANEL_COUNT_PER_LOT,
        p=panel_delamination_probability,
    )

    df["Defect"] = np.where(
        df["Delam_Panel_Count"] > 0,
        "Delamination",
        "Normal",
    )

    normal_yield = rng.normal(
        loc=98.5,
        scale=0.7,
        size=len(df),
    ).clip(
        PROCESS_SPEC["Yield"]["lcl"],
        PROCESS_SPEC["Yield"]["equipment_max"],
    )

    df["Yield"] = np.where(
        df["Defect"] == "Delamination",
        0.0,
        normal_yield,
    ).round(2)

    return df


def generate_process_data(
    sample_size: int = SAMPLE_SIZE,
) -> pd.DataFrame:
    """설정 파일의 표본 수만큼 제조 데이터를 생성합니다."""
    rng = np.random.default_rng(RANDOM_SEED)

    data = {
        "LOT_ID": [
            f"LOT{i:06d}"
            for i in range(1, sample_size + 1)
        ],
        "Model": rng.choice(
            MODELS,
            size=sample_size,
        ),
        "Machine": rng.choice(
            MACHINES,
            size=sample_size,
        ),
    }

    for parameter in PROCESS_PARAMETERS:
        data[parameter] = generate_parameter(
            rng=rng,
            parameter_name=parameter,
            sample_size=sample_size,
        )

    process_df = pd.DataFrame(data)

    return generate_quality_parameters(
        process_df,
        rng,
    )


def save_process_data(
    df: pd.DataFrame,
) -> Path:
    """생성된 데이터를 CSV로 저장합니다."""
    project_root = Path(__file__).resolve().parents[2]

    output_path = (
        project_root
        / "Data"
        / "process_monitoring_data.csv"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    return output_path


def main() -> None:
    process_df = generate_process_data()
    saved_path = save_process_data(process_df)

    print("=" * 60)
    print("Process Data Generation Completed")
    print("=" * 60)
    print(f"Sample Size: {SAMPLE_SIZE:,}")
    print(f"Random Seed: {RANDOM_SEED}")
    print(f"생성 열 수: {len(process_df.columns)}")
    print(f"저장 위치: {saved_path}")
    print()

    print("Defect 분포")
    print(process_df["Defect"].value_counts())
    print()

    print(f"평균 Yield: {process_df['Yield'].mean():.3f}")


if __name__ == "__main__":
    main()