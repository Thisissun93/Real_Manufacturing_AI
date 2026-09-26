"""품질 분석 대시보드.

src/quality 의 분석 결과를 화면으로 보여준다.
명령줄(`python -m src.quality.run_quality_analysis`)과 같은 계산을 쓰고
출력만 다르다.

구성
----
1. 공정능력     Cp/Cpk(단기)와 Pp/Ppk(장기), 규격선이 있는 분포
2. 관리도       설비별 I-MR 관리도 + Nelson 판정 규칙 8종
3. 설비 비교    일원분산분석 -> Tukey HSD 신뢰구간
4. 측정시스템   Gage R&R 분산 성분, 작업자별 산포
5. 모델 운전점  검출률을 올릴 때 과검이 늘어나는 정도
"""

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.process_spec import (
    CAPABILITY_CHARACTERISTICS,
    MACHINES,
    PROCESS_PARAMETERS,
    get_spec_limits,
    get_tolerance,
    get_unit,
)
from src.quality.anova import one_way_anova, tukey_hsd
from src.quality.capability import analyze_capability
from src.quality.control_charts import (
    build_defect_rate_subgroups,
    individual_moving_range_chart,
    p_chart,
)
from src.quality.msa import bias_and_linearity, gage_rnr_anova
from src.quality.nelson_rules import (
    RULE_DESCRIPTIONS,
    evaluate_chart,
    summarize_violations,
)
from src.utils.plotting import (
    AXIS_LINE,
    GRIDLINE,
    INK_MUTED,
    INK_SECONDARY,
    SERIES_AQUA,
    SERIES_BLUE,
    SERIES_ORANGE,
    STATUS_CRITICAL,
    STATUS_GOOD,
    STATUS_WARNING,
    capability_color,
    create_figure,
    gage_color,
    severity_color,
)


# I-MR 관리도로 감시하면 안 되는 특성.
# 수율은 불량 발생에 의해 이봉분포가 되는 계수형 성격이라 p 관리도로 본다.
ATTRIBUTE_DRIVEN = ("Yield",)

MONITORED_PARAMETERS = (
    "CZ_Concentration",
    "Press2_Pressure",
    "Press2_Temp",
    "Cure_Temp",
    "Anneal_Temp",
)


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _verdict_badge(label: str, verdict: str, color: str) -> str:
    """판정을 색과 글자로 함께 표시한다.

    색만으로 뜻을 전하지 않는다. 색각 이상이거나 흑백으로 인쇄하면
    색은 사라지고 글자만 남는다.
    """
    return (
        f'<span style="display:inline-block;padding:2px 10px;'
        f"border-radius:4px;background:{color}22;color:{color};"
        f'font-weight:600;font-size:12px;">{label} {verdict}</span>'
    )


# =====================================================================
# 1. 공정능력
# =====================================================================


def show_capability(dataframe: pd.DataFrame) -> None:
    st.subheader("공정능력 분석")
    st.caption(
        "Cp/Cpk 는 부분군 내 변동으로 계산한 단기 능력이고, "
        "Pp/Ppk 는 전체 변동으로 계산한 장기 성능입니다. "
        "둘을 나란히 보는 이유는 아래 해석에 있습니다."
    )

    available = [
        column
        for column in CAPABILITY_CHARACTERISTICS
        if column in dataframe.columns
    ]

    if not available:
        st.info("공정능력을 계산할 품질 특성이 없습니다.")
        return

    characteristic = st.selectbox(
        "품질 특성",
        available,
        key="capability_characteristic",
    )

    lower_spec, upper_spec = get_spec_limits(characteristic)

    try:
        result = analyze_capability(
            series=dataframe[characteristic],
            characteristic=characteristic,
            lower_spec=lower_spec,
            upper_spec=upper_spec,
        )
    except ValueError as error:
        st.warning(str(error))
        return

    st.markdown(
        _verdict_badge(
            "판정",
            result.verdict,
            capability_color(result.verdict),
        ),
        unsafe_allow_html=True,
    )

    column1, column2, column3, column4 = st.columns(4)

    column1.metric(
        "Cp (단기)",
        "규격 한쪽" if result.cp is None else f"{result.cp:.2f}",
    )
    column2.metric(
        "Cpk (단기)",
        "N/A" if result.cpk is None else f"{result.cpk:.2f}",
    )
    column3.metric(
        "Pp (장기)",
        "규격 한쪽" if result.pp is None else f"{result.pp:.2f}",
    )
    column4.metric(
        "Ppk (장기)",
        "N/A" if result.ppk is None else f"{result.ppk:.2f}",
    )

    _render_capability_histogram(
        dataframe=dataframe,
        characteristic=characteristic,
        result=result,
    )

    st.markdown("**해석**")
    st.write(result.diagnosis)

    detail = pd.DataFrame(
        [
            ("표본 수", f"{result.sample_size:,}"),
            ("평균", f"{result.mean:.4f}"),
            (
                "부분군 내 표준편차",
                f"{result.sigma_within:.4f}",
            ),
            ("전체 표준편차", f"{result.sigma_overall:.4f}"),
            (
                "규격 하한 LSL",
                "없음" if lower_spec is None else f"{lower_spec}",
            ),
            (
                "규격 상한 USL",
                "없음" if upper_spec is None else f"{upper_spec}",
            ),
            (
                "Cp - Cpk (중심 이탈)",
                "N/A"
                if result.centering_gap is None
                else f"{result.centering_gap:.3f}",
            ),
            (
                "Cp - Pp (부분군 간 변동)",
                "N/A"
                if result.between_subgroup_gap is None
                else f"{result.between_subgroup_gap:.3f}",
            ),
            (
                "규격 이탈 실측",
                f"{result.observed_out_of_spec_count:,} 건",
            ),
            (
                "규격 이탈 추정",
                "N/A"
                if result.expected_ppm_out_of_spec is None
                else f"{result.expected_ppm_out_of_spec:,.0f} ppm",
            ),
        ],
        columns=["항목", "값"],
    )

    st.dataframe(detail, use_container_width=True, hide_index=True)


