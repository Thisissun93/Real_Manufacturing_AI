from pathlib import Path

import streamlit as st

from src.data.loader import load_process_data
from src.report.pdf_report import create_pdf_report


st.set_page_config(
    page_title="PDF Report",
    page_icon="📄",
    layout="wide",
)


@st.cache_data
def load_data():
    return load_process_data()


def main() -> None:
    st.title("Manufacturing Process PDF Report")

    df = load_data()

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

    st.divider()

    st.write(
        "현재 공정 데이터를 기준으로 Yield Trend, "
        "Defect Pareto, 설비별 불량률 및 품질 인자 통계를 "
        "포함한 PDF 보고서를 생성합니다."
    )

    if st.button(
        "Generate PDF Report",
        use_container_width=True,
        type="primary",
    ):
        with st.spinner("PDF 보고서를 생성하고 있습니다."):
            try:
                pdf_path = create_pdf_report(df)
            except Exception as error:
                st.error(f"PDF 생성 중 오류가 발생했습니다: {error}")
                return

        st.success("PDF 보고서 생성이 완료되었습니다.")

        with open(pdf_path, "rb") as pdf_file:
            pdf_data = pdf_file.read()

        st.download_button(
            label="Download PDF Report",
            data=pdf_data,
            file_name=pdf_path.name,
            mime="application/pdf",
            use_container_width=True,
        )

        st.info(f"저장 위치: {pdf_path}")

        report_directory = Path(pdf_path).parent

        st.write("Report Directory")

        report_files = sorted(
            file.name
            for file in report_directory.iterdir()
            if file.is_file()
        )

        st.dataframe(
            {"Generated Files": report_files},
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()