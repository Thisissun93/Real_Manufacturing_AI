"""Compact complete inspection storage; PASS is explicit, never inferred from absence."""
from .core import ts, aoi_summary, finite


def inspection_groups(data, lot=None, layer=None, side=None, inspection=None, as_of=None):
    return [g for g in data.get('inspection_groups', []) if
            (lot is None or g['lot'] == lot) and (layer is None or g['layer'] == layer) and
            (side is None or g['side'] == side) and (inspection is None or g['inspection'] == inspection) and
            (as_of is None or ts(g['time']) <= ts(as_of))]


def inspection_rows(data, lot, layer, side, inspection, as_of=None):
    rows = [r for r in data['aoi'] if r['lot'] == lot and (r['layer'],r['side'],r['inspection']) == (layer,side,inspection) and (as_of is None or ts(r['time']) <= ts(as_of))]
    for g in inspection_groups(data,lot,layer,side,inspection,as_of):
        count = g['rows']*g['columns']
        for index, code in enumerate(g['codes']):
            q, unit = index//count+1, index%count+1
            rows.append({'id':f"{g['id']}-Q{q}-U{unit}", 'lot':lot,'panel':g['panel'],'quad':q,'unit':unit,
                         'layer':layer,'side':side,'inspection':inspection,'time':g['time'],'code':code,
                         'row':(unit-1)//g['columns']+1,'column':(unit-1)%g['columns']+1,
                         'x':((unit-1)%g['columns']+.5)/g['columns'], 'y':((unit-1)//g['columns']+.5)/g['rows'],
                         'defect_location':g.get('locations',{}).get(str(index))})
    return rows


def inspection_summary(data, lot, layer, side, inspection, as_of=None):
    legacy = [r for r in data['aoi'] if r['lot']==lot and (r['layer'],r['side'],r['inspection'])==(layer,side,inspection) and (as_of is None or ts(r['time'])<=ts(as_of))]
    result = aoi_summary(legacy)
    for g in inspection_groups(data,lot,layer,side,inspection,as_of):
        result['inspected'] += len(g['codes'])
        result['failed'] += sum(c!='PASS' for c in g['codes'])
        result['abf_first'] += g['codes'].count('ABF')
    n = result['inspected']
    result.update(other_first_abf_unknown=result['failed']-result['abf_first'],
                  defect_rate=result['failed']/n if n else None, abf_first_rate=result['abf_first']/n if n else None)
    return result


def validate_groups(data, lots):
    groups = data.get('inspection_groups', [])
    if not isinstance(groups,list) or len(groups)>10000:
        raise ValueError('검사 그룹 수/형식 오류')
    seen = set()
    total = 0
    for g in groups:
        if not isinstance(g,dict) or any(k not in g for k in ('id','lot','panel','layer','side','inspection','time','rows','columns','codes')):
            raise ValueError('검사 그룹 필수값 누락')
        key = tuple(g[k] for k in ('lot','panel','layer','side','inspection'))
        if key in seen or g['lot'] not in lots:
            raise ValueError('검사 그룹 중복 또는 LOT 연결 오류')
        seen.add(key)
        if any(tuple(a[k] for k in ('lot','panel','layer','side','inspection'))==key for a in data['aoi']):
            raise ValueError('검사 그룹과 개별 유닛 기록의 검사 범위 중복')
        if g['side'] not in ('TOP','BOTTOM') or ts(g['time']) < ts(lots[g['lot']]['start']):
            raise ValueError('검사 면/시각 오류')
        if any(type(g[k]) is not int or not 1<=g[k]<=100 for k in ('rows','columns')):
            raise ValueError('모델 유닛 배열 오류')
        if not isinstance(g['codes'],list) or len(g['codes']) != 4*g['rows']*g['columns'] or any(c not in ('PASS','ABF','CIRCUIT','DENT','OTHER') for c in g['codes']):
            raise ValueError('전체 유닛 검사 코드 수/종류 오류')
        lot = lots[g['lot']]
        if lot.get('expected_units') != len(g['codes']):
            raise ValueError('모델 예상 PCS와 검사 배열 크기 불일치')
        if lot.get('layout') and (lot['layout']['rows'],lot['layout']['columns']) != (g['rows'],g['columns']):
            raise ValueError('모델 배열과 검사 배열 불일치')
        total += len(g['codes'])
        if total > 2000000:
            raise ValueError('검사 유닛 수 제한 초과')
        for k,p in g.get('locations',{}).items():
            if not str(k).isdigit() or not 0<=int(k)<len(g['codes']) or g['codes'][int(k)]=='PASS':
                raise ValueError('불량 위치와 유닛 판정 연결 오류')
            if not isinstance(p,dict) or not all(finite(p.get(a)) and 0<=p[a]<=1 for a in ('x','y')):
                raise ValueError('유닛 내부 불량 좌표 오류')
    return groups
