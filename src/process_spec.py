"""규격 정의와 공정 구조 정의.

용어를 엄격히 구분한다
----------------------
- lsl / usl (Specification Limit, 규격한계)
  설계와 고객이 정한 합부 판정 기준이다. 데이터로부터 계산되지 않는다.
  공정능력지수 Cp, Cpk, Pp, Ppk 의 분자에 들어간다.

- lcl / ucl (Control Limit, 관리한계)
  공정 자체의 변동으로부터 추정한 값이다. 이 파일에는 존재하지 않는다.
  src.quality.control_charts 에서 데이터로부터 계산한다.

이전 버전은 규격한계를 lcl/ucl 키에 담고 있었다. 두 개념을 같은 이름으로
부르면 "관리한계를 벗어났다"와 "규격을 벗어났다"가 구분되지 않는다.
전자는 공정에 변화가 생겼다는 신호이고, 후자는 불량이다. 조치가 다르다.

- equipment_min / equipment_max
  설비가 물리적으로 낼 수 있는 범위. 데이터 생성 시 클리핑에만 사용한다.
"""

from typing import Final


PROCESS_SPEC: Final[dict[str, dict[str, float | str | None]]] = {
    "CZ_Concentration": {
        "equipment_min": 0.0,
        "equipment_max": 100.0,
        "lsl": 9.5,
        "target": 10.0,
        "usl": 10.5,
        "unit": "%",
    },
    "CZ_Roughness": {
        "equipment_min": 0.0,
        "equipment_max": 1000.0,
        "lsl": 320.0,
        "target": 350.0,
        "usl": 380.0,
        "unit": "nm",
    },
    "Press1_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 200.0,
        "lsl": 97.0,
        "target": 100.0,
        "usl": 103.0,
        "unit": "°C",
    },
    "Press1_Time": {
        "equipment_min": 15.0,
        "equipment_max": 45.0,
        "lsl": None,
        "target": 30.0,
        "usl": None,
        "unit": "sec",
    },
    "Press1_Pressure": {
        "equipment_min": 0.0,
        "equipment_max": 10.0,
        "lsl": 4.0,
        "target": 5.0,
        "usl": 6.0,
        "unit": "kgf/cm²",
    },
    "Press2_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 200.0,
        "lsl": 97.0,
        "target": 100.0,
        "usl": 103.0,
        "unit": "°C",
    },
    "Press2_Time": {
        "equipment_min": 30.0,
        "equipment_max": 90.0,
        "lsl": None,
        "target": 60.0,
        "usl": None,
        "unit": "sec",
    },
    "Press2_Pressure": {
        "equipment_min": 0.0,
        "equipment_max": 20.0,
        "lsl": 9.0,
        "target": 10.0,
        "usl": 11.0,
        "unit": "kgf/cm²",
    },
    "Press3_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 200.0,
        "lsl": 97.0,
        "target": 100.0,
        "usl": 103.0,
        "unit": "°C",
    },
    "Press3_Time": {
        "equipment_min": 15.0,
        "equipment_max": 45.0,
        "lsl": None,
        "target": 30.0,
        "usl": None,
        "unit": "sec",
    },
    "Press3_Pressure": {
        "equipment_min": 0.0,
        "equipment_max": 14.0,
        "lsl": 6.0,
        "target": 7.0,
        "usl": 8.0,
        "unit": "kgf/cm²",
    },
    "Cure_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 250.0,
        "lsl": 145.0,
        "target": 150.0,
        "usl": 155.0,
        "unit": "°C",
    },
    "Cure_Time": {
        "equipment_min": 30.0,
        "equipment_max": 90.0,
        "lsl": None,
        "target": 60.0,
        "usl": None,
        "unit": "min",
    },
    "Anneal_Time": {
        "equipment_min": 0.0,
        "equipment_max": 200.0,
        "lsl": None,
        "target": 90.0,
        "usl": None,
        "unit": "min",
    },
    "Anneal_Temp": {
        "equipment_min": 0.0,
        "equipment_max": 250.0,
        "lsl": 195.0,
        "target": 200.0,
        "usl": 205.0,
        "unit": "°C",
    },
    "Peel_Strength": {
        "equipment_min": 0.0,
        "equipment_max": 1000.0,
        "lsl": 400.0,
        "target": 500.0,
        "usl": None,
        "unit": "gf/cm",
    },
    "ABF_Roughness": {
        "equipment_min": 0.0,
        "equipment_max": 1000.0,
        "lsl": 300.0,
        "target": 350.0,
        "usl": 400.0,
        "unit": "nm",
    },
    "Total_Thickness": {
        "equipment_min": 0.0,
        "equipment_max": 37.5,
        "lsl": 30.0,
        "target": 32.0,
        "usl": 34.0,
        "unit": "um",
    },
    "Yield": {
        "equipment_min": 0.0,
        "equipment_max": 100.0,
        "lsl": 95.0,
        "target": 98.0,
        "usl": None,
        "unit": "%",
    },
}


