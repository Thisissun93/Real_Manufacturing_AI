from pathlib import Path
import subprocess
import sys

import streamlit as st


st.set_page_config(
    page_title="Pipeline Control",
    page_icon="⚙️",
    layout="wide",
)


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_log_path() -> Path:
    return get_project_root() / "report" / "pipeline.log"


def read_pipeline_log() -> str:
    log_path = get_log_path()

    if not log_path.exists():
        return "아직 생성된 Pipeline 로그가 없습니다."

    return log_path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def is_pipeline_disabled() -> bool:
    try:
        return bool(
            st.secrets
            .get("cloud", {})
            .get("disable_pipeline", False)
        )
    except Exception:
        return False


def run_pipeline() -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "src.pipeline.run_pipeline",
        ],
        cwd=get_project_root(),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> None:
    st.title("Manufacturing AI Pipeline Control")

    pipeline_disabled = is_pipeline_disabled()

    if pipeline_disabled:
        st.warning(
            "공개 Streamlit Cloud에서는 메모리 보호를 위해 "
            "전체 Pipeline 실행이 비활성화되어 있습니다."
        )

        st.info(
            "Full Pipeline은 로컬 PC 또는 GitHub Actions에서 실행하세요.\n\n"
            "`python -m src.pipeline.run_pipeline`"
        )
    else:
        st.write(
            "데이터 생성부터 분석, 모델 학습, SHAP 및 PDF 보고서 "
            "생성까지 전체 Pipeline을 실행합니다."
        )

    column1, column2 = st.columns(2)

    with column1:
        run_button = st.button(
            "Run Full Pipeline",
            type="primary",
            width="stretch",
            disabled=pipeline_disabled,
        )

    with column2:
        refresh_button = st.button(
            "Refresh Log",
            width="stretch",
        )

    if run_button:
        with st.spinner("전체 Pipeline을 실행하고 있습니다."):
            result = run_pipeline()

        if result.returncode == 0:
            st.success("Pipeline이 정상적으로 완료되었습니다.")
        else:
            st.error("Pipeline 실행 중 오류가 발생했습니다.")

        if result.stdout:
            st.subheader("Pipeline Output")
            st.code(result.stdout, language="text")

        if result.stderr:
            st.subheader("Error Output")
            st.code(result.stderr, language="text")

    if refresh_button:
        st.rerun()

    st.divider()
    st.subheader("Pipeline Log")

    log_text = read_pipeline_log()
    st.code(log_text, language="text")

    log_path = get_log_path()

    if log_path.exists():
        st.download_button(
            label="Download Pipeline Log",
            data=log_path.read_bytes(),
            file_name="pipeline.log",
            mime="text/plain",
            width="stretch",
        )


if __name__ == "__main__":
    main()