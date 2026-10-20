"""JMP 교차검증용 Python 기준값 생성.

저장소의 src/quality 모듈을 그대로 호출해 비교 대상 지표를
key,value 형식 CSV 로 저장한다. JMP 쪽(crosscheck.jsl)도 같은 key 로 저장한다.

실행: python -m tools.jmp_crosscheck.python_reference
"""
from pathlib import Path

import pandas as pd

from src.process_spec import build_capability_specifications
from src.quality.anova import one_way_anova, tukey_hsd
from src.quality.capability import analyze_capability
from src.quality.control_charts import individual_moving_range_chart
from src.quality.msa import bias_and_linearity, gage_rnr_anova

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "results" / "python_reference.csv"

ANOVA_RESPONSES = ["Peel_Strength", "ABF_Roughness", "Total_Thickness",
                   "Press2_Temp", "Press2_Pressure", "Cure_Temp"]
CAPABILITY = ["CZ_Roughness", "Peel_Strength", "ABF_Roughness", "Total_Thickness"]
IMR_PARAMS = ["Press2_Pressure", "Press2_Temp", "Cure_Temp"]


def main() -> None:
    proc = pd.read_csv(ROOT / "Data/process_monitoring_data.csv", encoding="utf-8-sig")
    grr = pd.read_csv(ROOT / "Data/msa_gage_rnr_data.csv", encoding="utf-8-sig")
    bias = pd.read_csv(ROOT / "Data/msa_bias_study_data.csv", encoding="utf-8-sig")
    rows: list[tuple[str, str, float]] = []

    def add(area: str, key: str, value) -> None:
        if value is not None:
            rows.append((area, key, float(value)))

    for y in ANOVA_RESPONSES:
        r = one_way_anova(proc, response=y, factor="Machine").to_dict()
        add("ANOVA", f"{y}|F", r["f"])
        add("ANOVA", f"{y}|Prob>F", r["p_value"])
        add("ANOVA", f"{y}|BrownForsythe_p", r["levene_p"])
        add("ANOVA", f"{y}|Welch_F", r["welch_f"])
        add("ANOVA", f"{y}|Welch_p", r["welch_p"])
        for c in tukey_hsd(proc, response=y, factor="Machine"):
            d = c.to_dict() if hasattr(c, "to_dict") else c.__dict__
            a, b = sorted([d["group_a"], d["group_b"]])
            sign = 1 if d["group_a"] == a else -1
            lo, hi = sorted([sign * d["ci_lower"], sign * d["ci_upper"]])
            add("Tukey", f"{y}|{a}-{b}|Diff", sign * d["mean_difference"])
            add("Tukey", f"{y}|{a}-{b}|Lower CL", lo)
            add("Tukey", f"{y}|{a}-{b}|Upper CL", hi)

    specs = build_capability_specifications()
    for y in CAPABILITY:
        s = specs[y]
        r = analyze_capability(proc[y], characteristic=y, lower_spec=s["lsl"], upper_spec=s["usl"],
                               target=s["target"]).to_dict()
        for k, name in [("mean", "Mean"), ("sigma_within", "Within Sigma"),
                        ("sigma_overall", "Overall Sigma"), ("cp", "Cp"),
                        ("cpk", "Cpk"), ("pp", "Pp"), ("ppk", "Ppk")]:
            add("Capability", f"{y}|{name}", r[k])

    g = gage_rnr_anova(grr, value_column="Total_Thickness")
    gd = g.to_dict()
    for _, row in g.variance_components().iterrows():
        add("GageRR", f"{row['source']}|Variance", row["variance"])
        add("GageRR", f"{row['source']}|%StudyVar", row["percent_study_variation"])
    add("GageRR", "Interaction|Prob>F", gd.get("interaction_p_value"))
    add("GageRR", "ndc", gd.get("ndc"))

    b = bias_and_linearity(bias, measured_column="Total_Thickness",
                           reference_column="Reference")
    add("Bias", "Bias", b["bias"])
    add("Bias", "Bias|Prob>|t|", b["bias_p_value"])
    add("Bias", "Slope(Measured~Reference)", b["slope"])
    add("Bias", "Intercept", b.get("intercept"))

    for m, sub in proc.groupby("Machine", sort=True):
        for p in IMR_PARAMS:
            ind, mr = individual_moving_range_chart(sub[p])
            add("IMR", f"{m}|{p}|Avg", ind.center_line)
            add("IMR", f"{m}|{p}|UCL", ind.upper_limit)
            add("IMR", f"{m}|{p}|LCL", ind.lower_limit)
            add("IMR", f"{m}|{p}|MR Avg", mr.center_line)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["area", "key", "python"]).to_csv(
        OUT, index=False, encoding="utf-8-sig")
    print(f"{len(rows)} 항목 저장: {OUT}")


if __name__ == "__main__":
    main()