def _render_capability_histogram(
    dataframe: pd.DataFrame,
    characteristic: str,
    result,
) -> None:
    """규격선과 분포를 함께 그린다."""
    values = dataframe[characteristic].dropna().to_numpy(dtype=float)

    figure, axes = create_figure(height=3.8)

    axes.hist(
        values,
        bins=60,
        color=SERIES_BLUE,
        alpha=0.75,
        edgecolor=AXIS_LINE,
        linewidth=0.3,
    )

    axes.axvline(
        result.mean,
        color=INK_SECONDARY,
        linewidth=1.4,
        label=f"평균 {result.mean:.3f}",
    )

    for spec_value, spec_name in (
        (result.lower_spec, "LSL"),
        (result.upper_spec, "USL"),
    ):
        if spec_value is None:
            continue

        axes.axvline(
            spec_value,
            color=STATUS_CRITICAL,
            linewidth=1.6,
            linestyle="--",
            label=f"{spec_name} {spec_value:g}",
        )

    axes.set_xlabel(
        f"{characteristic} [{get_unit(characteristic)}]"
    )
    axes.set_ylabel("LOT 수")
    axes.set_title(
        f"{characteristic} 분포와 규격한계",
        loc="left",
    )
    axes.legend(loc="upper right")

    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)


# =====================================================================
# 2. 관리도
# =====================================================================


def show_control_charts(dataframe: pd.DataFrame) -> None:
    st.subheader("관리도와 Nelson 판정 규칙")
    st.caption(
        "관리한계는 부분군 내 변동(이동범위)으로 추정합니다. "
        "전체 표준편차로 계산하면 추세나 평균 이동이 한계 폭을 넓혀 "
        "정작 검출해야 할 신호를 감춥니다."
    )

    machine_options = ["전체"] + [
        machine
        for machine in MACHINES
        if "Machine" in dataframe.columns
        and machine in set(dataframe["Machine"])
    ]

    candidates = [
        column
        for column in list(CAPABILITY_CHARACTERISTICS)
        + list(MONITORED_PARAMETERS)
        if column in dataframe.columns
        and column not in ATTRIBUTE_DRIVEN
    ]

    if not candidates:
        st.info("감시할 계량형 특성이 없습니다.")
        return

    column1, column2, column3 = st.columns([1, 1, 1])

    with column1:
        machine = st.selectbox(
            "설비", machine_options, key="chart_machine"
        )

    with column2:
        characteristic = st.selectbox(
            "감시 항목", candidates, key="chart_characteristic"
        )

    with column3:
        max_points = st.slider(
            "표시할 LOT 수",
            min_value=100,
            max_value=800,
            value=300,
            step=50,
            key="chart_points",
            help="타점이 너무 많으면 패턴이 보이지 않습니다.",
        )

    subset = dataframe

    if machine != "전체" and "Machine" in dataframe.columns:
        subset = dataframe[dataframe["Machine"] == machine]

    series = subset[characteristic]

    if series.dropna().size < 30:
        st.warning("관리도를 그리기에 관측값이 부족합니다.")
        return

    chart, moving_range_chart = individual_moving_range_chart(series)
    violations = evaluate_chart(chart)

    summary = summarize_violations(
        violations,
        point_count=int(series.dropna().size),
    )

    st.markdown(
        _verdict_badge(
            "종합",
            str(summary["overall_severity"]),
            severity_color(str(summary["overall_severity"])),
        ),
        unsafe_allow_html=True,
    )

    _render_individual_chart(
        chart=chart,
        characteristic=characteristic,
        violations=violations,
        max_points=max_points,
        machine=machine,
    )

    _render_rule_table(summary, characteristic, machine)

    with st.expander("이동범위(MR) 관리도 보기"):
        _render_moving_range_chart(
            moving_range_chart, characteristic, max_points
        )


