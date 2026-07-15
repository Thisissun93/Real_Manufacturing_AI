from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from data.loader import load_process_data


COMPARE_COLUMNS = [
    "CZ_Concentration",
    "CZ_Roughness",
    "Peel_Strength",
    "ABF_Roughness",
    "Total_Thickness",
    "Yield",
]


def get_image_directory() -> Path:
    project_root = Path(__file__).resolve().parent.parent
    image_dir = project_root / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    return image_dir


def plot_defect_pareto(df: pd.DataFrame) -> Path:
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

    fig, ax1 = plt.subplots(figsize=(10, 6))

    ax1.bar(
        defect_counts.index,
        defect_counts.values,
    )
    ax1.set_xlabel("Defect")
    ax1.set_ylabel("Count")
    ax1.tick_params(axis="x", rotation=30)

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

    plt.title("Defect Pareto Chart")
    fig.tight_layout()

    output_path = get_image_directory() / "defect_pareto.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.show()
    plt.close()

    return output_path


def print_defect_summary(df: pd.DataFrame) -> None:
    summary = (
        df.groupby("Defect")[COMPARE_COLUMNS]
        .mean()
        .round(3)
    )

    print("=" * 70)
    print("Defect별 평균 공정/품질 인자")
    print("=" * 70)
    print(summary)


def plot_defect_boxplots(df: pd.DataFrame) -> None:
    image_dir = get_image_directory()

    for column in COMPARE_COLUMNS:
        defect_groups = [
            group[column].dropna().values
            for _, group in df.groupby("Defect")
        ]

        defect_labels = [
            defect_name
            for defect_name, _ in df.groupby("Defect")
        ]

        plt.figure(figsize=(10, 6))
        plt.boxplot(
            defect_groups,
            tick_labels=defect_labels,
            showfliers=True,
        )

        plt.title(f"{column} by Defect")
        plt.xlabel("Defect")
        plt.ylabel(column)
        plt.xticks(rotation=30)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        output_path = (
            image_dir
            / f"{column.lower()}_by_defect_boxplot.png"
        )

        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.show()
        plt.close()

        print(f"저장 완료: {output_path}")


if __name__ == "__main__":
    process_df = load_process_data()

    pareto_path = plot_defect_pareto(process_df)
    print(f"저장 완료: {pareto_path}")

    print_defect_summary(process_df)
    plot_defect_boxplots(process_df)