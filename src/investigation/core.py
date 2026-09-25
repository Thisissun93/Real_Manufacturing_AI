"""Pure, testable investigation rules. All public limits are simulation settings."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import html
import json
import math
from statistics import median

VERSION = "1.0"
KST = timezone(timedelta(hours=9))
FORMAT = "MANUFACTURING-INVESTIGATION-1"
ROUTE = ["CZ", "PREBAKE", "LAMINATION", "CURE", "LASER", "DESMEAR", "PLATING", "PATTERN", "HIGH_BAKE", "AOI"]


def ts(value):
    if not isinstance(value, str):
        raise ValueError("시각은 시간대가 포함된 문자열이어야 합니다.")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("시각에는 시간대가 필요합니다.")
    return d


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def coupon_index(before, after, reference):
    if not all(finite(v) for v in (before, after, reference)):
        return None
    if reference <= 0 or before <= 0 or after < 0 or after > before:
        return None
    return (before - after) / reference


def shift_at(value):
    d = ts(value).astimezone(KST)
    start = d.replace(hour=7 if 7 <= d.hour < 19 else 19, minute=0, second=0, microsecond=0)
    if d.hour < 7:
        start -= timedelta(days=1)
    return {"shift": "DAY" if start.hour == 7 else "NIGHT", "start": start.isoformat(), "end": (start + timedelta(hours=12)).isoformat()}


def fingerprint(data):
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate(data):
    """Reject invalid links and ambiguous duplicates before applying any analysis."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("지원하지 않는 조사 데이터 형식입니다.")
    required = {
        "lots": ["id", "model", "recipe", "material", "start", "end"],
        "runs": ["id", "lot", "step", "equipment", "start", "end", "available_at", "parameters"],
        "tank_events": ["id", "tank", "type", "start", "end", "cycle", "available_at"],
        "aoi": ["id", "lot", "panel", "quad", "unit", "layer", "side", "inspection", "code", "time", "x", "y"],
        "confirmations": ["id", "lot", "panel", "quad", "unit", "layer", "side", "time", "method", "abf_confirmed"],
    }
    for table, fields in required.items():
        rows = data.get(table)
        if not isinstance(rows, list) or len(rows) > 100000:
            raise ValueError(f"{table}: 배열 형식 및 100,000행 제한을 확인하세요.")
        seen = set()
        for r in rows:
            if not isinstance(r, dict) or any(k not in r or r[k] is None for k in fields):
                raise ValueError(f"{table}: 필수 열/값 누락")
            if not isinstance(r["id"], str) or not r["id"] or r["id"] in seen:
                raise ValueError(f"{table}: 기록 ID 중복 또는 누락")
            seen.add(r["id"])
            for k in ("start", "end", "time", "available_at"):
                if k in r:
                    ts(r[k])
            if "end" in r and ts(r["end"]) <= ts(r["start"]):
                raise ValueError(f"{table}: 종료 시각 오류")
            if "available_at" in r and ts(r["available_at"]) < ts(r["end"]):
                raise ValueError(f"{table}: 완료 전 기록 확정 오류")
    lots = {r["id"]: r for r in data["lots"]}
    if not lots:
        raise ValueError("LOT가 없습니다.")
    for name in ("model", "recipe", "material"):
        if any(not isinstance(r[name], str) or not r[name] for r in lots.values()):
            raise ValueError(f"LOT {name} 누락")
    for table in ("runs", "aoi", "confirmations"):
        for r in data[table]:
            if r["lot"] not in lots:
                raise ValueError(f"{table}: 존재하지 않는 LOT 연결")
    unique = set()
    from .records import validate_groups
    groups = validate_groups(data, lots)
    group_lookup = {(g['lot'],g['panel'],g['layer'],g['side']):g for g in groups}
    legacy_lookup = {tuple(a[k] for k in ('lot','panel','quad','unit','layer','side')):a for a in data['aoi']}
    for r in data["aoi"]:
        if not isinstance(r["quad"], int) or isinstance(r["quad"], bool) or r["quad"] not in range(1, 5):
            raise ValueError("Quad는 1~4여야 합니다.")
        if ts(r["time"]) < ts(lots[r["lot"]]["start"]):
            raise ValueError("AOI 시각이 LOT 시작보다 빠릅니다.")
        key = tuple(r[k] for k in ("lot", "panel", "quad", "unit", "layer", "side", "inspection"))
        if key in unique:
            raise ValueError("AOI: 동일 유닛·층·면·검사 회차 중복")
        unique.add(key)
        if r["code"] not in ("PASS", "ABF", "CIRCUIT", "DENT", "OTHER") or r["side"] not in ("TOP", "BOTTOM"):
            raise ValueError("AOI 코드/면 오류")
        if not all(finite(r[k]) and 0 <= r[k] <= 1 for k in ("x", "y")):
            raise ValueError("AOI 좌표는 Quad 내 0~1 정규화 좌표여야 합니다.")
    for r in data["confirmations"]:
        if not isinstance(r["abf_confirmed"], bool):
            raise ValueError("확정 결과는 true/false여야 합니다.")
        a = legacy_lookup.get(tuple(r[k] for k in ('lot','panel','quad','unit','layer','side')))
        g = group_lookup.get(tuple(r[k] for k in ('lot','panel','layer','side')))
        valid_group = g is not None and 1<=r['quad']<=4 and 1<=r['unit']<=g['rows']*g['columns'] and ts(g['time'])<=ts(r['time'])
        if not valid_group and not (a and ts(a['time'])<=ts(r['time'])):
            raise ValueError("추가 분석의 검사 유닛 연결 오류")
    equipment = {}
    events = {r["id"]: r for r in data["tank_events"]}
    for r in data["runs"]:
        profile = r.get('profile')
        if isinstance(profile,dict):
            tolerance=profile.get('tolerance_c')
            if tolerance is not None and (not finite(tolerance) or tolerance<=0):
                raise ValueError('제품 온도 허용 편차는 양의 유한값이어야 합니다.')
            times, temps, refs = (profile.get(k,[]) for k in ('elapsed_s','temperature_c','reference_c'))
            if not times or len(times)!=len(temps) or len(times)!=len(refs) or len(times)>100000:
                raise ValueError('온도프로파일 표본 수 오류')
            if not all(finite(v) for v in times+temps+refs) or times[0]!=0 or any(b<=a for a,b in zip(times,times[1:])):
                raise ValueError('온도프로파일 값/시간 순서 오류')
            duration=(ts(r['end'])-ts(r['start'])).total_seconds()
            if abs(times[-1]-duration)>1:
                raise ValueError('온도프로파일과 공정 소요 시간 불일치')
            zones=profile.get('zones',[])
            if not zones or zones[0]['start_s']!=0 or zones[-1]['end_s']!=times[-1] or any(a['end_s']!=b['start_s'] for a,b in zip(zones,zones[1:])):
                raise ValueError('Zone 시간 구간 연결 오류')
        if not isinstance(r["parameters"], dict):
            raise ValueError("공정 측정값 형식 오류")
        for p in r["parameters"].values():
            if not isinstance(p, dict) or "value" not in p or not p.get("unit") or not p.get("basis"):
                raise ValueError("공정 인자 값·단위·근거 누락")
            if p["value"] is not None and not finite(p["value"]):
                raise ValueError("공정 측정값 숫자 오류")
            for limit in ("lower", "upper", "target"):
                if p.get(limit) is not None and not finite(p[limit]):
                    raise ValueError("기준값 숫자 오류")
            if p.get("lower") is not None and p.get("upper") is not None and p["lower"] >= p["upper"]:
                raise ValueError("하한/상한 역전")
        lot = lots[r["lot"]]
        if ts(r["start"]) < ts(lot["start"]) or ts(r["end"]) > ts(lot["end"]):
            raise ValueError("공정 시간이 LOT 범위 밖입니다.")
        equipment.setdefault(r["equipment"], []).append(r)
        for key, expected in (("replacement", "REPLACE"), ("refill", "REFILL")):
            if r.get(key):
                e = events.get(r[key])
                if not e or e["tank"] != r.get("tank") or e["cycle"] != r.get("cycle") or e["type"] != expected or ts(e["end"]) > ts(r["start"]):
                    raise ValueError("탱크 교체/보충 연결 또는 공회전 종료 시각 오류")
    for rows in equipment.values():
        rows.sort(key=lambda r: ts(r["start"]))
        for a, b in zip(rows, rows[1:]):
            if ts(a["end"]) > ts(b["start"]):
                raise ValueError("설비 처리 시간 중복: 한 설비 한 LOT 가정 위반")
    from .materials import validate_materials
    validate_materials(data)
    from .maintenance import validate_maintenance
    validate_maintenance(data)
    return data


