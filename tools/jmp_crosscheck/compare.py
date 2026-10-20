"""Python(src/quality) 결과와 JMP 결과를 같은 key 로 맞춰 비교한다.

입력
  results/python_reference.csv : python -m tools.jmp_crosscheck.python_reference
  results/jmp_dump.csv         : JMP 에서 crosscheck.jsl 실행 결과
출력
  results/crosscheck_table.csv : 항목별 Python 값, JMP 값, 상대 차이, 판정

실행: python -m tools.jmp_crosscheck.compare
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent / "results"

# 상대 차이 판정 기준
EXACT = 1e-6        # 부동소수 수준 일치
ROUNDING = 1e-3     # 상수 반올림 수준 (예: d2 = 1.128 vs 1.12838)

# 이름 대응: Python 분산 성분 이름 -> JMP 행 이름
GRR_VARIANCE = {
    "반복성(EV)": ("Variance Components", "Within"),
    "재현성(AV)": ("Variance Components", "Operator"),
    "교호작용": ("Variance Components", "Operator*Part"),
    "측정시스템(GRR)": ("Variance Components for Gauge R&R", "Gauge R&R"),
    "부품(PV)": ("Variance Components", "Part"),
    "총 변동(TV)": ("Variance Components", "Total"),
}
GRR_PERCENT = {
    "반복성(EV)": "Repeatability",
    "재현성(AV)": "Operator",
    "교호작용": "Operator*Part",
    "측정시스템(GRR)": "Gauge R&R",
    "부품(PV)": "Part Variation",
    "총 변동(TV)": "Total Variation",
}

# 차이가 나는 이유를 확인한 항목. 판정 옆에 근거로 남긴다.
KNOWN_CAUSE = {
    "Within Sigma": "d2 상수: Python 1.128(표 값) / JMP 2/sqrt(pi)=1.12838",
    "Cp": "Within Sigma 의 d2 반올림 차이가 그대로 전파",
    "Cpk": "Within Sigma 의 d2 반올림 차이가 그대로 전파",
    "UCL": "Python 2.660 x MR(표 값) / JMP 3/d2 = 2.6587 x MR",
    "LCL": "Python 2.660 x MR(표 값) / JMP 3/d2 = 2.6587 x MR",
}


class JmpLookup:
    def __init__(self, dump: pd.DataFrame) -> None:
        dump = dump.copy()
        dump["row"] = dump["row"].fillna("").astype(str).str.strip(" |")
        dump["column"] = dump["column"].fillna("").astype(str)
        dump["outline"] = dump["outline"].fillna("").astype(str)
        self.dump = dump

    def get(self, section: str, outline_end: str, column: str,
            row: str, row_prefix: bool = False) -> float:
        d = self.dump
        sel = d[(d.section == section)
                & d.outline.str.endswith(outline_end)
                & (d.column == column)]
        sel = sel[sel.row.str.startswith(row)] if row_prefix else sel[sel.row == row]
        if sel.empty:
            return np.nan
        return float(sel.value.iloc[0])


def jmp_value(j: JmpLookup, area: str, key: str) -> float:
    parts = key.split("|")

    if area == "ANOVA":
        y, stat = parts
        sec = f"ANOVA|{y}"
        return {
            "F": lambda: j.get(sec, "Analysis of Variance", "F Ratio", "Machine"),
            "Prob>F": lambda: j.get(sec, "Analysis of Variance", "Prob > F", "Machine"),
            "BrownForsythe_p": lambda: j.get(sec, "Tests that the Variances are Equal", "Prob > F", "Brown-Forsythe"),
            "Welch_F": lambda: j.get(sec, "Welch's Test", "F Ratio", "1"),
            "Welch_p": lambda: j.get(sec, "Welch's Test", "Prob > F", "1"),
        }[stat]()

    if area == "Tukey":
        y, pair, stat = parts
        a, b = pair.split("-", 1)
        sec = f"ANOVA|{y}"
        col = {"Diff": "Difference", "Lower CL": "Lower CL", "Upper CL": "Upper CL"}[stat]
        v = j.get(sec, "Ordered Differences Report", col, f"{a} | {b}")
        if not np.isnan(v):
            return v
        # JMP 는 평균이 큰 쪽을 앞에 둔다. 순서가 반대면 부호와 신뢰한계를 뒤집는다.
        flip = {"Difference": "Difference", "Lower CL": "Upper CL", "Upper CL": "Lower CL"}[col]
        return -j.get(sec, "Ordered Differences Report", flip, f"{b} | {a}")

    if area == "Capability":
        y, stat = parts
        base = f"{y} Capability"
        if stat in ("Mean", "Within Sigma", "Overall Sigma"):
            row = "Sample Mean" if stat == "Mean" else stat
            return j.get("Capability", f"{base} > Process Summary", "~Value", row)
        if stat in ("Cp", "Cpk"):
            return j.get("Capability", f"{base} > Within Sigma Capability", "Estimate", stat)
        return j.get("Capability", f"{base} > Overall Sigma Capability", "Estimate", stat)

    if area == "GageRR":
        if key == "ndc":
            return j.get("GageRR", "Gauge R&R", "~Gauge Stat", "Number of Distinct", row_prefix=True)
        if key == "Interaction|Prob>F":
            return j.get("GageRR", "Analysis of Variance", "Prob > F", "Operator*Part")
        source, stat = parts
        if stat == "Variance":
            outline, row = GRR_VARIANCE[source]
            return j.get("GageRR", outline, "Var Component", row)
        return j.get("GageRR", "Gauge R&R", "% Total", GRR_PERCENT[source] + " |", row_prefix=True)

    if area == "Bias":
        if key == "Bias":
            return j.get("Bias", "Parameter Estimates", "Estimate", "Intercept")
        if key == "Bias|Prob>|t|":
            return j.get("Bias", "Parameter Estimates", "Prob>|t|", "Intercept")
        if key.startswith("Slope"):
            return j.get("Linearity", "Parameter Estimates", "Estimate", "Reference")
        return j.get("Linearity", "Parameter Estimates", "Estimate", "Intercept")

    if area == "IMR":
        machine, param, stat = parts
        sec = f"IMR|{machine}|{param}"
        if stat == "MR Avg":
            return j.get(sec, "Limit Summaries", "Avg", "Moving Range", row_prefix=True)
        return j.get(sec, "Limit Summaries", stat, "Individual", row_prefix=True)

    return np.nan


def judge(py: float, jm: float, key: str) -> tuple[float, str, str]:
    if np.isnan(jm):
        return np.nan, "JMP 값 없음", ""
    if abs(py) < 1e-100 and abs(jm) < 1e-100:
        return 0.0, "일치", "두 값 모두 0 (표현 한계 아래)"
    rel = abs(py - jm) / max(abs(jm), 1e-300)
    stat = key.split("|")[-1]
    if rel < EXACT:
        return rel, "일치", ""
    if rel < ROUNDING:
        return rel, "일치(상수 반올림)", KNOWN_CAUSE.get(stat, "")
    return rel, "차이", KNOWN_CAUSE.get(stat, "원인 확인 필요")


def main() -> None:
    py = pd.read_csv(HERE / "python_reference.csv", encoding="utf-8-sig")
    j = JmpLookup(pd.read_csv(HERE / "jmp_dump.csv", encoding="utf-8-sig"))

    rows = []
    for _, r in py.iterrows():
        jm = jmp_value(j, r.area, r.key)
        rel, verdict, note = judge(float(r.python), jm, r.key)
        rows.append({"area": r.area, "key": r.key, "python": r.python,
                     "jmp": jm, "rel_diff": rel, "verdict": verdict, "note": note})

    out = pd.DataFrame(rows)
    out.to_csv(HERE / "crosscheck_table.csv", index=False, encoding="utf-8-sig")

    summary = out.groupby(["area", "verdict"]).size().unstack(fill_value=0)
    print(summary.to_string())
    print(f"\n전체 {len(out)}개 항목, 최대 상대 차이 {out.rel_diff.max():.2e}")


if __name__ == "__main__":
    main()
