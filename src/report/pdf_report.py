from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from src.data.loader import load_process_data
from src.process_spec import PROCESS_SPEC
from src.report.process_recommendation import (
    create_process_recommendation_page,
    save_recommendation_csv,
)


ROLLING_WINDOW = 50

CAPABILITY_COLUMNS = [
    "CZ_Roughness",
    "Total_Thickness",
    "Peel_Strength",
    "ABF_Roughness",
]


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def calculate_capability(
    series: pd.Series,
    lsl: float | None,
    usl: float | None,
) -> dict:
    """
    양측 규격이면 Cpk, 단측 규격이면 Cpl 또는 Cpu를 계산합니다.
    """
    clean_series = series.dropna()

    mean_value = clean_series.mean()
    std_value = clean_series.std(ddof=1)

    if std_value == 0 or np.isnan(std_value):
        return {
            "Mean": mean_value,
            "Std": std_value,
            "Cpl": None,
            "Cpu": None,
            "Cpk": None,
            "Capability": None,
        }

    cpl = None
    cpu = None

    if lsl is not None:
        cpl = (mean_value - lsl) / (3 * std_value)

    if usl is not None:
        cpu = (usl - mean_value) / (3 * std_value)

    if cpl is not None and cpu is not None:
        cpk = min(cpl, cpu)
        capability_value = cpk
    elif cpl is not None:
        cpk = None
        capability_value = cpl
    elif cpu is not None:
        cpk = None
        capability_value = cpu
    else:
        cpk = None
        capability_value = None

    return {
        "Mean": mean_value,
        "Std": std_value,
        "Cpl": cpl,
        "Cpu": cpu,
        "Cpk": cpk,
        "Capability": capability_value,
    }


def classify_capability(
    capability_value: float | None,
) -> str:
    if capability_value is None or np.isnan(capability_value):
        return "N/A"

    if capability_value >= 1.67:
        return "Excellent"

    if capability_value >= 1.33:
        return "Capable"

    if capability_value >= 1.00:
        return "Marginal"

    return "Improvement Required"


