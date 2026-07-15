from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from matplotlib.backends.backend_pdf import PdfPages

from src.data.loader import load_process_data


ROLLING_WINDOW = 50


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def create_summary_page(
    pdf: PdfPages,
    df: pd.DataFrame,
) -> None:
    total_lots = len(df)
    defect_lots = (df["Defect"] != "Normal").sum()
    defect_rate = defect_lots / total_lots * 100
    average_yield = df["Yield"].mean()

    fig = plt.figure(figsize=(11.69, 8.27))
    fig.suptitle(
        "Manufacturing Process Analysis Report",
        fontsize=20,
        fontweight="bold",
        y=0.93,
    )

    summary_text = (
        f"Total LOTs: {total_lots:,}\n\n"
        f"Defect LOTs: {defect_lots:,}\n\n"
        f"Defect Rate: {defect_rate:.2f}%\n\n"
        f"Average Yield: {average_yield:.2f}%"
    )

    fig.text(
        0.12,
        0.65,
        "Process Summary",
        fontsize=16,
        fontweight="bold",
    )

    fig.text(
        0.12,
        0.35,
        summary_text,
        fontsize=14,
    )

    fig.text(
        0.12,
        0.15,
        "Generated automatically from process_monitoring_data.csv",
        fontsize=10,
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

    ax.set_title("Machine Defect Rate Comparison", fontsize=16)
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


def create_pdf_report(df: pd.DataFrame) -> Path:
    project_root = get_project_root()

    report_dir = project_root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    output_path = (
        report_dir
        / "manufacturing_process_analysis_report.pdf"
    )

    with PdfPages(output_path) as pdf:
        create_summary_page(pdf, df)
        create_yield_trend_page(pdf, df)
        create_defect_page(pdf, df)
        create_machine_page(pdf, df)
        create_quality_summary_page(pdf, df)

        metadata = pdf.infodict()
        metadata["Title"] = (
            "Manufacturing Process Analysis Report"
        )
        metadata["Author"] = "Real Manufacturing AI"
        metadata["Subject"] = (
            "Process monitoring and defect analysis"
        )

    return output_path


def main() -> None:
    process_df = load_process_data()
    output_path = create_pdf_report(process_df)

    print("=" * 60)
    print("PDF Report Generated")
    print("=" * 60)
    print(f"저장 위치: {output_path}")


if __name__ == "__main__":
    main()