def _render_individual_chart(
    chart,
    characteristic: str,
    violations: list,
    max_points: int,
    machine: str,
) -> None:
    """개별값 관리도에 시그마 구역과 위반 구간을 표시한다."""
    values = chart.values[:max_points]
    zones = chart.sigma_zone_edges

    figure, axes = create_figure(height=4.4)

    # 위반 구간을 먼저 깔아 데이터가 위에 오게 한다.
    shaded = 0

    for violation in violations:
        if violation.start_index >= len(values):
            continue

        if shaded >= 80:
            break

        axes.axvspan(
            violation.start_index,
            min(violation.end_index, len(values) - 1),
            color=STATUS_CRITICAL,
            alpha=0.07,
            linewidth=0,
        )
        shaded += 1

    # 1/2 시그마 구역 경계는 보조선이므로 뒤로 물린다.
    for edge_key in ("plus_1", "plus_2", "minus_1", "minus_2"):
        axes.axhline(
            zones[edge_key],
            color=GRIDLINE,
            linewidth=0.8,
            linestyle=":",
            zorder=1,
        )

    axes.plot(
        range(len(values)),
        values,
        color=SERIES_BLUE,
        linewidth=1.1,
        marker="o",
        markersize=2.6,
        markerfacecolor=SERIES_BLUE,
        markeredgecolor="none",
        zorder=3,
    )

    axes.axhline(
        chart.center_line,
        color=INK_SECONDARY,
        linewidth=1.3,
        zorder=2,
    )

    for bound, name in (
        (chart.upper_limit, "UCL"),
        (chart.lower_limit, "LCL"),
    ):
        axes.axhline(
            bound,
            color=STATUS_WARNING,
            linewidth=1.4,
            linestyle="--",
            zorder=2,
        )
        axes.annotate(
            f"{name} {bound:.3f}",
            xy=(len(values), bound),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=INK_SECONDARY,
        )

    axes.annotate(
        f"CL {chart.center_line:.3f}",
        xy=(len(values), chart.center_line),
        xytext=(4, 0),
        textcoords="offset points",
        va="center",
        fontsize=8,
        color=INK_SECONDARY,
    )

    title_scope = "전체 설비" if machine == "전체" else machine

    axes.set_title(
        f"{characteristic} 개별값 관리도 · {title_scope} "
        f"(앞 {len(values)} LOT)",
        loc="left",
    )
    axes.set_xlabel("LOT 순서")
    axes.set_ylabel(f"{characteristic} [{get_unit(characteristic)}]")
    axes.margins(x=0.02)

    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)

    st.caption(
        "붉은 음영은 판정 규칙 위반 구간입니다. "
        "점선은 1·2 시그마 구역 경계이고, 주황 파선이 관리한계입니다."
    )


def _render_moving_range_chart(
    chart,
    characteristic: str,
    max_points: int,
) -> None:
    values = chart.values[:max_points]

    figure, axes = create_figure(height=2.8)

    axes.plot(
        range(len(values)),
        values,
        color=SERIES_ORANGE,
        linewidth=1.0,
    )

    axes.axhline(
        chart.center_line,
        color=INK_SECONDARY,
        linewidth=1.2,
    )
    axes.axhline(
        chart.upper_limit,
        color=STATUS_WARNING,
        linewidth=1.3,
        linestyle="--",
    )

    axes.set_title(
        f"{characteristic} 이동범위 관리도 "
        f"(UCL {chart.upper_limit:.4f})",
        loc="left",
    )
    axes.set_xlabel("LOT 순서")
    axes.set_ylabel("이동범위")

    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)

    st.caption(
        "이동범위 관리도는 산포의 변화를 본다. "
        "여기가 먼저 흔들리면 평균 관리도의 한계 자체를 신뢰할 수 없다."
    )


def _render_rule_table(
    summary: dict,
    characteristic: str,
    machine: str,
) -> None:
    """규칙별 관측 건수와 기대 오경보를 비교한다."""
    by_rule = summary["by_rule"]
    expected = summary["expected_false_alarms"]
    signals = summary["signal_rules"]

    if not by_rule:
        st.success("판정 규칙 위반이 없습니다.")
        return

    rows = []

    for rule_number in range(1, 9):
        key = f"NELSON_RULE_{rule_number}"
        observed = by_rule.get(key, 0)
        expected_count = expected.get(key, 0.0)

        ratio = (
            observed / expected_count
            if expected_count > 0
            else float("nan")
        )

        rows.append(
            {
                "규칙": f"규칙 {rule_number}",
                "내용": RULE_DESCRIPTIONS[rule_number],
                "관측": observed,
                "기대 오경보": round(expected_count, 1),
                "배수": round(ratio, 1)
                if np.isfinite(ratio)
                else None,
                "판정": "신호" if key in signals else "우연 수준",
            }
        )

    table = pd.DataFrame(rows)

    st.markdown("**판정 규칙별 관측 대 기대**")
    st.caption(
        "판정 규칙은 관리상태에서도 오경보를 냅니다. "
        "타점이 많으면 규칙 1 하나로도 우연히 수십 건이 나옵니다. "
        "그래서 건수가 아니라 기대 오경보 대비 배수로 판단합니다. "
        "기대값의 2배 이상이면 신호로 봅니다."
    )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )

    if signals:
        strongest = max(
            signals.items(), key=lambda item: item[1]["ratio"]
        )
        rule_key, statistics = strongest
        rule_number = int(rule_key.rsplit("_", 1)[1])

        scope = "전체 설비" if machine == "전체" else machine

        st.error(
            f"{scope} 의 {characteristic} 에서 "
            f"규칙 {rule_number}({RULE_DESCRIPTIONS[rule_number]}) 위반이 "
            f"기대 오경보 {statistics['expected']:.1f}건의 "
            f"{statistics['ratio']:.1f}배인 "
            f"{statistics['observed']:.0f}건입니다."
        )
    else:
        st.success(
            "모든 규칙의 위반 건수가 관리상태 기대 오경보 수준입니다. "
            "우연으로 설명됩니다."
        )


