from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, classification_report
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


def main():

    project_root = Path(__file__).resolve().parents[2]

    image_dir = project_root / "images"
    image_dir.mkdir(exist_ok=True)

    report_dir = project_root / "report"
    report_dir.mkdir(exist_ok=True)

    df = load_process_data()

    X = df[FEATURES]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced",
    )

    model.fit(X_train, y_train)

    pred = model.predict(X_test)

    accuracy = accuracy_score(y_test, pred)

    print("=" * 60)
    print(f"Accuracy : {accuracy:.4f}")
    print("=" * 60)

    print(classification_report(y_test, pred))

    rf_importance = pd.DataFrame({
        "Feature": FEATURES,
        "Importance": model.feature_importances_,
    }).sort_values(
        by="Importance",
        ascending=False,
    )

    print("\nRandom Forest Feature Importance")
    print(rf_importance)

    result = permutation_importance(
        model,
        X_test,
        y_test,
        n_repeats=20,
        random_state=42,
    )

    perm_importance = pd.DataFrame({
        "Feature": FEATURES,
        "Importance": result.importances_mean,
    }).sort_values(
        by="Importance",
        ascending=False,
    )

    print("\nPermutation Importance")
    print(perm_importance)

    perm_importance.to_csv(
        report_dir / "feature_importance.csv",
        index=False,
        encoding="utf-8-sig",
    )

    plt.figure(figsize=(10,7))

    plt.barh(
        perm_importance["Feature"],
        perm_importance["Importance"],
    )

    plt.gca().invert_yaxis()

    plt.title("Permutation Feature Importance")

    plt.xlabel("Importance")

    plt.tight_layout()

    plt.savefig(
        image_dir / "permutation_feature_importance.png",
        dpi=150,
        bbox_inches="tight",
    )

    plt.show()

    plt.close()

    print("\nTop 5 Important Features")

    print(perm_importance.head())

    print("\nCSV 저장 완료")

    print(report_dir / "feature_importance.csv")

    print("\n그래프 저장 완료")

    print(image_dir / "permutation_feature_importance.png")


if __name__ == "__main__":
    main()
    