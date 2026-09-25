import copy
from datetime import datetime
import json
import pytest

from src.investigation.core import (aoi_summary, backup, coupon_index, fingerprint, investigate, report_html, restore, shift_at, ts, validate, validate_review)
from src.investigation.demo import make_demo


@pytest.fixture(scope="module")
def demo():
    return make_demo(detailed=False)


@pytest.mark.parametrize("before,after,ref,expected", [(10,9.5,.5,1), (10,9.6,.5,.8), (10,9,0,None), (10,11,1,None), (None,9,1,None), (10,9,float('nan'),None)])
def test_coupon(before, after, ref, expected):
    value = coupon_index(before, after, ref)
    if expected is None:
        assert value is None
    else:
        assert value == pytest.approx(expected)


@pytest.mark.parametrize("when,shift,start", [("2026-01-02T06:59:59+09:00","NIGHT","2026-01-01T19:00:00+09:00"), ("2026-01-02T07:00:00+09:00","DAY","2026-01-02T07:00:00+09:00"), ("2026-01-02T19:00:00+09:00","NIGHT","2026-01-02T19:00:00+09:00")])
def test_shift_boundary(when, shift, start):
    assert shift_at(when)["shift"] == shift
    assert shift_at(when)["start"] == start


def test_2400_different_length_tables_and_sequential_equipment(demo):
    d, truth = demo
    assert len(d["lots"]) == 120
    assert len(d["aoi"]) == 120*48*4
    assert len(d["runs"]) == 1200
    validate(d)
    assert all("abf_present" not in r for r in d["aoi"])
    assert any(t["abf_present"] and t["other_present"] for t in truth)


def test_tank_refill_reset_and_mix_models(demo):
    d, _ = demo
    rows = sorted([r for r in d["runs"] if r.get("tank") == "TANK-1"], key=lambda r: ts(r["start"]))
    assert rows[23]["refill"] is None
    assert rows[24]["refill"]
    assert rows[24]["since_refill_before"] == 0
    assert rows[47]["bath_lots_before"] == 47
    assert rows[48]["bath_lots_before"] == 0
    assert rows[48]["replacement"] != rows[47]["replacement"]
    e = next(e for e in d["tank_events"] if e["id"] == rows[24]["refill"])
    assert ts(e["end"]) <= ts(rows[24]["start"])
    assert (ts(e["end"])-ts(e["dosing_end"])).total_seconds() == 720


def test_first_code_is_not_abf_absence(demo):
    d, truth = demo
    a = {r["id"]: r for r in d["aoi"]}
    masked = [t for t in truth if t["abf_present"] and a[t["aoi_id"]]["code"] == "CIRCUIT"]
    assert masked
    r = a[masked[0]["aoi_id"]]
    s = aoi_summary([r])
    assert s["failed"] == 1 and s["abf_first"] == 0 and s["other_first_abf_unknown"] == 1


def test_no_cross_layer_denominator(demo):
    with pytest.raises(ValueError, match="한 층"):
        aoi_summary(demo[0]["aoi"][:193])


def test_same_model_controls_and_reasons(demo):
    d, _ = demo
    r = investigate(d, "DEMO-0045")
    assert r["summary"]["inspected"] == 48
    assert r["summary"]["abf_first"] > 0
    assert r["controls"]
    by_id = {x["id"]: x for x in d["lots"]}
    assert all(by_id[c["lot"]]["model"] == r["lot"]["model"] for c in r["controls"])
    assert any("동일 탱크·전체 교체 구간" in x["reasons"] for x in r["related"])
    assert r["candidates"][0]["state"] == "우선 확인"


def test_time_cutoff_hides_future_measurements(demo):
    d, _ = demo
    start = d["lots"][44]["start"]
    r = investigate(d, "DEMO-0045", as_of=start)
    assert r["runs"] == [] and r["aoi"] == [] and r["confirmations"] == []
    assert all(ts(next(b for b in d["lots"] if b["id"] == c["lot"])["end"]) <= ts(start) for c in r["controls"])


def test_missing_is_not_normal(demo):
    r = investigate(demo[0], "DEMO-0066")
    assert any(s["factor"].startswith("Cu") and s["status"] == "MISSING" for s in r["signals"])
    assert r["candidates"][0]["state"] == "판단 보류"


@pytest.mark.parametrize("change", ["duplicate", "orphan", "overlap", "unit", "date", "coordinate"])
def test_bad_data_rejected(demo, change):
    d = copy.deepcopy(demo[0])
    if change == "duplicate":
        d["aoi"].append({**d["aoi"][0], "id": "UNIQUE-BUT-DUPLICATE-UNIT"})
    elif change == "orphan":
        d["runs"][0]["lot"] = "UNKNOWN"
    elif change == "overlap":
        d["runs"].append({**d["runs"][0], "id": "OVERLAP"})
    elif change == "unit":
        d["runs"][0]["parameters"]["Cu 시편 무게 감소 정규화 지수"]["unit"] = ""
    elif change == "date":
        d["runs"][0]["start"] = "2026-01-01T00:00:00"
    else:
        d["aoi"][0]["x"] = 5
    with pytest.raises((ValueError, TypeError)):
        validate(d)


def test_restore_is_atomic_and_idempotent():
    e = {"id": "R1", "lot": "L1", "saved": "2026-01-01T07:00:00+09:00", "owner": "A", "state": "진행 중", "result": "", "evidence": "", "data_hash": "X"}
    assert restore([e], backup([e])) == [e]
    original = [e]
    with pytest.raises(ValueError, match="충돌"):
        restore(original, backup([{**e, "owner": "B"}]))
    assert original == [e]
    bad = backup([e]); bad["payload"] += " "
    with pytest.raises(ValueError, match="손상"):
        restore([], bad)
    with pytest.raises(ValueError, match="검증 완료"):
        validate_review({**e, "state": "검증 완료"})


def test_report_escapes_input_and_keeps_scope(demo):
    r = investigate(demo[0], "DEMO-0045")
    text = report_html(r, {"result": "<script>alert('x')</script>"})
    assert "<script>alert('x')" not in text and "&lt;script&gt;" in text
    assert r["data_hash"] in text and "contenteditable" in text


def test_independent_handcrafted_aoi_counts():
    rows = [{"code": code, "layer": 1, "side": "TOP", "inspection": 1} for code in ["ABF", "CIRCUIT", "PASS", "DENT"]]
    assert aoi_summary(rows) == {"inspected":4,"failed":3,"abf_first":1,"other_first_abf_unknown":2,"defect_rate":.75,"abf_first_rate":.25}
