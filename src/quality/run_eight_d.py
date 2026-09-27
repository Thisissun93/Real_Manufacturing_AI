"""8D 리포트 생성 CLI.

    python -m src.quality.run_eight_d

품질 분석 결과(report/*.csv)를 읽어 8D 를 열어야 하는 사례를 찾고
사례별 마크다운 리포트와 전체 요약 CSV 를 저장한다.

앞 단계가 먼저 실행되어 있어야 한다.

    python -m src.quality.run_quality_analysis

사례 선정을 사람에게 맡기지 않는 이유
------------------------------------
8D 를 어디에 열지 고르는 일 자체가 편향이 들어가는 지점이다.
눈에 띄는 설비, 최근에 클레임이 있었던 설비가 먼저 선택된다.
여기서는 두 가지 기준을 코드로 고정한다.

    1. 불량률이 전체 평균의 1.5배 이상인 설비
    2. Nelson 판정에서 CRITICAL 신호가 잡힌 파라미터

2번은 불량이 아직 터지지 않은 사례다. 그쪽이 더 싸게 끝난다.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from src.quality.eight_d import (
    DISCIPLINE_TITLES,
    EightDReport,
    build_defect_rate_case,
    build_drift_case,
    build_recommended_cases,
    get_project_root,
    get_report_directory,
    missing_reports,
    rank_defect_cases,
    rank_drift_cases,
    render_markdown,
)


def get_eight_d_directory() -> Path:
    """8D 리포트를 모아두는 폴더.

    report/ 바로 아래에 두면 분석 산출물과 섞여 찾기 어렵다.
    """
    directory = get_report_directory() / "eight_d"
    directory.mkdir(parents=True, exist_ok=True)

    return directory


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_case_selection(report_dir: Path | None = None) -> None:
    """어떤 사례가 왜 선정됐는지 보여준다."""
    _print_section("1. 사례 선정")

    ranked = rank_defect_cases(report_dir)

    if ranked.empty:
        print("  설비별 불량률 요약이 없다.")
    else:
        print("\n  불량률 기준")
        print(
            f"  {'설비':<10}{'불량률':>10}{'전체 대비':>12}"
            f"{'8D 대상':>10}"
        )
        print("  " + "-" * 42)

        for _, row in ranked.iterrows():
            mark = "예" if bool(row["escalate"]) else "아니오"
            print(
                f"  {row['Machine']:<10}"
                f"{row['defect_rate_percent']:>9.2f}%"
                f"{row['ratio_to_overall']:>11.2f}배"
                f"{mark:>10}"
            )

    drifts = rank_drift_cases(report_dir)

    if drifts.empty:
        print("\n  관리도 CRITICAL 신호 없음")
    else:
        print("\n  관리도 이상 신호 기준")
        print(
            f"  {'설비':<10}{'특성':<18}{'규칙 수':>8}"
            f"{'최대 배수':>12}"
        )
        print("  " + "-" * 48)

        for _, row in drifts.iterrows():
            print(
                f"  {row['Machine']:<10}{row['characteristic']:<18}"
                f"{int(row['rule_count']):>8}"
                f"{row['max_ratio']:>11.1f}배"
            )


def print_report_outline(report: EightDReport) -> None:
    """사례 하나의 요약을 콘솔에 찍는다."""
    status = report.discipline_status

    print()
    print(f"  [{report.case_id}] {report.title}")
    print(f"    심각도       : {report.severity}")
    print(
        "    분석 단계    : "
        + ("완료" if report.analysis_complete else "진행 중")
    )
    print(
        "    실행 대기    : "
        + (", ".join(report.pending_stages) or "없음")
    )
    print()

    for code, title in DISCIPLINE_TITLES.items():
        print(f"      {code}  {title:<22}{status[code]}")

    print()
    print("    확인된 원인")

    for cause in report.confirmed_causes:
        print(f"      - [{cause.category}] {cause.description}")

    if report.unverified_causes:
        print("    미확인 원인 (현장 확인 필요)")

        for cause in report.unverified_causes:
            print(f"      - [{cause.category}] {cause.description}")


def save_reports(
    reports: list[EightDReport],
    output_dir: Path | None = None,
) -> list[Path]:
    """사례별 마크다운과 전체 요약 CSV 를 저장한다."""
    directory = output_dir or get_eight_d_directory()
    saved: list[Path] = []

    for report in reports:
        path = directory / f"{report.case_id}.md"
        path.write_text(render_markdown(report), encoding="utf-8")
        saved.append(path)

    if reports:
        summary = pd.DataFrame(
            [report.summary_row() for report in reports]
        )
        summary_path = directory / "eight_d_summary.csv"
        summary.to_csv(
            summary_path, index=False, encoding="utf-8-sig"
        )
        saved.append(summary_path)

    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="품질 분석 결과에서 8D 리포트를 생성한다."
    )
    parser.add_argument(
        "--machine",
        help=(
            "특정 설비의 불량률 사례만 생성한다. "
            "생략하면 기준을 넘는 사례를 모두 생성한다."
        ),
    )
    parser.add_argument(
        "--drift",
        nargs=2,
        metavar=("MACHINE", "CHARACTERISTIC"),
        help="특정 설비/특성의 드리프트 사례를 생성한다.",
    )
    parser.add_argument(
        "--opened-on",
        help="개시일(YYYY-MM-DD). 생략하면 오늘.",
    )
    arguments = parser.parse_args()

    opened_on = (
        date.fromisoformat(arguments.opened_on)
        if arguments.opened_on
        else None
    )

    print("=" * 78)
    print("8D 문제해결 리포트")
    print("=" * 78)

    missing = missing_reports()

    if missing:
        print()
        print("  필요한 분석 결과가 없다:")

        for name in missing:
            print(f"    - {name}")

        print()
        print(
            "  `python -m src.quality.run_quality_analysis` 를 "
            "먼저 실행한다."
        )
        return

    if arguments.machine:
        reports = [
            build_defect_rate_case(
                arguments.machine, opened_on=opened_on
            )
        ]
    elif arguments.drift:
        machine, characteristic = arguments.drift
        reports = [
            build_drift_case(
                machine, characteristic, opened_on=opened_on
            )
        ]
    else:
        print_case_selection()
        reports = build_recommended_cases(opened_on=opened_on)

    if not reports:
        _print_section("결과")
        print("  8D 를 열 기준에 해당하는 사례가 없다.")
        return

    _print_section(f"2. 사례별 요약 ({len(reports)}건)")

    for report in reports:
        print_report_outline(report)

    saved = save_reports(reports)

    _print_section("3. 저장된 파일")

    root = get_project_root()

    for path in saved:
        try:
            display = path.relative_to(root)
        except ValueError:
            display = path

        print(f"  {display}")


if __name__ == "__main__":
    main()