def create_executive_summary_page(
    pdf: PdfPages,
    df: pd.DataFrame,
) -> None:
    total_lots = len(df)
    defect_lots = (df["Defect"] != "Normal").sum()
    normal_lots = total_lots - defect_lots

    defect_rate = defect_lots / total_lots * 100
    normal_rate = normal_lots / total_lots * 100
    average_yield = df["Yield"].mean()

    normal_yield = df.loc[
        df["Defect"] == "Normal",
        "Yield",
    ].mean()

    defect_counts = (
        df.loc[df["Defect"] != "Normal", "Defect"]
        .value_counts()
    )

    if defect_counts.empty:
        defect_detail = "No defect LOTs were detected."
        major_defect_text = "No major defect"
    else:
        defect_lines = [
            f"- {defect_name}: {count:,} LOTs "
            f"({count / total_lots * 100:.2f}%)"
            for defect_name, count in defect_counts.items()
        ]

        defect_detail = "\n".join(defect_lines)

        major_defect = defect_counts.index[0]
        major_count = defect_counts.iloc[0]

        major_defect_text = (
            f"{major_defect}, {major_count:,} LOTs"
        )

    conclusion = (
        f"Based on the current {total_lots:,}-LOT simulation, "
        f"the expected overall yield is {average_yield:.2f}% "
        f"and the expected defect rate is {defect_rate:.2f}%. "
        f"The largest defect category is {major_defect_text}."
    )

    fig = plt.figure(figsize=(11.69, 8.27))

    fig.suptitle(
        "Manufacturing Process Executive Summary",
        fontsize=20,
        fontweight="bold",
        y=0.94,
    )

    summary_text = (
        f"Simulation LOTs: {total_lots:,}\n\n"
        f"Normal LOTs: {normal_lots:,} ({normal_rate:.2f}%)\n\n"
        f"Defect LOTs: {defect_lots:,} ({defect_rate:.2f}%)\n\n"
        f"Overall Average Yield: {average_yield:.2f}%\n\n"
        f"Normal LOT Average Yield: {normal_yield:.2f}%"
    )

    fig.text(
        0.08,
        0.78,
        "Key Performance Indicators",
        fontsize=15,
        fontweight="bold",
    )

    fig.text(
        0.08,
        0.49,
        summary_text,
        fontsize=13,
    )

    fig.text(
        0.55,
        0.78,
        "Defect Breakdown",
        fontsize=15,
        fontweight="bold",
    )

    fig.text(
        0.55,
        0.58,
        defect_detail,
        fontsize=12,
    )

    fig.text(
        0.08,
        0.27,
        "Conclusion",
        fontsize=15,
        fontweight="bold",
    )

    fig.text(
        0.08,
        0.15,
        conclusion,
        fontsize=12,
        wrap=True,
    )

    fig.text(
        0.08,
        0.07,
        (
            "Note: The values above are simulation results generated "
            "from the current process model, not actual production forecasts."
        ),
        fontsize=9,
    )

    plt.axis("off")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def create_yield_trend_page(
    pdf: PdfPages,
    df: pd.DataFrame,
) -> None:
    trend_df = df[["LOT_ID", "Yield"]].copy()

    trend_df["Rolling_Mean"] = (
        trend_df["Yield"]
        .rolling(
            window=ROLLING_WINDOW,
            min_periods=1,
        )
        .mean()
    )

    fig, ax = plt.subplots(figsize=(11.69, 8.27))

    ax.plot(
        range(len(trend_df)),
        trend_df["Rolling_Mean"],
        linewidth=1.5,
        label=f"{ROLLING_WINDOW}-LOT Moving Average",
    )

    ax.set_title("Yield Trend", fontsize=16)
    ax.set_xlabel("LOT Sequence")
    ax.set_ylabel("Yield (%)")
    ax.grid(True, alpha=0.3)
    ax.legend()

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def create_defect_page(
    pdf: PdfPages,
    df: pd.DataFrame,
) -> None:
    defect_counts = (
        df["Defect"]
        .value_counts()
        .sort_values(ascending=False)
    )

    cumulative_ratio = (
        defect_counts.cumsum()
        / defect_counts.sum()
        * 100
    )

    fig, ax1 = plt.subplots(figsize=(11.69, 8.27))

    ax1.bar(
        defect_counts.index,
        defect_counts.values,
    )

    ax1.set_title("Defect Pareto Analysis", fontsize=16)
    ax1.set_xlabel("Defect Type")
    ax1.set_ylabel("Count")
    ax1.tick_params(axis="x", rotation=25)

    ax2 = ax1.twinx()

    ax2.plot(
        defect_counts.index,
        cumulative_ratio.values,
        marker="o",
        linewidth=1.5,
    )

    ax2.set_ylabel("Cumulative Ratio (%)")
    ax2.set_ylim(0, 110)
    ax2.axhline(
        80,
        linestyle="--",
        linewidth=1,
    )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def create_machine_page(
    pdf: PdfPages,
    df: pd.DataFrame,
) -> None:
    machine_summary = (
        df.groupby("Machine")
        .agg(
            Average_Yield=("Yield", "mean"),
            Defect_Count=(
                "Defect",
                lambda values: (values != "Normal").sum(),
            ),
            LOT_Count=("LOT_ID", "count"),
        )
        .reset_index()
    )

    machine_summary["Defect_Rate"] = (
        machine_summary["Defect_Count"]
        / machine_summary["LOT_Count"]
        * 100
    )

    fig, ax = plt.subplots(figsize=(11.69, 8.27))

    ax.bar(
        machine_summary["Machine"],
        machine_summary["Defect_Rate"],
    )

    ax.set_title(
        "Machine Defect Rate Comparison",
        fontsize=16,
    )

    ax.set_xlabel("Machine")
    ax.set_ylabel("Defect Rate (%)")
    ax.grid(True, axis="y", alpha=0.3)

    for index, value in enumerate(
        machine_summary["Defect_Rate"]
    ):
        ax.text(
            index,
            value,
            f"{value:.2f}%",
            ha="center",
            va="bottom",
        )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def create_capability_page(
    pdf: PdfPages,
    df: pd.DataFrame,
) -> None:
    capability_records = []

    for column in CAPABILITY_COLUMNS:
        spec = PROCESS_SPEC[column]

        lsl = spec["lcl"]
        usl = spec["ucl"]

        result = calculate_capability(
            series=df[column],
            lsl=lsl,
            usl=usl,
        )

        capability_name = "Cpk"

        if lsl is not None and usl is None:
            capability_name = "Cpl"

        elif lsl is None and usl is not None:
            capability_name = "Cpu"

        capability_records.append({
            "Parameter": column,
            "Mean": round(result["Mean"], 3),
            "Std": round(result["Std"], 3),
            "LSL": lsl,
            "USL": usl,
            "Index": capability_name,
            "Value": (
                None
                if result["Capability"] is None
                else round(result["Capability"], 3)
            ),
            "Assessment": classify_capability(
                result["Capability"]
            ),
        })

    capability_df = pd.DataFrame(
        capability_records
    )

    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.axis("off")

    ax.set_title(
        "Process Capability Summary",
        fontsize=16,
        pad=25,
    )

    table = ax.table(
        cellText=capability_df.values,
        colLabels=capability_df.columns,
        cellLoc="center",
        loc="center",
    )

    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.6)

    ax.text(
        0.02,
        0.12,
        (
            "Assessment guide: Excellent >= 1.67, "
            "Capable >= 1.33, Marginal >= 1.00, "
            "Improvement Required < 1.00"
        ),
        transform=ax.transAxes,
        fontsize=9,
    )

    ax.text(
        0.02,
        0.07,
        (
            "Cpk is used for two-sided specifications. "
            "Cpl or Cpu is used for one-sided specifications."
        ),
        transform=ax.transAxes,
        fontsize=9,
    )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def create_quality_summary_page(
    pdf: PdfPages,
    df: pd.DataFrame,
) -> None:
    quality_columns = [
        "CZ_Roughness",
        "Total_Thickness",
        "Peel_Strength",
        "ABF_Roughness",
        "Yield",
    ]

    summary_df = (
        df[quality_columns]
        .describe()
        .round(3)
        .T
        .reset_index()
        .rename(columns={"index": "Parameter"})
    )

    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.axis("off")

    ax.set_title(
        "Quality Parameter Summary",
        fontsize=16,
        pad=20,
    )

    table = ax.table(
        cellText=summary_df.values,
        colLabels=summary_df.columns,
        cellLoc="center",
        loc="center",
    )

    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.5)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def create_pdf_report(
    df: pd.DataFrame,
) -> Path:
    report_dir = get_project_root() / "report"
    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        report_dir
        / "manufacturing_process_analysis_report.pdf"
    )
    with PdfPages(output_path) as pdf:
        create_executive_summary_page(pdf, df)
        create_yield_trend_page(pdf, df)
        create_defect_page(pdf, df)
        create_machine_page(pdf, df)
        create_capability_page(pdf, df)
        create_process_recommendation_page(pdf, df)
        create_quality_summary_page(pdf, df)

        metadata = pdf.infodict()
        metadata["Title"] = (
            "Manufacturing Process Analysis Report"
        )
        metadata["Author"] = "Real Manufacturing AI"
        metadata["Subject"] = (
            "Process monitoring, capability and defect analysis"
        )

    return output_path


def main() -> None:
    process_df = load_process_data()

    output_path = create_pdf_report(process_df)

    recommendation_path = save_recommendation_csv(
        process_df
    )

    print("=" * 60)
    print("PDF Report Generated")
    print("=" * 60)
    print(f"PDF 저장 위치: {output_path}")
    print(f"추천 결과 저장 위치: {recommendation_path}")

if __name__ == "__main__":
    main()