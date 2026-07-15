from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = [
    "LOT_ID",
    "Model",
    "Machine",
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
    "CZ_Roughness",
    "Total_Thickness",
    "Peel_Strength",
    "ABF_Roughness",
    "Delam_Panel_Count",
    "Defect",
    "Yield",
]


def get_data_path() -> Path:
    """프로젝트의 공정 데이터 파일 경로를 반환합니다."""
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "Data" / "process_monitoring_data.csv"


def load_process_data(file_path: Path | None = None) -> pd.DataFrame:
    """CSV 파일을 불러오고 기본 유효성을 검사합니다."""
    path = file_path or get_data_path()

    if not path.exists():
        raise FileNotFoundError(
            f"데이터 파일을 찾을 수 없습니다: {path}\n"
            "먼저 generate_process_data.py를 실행하세요."
        )

    df = pd.read_csv(path)

    if df.empty:
        raise ValueError("데이터가 비어 있습니다.")

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"필수 컬럼이 누락되었습니다: {missing_columns}"
        )

    return df


def print_data_summary(df: pd.DataFrame) -> None:
    """데이터의 구조와 품질을 요약 출력합니다."""
    print("=" * 60)
    print("1. 데이터 크기")
    print("=" * 60)
    print(f"행 수: {len(df):,}")
    print(f"열 수: {len(df.columns)}")

    print("\n" + "=" * 60)
    print("2. 컬럼 목록")
    print("=" * 60)
    for index, column in enumerate(df.columns, start=1):
        print(f"{index:02d}. {column}")

    print("\n" + "=" * 60)
    print("3. 결측치")
    print("=" * 60)
    missing = df.isna().sum()
    missing = missing[missing > 0]

    if missing.empty:
        print("결측치 없음")
    else:
        print(missing)

    print("\n" + "=" * 60)
    print("4. 중복 LOT_ID")
    print("=" * 60)
    duplicated_lots = df["LOT_ID"].duplicated().sum()
    print(f"중복 LOT 수: {duplicated_lots:,}")

    print("\n" + "=" * 60)
    print("5. Defect 분포")
    print("=" * 60)
    defect_summary = df["Defect"].value_counts(dropna=False)
    defect_ratio = (
        df["Defect"]
        .value_counts(normalize=True, dropna=False)
        .mul(100)
        .round(2)
    )

    defect_table = pd.DataFrame({
        "Count": defect_summary,
        "Ratio_%": defect_ratio,
    })
    print(defect_table)

    print("\n" + "=" * 60)
    print("6. Yield 요약")
    print("=" * 60)
    print(df["Yield"].describe().round(3))

    print("\n" + "=" * 60)
    print("7. 주요 품질 인자 요약")
    print("=" * 60)
    quality_columns = [
        "CZ_Roughness",
        "Total_Thickness",
        "Peel_Strength",
        "ABF_Roughness",
        "Delam_Panel_Count",
        "Yield",
    ]
    print(df[quality_columns].describe().round(3).T)

    print("\n" + "=" * 60)
    print("8. 데이터 샘플")
    print("=" * 60)
    print(df.head())


if __name__ == "__main__":
    process_df = load_process_data()
    print_data_summary(process_df)