from pathlib import Path

import numpy as np
import pandas as pd

from src.process_spec import PROCESS_PARAMETERS, PROCESS_SPEC


RANDOM_SEED = 42
SAMPLE_SIZE = 5000
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

    # 관리 상·하한이 없는 조건은 설비 범위의 약 1/30 사용
    return (spec["equipment_max"] - spec["equipment_min"]) / 30


def generate_parameter(
    rng: np.random.Generator,
    parameter_name: str,
    sample_size: int,
) -> np.ndarray:
    """Target 중심의 공정조건 데이터를 생성합니다."""
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
    return 1 / (1 + np.exp(-values))


def generate_quality_parameters(
    df: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """X 인자를 기반으로 Y 품질 특성을 생성합니다."""

    # 1. CZ 농도가 높을수록 CZ 조도가 증가
    df["CZ_Roughness"] = (
        350
        + 55 * (df["CZ_Concentration"] - 10)
        + rng.normal(0, 4, len(df))
    ).clip(0, 1000).round(2)

    # 2. Press 온도와 시간이 높을수록 Total Thickness 감소
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
    ).clip(0, 37.5).round(3)

    # 3. CZ 조도가 낮을수록 Peel Strength 감소
    #    Cure/Anneal 조건이 높을수록 Peel Strength 감소
    df["Peel_Strength"] = (
        500
        + 2.2 * (df["CZ_Roughness"] - 350)
        - 2.0 * (df["Cure_Temp"] - 150)
        - 0.8 * (df["Cure_Time"] - 60)
        - 0.6 * (df["Anneal_Time"] - 90)
        - 2.0 * (df["Anneal_Temp"] - 200)
        + rng.normal(0, 12, len(df))
    ).clip(0, 1000).round(2)

    # 4. Peel Strength가 낮을수록 ABF Roughness 감소
    df["ABF_Roughness"] = (
        350
        + 0.22 * (df["Peel_Strength"] - 500)
        + rng.normal(0, 5, len(df))
    ).clip(0, 1000).round(2)

    # 5. Peel Strength와 ABF Roughness가 낮을수록
    #    Panel Delamination 발생 확률 증가
    delam_score = (
        -5.5
        + 0.018 * (500 - df["Peel_Strength"])
        + 0.025 * (350 - df["ABF_Roughness"])
    )

    panel_delam_probability = sigmoid(delam_score).clip(0, 1)

    df["Delam_Panel_Count"] = rng.binomial(
        n=PANEL_COUNT_PER_LOT,
        p=panel_delam_probability,
    )

    # 1개 Panel이라도 Delamination 발생 시 LOT 전체 불량
    df["Defect"] = np.where(
        df["Delam_Panel_Count"] > 0,
        "Delamination",
        "Normal",
    )

    # 정상 LOT은 약 97~100%, Delamination LOT은 전량 폐기
    normal_yield = rng.normal(98.5, 0.7, len(df)).clip(85, 100)

    df["Yield"] = np.where(
        df["Defect"] == "Delamination",
        0.0,
        normal_yield,
    ).round(2)

    return df


def generate_process_data(sample_size: int = SAMPLE_SIZE) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)

    data = {
        "LOT_ID": [f"LOT{i:06d}" for i in range(1, sample_size + 1)],
        "Model": rng.choice(MODELS, size=sample_size),
        "Machine": rng.choice(MACHINES, size=sample_size),
    }

    for parameter in PROCESS_PARAMETERS:
        data[parameter] = generate_parameter(
            rng=rng,
            parameter_name=parameter,
            sample_size=sample_size,
        )

    df = pd.DataFrame(data)
    df = generate_quality_parameters(df, rng)

    return df


def save_process_data(df: pd.DataFrame) -> Path:
    project_root = Path(__file__).resolve().parents[2]
    output_path = project_root / "Data" / "process_monitoring_data.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    return output_path


if __name__ == "__main__":
    process_df = generate_process_data()
    saved_path = save_process_data(process_df)

    print(f"생성 행 수: {len(process_df):,}")
    print(f"생성 열 수: {len(process_df.columns)}")
    print(f"저장 위치: {saved_path}")
    print()
    print(process_df.head())
    print()
    print("Defect 분포")
    print(process_df["Defect"].value_counts())
    print()
    print("평균 Yield")
    print(process_df["Yield"].mean())