def summary_text(result):
    s = result["summary"]
    if not s["inspected"]:
        return "선택한 시점·층·면·회차에 검사 기록이 없어 불량률과 원인 판단을 보류합니다."
    outside = [x for x in result["signals"] if x["status"] == "OUTSIDE"]
    text = f"검사 {s['inspected']} PCS 중 불량 {s['failed']} PCS({s['defect_rate']:.1%})이며, ABF가 대표 코드인 유닛은 {s['abf_first']} PCS입니다. "
    text += ("등록 기준 이탈: " + ", ".join(x["step"]+" / "+x["factor"] for x in outside) + ". 관련 계측값과 전후 이력을 우선 확인하세요. ") if outside else "확보된 측정값에서 등록 기준 이탈이 확인되지 않았습니다. 미수집 인자는 별도 확인이 필요합니다. "
    if s["other_first_abf_unknown"]:
        text += f"다른 코드로 집계된 {s['other_first_abf_unknown']} PCS의 ABF 동반 여부는 알 수 없습니다. "
    return text + "현재 결과만으로 특정 공정·자재를 근본 원인으로 확정할 수 없습니다."


def aoi_summary(rows):
    """Caller chooses one layer/side/inspection; never silently double-count."""
    if len({(r["layer"], r["side"], r["inspection"]) for r in rows}) > 1:
        raise ValueError("불량률은 한 층·면·검사 회차를 선택해 계산하세요.")
    n = len(rows)
    failed = sum(r["code"] != "PASS" for r in rows)
    abf = sum(r["code"] == "ABF" for r in rows)
    return {"inspected": n, "failed": failed, "abf_first": abf, "other_first_abf_unknown": failed-abf,
            "defect_rate": failed/n if n else None, "abf_first_rate": abf/n if n else None}


