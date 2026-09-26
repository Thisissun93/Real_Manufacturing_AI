"""FC-BGA 패키지기판 공정 데이터 생성기.

이전 버전의 문제
----------------
공정 인자에서 품질 특성으로 가는 경로는 있었으나, 각 단계에 더해지는
측정 노이즈가 인자 변동보다 훨씬 커서 공정 인자에서 불량으로 가는 신호가
사실상 사라졌다. 실제로 확인한 결과 14개 공정 인자 중 가장 효과가 큰
CZ_Concentration 의 Cohen's d 가 -0.32 였고, 나머지는 모두 0.16 미만이었다.
그 결과 Random Forest 의 Delamination 재현율이 2.9%(136건 중 4건 검출)에
머물렀다. 모델이 잘못된 것이 아니라 데이터에 배울 것이 없었다.

또한 Machine(PRESS_01/02/03)과 Model(MODEL_A/B/C)이 무작위로 배정되고
품질에 아무 영향을 주지 않아, 설비 간 비교(ANOVA, Tukey HSD)를 해도
찾아낼 차이가 없었다.

이 버전에서 심은 구조
--------------------
1. 물리적으로 설명되는 인과 경로
   CZ 농도 -> 표면조도 -> 접착력 -> 박리
   Press2 온도/압력 -> 보이드 -> 박리
   Cure 온도/시간 -> 경화도 -> 접착력
   Anneal 온도/시간 -> 잔류응력 -> 박리

2. 교호작용 (JMP Interaction Analysis 로 잡아낼 수 있는 구조)
   Press2 온도와 압력이 '동시에' 부족할 때 박리 위험이 각각의 합보다 크다.
   선형 모델로는 완전히 잡히지 않고 트리 모델이 이득을 보는 구간이다.

3. 설비 효과 (ANOVA + Tukey HSD 로 검출되는 구조)
   PRESS_02 는 Press2 압력이 목표보다 낮게 유지되고 산포도 크다.
   PRESS_03 은 Cure 온도가 기간에 걸쳐 서서히 하강한다(드리프트).

4. 드리프트 (Nelson 규칙 2, 3 으로 검출되는 구조)
   PRESS_03 의 Cure 온도 하강은 관리한계를 벗어나지 않으면서 진행된다.
   규칙 1(3시그마 이탈)로는 잡히지 않고 규칙 3(6점 연속 감소)과
   규칙 2(9점 연속 한쪽)로 잡힌다. 관리도를 '판정'해야 하는 이유다.

5. 모델 효과
   MODEL_C 는 층수가 많아 동일 조건에서 박리에 더 민감하다.

6. 수율 연속화
   이전 버전은 Delamination LOT 의 수율을 일괄 0.0 으로 두어,
   수율이 불량 라벨의 결정론적 함수가 되었다. 관리도와 공정능력 분석이
   의미를 잃는다. 이번에는 박리 패널 수에 비례해 연속적으로 감소시킨다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from src.config import CONFIG
from src.process_spec import (
    MACHINES,
    MODELS,
    PROCESS_PARAMETERS,
    PROCESS_SPEC,
)


RANDOM_SEED: Final[int] = CONFIG["data"]["random_state"]
SAMPLE_SIZE: Final[int] = CONFIG["data"]["sample_size"]

PANEL_COUNT_PER_LOT: Final[int] = 30

# 공정 인자의 산포를 결정하는 목표 공정능력.
# 1.67 은 현실의 양산 라인보다 지나치게 안정적이어서 인자 변동이
# 거의 없어진다. 1.33 은 자동차/반도체 업계의 일반적인 관리 수준이다.
TARGET_CPK: Final[float] = 1.33

# 목표 LOT 단위 박리 발생률. 이 값에 맞춰 로짓 절편을 자동 보정한다.
TARGET_LOT_DEFECT_RATE: Final[float] = 0.12

LOT_INTERVAL_MINUTES: Final[int] = 20
PRODUCTION_START: Final[str] = "2026-01-02 08:00:00"


@dataclass(frozen=True)
class MachineProfile:
    """설비별 고유 특성.

    실제 라인에서 같은 레시피를 걸어도 설비마다 실제 도달값이 다르다.
    이 차이가 설비 간 비교 분석의 대상이다.
    """

    name: str
    # 인자별 평균 오프셋 (목표값 대비)
    parameter_offsets: dict[str, float]
    # 인자별 산포 배율 (1.0 = 기준)
    parameter_spread_multipliers: dict[str, float]
    # 기간에 걸친 선형 드리프트 (첫 LOT -> 마지막 LOT 총 변화량)
    parameter_drifts: dict[str, float]


MACHINE_PROFILES: Final[dict[str, MachineProfile]] = {
    "PRESS_01": MachineProfile(
        name="PRESS_01",
        parameter_offsets={},
        parameter_spread_multipliers={},
        parameter_drifts={},
    ),
    # 압착 압력이 목표보다 낮게 유지되고 산포도 크다.
    # Tukey HSD 에서 PRESS_02 가 나머지 두 대와 유의하게 다르게 나온다.
    "PRESS_02": MachineProfile(
        name="PRESS_02",
        parameter_offsets={
            "Press2_Pressure": -0.22,
            "Press2_Temp": -0.55,
        },
        parameter_spread_multipliers={
            "Press2_Pressure": 1.45,
            "Press2_Temp": 1.25,
        },
        parameter_drifts={},
    ),
    # Cure 온도가 기간에 걸쳐 서서히 하강한다.
    # 관리한계 안에서 진행되므로 Nelson 규칙 2, 3 으로만 잡힌다.
    "PRESS_03": MachineProfile(
        name="PRESS_03",
        parameter_offsets={},
        parameter_spread_multipliers={},
        parameter_drifts={
            "Cure_Temp": -3.4,
        },
    ),
}


# 제품 모델별 박리 민감도 (로짓 가산)
MODEL_SENSITIVITY: Final[dict[str, float]] = {
    "MODEL_A": 0.0,
    "MODEL_B": 0.18,
    # 층수가 많아 동일 조건에서 박리에 더 민감하다.
    "MODEL_C": 0.62,
}


# 박리 로짓 계수. 표준화된 결핍량(deficit)에 곱한다.
# 값이 클수록 해당 인자가 박리에 크게 기여한다.
DELAMINATION_COEFFICIENTS: Final[dict[str, float]] = {
    "adhesion_deficit": 1.35,
    "void_deficit": 0.95,
    "residual_stress": 0.45,
    "interaction_temp_pressure": 0.70,
}


def calculate_parameter_sigma(parameter_name: str) -> float:
    """목표 Cpk 로부터 공정 인자의 표준편차를 계산한다.

    양측 규격이 있으면 규격폭에서, 없으면 설비 가동범위에서 추정한다.
    """
    spec = PROCESS_SPEC[parameter_name]

    lower = spec["lsl"]
    upper = spec["usl"]

    if lower is not None and upper is not None:
        return (float(upper) - float(lower)) / (6 * TARGET_CPK)

    return (
        float(spec["equipment_max"]) - float(spec["equipment_min"])
    ) / 30.0


def generate_process_parameters(
    rng: np.random.Generator,
    machines: np.ndarray,
    sample_size: int,
) -> dict[str, np.ndarray]:
    """설비 프로필을 반영해 공정 인자를 생성한다."""
    # 0 -> 1 로 진행하는 기간 진척도. 드리프트에 사용한다.
    progress = np.linspace(0.0, 1.0, sample_size)

    parameters: dict[str, np.ndarray] = {}

    for parameter_name in PROCESS_PARAMETERS:
        spec = PROCESS_SPEC[parameter_name]
        base_sigma = calculate_parameter_sigma(parameter_name)
        target = float(spec["target"])

        offsets = np.zeros(sample_size)
        spreads = np.full(sample_size, base_sigma)
        drifts = np.zeros(sample_size)

        for machine_name, profile in MACHINE_PROFILES.items():
            mask = machines == machine_name

            if not mask.any():
                continue

            offsets[mask] = profile.parameter_offsets.get(
                parameter_name, 0.0
            )

            spreads[mask] = (
                base_sigma
                * profile.parameter_spread_multipliers.get(
                    parameter_name, 1.0
                )
            )

            total_drift = profile.parameter_drifts.get(
                parameter_name, 0.0
            )

            if total_drift != 0.0:
                drifts[mask] = total_drift * progress[mask]

        values = (
            target
            + offsets
            + drifts
            + rng.normal(0.0, 1.0, sample_size) * spreads
        )

        values = np.clip(
            values,
            float(spec["equipment_min"]),
            float(spec["equipment_max"]),
        )

        parameters[parameter_name] = np.round(values, 3)

    return parameters


def _standardized_deficit(
    values: np.ndarray,
    threshold: float,
    scale: float,
) -> np.ndarray:
    """기준값에 미달한 정도를 표준화해 0 이상의 값으로 반환한다.

    기준을 넘으면 0. 미달하면 미달량을 scale 로 나눈 값.
    한쪽 방향만 위험한 인자(압력 부족, 접착력 부족)에 사용한다.
    """
    deficit = np.clip(threshold - values, 0.0, None)

    return deficit / scale


def generate_quality_characteristics(
    dataframe: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """공정 인자로부터 품질 특성과 불량을 생성한다."""
    row_count = len(dataframe)

    # --- 1단계: CZ 조화 처리 -> 표면조도 ---------------------------------
    # 약액 농도가 낮으면 조화가 덜 되어 조도가 낮아진다.
    dataframe["CZ_Roughness"] = (
        350.0
        + 62.0 * (dataframe["CZ_Concentration"] - 10.0)
        + rng.normal(0.0, 2.6, row_count)
    ).round(2)

    # --- 2단계: 압착 -> 두께 --------------------------------------------
    press_temp_effect = (
        (dataframe["Press1_Temp"] - 100.0)
        + (dataframe["Press2_Temp"] - 100.0)
        + (dataframe["Press3_Temp"] - 100.0)
    )

    press_pressure_effect = (
        (dataframe["Press1_Pressure"] - 5.0)
        + (dataframe["Press2_Pressure"] - 10.0)
        + (dataframe["Press3_Pressure"] - 7.0)
    )

    press_time_effect = (
        (dataframe["Press1_Time"] - 30.0)
        + (dataframe["Press2_Time"] - 60.0)
        + (dataframe["Press3_Time"] - 30.0)
    )

    dataframe["Total_Thickness"] = (
        32.0
        - 0.085 * press_temp_effect
        - 0.115 * press_pressure_effect
        - 0.022 * press_time_effect
        + rng.normal(0.0, 0.22, row_count)
    ).round(3)

    # --- 3단계: 경화/어닐 -> 접착력 --------------------------------------
    # 조도가 충분해야 접착 면적이 확보된다.
    # 경화 온도/시간이 부족하면 경화도가 낮아 접착력이 떨어진다.
    cure_index = (
        0.55 * (dataframe["Cure_Temp"] - 150.0)
        + 0.16 * (dataframe["Cure_Time"] - 60.0)
    )

    dataframe["Peel_Strength"] = (
        500.0
        + 2.35 * (dataframe["CZ_Roughness"] - 350.0)
        + 9.5 * cure_index
        + 1.30 * (dataframe["Anneal_Temp"] - 200.0)
        + 0.32 * (dataframe["Anneal_Time"] - 90.0)
        + rng.normal(0.0, 6.5, row_count)
    ).round(2)

    # --- 4단계: 빌드업 표면조도 -----------------------------------------
    dataframe["ABF_Roughness"] = (
        350.0
        + 0.20 * (dataframe["Peel_Strength"] - 500.0)
        + rng.normal(0.0, 3.2, row_count)
    ).round(2)

    # --- 5단계: 박리 위험도 ---------------------------------------------
    # 접착력 부족
    adhesion_deficit = _standardized_deficit(
        values=dataframe["Peel_Strength"].to_numpy(),
        threshold=500.0,
        scale=30.0,
    )

    # 압착 압력 부족 -> 보이드
    pressure_deficit = _standardized_deficit(
        values=dataframe["Press2_Pressure"].to_numpy(),
        threshold=10.0,
        scale=0.30,
    )

    # 압착 온도 부족 -> 수지 흐름 불량
    temperature_deficit = _standardized_deficit(
        values=dataframe["Press2_Temp"].to_numpy(),
        threshold=100.0,
        scale=1.0,
    )

    void_deficit = 0.62 * pressure_deficit + 0.38 * temperature_deficit

    # 어닐 온도 부족 -> 잔류응력 잔존
    residual_stress = _standardized_deficit(
        values=dataframe["Anneal_Temp"].to_numpy(),
        threshold=200.0,
        scale=1.5,
    )

    # 교호작용: 온도와 압력이 동시에 부족할 때 위험이 곱으로 커진다.
    interaction = pressure_deficit * temperature_deficit

    model_sensitivity = (
        dataframe["Model"].map(MODEL_SENSITIVITY).to_numpy(dtype=float)
    )

    logit_without_intercept = (
        DELAMINATION_COEFFICIENTS["adhesion_deficit"] * adhesion_deficit
        + DELAMINATION_COEFFICIENTS["void_deficit"] * void_deficit
        + DELAMINATION_COEFFICIENTS["residual_stress"]
        * residual_stress
        + DELAMINATION_COEFFICIENTS["interaction_temp_pressure"]
        * interaction
        + model_sensitivity
    )

    intercept = _calibrate_intercept(
        logit_without_intercept=logit_without_intercept,
        target_lot_defect_rate=TARGET_LOT_DEFECT_RATE,
    )

    panel_probability = _sigmoid(
        intercept + logit_without_intercept
    )

    dataframe["Delam_Panel_Count"] = rng.binomial(
        n=PANEL_COUNT_PER_LOT,
        p=panel_probability,
    )

    dataframe["Defect"] = np.where(
        dataframe["Delam_Panel_Count"] > 0,
        "Delamination",
        "Normal",
    )

    # --- 6단계: 수율 ----------------------------------------------------
    # 박리 패널 수에 비례해 연속적으로 감소한다.
    # 이전 버전처럼 0.0 으로 일괄 처리하면 수율이 불량 라벨의
    # 결정론적 함수가 되어 관리도와 공정능력 분석이 무의미해진다.
    base_yield = 98.6 + rng.normal(0.0, 0.42, row_count)

    panel_loss = (
        100.0
        * dataframe["Delam_Panel_Count"].to_numpy()
        / PANEL_COUNT_PER_LOT
    )

    # 박리 패널 주변의 인접 손실을 반영해 손실을 약간 크게 잡는다.
    dataframe["Yield"] = np.clip(
        base_yield - 1.35 * panel_loss,
        0.0,
        100.0,
    ).round(2)

    return dataframe


def _sigmoid(values: np.ndarray) -> np.ndarray:
    """로짓을 확률로 변환한다."""
    return 1.0 / (1.0 + np.exp(-values))


def _lot_defect_rate(
    intercept: float,
    logit_without_intercept: np.ndarray,
) -> float:
    """절편이 주어졌을 때 기대되는 LOT 단위 박리 발생률."""
    panel_probability = _sigmoid(intercept + logit_without_intercept)

    lot_defect_probability = 1.0 - np.power(
        1.0 - panel_probability,
        PANEL_COUNT_PER_LOT,
    )

    return float(lot_defect_probability.mean())


def _calibrate_intercept(
    logit_without_intercept: np.ndarray,
    target_lot_defect_rate: float,
    lower: float = -14.0,
    upper: float = 2.0,
    iterations: int = 80,
) -> float:
    """목표 불량률에 맞도록 로짓 절편을 이분법으로 보정한다.

    계수를 조정할 때마다 불량률이 흔들리는 것을 막는다.
    불량률은 설정값으로 관리하고, 계수는 인자 간 상대적 기여도만 정한다.
    """
    for _ in range(iterations):
        middle = (lower + upper) / 2.0

        rate = _lot_defect_rate(
            intercept=middle,
            logit_without_intercept=logit_without_intercept,
        )

        if rate > target_lot_defect_rate:
            upper = middle
        else:
            lower = middle

    return (lower + upper) / 2.0


def generate_process_data(
    sample_size: int = SAMPLE_SIZE,
) -> pd.DataFrame:
    """공정 데이터를 생성한다."""
    rng = np.random.default_rng(RANDOM_SEED)

    machines = rng.choice(MACHINES, size=sample_size)
    models = rng.choice(MODELS, size=sample_size)

    timestamps = pd.date_range(
        start=PRODUCTION_START,
        periods=sample_size,
        freq=f"{LOT_INTERVAL_MINUTES}min",
    )

    data: dict[str, object] = {
        "LOT_ID": [
            f"LOT{index:06d}"
            for index in range(1, sample_size + 1)
        ],
        "Timestamp": timestamps,
        "Model": models,
        "Machine": machines,
    }

    data.update(
        generate_process_parameters(
            rng=rng,
            machines=machines,
            sample_size=sample_size,
        )
    )

    dataframe = pd.DataFrame(data)

    return generate_quality_characteristics(dataframe, rng)


def save_process_data(dataframe: pd.DataFrame) -> Path:
    """생성된 데이터를 CSV로 저장한다."""
    project_root = Path(__file__).resolve().parents[2]

    output_path = (
        project_root / "Data" / "process_monitoring_data.csv"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    return output_path


def print_generation_summary(dataframe: pd.DataFrame) -> None:
    """생성 결과를 요약 출력한다."""
    print("=" * 62)
    print("Process Data Generation Completed")
    print("=" * 62)
    print(f"Sample Size   : {len(dataframe):,}")
    print(f"Random Seed   : {RANDOM_SEED}")
    print(f"Target Cpk    : {TARGET_CPK}")
    print(f"Columns       : {len(dataframe.columns)}")
    print()

    defect_counts = dataframe["Defect"].value_counts()
    defect_rate = (
        100.0
        * defect_counts.get("Delamination", 0)
        / len(dataframe)
    )

    print("Defect 분포")
    print(defect_counts.to_string())
    print(f"박리 발생률   : {defect_rate:.2f}%")
    print()

    print("설비별 박리율")
    machine_rate = (
        dataframe.assign(
            is_defect=(dataframe["Defect"] == "Delamination").astype(
                int
            )
        )
        .groupby("Machine")["is_defect"]
        .mean()
        .mul(100)
        .round(2)
    )
    print(machine_rate.to_string())
    print()

    print("모델별 박리율")
    model_rate = (
        dataframe.assign(
            is_defect=(dataframe["Defect"] == "Delamination").astype(
                int
            )
        )
        .groupby("Model")["is_defect"]
        .mean()
        .mul(100)
        .round(2)
    )
    print(model_rate.to_string())
    print()

    print(f"평균 수율     : {dataframe['Yield'].mean():.3f}%")
    print(
        "정상 LOT 수율 : "
        f"{dataframe.loc[dataframe['Defect'] == 'Normal', 'Yield'].mean():.3f}%"
    )


def main() -> None:
    dataframe = generate_process_data()
    saved_path = save_process_data(dataframe)

    print_generation_summary(dataframe)
    print()
    print(f"저장 위치     : {saved_path}")


if __name__ == "__main__":
    main()
