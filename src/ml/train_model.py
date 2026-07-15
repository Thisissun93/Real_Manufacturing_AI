from pathlib import Path

import joblib
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
)
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


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]

    model_dir = project_root / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

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
        n_estimators=300,
        random_state=RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
    )

    model.fit(x_train, y_train)

    prediction = model.predict(x_test)
    probability = model.predict_proba(x_test)

    accuracy = accuracy_score(y_test, prediction)

    print("=" * 60)
    print("Random Forest Model Training")
    print("=" * 60)
    print(f"Train rows: {len(x_train):,}")
    print(f"Test rows: {len(x_test):,}")
    print(f"Accuracy: {accuracy:.4f}")
    print()
    print(classification_report(y_test, prediction))

    model_path = model_dir / "random_forest_defect_model.joblib"

    model_package = {
        "model": model,
        "features": FEATURES,
        "target": TARGET,
        "classes": model.classes_.tolist(),
    }

    joblib.dump(model_package, model_path)

    result_df = x_test.copy()
    result_df["Actual_Defect"] = y_test.values
    result_df["Predicted_Defect"] = prediction

    for index, class_name in enumerate(model.classes_):
        result_df[f"Probability_{class_name}"] = probability[:, index]

    prediction_path = report_dir / "model_test_predictions.csv"

    result_df.to_csv(
        prediction_path,
        index=False,
        encoding="utf-8-sig",
    )

    confusion_df = pd.DataFrame(
        confusion_matrix(
            y_test,
            prediction,
            labels=model.classes_,
        ),
        index=[f"Actual_{name}" for name in model.classes_],
        columns=[f"Predicted_{name}" for name in model.classes_],
    )

    confusion_path = report_dir / "confusion_matrix.csv"

    confusion_df.to_csv(
        confusion_path,
        encoding="utf-8-sig",
    )

    print(f"모델 저장: {model_path}")
    print(f"예측 결과 저장: {prediction_path}")
    print(f"혼동행렬 저장: {confusion_path}")


if __name__ == "__main__":
    main()