def investigate(data, lot_id, layer=1, side="TOP", inspection=1, as_of=None):
    from .records import inspection_rows, inspection_summary
    lots = {r["id"]: r for r in data["lots"]}
    if lot_id not in lots:
        raise ValueError("LOT를 찾을 수 없습니다.")
    selected = lots[lot_id]
    now = ts(as_of) if as_of else max((ts(r["time"]) for r in data["aoi"]+data.get('inspection_groups',[])), default=ts(selected["end"]))
    runs = [r for r in data["runs"] if ts(r["available_at"]) <= now]
    own = sorted([r for r in runs if r["lot"] == lot_id], key=lambda r: ts(r["start"]))
    rows = inspection_rows(data,lot_id,layer,side,inspection,now.isoformat())
    status = aoi_summary(rows)
    signals = []
    for r in own:
        for name, p in r["parameters"].items():
            v, lo, hi = p.get("value"), p.get("lower"), p.get("upper")
            kind = "MISSING" if v is None else "OUTSIDE" if (lo is not None and v < lo) or (hi is not None and v > hi) else "WITHIN" if lo is not None or hi is not None else "NO_LIMIT"
            signals.append({"record": r["id"], "step": r["step"], "factor": name, "value": v, "unit": p["unit"], "lower": lo, "upper": hi, "target": p.get("target"), "status": kind, "basis": p["basis"]})
    own_tanks = {(r.get("tank"), r.get("cycle")) for r in own if r.get("tank")}
    own_eq = {(r["step"], r["equipment"]) for r in own}
    related, controls, exclusions = [], [], Counter()
    for other_id, other in lots.items():
        if other_id == lot_id or ts(other["start"]) > now:
            continue
        rr = [r for r in runs if r["lot"] == other_id]
        summary = inspection_summary(data,other_id,layer,side,inspection,now.isoformat())
        reasons = []
        if other["material"] == selected["material"]:
            reasons.append("동일 자재 LOT")
        shared_tank = [r for r in rr if (r.get("tank"), r.get("cycle")) in own_tanks]
        if shared_tank:
            reasons.append("동일 탱크·전체 교체 구간")
        shared = [r for r in rr if (r["step"], r["equipment"]) in own_eq]
        if shared:
            reasons.append("동일 공정 설비")
        entry = {"lot": other_id, "model": other["model"], "reasons": reasons, **summary,
                 "records": [r["id"] for r in shared_tank+shared]}
        if reasons:
            related.append(entry)
        if other["model"] != selected["model"]:
            exclusions["다른 모델"] += 1
        elif other["recipe"] != selected["recipe"]:
            exclusions["다른 공정 개정"] += 1
        elif summary["inspected"] != selected.get("expected_units") or summary["inspected"] == 0:
            exclusions["검사 수량 불완전/미확보"] += 1
        elif summary["failed"]:
            exclusions["AOI 불량 포함"] += 1
        else:
            controls.append({"lot": other_id, "reason": "동일 모델·개정, 선택 층/면/회차 전수 AOI PASS", "inspected": summary["inspected"], "material": other["material"]})
    control_ids = {c["lot"] for c in controls}
    durations = []
    for r in own:
        ref = [x for x in runs if x['lot'] in control_ids and x['step']==r['step']]
        # Compare one summed duration per LOT when a step has multiple records.
        totals = {}
        for x in ref:
            totals[x['lot']] = totals.get(x['lot'],0)+(ts(x['end'])-ts(x['start'])).total_seconds()/60
        actual = sum((ts(x['end'])-ts(x['start'])).total_seconds()/60 for x in own if x['step']==r['step'])
        if any(x['step']==r['step'] for x in durations):
            continue
        values = list(totals.values())
        mid = median(values) if values else None
        durations.append({'step':r['step'],'actual_min':actual,'normal_n':len(values),'normal_median_min':mid,
                          'normal_min':min(values) if values else None,'normal_max':max(values) if values else None,
                          'difference_min':actual-mid if mid is not None else None,
                          'difference_pct':100*(actual-mid)/mid if mid else None,
                          'comparison':'비교군 부족' if len(values)<3 else '정상 관측 범위보다 김' if actual>max(values) else '정상 관측 범위보다 짧음' if actual<min(values) else '정상 관측 범위 이내'})
    candidates = []
    groups = [("약액 상태 또는 계측 이상", ["CZ"], "동일 조건 Cu 시편 반복 측정, 저울·기준 무게 확인, 보충·교체 전후 비교"),
              ("적층 조건 또는 자재 상태", ["LAMINATION"], "설비 실측값·SUS Plate 점검, 동일 자재의 다른 설비 LOT 대조"),
              ("열처리 조건 또는 온도 전달 차이", ["PREBAKE", "CURE", "HIGH_BAKE"], "설정값과 실측 제품 프로파일 비교, 측정기 점검 및 동일 조건 재현 시험")]
    for name, steps, action in groups:
        support = [s for s in signals if s["step"] in steps and s["status"] == "OUTSIDE"]
        missing = [s["factor"] for s in signals if s["step"] in steps and s["status"] == "MISSING"]
        missing.extend(s+" 공정 기록 없음" for s in steps if not any(r["step"] == s for r in own))
        same_exposure = sorted({r["lot"] for r in runs if r["lot"] in control_ids and r["step"] in steps and ((r.get("tank"), r.get("cycle")) in own_tanks if steps == ["CZ"] else (r["step"], r["equipment"]) in own_eq)})
        candidates.append({"candidate": name, "state": "우선 확인" if support else "판단 보류" if missing else "현재 등록값에서 이탈 근거 없음",
                           "support": [s["record"]+" / "+s["factor"] for s in support],
                           "counter": same_exposure, "missing": missing,
                           "next_action": action, "limitation": "연관성만으로 원인 확정 불가. AOI PASS도 잠재 계면 결함 부재를 보증하지 않음."})
    material_peers=[p for p in related if '동일 자재 LOT' in p['reasons'] and p['model']==selected['model'] and lots[p['lot']]['recipe']==selected['recipe'] and p['abf_first']>0]
    material_lots={lot_id}|{p['lot'] for p in material_peers}
    material_equipment={r['equipment'] for r in runs if r['lot'] in material_lots and r['step']=='LAMINATION'}
    material_signal=status['abf_first']>0 and bool(material_peers) and len(material_equipment)>1
    candidates.append({'candidate':'자재 공유 이력','state':'우선 확인' if material_signal else '현재 등록값에서 이탈 근거 없음',
                       'support':[p['lot']+' / 동일 자재·다른 설비 대조 필요' for p in material_peers] if material_signal else [],
                       'counter':[c['lot'] for c in controls if c['material']==selected['material']], 'missing':[],
                       'next_action':'같은 모델에서 자재 LOT와 설비를 교차 비교하고 보관·해동 이력 및 선택 유닛 단면 결과를 확인',
                       'limitation':'동일 자재를 공유한 불량 분포는 관찰 근거이며 자재 원인 확정이 아님.'})
    confirmations = [r for r in data["confirmations"] if r["lot"] == lot_id and r["layer"] == layer and r["side"] == side and ts(r["time"]) <= now]
    warnings = []
    missing_steps = [s for s in ROUTE if s not in {r["step"] for r in own}]
    if missing_steps:
        warnings.append("조회 시점에 확보되지 않은 공정: " + ", ".join(missing_steps))
    if status["inspected"] != selected.get("expected_units"):
        warnings.append("선택 검사 범위의 예상 수량과 기록 수가 다릅니다. 전수 검사 결과로 해석하지 마세요.")
    if not controls:
        warnings.append("정상 비교 LOT가 없습니다. 기준을 완화해 자동 대체하지 않았습니다.")
    warnings.append("다른 대표 불량 유닛의 ABF 동반 여부는 미확인입니다. 아래 비율은 실제 ABF 존재율이 아닙니다.")
    if status['inspected'] and not status['failed'] and any(s['status']=='OUTSIDE' for s in signals):
        warnings.append('조건 이탈이 있지만 선택 검사 범위는 AOI PASS입니다. 이탈을 불량 원인으로 자동 해석하지 마세요.')
    if status['abf_first'] and not any(s['status']=='OUTSIDE' for s in signals):
        warnings.append('등록값이 기준 이내인데 ABF 대표 불량이 있습니다. 미수집 인자·국부 조건·자재와 추가 분석을 확인하세요.')
    from .materials import assess
    material_assessment=assess(data,lot_id,now.isoformat())
    from .maintenance import recommendations
    maintenance_checks=recommendations(data,own)
    due=[r for r in maintenance_checks if any(s in r['판정'] for s in ('초과','도달','임박'))]
    if due:
        candidates.append({'candidate':'설비 부품 교체·교정 기한 검토','state':'우선 확인',
                           'support':[r['설비']+' / '+r['점검 대상']+' / '+r['판정'] for r in due],
                           'counter':[],'missing':['기한 도래 시점의 부품 실측 상태·정비 결과'],
                           'next_action':'적용 매뉴얼과 실제 사용시간을 대조하고, 부품 상태 및 정비 전후 제품 결과를 확인하세요.',
                           'limitation':'기한 초과·임박은 관리 신호이며 고장 또는 불량 원인 확정이 아닙니다.'})
    if material_assessment['status']=='이탈 확인':
        candidates.append({'candidate':'지정 자재 또는 취급 순서 이상','state':'우선 확인',
                           'support':material_assessment['issues'],'counter':[], 'missing':[],
                           'next_action':'자재 개체·냉동/냉장/해동 시각을 대조하고 Pore·Void 의심 부위를 단면 확인하세요.',
                           'limitation':'취급 이탈만으로 Pore·Void 발생이나 원인을 확정하지 않습니다.'})
    return {"lot": selected, "as_of": now.isoformat(), "selection": {"layer": layer, "side": side, "inspection": inspection},
            'material_assessment':material_assessment,
            'maintenance_recommendations':maintenance_checks,
            "data_hash": fingerprint(data), "summary": status, "runs": own, "aoi": rows, "signals": signals,
            "related": related, "controls": controls, "exclusions": dict(exclusions), "candidates": candidates,
            "confirmations": confirmations, "warnings": warnings, 'durations':durations}


