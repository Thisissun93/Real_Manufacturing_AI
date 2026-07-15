from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.data.loader import load_process_data


CORR_COLUMNS = [
    "CZ_Concentration",
    "CZ_Roughness",
    "Press1_Temp",
    "Press2_Temp",
    "Press3_Temp",
    "Total_Thickness",
    "Peel_Strength",
    "ABF_Roughness",
    "Yield",
]


def get_image_directory():
    project_root = Path(__file__).resolve().parent.parent
    image_dir = project_root / "images"
    image_dir.mkdir(exist_ok=True)

    return image_dir


def draw_correlation(df):

    corr = df[CORR_COLUMNS].corr()

    fig, ax = plt.subplots(figsize=(10,8))

    im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)

    ax.set_xticks(range(len(CORR_COLUMNS)))
    ax.set_xticklabels(CORR_COLUMNS, rotation=45, ha="right")

    ax.set_yticks(range(len(CORR_COLUMNS)))
    ax.set_yticklabels(CORR_COLUMNS)

    for i in range(len(CORR_COLUMNS)):
        for j in range(len(CORR_COLUMNS)):
            ax.text(
                j,
                i,
                f"{corr.iloc[i,j]:.2f}",
                ha="center",
                va="center",
                fontsize=8,
            )

    plt.title("Correlation Matrix")

    plt.colorbar(im)

    plt.tight_layout()

    output = get_image_directory() / "correlation_matrix.png"

    plt.savefig(output, dpi=150)

    plt.show()

    print(f"저장 완료 : {output}")


if __name__ == "__main__":

    df = load_process_data()

    draw_correlation(df)