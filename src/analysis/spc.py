from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from data.loader import load_process_data
from process_spec import PROCESS_SPEC


SPC_COLUMNS = [
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


def calculate_control_limits(
    series: pd.Series,
) -> tuple[float, float, float]:
    mean_value = series.mean()
    std_value = series.std(ddof=1)

    ucl = mean_value + 3 * std_value
    lcl = mean_value - 3 * std_value

    return mean_value, lcl, ucl


def calculate_cpk(
    series: pd.Series,
    lsl: float | None,
    usl: float | None,
) -> float | None:
    mean_value = series.mean()
    std_value = series.std(ddof=1)

    if std_value == 0:
        return None

    cpu = None
    cpl = None

    if usl is not None:
        cpu = (usl - mean_value) / (3 * std_value)

    if lsl is not None:
        cpl = (mean_value - lsl) / (3 * std_value)

    if cpu is not None and cpl is not None:
        return min(cpu, cpl)

    if cpu is not None:
        return cpu

    if cpl is not None:
        return cpl

    return None


def plot_spc_chart(
    df: pd.DataFrame,
    column: str,
    save: bool = True,
) -> Path | None:
    if column not in df.columns:
        raise ValueError(f"존재하지 않는 컬럼입니다: {column}")

    series = df[column].dropna().reset_index(drop=True)

    mean_value, lcl, ucl = calculate_control_limits(series)

    spec = PROCESS_SPEC[column]
    spec_lcl = spec["lcl"]
    spec_ucl = spec["ucl"]

    cpk = calculate_cpk(
        series=series,
        lsl=spec_lcl,
        usl=spec_ucl,
    )

    outlier_mask = (series < lcl) | (series > ucl)
    outlier_indices = series.index[outlier_mask]
    outlier_values = series[outlier_mask]

    x = range(len(series))

    plt.figure(figsize=(14, 6))

    plt.plot(
        x,
        series,
        linewidth=0.7,
        alpha=0.7,
        label=column,
    )

    plt.axhline(
        mean_value,
        linestyle="-",
        linewidth=1.2,
        label=f"Mean: {mean_value:.2f}",
    )

    plt.axhline(
        ucl,
        linestyle="--",
        linewidth=1.2,
        label=f"UCL: {ucl:.2f}",
    )

    plt.axhline(
        lcl,
        linestyle="--",
        linewidth=1.2,
        label=f"LCL: {lcl:.2f}",
    )

    if spec_ucl is not None:
        plt.axhline(
            spec_ucl,
            linestyle=":",
            linewidth=1.2,
            label=f"Spec UCL: {spec_ucl:.2f}",
        )

    if spec_lcl is not None:
        plt.axhline(
            spec_lcl,
            linestyle=":",
            linewidth=1.2,
            label=f"Spec LCL: {spec_lcl:.2f}",
        )

    plt.scatter(
        outlier_indices,
        outlier_values,
        s=18,
        label=f"Outliers: {len(outlier_values)}",
        zorder=3,
    )

    cpk_text = "N/A" if cpk is None else f"{cpk:.3f}"

    plt.title(f"{column} SPC Chart | Cpk: {cpk_text}")
    plt.xlabel("LOT Sequence")
    plt.ylabel(column)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()

    output_path = None

    if save:
        image_dir = get_image_directory()
        output_path = image_dir / f"{column.lower()}_spc_chart.png"
        plt.savefig(output_path, dpi=150, bbox_inches="tight")

    plt.show()
    plt.close()

    print(f"{column}")
    print(f"Mean: {mean_value:.3f}")
    print(f"LCL: {lcl:.3f}")
    print(f"UCL: {ucl:.3f}")
    print(f"Cpk: {cpk_text}")
    print(f"Outlier count: {len(outlier_values)}")
    print("-" * 50)

    return output_path


def generate_all_spc_charts(df: pd.DataFrame) -> None:
    for column in SPC_COLUMNS:
        saved_path = plot_spc_chart(df, column)
        print(f"저장 완료: {saved_path}")


if __name__ == "__main__":
    process_df = load_process_data()
    generate_all_spc_charts(process_df)