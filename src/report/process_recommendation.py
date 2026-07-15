from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from src.process_spec import PROCESS_SPEC


CONTROLLABLE_FEATURES = [
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
]


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_feature_importance() -> dict[str, float]:
    """
    저장된 Random Forest 모델의 Feature Importance를 불러옵니다.

    모델이 없거나 불러오지 못하면 모든 인자에 동일한 가중치를
    적용합니다.
    """
    model_path = (
        get_project_root()
        / "models"
        / "random_forest_defect_model.joblib"
    )

    default_importance = {
        feature: 1.0
        for feature in CONTROLLABLE_FEATURES
    }

    if not model_path.exists():
        return default_importance

    try:
        model_package = joblib.load(model_path)

        model = model_package["model"]
        model_features = model_package["features"]

        importance_map = dict(
            zip(
                model_features,
                model.feature_importances_,
            )
        )

        return {
            feature: float(
                importance_map.get(feature, 0.0)
            )
            for feature in CONTROLLABLE_FEATURES
        }

    except Exception:
        return default_importance


def calculate_recommendations(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    정상 LOT과 불량 LOT의 인자 평균 차이와 모델 중요도를 조합하여
    조정 우선순위와 방향을 계산합니다.
    """
    normal_df = df[df["Defect"] == "Normal"]
    defect_df = df[df["Defect"] != "Normal"]

    if normal_df.empty:
        raise ValueError(
            "정상 LOT 데이터가 없어 추천 방향을 계산할 수 없습니다."
        )

    if defect_df.empty:
        raise ValueError(
            "불량 LOT 데이터가 없어 추천 방향을 계산할 수 없습니다."
        )

    importance_map = load_feature_importance()

    records = []

    for feature in CONTROLLABLE_FEATURES:
        if feature not in df.columns:
            continue

        specification = PROCESS_SPEC[feature]

        target = float(specification["target"])
        unit = specification["unit"]

        overall_mean = float(df[feature].mean())
        normal_mean = float(normal_df[feature].mean())
        defect_mean = float(defect_df[feature].mean())
        overall_std = float(df[feature].std(ddof=1))

        if overall_std == 0 or np.isnan(overall_std):
            standardized_difference = 0.0
        else:
            standardized_difference = (
                defect_mean - normal_mean
            ) / overall_std

        importance = float(
            importance_map.get(feature, 0.0)
        )

        priority_score = (
            abs(standardized_difference)
            * max(importance, 0.0001)
        )

        if standardized_difference > 0.05:
            direction = "Decrease"
            action = (
                f"Reduce toward target "
                f"{target:.3f} {unit}"
            )

        elif standardized_difference < -0.05:
            direction = "Increase"
            action = (
                f"Increase toward target "
                f"{target:.3f} {unit}"
            )

        else:
            direction = "Maintain"
            action = (
                f"Maintain near target "
                f"{target:.3f} {unit}"
            )

        records.append({
            "Parameter": feature,
            "Current_Mean": overall_mean,
            "Normal_Mean": normal_mean,
            "Defect_Mean": defect_mean,
            "Target": target,
            "Direction": direction,
            "Priority_Score": priority_score,
            "Action": action,
        })

    recommendation_df = pd.DataFrame(records)

    recommendation_df = recommendation_df.sort_values(
        by="Priority_Score",
        ascending=False,
    ).reset_index(drop=True)

    recommendation_df["Priority"] = (
        recommendation_df.index + 1
    )

    return recommendation_df


def create_recommendation_summary(
    recommendation_df: pd.DataFrame,
    top_n: int = 5,
) -> str:
    top_df = recommendation_df.head(top_n)

    summary_lines = []

    for _, row in top_df.iterrows():
        summary_lines.append(
            f"{int(row['Priority'])}. "
            f"{row['Parameter']}: "
            f"{row['Action']}"
        )

    return "\n".join(summary_lines)


def create_process_recommendation_page(
    pdf: PdfPages,
    df: pd.DataFrame,
) -> None:
    recommendation_df = calculate_recommendations(df)
    top_recommendations = recommendation_df.head(5).copy()

    display_columns = [
        "Priority",
        "Parameter",
        "Current_Mean",
        "Normal_Mean",
        "Defect_Mean",
        "Target",
        "Direction",
    ]

    display_df = top_recommendations[
        display_columns
    ].copy()

    numeric_columns = [
        "Current_Mean",
        "Normal_Mean",
        "Defect_Mean",
        "Target",
    ]

    display_df[numeric_columns] = (
        display_df[numeric_columns]
        .round(3)
    )

    summary_text = create_recommendation_summary(
        recommendation_df,
        top_n=5,
    )

    fig = plt.figure(figsize=(11.69, 8.27))

    fig.suptitle(
        "Process Adjustment Recommendations",
        fontsize=19,
        fontweight="bold",
        y=0.95,
    )

    fig.text(
        0.06,
        0.86,
        "Recommended Adjustment Priorities",
        fontsize=14,
        fontweight="bold",
    )

    fig.text(
        0.06,
        0.62,
        summary_text,
        fontsize=11,
        linespacing=1.7,
    )

    table_ax = fig.add_axes([
        0.05,
        0.22,
        0.90,
        0.30,
    ])

    table_ax.axis("off")

    table = table_ax.table(
        cellText=display_df.values,
        colLabels=display_df.columns,
        cellLoc="center",
        loc="center",
    )

    table.auto_set_font_size(False)
    table.set_fontsize(7.5)
    table.scale(1, 1.5)

    fig.text(
        0.06,
        0.12,
        (
            "Method: Recommendations are ranked using the standardized "
            "difference between normal and defect LOTs combined with "
            "Random Forest feature importance."
        ),
        fontsize=9,
        wrap=True,
    )

    fig.text(
        0.06,
        0.07,
        (
            "Important: These are directional recommendations derived "
            "from synthetic simulation data. They must not be applied "
            "directly to production without DOE, engineering review, "
            "and process validation."
        ),
        fontsize=9,
        wrap=True,
    )

    pdf.savefig(
        fig,
        bbox_inches="tight",
    )

    plt.close(fig)


def save_recommendation_csv(
    df: pd.DataFrame,
) -> Path:
    recommendation_df = calculate_recommendations(df)

    report_dir = get_project_root() / "report"
    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        report_dir
        / "process_adjustment_recommendations.csv"
    )

    recommendation_df.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    return output_path