PROCESS_PARAMETERS: Final[list[str]] = [
    "CZ_Concentration",
    "Press1_Temp",
    "Press1_Time",
    "Press1_Pressure",
    "Press2_Temp",
    "Press2_Time",
    "Press2_Pressure",
    "Press3_Temp",
    "Press3_Time",
    "Press3_Pressure",
    "Cure_Temp",
    "Cure_Time",
    "Anneal_Time",
    "Anneal_Temp",
]


QUALITY_PARAMETERS: Final[list[str]] = [
    "CZ_Roughness",
    "Peel_Strength",
    "ABF_Roughness",
    "Total_Thickness",
    "Yield",
]


# 공정능력 분석 대상. 양측 또는 단측 규격이 정의된 품질 특성.
CAPABILITY_CHARACTERISTICS: Final[list[str]] = [
    "CZ_Roughness",
    "Peel_Strength",
    "ABF_Roughness",
    "Total_Thickness",
    "Yield",
]


MODELS: Final[list[str]] = ["MODEL_A", "MODEL_B", "MODEL_C"]

MACHINES: Final[list[str]] = ["PRESS_01", "PRESS_02", "PRESS_03"]

OPERATORS: Final[list[str]] = ["OP_A", "OP_B", "OP_C"]


def get_spec_limits(
    characteristic: str,
) -> tuple[float | None, float | None]:
    """(LSL, USL) 을 반환한다."""
    if characteristic not in PROCESS_SPEC:
        raise ValueError(
            f"규격이 정의되지 않은 특성입니다: {characteristic}"
        )

    spec = PROCESS_SPEC[characteristic]

    return spec["lsl"], spec["usl"]


def get_target(characteristic: str) -> float | None:
    """목표값을 반환한다."""
    if characteristic not in PROCESS_SPEC:
        raise ValueError(
            f"규격이 정의되지 않은 특성입니다: {characteristic}"
        )

    return PROCESS_SPEC[characteristic]["target"]


def get_tolerance(characteristic: str) -> float | None:
    """규격 공차(USL - LSL)를 반환한다.

    한쪽 규격만 있으면 공차를 정의할 수 없으므로 None 을 반환한다.
    %P/T 계산에 사용한다.
    """
    lower, upper = get_spec_limits(characteristic)

    if lower is None or upper is None:
        return None

    return float(upper) - float(lower)


def get_unit(characteristic: str) -> str:
    """단위를 반환한다."""
    if characteristic not in PROCESS_SPEC:
        return ""

    return str(PROCESS_SPEC[characteristic].get("unit", ""))


def build_capability_specifications() -> dict[
    str, dict[str, float | None]
]:
    """공정능력 분석 모듈에 넘길 규격 딕셔너리를 만든다."""
    specifications: dict[str, dict[str, float | None]] = {}

    for characteristic in CAPABILITY_CHARACTERISTICS:
        lower, upper = get_spec_limits(characteristic)

        specifications[characteristic] = {
            "lsl": lower,
            "usl": upper,
            "target": get_target(characteristic),
        }

    return specifications
