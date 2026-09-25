"""Authored simulation fixtures. Expected answers are not used by investigation rules."""
import random

CASES = [
    ('DEMO-0045','약액 상태 변화','약액 상태 또는 계측 이상','우선 확인',True),
    ('DEMO-0021','밀착 압력·시간 이탈','적층 조건 또는 자재 상태','우선 확인',True),
    ('DEMO-0046','Cure 제품 온도 이탈','열처리 조건 또는 온도 전달 차이','우선 확인',True),
    ('DEMO-0081','약액·밀착 동시 이탈','적층 조건 또는 자재 상태','우선 확인',True),
    ('DEMO-0085','등록 조건 정상·불량 발생','적층 조건 또는 자재 상태','현재 등록값에서 이탈 근거 없음',True),
    ('DEMO-0089','밀착 이탈·AOI PASS 반례','적층 조건 또는 자재 상태','우선 확인',False),
    ('DEMO-0066','Cu 시편 기록 누락','약액 상태 또는 계측 이상','판단 보류',False),
    ('DEMO-0069','계측 편향·AOI PASS 반례','약액 상태 또는 계측 이상','우선 확인',False),
    ('DEMO-0093','동일 자재·다른 설비 불량','자재 공유 이력','우선 확인',True),
]


def apply_scenarios(data, seed=721, truth=None):
    """Modify observable fixtures, never attach expected causes to LOT records."""
    runs={(r['lot'],r['step']):r for r in data['runs']}
    lots={r['id']:r for r in data['lots']}
    def parameter(lot,step,name,value,unit,lower,upper):
        if (lot,step) in runs:
            runs[lot,step]['parameters'][name]={'value':value,'unit':unit,'lower':lower,'upper':upper,'target':0 if unit=='%' else None,'basis':'PUBLIC-SIM-2'}
    for lot in ('DEMO-0021','DEMO-0081','DEMO-0089'):
        parameter(lot,'LAMINATION','압력 설정 대비 실측 편차',-7.5,'%',-4,4)
        parameter(lot,'LAMINATION','밀착 유지시간 설정 대비 실측 편차',-9,'%',-5,5)
    for lot in lots:
        if (lot,'LAMINATION') in runs:
            runs[lot,'LAMINATION']['parameters'].setdefault('밀착 유지시간 설정 대비 실측 편차',{'value':.2,'unit':'%','lower':-5,'upper':5,'target':0,'basis':'PUBLIC-SIM-2'})
    r=runs.get(('DEMO-0081','CZ'))
    if r:
        r['coupon']['after']=r['coupon']['before']-r['coupon']['reference']*.98
        r['parameters']['Cu 시편 무게 감소 정규화 지수']['value']=.98
        r['parameters']['순수 저항계 표시값']['value']=.82
    for lot in ('DEMO-0093','DEMO-0094'):
        if lot in lots: lots[lot]['material']='FILM-SHARED-REVIEW'
    failed={'DEMO-0021','DEMO-0081','DEMO-0085','DEMO-0093','DEMO-0094'}
    passed={'DEMO-0089','DEMO-0069','DEMO-0066'}
    if truth is not None:
        truth[:]=[t for t in truth if not any(t['aoi_id'].startswith(lot+'-') for lot in failed|passed)]
    for g in data.get('inspection_groups',[]):
        lot=g['lot']
        if lot not in failed|passed: continue
        g['locations']={}
        rng=random.Random(f'{seed}:{g["id"]}:scenario')
        for i in range(len(g['codes'])):
            unit=i%(g['rows']*g['columns'])
            edge=unit%g['columns'] in (0,g['columns']-1)
            probability=.35 if lot in ('DEMO-0021','DEMO-0081') and edge else .045
            bad=lot in failed and (unit==0 or rng.random()<probability)
            g['codes'][i]='ABF' if bad else 'PASS'
            if bad: g['locations'][str(i)]={'x':round(rng.uniform(.05,.95),4),'y':round(rng.uniform(.05,.95),4)}
            if bad and truth is not None:
                count=g['rows']*g['columns']
                truth.append({'aoi_id':f"{g['id']}-Q{i//count+1}-U{i%count+1}",'abf_present':True,'other_present':False,'scenario':'AUTHORED_VALIDATION','representative_code':'ABF'})
    # These cases have no section evidence; do not preserve obsolete sample results.
    data['confirmations']=[r for r in data['confirmations'] if r['lot'] not in failed|passed]
    return data


def test_decisions(tests):
    """Evidence-based review state, not a causal classifier or probability."""
    grouped={}
    for t in tests:
        grouped.setdefault(t['candidate'],[]).append(t)
    result=[]
    for candidate,rows in grouped.items():
        outcomes={r['outcome'] for r in rows}
        state='판단 보류'
        if outcomes=={'지지'}: state='후보 유지'
        elif outcomes=={'반증'}: state='검토 범위에서 제외'
        elif '지지' in outcomes and '반증' in outcomes: state='상충 결과 · 재검증'
        result.append({'원인 후보':candidate,'검토 판단':state,'시험 수':len(rows),'근거':' · '.join(r['evidence'] for r in rows)})
    return result


def validate_tests(tests):
    if not isinstance(tests,list) or len(tests)>100:
        raise ValueError('확인시험 목록 형식/수량 오류')
    for t in tests:
        if not isinstance(t,dict) or t.get('outcome') not in ('지지','반증','판단 불가'):
            raise ValueError('확인시험 판정 오류')
        for k in ('candidate','method','result','evidence','owner','scope'):
            if not isinstance(t.get(k),str) or not t[k].strip():
                raise ValueError('확인시험에는 후보·방법·실제 결과·증거·담당자·검증 범위를 모두 입력하세요.')


def effectiveness(values):
    if not isinstance(values,dict):
        raise ValueError('효과 확인 자료 형식 오류')
    for k in ('before_n','before_failed','after_n','after_failed','minimum_n'):
        if type(values.get(k)) is not int or values[k]<0:
            raise ValueError('효과 확인 수량은 0 이상의 정수여야 합니다.')
    if values['minimum_n']<1 or values['before_failed']>values['before_n'] or values['after_failed']>values['after_n']:
        raise ValueError('효과 확인의 검사 수량·불량 수량·최소 표본을 확인하세요.')
    if not isinstance(values.get('scope'),str) or not values['scope'].strip():
        raise ValueError('효과 확인의 기간·동일 모델·검사 범위를 입력하세요.')
    before=values['before_failed']/values['before_n'] if values['before_n'] else None
    after=values['after_failed']/values['after_n'] if values['after_n'] else None
    return {'조치 전 불량률(%)':100*before if before is not None else None,'조치 후 불량률(%)':100*after if after is not None else None,'변화(%p)':100*(after-before) if before is not None and after is not None else None,
            '판정':'표본 부족 · 추가 수집' if min(values['before_n'],values['after_n'])<values['minimum_n'] else '감소 관찰 · 효과 확정 아님' if after<before else '감소 미확인 · 재검토',
            '비교 범위':values['scope']}