# =====================================================================
# 2-1. 불량률 p 관리도
# =====================================================================


def show_defect_rate_chart(dataframe: pd.DataFrame) -> None:
    st.subheader("불량률 p 관리도")
    st.caption(
        "수율과 불량률은 이항분포를 따르는 계수형 데이터입니다. "
        "계량형 관리도에 올리면 불량 LOT 이 전부 규칙 1 위반으로 잡히는데, "
        "이상 신호가 아니라 차트 선택이 틀린 것입니다."
    )

    if "Defect" not in dataframe.columns:
        st.info("Defect 컬럼이 없습니다.")
        return

    subgroup_size = st.slider(
        "부분군 크기 (LOT)",
        min_value=20,
        max_value=200,
        value=50,
        step=10,
        key="p_chart_subgroup",
    )

    scope_options = ["전체"] + [
        machine
        for machine in MACHINES
        if "Machine" in dataframe.columns
        and machine in set(dataframe["Machine"])
    ]

    scope = st.selectbox("범위", scope_options, key="p_chart_scope")

    subset = dataframe

    if scope != "전체":
        subset = dataframe[dataframe["Machine"] == scope]

    try:
        counts, sizes = build_defect_rate_subgroups(
            dataframe=subset,
            subgroup_size=subgroup_size,
        )
        chart = p_chart(counts, sizes)
    except ValueError as error:
        st.warning(str(error))
        return

    beyond = chart.points_beyond_limits()

    column1, column2, column3 = st.columns(3)
    column1.metric("평균 불량률", f"{chart.center_line * 100:.2f}%")
    column2.metric("관리상한", f"{chart.upper_limit * 100:.2f}%")
    column3.metric("관리이탈 부분군", f"{len(beyond)}개")

    figure, axes = create_figure(height=3.6)

    proportions = chart.values * 100

    axes.plot(
        range(len(proportions)),
        proportions,
        color=SERIES_BLUE,
        linewidth=1.3,
        marker="o",
        markersize=4,
        markeredgecolor="none",
    )

    if beyond.size:
        axes.scatter(
            beyond,
            proportions[beyond],
            s=54,
            facecolor=STATUS_CRITICAL,
            edgecolor="white",
            linewidth=1.1,
            zorder=4,
            label=f"관리이탈 {len(beyond)}점",
        )

    axes.axhline(
        chart.center_line * 100,
        color=INK_SECONDARY,
        linewidth=1.3,
        label=f"p̄ {chart.center_line * 100:.2f}%",
    )
    axes.axhline(
        chart.upper_limit * 100,
        color=STATUS_WARNING,
        linewidth=1.4,
        linestyle="--",
        label=f"UCL {chart.upper_limit * 100:.2f}%",
    )

    if chart.lower_limit > 0:
        axes.axhline(
            chart.lower_limit * 100,
            color=STATUS_WARNING,
            linewidth=1.4,
            linestyle="--",
            label=f"LCL {chart.lower_limit * 100:.2f}%",
        )

    axes.set_title(
        f"불량률 p 관리도 · {scope} "
        f"(부분군 {subgroup_size} LOT)",
        loc="left",
    )
    axes.set_xlabel("부분군 순서")
    axes.set_ylabel("불량률 [%]")
    axes.legend(loc="upper right")

    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)


# =====================================================================
# 3. 설비 비교
# =====================================================================


