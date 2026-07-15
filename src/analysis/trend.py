from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.data.loader import load_process_data


TREND_COLUMNS = [
    "Yield",
    "Peel_Strength",
    "CZ_Roughness",
    "Total_Thickness",
]

ROLLING_WINDOW = 50


def get_image_directory() -> Path:
    project_root = Path(__file__).resolve().parent.parent
    image_dir = project_root / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    return image_dir


def plot_lot_trend(
    df: pd.DataFrame,
    column: str,
    save: bool = True,
) -> Path | None:
    if column not in df.columns:
        raise ValueError(f"존재하지 않는 컬럼입니다: {column}")

    plot_df = df[["LOT_ID", column]].copy()
    plot_df["Rolling_Mean"] = (
        plot_df[column]
        .rolling(window=ROLLING_WINDOW, min_periods=1)
        .mean()
    )

    x = range(len(plot_df))

    plt.figure(figsize=(14, 6))
    plt.plot(
        x,
        plot_df["Rolling_Mean"],
        linewidth=1.5,
        label=f"{ROLLING_WINDOW}-LOT Moving Average",
    )

    plt.title(f"{column} Lot Trend")
    plt.xlabel("LOT sequence")
    plt.ylabel(column)
    plt.grid(True, alpha=0.3)
    plt.legend()

    tick_interval = max(len(plot_df) // 10, 1)
    tick_positions = list(range(0, len(plot_df), tick_interval))

    plt.xticks(
        ticks=tick_positions,
        labels=plot_df["LOT_ID"].iloc[tick_positions],
        rotation=45,
    )

    plt.tight_layout()

    output_path = None

    if save:
        image_dir = get_image_directory()
        output_path = image_dir / f"{column.lower()}_lot_trend.png"
        plt.savefig(output_path, dpi=150, bbox_inches="tight")

    plt.show()
    plt.close()

    return output_path


def generate_all_trend_charts(df: pd.DataFrame) -> None:
    for column in TREND_COLUMNS:
        saved_path = plot_lot_trend(df, column)
        print(f"저장 완료: {saved_path}")


if __name__ == "__main__":
    process_df = load_process_data()
    generate_all_trend_charts(process_df)