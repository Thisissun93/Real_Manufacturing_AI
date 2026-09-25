"""Independent public synthetic fixture; private factory conditions are not encoded.

Truth is intentionally separated from observable AOI and never used by investigation.
"""
from datetime import datetime, timedelta
import random
import math
from .core import FORMAT, KST, coupon_index, validate


def temperature_profile(minutes, zone_count, abnormal=False):
    seconds = int(round(minutes*60))
    setpoints = [round(32+110*math.sin(math.pi*(z+.5)/zone_count)**.75,1) for z in range(zone_count)]
    zones = [{'zone':z+1,'start_s':round(z*seconds/zone_count),'end_s':round((z+1)*seconds/zone_count),'setpoint_c':v} for z,v in enumerate(setpoints)]
    values, reference = [], []
    baseline = actual = 26.0
    for t in range(seconds+1):
        z = min(zone_count-1, int(t*zone_count/seconds))
        baseline += (setpoints[z]-baseline)/45
        offset = 8 if abnormal and zone_count//3 <= z < zone_count-2 else 0
        actual += (setpoints[z]+offset-actual)/45
        values.append(round(actual+.12*math.sin(t/17),2))
        reference.append(round(baseline,2))
    return {'elapsed_s':list(range(seconds+1)), 'temperature_c':values, 'reference_c':reference, 'zones':zones, 'sample_interval_s':1, 'tolerance_c':4, 'tolerance_basis':'시연용 기준 ±4°C'}


