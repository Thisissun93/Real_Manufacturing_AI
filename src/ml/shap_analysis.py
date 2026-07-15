from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import shap

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

from src.data.loader import load_process_data


FEATURES = [
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
]

TARGET = "Defect"
RANDOM_STATE = 42
TEST_SIZE = 0.2
SHAP_SAMPLE_SIZE = 500


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]

    image_dir = project_root / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    report_dir = project_root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    df = load_process_data()

    x = df[FEATURES]
    y = df[TARGET]

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=RANDOM_STATE,
        class_weight="balanced",
    )

    model.fit(x_train, y_train)

    sample_size = min(SHAP_SAMPLE_SIZE, len(x_test))
    x_sample = x_test.sample(
        n=sample_size,
        random_state=RANDOM_STATE,
    )

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(x_sample)

    class_names = list(model.classes_)

    if "Delamination" not in class_names:
        raise ValueError(
            "모델 클래스에 'Delamination'이 없습니다. "
            f"현재 클래스: {class_names}"
        )

    delam_class_index = class_names.index("Delamination")

    if isinstance(shap_values, list):
        delam_shap_values = shap_values[delam_class_index]
    else:
        if shap_values.ndim == 3:
            delam_shap_values = shap_values[:, :, delam_class_index]
        else:
            delam_shap_values = shap_values

    shap.summary_plot(
        delam_shap_values,
        x_sample,
        show=False,
    )
    plt.tight_layout()

    summary_path = image_dir / "shap_summary.png"
    plt.savefig(
        summary_path,
        dpi=150,
        bbox_inches="tight",
    )
    plt.close()

    shap.summary_plot(
        delam_shap_values,
        x_sample,
        plot_type="bar",
        show=False,
    )
    plt.tight_layout()

    bar_path = image_dir / "shap_bar.png"
    plt.savefig(
        bar_path,
        dpi=150,
        bbox_inches="tight",
    )
    plt.close()

    shap_importance = pd.DataFrame({
        "Feature": FEATURES,
        "Mean_Abs_SHAP": abs(delam_shap_values).mean(axis=0),
    }).sort_values(
        by="Mean_Abs_SHAP",
        ascending=False,
    )

    csv_path = report_dir / "shap_importance.csv"
    shap_importance.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )

    print("=" * 60)
    print("SHAP 분석 완료")
    print("=" * 60)
    print()
    print("Top 10 SHAP Features")
    print(shap_importance.head(10))
    print()
    print(f"요약 그래프: {summary_path}")
    print(f"막대그래프: {bar_path}")
    print(f"CSV 리포트: {csv_path}")


if __name__ == "__main__":
    main()