import pandas as pd
import streamlit as st

from src.data.loader import load_process_data


st.set_page_config(
    page_title="Manufacturing AI Dashboard",
    page_icon="📊",
    layout="wide",
)


@st.cache_data
def load_data() -> pd.DataFrame:
    return load_process_data()


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    model_options = ["All"] + sorted(df["Model"].dropna().unique().tolist())
    selected_model = st.sidebar.selectbox(
        "Model",
        model_options,
    )

    machine_options = ["All"] + sorted(df["Machine"].dropna().unique().tolist())
    selected_machine = st.sidebar.selectbox(
        "Machine",
        machine_options,
    )

    min_yield = float(df["Yield"].min())
    max_yield = float(df["Yield"].max())

    selected_yield_range = st.sidebar.slider(
        "Yield Range",
        min_value=min_yield,
        max_value=max_yield,
        value=(min_yield, max_yield),
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
    total_lots = len(df)

    if total_lots == 0:
        st.warning("필터 조건에 해당하는 데이터가 없습니다.")
        return

    defect_lots = (df["Defect"] != "Normal").sum()
    defect_rate = defect_lots / total_lots * 100
    average_yield = df["Yield"].mean()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total LOTs",
        f"{total_lots:,}",
    )

    col2.metric(
        "Defect LOTs",
        f"{defect_lots:,}",
    )

    col3.metric(
        "Defect Rate",
        f"{defect_rate:.2f}%",
    )

    col4.metric(
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

    chart_df = trend_df.set_index("LOT_ID")[
        ["Rolling_Mean_50"]
    ]

    st.line_chart(chart_df)


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
                lambda x: (x != "Normal").sum(),
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

    if numeric_df.empty:
        st.info("상관분석이 가능한 숫자형 데이터가 없습니다.")
        return

    correlation = numeric_df.corr()

    st.dataframe(
        correlation.round(3),
        use_container_width=True,
    )


def show_lot_detail(df: pd.DataFrame) -> None:
    st.subheader("LOT Detail")

    if df.empty:
        st.info("검색된 LOT이 없습니다.")
        return

    if len(df) == 1:
        lot_row = df.iloc[0]

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "LOT ID",
            str(lot_row["LOT_ID"]),
        )

        col2.metric(
            "Model",
            str(lot_row["Model"]),
        )

        col3.metric(
            "Machine",
            str(lot_row["Machine"]),
        )

        col4.metric(
            "Yield",
            f"{lot_row['Yield']:.2f}%",
        )

        st.dataframe(
            df.T.rename(columns={df.index[0]: "Value"}),
            use_container_width=True,
        )
    else:
        st.dataframe(
            df,
            use_container_width=True,
            height=400,
        )


def main() -> None:
    st.title("Manufacturing AI Dashboard")

    original_df = load_data()
    filtered_df = apply_filters(original_df)

    st.caption(
        f"Filtered rows: {len(filtered_df):,} / "
        f"Total rows: {len(original_df):,}"
    )

    show_summary(filtered_df)

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        show_yield_trend(filtered_df)

    with col2:
        show_defect_summary(filtered_df)

    st.divider()

    show_machine_summary(filtered_df)

    st.divider()

    show_correlation(filtered_df)

    st.divider()

    show_lot_detail(filtered_df)


if __name__ == "__main__":
    main()