def make_demo(count=120, seed=721, detailed=True):
    rng = random.Random(seed)
    data = {"format": FORMAT, "origin": "SYNTHETIC", "config": {"refill_every": 24, "replace_every": 48, "refill_idle_min": 12,
            "prebake_zones": 11, "cure_zones": 13, "prebake_min": 36, "cure_min": 54,
            "notice": "공개용 독립 시나리오. 양산 조건/수율을 재현하지 않음.",
            "aoi_policy": "전체 스캔·최초 대표 코드 저장: 사용자 설명에 따른 미검증 가정"},
            "lots": [], "runs": [], "tank_events": [], "aoi": [], "confirmations": [], "inspection_groups": []}
    truth = []
    base = datetime(2026, 1, 1, 7, tzinfo=KST)
    iso = lambda dt: dt.isoformat()
    p = lambda value, unit, lower=None, upper=None, target=None: {"value": value, "unit": unit, "lower": lower, "upper": upper, "target": target, "basis": "PUBLIC-SIM-1"}
    events = set()
    for i in range(count):
        lane, seq = i % 2+1, i//2
        lot_id = f"DEMO-{i+1:04d}"
        model = "MODEL-A" if seq % 3 else "MODEL-B"
        nr, nc, size = (20,20,12) if model=='MODEL-A' else (14,14,17)
        if not detailed:
            nr,nc=4,3
        layout = {'rows':nr,'columns':nc,'unit_width_mm':size,'unit_height_mm':size,'pcs_per_quad':nr*nc}
        start = base+timedelta(minutes=seq*360)
        cycle, age = seq//48, seq%48
        bath = f"TANK-{lane}-C{cycle}"
        replacement = f"REPLACE-{lane}-{cycle}"
        if replacement not in events:
            end = base+timedelta(minutes=(seq-age)*360-1)
            data["tank_events"].append({"id": replacement, "tank": f"TANK-{lane}", "type": "REPLACE", "cycle": bath,
                                        "start": iso(end-timedelta(minutes=30)), "end": iso(end), "available_at": iso(end), "quantity": None, "quantity_unit": "L"})
            events.add(replacement)
        refill = None
        if age >= 24:
            refill = f"REFILL-{lane}-{cycle}"
            if refill not in events:
                end = base+timedelta(minutes=(seq-age+24)*360-1)
                data["tank_events"].append({"id": refill, "tank": f"TANK-{lane}", "type": "REFILL", "cycle": bath,
                    "start": iso(end-timedelta(minutes=14)), "dosing_end": iso(end-timedelta(minutes=12)), "end": iso(end),
                    "available_at": iso(end), "quantity": 2.5, "quantity_unit": "L"})
                events.add(refill)
        # Tank 1 drift before first refill; refill improves synthetic response, not a causal proof.
        drift = lane == 1 and cycle == 0 and 16 <= age < 24
        thermal = lane == 2 and 20 <= seq < 27
        sensor = lane == 1 and 34 <= seq < 37
        missing = lane == 2 and seq == 32
        scenario = "TANK_DRIFT" if drift else "THERMAL" if thermal else "SENSOR_BIAS" if sensor else "MISSING" if missing else "BASELINE"
        observed_index = 0.70 + (0.28 if drift or sensor else 0) + rng.uniform(-.035, .035)
        index = None if missing else round(observed_index, 5)
        duration = [("CZ", 16), ("PREBAKE", 36), ("LAMINATION", 7), ("CURE", 54), ("LASER", 14), ("DESMEAR", 18), ("PLATING", 28), ("PATTERN", 22), ("HIGH_BAKE", 120), ("AOI", 12)]
        duration = [(step, 120 if step=="HIGH_BAKE" else round(m*(1.25 if drift and step=='CZ' else .86 if thermal and step=='CURE' else 1)+rng.uniform(-.18,.18),2)) for step,m in duration]
        end = start+timedelta(minutes=sum(d for _, d in duration)+2*(len(duration)-1))
        data["lots"].append({"id": lot_id, "model": model, "recipe": model+"-R1", "film": model+"-FILM", "material": f"FILM-{model}-{seq//24}",
                             "start": iso(start), "end": iso(end), "expected_units": 4*nr*nc, "layout":layout, "panel_layout": "1 Panel / Quad A·B·C·D"})
        cursor = start
        for step, minutes in duration:
            finish = cursor+timedelta(minutes=minutes)
            params = {}
            if step == "CZ":
                before, ref = 12.0, .025
                after = None if index is None else round(before-index*ref, 7)
                params = {"Cu 시편 무게 감소 정규화 지수": p(coupon_index(before, after, ref), "1", .55, .85, .70),
                          "순수 저항계 표시값": p(round(rng.uniform(.65,.95) if drift else rng.uniform(1.4,8.5),3), "MΩ", 1, None, None)}
            if step in ("PREBAKE", "CURE"):
                zones = 11 if step == "PREBAKE" else 13
                profile = temperature_profile(minutes,zones,thermal and step=='CURE')
                params["제품 온도프로파일 기준대비 최대 편차"] = p(round(max(abs(a-b) for a,b in zip(profile['temperature_c'],profile['reference_c'])),2), "°C", None, 4, 0)
            if step == "HIGH_BAKE":
                from .thermal import high_bake_profile
                profile=high_bake_profile(190 if model=='MODEL-A' else 200,lot_id=='DEMO-0046')
                params["제품 온도프로파일 기준대비 최대 편차"] = p(round(max(abs(a-b) for a,b in zip(profile['temperature_c'],profile['reference_c'])),2), "°C", None, 4, 0)
            if step == "LAMINATION":
                params["압력 설정 대비 실측 편차"] = p(rng.uniform(-1, 1), "%", -4, 4, 0)
            row = {"id": lot_id+"-"+step, "lot": lot_id, "step": step, "equipment": f"{step}-{lane}",
                   "start": iso(cursor), "end": iso(finish), "available_at": iso(finish), "parameters": params}
            if step == "CZ":
                row.update(tank=f"TANK-{lane}", cycle=bath, replacement=replacement, refill=refill, bath_lots_before=age,
                           since_refill_before=age%24, coupon={"before": before, "after": after, "reference": ref, "mass_unit": "g"})
            if step in ("PREBAKE", "CURE", "HIGH_BAKE"):
                row["profile"] = profile
            data["runs"].append(row)
            cursor = finish+timedelta(minutes=2)
        for layer in (1, 2):
            for side in ("TOP", "BOTTOM"):
                group = {'id':f'{lot_id}-L{layer}-{side}', 'lot':lot_id,'panel':'P1','layer':layer,'side':side,'inspection':1,
                         'time':iso(end+timedelta(minutes=layer)),'rows':nr,'columns':nc,'codes':[],'locations':{}}
                for q in range(1, 5):
                    for u in range(1, nr*nc+1):
                        x, y = ((u-1)%nc+.5)/nc, ((u-1)//nc+.5)/nr
                        risk = (.26 if drift else .18 if thermal else 0)
                        abf = rng.random() < risk*(1.3 if x < .2 or x > .8 else .7)
                        other = rng.random() < (.10 if seq%9 == 0 else 0)
                        # Explicit multi-defect fixture for first-code masking regression.
                        if drift and q == 1 and u == 2:
                            abf, other = True, True
                        # Synthetic rank captures masking without storing additional AOI codes.
                        code = "CIRCUIT" if other and (not abf or u%2 == 0) else "ABF" if abf else "PASS"
                        aoi = {"id": f"{lot_id}-L{layer}-{side}-Q{q}-U{u}", "lot": lot_id, "panel": "P1", "quad": q, "unit": u,
                               "layer": layer, "side": side, "inspection": 1, "code": code, "time": iso(end+timedelta(minutes=layer)), "x": x, "y": y}
                        group['codes'].append(code)
                        if code != 'PASS':
                            loc_rng = random.Random(f'{seed}:{aoi["id"]}')
                            group['locations'][str((q-1)*nr*nc+u-1)] = {'x':round(loc_rng.uniform(.05,.95),4),'y':round(loc_rng.uniform(.05,.95),4)}
                        if not detailed:
                            data["aoi"].append(aoi)
                        if abf or other:
                            truth.append({"aoi_id": aoi["id"], "abf_present": abf, "other_present": other, "scenario": scenario, 'representative_code':code})
                        if abf and q == 1 and u%3 == 0 and u<=12 and layer == 1 and side == "TOP":
                            data["confirmations"].append({"id": "SEC-"+aoi["id"], "lot": lot_id, "panel": "P1", "quad": q, "unit": u,
                                "layer": layer, "side": side, "time": iso(end+timedelta(hours=3)), "method": "단면", "abf_confirmed": True, "interface": "FILM/Cu", "selection": "의심 유닛 선택 검사: 전체 대표성 없음"})
                if detailed:
                    data['inspection_groups'].append(group)
    if detailed:
        from .scenarios import apply_scenarios
        apply_scenarios(data,seed,truth)
        from .materials import add_demo_materials
        add_demo_materials(data)
        # Explicit public trend scenario: current values remain within limits; no future defects are invented.
        selected_lots={r['id'] for r in data['lots'] if r['model']=='MODEL-A'}
        trend_runs=sorted([r for r in data['runs'] if r['equipment']=='LAMINATION-2' and r['lot'] in selected_lots],key=lambda r:r['start'])[-8:]
        for n,run in enumerate(trend_runs):
            run['parameters']['압력 설정 대비 실측 편차']['value']=round(.6+.38*n,3)
    validate(data)
    return data, truth


if __name__ == "__main__":
    import json
    from pathlib import Path
    d, truth = make_demo()
    out = Path(__file__).resolve().parents[2]/"samples"/"investigation"
    out.mkdir(parents=True, exist_ok=True)
    (out/"demo.json").write_text(json.dumps(d, ensure_ascii=False, separators=(',',':')), encoding="utf-8")
    (out/"evaluation_truth.json").write_text(json.dumps(truth, ensure_ascii=False), encoding="utf-8")
    print("Public synthetic data generated:", len(d["lots"]), "lots;", sum(len(g['codes']) for g in d['inspection_groups'])+len(d['aoi']), "AOI inspection records")
