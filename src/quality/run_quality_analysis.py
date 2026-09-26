"""품질 분석 통합 실행.

JMP 에서 순서대로 하던 작업을 하나의 파이프라인으로 묶은 것이다.

1. 공정능력 분석        Cp/Cpk(단기) 와 Pp/Ppk(장기) 비교
2. 설비 층별 관리도     설비별 I-MR 관리도 + Nelson 판정 규칙 8종
3. 설비 간 비교         일원분산분석 -> 유의하면 Tukey HSD 다중비교
4. 측정시스템 분석      Gage R&R(ANOVA 법), 편향, 선형성

왜 층별이 먼저인가
-----------------
전체 데이터를 한 장의 관리도로 그리면 설비별 특성이 섞여 서로를 가린다.
설비 3대 중 1대에서만 진행되는 드리프트는 전체 관리도에서 사라지고,
전체 산포만 커져 관리한계가 넓어진다. 결과적으로 이상이 감춰진다.
그래서 설비별로 나눠 관리도를 그린 다음, 설비 간 차이는 분산분석으로 본다.
"""

from pathlib import Path
from typing import Final

import pandas as pd

from src.config import CONFIG
from src.data.loader import load_process_data
from src.process_spec import (
    CAPABILITY_CHARACTERISTICS,
    PROCESS_PARAMETERS,
    build_capability_specifications,
    get_spec_limits,
    get_tolerance,
)
from src.quality.anova import (
    compare_factor_across_responses,
    one_way_anova,
    tukey_hsd,
)
from src.quality.capability import (
    analyze_capability,
    analyze_capability_table,
)
from src.quality.control_charts import (
    build_defect_rate_subgroups,
    individual_moving_range_chart,
    p_chart,
)
from src.quality.msa import bias_and_linearity, gage_rnr_anova
from src.quality.nelson_rules import (
    evaluate_chart,
    summarize_violations,
)


STRATIFICATION_FACTORS: Final[list[str]] = ["Machine", "Model"]

MSA_CHARACTERISTIC: Final[str] = str(
    CONFIG.get("msa", {}).get("characteristic", "Total_Thickness")
)

# 설비 층별 관리도에서 추가로 감시할 공정 인자.
# 품질 특성만 보면 드리프트의 원인 인자를 놓친다.
# I-MR 관리도로 감시하면 안 되는 특성.
# 수율은 불량 발생 여부에 의해 이봉분포가 되므로 계량형 관리도에서
# 모든 불량 LOT 이 규칙 1 위반으로 잡힌다. 이상 신호가 아니라
# 차트 선택이 틀린 것이다. 불량률은 p 관리도로 본다.
ATTRIBUTE_DRIVEN_CHARACTERISTICS: Final[list[str]] = ["Yield"]

