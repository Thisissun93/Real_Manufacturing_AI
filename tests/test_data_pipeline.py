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


def test_delamination_yield_is_zero() -> None:
    df = generate_process_data(
        sample_size=TEST_SAMPLE_SIZE,
    )

    delamination_df = df[
        df["Defect"] == "Delamination"
    ]

    assert (
        delamination_df["Yield"] == 0
    ).all()


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