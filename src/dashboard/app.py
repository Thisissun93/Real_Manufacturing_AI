from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

from src.data.loader import load_process_data
from src.process_spec import PROCESS_SPEC


st.set_page_config(
    page_title="Manufacturing AI Dashboard",
    page_icon="📊",
    layout="wide",
)


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

    column1.metric(
        "Total LOTs",
        f"{total_lots:,}",
    )

    column2.metric(
        "Defect LOTs",
        f"{defect_lots:,}",
    )

    column3.metric(
        "Defect Rate",
        f"{defect_rate:.2f}%",
    )

    column4.metric(
        "Average Yield",
        f"{average_yield:.2f}%",
    )


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
            f"LCL: {spec['lcl']} / UCL: {spec['ucl']}"
        ),
    )


def show_defect_prediction() -> None:
    st.subheader("Defect Prediction")

    try:
        model_package = load_model_package()
    except FileNotFoundError as error:
        st.error(str(error))
        return

    model = model_package["model"]
    model_features = model_package["features"]
    model_classes = model_package["classes"]

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

    predicted_class = model.predict(input_df)[0]
    probabilities = model.predict_proba(input_df)[0]

    probability_df = pd.DataFrame({
        "Defect": model_classes,
        "Probability_%": probabilities * 100,
    }).sort_values(
        by="Probability_%",
        ascending=False,
    )

    highest_probability = probability_df.iloc[0]["Probability_%"]

    result_column1, result_column2 = st.columns(2)

    result_column1.metric(
        "Predicted Defect",
        str(predicted_class),
    )

    result_column2.metric(
        "Prediction Probability",
        f"{highest_probability:.2f}%",
    )

    if predicted_class == "Normal":
        st.success("예측 결과: 정상 공정 조건입니다.")
    else:
        st.error(
            f"예측 결과: {predicted_class} 발생 가능성이 있습니다."
        )

    st.bar_chart(
        probability_df.set_index("Defect")[["Probability_%"]]
    )

    st.dataframe(
        probability_df.round(3),
        use_container_width=True,
        hide_index=True,
    )

    st.write("입력한 공정 조건")

    st.dataframe(
        input_df.T.rename(columns={0: "Input_Value"}),
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
    st.title("Manufacturing AI Dashboard")

    dashboard_tab, prediction_tab = st.tabs([
        "Process Dashboard",
        "Defect Prediction",
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

    with prediction_tab:
        show_defect_prediction()


if __name__ == "__main__":
    main()