MONITORED_PARAMETERS: Final[list[str]] = [
    "CZ_Concentration",
    "Press2_Pressure",
    "Press2_Temp",
    "Cure_Temp",
    "Anneal_Temp",
]


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_report_directory() -> Path:
    report_dir = get_project_root() / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    return report_dir


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def run_capability_analysis(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """전체 품질 특성의 공정능력을 분석한다."""
    _print_section("1. 공정능력 분석  (Cp/Cpk 단기, Pp/Ppk 장기)")

    table = analyze_capability_table(
        dataframe=dataframe,
        specifications=build_capability_specifications(),
    )

    if table.empty:
        print("규격이 정의된 품질 특성이 없습니다.")
        return table

    display = table[
        [
            "characteristic",
            "mean",
            "sigma_within",
            "sigma_overall",
            "cp",
            "cpk",
            "pp",
            "ppk",
            "cp_minus_cpk",
            "cp_minus_pp",
            "verdict",
        ]
    ].copy()

    numeric_columns = display.select_dtypes("number").columns
    display[numeric_columns] = display[numeric_columns].round(3)

    print(display.to_string(index=False))
    print()

    for _, row in table.iterrows():
        print(f"  [{row['characteristic']}] {row['diagnosis']}")

    return table


def run_stratified_control_charts(
    dataframe: pd.DataFrame,
    stratify_by: str = "Machine",
) -> pd.DataFrame:
    """설비별로 층별한 관리도에 판정 규칙을 적용한다.

    전체 관리도에서는 보이지 않는 설비 고유의 이상을 찾는다.
    """
    _print_section(
        f"2. {stratify_by} 층별 관리도 + Nelson 판정 규칙 8종"
    )

    if stratify_by not in dataframe.columns:
        print(f"층별 컬럼이 없습니다: {stratify_by}")
        return pd.DataFrame()

    characteristics = [
        column
        for column in CAPABILITY_CHARACTERISTICS + MONITORED_PARAMETERS
        if column in dataframe.columns
        and column not in ATTRIBUTE_DRIVEN_CHARACTERISTICS
    ]

    print(
        "계량형 특성만 I-MR 관리도로 감시합니다. "
        f"제외: {', '.join(ATTRIBUTE_DRIVEN_CHARACTERISTICS)} "
        "(불량 발생에 의해 이봉분포가 되는 계수형 성격이므로 "
        "p 관리도로 따로 본다)"
    )
    print()

    rows: list[dict[str, object]] = []

    for level, subset in dataframe.groupby(stratify_by, sort=True):
        if len(subset) < 30:
            continue

        for characteristic in characteristics:
            series = subset[characteristic]

            try:
                individual_chart, _ = (
                    individual_moving_range_chart(series)
                )
            except ValueError:
                continue

            violations = evaluate_chart(individual_chart)

            summary = summarize_violations(
                violations,
                point_count=len(series.dropna()),
            )

            signal_rules = summary["signal_rules"]

            if not signal_rules:
                continue

            for rule_key, statistics in sorted(signal_rules.items()):
                rows.append(
                    {
                        stratify_by: str(level),
                        "characteristic": characteristic,
                        "rule": rule_key,
                        "observed": int(statistics["observed"]),
                        "expected_false_alarms": round(
                            statistics["expected"], 2
                        ),
                        "ratio": round(statistics["ratio"], 1),
                        "severity": summary["overall_severity"],
                        "point_count": len(series.dropna()),
                    }
                )

    table = pd.DataFrame(rows)

    if table.empty:
        print(
            "우연 수준을 넘는 판정 규칙 위반이 없습니다. "
            "모든 층에서 관리상태로 판단됩니다."
        )
        return table

    table = table.sort_values(
        "ratio", ascending=False, ignore_index=True
    )

    print(
        "관측 건수가 관리상태 기대 오경보의 2배 이상인 항목만 표시합니다."
    )
    print()
    print(table.to_string(index=False))
    print()

    top = table.iloc[0]

    print(
        f"  가장 강한 신호: {top[stratify_by]} 의 {top['characteristic']} 에서 "
        f"{top['rule'].replace('NELSON_RULE_', '규칙 ')} 위반이 "
        f"기대치의 {top['ratio']}배."
    )

    return table


def run_defect_rate_control_chart(
    dataframe: pd.DataFrame,
    subgroup_size: int = 50,
) -> pd.DataFrame:
    """불량률을 p 관리도로 감시한다.

    계수형 데이터에 맞는 관리도다. 부분군 단위 불량률을 타점하고
    이항분포의 표준오차로 관리한계를 계산한다.
    """
    _print_section(
        f"2-1. 불량률 p 관리도  (LOT {subgroup_size}개 단위 부분군)"
    )

    if "Defect" not in dataframe.columns:
        print("Defect 컬럼이 없습니다.")
        return pd.DataFrame()

    rows: list[dict[str, object]] = []

    targets: list[tuple[str, pd.DataFrame]] = [
        ("전체", dataframe)
    ]

    if "Machine" in dataframe.columns:
        targets.extend(
            (str(level), subset)
            for level, subset in dataframe.groupby(
                "Machine", sort=True
            )
        )

    for label, subset in targets:
        try:
            counts, sizes = build_defect_rate_subgroups(
                dataframe=subset,
                subgroup_size=subgroup_size,
            )
            chart = p_chart(counts, sizes)
        except ValueError:
            continue

        beyond = chart.points_beyond_limits()

        rows.append(
            {
                "scope": label,
                "subgroup_count": len(chart.values),
                "p_bar_percent": round(100 * chart.center_line, 2),
                "ucl_percent": round(100 * chart.upper_limit, 2),
                "lcl_percent": round(100 * chart.lower_limit, 2),
                "out_of_control_points": len(beyond),
                "out_of_control_percent": round(
                    100 * len(beyond) / len(chart.values), 1
                ),
            }
        )

    table = pd.DataFrame(rows)

    if table.empty:
        print("부분군을 만들 수 없습니다.")
        return table

    print(table.to_string(index=False))
    print()

    overall = table[table["scope"] == "전체"]

    if not overall.empty:
        row = overall.iloc[0]
        print(
            f"  전체 평균 불량률 {row['p_bar_percent']}% "
            f"(관리한계 {row['lcl_percent']} ~ {row['ucl_percent']}%), "
            f"관리이탈 부분군 {row['out_of_control_points']}개"
        )

    machine_rows = table[table["scope"] != "전체"]

    if not machine_rows.empty:
        worst = machine_rows.loc[
            machine_rows["p_bar_percent"].idxmax()
        ]
        print(
            f"  설비별 평균 불량률 최고: {worst['scope']} "
            f"{worst['p_bar_percent']}%"
        )
        print(
            "  설비별 관리한계가 서로 겹치지 않으면 설비를 하나의 "
            "관리도로 묶어 관리하는 것 자체가 부적절하다는 신호다."
        )

    return table


def run_factor_comparison(
    dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """설비와 모델 간 차이를 분산분석과 Tukey HSD 로 검정한다."""
    _print_section("3. 설비 / 모델 간 비교  (ANOVA -> Tukey HSD)")

    responses = [
        column
        for column in CAPABILITY_CHARACTERISTICS + PROCESS_PARAMETERS
        if column in dataframe.columns
    ]

    anova_frames: list[pd.DataFrame] = []
    pairwise_frames: list[pd.DataFrame] = []

    for factor in STRATIFICATION_FACTORS:
        if factor not in dataframe.columns:
            continue

        anova_table, pairwise_table = (
            compare_factor_across_responses(
                dataframe=dataframe,
                factor=factor,
                responses=responses,
            )
        )

        if not anova_table.empty:
            anova_table.insert(0, "factor_name", factor)
            anova_frames.append(anova_table)

        if not pairwise_table.empty:
            pairwise_frames.append(pairwise_table)

        significant = (
            anova_table[anova_table["significant"]]
            if not anova_table.empty
            else pd.DataFrame()
        )

        print(f"[{factor}]  검정 대상 {len(anova_table)}개 특성")

        if significant.empty:
            print("  유의한 차이가 있는 특성이 없습니다.")
            print()
            continue

        display = significant[
            [
                "response",
                "f",
                "p_value",
                "eta_squared",
                "effect_size",
                "equal_variance",
            ]
        ].copy()

        display["f"] = display["f"].round(2)
        display["p_value"] = display["p_value"].map(
            lambda value: f"{value:.2e}"
        )
        display["eta_squared"] = display["eta_squared"].round(4)

        print(
            f"  유의한 차이 {len(significant)}개 "
            "(효과 크기 순)"
        )
        print(
            display.sort_values(
                "eta_squared", ascending=False
            ).to_string(index=False)
        )
        print()

    anova_result = (
        pd.concat(anova_frames, ignore_index=True)
        if anova_frames
        else pd.DataFrame()
    )

    pairwise_result = (
        pd.concat(pairwise_frames, ignore_index=True)
        if pairwise_frames
        else pd.DataFrame()
    )

    if not pairwise_result.empty:
        print("Tukey HSD 유의한 쌍별 비교 (상위 12건, p값 순)")

        display = pairwise_result.nsmallest(12, "p_value")[
            [
                "factor",
                "response",
                "group_a",
                "group_b",
                "mean_difference",
                "ci_lower",
                "ci_upper",
                "p_value",
            ]
        ].copy()

        for column in (
            "mean_difference",
            "ci_lower",
            "ci_upper",
        ):
            display[column] = display[column].round(4)

        display["p_value"] = display["p_value"].map(
            lambda value: f"{value:.2e}"
        )

        print(display.to_string(index=False))

    return anova_result, pairwise_result


def run_defect_rate_comparison(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """설비별 불량률과 주요 인자의 차이를 함께 본다."""
    _print_section("3-1. 설비별 불량률과 원인 인자 연결")

    if "Defect" not in dataframe.columns:
        return pd.DataFrame()

    working = dataframe.copy()
    working["is_defect"] = (
        working["Defect"] == "Delamination"
    ).astype(int)

    summary = (
        working.groupby("Machine")
        .agg(
            lot_count=("is_defect", "size"),
            defect_rate_percent=("is_defect", "mean"),
        )
        .assign(
            defect_rate_percent=lambda frame: (
                frame["defect_rate_percent"] * 100
            ).round(2)
        )
    )

    for parameter in MONITORED_PARAMETERS:
        if parameter not in working.columns:
            continue

        summary[f"{parameter}_mean"] = (
            working.groupby("Machine")[parameter].mean().round(3)
        )

    print(summary.to_string())
    print()

    worst_machine = summary["defect_rate_percent"].idxmax()
    best_machine = summary["defect_rate_percent"].idxmin()

    print(
        f"  불량률 최고 {worst_machine} "
        f"({summary.loc[worst_machine, 'defect_rate_percent']}%) vs "
        f"최저 {best_machine} "
        f"({summary.loc[best_machine, 'defect_rate_percent']}%)"
    )

    for parameter in MONITORED_PARAMETERS:
        if parameter not in working.columns:
            continue

        try:
            anova = one_way_anova(
                dataframe=working,
                response=parameter,
                factor="Machine",
            )
        except ValueError:
            continue

        if not anova.significant:
            continue

        comparisons = [
            comparison
            for comparison in tukey_hsd(
                dataframe=working,
                response=parameter,
                factor="Machine",
            )
            if comparison.significant
        ]

        if not comparisons:
            continue

        pairs = ", ".join(
            f"{comparison.group_a} vs {comparison.group_b} "
            f"({comparison.mean_difference:+.3f})"
            for comparison in comparisons[:3]
        )

        print(
            f"  {parameter}: 설비 간 차이 유의 "
            f"(eta^2={anova.eta_squared:.3f}) -> {pairs}"
        )

    return summary.reset_index()


def run_measurement_system_analysis() -> (
    tuple[pd.DataFrame, dict[str, float] | None]
):
    """Gage R&R 과 편향/선형성 분석을 수행한다."""
    _print_section(
        "4. 측정시스템 분석  (Gage R&R ANOVA 법, 편향, 선형성)"
    )

    data_dir = get_project_root() / "Data"

    gage_path = data_dir / "msa_gage_rnr_data.csv"
    bias_path = data_dir / "msa_bias_study_data.csv"

    if not gage_path.exists():
        print(
            "MSA 데이터가 없습니다. "
            "python -m src.data.generate_msa_data 를 먼저 실행하세요."
        )
        return pd.DataFrame(), None

    gage_data = pd.read_csv(gage_path)

    result = gage_rnr_anova(
        dataframe=gage_data,
        value_column=MSA_CHARACTERISTIC,
        tolerance=get_tolerance(MSA_CHARACTERISTIC),
    )

    lower_spec, upper_spec = get_spec_limits(MSA_CHARACTERISTIC)

    print(
        f"측정 특성: {MSA_CHARACTERISTIC}  "
        f"(규격 {lower_spec} ~ {upper_spec}, "
        f"공차 {get_tolerance(MSA_CHARACTERISTIC)})"
    )
    print(
        f"설계: 시료 {result.part_count} x "
        f"작업자 {result.operator_count} x "
        f"반복 {result.replicate_count}"
    )
    print()

    print("분산분석표")
    print(result.anova_table.round(6).to_string(index=False))
    print()

    print("분산 성분")
    print(result.variance_components().round(5).to_string(index=False))
    print()

    print(
        f"%GRR {result.percent_grr:.1f}%   "
        f"ndc {result.number_of_distinct_categories}   "
        f"%P/T {result.percent_precision_to_tolerance:.1f}%   "
        f"-> {result.verdict}"
    )

    if result.interaction_p_value is not None:
        pooled = (
            "오차항에 통합"
            if result.interaction_pooled
            else "유의하여 분리 유지"
        )
        print(
            f"부품 x 작업자 교호작용 p={result.interaction_p_value:.4f} "
            f"({pooled})"
        )

    print()
    print(f"  {result.diagnosis}")

    bias_result: dict[str, float] | None = None

    if bias_path.exists():
        bias_data = pd.read_csv(bias_path)

        bias_result = bias_and_linearity(
            dataframe=bias_data,
            measured_column=MSA_CHARACTERISTIC,
            reference_column="Reference",
        )

        print()
        print("편향 및 선형성")
        print(
            f"  편향        {bias_result['bias']:+.4f} "
            f"(p={bias_result['bias_p_value']:.4g}, "
            f"{'유의' if bias_result['bias_significant'] else '유의하지 않음'})"
        )
        print(
            f"  기울기      {bias_result['slope']:.4f} "
            f"(1에서 벗어난 정도가 선형성 이탈)"
        )
        print(f"  선형성      {bias_result['linearity']:.4f}")
        print(f"  R^2         {bias_result['r_squared']:.4f}")

        if bias_result["bias_significant"]:
            print(
                "  -> 계통 편향이 통계적으로 유의하다. "
                "계측기 영점 조정 또는 보정계수 적용이 필요하다."
            )

    return result.variance_components(), bias_result


def save_reports(
    capability_table: pd.DataFrame,
    stratified_table: pd.DataFrame,
    anova_table: pd.DataFrame,
    pairwise_table: pd.DataFrame,
    machine_summary: pd.DataFrame,
    variance_components: pd.DataFrame,
    defect_rate_table: pd.DataFrame,
) -> list[Path]:
    """분석 결과를 CSV로 저장한다."""
    report_dir = get_report_directory()

    outputs: list[tuple[str, pd.DataFrame]] = [
        ("quality_capability.csv", capability_table),
        ("quality_stratified_rule_signals.csv", stratified_table),
        ("quality_anova.csv", anova_table),
        ("quality_tukey_hsd.csv", pairwise_table),
        ("quality_machine_summary.csv", machine_summary),
        ("quality_defect_rate_p_chart.csv", defect_rate_table),
        ("quality_msa_variance_components.csv", variance_components),
    ]

    saved: list[Path] = []

    for filename, table in outputs:
        if table is None or table.empty:
            continue

        path = report_dir / filename
        table.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(path)

    return saved


def main() -> None:
    dataframe = load_process_data()

    print("=" * 78)
    print("Quality Analysis Suite")
    print("=" * 78)
    print(f"LOT 수: {len(dataframe):,}")

    if "Defect" in dataframe.columns:
        defect_rate = (
            100.0
            * (dataframe["Defect"] == "Delamination").mean()
        )
        print(f"박리 발생률: {defect_rate:.2f}%")

    capability_table = run_capability_analysis(dataframe)
    stratified_table = run_stratified_control_charts(dataframe)
    defect_rate_table = run_defect_rate_control_chart(dataframe)
    anova_table, pairwise_table = run_factor_comparison(dataframe)
    machine_summary = run_defect_rate_comparison(dataframe)
    variance_components, _ = run_measurement_system_analysis()

    saved = save_reports(
        capability_table=capability_table,
        stratified_table=stratified_table,
        anova_table=anova_table,
        pairwise_table=pairwise_table,
        machine_summary=machine_summary,
        variance_components=variance_components,
        defect_rate_table=defect_rate_table,
    )

    _print_section("저장된 리포트")

    for path in saved:
        print(f"  {path}")


if __name__ == "__main__":
    main()