def report_html(result, review=None):
    from .reporting import build_report
    return build_report(result, review)


def validate_review(entry):
    if isinstance(entry,dict) and entry.get('effectiveness') is not None:
        from .scenarios import effectiveness
        effectiveness(entry['effectiveness'])
    if isinstance(entry,dict) and 'tests' in entry:
        from .scenarios import validate_tests
        validate_tests(entry['tests'])
    if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) for k in ("id", "lot", "saved", "owner", "state", "result", "evidence", "data_hash")):
        raise ValueError("검토 기록 필수값 오류")
    ts(entry["saved"])
    if not entry["id"] or entry["state"] not in ("제안", "진행 중", "검증 완료"):
        raise ValueError("검토 ID/상태 오류")
    if entry["state"] == "검증 완료" and not all(entry[k].strip() for k in ("owner", "result", "evidence")):
        raise ValueError("검증 완료에는 담당자·실제 결과·증거/검토자가 필요합니다.")
    if entry['state']=='검증 완료' and 'tests' in entry and not entry['tests']:
        raise ValueError('검증 완료에는 실제 확인시험 기록을 포함해야 합니다.')
    return entry


def backup(records):
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return {"format": "MANUFACTURING-REVIEW-BACKUP-1", "payload": payload, "sha256": sha256(payload.encode()).hexdigest()}


def restore(existing, package):
    if not isinstance(package, dict) or package.get("format") != "MANUFACTURING-REVIEW-BACKUP-1" or not isinstance(package.get("payload"), str):
        raise ValueError("백업 형식 오류")
    if sha256(package["payload"].encode()).hexdigest() != package.get("sha256"):
        raise ValueError("백업 손상 검사 실패")
    incoming = json.loads(package["payload"])
    if not isinstance(incoming, list) or len(incoming) > 10000:
        raise ValueError("백업 기록 수/형식 오류")
    merged = {r["id"]: r for r in existing}
    for r in incoming:
        validate_review(r)
        if r["id"] in merged and merged[r["id"]] != r:
            raise ValueError("동일 ID의 내용 충돌. 복원하지 않았습니다.")
        merged[r["id"]] = r
    return list(merged.values())
