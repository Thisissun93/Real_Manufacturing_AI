from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
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


def main() -> None:
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

    print(f"Accuracy: {accuracy:.4f}")
    print()
    print("Classification Report")
    print(classification_report(y_test, pred))

    feature_importance = pd.DataFrame({
        "Feature": FEATURES,
        "Importance": model.feature_importances_,
    }).sort_values(
        by="Importance",
        ascending=False,
    )

    print()
    print("Feature Importance")
    print(feature_importance)

    project_root = Path(__file__).resolve().parents[2]
    image_dir = project_root / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(10, 7))
    plt.barh(
        feature_importance["Feature"],
        feature_importance["Importance"],
    )

    plt.gca().invert_yaxis()
    plt.title("Random Forest Feature Importance")
    plt.xlabel("Importance")
    plt.ylabel("Feature")
    plt.tight_layout()

    output_path = image_dir / "random_forest_feature_importance.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.show()
    plt.close()

    print(f"저장 완료: {output_path}")


if __name__ == "__main__":
    main()