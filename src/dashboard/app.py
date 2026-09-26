from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
      
import joblib
import pandas as pd
import streamlit as st

from src.dashboard.quality_view import show_quality_analysis
from src.data.loader import load_process_data
from src.process_spec import PROCESS_SPEC


st.set_page_config(
    page_title="Manufacturing AI Dashboard",
    page_icon="📊",
    layout="wide",
)


@st.cache_data
def load_data() -> pd.DataFrame:
    return load_process_data()


@st.cache_resource
def load_model_package() -> dict:
    project_root = Path(__file__).resolve().parents[2]
    model_path = (
        project_root
        / "models"
        / "random_forest_defect_model.joblib"
    )

    if not model_path.exists():
        raise FileNotFoundError(
            "저장된 모델을 찾을 수 없습니다.\n"
            "먼저 아래 명령을 실행하세요.\n"
            "python -m src.ml.train_model"
        )

    return joblib.load(model_path)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    model_options = [
        "All",
        *sorted(df["Model"].dropna().unique().tolist()),
    ]

    selected_model = st.sidebar.selectbox(
        "Model",
        model_options,
    )

    machine_options = [
        "All",
        *sorted(df["Machine"].dropna().unique().tolist()),
    ]

    selected_machine = st.sidebar.selectbox(
        "Machine",
        machine_options,
    )

    minimum_yield = float(df["Yield"].min())
    maximum_yield = float(df["Yield"].max())

    selected_yield_range = st.sidebar.slider(
        "Yield Range",
        min_value=minimum_yield,
        max_value=maximum_yield,
        value=(minimum_yield, maximum_yield),
        step=0.1,
    )

    lot_search = st.sidebar.text_input(
        "LOT Search",
        placeholder="예: LOT000321",
    ).strip()

    filtered_df = df.copy()

    if selected_model != "All":
        filtered_df = filtered_df[
            filtered_df["Model"] == selected_model
        ]

    if selected_machine != "All":
        filtered_df = filtered_df[
            filtered_df["Machine"] == selected_machine
        ]

    filtered_df = filtered_df[
        filtered_df["Yield"].between(
            selected_yield_range[0],
            selected_yield_range[1],
        )
    ]

    if lot_search:
        filtered_df = filtered_df[
            filtered_df["LOT_ID"]
            .astype(str)
            .str.contains(
                lot_search,
                case=False,
                na=False,
            )
        ]

    return filtered_df


def show_summary(df: pd.DataFrame) -> None:
    if df.empty:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    total_lots = len(df)
    defect_lots = (df["Defect"] != "Normal").sum()
    defect_rate = defect_lots / total_lots * 100
    average_yield = df["Yield"].mean()

    column1, column2, column3, column4 = st.columns(4)

    column1.metric("Total LOTs", f"{total_lots:,}")
    column2.metric("Defect LOTs", f"{defect_lots:,}")
    column3.metric("Defect Rate", f"{defect_rate:.2f}%")
    column4.metric("Average Yield", f"{average_yield:.2f}%")


def show_yield_trend(df: pd.DataFrame) -> None:
    st.subheader("Yield Trend")

    if df.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    trend_df = df[["LOT_ID", "Yield"]].copy()

    trend_df["Rolling_Mean_50"] = (
        trend_df["Yield"]
        .rolling(
            window=50,
            min_periods=1,
        )
        .mean()
    )

    st.line_chart(
        trend_df.set_index("LOT_ID")[["Rolling_Mean_50"]]
    )


def show_defect_summary(df: pd.DataFrame) -> None:
    st.subheader("Defect Summary")

    if df.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    defect_counts = (
        df["Defect"]
        .value_counts()
        .rename_axis("Defect")
        .reset_index(name="Count")
    )

    st.bar_chart(
        defect_counts.set_index("Defect")
    )

    st.dataframe(
        defect_counts,
        use_container_width=True,
        hide_index=True,
    )


def show_machine_summary(df: pd.DataFrame) -> None:
    st.subheader("Machine Comparison")

    if df.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    machine_summary = (
        df.groupby("Machine")
        .agg(
            Average_Yield=("Yield", "mean"),
            Defect_Count=(
                "Defect",
                lambda values: (values != "Normal").sum(),
            ),
            LOT_Count=("LOT_ID", "count"),
        )
        .reset_index()
    )

    machine_summary["Defect_Rate_%"] = (
        machine_summary["Defect_Count"]
        / machine_summary["LOT_Count"]
        * 100
    )

    st.dataframe(
        machine_summary.round(3),
        use_container_width=True,
        hide_index=True,
    )


def show_correlation(df: pd.DataFrame) -> None:
    st.subheader("Correlation Matrix")

    if df.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    numeric_df = df.select_dtypes(include="number")
    correlation = numeric_df.corr()

    st.dataframe(
        correlation.round(3),
        use_container_width=True,
    )