def show_factor_comparison(dataframe: pd.DataFrame) -> None:
    st.subheader("설비·모델 간 비교")
    st.caption(
        "설비가 3대면 쌍별 비교가 3번입니다. 각 비교를 5% 유의수준으로 하면 "
        "어느 하나라도 유의하게 나올 확률이 14%까지 올라갑니다. "
        "그래서 분산분석으로 먼저 판정하고, 유의할 때만 Tukey HSD 로 "
        "어느 쌍이 다른지 봅니다."
    )

    factor_options = [
        column
        for column in ("Machine", "Model")
        if column in dataframe.columns
    ]

    if not factor_options:
        st.info("비교할 인자 컬럼이 없습니다.")
        return

    responses = [
        column
        for column in list(CAPABILITY_CHARACTERISTICS)
        + list(PROCESS_PARAMETERS)
        if column in dataframe.columns
    ]

    column1, column2 = st.columns(2)

    with column1:
        factor = st.selectbox(
            "비교 인자", factor_options, key="anova_factor"
        )

    with column2:
        response = st.selectbox(
            "품질 특성 / 공정 인자",
            responses,
            key="anova_response",
        )

    try:
        result = one_way_anova(
            dataframe=dataframe,
            response=response,
            factor=factor,
        )
    except ValueError as error:
        st.warning(str(error))
        return

    verdict = "차이 있음" if result.significant else "차이 없음"
    color = STATUS_CRITICAL if result.significant else STATUS_GOOD

    st.markdown(
        _verdict_badge("분산분석", verdict, color),
        unsafe_allow_html=True,
    )

    column1, column2, column3, column4 = st.columns(4)

    column1.metric("F 통계량", f"{result.f_statistic:.2f}")
    column2.metric(
        "p 값",
        f"{result.p_value:.2e}"
        if result.equal_variance_assumed
        else f"{result.welch_p_value:.2e}",
    )
    column3.metric(
        "효과 크기 eta²",
        f"{result.eta_squared:.4f}",
        help=f"효과 크기: {result.effect_size_label}",
    )
    column4.metric(
        "등분산 가정",
        "성립" if result.equal_variance_assumed else "기각",
        help=f"Levene 검정 p = {result.levene_p_value:.4f}",
    )

    st.write(result.diagnosis)

    st.markdown("**수준별 요약**")
    summary = result.group_summary.copy()
    summary.columns = ["수준", "n", "평균", "표준편차", "최소", "최대"]

    st.dataframe(
        summary.round(4),
        use_container_width=True,
        hide_index=True,
    )

    if not result.significant:
        st.info(
            "분산분석에서 유의한 차이가 없으므로 "
            "Tukey HSD 다중비교로 넘어가지 않습니다."
        )
        return

    _render_tukey(dataframe, response, factor)


def _render_tukey(
    dataframe: pd.DataFrame,
    response: str,
    factor: str,
) -> None:
    """Tukey HSD 결과를 신뢰구간 그래프로 그린다.

    막대그래프 대신 신뢰구간을 쓰는 이유는, 판정의 근거가
    '구간이 0을 포함하는가'이기 때문이다. 그림이 곧 판정이 된다.
    """
    comparisons = tukey_hsd(
        dataframe=dataframe,
        response=response,
        factor=factor,
    )

    if not comparisons:
        st.info("비교할 쌍이 없습니다.")
        return

    st.markdown("**Tukey HSD 다중비교**")

    labels = [
        f"{item.group_a}\nvs {item.group_b}" for item in comparisons
    ]
    differences = [item.mean_difference for item in comparisons]
    lowers = [item.confidence_lower for item in comparisons]
    uppers = [item.confidence_upper for item in comparisons]
    significant = [item.significant for item in comparisons]

    positions = np.arange(len(comparisons))

    figure, axes = create_figure(
        height=max(2.4, 0.85 * len(comparisons) + 1.4)
    )

    axes.axvline(
        0.0,
        color=INK_MUTED,
        linewidth=1.2,
        linestyle="--",
        zorder=1,
    )

    for index, is_significant in enumerate(significant):
        color = STATUS_CRITICAL if is_significant else INK_MUTED

        axes.plot(
            [lowers[index], uppers[index]],
            [positions[index], positions[index]],
            color=color,
            linewidth=2.0,
            solid_capstyle="round",
            zorder=2,
        )

        axes.scatter(
            [differences[index]],
            [positions[index]],
            s=58,
            facecolor=color,
            edgecolor="white",
            linewidth=1.2,
            zorder=3,
        )

        axes.annotate(
            "유의" if is_significant else "유의하지 않음",
            xy=(uppers[index], positions[index]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=color,
        )

    axes.set_yticks(positions)
    axes.set_yticklabels(labels, fontsize=8)
    axes.invert_yaxis()
    axes.set_xlabel(f"{response} 평균 차이 (95% 신뢰구간)")
    axes.set_title(
        f"{factor} 수준 간 {response} 차이",
        loc="left",
    )
    axes.grid(axis="y", visible=False)
    axes.margins(x=0.22)

    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)

    st.caption(
        "신뢰구간이 0(세로 점선)을 넘지 않으면 두 수준의 평균이 "
        "통계적으로 다릅니다. 전체 유의수준은 5%로 유지됩니다."
    )

    table = pd.DataFrame(
        [
            {
                "수준 A": item.group_a,
                "수준 B": item.group_b,
                "평균 차이": round(item.mean_difference, 4),
                "하한": round(item.confidence_lower, 4),
                "상한": round(item.confidence_upper, 4),
                "p 값": f"{item.p_value:.2e}",
                "판정": "유의" if item.significant else "유의하지 않음",
            }
            for item in comparisons
        ]
    )

    st.dataframe(table, use_container_width=True, hide_index=True)


