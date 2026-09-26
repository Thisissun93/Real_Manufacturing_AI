import pandas as pd

from src.data.generate_process_data import generate_process_data
from src.data.loader import REQUIRED_COLUMNS, validate_process_data


TEST_SAMPLE_SIZE = 100


def test_generate_process_data_row_count() -> None:
    df = generate_process_data(
        sample_size=TEST_SAMPLE_SIZE,
    )

    assert len(df) == TEST_SAMPLE_SIZE


def test_generate_process_data_required_columns() -> None:
    df = generate_process_data(
        sample_size=TEST_SAMPLE_SIZE,
    )

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    assert missing_columns == []


def test_lot_id_is_unique() -> None:
    df = generate_process_data(
        sample_size=TEST_SAMPLE_SIZE,
    )

    assert df["LOT_ID"].is_unique


def test_no_missing_values() -> None:
    df = generate_process_data(
        sample_size=TEST_SAMPLE_SIZE,
    )

    assert df.isna().sum().sum() == 0


def test_yield_range() -> None:
    df = generate_process_data(
        sample_size=TEST_SAMPLE_SIZE,
    )

    assert df["Yield"].between(0, 100).all()


def test_defect_classes() -> None:
    df = generate_process_data(
        sample_size=TEST_SAMPLE_SIZE,
    )

    allowed_classes = {
        "Normal",
        "Delamination",
    }

    generated_classes = set(
        df["Defect"].unique()
    )

    assert generated_classes.issubset(
        allowed_classes
    )


def test_delamination_yield_is_not_a_constant() -> None:
    """박리 LOT 의 수율이 상수가 아니어야 한다.

    이전 생성기는 박리 LOT 의 수율을 일괄 0.0 으로 두었다.
    그렇게 하면 수율이 불량 라벨의 결정론적 함수가 되어
    수율 관리도와 공정능력 분석이 아무 정보를 담지 못한다.
    (이 테스트는 그 동작을 요구하던 이전 테스트를 대체한 것이다.)
    """
    df = generate_process_data(sample_size=2000)

    delamination_df = df[df["Defect"] == "Delamination"]

    assert len(delamination_df) > 0
    assert delamination_df["Yield"].nunique() > 1
    assert delamination_df["Yield"].std(ddof=1) > 0


def test_yield_decreases_with_delaminated_panel_count() -> None:
    """박리 패널 수가 늘면 수율이 감소해야 한다.

    수율은 0% 에서 바닥이 잡히므로, 박리 패널이 매우 많은 구간에서는
    평균이 0 으로 동률이 된다. 물리적으로 정상이다.
    따라서 전 구간에서는 단조 비증가, 바닥에 닿지 않은 구간에서는
    엄격한 감소를 요구한다.
    """
    df = generate_process_data(sample_size=4000)

    mean_yield_by_count = (
        df.groupby("Delam_Panel_Count")["Yield"]
        .mean()
        .sort_index()
    )

    assert len(mean_yield_by_count) >= 2

    differences = mean_yield_by_count.diff().dropna()

    # 전 구간: 단조 비증가
    assert (differences <= 1e-9).all()

    # 바닥(0%)에 닿지 않은 구간: 엄격한 감소
    above_floor = mean_yield_by_count[mean_yield_by_count > 0.0]
    strict_differences = above_floor.diff().dropna()

    assert len(strict_differences) >= 2
    assert (strict_differences < 0).all()


def test_yield_stays_within_physical_bounds() -> None:
    df = generate_process_data(sample_size=2000)

    assert df["Yield"].between(0.0, 100.0).all()


def test_normal_yield_is_positive() -> None:
    df = generate_process_data(
        sample_size=TEST_SAMPLE_SIZE,
    )

    normal_df = df[
        df["Defect"] == "Normal"
    ]

    assert (
        normal_df["Yield"] > 0
    ).all()


def test_validate_process_data() -> None:
    df = generate_process_data(
        sample_size=TEST_SAMPLE_SIZE,
    )

    validated_df = validate_process_data(df)

    assert isinstance(
        validated_df,
        pd.DataFrame,
    )

    assert len(validated_df) == TEST_SAMPLE_SIZE