def create_input_value(feature: str) -> float:
    spec = PROCESS_SPEC[feature]

    equipment_min = float(spec["equipment_min"])
    equipment_max = float(spec["equipment_max"])
    target = float(spec["target"])

    return st.number_input(
        feature,
        min_value=equipment_min,
        max_value=equipment_max,
        value=target,
        step=0.1,
        format="%.3f",
        help=(
            f"Target: {target} {spec['unit']} / "
            f"LSL: {spec['lsl']} / USL: {spec['usl']}"
        ),
    )


def show_defect_prediction() -> None:
    st.subheader("Single LOT Defect Prediction")

    try:
        model_package = load_model_package()
    except FileNotFoundError as error:
        st.error(str(error))
        return

    model = model_package["model"]
    model_features = model_package["features"]

    positive_label = model_package.get(
        "positive_label", "Delamination"
    )
    threshold = float(
        model_package.get("decision_threshold", 0.5)
    )

    st.caption(
        f"판정 임계값 {threshold * 100:.2f}% "
        f"(목표 검출률 {model_package.get('target_recall', 0.9):.0%} 기준). "
        "불량이 희소한 공정에서 0.5 를 쓰면 검출률이 크게 떨어지므로, "
        "학습 단계에서 결정한 임계값을 그대로 사용합니다."
    )

    input_values = {}

    with st.form("defect_prediction_form"):
        st.write("공정 조건을 입력한 뒤 예측 버튼을 누르세요.")

        column1, column2, column3 = st.columns(3)

        for index, feature in enumerate(model_features):
            target_column = [
                column1,
                column2,
                column3,
            ][index % 3]

            with target_column:
                input_values[feature] = create_input_value(feature)

        submitted = st.form_submit_button(
            "Predict Defect",
            use_container_width=True,
        )

    if not submitted:
        return

    input_df = pd.DataFrame(
        [input_values],
        columns=model_features,
    )

    defect_probability = float(
        model.predict_proba(input_df)[0][1]
    )

    is_flagged = defect_probability >= threshold

    predicted_label = positive_label if is_flagged else "Normal"

    probability_df = pd.DataFrame(
        {
            "Defect": [positive_label, "Normal"],
            "Probability_%": [
                defect_probability * 100,
                (1.0 - defect_probability) * 100,
            ],
        }
    )

    result_column1, result_column2, result_column3 = st.columns(3)

    result_column1.metric("판정", predicted_label)

    result_column2.metric(
        f"{positive_label} 확률",
        f"{defect_probability * 100:.2f}%",
    )

    result_column3.metric(
        "임계값까지 여유",
        f"{(threshold - defect_probability) * 100:+.2f}%p",
        help="음수이면 이미 임계값을 넘어 불량 위험으로 판정된 상태입니다.",
    )

    if is_flagged:
        st.error(
            f"예측 결과: {positive_label} 위험. "
            f"확률 {defect_probability * 100:.2f}% 가 "
            f"임계값 {threshold * 100:.2f}% 이상입니다."
        )
    else:
        st.success(
            f"예측 결과: 정상 범위. "
            f"확률 {defect_probability * 100:.2f}% 가 "
            f"임계값 {threshold * 100:.2f}% 미만입니다."
        )

    st.bar_chart(
        probability_df.set_index("Defect")[["Probability_%"]]
    )

    st.dataframe(
        probability_df.round(3),
        use_container_width=True,
        hide_index=True,
    )


def validate_batch_columns(
    df: pd.DataFrame,
    required_features: list[str],
) -> list[str]:
    return [
        feature
        for feature in required_features
        if feature not in df.columns
    ]


def predict_batch(
    df: pd.DataFrame,
    model_package: dict,
) -> pd.DataFrame:
    model = model_package["model"]
    features = model_package["features"]

    positive_label = model_package.get(
        "positive_label", "Delamination"
    )
    threshold = float(
        model_package.get("decision_threshold", 0.5)
    )

    input_x = df[features]

    defect_probability = model.predict_proba(input_x)[:, 1]
    is_flagged = defect_probability >= threshold

    result_df = df.copy()

    result_df[f"Probability_{positive_label}_%"] = (
        defect_probability * 100
    ).round(3)

    result_df["Decision_Threshold_%"] = round(threshold * 100, 3)

    result_df["Margin_To_Threshold_%"] = (
        (threshold - defect_probability) * 100
    ).round(3)

    result_df["Predicted_Defect"] = [
        positive_label if flag else "Normal" for flag in is_flagged
    ]

    result_df["Prediction_Status"] = [
        "Defect Risk" if flag else "Normal" for flag in is_flagged
    ]

    return result_df


