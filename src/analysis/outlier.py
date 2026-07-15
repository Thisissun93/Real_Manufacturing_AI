from pathlib import Path

import pandas as pd

from src.data.loader import load_process_data
from src.process_spec import PROCESS_SPEC


CHECK_COLUMNS = [
    "CZ_Concentration",
    "CZ_Roughness",
    "Press1_Temp",
    "Press1_Pressure",
    "Press2_Temp",
    "Press2_Pressure",
    "Press3_Temp",
    "Press3_Pressure",
    "Cure_Temp",
    "Anneal_Temp",
    "Peel_Strength",
    "ABF_Roughness",
    "Total_Thickness",
    "Yield",
]


def find_spec_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """공정 관리범위를 벗어난 LOT을 추출합니다."""
    outlier_records = []

    for column in CHECK_COLUMNS:
        spec = PROCESS_SPEC[column]
        lcl = spec["lcl"]
        ucl = spec["ucl"]

        mask = pd.Series(False, index=df.index)

        if lcl is not None:
            mask |= df[column] < lcl

        if ucl is not None:
            mask |= df[column] > ucl

        abnormal_df = df.loc[mask, ["LOT_ID", "Model", "Machine", column]].copy()

        if abnormal_df.empty:
            continue

        abnormal_df["Parameter"] = column
        abnormal_df["Value"] = abnormal_df[column]
        abnormal_df["LCL"] = lcl
        abnormal_df["UCL"] = ucl

        abnormal_df["Violation"] = abnormal_df["Value"].apply(
            lambda value: classify_violation(value, lcl, ucl)
        )

        outlier_records.append(
            abnormal_df[
                [
                    "LOT_ID",
                    "Model",
                    "Machine",
                    "Parameter",
                    "Value",
                    "LCL",
                    "UCL",
                    "Violation",
                ]
            ]
        )

    if not outlier_records:
        return pd.DataFrame(
            columns=[
                "LOT_ID",
                "Model",
                "Machine",
                "Parameter",
                "Value",
                "LCL",
                "UCL",
                "Violation",
            ]
        )

    return pd.concat(outlier_records, ignore_index=True)


def classify_violation(
    value: float,
    lcl: float | None,
    ucl: float | None,
) -> str:
    if lcl is not None and value < lcl:
        return "Below LCL"

    if ucl is not None and value > ucl:
        return "Above UCL"

    return "Normal"


def create_lot_summary(
    df: pd.DataFrame,
    outlier_df: pd.DataFrame,
) -> pd.DataFrame:
    """LOT별 이상 인자 개수와 품질 결과를 요약합니다."""
    violation_count = (
        outlier_df.groupby("LOT_ID")
        .size()
        .rename("Violation_Count")
        .reset_index()
    )

    summary_columns = [
        "LOT_ID",
        "Model",
        "Machine",
        "Defect",
        "Delam_Panel_Count",
        "Yield",
    ]

    summary_df = df[summary_columns].merge(
        violation_count,
        on="LOT_ID",
        how="left",
    )

    summary_df["Violation_Count"] = (
        summary_df["Violation_Count"]
        .fillna(0)
        .astype(int)
    )

    summary_df["Abnormal_LOT"] = (
        (summary_df["Violation_Count"] > 0)
        | (summary_df["Defect"] != "Normal")
    )

    return summary_df


def save_reports(
    outlier_df: pd.DataFrame,
    summary_df: pd.DataFrame,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    report_dir = project_root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    outlier_path = report_dir / "parameter_outliers.csv"
    summary_path = report_dir / "lot_abnormal_summary.csv"

    outlier_df.to_csv(
        outlier_path,
        index=False,
        encoding="utf-8-sig",
    )

    summary_df.to_csv(
        summary_path,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"인자별 이상값 저장: {outlier_path}")
    print(f"LOT별 요약 저장: {summary_path}")


if __name__ == "__main__":
    process_df = load_process_data()

    parameter_outliers = find_spec_outliers(process_df)
    lot_summary = create_lot_summary(
        process_df,
        parameter_outliers,
    )

    save_reports(parameter_outliers, lot_summary)

    print(f"인자별 관리범위 이탈 건수: {len(parameter_outliers):,}")
    print(
        "이상 LOT 수:",
        f"{lot_summary['Abnormal_LOT'].sum():,}",
    )