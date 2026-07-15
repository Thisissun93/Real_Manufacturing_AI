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


def prepare_data(
    df: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
    pd.Series,
]:
    x = df[FEATURES]
    y = df[TARGET]

    return train_test_split(
        x,
        y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )


def train_model(
    x_train: pd.DataFrame,
    y_train: pd.Series,
) -> RandomForestClassifier:
    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        random_state=RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
    )

    model.fit(x_train, y_train)

    return model


def save_model_package(
    model: RandomForestClassifier,
) -> Path:
    model_dir = get_project_root() / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = (
        model_dir
        / "random_forest_defect_model.joblib"
    )

    model_package = {
        "model": model,
        "features": FEATURES,
        "target": TARGET,
        "classes": model.classes_.tolist(),
        "config": {
            "random_state": RANDOM_STATE,
            "test_size": TEST_SIZE,
            "n_estimators": N_ESTIMATORS,
        },
    }

    joblib.dump(
        model_package,
        model_path,
    )

    return model_path


def save_prediction_report(
    x_test: pd.DataFrame,
    y_test: pd.Series,
    prediction,
    probability,
    model: RandomForestClassifier,
) -> tuple[Path, Path]:
    report_dir = get_project_root() / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    result_df = x_test.copy()
    result_df["Actual_Defect"] = y_test.values
    result_df["Predicted_Defect"] = prediction

    for class_index, class_name in enumerate(
        model.classes_
    ):
        result_df[
            f"Probability_{class_name}"
        ] = probability[:, class_index]

    prediction_path = (
        report_dir
        / "model_test_predictions.csv"
    )

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
        index=[
            f"Actual_{class_name}"
            for class_name in model.classes_
        ],
        columns=[
            f"Predicted_{class_name}"
            for class_name in model.classes_
        ],
    )

    confusion_path = (
        report_dir
        / "confusion_matrix.csv"
    )

    confusion_df.to_csv(
        confusion_path,
        encoding="utf-8-sig",
    )

    return prediction_path, confusion_path


def main() -> None:
    df = load_process_data()

    x_train, x_test, y_train, y_test = (
        prepare_data(df)
    )

    model = train_model(
        x_train,
        y_train,
    )

    prediction = model.predict(x_test)
    probability = model.predict_proba(x_test)

    accuracy = accuracy_score(
        y_test,
        prediction,
    )

    model_path = save_model_package(model)

    prediction_path, confusion_path = (
        save_prediction_report(
            x_test=x_test,
            y_test=y_test,
            prediction=prediction,
            probability=probability,
            model=model,
        )
    )

    print("=" * 60)
    print("Random Forest Model Training")
    print("=" * 60)
    print(f"Train Rows: {len(x_train):,}")
    print(f"Test Rows: {len(x_test):,}")
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

    print(f"모델 저장: {model_path}")
    print(f"예측 결과 저장: {prediction_path}")
    print(f"혼동행렬 저장: {confusion_path}")


if __name__ == "__main__":
    main()