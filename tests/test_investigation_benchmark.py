from src.investigation.benchmark import _cell, _percentile, markdown


def _sample():
    return {
        "seed": 1, "lots": 2, "lots_with_failures": 1,
        "seconds_median": 0.5, "seconds_p95": 0.9, "seconds_total": 1.4,
        "per_lot_median": {"runs": 10, "aoi": 1600, "related": 70, "signals": 7, "candidates": 4},
        "per_lot_max": {"runs": 10, "aoi": 1600, "related": 75, "signals": 7, "candidates": 4},
        "scenario_passed": 27, "scenario_total": 27, "scenario_cases": 9,
        "example": {
            "lot": "DEMO-0046",
            "summary": {"inspected": 1600, "failed": 268, "defect_rate": 0.1675},
            "signals": [{"step": "CURE", "factor": "편차", "value": 8.123, "lower": None,
                         "upper": 4, "status": "OUTSIDE"}],
            "candidates": [{"candidate": "열처리", "state": "우선 확인"}],
        },
    }


def test_markdown_shows_missing_limits_as_dash_and_states_scope():
    text = markdown(_sample())
    assert "| CURE | 편차 | 8.12 | - | 4 | OUTSIDE |" in text
    assert "27건 통과" in text
    assert "현장 원인 진단 정확도가 아닙니다" in text
    assert "None" not in text


def test_helpers():
    assert _cell(None) == "-"
    assert _cell(0.123456) == "0.123"
    assert _percentile([1, 2, 3, 4, 5], 0.95) == 5
    assert _percentile([3.0], 0.5) == 3.0
