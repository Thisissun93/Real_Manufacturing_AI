"""업무 시나리오 측정: 불량 LOT 하나를 조사할 때 걸리는 시간과 대조하는 기록 수.

엔지니어가 LOT ID를 넣으면 공정 이력·AOI·동일 조건 LOT·기준 이탈을 모아
원인 후보와 확인 순서를 내는 `investigate()`를 120 LOT 전체에 실행합니다.
합성 데이터 기준이며 현장 진단 정확도를 뜻하지 않습니다.

실행: python -m src.investigation.benchmark
출력: docs/BENCHMARK.md, docs/benchmark.json
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from .core import investigate
from .demo import make_demo
from .scenarios import CASES

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_LOT = "DEMO-0046"


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def run(seed: int = 721) -> dict:
    data, _ = make_demo(seed=seed)
    lots = [lot["id"] for lot in data["lots"]]
    investigate(data, lots[0])  # 첫 호출 준비 시간 제외

    seconds: list[float] = []
    counts = {"runs": [], "aoi": [], "related": [], "signals": [], "candidates": []}
    failed_lots = 0
    for lot in lots:
        start = time.perf_counter()
        result = investigate(data, lot)
        seconds.append(time.perf_counter() - start)
        for key in counts:
            counts[key].append(len(result[key]))
        failed_lots += bool(result["summary"]["failed"])

    example = investigate(data, EXAMPLE_LOT)
    scenario_path = ROOT / "docs" / "scenario_validation.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))

    output = {
        "seed": seed,
        "lots": len(lots),
        "lots_with_failures": failed_lots,
        "seconds_median": statistics.median(seconds),
        "seconds_p95": _percentile(seconds, 0.95),
        "seconds_total": sum(seconds),
        "per_lot_median": {key: statistics.median(value) for key, value in counts.items()},
        "per_lot_max": {key: max(value) for key, value in counts.items()},
        "scenario_passed": scenario["passed"],
        "scenario_total": scenario["total"],
        "scenario_cases": len(CASES),
        "example": {
            "lot": EXAMPLE_LOT,
            "summary": example["summary"],
            "signals": [
                {k: s.get(k) for k in ("step", "factor", "value", "lower", "upper", "status")}
                for s in example["signals"]
            ],
            "candidates": [
                {"candidate": c["candidate"], "state": c["state"]}
                for c in example["candidates"]
            ],
        },
    }
    (ROOT / "docs" / "benchmark.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (ROOT / "docs" / "BENCHMARK.md").write_text(markdown(output), encoding="utf-8")
    print(
        f"LOT {output['lots']}개 조사: 중앙값 {output['seconds_median']:.2f}초, "
        f"p95 {output['seconds_p95']:.2f}초"
    )
    return output


def _cell(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3g}"
    return str(value)


def markdown(o: dict) -> str:
    median = o["per_lot_median"]
    maximum = o["per_lot_max"]
    example = o["example"]
    lines = [
        "# 업무 시나리오 측정",
        "",
        "`python -m src.investigation.benchmark`로 다시 만들 수 있습니다. "
        f"합성 데이터(seed {o['seed']}) 120 LOT 전체에 LOT 조사를 한 번씩 실행했습니다. "
        "실행 환경에 따라 시간은 달라지며, 수작업 소요 시간과 비교한 측정은 아닙니다.",
        "",
        "## LOT 하나를 조사할 때",
        "",
        "| 항목 | 중앙값 | 최대 |",
        "|---|---:|---:|",
        f"| 대조한 공정 이력 (설비 Run) | {median['runs']:g} | {maximum['runs']} |",
        f"| AOI 유닛 판정 | {median['aoi']:g} | {maximum['aoi']} |",
        f"| 동일 조건 비교 LOT | {median['related']:g} | {maximum['related']} |",
        f"| 기준 대비 판정한 공정 인자 | {median['signals']:g} | {maximum['signals']} |",
        f"| 원인 후보 | {median['candidates']:g} | {maximum['candidates']} |",
        f"| **소요 시간** | **{o['seconds_median']:.2f}초** | p95 {o['seconds_p95']:.2f}초 |",
        "",
        f"불량이 있는 LOT {o['lots_with_failures']}개를 포함해 120 LOT 전체 조사에 "
        f"{o['seconds_total']:.0f}초가 걸렸습니다.",
        "",
        "## 원인 후보가 기대한 방향으로 나오는가",
        "",
        f"원인 유형 {o['scenario_cases']}종 × 난수 조건 3종 = "
        f"{o['scenario_total']}건 중 **{o['scenario_passed']}건 통과** "
        "(`docs/scenario_validation.json`). 작성한 합성 시나리오에 대한 수용 검증이며, "
        "현장 원인 진단 정확도가 아닙니다.",
        "",
        f"## 사례: {example['lot']}",
        "",
        f"검사 {example['summary']['inspected']:,} PCS 중 불량 {example['summary']['failed']:,} PCS "
        f"({example['summary']['defect_rate']:.1%}).",
        "",
        "| 공정 | 인자 | 측정값 | 하한 | 상한 | 판정 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for s in example["signals"]:
        lines.append(
            f"| {s['step']} | {s['factor']} | {_cell(s['value'])} | {_cell(s['lower'])} "
            f"| {_cell(s['upper'])} | {s['status']} |"
        )
    lines += ["", "| 원인 후보 | 판단 |", "|---|---|"]
    lines += [f"| {c['candidate']} | {c['state']} |" for c in example["candidates"]]
    lines += [
        "",
        "'우선 확인'은 확인시험 순서를 정하는 표시입니다. 원인 확정이나 확률이 아닙니다.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    run()