# =====================================================================
# 4. 측정시스템 분석
# =====================================================================


def show_measurement_system() -> None:
    st.subheader("측정시스템 분석 (Gage R&R)")
    st.caption(
        "현장의 계측기 검교정과 작업자 간 비교가 통계적으로는 "
        "반복성(계측기 자체 산포)과 재현성(작업자가 바뀔 때의 산포)입니다. "
        "AIAG MSA 4판의 ANOVA 법으로 계산합니다."
    )

    data_dir = get_project_root() / "Data"
    gage_path = data_dir / "msa_gage_rnr_data.csv"
    bias_path = data_dir / "msa_bias_study_data.csv"

    if not gage_path.exists():
        st.warning(
            "MSA 데이터가 없습니다. 아래 명령을 먼저 실행하세요.\n\n"
            "`python -m src.data.generate_msa_data`"
        )
        return

    gage_data = pd.read_csv(gage_path)

    value_columns = [
        column
        for column in gage_data.columns
        if column not in ("Part", "Operator", "Replicate", "TrueValue")
    ]

    if not value_columns:
        st.warning("측정값 컬럼을 찾을 수 없습니다.")
        return

    characteristic = value_columns[0]

    try:
        result = gage_rnr_anova(
            dataframe=gage_data,
            value_column=characteristic,
            tolerance=get_tolerance(characteristic),
        )
    except ValueError as error:
        st.warning(str(error))
        return

    st.markdown(
        _verdict_badge(
            "판정", result.verdict, gage_color(result.verdict)
        ),
        unsafe_allow_html=True,
    )

    column1, column2, column3, column4 = st.columns(4)

    column1.metric("%GRR", f"{result.percent_grr:.1f}%")
    column2.metric(
        "ndc",
        f"{result.number_of_distinct_categories}",
        help="구별 가능 범주 수. 5 이상이어야 구간 판정이 가능합니다.",
    )
    column3.metric(
        "%P/T",
        "N/A"
        if result.percent_precision_to_tolerance is None
        else f"{result.percent_precision_to_tolerance:.1f}%",
        help="공차 대비 측정 산포.",
    )
    column4.metric("주된 원인", result.dominant_source)

    st.write(result.diagnosis)

    _render_variance_components(result)
    _render_operator_spread(gage_data, characteristic)

    with st.expander("분산분석표 보기"):
        anova_table = result.anova_table.copy()
        anova_table.columns = ["요인", "자유도", "제곱합", "평균제곱"]
        st.dataframe(
            anova_table.round(6),
            use_container_width=True,
            hide_index=True,
        )

        if result.interaction_p_value is not None:
            pooled = (
                "오차항에 통합했습니다"
                if result.interaction_pooled
                else "유의하여 분리 유지했습니다"
            )
            st.caption(
                f"부품 x 작업자 교호작용 p = "
                f"{result.interaction_p_value:.4f} · {pooled} "
                "(AIAG 기준 p > 0.25 이면 통합)"
            )

    if bias_path.exists():
        _render_bias(bias_path, characteristic)


def _render_variance_components(result) -> None:
    """분산 성분을 가로 막대로 그린다."""
    components = result.variance_components()
    components = components[components["source"] != "총 변동(TV)"]

    figure, axes = create_figure(height=3.0)

    labels = components["source"].tolist()
    percents = components["percent_study_variation"].tolist()

    positions = np.arange(len(labels))

    colors = [
        STATUS_CRITICAL
        if label.startswith("측정시스템")
        else SERIES_AQUA
        if label.startswith("부품")
        else SERIES_BLUE
        for label in labels
    ]

    axes.barh(
        positions,
        percents,
        color=colors,
        height=0.62,
    )

    for position, percent in zip(positions, percents):
        axes.annotate(
            f"{percent:.1f}%",
            xy=(percent, position),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=INK_SECONDARY,
        )

    axes.set_yticks(positions)
    axes.set_yticklabels(labels, fontsize=9)
    axes.invert_yaxis()
    axes.set_xlabel("총 변동 대비 비율 [%]")
    axes.set_title("분산 성분", loc="left")
    axes.grid(axis="y", visible=False)
    axes.margins(x=0.14)

    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)

    st.caption(
        "측정시스템(GRR)이 10% 미만이면 적합, 10~30%는 조건부 적합, "
        "30%를 넘으면 이 계측기로 공정 판정을 할 수 없습니다."
    )