def show_batch_prediction() -> None:
    st.subheader("Batch CSV Prediction")

    try:
        model_package = load_model_package()
    except FileNotFoundError as error:
        st.error(str(error))
        return

    uploaded_file = st.file_uploader(
        "예측할 CSV 파일을 업로드하세요.",
        type=["csv"],
    )

    if uploaded_file is None:
        st.info(
            "모델 학습에 사용한 공정 입력 컬럼이 포함된 CSV가 필요합니다."
        )
        return

    try:
        upload_df = pd.read_csv(uploaded_file)
    except Exception as error:
        st.error(f"CSV 파일을 읽을 수 없습니다: {error}")
        return

    if upload_df.empty:
        st.error("업로드한 CSV 파일이 비어 있습니다.")
        return

    required_features = model_package["features"]

    missing_columns = validate_batch_columns(
        upload_df,
        required_features,
    )

    if missing_columns:
        st.error(
            "예측에 필요한 컬럼이 누락되었습니다:\n"
            f"{missing_columns}"
        )
        return

    st.write("업로드 데이터 미리보기")

    st.dataframe(
        upload_df.head(20),
        use_container_width=True,
        hide_index=True,
    )

    if not st.button(
        "Run Batch Prediction",
        use_container_width=True,
    ):
        return

    result_df = predict_batch(
        upload_df,
        model_package,
    )

    total_rows = len(result_df)
    defect_rows = (
        result_df["Predicted_Defect"] != "Normal"
    ).sum()
    defect_rate = defect_rows / total_rows * 100
    probability_column = next(
        column
        for column in result_df.columns
        if column.startswith("Probability_")
    )
    average_probability = result_df[probability_column].mean()

    column1, column2, column3, column4 = st.columns(4)

    column1.metric("Predicted LOTs", f"{total_rows:,}")
    column2.metric("Defect Risk LOTs", f"{defect_rows:,}")
    column3.metric("Defect Risk Rate", f"{defect_rate:.2f}%")
    column4.metric(
        "평균 불량 확률",
        f"{average_probability:.2f}%",
    )

    prediction_counts = (
        result_df["Predicted_Defect"]
        .value_counts()
        .rename_axis("Predicted_Defect")
        .reset_index(name="Count")
    )

    st.bar_chart(
        prediction_counts.set_index("Predicted_Defect")
    )

    st.dataframe(
        result_df,
        use_container_width=True,
        hide_index=True,
        height=500,
    )

    csv_data = result_df.to_csv(
        index=False,
        encoding="utf-8-sig",
    ).encode("utf-8-sig")

    st.download_button(
        label="Download Prediction Result",
        data=csv_data,
        file_name="batch_prediction_result.csv",
        mime="text/csv",
        use_container_width=True,
    )


def show_lot_detail(df: pd.DataFrame) -> None:
    st.subheader("LOT Detail")

    if df.empty:
        st.info("검색된 LOT이 없습니다.")
        return

    st.dataframe(
        df,
        use_container_width=True,
        height=400,
    )


def main() -> None:
    mode = st.sidebar.radio("작업 선택", ["제조 이력 조사", "기존 통계·ML (학습용)"])
    if mode == "제조 이력 조사":
        from src.investigation.ui import render
        render()
        return
    st.warning("기존 합성 데이터·무작위 분할 모델의 학습용 화면입니다. 실제 공정 불량 확률이나 원인으로 해석하지 마세요.")
    st.title("Manufacturing AI Dashboard")

    (
        dashboard_tab,
        quality_tab,
        single_prediction_tab,
        batch_prediction_tab,
    ) = st.tabs([
        "Process Dashboard",
        "품질 분석",
        "Single Prediction",
        "Batch CSV Prediction",
    ])

    with dashboard_tab:
        original_df = load_data()
        filtered_df = apply_filters(original_df)

        st.caption(
            f"Filtered rows: {len(filtered_df):,} / "
            f"Total rows: {len(original_df):,}"
        )

        show_summary(filtered_df)

        st.divider()

        column1, column2 = st.columns(2)

        with column1:
            show_yield_trend(filtered_df)

        with column2:
            show_defect_summary(filtered_df)

        st.divider()
        show_machine_summary(filtered_df)

        st.divider()
        show_correlation(filtered_df)

        st.divider()
        show_lot_detail(filtered_df)

    with quality_tab:
        show_quality_analysis(load_data())

    with single_prediction_tab:
        show_defect_prediction()

    with batch_prediction_tab:
        show_batch_prediction()


if __name__ == "__main__":
    st.navigation([st.Page(main,title="제조 이력 조사",default=True),
                   st.Page("pages/4_PDF_Report.py",title="조사 보고서 PDF"),
                   st.Page("pages/5_Pipeline_Control.py",title="시료 불출·수령 관리")]).run()
