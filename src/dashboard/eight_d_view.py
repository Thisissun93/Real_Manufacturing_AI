"""8D 문제해결 리포트 화면.

관리도와 분산분석이 찾아낸 이상을 조치로 잇는 화면이다.
앞의 다섯 탭이 "무엇이 이상한가"를 말한다면 여기는
"그래서 누가 무엇을 하고 어떻게 확인하는가"를 말한다.

화면 구성
--------
사례 선택 -> 진행 현황 -> D0~D8 순서.
D4 에는 발생원인과 유출원인을 나란히 둔다. 둘을 한 화면에 놓는 것이
이 탭의 핵심이다. 불량을 없애는 조치와 검출 체계를 고치는 조치는
서로 다른 일이고, 하나만 하면 같은 문제가 다시 나온다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from src.quality.eight_d import (
    ACTION_DONE,
    ACTION_ONGOING,
    ACTION_PENDING,
    DISCIPLINE_TITLES,
    STATUS_CONFIRMED,
    STATUS_EXCLUDED,
    STATUS_UNVERIFIED,
    Action,
    EightDReport,
    WhyStep,
    build_recommended_cases,
    build_verification_table,
    get_report_directory,
    missing_reports,
    rank_defect_cases,
    render_markdown,
)
from src.quality.eight_d import (
    _machine_parameter_gaps as machine_parameter_gaps,
)
from src.utils.plotting import (
    AXIS_LINE,
    INK_MUTED,
    INK_SECONDARY,
    SERIES_BLUE,
    STATUS_CRITICAL,
    STATUS_GOOD,
    STATUS_WARNING,
    create_figure,
)


# 평균 이동이 한쪽 공차의 몇 %를 먹으면 위험한가.
# 20%를 넘으면 산포가 그대로여도 Cpk 가 눈에 띄게 떨어진다.
TOLERANCE_WARNING: float = 0.10
TOLERANCE_CRITICAL: float = 0.20

CAUSE_STATUS_COLORS: dict[str, str] = {
    STATUS_CONFIRMED: STATUS_CRITICAL,
    STATUS_UNVERIFIED: STATUS_WARNING,
    STATUS_EXCLUDED: STATUS_GOOD,
}

ACTION_STATUS_COLORS: dict[str, str] = {
    ACTION_DONE: STATUS_GOOD,
    ACTION_ONGOING: STATUS_WARNING,
    ACTION_PENDING: INK_MUTED,
    "검증 대기": STATUS_WARNING,
}


def _chip(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 9px;'
        f"margin:0 4px 4px 0;border-radius:4px;background:{color}1f;"
        f'color:{color};font-weight:600;font-size:12px;">{text}</span>'
    )


# =====================================================================
# 사례 불러오기
# =====================================================================


@st.cache_data(show_spinner=False)
def load_cases() -> list[EightDReport]:
    """분석 결과에서 8D 사례를 만든다.

    report/*.csv 만 읽으므로 가볍다. 파일이 바뀌면
    Streamlit 이 앱을 다시 띄우면서 캐시도 비워진다.
    """
    return build_recommended_cases()


# =====================================================================
# 진행 현황
# =====================================================================


def _render_progress(report: EightDReport) -> None:
    status = report.discipline_status

    st.markdown(
        "".join(
            _chip(
                f"{code} {status[code]}",
                ACTION_STATUS_COLORS.get(status[code], INK_MUTED),
            )
            for code in DISCIPLINE_TITLES
        ),
        unsafe_allow_html=True,
    )

    st.caption(
        "분석 단계(D1·D2·D4)는 데이터로 닫을 수 있지만 "
        "D0·D3·D5·D7 은 현장에서 사람이 실행해야 닫힌다. "
        "미착수로 표시된 것은 결함이 아니라 현재 상태다."
    )


def _render_actions(actions: tuple[Action, ...]) -> None:
    if not actions:
        st.info("등록된 조치가 없습니다.")
        return

    st.dataframe(
        pd.DataFrame([action.as_row() for action in actions]),
        width="stretch",
        hide_index=True,
    )

    for action in actions:
        for item in action.evidence:
            st.caption(f"근거 · {item.as_line()}")


# =====================================================================
# D2 문제 기술
# =====================================================================


def _render_problem(report: EightDReport) -> None:
    problem = report.d2_problem

    if problem is None:
        st.info("문제 기술이 없습니다.")
        return

    left, right = st.columns([3, 2])

    with left:
        st.markdown("**5W2H**")
        st.dataframe(
            pd.DataFrame(problem.as_rows()),
            width="stretch",
            hide_index=True,
        )

    with right:
        st.markdown("**IS / IS-NOT**")
        st.caption(
            "발생한 곳만 보면 원인이 좁혀지지 않는다. "
            "비슷한 조건인데 발생하지 않은 곳을 함께 적으면 "
            "둘의 차이가 원인 후보로 남는다."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "구분": "발생함(IS)",
                        "대상": ", ".join(problem.is_observed),
                    },
                    {
                        "구분": "발생하지 않음(IS-NOT)",
                        "대상": ", ".join(problem.is_not_observed),
                    },
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    for item in problem.evidence:
        st.caption(f"근거 · {item.as_line()}")


# =====================================================================
# D4 근본원인
# =====================================================================


def _render_why_chain(steps: tuple[WhyStep, ...], title: str) -> None:
    st.markdown(f"**{title}**")

    if not steps:
        st.info("분석 내용이 없습니다.")
        return

    for step in steps:
        color = STATUS_GOOD if step.verified else STATUS_WARNING
        st.markdown(
            f"{_chip(step.marker, color)} "
            f"**{step.depth}. {step.question}**",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="margin:-2px 0 10px 8px;'
            f'padding-left:12px;border-left:2px solid {AXIS_LINE};'
            f'color:{INK_SECONDARY};font-size:14px;">'
            f"{step.answer}</div>",
            unsafe_allow_html=True,
        )

        for item in step.evidence:
            st.caption(f"근거 · {item.as_line()}")


def _render_cause_table(report: EightDReport) -> None:
    if not report.d4_causes:
        st.info("원인 후보가 없습니다.")
        return

    st.markdown("**특성요인 정리 (6M)**")
    st.caption(
        "확인되지 않은 것을 확인한 것처럼 적지 않는다. "
        "미확인으로 남은 항목이 다음에 현장에서 볼 일이다."
    )

    st.markdown(
        "".join(
            _chip(
                f"{label} {count}",
                CAUSE_STATUS_COLORS[label],
            )
            for label, count in (
                (STATUS_CONFIRMED, len(report.confirmed_causes)),
                (STATUS_UNVERIFIED, len(report.unverified_causes)),
                (
                    STATUS_EXCLUDED,
                    sum(
                        1
                        for cause in report.d4_causes
                        if cause.status == STATUS_EXCLUDED
                    ),
                ),
            )
        ),
        unsafe_allow_html=True,
    )

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "분류": cause.category,
                    "원인 후보": cause.description,
                    "상태": cause.status,
                    "판단 근거": cause.basis,
                }
                for cause in report.d4_causes
            ]
        ),
        width="stretch",
        hide_index=True,
    )


def _render_deviation_chart(machine: str) -> None:
    """설비 파라미터가 규격 중심에서 얼마나 벗어났는지.

    절대값이 아니라 공차 대비 비율로 그린다. 단위가 다른 파라미터를
    한 그림에 놓고 비교하려면 이 방법밖에 없다. 온도 1도와
    압력 1kgf/cm² 는 크기를 비교할 수 있는 양이 아니다.
    """
    gaps = machine_parameter_gaps(get_report_directory(), machine)

    if not gaps:
        return

    # 공차 정보가 없는 파라미터는 비율이 0 이 되므로 제외한다.
    gaps = [gap for gap in gaps if gap.half_tolerance > 0][:6]

    if not gaps:
        return

    st.markdown("**규격 중심 대비 평균 이탈**")
    st.caption(
        "단위가 다른 파라미터를 비교하려면 공차 대비 비율로 봐야 한다. "
        f"한쪽 공차의 {TOLERANCE_CRITICAL:.0%} 를 평균 이동만으로 "
        "소모하면 산포가 그대로여도 Cpk 가 눈에 띄게 떨어진다."
    )

    labels = [gap.parameter for gap in gaps][::-1]
    values = [gap.tolerance_fraction * 100 for gap in gaps][::-1]

    colors = []

    for value in values:
        magnitude = abs(value) / 100

        if magnitude >= TOLERANCE_CRITICAL:
            colors.append(STATUS_CRITICAL)
        elif magnitude >= TOLERANCE_WARNING:
            colors.append(STATUS_WARNING)
        else:
            colors.append(STATUS_GOOD)

    figure, axes = create_figure(width=10.0, height=0.55 * len(gaps) + 1.6)
    positions = np.arange(len(labels))

    axes.barh(positions, values, color=colors, height=0.58)
    axes.axvline(0, color=AXIS_LINE, linewidth=1.0)

    for boundary in (-TOLERANCE_CRITICAL, TOLERANCE_CRITICAL):
        axes.axvline(
            boundary * 100,
            color=STATUS_CRITICAL,
            linewidth=0.9,
            linestyle="--",
            alpha=0.55,
        )

    for position, value in zip(positions, values):
        offset = 1.4 if value >= 0 else -1.4
        axes.text(
            value + offset,
            position,
            f"{value:+.1f}%",
            va="center",
            ha="left" if value >= 0 else "right",
            fontsize=8,
            color=INK_SECONDARY,
        )

    axes.set_yticks(positions)
    axes.set_yticklabels(labels)
    axes.set_xlabel("한쪽 공차 대비 평균 이탈 [%]")
    axes.set_title(f"{machine} 파라미터별 중심 이탈")

    span = max(abs(min(values)), abs(max(values)), 25.0) * 1.35
    axes.set_xlim(-span, span)
    axes.grid(axis="y", visible=False)

    st.pyplot(figure, width="stretch")


# =====================================================================
# D6 효과 확인
# =====================================================================


def _render_verification(
    report: EightDReport,
    dataframe: pd.DataFrame | None,
) -> None:
    if not report.d6_targets:
        st.info("확인 지표가 없습니다.")
        return

    st.caption(
        "기준선과 목표를 조치 전에 고정한다. 조치 후에 목표를 정하면 "
        "달성했다는 결론이 먼저 나온다. 현재 값은 매번 원본 데이터에서 "
        "다시 계산하므로, 시정조치를 실행하지 않은 지금은 기준선과 "
        "같게 나오는 것이 정상이다."
    )

    table = build_verification_table(report, dataframe)
    st.dataframe(table, width="stretch", hide_index=True)

    numeric = table[table["현재"] != "-"]

    if numeric.empty:
        return

    figure, axes = create_figure(
        width=10.0, height=0.7 * len(numeric) + 1.6
    )
    positions = np.arange(len(numeric))[::-1]

    for position, (_, row) in zip(positions, numeric.iterrows()):
        baseline = float(row["기준선"])
        target = float(row["목표"])
        current = float(row["현재"])

        axes.plot(
            [min(baseline, target), max(baseline, target)],
            [position, position],
            color=AXIS_LINE,
            linewidth=6,
            solid_capstyle="round",
            zorder=1,
        )
        axes.scatter(
            [baseline],
            [position],
            color=INK_MUTED,
            s=70,
            zorder=3,
            label="기준선" if position == positions[0] else None,
        )
        axes.scatter(
            [target],
            [position],
            color=STATUS_GOOD,
            marker="D",
            s=70,
            zorder=3,
            label="목표" if position == positions[0] else None,
        )
        axes.scatter(
            [current],
            [position],
            color=SERIES_BLUE,
            marker="|",
            s=420,
            linewidths=3,
            zorder=4,
            label="현재" if position == positions[0] else None,
        )

    axes.set_yticks(positions)
    axes.set_yticklabels(list(numeric["확인 지표"]))
    axes.set_xlabel("값")
    axes.set_title("기준선 → 목표 대비 현재 위치")
    axes.legend(loc="lower right", ncols=3)
    axes.grid(axis="y", visible=False)

    st.pyplot(figure, width="stretch")


# =====================================================================
# 본문
# =====================================================================


def _render_report(
    report: EightDReport,
    dataframe: pd.DataFrame | None,
) -> None:
    header_left, header_right = st.columns([3, 1])

    with header_left:
        st.subheader(report.title)
        st.caption(
            f"{report.case_id} · 개시 "
            f"{report.opened_on.isoformat()} · 심각도 "
            f"{report.severity}"
        )

    with header_right:
        st.download_button(
            "마크다운 내려받기",
            data=render_markdown(report).encode("utf-8"),
            file_name=f"{report.case_id}.md",
            mime="text/markdown",
            width="stretch",
        )

    _render_progress(report)
    st.divider()

    st.markdown("#### D0 · 준비 및 긴급 대응")
    _render_actions(report.d0_emergency)

    st.markdown("#### D1 · 팀 구성")
    st.caption(
        "역할로 먼저 잡고 이름은 착수할 때 붙인다. "
        "가상의 인명을 채워 넣으면 문서가 가짜가 된다."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "역할": member.role,
                    "책임": member.responsibility,
                    "주 담당 단계": member.discipline_focus,
                }
                for member in report.d1_team
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    st.markdown("#### D2 · 문제 기술")
    _render_problem(report)

    st.markdown("#### D3 · 임시 봉쇄조치")
    st.caption(
        "원인을 모르는 동안 불량이 고객에게 나가지 않게 막는 단계다. "
        "영구 조치가 아니므로 D5 가 확정되면 해제한다. "
        "박리 예측 모델은 여기서 선별 대상을 고르는 데 쓰인다."
    )
    _render_actions(report.d3_containment)

    st.markdown("#### D4 · 근본원인 분석 및 검증")
    st.caption(
        "발생원인과 유출원인을 나누어 본다. 발생원인만 없애면 "
        "다음 불량도 같은 경로로 빠져나간다."
    )

    occurrence, escape = st.columns(2)

    with occurrence:
        _render_why_chain(
            report.d4_occurrence_whys, "발생원인 — 왜 생겼는가"
        )

    with escape:
        _render_why_chain(
            report.d4_escape_whys, "유출원인 — 왜 못 걸렀는가"
        )

    st.markdown("")
    _render_cause_table(report)

    if report.machine:
        st.markdown("")
        _render_deviation_chart(report.machine)

    st.markdown("#### D5 · 영구 시정조치 선정")
    _render_actions(report.d5_corrective)

    st.markdown("#### D6 · 시정조치 실행 및 효과 확인")
    _render_verification(report, dataframe)

    st.markdown("#### D7 · 재발 방지")
    st.caption(
        "같은 문제가 다른 라인에 있는지 보는 수평 전개와, "
        "표준·FMEA 에 반영해 구조를 바꾸는 일이 여기 들어간다."
    )
    _render_actions(report.d7_prevention)

    st.markdown("#### D8 · 종결 및 팀 인정")
    st.info(
        report.d8_closure
        or "D6 효과 확인이 끝난 뒤 작성한다. 지금은 종결 전 단계다."
    )

    if report.open_questions:
        st.markdown("#### 미해결 항목")
        st.caption(
            "현재 데이터만으로는 답할 수 없어 현장 확인이 필요한 "
            "항목이다. 비워두는 편이 채워 넣는 것보다 정확하다."
        )

        for question in report.open_questions:
            st.markdown(f"- {question}")


def show_eight_d(dataframe: pd.DataFrame | None = None) -> None:
    """8D 탭을 렌더링한다."""
    st.markdown("### 8D 문제해결 리포트")
    st.caption(
        "관리도와 분산분석이 찾아낸 이상을 조치로 잇는 단계다. "
        "D2 의 숫자와 D4 의 원인 후보는 앞 탭의 분석 결과에서 "
        "그대로 가져오므로, 모든 문장에 출처가 붙는다."
    )

    missing = missing_reports()

    if missing:
        st.warning(
            "품질 분석 결과가 없습니다. 아래 명령을 먼저 실행하세요.\n\n"
            "`python -m src.quality.run_quality_analysis`\n\n"
            "없는 파일: " + ", ".join(missing)
        )
        return

    try:
        reports = load_cases()
    except (FileNotFoundError, ValueError) as error:
        st.warning(f"8D 사례를 만들 수 없습니다. {error}")
        return

    if not reports:
        st.success(
            "8D 를 열 기준에 해당하는 사례가 없습니다. "
            "불량률이 전체 평균의 1.5배를 넘는 설비도, "
            "관리도 CRITICAL 신호도 없습니다."
        )
        return

    with st.expander("사례 선정 기준", expanded=False):
        st.caption(
            "어디에 8D 를 열지 사람이 고르지 않는다. 눈에 띄는 설비나 "
            "최근 클레임이 있었던 설비가 먼저 선택되는 편향을 막기 "
            "위해서다. 아래 두 기준을 코드로 고정했다."
        )
        st.markdown(
            "1. 불량률이 전체 평균의 **1.5배 이상**인 설비\n"
            "2. Nelson 판정에서 **CRITICAL** 신호가 잡힌 파라미터 "
            "— 불량이 아직 터지지 않은 사례이고, 그쪽이 더 싸게 끝난다"
        )

        ranked = rank_defect_cases()

        if not ranked.empty:
            st.dataframe(
                ranked[
                    [
                        "Machine",
                        "lot_count",
                        "defect_rate_percent",
                        "ratio_to_overall",
                        "escalate",
                    ]
                ].rename(
                    columns={
                        "Machine": "설비",
                        "lot_count": "LOT 수",
                        "defect_rate_percent": "불량률 [%]",
                        "ratio_to_overall": "전체 대비 배수",
                        "escalate": "8D 대상",
                    }
                ),
                width="stretch",
                hide_index=True,
            )

    labels = {report.title: report for report in reports}
    choice = st.selectbox(
        "사례",
        list(labels),
        help=f"기준을 넘은 사례 {len(reports)}건",
    )

    st.divider()
    _render_report(labels[choice], dataframe)