def _render_operator_spread(
    gage_data: pd.DataFrame,
    characteristic: str,
) -> None:
    """작업자별로 부품 측정 평균을 겹쳐 그린다.

    선들이 나란하면 작업자 간 편향만 있는 것이고,
    선들이 엇갈리면 부품 x 작업자 교호작용이 있는 것이다.
    """
    pivot = (
        gage_data.groupby(["Part", "Operator"])[characteristic]
        .mean()
        .unstack()
    )

    if pivot.empty:
        return

    figure, axes = create_figure(height=3.4)

    palette = (SERIES_BLUE, SERIES_ORANGE, SERIES_AQUA)

    for index, operator in enumerate(pivot.columns):
        axes.plot(
            range(len(pivot.index)),
            pivot[operator].to_numpy(),
            color=palette[index % len(palette)],
            marker="o",
            markersize=5,
            markeredgecolor="white",
            markeredgewidth=0.8,
            linewidth=1.5,
            label=str(operator),
        )

    axes.set_xticks(range(len(pivot.index)))
    axes.set_xticklabels(pivot.index, rotation=45, ha="right", fontsize=8)
    axes.set_xlabel("시료")
    axes.set_ylabel(
        f"{characteristic} 평균 [{get_unit(characteristic)}]"
    )
    axes.set_title("작업자별 시료 측정 평균", loc="left")
    axes.legend(title="작업자", loc="best", title_fontsize=8)

    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)

    st.caption(
        "선들이 나란하면 작업자 간 편향만 있는 것이고, "
        "선들이 엇갈리면 특정 작업자가 특정 시료에서만 다르게 측정하는 "
        "교호작용이 있는 것입니다."
    )


def _render_bias(bias_path: Path, characteristic: str) -> None:
    """편향과 선형성을 표시한다."""
    bias_data = pd.read_csv(bias_path)

    if "Reference" not in bias_data.columns:
        return

    try:
        result = bias_and_linearity(
            dataframe=bias_data,
            measured_column=characteristic,
            reference_column="Reference",
        )
    except ValueError:
        return

    st.markdown("**편향과 선형성**")
    st.caption(
        "기준값이 알려진 표준 시료를 측정해, 계측기가 전 구간에서 "
        "일정하게 치우쳐 있는지(편향)와 구간에 따라 치우침이 "
        "달라지는지(선형성)를 봅니다."
    )

    column1, column2, column3 = st.columns(3)

    column1.metric(
        "편향",
        f"{result['bias']:+.4f}",
        help=f"p = {result['bias_p_value']:.4g}",
    )
    column2.metric(
        "회귀 기울기",
        f"{result['slope']:.4f}",
        help="1에서 벗어난 정도가 선형성 이탈입니다.",
    )
    column3.metric("R²", f"{result['r_squared']:.4f}")

    if result["bias_significant"]:
        st.error(
            "계통 편향이 통계적으로 유의합니다. "
            "계측기 영점 조정 또는 보정계수 적용이 필요합니다."
        )
    else:
        st.success("계통 편향이 통계적으로 유의하지 않습니다.")

    figure, axes = create_figure(height=3.2)

    reference = bias_data["Reference"].to_numpy(dtype=float)
    measured = bias_data[characteristic].to_numpy(dtype=float)

    axes.scatter(
        reference,
        measured,
        s=26,
        facecolor=SERIES_BLUE,
        edgecolor="white",
        linewidth=0.5,
        alpha=0.85,
        label="측정값",
    )

    line_x = np.linspace(reference.min(), reference.max(), 100)

    axes.plot(
        line_x,
        line_x,
        color=INK_MUTED,
        linewidth=1.2,
        linestyle="--",
        label="기준선 (기울기 1)",
    )

    axes.plot(
        line_x,
        result["intercept"] + result["slope"] * line_x,
        color=STATUS_CRITICAL,
        linewidth=1.6,
        label=f"회귀선 (기울기 {result['slope']:.3f})",
    )

    axes.set_xlabel(f"기준값 [{get_unit(characteristic)}]")
    axes.set_ylabel(f"측정값 [{get_unit(characteristic)}]")
    axes.set_title("편향·선형성", loc="left")
    axes.legend(loc="upper left")

    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)


# =====================================================================
# 5. 모델 운전점
# =====================================================================


