"""SPC 분석과 관리도 작성.

이전 버전에서 고친 것
--------------------
1. 관리한계를 전체 표준편차(mean +- 3 * std)로 계산하고 있었다.
   전체 표준편차는 부분군 간 변동까지 포함하므로, 공정에 평균 이동이나
   추세가 있으면 그 변동이 한계 폭을 넓혀 정작 검출해야 할 신호를 감춘다.
   이번 버전은 이동범위로 부분군 내 변동을 추정한다.
   sigma_hat = MR_bar / d2(2), UCL = X_bar + 2.660 * MR_bar

2. 관리한계를 벗어난 점(Nelson 규칙 1)만 표시하고 있었다.
   규칙 2~8 을 적용해 관리한계 안에서 진행되는 평균 이동, 추세,
   층별 혼입을 검출한다.

3. Cpk 만 계산하고 있었다. Cp, Cpk, Pp, Ppk 를 모두 계산한다.
   Cp 와 Cpk 의 차이는 중심 이탈, Cp 와 Pp 의 차이는 부분군 간 변동이며
   각각 필요한 조치가 다르다.

4. 이미지 저장 경로가 src/images 로 잡혀 있었다.
   Path(__file__).parent.parent 는 src 디렉터리다.
   프로젝트 루트의 images 로 바로잡았다.

5. 파이프라인 안에서 plt.show() 를 호출해 헤드리스 환경과 CI 에서 멈췄다.
   제거했다.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from src.data.loader import load_process_data
from src.process_spec import (
    CAPABILITY_CHARACTERISTICS,
    get_spec_limits,
    get_unit,
)
from src.quality.capability import CapabilityResult, analyze_capability
from src.quality.control_charts import (
    ControlChart,
    individual_moving_range_chart,
)
from src.quality.nelson_rules import (
    RuleViolation,
    evaluate_chart,
    summarize_violations,
)


SPC_COLUMNS = CAPABILITY_CHARACTERISTICS


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_image_directory() -> Path:
    """이미지 저장 디렉터리.

    이전 버전은 parents[1](= src)을 루트로 보아 src/images 에 저장했다.
    """
    image_dir = get_project_root() / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    return image_dir


def get_report_directory() -> Path:
    report_dir = get_project_root() / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    return report_dir


def analyze_characteristic(
    dataframe: pd.DataFrame,
    characteristic: str,
) -> tuple[ControlChart, ControlChart, CapabilityResult, list[RuleViolation]]:
    """단일 품질 특성의 관리도, 공정능력, 판정 규칙을 한 번에 계산한다."""
    if characteristic not in dataframe.columns:
        raise ValueError(
            f"존재하지 않는 컬럼입니다: {characteristic}"
        )

    series = dataframe[characteristic]

    individual_chart, moving_range_chart = (
        individual_moving_range_chart(series)
    )

    lower_spec, upper_spec = get_spec_limits(characteristic)

    capability = analyze_capability(
        series=series,
        characteristic=characteristic,
        lower_spec=lower_spec,
        upper_spec=upper_spec,
    )

    violations = evaluate_chart(individual_chart)

    return (
        individual_chart,
        moving_range_chart,
        capability,
        violations,
    )


def plot_control_chart(
    chart: ControlChart,
    characteristic: str,
    capability: CapabilityResult | None = None,
    violations: list[RuleViolation] | None = None,
    max_points: int = 600,
    save: bool = True,
) -> Path | None:
    """관리도를 그린다.

    타점이 많으면 앞부분만 그린다. 8000점을 한 화면에 그리면
    패턴이 보이지 않는다.
    """
    values = chart.values[:max_points]
    zones = chart.sigma_zone_edges

    figure, axes = plt.subplots(figsize=(14, 6))

    axes.plot(
        range(len(values)),
        values,
        linewidth=0.8,
        alpha=0.85,
        marker="o",
        markersize=2.2,
        label=characteristic,
    )

    axes.axhline(
        chart.center_line,
        linewidth=1.3,
        color="#1f6096",
        label=f"CL {chart.center_line:.3f}",
    )

    for bound, name in (
        (chart.upper_limit, "UCL"),
        (chart.lower_limit, "LCL"),
    ):
        axes.axhline(
            bound,
            linestyle="--",
            linewidth=1.2,
            color="#9c3038",
            label=f"{name} {bound:.3f}",
        )

    for edge_key in ("plus_1", "plus_2", "minus_1", "minus_2"):
        axes.axhline(
            zones[edge_key],
            linestyle=":",
            linewidth=0.7,
            color="#9aa5b1",
        )

    if capability is not None:
        for spec_value, name in (
            (capability.upper_spec, "USL"),
            (capability.lower_spec, "LSL"),
        ):
            if spec_value is None:
                continue

            axes.axhline(
                spec_value,
                linestyle="-.",
                linewidth=1.1,
                color="#a55f21",
                label=f"{name} {spec_value:.3f}",
            )

    if violations:
        marked = [
            violation
            for violation in violations
            if violation.start_index < len(values)
        ]

        for violation in marked[:60]:
            axes.axvspan(
                violation.start_index,
                min(violation.end_index, len(values) - 1),
                alpha=0.08,
                color="#9c3038",
            )

    title = f"{characteristic} {chart.chart_type} Chart"

    if capability is not None:
        title += (
            f"  |  Cp {_format(capability.cp)}"
            f"  Cpk {_format(capability.cpk)}"
            f"  Pp {_format(capability.pp)}"
            f"  Ppk {_format(capability.ppk)}"
        )

    if violations:
        title += f"  |  규칙 위반 {len(violations)}건"

    axes.set_title(title, fontsize=11)
    axes.set_xlabel(f"LOT 순서 (최대 {max_points}점)")
    axes.set_ylabel(f"{characteristic} [{get_unit(characteristic)}]")
    axes.grid(True, alpha=0.25)
    axes.legend(fontsize=8, ncol=3, loc="best")

    figure.tight_layout()

    output_path = None

    if save:
        output_path = (
            get_image_directory()
            / f"{characteristic.lower()}_{chart.chart_type.lower()}_chart.png"
        )
        figure.savefig(output_path, dpi=150, bbox_inches="tight")

    plt.close(figure)

    return output_path


def _format(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def print_characteristic_report(
    characteristic: str,
    capability: CapabilityResult,
    violations: list[RuleViolation],
) -> None:
    """특성 1개의 분석 결과를 출력한다."""
    print(f"[{characteristic}]  단위: {get_unit(characteristic)}")
    print(
        f"  규격      LSL {_format(capability.lower_spec)} / "
        f"USL {_format(capability.upper_spec)}"
    )
    print(
        f"  평균      {capability.mean:.4f}   "
        f"sigma_within {capability.sigma_within:.4f}   "
        f"sigma_overall {capability.sigma_overall:.4f}"
    )
    print(
        f"  능력      Cp {_format(capability.cp)}  "
        f"Cpk {_format(capability.cpk)}  "
        f"Pp {_format(capability.pp)}  "
        f"Ppk {_format(capability.ppk)}  "
        f"-> {capability.verdict}"
    )

    if capability.expected_ppm_out_of_spec is not None:
        print(
            f"  규격이탈  실측 {capability.observed_out_of_spec_count}건 / "
            f"추정 {capability.expected_ppm_out_of_spec:,.0f} ppm"
        )

    summary = summarize_violations(
        violations,
        point_count=capability.sample_size,
    )

    print(
        f"  판정규칙  위반 {summary['total_violations']}건  "
        f"종합 {summary['overall_severity']}"
    )

    if summary["by_rule"]:
        expected = summary["expected_false_alarms"]
        detail = ", ".join(
            f"{rule.replace('NELSON_RULE_', 'R')}="
            f"{count}(기대 {expected.get(rule, 0.0):.0f})"
            for rule, count in sorted(summary["by_rule"].items())
        )
        print(f"            {detail}")

    signal_rules = summary["signal_rules"]

    if signal_rules:
        for rule, stats in sorted(signal_rules.items()):
            print(
                f"            [신호] {rule.replace('NELSON_RULE_', '규칙 ')}: "
                f"관측 {stats['observed']:.0f}건은 기대 오경보 "
                f"{stats['expected']:.1f}건의 {stats['ratio']:.1f}배"
            )
    else:
        print(
            "            모든 규칙의 위반 건수가 관리상태 기대 오경보 "
            "수준이다. 우연으로 설명된다."
        )

    print(f"  진단      {capability.diagnosis}")
    print("-" * 74)


def build_capability_table(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """전체 특성의 공정능력 요약표를 만든다."""
    rows: list[dict[str, object]] = []

    for characteristic in SPC_COLUMNS:
        if characteristic not in dataframe.columns:
            continue

        _, _, capability, violations = analyze_characteristic(
            dataframe=dataframe,
            characteristic=characteristic,
        )

        summary = summarize_violations(
            violations,
            point_count=capability.sample_size,
        )

        row = capability.to_dict()
        row["nelson_violations"] = summary["total_violations"]
        row["nelson_severity"] = summary["overall_severity"]

        rows.append(row)

    return pd.DataFrame(rows)


def build_violation_table(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """판정 규칙 위반 목록을 만든다.

    LOT_ID 를 함께 붙여, 몇 번째 LOT 부터 이상인지 바로 추적할 수 있게 한다.
    """
    rows: list[dict[str, object]] = []

    lot_ids = (
        dataframe["LOT_ID"].tolist()
        if "LOT_ID" in dataframe.columns
        else []
    )

    for characteristic in SPC_COLUMNS:
        if characteristic not in dataframe.columns:
            continue

        _, _, _, violations = analyze_characteristic(
            dataframe=dataframe,
            characteristic=characteristic,
        )

        for violation in violations:
            row = violation.to_dict()
            row["characteristic"] = characteristic

            if lot_ids:
                row["start_lot"] = lot_ids[
                    min(violation.start_index, len(lot_ids) - 1)
                ]
                row["end_lot"] = lot_ids[
                    min(violation.end_index, len(lot_ids) - 1)
                ]

            rows.append(row)

    return pd.DataFrame(rows)


def generate_all_spc_charts(
    dataframe: pd.DataFrame,
    save_images: bool = True,
) -> None:
    """전체 특성의 관리도를 생성하고 결과를 출력한다."""
    print("=" * 74)
    print("SPC Analysis  (관리한계는 부분군 내 변동으로 추정)")
    print("=" * 74)

    for characteristic in SPC_COLUMNS:
        if characteristic not in dataframe.columns:
            continue

        (
            individual_chart,
            moving_range_chart,
            capability,
            violations,
        ) = analyze_characteristic(
            dataframe=dataframe,
            characteristic=characteristic,
        )

        print_characteristic_report(
            characteristic=characteristic,
            capability=capability,
            violations=violations,
        )

        if not save_images:
            continue

        plot_control_chart(
            chart=individual_chart,
            characteristic=characteristic,
            capability=capability,
            violations=violations,
        )

        plot_control_chart(
            chart=moving_range_chart,
            characteristic=characteristic,
        )


def main() -> None:
    dataframe = load_process_data()

    generate_all_spc_charts(dataframe)

    report_dir = get_report_directory()

    capability_table = build_capability_table(dataframe)
    capability_path = report_dir / "process_capability.csv"
    capability_table.to_csv(
        capability_path,
        index=False,
        encoding="utf-8-sig",
    )

    violation_table = build_violation_table(dataframe)
    violation_path = report_dir / "nelson_rule_violations.csv"
    violation_table.to_csv(
        violation_path,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"공정능력 요약 저장   : {capability_path}")
    print(f"판정규칙 위반 저장   : {violation_path}")


if __name__ == "__main__":
    main()
