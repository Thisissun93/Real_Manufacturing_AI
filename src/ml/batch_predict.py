from pathlib import Path

import joblib
import pandas as pd


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_model_package() -> dict:
    model_path = (
        get_project_root()
        / "models"
        / "random_forest_defect_model.joblib"
    )

    if not model_path.exists():
        raise FileNotFoundError(
            f"모델 파일이 없습니다: {model_path}\n"
            "먼저 python -m src.ml.train_model 을 실행하세요."
        )

    return joblib.load(model_path)


def load_input_data(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(
            f"입력 CSV 파일이 없습니다: {file_path}"
        )

    df = pd.read_csv(file_path)

    if df.empty:
        raise ValueError("입력 CSV 파일이 비어 있습니다.")

    return df


def validate_features(
    df: pd.DataFrame,
    features: list[str],
) -> None:
    missing_features = [
        feature
        for feature in features
        if feature not in df.columns
    ]

    if missing_features:
        raise ValueError(
            "예측에 필요한 컬럼이 누락되었습니다:\n"
            f"{missing_features}"
        )


def predict_defects(
    df: pd.DataFrame,
    model_package: dict,
) -> pd.DataFrame:
    model = model_package["model"]
    features = model_package["features"]
    classes = model_package["classes"]

    validate_features(df, features)

    input_x = df[features]

    predicted_classes = model.predict(input_x)
    predicted_probabilities = model.predict_proba(input_x)

    result_df = df.copy()
    result_df["Predicted_Defect"] = predicted_classes

    for class_index, class_name in enumerate(classes):
        result_df[f"Probability_{class_name}"] = (
            predicted_probabilities[:, class_index] * 100
        ).round(3)

    probability_columns = [
        f"Probability_{class_name}"
        for class_name in classes
    ]

    result_df["Max_Probability_%"] = (
        result_df[probability_columns]
        .max(axis=1)
        .round(3)
    )

    result_df["Prediction_Status"] = result_df[
        "Predicted_Defect"
    ].apply(
        lambda value: (
            "Normal"
            if value == "Normal"
            else "Defect Risk"
        )
    )

    return result_df


def save_prediction_report(
    prediction_df: pd.DataFrame,
) -> Path:
    report_dir = get_project_root() / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    output_path = report_dir / "batch_prediction_result.csv"

    prediction_df.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    return output_path


def print_prediction_summary(
    prediction_df: pd.DataFrame,
) -> None:
    print("=" * 60)
    print("Batch Defect Prediction Summary")
    print("=" * 60)

    print(f"예측 LOT 수: {len(prediction_df):,}")

    print()
    print("예측 불량 분포")
    print(
        prediction_df["Predicted_Defect"]
        .value_counts()
    )

    print()
    print("평균 예측 확률")
    print(
        prediction_df["Max_Probability_%"]
        .mean()
        .round(3)
    )


def main() -> None:
    project_root = get_project_root()

    input_path = (
        project_root
        / "Data"
        / "process_monitoring_data.csv"
    )

    model_package = load_model_package()
    input_df = load_input_data(input_path)

    prediction_df = predict_defects(
        input_df,
        model_package,
    )

    output_path = save_prediction_report(
        prediction_df
    )

    print_prediction_summary(prediction_df)

    print()
    print(f"예측 결과 저장: {output_path}")


if __name__ == "__main__":
    main()