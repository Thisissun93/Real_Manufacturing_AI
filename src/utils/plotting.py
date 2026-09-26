"""차트 공통 설정.

두 가지를 담당한다.

1. 한글 폰트 등록
   matplotlib 기본 폰트(DejaVu Sans)에는 한글 글리프가 없다. 설정하지 않으면
   축 이름과 범례의 한글이 네모로 깨지고 "Glyph missing from font" 경고가 뜬다.
   저장소에 포함된 assets/fonts/NanumGothic.ttf 를 등록해 해결한다.

2. 색상 역할 정의
   색을 '무슨 뜻인지'로 고정한다. 계열 색과 상태 색을 섞어 쓰면
   빨간 선이 어떤 때는 4번째 계열이고 어떤 때는 경고가 되어 읽을 수 없다.

   - SERIES_*   : 서로 구분해야 하는 계열. 정해진 순서대로만 쓴다.
   - STATUS_*   : 좋음/주의/심각/위험 판정. 계열 색으로 재사용하지 않는다.
   - 회색 계열  : 격자, 축, 보조선처럼 뒤로 물러나야 하는 요소.

   계열 색 3개는 색각 이상 조건에서도 구분되도록 검증된 조합이다.
   4개 이상이 필요하면 색을 하나 더 만들지 말고 묶거나 화면을 나눈다.
"""

from functools import lru_cache
from pathlib import Path
from typing import Final

import matplotlib


matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager


# --- 계열 색 (정해진 순서대로 사용) ---------------------------------------
SERIES_BLUE: Final[str] = "#2a78d6"
SERIES_ORANGE: Final[str] = "#eb6834"
SERIES_AQUA: Final[str] = "#1baf7a"

SERIES_COLORS: Final[tuple[str, ...]] = (
    SERIES_BLUE,
    SERIES_ORANGE,
    SERIES_AQUA,
)

# --- 상태 색 (판정 전용. 계열 색으로 쓰지 않는다) --------------------------
STATUS_GOOD: Final[str] = "#0ca30c"
STATUS_WARNING: Final[str] = "#fab219"
STATUS_SERIOUS: Final[str] = "#ec835a"
STATUS_CRITICAL: Final[str] = "#d03b3b"

# --- 차트 크롬 -------------------------------------------------------------
INK_PRIMARY: Final[str] = "#0b0b0b"
INK_SECONDARY: Final[str] = "#52514e"
INK_MUTED: Final[str] = "#898781"
GRIDLINE: Final[str] = "#e1e0d9"
AXIS_LINE: Final[str] = "#c3c2b7"
SURFACE: Final[str] = "#fcfcfb"


SEVERITY_COLORS: Final[dict[str, str]] = {
    "NORMAL": STATUS_GOOD,
    "WATCH": STATUS_WARNING,
    "WARNING": STATUS_SERIOUS,
    "CRITICAL": STATUS_CRITICAL,
}

CAPABILITY_VERDICT_COLORS: Final[dict[str, str]] = {
    "우수": STATUS_GOOD,
    "양호": STATUS_GOOD,
    "개선 필요": STATUS_WARNING,
    "부적합": STATUS_CRITICAL,
}

GAGE_VERDICT_COLORS: Final[dict[str, str]] = {
    "적합": STATUS_GOOD,
    "조건부 적합": STATUS_WARNING,
    "부적합": STATUS_CRITICAL,
}


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def register_korean_font() -> str | None:
    """번들된 나눔고딕을 matplotlib 에 등록한다.

    등록에 성공하면 폰트 이름을, 폰트 파일이 없으면 None 을 반환한다.
    폰트가 없어도 차트는 그려지고 한글만 깨진다.
    """
    font_path = (
        get_project_root() / "assets" / "fonts" / "NanumGothic.ttf"
    )

    if not font_path.exists():
        return None

    try:
        font_manager.fontManager.addfont(str(font_path))
        font_name = font_manager.FontProperties(
            fname=str(font_path)
        ).get_name()
    except (RuntimeError, OSError):
        return None

    plt.rcParams["font.family"] = font_name
    # 폰트를 바꾸면 마이너스 기호가 네모로 깨진다.
    plt.rcParams["axes.unicode_minus"] = False

    return font_name


def apply_chart_style() -> None:
    """차트 공통 스타일을 적용한다.

    격자와 축은 뒤로 물러나게 하고 데이터가 앞에 오게 한다.
    """
    register_korean_font()

    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "axes.edgecolor": AXIS_LINE,
            "axes.labelcolor": INK_SECONDARY,
            "axes.titlecolor": INK_PRIMARY,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "grid.color": GRIDLINE,
            "grid.linewidth": 0.6,
            "grid.alpha": 0.9,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "legend.frameon": False,
            "lines.linewidth": 1.6,
            "figure.dpi": 110,
        }
    )


def create_figure(
    width: float = 11.0,
    height: float = 4.2,
) -> tuple[plt.Figure, plt.Axes]:
    """공통 스타일이 적용된 figure 와 axes 를 만든다."""
    apply_chart_style()

    figure, axes = plt.subplots(figsize=(width, height))

    axes.set_axisbelow(True)
    axes.spines["top"].set_visible(False)
    axes.spines["right"].set_visible(False)

    return figure, axes


def severity_color(severity: str) -> str:
    """판정 등급에 대응하는 상태 색을 반환한다."""
    return SEVERITY_COLORS.get(severity, INK_MUTED)


def capability_color(verdict: str) -> str:
    """공정능력 판정에 대응하는 상태 색을 반환한다."""
    return CAPABILITY_VERDICT_COLORS.get(verdict, INK_MUTED)


def gage_color(verdict: str) -> str:
    """Gage R&R 판정에 대응하는 상태 색을 반환한다."""
    return GAGE_VERDICT_COLORS.get(verdict, INK_MUTED)
