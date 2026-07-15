from pathlib import Path
import sqlite3

import pandas as pd


REQUIRED_COLUMNS = [
    "LOT_ID",
    "Model",
    "Machine",
    "CZ_Concentration",
    "CZ_Roughness",
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
    "Total_Thickness",
    "Peel_Strength",
    "ABF_Roughness",
    "Delam_Panel_Count",
    "Defect",
    "Yield",
]


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_database_path() -> Path:
    return (
        get_project_root()
        / "database"
        / "manufacturing_ai.db"
    )


def get_csv_path() -> Path:
    return (
        get_project_root()
        / "Data"
        / "process_monitoring_data.csv"
    )


def load_from_database() -> pd.DataFrame:
    database_path = get_database_path()

    if not database_path.exists():
        raise FileNotFoundError(
            f"데이터베이스가 없습니다: {database_path}"
        )

    with sqlite3.connect(database_path) as connection:
        table_check_query = """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'process_data'
        """

        table_exists = pd.read_sql_query(
            table_check_query,
            connection,
        )

        if table_exists.empty:
            raise ValueError(
                "데이터베이스에 process_data 테이블이 없습니다."
            )

        df = pd.read_sql_query(
            "SELECT * FROM process_data",
            connection,
        )

    return df


def load_from_csv() -> pd.DataFrame:
    csv_path = get_csv_path()

    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV 파일이 없습니다: {csv_path}"
        )

    return pd.read_csv(csv_path)


def validate_process_data(
    df: pd.DataFrame,
) -> pd.DataFrame:
    if df.empty:
        raise ValueError("불러온 데이터가 비어 있습니다.")

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "필수 컬럼이 누락되었습니다:\n"
            f"{missing_columns}"
        )

    duplicated_lots = df["LOT_ID"].duplicated().sum()

    if duplicated_lots > 0:
        raise ValueError(
            f"중복 LOT_ID가 {duplicated_lots:,}개 있습니다."
        )

    return df


def load_process_data(
    source: str = "database",
) -> pd.DataFrame:
    """
    제조 데이터를 불러옵니다.

    source:
        database : SQLite에서 조회
        csv      : CSV에서 조회
        auto     : SQLite 우선, 없으면 CSV 사용
    """

    if source == "database":
        df = load_from_database()

    elif source == "csv":
        df = load_from_csv()

    elif source == "auto":
        try:
            df = load_from_database()
        except (FileNotFoundError, ValueError):
            df = load_from_csv()

    else:
        raise ValueError(
            "source는 'database', 'csv', 'auto' 중 하나여야 합니다."
        )

    return validate_process_data(df)


def print_data_summary(
    df: pd.DataFrame,
) -> None:
    print("=" * 60)
    print("Process Data Summary")
    print("=" * 60)
    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns):,}")
    print(f"Missing Values: {df.isna().sum().sum():,}")
    print(f"Duplicated LOTs: {df['LOT_ID'].duplicated().sum():,}")
    print()

    print("Defect Distribution")
    print(df["Defect"].value_counts())
    print()

    print(f"Average Yield: {df['Yield'].mean():.3f}")


def main() -> None:
    process_df = load_process_data(
        source="database",
    )

    print_data_summary(process_df)


if __name__ == "__main__":
    main()