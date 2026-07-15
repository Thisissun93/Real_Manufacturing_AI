from datetime import datetime
from pathlib import Path
import subprocess
import sys
import time


PIPELINE_MODULES = [
    ("Generate Process Data", "src.data.generate_process_data"),
    ("Update SQLite Database", "src.database.create_database"),
    ("Validate Process Data", "src.data.loader"),
    ("Generate Trend Analysis", "src.analysis.trend"),
    ("Generate SPC Analysis", "src.analysis.spc"),
    ("Generate Correlation Analysis", "src.analysis.correlation"),
    ("Generate Defect Analysis", "src.analysis.defect"),
    ("Detect Abnormal LOTs", "src.analysis.outlier"),
    ("Train and Save Model", "src.ml.train_model"),
    ("Run Random Forest Analysis", "src.ml.random_forest"),
    ("Run SHAP Analysis", "src.ml.shap_analysis"),
    ("Run Batch Prediction", "src.ml.batch_predict"),
    ("Generate PDF Report", "src.report.pdf_report"),
]


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_log_path() -> Path:
    report_dir = get_project_root() / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    return report_dir / "pipeline.log"


def write_log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"

    print(log_message)

    with get_log_path().open(
        "a",
        encoding="utf-8",
    ) as log_file:
        log_file.write(log_message + "\n")


def run_module(
    step_number: int,
    step_name: str,
    module_name: str,
) -> bool:
    separator = "=" * 70

    write_log(separator)
    write_log(f"STEP {step_number:02d} START: {step_name}")
    write_log(f"Module: {module_name}")

    start_time = time.perf_counter()

    process = subprocess.run(
        [
            sys.executable,
            "-m",
            module_name,
        ],
        cwd=get_project_root(),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    elapsed_time = time.perf_counter() - start_time

    if process.stdout.strip():
        print(process.stdout)

    if process.returncode != 0:
        write_log(f"STEP {step_number:02d} FAILED: {step_name}")

        if process.stderr.strip():
            print(process.stderr)

        write_log(f"Elapsed Time: {elapsed_time:.2f} seconds")

        return False

    write_log(f"STEP {step_number:02d} COMPLETED: {step_name}")
    write_log(f"Elapsed Time: {elapsed_time:.2f} seconds")

    return True


def run_pipeline() -> None:
    pipeline_start_time = time.perf_counter()

    write_log("")
    write_log("#" * 70)
    write_log("MANUFACTURING AI PIPELINE START")
    write_log("#" * 70)

    completed_steps = 0

    for step_number, (
        step_name,
        module_name,
    ) in enumerate(
        PIPELINE_MODULES,
        start=1,
    ):
        success = run_module(
            step_number=step_number,
            step_name=step_name,
            module_name=module_name,
        )

        if not success:
            write_log("")
            write_log("PIPELINE STOPPED")
            write_log(
                f"Failed Step: {step_number:02d} - {step_name}"
            )
            write_log(
                f"Completed Steps: "
                f"{completed_steps}/{len(PIPELINE_MODULES)}"
            )

            raise RuntimeError(
                f"Pipeline failed at Step {step_number}: "
                f"{step_name}"
            )

        completed_steps += 1

    total_elapsed_time = (
        time.perf_counter() - pipeline_start_time
    )

    write_log("")
    write_log("#" * 70)
    write_log("MANUFACTURING AI PIPELINE COMPLETED")
    write_log(
        f"Completed Steps: "
        f"{completed_steps}/{len(PIPELINE_MODULES)}"
    )
    write_log(
        f"Total Elapsed Time: "
        f"{total_elapsed_time:.2f} seconds"
    )
    write_log("#" * 70)


if __name__ == "__main__":
    run_pipeline()