def show_operating_points() -> None:
    st.subheader("불량 예측 모델 운전점")
    st.caption(
        "현장에서 필요한 판단은 '모델 성능이 얼마인가'가 아니라 "
        "'검출률을 얼마로 잡으면 재검사 물량이 얼마나 늘어나는가'입니다."
    )

    report_dir = get_project_root() / "report"

    operating_path = report_dir / "model_operating_points.csv"
    comparison_path = report_dir / "model_comparison.csv"

    if not operating_path.exists():
        st.warning(
            "모델 평가 결과가 없습니다. 아래 명령을 먼저 실행하세요.\n\n"
            "`python -m src.ml.train_model`"
        )
        return

    operating_points = pd.read_csv(operating_path)

    if comparison_path.exists():
        comparison = pd.read_csv(comparison_path)
        _render_model_comparison(comparison)

    _render_operating_curve(operating_points)

    table = operating_points.copy()

    for column in (
        "target_recall",
        "achieved_recall",
        "precision",
        "false_alarm_rate",
        "escape_rate",
    ):
        if column in table.columns:
            table[column] = (table[column] * 100).round(1)

    table = table.rename(
        columns={
            "target_recall": "목표 검출률 %",
            "threshold": "임계값",
            "achieved_recall": "달성 검출률 %",
            "precision": "정밀도 %",
            "false_alarm_rate": "과검률 %",
            "escape_rate": "미검률 %",
            "flagged_lots": "의심 LOT 수",
            "missed_defects": "놓친 불량 수",
        }
    )

    st.dataframe(table, use_container_width=True, hide_index=True)

    st.caption(
        "과검은 정상 LOT 을 불량으로 의심해 재검사 공수가 드는 것이고, "
        "미검은 불량이 그대로 흘러가는 것입니다. 두 오류의 비용이 다르므로 "
        "하나의 숫자로 합치지 않습니다."
    )


def _render_model_comparison(comparison: pd.DataFrame) -> None:
    """더미 대비 성능을 표시한다."""
    if "model" not in comparison.columns:
        return

    primary = comparison[comparison["model"] == "RandomForest"]
    dummy = comparison[
        comparison["model"].str.startswith("Dummy")
    ]

    if primary.empty:
        return

    primary_row = primary.iloc[0]

    column1, column2, column3, column4 = st.columns(4)

    column1.metric("PR-AUC", f"{primary_row['pr_auc']:.4f}")

    if not dummy.empty:
        dummy_auc = float(dummy.iloc[0]["pr_auc"])
        lift = (
            primary_row["pr_auc"] / dummy_auc
            if dummy_auc > 0
            else float("nan")
        )
        column2.metric(
            "더미 대비",
            f"{lift:.2f}배",
            help=(
                "전부 정상으로 예측하는 모델 대비 배수. "
                "이 비교 없이 정확도만 보면 의미가 없습니다."
            ),
        )

    column3.metric("검출률", f"{primary_row['recall'] * 100:.1f}%")
    column4.metric(
        "과검률",
        f"{primary_row['false_alarm_rate'] * 100:.1f}%",
    )

    with st.expander("모델 비교표 보기"):
        display = comparison.copy()

        for column in (
            "recall",
            "precision",
            "false_alarm_rate",
            "escape_rate",
        ):
            if column in display.columns:
                display[column] = (display[column] * 100).round(1)

        st.dataframe(
            display, use_container_width=True, hide_index=True
        )


def _render_operating_curve(operating_points: pd.DataFrame) -> None:
    """검출률과 과검률의 상충 관계를 그린다."""
    required = {"achieved_recall", "false_alarm_rate"}

    if not required.issubset(set(operating_points.columns)):
        return

    recall = operating_points["achieved_recall"].to_numpy() * 100
    false_alarm = (
        operating_points["false_alarm_rate"].to_numpy() * 100
    )

    figure, axes = create_figure(height=3.6)

    axes.plot(
        recall,
        false_alarm,
        color=SERIES_BLUE,
        linewidth=1.8,
        marker="o",
        markersize=7,
        markeredgecolor="white",
        markeredgewidth=1.0,
    )

    for index in range(len(recall)):
        axes.annotate(
            f"{recall[index]:.0f}% / {false_alarm[index]:.0f}%",
            xy=(recall[index], false_alarm[index]),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            fontsize=7.5,
            color=INK_SECONDARY,
        )

    axes.set_xlabel("검출률 (실제 불량 중 잡아낸 비율) [%]")
    axes.set_ylabel("과검률 (정상인데 의심받은 비율) [%]")
    axes.set_title(
        "검출률을 올릴 때 치르는 대가", loc="left"
    )
    axes.margins(x=0.10, y=0.18)

    figure.tight_layout()
    st.pyplot(figure, use_container_width=True)


# =====================================================================
# 진입점
# =====================================================================


def show_quality_analysis(dataframe: pd.DataFrame) -> None:
    """품질 분석 탭 전체를 렌더링한다."""
    st.header("품질 분석")
    st.caption(
        "JMP 로 수행하던 통계 분석을 코드로 옮긴 결과입니다. "
        "명령줄 `python -m src.quality.run_quality_analysis` 와 "
        "같은 계산을 사용합니다."
    )

    (
        capability_tab,
        chart_tab,
        comparison_tab,
        msa_tab,
        model_tab,
    ) = st.tabs(
        [
            "공정능력",
            "관리도",
            "설비 비교",
            "측정시스템",
            "모델 운전점",
        ]
    )

    with capability_tab:
        show_capability(dataframe)

    with chart_tab:
        show_control_charts(dataframe)
        st.divider()
        show_defect_rate_chart(dataframe)

    with comparison_tab:
        show_factor_comparison(dataframe)

    with msa_tab:
        show_measurement_system()

    with model_tab:
        show_operating_points()
