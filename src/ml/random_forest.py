from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

from src.config import CONFIG
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

RANDOM_STATE = CONFIG["data"]["random_state"]
TEST_SIZE = CONFIG["model"]["test_size"]
N_ESTIMATORS = CONFIG["model"]["n_estimators"]


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> None:
    project_root = get_project_root()

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
        n_estimators=N_ESTIMATORS,
        random_state=RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
    )

    model.fit(x_train, y_train)

    prediction = model.predict(x_test)

    accuracy = accuracy_score(
        y_test,
        prediction,
    )

    print("=" * 60)
    print("Random Forest Analysis")
    print("=" * 60)
    print(f"Random State: {RANDOM_STATE}")
    print(f"Test Size: {TEST_SIZE}")
    print(f"N Estimators: {N_ESTIMATORS}")
    print(f"Accuracy: {accuracy:.4f}")
    print()

    print("Classification Report")
    print(
        classification_report(
            y_test,
            prediction,
            zero_division=0,
        )
    )

    rf_importance = pd.DataFrame({
        "Feature": FEATURES,
        "RF_Importance": model.feature_importances_,
    }).sort_values(
        by="RF_Importance",
        ascending=False,
    )

    permutation_result = permutation_importance(
        model,
        x_test,
        y_test,
        n_repeats=20,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    permutation_df = pd.DataFrame({
        "Feature": FEATURES,
        "Permutation_Importance":
            permutation_result.importances_mean,
        "Permutation_Std":
            permutation_result.importances_std,
    }).sort_values(
        by="Permutation_Importance",
        ascending=False,
    )

    importance_df = rf_importance.merge(
        permutation_df,
        on="Feature",
        how="left",
    )

    importance_path = (
        report_dir
        / "feature_importance.csv"
    )

    importance_df.to_csv(
        importance_path,
        index=False,
        encoding="utf-8-sig",
    )

    plt.figure(figsize=(10, 7))

    plt.barh(
        permutation_df["Feature"],
        permutation_df["Permutation_Importance"],
        xerr=permutation_df["Permutation_Std"],
    )

    plt.gca().invert_yaxis()
    plt.title("Permutation Feature Importance")
    plt.xlabel("Importance")
    plt.ylabel("Feature")
    plt.tight_layout()

    image_path = (
        image_dir
        / "permutation_feature_importance.png"
    )

    plt.savefig(
        image_path,
        dpi=150,
        bbox_inches="tight",
    )

    plt.show()
    plt.close()

    print()
    print("Top 5 Important Features")
    print(
        permutation_df.head(5).to_string(index=False)
    )

    print()
    print(f"CSV 저장: {importance_path}")
    print(f"그래프 저장: {image_path}")


if __name__ == "__main__":
    main()