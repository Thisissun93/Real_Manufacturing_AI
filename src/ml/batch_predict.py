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
    """저장된 판정 임계값으로 불량 위험을 예측한다.

    model.predict() 를 쓰지 않는 이유
    --------------------------------
    scikit-learn 의 predict() 는 확률 0.5 를 기준으로 판정한다.
    불량률이 13% 수준인 공정에서 0.5 는 검출을 거의 포기하는 임계값이다.
    학습 단계에서 목표 재현율로 결정한 임계값을 모델 패키지에 함께 저장했고,
    추론에서도 그 값을 써야 학습 시 평가한 성능이 재현된다.
    """
    model = model_package["model"]
    features = model_package["features"]

    positive_label = model_package.get(
        "positive_label", "Delamination"
    )
    threshold = float(
        model_package.get("decision_threshold", 0.5)
    )

    validate_features(df, features)

    input_x = df[features]

    defect_probability = model.predict_proba(input_x)[:, 1]

    result_df = df.copy()

    result_df[f"Probability_{positive_label}_%"] = (
        defect_probability * 100
    ).round(3)

    result_df["Decision_Threshold_%"] = round(threshold * 100, 3)

    is_flagged = defect_probability >= threshold

    result_df["Predicted_Defect"] = [
        positive_label if flag else "Normal" for flag in is_flagged
    ]

    result_df["Prediction_Status"] = [
        "Defect Risk" if flag else "Normal" for flag in is_flagged
    ]

    # 임계값까지 남은 여유. 음수면 이미 임계값을 넘었다.
    result_df["Margin_To_Threshold_%"] = (
        (threshold - defect_probability) * 100
    ).round(3)

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
    print("예측 판정 분포")
    print(prediction_df["Predicted_Defect"].value_counts().to_string())

    probability_columns = [
        column
        for column in prediction_df.columns
        if column.startswith("Probability_")
    ]

    if probability_columns:
        column = probability_columns[0]

        print()
        print(f"{column} 통계")
        print(
            prediction_df[column]
            .describe()
            .round(3)
            .to_string()
        )

    if "Decision_Threshold_%" in prediction_df.columns:
        threshold = prediction_df["Decision_Threshold_%"].iloc[0]
        flagged = (
            prediction_df["Prediction_Status"] == "Defect Risk"
        ).sum()

        print()
        print(
            f"판정 임계값 {threshold}% 적용 -> 의심 LOT "
            f"{flagged:,}건 ({100 * flagged / len(prediction_df):.2f}%)"
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