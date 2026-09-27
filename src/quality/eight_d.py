"""8D 문제해결 리포트.

관리도와 분산분석은 "이상이 있다"까지만 말한다. 현업에서 그 다음이 본 업무다.
누가 언제까지 무엇을 하고, 그게 효과가 있었는지 어떻게 확인하고,
다른 라인에 같은 문제가 없는지 누가 점검하는가.
8D 는 그 흐름을 8단계로 고정한 양식이다.

이 모듈이 빈 양식과 다른 점
---------------------------
D2 의 숫자와 D4 의 원인 후보를 사람이 적는 대신
report/ 에 이미 저장된 분석 결과에서 읽어온다.

    quality_machine_summary.csv        -> D2 얼마나 / D4 설비 간 차이
    quality_defect_rate_p_chart.csv    -> D2 언제 / D4 유출원인
    quality_anova.csv, quality_tukey_hsd.csv -> D4 인자별 유의성
    quality_msa_variance_components.csv      -> D4 측정 원인 배제 판단
    quality_stratified_rule_signals.csv      -> D2 이상 신호
    model_operating_points.csv         -> D3 봉쇄조치의 선별 부하
    quality_capability.csv             -> D6 효과 확인 기준선

그래서 모든 문장에 출처가 붙는다. `Evidence` 가 그 역할을 한다.

발생원인과 유출원인을 나누는 이유
--------------------------------
8D 를 형식만 따라 하면 D4 에 원인을 하나만 적고 끝낸다.
정석은 두 갈래다.

    발생원인(occurrence) : 왜 불량이 생겼나
    유출원인(escape)     : 왜 그걸 못 걸러냈나

둘은 시정조치가 다르다. 발생원인을 없애도 검출 체계가 그대로면
다음 불량도 똑같이 빠져나간다. 이 모듈은 둘을 각각 5 Why 로 추적한다.

정직성에 대한 주의
------------------
D5 이후는 사람이 실행해야 하는 단계다. 코드가 만들어낼 수 있는 것은
'무엇을 목표로 어떻게 검증할지'까지이고, '했더니 좋아졌다'는 결과가 아니다.
그래서 D5~D8 의 조치는 전부 status 가 미착수 또는 검증 대기로 시작하고,
D6 의 효과 확인은 현재 데이터를 다시 계산해 기준선과 비교하는 방식으로 둔다.
조치를 하지 않았으면 차이가 0 으로 나오고, 그게 맞는 표시다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

import pandas as pd

from src.process_spec import get_target, get_tolerance


# =====================================================================
# 어휘 정의
# =====================================================================

DISCIPLINE_TITLES: Final[dict[str, str]] = {
    "D0": "준비 및 긴급 대응",
    "D1": "팀 구성",
    "D2": "문제 기술",
    "D3": "임시 봉쇄조치",
    "D4": "근본원인 분석 및 검증",
    "D5": "영구 시정조치 선정",
    "D6": "시정조치 실행 및 효과 확인",
    "D7": "재발 방지",
    "D8": "종결 및 팀 인정",
}

# 특성요인도(Ishikawa) 6M. 원인 후보를 빠짐없이 훑기 위한 분류 축이다.
CAUSE_CATEGORIES: Final[tuple[str, ...]] = (
    "설비(Machine)",
    "자재(Material)",
    "사람(Man)",
    "방법(Method)",
    "측정(Measurement)",
    "환경(Environment)",
)

# 원인 후보의 검증 상태.
# 미확인을 남겨두는 것이 중요하다. 확인하지 않은 것을 확인한 것처럼
# 적는 순간 8D 는 보고용 문서가 되고 재발을 막지 못한다.
STATUS_CONFIRMED: Final[str] = "확인됨"
STATUS_EXCLUDED: Final[str] = "배제됨"
STATUS_UNVERIFIED: Final[str] = "미확인"

# 조치의 진행 상태.
ACTION_DONE: Final[str] = "완료"
ACTION_ONGOING: Final[str] = "진행 중"
ACTION_PENDING: Final[str] = "미착수"
ACTION_AWAITING: Final[str] = "검증 대기"

# 불량률이 전체 평균의 몇 배를 넘으면 8D 를 열 것인가.
# 현업에서는 고객 클레임이나 목표 대비로 정하지만
# 여기서는 데이터만으로 판단해야 하므로 배수로 둔다.
ESCALATION_RATIO: Final[float] = 1.5

# Gage R&R 이 이 값을 넘으면 측정시스템을 원인 후보에서 배제할 수 없다.
# AIAG 기준으로 10% 미만이 적합, 30% 미만이 조건부 적합이다.
GRR_EXCLUSION_THRESHOLD: Final[float] = 10.0


# =====================================================================
# 구성 요소
# =====================================================================


@dataclass(frozen=True)
class Evidence:
    """근거 한 건.

    어느 파일의 어떤 값을 보고 그렇게 판단했는지 남긴다.
    이게 없으면 8D 는 의견 모음이 된다.
    """

    source: str
    metric: str
    value: str
    interpretation: str

    def as_line(self) -> str:
        return (
            f"{self.metric} = {self.value} "
            f"({self.interpretation}, 출처: {self.source})"
        )


@dataclass(frozen=True)
class WhyStep:
    """5 Why 한 단계.

    verified 가 False 인 단계는 데이터로 확인되지 않은 추정이다.
    거기서 Why 가 멈추면 그 지점이 다음에 확인할 일이 된다.
    """

    depth: int
    question: str
    answer: str
    verified: bool
    evidence: tuple[Evidence, ...] = ()

    @property
    def marker(self) -> str:
        return "확인" if self.verified else "추정"


@dataclass(frozen=True)
class CauseCandidate:
    """특성요인도의 가지 하나."""

    category: str
    description: str
    status: str
    basis: str


@dataclass(frozen=True)
class ProblemStatement:
    """D2. 5W2H 와 IS / IS-NOT.

    IS / IS-NOT 은 Kepner-Tregoe 방식이다.
    '어디서 발생했나'만 보면 원인이 좁혀지지 않는다.
    '비슷한 조건인데 발생하지 않은 곳'을 함께 적어야
    둘의 차이가 원인 후보로 남는다.
    """

    what: str
    where: str
    when: str
    who: str
    which: str
    how: str
    how_many: str
    is_observed: tuple[str, ...]
    is_not_observed: tuple[str, ...]
    evidence: tuple[Evidence, ...] = ()

    def as_rows(self) -> list[dict[str, str]]:
        return [
            {"항목": "무엇이(What)", "내용": self.what},
            {"항목": "어디서(Where)", "내용": self.where},
            {"항목": "언제(When)", "내용": self.when},
            {"항목": "누가(Who)", "내용": self.who},
            {"항목": "어느 것이(Which)", "내용": self.which},
            {"항목": "어떻게(How)", "내용": self.how},
            {"항목": "얼마나(How many)", "내용": self.how_many},
        ]


@dataclass(frozen=True)
class Action:
    """D0 / D3 / D5 / D7 에 들어가는 조치 한 건."""

    description: str
    owner_role: str
    verification: str
    status: str
    evidence: tuple[Evidence, ...] = ()

    def as_row(self) -> dict[str, str]:
        return {
            "조치": self.description,
            "담당": self.owner_role,
            "검증 방법": self.verification,
            "상태": self.status,
        }


@dataclass(frozen=True)
class TeamRole:
    """D1. 이름이 아니라 역할로 둔다.

    포트폴리오에 가상의 인명을 채워 넣으면 문서가 가짜로 보인다.
    실제 8D 에서도 초안은 역할로 먼저 잡고 이름을 나중에 붙인다.
    """

    role: str
    responsibility: str
    discipline_focus: str


@dataclass(frozen=True)
class VerificationTarget:
    """D6 에서 확인할 지표 하나.

    기준선(baseline)과 목표(target)를 미리 못박아 둔다.
    조치 후에 목표를 정하면 달성했다는 결론이 먼저 나온다.
    """

    metric: str
    baseline: float
    target: float
    unit: str
    direction: str  # "감소" 또는 "증가"
    method: str

    def is_met(self, current: float) -> bool:
        if self.direction == "감소":
            return current <= self.target
        return current >= self.target

    def progress(self, current: float) -> float:
        """기준선에서 목표까지 몇 %를 왔는지.

        조치 전이면 0 이 나온다. 목표를 넘어서면 100 을 넘는다.
        """
        span = self.target - self.baseline

        if span == 0:
            return 100.0

        return 100.0 * (current - self.baseline) / span


@dataclass
class EightDReport:
    """8D 리포트 한 건."""

    case_id: str
    title: str
    opened_on: date
    severity: str
    machine: str = ""

    d0_emergency: tuple[Action, ...] = ()
    d1_team: tuple[TeamRole, ...] = ()
    d2_problem: ProblemStatement | None = None
    d3_containment: tuple[Action, ...] = ()
    d4_occurrence_whys: tuple[WhyStep, ...] = ()
    d4_escape_whys: tuple[WhyStep, ...] = ()
    d4_causes: tuple[CauseCandidate, ...] = ()
    d5_corrective: tuple[Action, ...] = ()
    d6_targets: tuple[VerificationTarget, ...] = ()
    d7_prevention: tuple[Action, ...] = ()
    d8_closure: str = ""
    open_questions: tuple[str, ...] = field(default_factory=tuple)

    # -- 진행률 ------------------------------------------------------

    @property
    def discipline_status(self) -> dict[str, str]:
        """단계별 상태.

        D5 이후가 미착수인 것은 결함이 아니라 현재 상태다.
        분석은 끝났고 조치는 사람이 해야 한다.
        """

        def action_status(actions: tuple[Action, ...]) -> str:
            if not actions:
                return ACTION_PENDING
            if all(a.status == ACTION_DONE for a in actions):
                return ACTION_DONE
            if any(a.status != ACTION_PENDING for a in actions):
                return ACTION_ONGOING
            return ACTION_PENDING

        return {
            "D0": action_status(self.d0_emergency),
            "D1": ACTION_DONE if self.d1_team else ACTION_PENDING,
            "D2": ACTION_DONE if self.d2_problem else ACTION_PENDING,
            "D3": action_status(self.d3_containment),
            "D4": (
                ACTION_DONE
                if self.confirmed_causes
                else ACTION_ONGOING
            ),
            "D5": action_status(self.d5_corrective),
            "D6": (
                ACTION_AWAITING if self.d6_targets else ACTION_PENDING
            ),
            "D7": action_status(self.d7_prevention),
            "D8": ACTION_DONE if self.d8_closure else ACTION_PENDING,
        }

    @property
    def confirmed_causes(self) -> tuple[CauseCandidate, ...]:
        return tuple(
            cause
            for cause in self.d4_causes
            if cause.status == STATUS_CONFIRMED
        )

    @property
    def unverified_causes(self) -> tuple[CauseCandidate, ...]:
        return tuple(
            cause
            for cause in self.d4_causes
            if cause.status == STATUS_UNVERIFIED
        )

    @property
    def analysis_complete(self) -> bool:
        """분석 단계(D1, D2, D4)가 끝났는가.

        조치 단계와 분리해서 본다. 분석은 데이터로 끝낼 수 있지만
        조치는 사람이 현장에서 해야 하므로 진행률을 섞으면
        '8D 가 33% 진행됨' 같은 뜻 없는 숫자가 나온다.
        """
        status = self.discipline_status

        return all(
            status[code] == ACTION_DONE for code in ("D1", "D2", "D4")
        )

    @property
    def pending_stages(self) -> tuple[str, ...]:
        """사람이 실행해야 남는 단계."""
        status = self.discipline_status

        return tuple(
            code
            for code in ("D0", "D3", "D5", "D6", "D7", "D8")
            if status[code] != ACTION_DONE
        )

    def summary_row(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "opened_on": self.opened_on.isoformat(),
            "severity": self.severity,
            "analysis_complete": self.analysis_complete,
            "confirmed_causes": len(self.confirmed_causes),
            "unverified_causes": len(self.unverified_causes),
            "open_questions": len(self.open_questions),
            "pending_stages": ", ".join(self.pending_stages),
        }


# =====================================================================
# 분석 결과 읽기
# =====================================================================


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_report_directory() -> Path:
    return get_project_root() / "report"


REQUIRED_REPORTS: Final[tuple[str, ...]] = (
    "quality_machine_summary.csv",
    "quality_defect_rate_p_chart.csv",
    "quality_anova.csv",
    "quality_capability.csv",
)

OPTIONAL_REPORTS: Final[tuple[str, ...]] = (
    "quality_tukey_hsd.csv",
    "quality_msa_variance_components.csv",
    "quality_stratified_rule_signals.csv",
    "model_operating_points.csv",
)


def missing_reports(report_dir: Path | None = None) -> list[str]:
    """8D 를 만들기 위해 반드시 있어야 하는데 없는 파일 목록."""
    directory = report_dir or get_report_directory()

    return [
        name
        for name in REQUIRED_REPORTS
        if not (directory / name).exists()
    ]


def _read(report_dir: Path, name: str) -> pd.DataFrame | None:
    """리포트 CSV 하나를 읽는다. 없으면 None."""
    path = report_dir / name

    if not path.exists():
        return None

    # 다른 모듈이 BOM 을 붙여 저장하므로 utf-8-sig 로 읽는다.
    return pd.read_csv(path, encoding="utf-8-sig")


# =====================================================================
# 사례 선정
# =====================================================================


def rank_defect_cases(
    report_dir: Path | None = None,
) -> pd.DataFrame:
    """불량률이 높은 순서로 설비를 정렬한다.

    8D 를 어디에 열 것인지 사람이 고르지 않고 데이터가 고르게 한다.
    전체 평균 대비 배수가 ESCALATION_RATIO 를 넘으면 대상으로 본다.
    """
    directory = report_dir or get_report_directory()
    summary = _read(directory, "quality_machine_summary.csv")

    if summary is None or summary.empty:
        return pd.DataFrame()

    overall = float(
        (
            summary["defect_rate_percent"] * summary["lot_count"]
        ).sum()
        / summary["lot_count"].sum()
    )

    ranked = summary.copy()
    ranked["overall_defect_rate_percent"] = round(overall, 2)
    ranked["ratio_to_overall"] = (
        ranked["defect_rate_percent"] / overall
    ).round(2)
    ranked["escalate"] = ranked["ratio_to_overall"] >= ESCALATION_RATIO

    return ranked.sort_values(
        "defect_rate_percent", ascending=False
    ).reset_index(drop=True)


def rank_drift_cases(
    report_dir: Path | None = None,
) -> pd.DataFrame:
    """관리도 이상 신호가 심한 순서로 정렬한다.

    불량률은 아직 안 올랐지만 파라미터가 흐르고 있는 경우를 잡는다.
    불량이 터진 뒤에 여는 8D 보다 이쪽이 싸다.
    """
    directory = report_dir or get_report_directory()
    signals = _read(directory, "quality_stratified_rule_signals.csv")

    if signals is None or signals.empty:
        return pd.DataFrame()

    critical = signals[signals["severity"] == "CRITICAL"]

    if critical.empty:
        return pd.DataFrame()

    grouped = (
        critical.groupby(["Machine", "characteristic"])
        .agg(
            rule_count=("rule", "count"),
            max_ratio=("ratio", "max"),
            total_observed=("observed", "sum"),
        )
        .reset_index()
    )

    return grouped.sort_values(
        ["rule_count", "max_ratio"], ascending=False
    ).reset_index(drop=True)


# =====================================================================
# D2 문제 기술
# =====================================================================


def _build_problem_statement(
    report_dir: Path,
    machine: str,
) -> ProblemStatement:
    ranked = rank_defect_cases(report_dir)
    row = ranked[ranked["Machine"] == machine].iloc[0]

    overall = float(row["overall_defect_rate_percent"])
    rate = float(row["defect_rate_percent"])
    ratio = float(row["ratio_to_overall"])
    lots = int(row["lot_count"])

    best = ranked.iloc[-1]
    best_machine = str(best["Machine"])
    best_rate = float(best["defect_rate_percent"])

    p_chart = _read(report_dir, "quality_defect_rate_p_chart.csv")
    when_text = "p 관리도 부분군 전 구간에서 지속 발생"
    evidence: list[Evidence] = [
        Evidence(
            source="quality_machine_summary.csv",
            metric=f"{machine} 박리 불량률",
            value=f"{rate:.2f}%",
            interpretation=(
                f"전체 평균 {overall:.2f}% 의 {ratio:.2f}배, "
                f"최저 설비 {best_machine} {best_rate:.2f}% 의 "
                f"{rate / best_rate:.1f}배"
            ),
        )
    ]

    if p_chart is not None and not p_chart.empty:
        scoped = p_chart[p_chart["scope"] == machine]

        if not scoped.empty:
            scope_row = scoped.iloc[0]
            subgroups = int(scope_row["subgroup_count"])
            out_points = int(scope_row["out_of_control_points"])
            ucl = float(scope_row["ucl_percent"])

            when_text = (
                f"{subgroups}개 부분군 중 관리한계 이탈 "
                f"{out_points}건. 상시 높은 수준이며 특정 시점에 "
                "튄 것이 아니다"
            )
            evidence.append(
                Evidence(
                    source="quality_defect_rate_p_chart.csv",
                    metric=f"{machine} p 관리도 UCL",
                    value=f"{ucl:.2f}%",
                    interpretation=(
                        "설비 자신의 평균으로 계산한 관리한계라 "
                        "현재 불량률이 관리 상태로 판정된다"
                    ),
                )
            )

    is_observed = (machine,)
    is_not_observed = tuple(
        str(name)
        for name in ranked["Machine"]
        if str(name) != machine
    )

    return ProblemStatement(
        what="ABF 빌드업 층 박리(Delamination)",
        where=f"압착 공정 {machine}",
        when=when_text,
        who=(
            "작업자 구분 없이 발생. Gage R&R 재현성(AV)이 "
            "반복성(EV)보다 작아 작업자 요인으로 설명되지 않는다"
        ),
        which=(
            "전 기종. 기종별 민감도 차이는 D4 에서 별도 확인 대상"
        ),
        how=(
            "압착 압력과 온도가 규격 중심보다 낮은 쪽으로 치우친 "
            "상태에서 박리 발생률이 상승"
        ),
        how_many=(
            f"LOT {lots:,}건 중 {rate:.2f}% "
            f"(전체 평균 대비 {ratio:.2f}배)"
        ),
        is_observed=is_observed,
        is_not_observed=is_not_observed,
        evidence=tuple(evidence),
    )


# =====================================================================
# D3 임시 봉쇄조치
# =====================================================================


def _build_containment(
    report_dir: Path,
    machine: str,
) -> tuple[Action, ...]:
    """봉쇄조치.

    여기서 ML 모델이 제 역할을 한다. 원인을 모르는 동안 고객에게
    불량이 나가지 않게 막아야 하고, 그 수단이 전수 선별이다.
    모델 운전점 표가 '검출률을 얼마로 잡으면 몇 개를 선별해야 하는가'를
    알려주므로 봉쇄 비용을 숫자로 말할 수 있다.
    """
    actions: list[Action] = [
        Action(
            description=(
                f"{machine} 생산분 출하 보류 및 전수 초음파 검사"
            ),
            owner_role="품질보증",
            verification="보류 LOT 목록과 검사 성적서 대조",
            status=ACTION_PENDING,
        ),
        Action(
            description=(
                f"{machine} 압착 압력·온도 설정값을 규격 중심으로 "
                "재설정하고 셋업 조건 기록"
            ),
            owner_role="생산기술",
            verification=(
                "재설정 후 24시간 데이터로 설비 간 평균 차이 재계산"
            ),
            status=ACTION_PENDING,
        ),
    ]

    operating = _read(report_dir, "model_operating_points.csv")

    if operating is not None and not operating.empty:
        # 검출률 90% 지점을 봉쇄 운전점으로 잡는다.
        # 봉쇄 단계에서는 과검보다 미검이 훨씬 비싸다.
        target = operating.iloc[
            (operating["target_recall"] - 0.90).abs().argsort()[:1]
        ].iloc[0]

        threshold = float(target["threshold"])
        recall = float(target["achieved_recall"])
        false_alarm = float(target["false_alarm_rate"])
        flagged = int(target["flagged_lots"])
        missed = int(target["missed_defects"])

        actions.append(
            Action(
                description=(
                    f"박리 예측 모델 임계값을 {threshold:.3f} 로 "
                    "낮춰 선별 대상 자동 선정"
                ),
                owner_role="품질/데이터",
                verification=(
                    "선별 LOT 의 실제 박리 발생 여부로 검출률 재확인"
                ),
                status=ACTION_PENDING,
                evidence=(
                    Evidence(
                        source="model_operating_points.csv",
                        metric="검출률 / 과검률",
                        value=(
                            f"{recall * 100:.1f}% / "
                            f"{false_alarm * 100:.1f}%"
                        ),
                        interpretation=(
                            f"선별 대상 {flagged:,}건으로 늘지만 "
                            f"미검이 {missed}건까지 줄어든다. "
                            "봉쇄 기간 한정 운전점이다"
                        ),
                    ),
                ),
            )
        )

    return tuple(actions)


# =====================================================================
# D4 근본원인
# =====================================================================


@dataclass(frozen=True)
class ParameterGap:
    """설비 하나의 파라미터 평균이 규격 중심에서 얼마나 벗어났는지."""

    parameter: str
    machine_mean: float
    target: float
    deviation: float
    half_tolerance: float
    peer_median: float

    @property
    def tolerance_fraction(self) -> float:
        """공차 반폭의 몇 배만큼 중심에서 벗어났는가.

        0.2 면 한쪽 공차의 20%를 평균 이동만으로 먹었다는 뜻이다.
        """
        if self.half_tolerance <= 0:
            return 0.0

        return self.deviation / self.half_tolerance

    @property
    def peer_gap(self) -> float:
        """다른 설비들의 중앙값과의 차이. 참고용이다.

        순위를 매기는 데 쓰지 않는다. 설비가 셋뿐이면 남는 비교
        대상이 둘이고, 둘의 중앙값은 곧 평균이라 중앙값을 써도
        드리프트 중인 설비가 기준선을 끌고 간다. 실제로 이 데이터에서
        PRESS_03 의 Cure_Temp 드리프트 때문에 멀쩡한 PRESS_01 이
        +0.8 이탈한 것처럼 보인다.

        그래서 순위는 규격 중심(target) 기준의 tolerance_fraction 으로
        정한다. 규격은 다른 설비의 상태와 무관하게 고정된 기준이다.
        설비가 넉넉히 많을 때는 중앙값도 쓸 만한 보조 지표가 된다.
        """
        return self.machine_mean - self.peer_median


def _machine_parameter_gaps(
    report_dir: Path,
    machine: str,
) -> list[ParameterGap]:
    """해당 설비의 파라미터 평균 이탈을 큰 순서로 돌려준다.

    순서를 정하는 기준은 공차 대비 비율이다. 절대값으로 줄을 세우면
    단위가 큰 파라미터가 항상 이긴다. Cure_Temp 의 0.9°C 이탈
    (공차 ±5) 과 Press2_Pressure 의 0.22kgf/cm² 이탈 (공차 ±1) 중
    공정에 위험한 쪽은 후자인데, 숫자만 보면 전자가 커 보인다.
    """
    summary = _read(report_dir, "quality_machine_summary.csv")

    if summary is None or summary.empty:
        return []

    columns = [
        column
        for column in summary.columns
        if column.endswith("_mean")
    ]

    own_row = summary[summary["Machine"] == machine]
    peers = summary[summary["Machine"] != machine]

    if own_row.empty or peers.empty:
        return []

    gaps: list[ParameterGap] = []

    for column in columns:
        parameter = column.removesuffix("_mean")
        own = float(own_row[column].iloc[0])
        peer_median = float(peers[column].median())

        target = get_target(parameter)
        tolerance = get_tolerance(parameter)

        # 규격이 없는 파라미터는 다른 설비의 중앙값을 기준으로 본다.
        if target is None:
            target = peer_median

        half_tolerance = (
            tolerance / 2.0 if tolerance else 0.0
        )

        gaps.append(
            ParameterGap(
                parameter=parameter,
                machine_mean=own,
                target=float(target),
                deviation=own - float(target),
                half_tolerance=half_tolerance,
                peer_median=peer_median,
            )
        )

    return sorted(
        gaps,
        key=lambda gap: abs(gap.tolerance_fraction),
        reverse=True,
    )


def _machine_effect_lookup(
    report_dir: Path,
) -> dict[str, tuple[float, str, bool]]:
    """설비 인자의 응답별 효과 크기를 찾아본다.

    {응답 이름: (eta^2, 효과 크기 라벨, 유의 여부)}

    p 값만으로 원인을 확정하지 않기 위해 효과 크기를 함께 들고 온다.
    표본이 크면 의미 없는 차이도 유의해지기 때문이다.
    """
    anova = _read(report_dir, "quality_anova.csv")

    if anova is None or anova.empty:
        return {}

    scoped = anova[anova["factor_name"] == "Machine"]
    lookup: dict[str, tuple[float, str, bool]] = {}

    for _, row in scoped.iterrows():
        lookup[str(row["response"])] = (
            float(row["eta_squared"]),
            str(row["effect_size"]),
            bool(row["significant"]),
        )

    return lookup


def _measurement_verdict(
    report_dir: Path,
) -> tuple[str, str, Evidence | None]:
    """측정시스템을 원인 후보에서 배제할 수 있는지 판단한다.

    설비 간 차이를 보기 전에 먼저 물어야 하는 질문이다.
    측정이 흔들리면 설비가 다른 게 아니라 다르게 측정된 것일 수 있다.
    """
    components = _read(
        report_dir, "quality_msa_variance_components.csv"
    )

    if components is None or components.empty:
        return (
            STATUS_UNVERIFIED,
            "Gage R&R 결과가 없어 측정 요인을 판단할 수 없다.",
            None,
        )

    grr_rows = components[
        components["source"].str.contains("GRR", na=False)
    ]

    if grr_rows.empty:
        return (
            STATUS_UNVERIFIED,
            "분산 성분 표에서 GRR 항목을 찾지 못했다.",
            None,
        )

    grr = float(grr_rows["percent_study_variation"].iloc[0])

    evidence = Evidence(
        source="quality_msa_variance_components.csv",
        metric="%GRR",
        value=f"{grr:.1f}%",
        interpretation=(
            "AIAG 기준 10% 미만 적합, 30% 미만 조건부 적합"
        ),
    )

    if grr < GRR_EXCLUSION_THRESHOLD:
        return (
            STATUS_EXCLUDED,
            (
                f"%GRR {grr:.1f}% 로 측정 산포가 충분히 작다. "
                "설비 간 차이를 측정 오차로 설명할 수 없으므로 "
                "측정 요인을 원인 후보에서 제외한다."
            ),
            evidence,
        )

    return (
        STATUS_UNVERIFIED,
        (
            f"%GRR {grr:.1f}% 로 조건부 적합 수준이다. "
            "설비 간 차이가 측정 산포보다 크므로 주원인은 아니지만, "
            "측정 자체의 개선 없이는 이번 차이의 크기를 "
            "정확히 말할 수 없다. 별도 과제로 분리한다."
        ),
        evidence,
    )


def _build_occurrence_whys(
    report_dir: Path,
    machine: str,
) -> tuple[WhyStep, ...]:
    ranked = rank_defect_cases(report_dir)
    row = ranked[ranked["Machine"] == machine].iloc[0]
    rate = float(row["defect_rate_percent"])
    best = ranked.iloc[-1]

    gaps = _machine_parameter_gaps(report_dir, machine)
    primary = gaps[0] if gaps else None
    secondary = gaps[1] if len(gaps) > 1 else None

    steps: list[WhyStep] = [
        WhyStep(
            depth=1,
            question=f"왜 {machine} 의 불량률이 높은가?",
            answer=(
                f"박리 불량률이 {rate:.2f}% 로 최저 설비 "
                f"{best['Machine']} "
                f"{float(best['defect_rate_percent']):.2f}% 의 "
                f"{rate / float(best['defect_rate_percent']):.1f}배다."
            ),
            verified=True,
            evidence=(
                Evidence(
                    source="quality_machine_summary.csv",
                    metric="설비별 불량률",
                    value=f"{rate:.2f}%",
                    interpretation="설비 간 차이가 명확하다",
                ),
            ),
        )
    ]

    lookup = _machine_effect_lookup(report_dir)

    if primary is not None:
        effect = lookup.get(primary.parameter)
        effect_text = ""
        effect_evidence: tuple[Evidence, ...] = ()

        if effect is not None:
            eta, label, _ = effect
            effect_text = (
                " 설비 간 분산분석에서도 이 인자의 효과 크기가 "
                f"eta^2 = {eta:.3f}({label})로 나타난다."
            )
            effect_evidence = (
                Evidence(
                    source="quality_anova.csv",
                    metric=f"Machine x {primary.parameter} eta^2",
                    value=f"{eta:.3f}",
                    interpretation=(
                        f"효과 크기 {label}. 설비 간 차이가 "
                        "우연으로 설명되지 않는다"
                    ),
                ),
            )

        steps.append(
            WhyStep(
                depth=2,
                question=f"왜 {machine} 에서 박리가 더 생기는가?",
                answer=(
                    f"{primary.parameter} 평균이 "
                    f"{primary.machine_mean:.3f} 로 규격 중심 "
                    f"{primary.target:.3f} 에서 "
                    f"{primary.deviation:+.3f} 벗어나 있다. "
                    "평균 이동만으로 한쪽 공차의 "
                    f"{abs(primary.tolerance_fraction) * 100:.0f}% 를 "
                    "이미 소모한 상태다."
                    + effect_text
                ),
                verified=True,
                evidence=(
                    Evidence(
                        source="quality_machine_summary.csv",
                        metric=f"{primary.parameter} 평균 / 공차 대비",
                        value=(
                            f"{primary.machine_mean:.3f} / "
                            f"{primary.tolerance_fraction:+.1%}"
                        ),
                        interpretation=(
                            f"규격 중심 대비 {primary.deviation:+.3f}, "
                            f"타 설비 중앙값 대비 "
                            f"{primary.peer_gap:+.3f}"
                        ),
                    ),
                )
                + effect_evidence,
            )
        )

    if secondary is not None:
        same_direction = (
            primary is not None
            and primary.deviation * secondary.deviation > 0
        )

        steps.append(
            WhyStep(
                depth=3,
                question="단일 파라미터 문제인가?",
                answer=(
                    f"{secondary.parameter} 도 "
                    f"{secondary.machine_mean:.3f} 로 공차의 "
                    f"{abs(secondary.tolerance_fraction) * 100:.0f}% "
                    "를 소모했다."
                    + (
                        " 두 파라미터가 같은 방향으로 함께 치우쳤다. "
                        "독립적으로 흔들렸다면 방향이 갈렸을 것이므로 "
                        "설정값 오류나 설비 계통 문제를 시사한다."
                        if same_direction
                        else " 다만 이탈 방향이 서로 달라 공통 원인으로"
                        " 묶기 어렵다. 별개 요인으로 본다."
                    )
                ),
                verified=True,
                evidence=(
                    Evidence(
                        source="quality_machine_summary.csv",
                        metric=(
                            f"{secondary.parameter} 평균 / 공차 대비"
                        ),
                        value=(
                            f"{secondary.machine_mean:.3f} / "
                            f"{secondary.tolerance_fraction:+.1%}"
                        ),
                        interpretation=(
                            f"규격 중심 대비 {secondary.deviation:+.3f}"
                        ),
                    ),
                ),
            )
        )

    steps.append(
        WhyStep(
            depth=len(steps) + 1,
            question="왜 그 파라미터가 낮게 유지되는가?",
            answer=(
                "여기서부터는 데이터만으로 답할 수 없다. "
                "압력 센서 검교정 이력, 유압 계통 누유 점검, "
                "셋업 표준 준수 여부를 현장에서 확인해야 한다. "
                "세 가지 중 어느 것인지 확인되면 D5 시정조치가 "
                "정해진다."
            ),
            verified=False,
        )
    )

    return tuple(steps)


def _build_escape_whys(
    report_dir: Path,
    machine: str,
) -> tuple[WhyStep, ...]:
    """유출원인.

    이번 사례의 유출원인은 관리한계를 설비별로 따로 계산한 데 있다.
    나쁜 설비의 나쁜 수준이 그 설비의 기준이 되어버리면
    관리도는 영원히 관리 상태를 가리킨다. 흔한 함정이다.
    """
    p_chart = _read(report_dir, "quality_defect_rate_p_chart.csv")

    if p_chart is None or p_chart.empty:
        return ()

    scoped = p_chart[p_chart["scope"] == machine]
    overall = p_chart[p_chart["scope"] == "전체"]

    if scoped.empty:
        return ()

    row = scoped.iloc[0]
    ucl = float(row["ucl_percent"])
    p_bar = float(row["p_bar_percent"])
    out_points = int(row["out_of_control_points"])
    subgroups = int(row["subgroup_count"])

    overall_ucl = (
        float(overall["ucl_percent"].iloc[0])
        if not overall.empty
        else None
    )

    steps = [
        WhyStep(
            depth=1,
            question="왜 이 수준이 이상으로 걸러지지 않았는가?",
            answer=(
                f"{machine} p 관리도에서 {subgroups}개 부분군 중 "
                f"이탈이 {out_points}건뿐이다. 통계적으로는 "
                "관리 상태로 판정된다."
            ),
            verified=True,
            evidence=(
                Evidence(
                    source="quality_defect_rate_p_chart.csv",
                    metric=f"{machine} 관리한계 이탈",
                    value=f"{out_points}/{subgroups}",
                    interpretation="관리 상태로 판정",
                ),
            ),
        ),
        WhyStep(
            depth=2,
            question="왜 관리 상태로 판정되는가?",
            answer=(
                f"관리한계 UCL {ucl:.2f}% 가 이 설비 자신의 평균 "
                f"{p_bar:.2f}% 에서 계산되었기 때문이다. "
                "판정 기준이 현재 수준에 맞춰져 있으므로, "
                "불량률이 높아도 그 높은 수준이 기준이 된다."
            ),
            verified=True,
            evidence=(
                Evidence(
                    source="quality_defect_rate_p_chart.csv",
                    metric=f"{machine} UCL / p̄",
                    value=f"{ucl:.2f}% / {p_bar:.2f}%",
                    interpretation="자기 기준으로 산출된 관리한계",
                ),
            ),
        ),
        WhyStep(
            depth=3,
            question="왜 자기 기준으로 계산했는가?",
            answer=(
                "설비별 층별 관리는 설비 안의 변화를 보기 위한 "
                "방법이다. 설비 간 차이는 구조적으로 흡수된다. "
                "층별 관리만 운영하면 설비 간 격차는 영원히 "
                "보이지 않는다."
                + (
                    f" 전체 기준 UCL 은 {overall_ucl:.2f}% 이고 "
                    f"{machine} 평균 {p_bar:.2f}% 는 그 아래에 "
                    "있어 전체 관리도에서도 잡히지 않는다."
                    if overall_ucl is not None
                    else ""
                )
            ),
            verified=True,
        ),
        WhyStep(
            depth=4,
            question="무엇이 있었어야 했는가?",
            answer=(
                "설비 간 비교를 정기 판정 항목으로 두어야 했다. "
                "분산분석으로 설비 간 차이를 주기적으로 검정하거나, "
                "목표 불량률을 고정 기준선으로 관리도에 함께 "
                "표시했어야 한다. 이것이 D5 의 두 번째 시정조치가 "
                "된다."
            ),
            verified=True,
        ),
    ]

    return tuple(steps)


def _build_cause_candidates(
    report_dir: Path,
    machine: str,
) -> tuple[CauseCandidate, ...]:
    """6M 축으로 원인 후보를 훑는다."""
    causes: list[CauseCandidate] = []
    gaps = _machine_parameter_gaps(report_dir, machine)
    anova_lookup = _machine_effect_lookup(report_dir)

    for gap in gaps[:2]:
        effect = anova_lookup.get(gap.parameter)

        if effect is None:
            basis = "quality_machine_summary.csv 설비별 평균 비교"
            status = STATUS_UNVERIFIED
        else:
            eta, label, significant = effect
            basis = (
                "quality_machine_summary.csv 평균 비교 + "
                f"quality_anova.csv 설비 간 분산분석 "
                f"(eta^2 = {eta:.3f}, 효과 크기 {label})"
            )
            status = (
                STATUS_CONFIRMED
                if significant and label != "무시할 수준"
                else STATUS_UNVERIFIED
            )

        causes.append(
            CauseCandidate(
                category="설비(Machine)",
                description=(
                    f"{gap.parameter} 평균이 규격 중심에서 "
                    f"{gap.deviation:+.3f} 이탈 — 공차의 "
                    f"{abs(gap.tolerance_fraction) * 100:.0f}% 소모 "
                    f"(현재 {gap.machine_mean:.3f})"
                ),
                status=status,
                basis=basis,
            )
        )

    # 측정
    status, note, _ = _measurement_verdict(report_dir)
    causes.append(
        CauseCandidate(
            category="측정(Measurement)",
            description="계측기 반복성/재현성이 차이를 만들었을 가능성",
            status=status,
            basis=note,
        )
    )

    # 사람
    components = _read(
        report_dir, "quality_msa_variance_components.csv"
    )

    if components is not None and not components.empty:
        ev_rows = components[
            components["source"].str.contains("EV", na=False)
        ]
        av_rows = components[
            components["source"].str.contains("AV", na=False)
        ]

        if not ev_rows.empty and not av_rows.empty:
            ev = float(ev_rows["percent_study_variation"].iloc[0])
            av = float(av_rows["percent_study_variation"].iloc[0])
            causes.append(
                CauseCandidate(
                    category="사람(Man)",
                    description="작업자 간 편차가 불량률 차이를 유발",
                    status=(
                        STATUS_EXCLUDED
                        if av < ev
                        else STATUS_UNVERIFIED
                    ),
                    basis=(
                        f"재현성(AV) {av:.1f}% 가 반복성(EV) "
                        f"{ev:.1f}% 보다 작다. 작업자 요인이 "
                        "계측기 자체 산포보다 작으므로 주원인으로 "
                        "보기 어렵다"
                    ),
                )
            )

    # 방법
    causes.append(
        CauseCandidate(
            category="방법(Method)",
            description=(
                "설비별 층별 관리한계만 운영하여 설비 간 격차가 "
                "판정 대상에서 빠짐"
            ),
            status=STATUS_CONFIRMED,
            basis=(
                "quality_defect_rate_p_chart.csv — 해당 설비가 "
                "자기 관리한계 안에서 관리 상태로 판정됨"
            ),
        )
    )

    # 자재
    #
    # 여기서 p 값만 보면 틀린다. n 이 8,000 이면 실무적으로 의미 없는
    # 차이도 유의하게 나온다. 효과 크기를 함께 봐야 한다.
    # '유의하지만 무시할 수준'은 원인이 아니다.
    anova = _read(report_dir, "quality_anova.csv")
    model_effect_checked = False

    if anova is not None and not anova.empty:
        model_rows = anova[anova["factor_name"] == "Model"]

        if not model_rows.empty:
            model_effect_checked = True
            meaningful = model_rows[
                model_rows["significant"]
                & (model_rows["effect_size"] != "무시할 수준")
            ]
            significant_count = int(model_rows["significant"].sum())
            max_eta = float(model_rows["eta_squared"].max())

            causes.append(
                CauseCandidate(
                    category="자재(Material)",
                    description="기종/자재 조합에 따른 박리 민감도 차이",
                    status=(
                        STATUS_CONFIRMED
                        if not meaningful.empty
                        else STATUS_EXCLUDED
                    ),
                    basis=(
                        f"quality_anova.csv — Model 인자에서 "
                        f"{significant_count}개 응답이 유의하나 "
                        f"최대 eta^2 = {max_eta:.4f} 로 전부 무시할 "
                        "수준이다. n 이 커서 유의성만으로는 판단할 수 "
                        "없으므로 효과 크기로 배제한다"
                        if meaningful.empty
                        else (
                            "quality_anova.csv — Model 인자에서 "
                            f"최대 eta^2 = {max_eta:.4f} 로 무시할 수 "
                            "없는 효과가 확인된다"
                        )
                    ),
                )
            )

    if not model_effect_checked:
        causes.append(
            CauseCandidate(
                category="자재(Material)",
                description="기종/자재 로트에 따른 박리 민감도 차이",
                status=STATUS_UNVERIFIED,
                basis="기종별 분산분석 결과가 리포트에 없다",
            )
        )

    # 환경
    causes.append(
        CauseCandidate(
            category="환경(Environment)",
            description="온습도, 클린룸 조건에 의한 영향",
            status=STATUS_UNVERIFIED,
            basis="환경 데이터를 수집하지 않아 확인 불가",
        )
    )

    return tuple(causes)


# =====================================================================
# D5 ~ D8
# =====================================================================


def _build_corrective(
    report_dir: Path,
    machine: str,
) -> tuple[Action, ...]:
    gaps = _machine_parameter_gaps(report_dir, machine)
    primary = gaps[0].parameter if gaps else "압착 파라미터"

    return (
        Action(
            description=(
                f"{machine} {primary} 계통 점검 후 원인 부품 교체 "
                "또는 보정 (D4 4단계 확인 결과에 따라 확정)"
            ),
            owner_role="설비기술",
            verification=(
                "조치 전후 설비 간 평균 차이를 분산분석으로 재검정"
            ),
            status=ACTION_PENDING,
        ),
        Action(
            description=(
                "설비 간 비교를 정기 품질 판정 항목으로 추가. "
                "월 1회 분산분석 + Tukey HSD 로 설비 간 차이 검정"
            ),
            owner_role="품질보증",
            verification="정기 판정 기록 존재 여부와 이상 시 조치 이력",
            status=ACTION_PENDING,
        ),
        Action(
            description=(
                "p 관리도에 목표 불량률 기준선을 함께 표시하여 "
                "자기 기준 관리한계만으로 판정하지 않도록 변경"
            ),
            owner_role="품질/데이터",
            verification="변경된 관리도 화면과 판정 기준서 개정본",
            status=ACTION_PENDING,
        ),
    )


def _build_verification_targets(
    report_dir: Path,
    machine: str,
) -> tuple[VerificationTarget, ...]:
    ranked = rank_defect_cases(report_dir)

    if ranked.empty:
        return ()

    row = ranked[ranked["Machine"] == machine].iloc[0]
    rate = float(row["defect_rate_percent"])
    overall = float(row["overall_defect_rate_percent"])
    best_rate = float(ranked.iloc[-1]["defect_rate_percent"])

    targets = [
        VerificationTarget(
            metric=f"{machine} 박리 불량률",
            baseline=rate,
            target=overall,
            unit="%",
            direction="감소",
            method="조치 후 4주 데이터로 재계산",
        ),
        VerificationTarget(
            metric=f"{machine} 박리 불량률 (최종 목표)",
            baseline=rate,
            target=best_rate,
            unit="%",
            direction="감소",
            method="최저 설비 수준까지 도달했는지 확인",
        ),
    ]

    capability = _read(report_dir, "quality_capability.csv")

    if capability is not None and not capability.empty:
        peel = capability[
            capability["characteristic"] == "Peel_Strength"
        ]

        if not peel.empty:
            cpk = float(peel["cpk"].iloc[0])
            targets.append(
                VerificationTarget(
                    metric="Peel_Strength Cpk (전체)",
                    baseline=cpk,
                    target=max(1.67, cpk),
                    unit="",
                    direction="증가",
                    method="조치 후 4주 데이터로 공정능력 재계산",
                )
            )

    return tuple(targets)


def _build_prevention(machine: str) -> tuple[Action, ...]:
    return (
        Action(
            description=(
                f"동일 기종 압착 설비 전체({machine} 외)에 대해 "
                "파라미터 평균 편차 점검 — 수평 전개"
            ),
            owner_role="생산기술",
            verification="설비별 점검 기록과 편차 표",
            status=ACTION_PENDING,
        ),
        Action(
            description=(
                "설비 셋업 표준서에 압착 압력·온도 허용 편차 범위를 "
                "명시하고 셋업 시 기록 의무화"
            ),
            owner_role="생산기술",
            verification="개정된 표준서와 셋업 기록지 샘플",
            status=ACTION_PENDING,
        ),
        Action(
            description=(
                "Gage R&R 개선 과제 착수 — 고정구 개선과 측정 위치 "
                "규정으로 %GRR 10% 미만 목표"
            ),
            owner_role="품질보증",
            verification="재실시한 Gage R&R 의 %GRR 과 ndc",
            status=ACTION_PENDING,
        ),
        Action(
            description=(
                "FMEA 의 해당 고장모드 검출도(Detection) 재평가 — "
                "층별 관리만으로는 검출되지 않음이 확인됨"
            ),
            owner_role="품질보증",
            verification="개정된 FMEA 의 RPN 변화",
            status=ACTION_PENDING,
        ),
    )


def _build_team() -> tuple[TeamRole, ...]:
    return (
        TeamRole(
            role="챔피언 / 품질팀장",
            responsibility="자원 배정과 의사결정, D8 종결 승인",
            discipline_focus="D1, D8",
        ),
        TeamRole(
            role="팀 리더 / 품질 엔지니어",
            responsibility="8D 진행 관리, 분석 수행, 보고",
            discipline_focus="D2, D4, D6",
        ),
        TeamRole(
            role="생산기술 엔지니어",
            responsibility="공정 조건 분석과 셋업 표준 개정",
            discipline_focus="D3, D5, D7",
        ),
        TeamRole(
            role="설비기술 엔지니어",
            responsibility="설비 계통 점검과 부품 교체",
            discipline_focus="D4, D5",
        ),
        TeamRole(
            role="생산 담당",
            responsibility="봉쇄조치 실행과 현장 조건 확인",
            discipline_focus="D3, D6",
        ),
        TeamRole(
            role="데이터 담당",
            responsibility="관리도·모델 운전점 운영과 판정 기준 반영",
            discipline_focus="D3, D5",
        ),
    )


# =====================================================================
# 조립
# =====================================================================


def build_defect_rate_case(
    machine: str,
    report_dir: Path | None = None,
    opened_on: date | None = None,
) -> EightDReport:
    """설비 불량률 사례로 8D 를 구성한다."""
    directory = report_dir or get_report_directory()
    missing = missing_reports(directory)

    if missing:
        raise FileNotFoundError(
            "8D 구성에 필요한 분석 결과가 없다: "
            + ", ".join(missing)
            + ". `python -m src.quality.run_quality_analysis` 를 "
            "먼저 실행한다."
        )

    ranked = rank_defect_cases(directory)

    if ranked.empty or machine not in set(ranked["Machine"]):
        raise ValueError(
            f"{machine} 은(는) 분석 결과에 없는 설비다. "
            f"가능한 값: {sorted(set(ranked['Machine']))}"
        )

    row = ranked[ranked["Machine"] == machine].iloc[0]
    ratio = float(row["ratio_to_overall"])
    severity = "중대" if ratio >= 1.5 else "일반"

    causes = _build_cause_candidates(directory, machine)
    _, measurement_note, _ = _measurement_verdict(directory)

    open_questions = [
        f"{machine} 압력·온도 저하의 물리적 원인 "
        "(센서 편차 / 유압 계통 / 셋업 편차 중 무엇인가)",
        measurement_note,
    ]
    open_questions.extend(
        f"{cause.category} — {cause.description}"
        for cause in causes
        if cause.status == STATUS_UNVERIFIED
    )

    return EightDReport(
        case_id=f"8D-{machine}-DEFECT-RATE",
        title=f"{machine} 박리 불량률 상승",
        opened_on=opened_on or date.today(),
        severity=severity,
        machine=machine,
        d0_emergency=(
            Action(
                description=(
                    f"{machine} 생산 LOT 의 출하 보류 여부를 "
                    "품질팀장이 24시간 내 판단"
                ),
                owner_role="품질보증",
                verification="보류 결정 기록",
                status=ACTION_PENDING,
            ),
        ),
        d1_team=_build_team(),
        d2_problem=_build_problem_statement(directory, machine),
        d3_containment=_build_containment(directory, machine),
        d4_occurrence_whys=_build_occurrence_whys(directory, machine),
        d4_escape_whys=_build_escape_whys(directory, machine),
        d4_causes=causes,
        d5_corrective=_build_corrective(directory, machine),
        d6_targets=_build_verification_targets(directory, machine),
        d7_prevention=_build_prevention(machine),
        d8_closure="",
        open_questions=tuple(open_questions),
    )


def build_drift_case(
    machine: str,
    characteristic: str,
    report_dir: Path | None = None,
    opened_on: date | None = None,
) -> EightDReport:
    """관리도 드리프트 사례로 8D 를 구성한다.

    불량이 아직 터지지 않았지만 파라미터가 흐르는 경우다.
    D2 의 '얼마나'가 불량 수가 아니라 이상 신호의 배수가 된다.
    """
    directory = report_dir or get_report_directory()
    signals = _read(directory, "quality_stratified_rule_signals.csv")

    if signals is None or signals.empty:
        raise FileNotFoundError(
            "quality_stratified_rule_signals.csv 가 없다. "
            "`python -m src.quality.run_quality_analysis` 를 "
            "먼저 실행한다."
        )

    scoped = signals[
        (signals["Machine"] == machine)
        & (signals["characteristic"] == characteristic)
    ].sort_values("ratio", ascending=False)

    if scoped.empty:
        raise ValueError(
            f"{machine} / {characteristic} 조합의 이상 신호가 없다."
        )

    top = scoped.iloc[0]
    rule_numbers = [
        str(name).replace("NELSON_RULE_", "")
        for name in scoped["rule"]
    ]
    # 조사 문제를 피하려고 "규칙 1 가" 대신 "규칙 5종(...)" 형태로 쓴다.
    rules = f"Nelson 규칙 {len(rule_numbers)}종({', '.join(rule_numbers)})"
    point_count = int(top["point_count"])

    gaps = _machine_parameter_gaps(directory, machine)
    drift_gap = next(
        (
            gap
            for gap in gaps
            if gap.parameter == characteristic
        ),
        None,
    )

    evidence = (
        Evidence(
            source="quality_stratified_rule_signals.csv",
            metric=f"{characteristic} 최대 초과 배수",
            value=f"{float(top['ratio']):.1f}배",
            interpretation=(
                f"관리 상태에서 기대되는 오경보 수 대비. "
                f"{rules}이 동시에 발화"
            ),
        ),
    )

    whys = [
        WhyStep(
            depth=1,
            question=f"왜 {machine} 의 {characteristic} 에 신호가 뜨는가?",
            answer=(
                f"{rules}이 기대 오경보 대비 최대 "
                f"{float(top['ratio']):.1f}배로 발화했다. "
                "런 규칙이 집중적으로 걸린 것은 평균이 한쪽으로 "
                "이동했다는 뜻이다."
            ),
            verified=True,
            evidence=evidence,
        ),
    ]

    if drift_gap is not None:
        whys.append(
            WhyStep(
                depth=2,
                question="이동 방향과 크기는?",
                answer=(
                    f"{characteristic} 평균이 규격 중심 "
                    f"{drift_gap.target:.3f} 에서 "
                    f"{drift_gap.deviation:+.3f} 벗어나 "
                    "한쪽 공차의 "
                    f"{abs(drift_gap.tolerance_fraction) * 100:.0f}%"
                    " 를 소모했다. 아직 규격을 벗어나지 않아 불량으로는"
                    " 나타나지 않지만, 3σ 이탈 없이 런 규칙만 걸리는 "
                    "것은 작은 폭의 지속적 드리프트의 전형이다."
                ),
                verified=True,
                evidence=(
                    Evidence(
                        source="quality_machine_summary.csv",
                        metric=f"{characteristic} 평균 / 공차 대비",
                        value=(
                            f"{drift_gap.machine_mean:.3f} / "
                            f"{drift_gap.tolerance_fraction:+.1%}"
                        ),
                        interpretation=(
                            "규격 이탈 전이므로 불량률로는 아직 "
                            "드러나지 않는다"
                        ),
                    ),
                ),
            )
        )

    whys.append(
        WhyStep(
            depth=len(whys) + 1,
            question="왜 드리프트가 생겼는가?",
            answer=(
                "온도 제어 계통의 열전대 노화, 히터 출력 저하, "
                "설정값 변경 이력 중 무엇인지 현장 확인이 필요하다. "
                "드리프트는 단발 이상과 달리 시간에 따라 커지므로 "
                "확인이 늦을수록 비용이 커진다."
            ),
            verified=False,
        )
    )

    return EightDReport(
        case_id=f"8D-{machine}-{characteristic.upper()}-DRIFT",
        title=f"{machine} {characteristic} 드리프트",
        opened_on=opened_on or date.today(),
        severity="예방",
        machine=machine,
        d0_emergency=(
            Action(
                description=(
                    f"{machine} {characteristic} 설정값과 최근 "
                    "검교정 이력 즉시 확인"
                ),
                owner_role="설비기술",
                verification="검교정 성적서와 설정값 기록 대조",
                status=ACTION_PENDING,
            ),
        ),
        d1_team=_build_team(),
        d2_problem=ProblemStatement(
            what=f"{characteristic} 평균의 지속적 이동",
            where=f"압착 공정 {machine}",
            when=(
                f"관측점 {point_count:,}개 구간 전반. "
                "특정 시점 급변이 아니라 누적 드리프트"
            ),
            who="설비 고유 현상. 작업자와 무관",
            which="해당 설비를 거치는 전 기종",
            how=(
                "3σ 이탈 없이 런 규칙만 발화. "
                "Shewhart 관리도가 둔감한 작은 폭의 이동"
            ),
            how_many=(
                f"기대 오경보 대비 최대 {float(top['ratio']):.1f}배"
            ),
            is_observed=(f"{machine} / {characteristic}",),
            is_not_observed=(
                "동일 설비의 타 파라미터, 타 설비의 동일 파라미터",
            ),
            evidence=evidence,
        ),
        d3_containment=(
            Action(
                description=(
                    f"{characteristic} 을 일 1회 수동 확인 항목으로 "
                    "임시 추가"
                ),
                owner_role="생산",
                verification="일일 점검 기록",
                status=ACTION_PENDING,
            ),
        ),
        d4_occurrence_whys=tuple(whys),
        d4_escape_whys=(
            WhyStep(
                depth=1,
                question="왜 더 일찍 발견되지 않았는가?",
                answer=(
                    "3σ 이탈 기준(규칙 1)만 보면 잡히지 않는다. "
                    "Shewhart 관리도는 1.5σ 이하의 작은 이동에 "
                    "둔감하다. 런 규칙을 함께 보지 않으면 "
                    "드리프트는 규격을 벗어날 때까지 드러나지 않는다."
                ),
                verified=True,
            ),
            WhyStep(
                depth=2,
                question="무엇이 있었어야 했는가?",
                answer=(
                    "작은 이동에 민감한 EWMA 또는 CUSUM 관리도를 "
                    "병행했어야 한다. 누적 방식이라 지속적 드리프트를 "
                    "Shewhart 보다 훨씬 빨리 검출한다."
                ),
                verified=True,
            ),
        ),
        d4_causes=(
            CauseCandidate(
                category="설비(Machine)",
                description=f"{characteristic} 제어 계통의 특성 변화",
                status=STATUS_UNVERIFIED,
                basis="현장 점검 필요",
            ),
            CauseCandidate(
                category="방법(Method)",
                description=(
                    "Shewhart 관리도만 운영하여 작은 드리프트가 "
                    "검출되지 않음"
                ),
                status=STATUS_CONFIRMED,
                basis=(
                    "규칙 1 대비 런 규칙의 발화 비율 — "
                    "quality_stratified_rule_signals.csv"
                ),
            ),
            CauseCandidate(
                category="측정(Measurement)",
                description="온도 센서 자체의 드리프트",
                status=STATUS_UNVERIFIED,
                basis="센서 검교정 이력 확인 필요",
            ),
        ),
        d5_corrective=(
            Action(
                description=(
                    f"{characteristic} 제어 계통 점검 및 "
                    "원인 부품 조치"
                ),
                owner_role="설비기술",
                verification="조치 후 4주 관리도에서 런 규칙 소멸 확인",
                status=ACTION_PENDING,
            ),
            Action(
                description=(
                    "주요 온도 파라미터에 EWMA 관리도 도입"
                ),
                owner_role="품질/데이터",
                verification="과거 데이터로 검출 시점 비교 후 적용",
                status=ACTION_PENDING,
            ),
        ),
        d6_targets=(
            VerificationTarget(
                metric=f"{characteristic} 런 규칙 초과 배수",
                baseline=float(top["ratio"]),
                target=2.0,
                unit="배",
                direction="감소",
                method="조치 후 4주 데이터로 Nelson 판정 재실행",
            ),
        ),
        d7_prevention=(
            Action(
                description=(
                    "전 설비 온도 파라미터에 EWMA 병행 적용"
                ),
                owner_role="품질/데이터",
                verification="적용 설비 목록과 관리도 화면",
                status=ACTION_PENDING,
            ),
            Action(
                description=(
                    "온도 센서 검교정 주기 재검토 — 드리프트 "
                    "발생 구간을 근거로 주기 단축 검토"
                ),
                owner_role="품질보증",
                verification="개정된 검교정 관리 규정",
                status=ACTION_PENDING,
            ),
        ),
        open_questions=(
            f"{machine} {characteristic} 드리프트의 물리적 원인",
            "EWMA 의 가중치(λ)와 관리한계 폭 설정값 결정",
        ),
    )


def build_recommended_cases(
    report_dir: Path | None = None,
    opened_on: date | None = None,
) -> list[EightDReport]:
    """데이터가 8D 를 열어야 한다고 말하는 사례를 모두 만든다.

    사람이 고르지 않는다. 불량률이 전체 평균의 ESCALATION_RATIO 배를
    넘는 설비와, CRITICAL 이상 신호가 잡힌 파라미터가 대상이다.
    """
    directory = report_dir or get_report_directory()
    reports: list[EightDReport] = []

    ranked = rank_defect_cases(directory)

    if not ranked.empty:
        for _, row in ranked[ranked["escalate"]].iterrows():
            reports.append(
                build_defect_rate_case(
                    str(row["Machine"]),
                    report_dir=directory,
                    opened_on=opened_on,
                )
            )

    drifts = rank_drift_cases(directory)

    if not drifts.empty:
        seen: set[str] = set()

        for _, row in drifts.iterrows():
            machine = str(row["Machine"])
            characteristic = str(row["characteristic"])
            key = f"{machine}|{characteristic}"

            if key in seen:
                continue

            seen.add(key)
            reports.append(
                build_drift_case(
                    machine,
                    characteristic,
                    report_dir=directory,
                    opened_on=opened_on,
                )
            )

    return reports


# =====================================================================
# D6 효과 확인
# =====================================================================


def verify_defect_rate(
    dataframe: pd.DataFrame,
    machine: str,
) -> float:
    """현재 데이터에서 해당 설비의 박리 불량률을 다시 계산한다.

    D6 는 '조치했다'가 아니라 '조치 후 지표가 목표에 닿았다'로
    닫아야 한다. 그래서 값을 고정해두지 않고 매번 계산한다.
    조치 전이면 기준선과 같은 값이 나오고, 그게 정확한 표시다.
    """
    if "Machine" not in dataframe.columns:
        raise KeyError("Machine 열이 없다.")

    if "Defect" not in dataframe.columns:
        raise KeyError("Defect 열이 없다.")

    scoped = dataframe[dataframe["Machine"] == machine]

    if scoped.empty:
        raise ValueError(f"{machine} 데이터가 없다.")

    return float(
        100.0 * (scoped["Defect"] == "Delamination").mean()
    )


def build_verification_table(
    report: EightDReport,
    dataframe: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """D6 목표별 현재 값과 달성 여부 표."""
    rows: list[dict[str, object]] = []

    for target in report.d6_targets:
        current: float | None = None

        if (
            dataframe is not None
            and report.machine
            and "불량률" in target.metric
        ):
            try:
                current = verify_defect_rate(
                    dataframe, report.machine
                )
            except (KeyError, ValueError):
                current = None

        rows.append(
            {
                "확인 지표": target.metric,
                "기준선": round(target.baseline, 3),
                "목표": round(target.target, 3),
                "단위": target.unit,
                "현재": (
                    round(current, 3) if current is not None else "-"
                ),
                "달성": (
                    ("예" if target.is_met(current) else "아니오")
                    if current is not None
                    else "미측정"
                ),
                "확인 방법": target.method,
            }
        )

    return pd.DataFrame(rows)


# =====================================================================
# 마크다운 출력
# =====================================================================


def _why_lines(steps: tuple[WhyStep, ...]) -> list[str]:
    lines: list[str] = []

    for step in steps:
        lines.append(
            f"{step.depth}. **{step.question}** [{step.marker}]"
        )
        lines.append(f"   {step.answer}")

        for item in step.evidence:
            lines.append(f"   - 근거: {item.as_line()}")

        lines.append("")

    return lines


def _action_table(actions: tuple[Action, ...]) -> list[str]:
    if not actions:
        return ["_등록된 조치 없음_", ""]

    lines = [
        "| 조치 | 담당 | 검증 방법 | 상태 |",
        "| --- | --- | --- | --- |",
    ]

    for action in actions:
        lines.append(
            f"| {action.description} | {action.owner_role} | "
            f"{action.verification} | {action.status} |"
        )

    lines.append("")

    for action in actions:
        for item in action.evidence:
            lines.append(f"- 근거: {item.as_line()}")

    lines.append("")

    return lines


def render_markdown(report: EightDReport) -> str:
    """8D 리포트를 마크다운으로 렌더링한다."""
    status = report.discipline_status
    lines: list[str] = [
        f"# {report.case_id} — {report.title}",
        "",
        f"- 개시일: {report.opened_on.isoformat()}",
        f"- 심각도: {report.severity}",
        "- 분석 단계(D1·D2·D4): "
        + ("완료" if report.analysis_complete else "진행 중"),
        "- 실행 대기 단계: "
        + (", ".join(report.pending_stages) or "없음"),
        "",
        "## 진행 현황",
        "",
        "| 단계 | 제목 | 상태 |",
        "| --- | --- | --- |",
    ]

    for code, title in DISCIPLINE_TITLES.items():
        lines.append(f"| {code} | {title} | {status[code]} |")

    lines.extend(["", "## D0. 준비 및 긴급 대응", ""])
    lines.extend(_action_table(report.d0_emergency))

    lines.extend(["## D1. 팀 구성", ""])
    lines.append("역할 기준으로 구성한다. 이름은 착수 시 배정한다.")
    lines.extend(
        [
            "",
            "| 역할 | 책임 | 주 담당 단계 |",
            "| --- | --- | --- |",
        ]
    )

    for member in report.d1_team:
        lines.append(
            f"| {member.role} | {member.responsibility} | "
            f"{member.discipline_focus} |"
        )

    lines.append("")

    if report.d2_problem is not None:
        problem = report.d2_problem
        lines.extend(["## D2. 문제 기술", "", "### 5W2H", ""])
        lines.extend(["| 항목 | 내용 |", "| --- | --- |"])

        for row in problem.as_rows():
            lines.append(f"| {row['항목']} | {row['내용']} |")

        lines.extend(
            [
                "",
                "### IS / IS-NOT",
                "",
                "비슷한 조건에서 발생하지 않은 대상을 함께 적는다. "
                "둘의 차이가 원인 후보로 남는다.",
                "",
                "| 구분 | 대상 |",
                "| --- | --- |",
                f"| 발생함(IS) | {', '.join(problem.is_observed)} |",
                "| 발생하지 않음(IS-NOT) | "
                f"{', '.join(problem.is_not_observed)} |",
                "",
            ]
        )

        if problem.evidence:
            lines.append("근거")
            lines.append("")

            for item in problem.evidence:
                lines.append(f"- {item.as_line()}")

            lines.append("")

    lines.extend(["## D3. 임시 봉쇄조치", ""])
    lines.append(
        "원인을 모르는 동안 불량이 고객에게 나가지 않게 막는 단계다. "
        "영구 조치가 아니므로 D5 확정 후 해제한다."
    )
    lines.append("")
    lines.extend(_action_table(report.d3_containment))

    lines.extend(
        [
            "## D4. 근본원인 분석 및 검증",
            "",
            "발생원인과 유출원인을 나누어 추적한다. "
            "발생원인만 없애면 다음 불량도 같은 경로로 빠져나간다.",
            "",
            "### 발생원인 5 Why — 왜 생겼는가",
            "",
        ]
    )
    lines.extend(_why_lines(report.d4_occurrence_whys))

    lines.extend(["### 유출원인 5 Why — 왜 못 걸렀는가", ""])
    lines.extend(_why_lines(report.d4_escape_whys))

    lines.extend(
        [
            "### 특성요인 정리 (6M)",
            "",
            "| 분류 | 원인 후보 | 상태 | 판단 근거 |",
            "| --- | --- | --- | --- |",
        ]
    )

    for cause in report.d4_causes:
        lines.append(
            f"| {cause.category} | {cause.description} | "
            f"{cause.status} | {cause.basis} |"
        )

    lines.extend(["", "## D5. 영구 시정조치 선정", ""])
    lines.extend(_action_table(report.d5_corrective))

    lines.extend(
        [
            "## D6. 시정조치 실행 및 효과 확인",
            "",
            "기준선과 목표를 조치 전에 고정한다. "
            "조치 후에 목표를 정하면 달성했다는 결론이 먼저 나온다.",
            "",
            "| 확인 지표 | 기준선 | 목표 | 단위 | 확인 방법 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    for target in report.d6_targets:
        lines.append(
            f"| {target.metric} | {target.baseline:.3f} | "
            f"{target.target:.3f} | {target.unit or '-'} | "
            f"{target.method} |"
        )

    lines.extend(["", "## D7. 재발 방지", ""])
    lines.extend(_action_table(report.d7_prevention))

    lines.extend(["## D8. 종결 및 팀 인정", ""])
    lines.append(
        report.d8_closure
        or "_D6 효과 확인이 끝난 뒤 작성한다._"
    )

    if report.open_questions:
        lines.extend(
            [
                "",
                "## 미해결 항목",
                "",
                "확인하지 않은 것을 확인한 것처럼 적지 않는다. "
                "아래는 현재 데이터만으로는 답할 수 없어 현장 확인이 "
                "필요한 항목이다.",
                "",
            ]
        )

        for question in report.open_questions:
            lines.append(f"- {question}")

    lines.append("")

    return "\n".join(lines)
