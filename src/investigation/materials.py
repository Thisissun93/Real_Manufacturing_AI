"""Material-unit traceability. User supplied handling policy, not a vendor specification."""
from datetime import timedelta
from .core import ts

POLICY = {'FROZEN':48, 'COLD':24, 'THAW':12}
LABELS = {'FROZEN':'최초 냉동', 'COLD':'냉장', 'THAW':'해동', 'USE':'사용'}


def assess(data, lot_id, as_of):
    lot = next(x for x in data['lots'] if x['id']==lot_id)
    unit = next((x for x in data.get('material_units',[]) if x['id']==lot.get('material_unit')), None)
    if unit is None:
        return {'status':'기록 부족', 'issues':['자재 개체 또는 취급 이력 미등록'], 'history':[], 'uses':None}
    cutoff=ts(as_of)
    own_use=next((e for e in unit.get('events',[]) if e.get('stage')=='USE' and e.get('lot')==lot_id),None)
    if own_use: cutoff=min(cutoff,ts(own_use['end']))
    events=sorted([e for e in unit.get('events',[]) if ts(e['end'])<=cutoff],key=lambda e:ts(e['start']))
    designated=data.get('model_materials',{}).get(lot['model'])
    issues=[]
    if not designated: issues.append('모델 지정 자재 미등록')
    elif unit['type']!=designated: issues.append('모델 지정 자재 불일치')
    if unit.get('supplier_lot')!=lot.get('material'): issues.append('공급 자재 LOT 연결 불일치')
    last=None; thaws=uses=0; selected=False
    allowed={None:{'FROZEN'},'FROZEN':{'COLD'},'COLD':{'THAW'},'THAW':{'USE'},'USE':{'USE','COLD'}}
    history=[]
    previous_end=None
    for e in events:
        stage=e['stage']; start=ts(e['start']); end=ts(e['end'])
        if stage not in allowed.get(last,set()): issues.append('취급 순서 위반: '+LABELS.get(stage,stage))
        if end<start or (previous_end and start<previous_end): issues.append('자재 취급 시간 중복 또는 역전')
        hours=(end-start).total_seconds()/3600
        if stage in POLICY and hours<POLICY[stage]: issues.append(f'{LABELS[stage]} 최소 {POLICY[stage]}시간 미달')
        if stage=='COLD' and thaws>=3: issues.append('3회 해동 후 재냉장 금지 위반')
        if stage=='THAW':
            thaws+=1
            if thaws>3: issues.append('최대 해동 3회 초과')
        if uses>=6: issues.append('6 LOT 사용 종료 후 추가 취급')
        if stage=='USE':
            uses+=1
            selected |= e.get('lot')==lot_id
            if uses>6: issues.append('최대 6 LOT 사용 초과')
        history.append({'단계':LABELS.get(stage,stage),'시작':e['start'],'종료':e['end'],'시간(h)':round(hours,2),'LOT':e.get('lot','')})
        last=stage; previous_end=end
    if not selected: issues.append('조사 LOT의 자재 사용 기록 미확인')
    return {'status':'이탈 확인' if issues else '등록 기준 충족','issues':list(dict.fromkeys(issues)), 'history':history,
            'unit':unit['id'],'supplier_lot':unit.get('supplier_lot'), 'type':unit['type'],'designated':designated,
            'uses':uses,'remaining_lots':max(0,6-uses),'thaws':thaws,
            'storage':'사용 종료 · 잔량 없음' if uses>=6 else '재냉장 불가' if thaws>=3 else '재냉장 가능'}


def add_demo_materials(data):
    """Two uses per thaw, three thaws per unit; wait constraints schedule material availability."""
    data['model_materials']={m:m+'-FILM' for m in {l['model'] for l in data['lots']}}
    units=[]
    for lot in data['lots']:
        run=next(r for r in data['runs'] if r['lot']==lot['id'] and r['step']=='LAMINATION')
        finish=ts(run['end']); start=ts(run['start'])
        reused=None
        for u in units:
            uses=sum(e['stage']=='USE' for e in u['events'])
            gap=36 if uses%2==0 else 0
            if u['type']==lot['film'] and u['supplier_lot']==lot['material'] and uses<6 and ts(u['events'][-1]['end'])+timedelta(hours=gap)<=start:
                reused=u; break
        if reused:
            if sum(e['stage']=='USE' for e in reused['events'])%2==0:
                cursor=start-timedelta(hours=36)
                for stage,hours in [('COLD',24),('THAW',12)]:
                    end=cursor+timedelta(hours=hours)
                    reused['events'].append({'stage':stage,'start':cursor.isoformat(),'end':end.isoformat()}); cursor=end
            reused['events'].append({'stage':'USE','start':start.isoformat(),'end':finish.isoformat(),'lot':lot['id']})
            lot['material_unit']=reused['id']
            continue
        events=[]; cursor=start-timedelta(hours=84)
        for stage,hours in POLICY.items():
            end=cursor+timedelta(hours=hours)
            events.append({'stage':stage,'start':cursor.isoformat(),'end':end.isoformat()}); cursor=end
        events.append({'stage':'USE','start':start.isoformat(),'end':finish.isoformat(),'lot':lot['id']})
        uid='UNIT-'+lot['id']; lot['material_unit']=uid
        units.append({'id':uid,'type':lot['film'],'supplier_lot':lot['material'],'events':events})
    data['material_units']=units


def validate_materials(data):
    units=data.get('material_units',[])
    if not isinstance(units,list) or len(units)>10000: raise ValueError('자재 개체 목록 형식 또는 건수를 확인하세요.')
    ids=set(); known={r['id']:r for r in data['lots']}; used=set()
    for u in units:
        if not isinstance(u,dict) or not all(isinstance(u.get(k),str) and u[k] for k in ('id','type','supplier_lot')): raise ValueError('자재 개체 식별 정보가 필요합니다.')
        if u['id'] in ids: raise ValueError('자재 개체 ID 중복')
        ids.add(u['id'])
        if not isinstance(u.get('events'),list) or len(u['events'])>1000: raise ValueError('자재 취급 이력을 확인하세요.')
        for e in u['events']:
            if not isinstance(e,dict) or e.get('stage') not in LABELS: raise ValueError('자재 취급 단계 오류')
            ts(e.get('start')); ts(e.get('end'))
            if e['stage']=='USE':
                lid=e.get('lot')
                if lid not in known or known[lid].get('material_unit')!=u['id']: raise ValueError('자재 사용 LOT 연결 오류')
                if lid in used: raise ValueError('LOT 자재 사용 기록 중복')
                used.add(lid)
    if units:
        for lot in data['lots']:
            if lot.get('material_unit') not in ids: raise ValueError('LOT의 자재 개체가 존재하지 않습니다.')
    models=data.get('model_materials',{})
    if not isinstance(models,dict) or any(not isinstance(v,str) for v in models.values()): raise ValueError('모델 지정 자재 형식 오류')
