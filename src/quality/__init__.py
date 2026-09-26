"""품질 분석 모듈.

JMP 에서 수행하던 분석을 코드로 옮긴 것이다.

- control_charts : I-MR, X-bar-R 관리도. 관리한계를 부분군 내 변동으로 추정
- nelson_rules   : Nelson 판정 규칙 8종
- capability     : Cp/Cpk(단기)와 Pp/Ppk(장기) 공정능력
- msa            : Gage R&R(ANOVA 법), 편향, 선형성
- anova          : 일원분산분석, Levene 등분산 검정, Tukey HSD 다중비교
"""

from src.quality.anova import (
    AnovaResult,
    TukeyComparison,
    compare_factor_across_responses,
    one_way_anova,
    tukey_hsd,
    tukey_hsd_table,
)
from src.quality.capability import (
    CapabilityResult,
    analyze_capability,
    analyze_capability_table,
)
from src.quality.control_charts import (
    ControlChart,
    estimate_sigma_overall,
    estimate_sigma_within,
    individual_moving_range_chart,
    xbar_r_chart,
)
from src.quality.msa import (
    GageRnRResult,
    bias_and_linearity,
    gage_rnr_anova,
)
from src.quality.nelson_rules import (
    RuleViolation,
    evaluate_all_rules,
    evaluate_chart,
    summarize_violations,
)

__all__ = [
    "AnovaResult",
    "CapabilityResult",
    "ControlChart",
    "GageRnRResult",
    "RuleViolation",
    "TukeyComparison",
    "analyze_capability",
    "analyze_capability_table",
    "bias_and_linearity",
    "compare_factor_across_responses",
    "estimate_sigma_overall",
    "estimate_sigma_within",
    "evaluate_all_rules",
    "evaluate_chart",
    "gage_rnr_anova",
    "individual_moving_range_chart",
    "one_way_anova",
    "summarize_violations",
    "tukey_hsd",
    "tukey_hsd_table",
    "xbar_r_chart",
]
