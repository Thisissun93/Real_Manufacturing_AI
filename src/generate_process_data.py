from pathlib import Path

import numpy as np
import pandas as pd

from process_spec import PROCESS_PARAMETERS, PROCESS_SPEC


RANDOM_SEED = 42
SAMPLE_SIZE = 5000

MODELS = ["MODEL_A", "MODEL_B", "MODEL_C"]
MACHINES = ["PRESS_01", "PRESS_02", "PRESS_03"]


def calculate_sigma(spec: dict) -> float:
    """관리 범위가 있으면 6시그마 기준으로 표준편차를 계산합니다."""
    lcl = spec["lcl"]
    ucl = spec["ucl"]

    if lcl is not None and ucl is not None:
        return (ucl - lcl) / 6

    # 관리 상·하한이 없는 시간 조건은 설비 범위의 약 1/30을 사용합니다.
    return (spec["equipment_max"] - spec["equipment_min"]) / 30


def generate_parameter(
    rng: np.random.Generator,
    parameter_name: str,
    sample_size: int,
) -> np.ndarray:
    """Target 중심의 정규분포 데이터를 생성하고 설비 범위로 제한합니다."""
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

    return pd.DataFrame(data)


def save_process_data(df: pd.DataFrame) -> Path:
    project_root = Path(__file__).resolve().parent.parent
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
    print(process_df.head())