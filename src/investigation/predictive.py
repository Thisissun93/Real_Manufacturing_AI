"""Observational ABF representative-code analysis; not a causal or failure-probability model."""
from collections import defaultdict
import math
from .core import ts, finite
from .records import inspection_summary


def margin(parameter):
    v=parameter.get('value'); lo=parameter.get('lower'); hi=parameter.get('upper')
    if not finite(v): return None
    if finite(lo) and finite(hi) and hi>lo: return abs(v-(lo+hi)/2)/((hi-lo)/2)
    if finite(lo): return 1+(lo-v)/max(abs(lo),1e-9)
    if finite(hi): return 1+(v-hi)/max(abs(hi),1e-9)
    return None


def dataset(data,model,selection,as_of):
    rows=[]; now=ts(as_of)
    for lot in data['lots']:
        if lot['model']!=model: continue
        inspections=[r for r in data.get('inspection_groups',[])+data['aoi'] if r['lot']==lot['id'] and
                     (r['layer'],r['side'],r['inspection'])==(selection['layer'],selection['side'],selection['inspection']) and ts(r['time'])<=now]
        if not inspections: continue
        available=max(ts(r['time']) for r in inspections)
        summary=inspection_summary(data,lot['id'],**selection,as_of=as_of)
        if summary['inspected']!=lot.get('expected_units'): continue
        runs=[r for r in data['runs'] if r['lot']==lot['id'] and ts(r['available_at'])<=available and ts(r['end'])<=available]
        features={}; equipment={}; readings=[]
        for run in runs:
            equipment[run['step']]=run['equipment']
            for factor,p in run['parameters'].items():
                key=run['step']+' / '+factor
                value=margin(p)
                features[key]=value
                if value is not None:
                    readings.append({'factor':key,'equipment':run['equipment'],'step':run['step'],'margin':value,
                                     'time':run['end'],'signature':(p.get('lower'),p.get('upper'),p.get('unit'),p.get('basis'))})
        rows.append({'lot':lot['id'],'recipe':lot['recipe'],'time':available.isoformat(),'start':lot['start'],
                     'features':features,'equipment':equipment,'readings':readings,'n':summary['inspected'],
                     'abf':summary['abf_first'],'y':summary['abf_first_rate']})
    return sorted(rows,key=lambda r:(ts(r['start']),r['lot']))


def trend_projection(values,horizon=3):
    """Recent LOT-order linear extrapolation. Returned values are scenarios, not forecasts of failure."""
    import numpy as np
    if len(values)<8: return None
    y=np.asarray(values[-8:],dtype=float); x=np.arange(8,dtype=float)
    slope,intercept=np.polyfit(x,y,1); fit=slope*x+intercept
    total=float(((y-y.mean())**2).sum()); r2=1-float(((y-fit)**2).sum())/total if total>1e-12 else 0
    projections=[float(intercept+slope*(7+i)) for i in range(1,horizon+1)]
    crossing=next((i for i,v in enumerate(projections,1) if v>1),None)
    signal=bool(y[-1]<=1 and slope>0 and r2>=.6 and crossing)
    return {'current':float(y[-1]),'slope':float(slope),'r2':r2,'next':projections,'crossing':crossing if signal else None}


def analyze(data,model,selection,as_of,recipe=None):
    rows=dataset(data,model,selection,as_of)
    if recipe is not None: rows=[r for r in rows if r['recipe']==recipe]
    result={'scope':{'model':model,'recipe':recipe,**selection,'as_of':as_of},'lots':len(rows),'equipment':[],'factors':[],'trends':[],
            'shap':[],'validation':{'state':'학습 보류: 완전 검사 LOT 40건 이상 필요'},'recommendations':[]}
    byeq=defaultdict(list); byfactor=defaultdict(list); series=defaultdict(list)
    for row in rows:
        for step,eq in row['equipment'].items(): byeq[(step,eq)].append(row)
        for reading in row['readings']:
            byfactor[reading['factor']].append((reading['margin'],row))
            series[(reading['equipment'],reading['factor'],row['recipe'],reading['signature'])].append((ts(reading['time']),reading['margin']))
    for (step,eq),rr in byeq.items():
        n=sum(r['n'] for r in rr); bad=sum(r['abf'] for r in rr)
        result['equipment'].append({'공정':step,'설비':eq,'LOT 수':len(rr),'검사 PCS':n,'ABF 대표 PCS':bad,'ABF 대표 비율(%)':round(100*bad/n,3)})
    result['equipment'].sort(key=lambda r:(r['공정'],-r['ABF 대표 비율(%)']))
    for factor,rr in byfactor.items():
        outside=[r for v,r in rr if v>1]; within=[r for v,r in rr if v<=1]
        rate=lambda arr:100*sum(r['abf'] for r in arr)/sum(r['n'] for r in arr) if arr else None
        a,b=rate(outside),rate(within)
        result['factors'].append({'인자':factor,'이탈 LOT':len(outside),'기준 내 LOT':len(within),
                                  '이탈군 ABF 대표 비율(%)':a,'기준 내 비율(%)':b,
                                  '관찰 차이(%p)':a-b if a is not None and b is not None and min(len(outside),len(within))>=3 else None})
    result['factors'].sort(key=lambda r:(r['관찰 차이(%p)'] is None,-(r['관찰 차이(%p)'] or 0)))
    for (eq,factor,recipe,signature),seq in series.items():
        seq.sort(); tr=trend_projection([v for _,v in seq])
        if tr:
            result['trends'].append({'설비':eq,'인자':factor,'개정':recipe,'최근 부하 지수':round(tr['current'],3),
                                     '추세 R²':round(tr['r2'],3),'다음 1 LOT':round(tr['next'][0],3),'다음 2 LOT':round(tr['next'][1],3),'다음 3 LOT':round(tr['next'][2],3),
                                     '추세 신호':f"{tr['crossing']} LOT 이내 기준 접근·이탈 시나리오" if tr['crossing'] else '뚜렷한 접근 신호 없음',
                                     'early':bool(tr['crossing'])})
    for eqrow in result['equipment']:
        eq=eqrow['설비']; step=eqrow['공정']; rr=byeq[(step,eq)]
        current=[r for r in rr[-3:] if any(q['step']==step and q['margin']>1 for q in r['readings'])]
        early=[r for r in result['trends'] if r['설비']==eq and r['early']]
        historical=sum(r['abf']>0 and any(q['step']==step and q['margin']>1 for q in r['readings']) for r in rr)>=3
        if not current and not early and not historical: continue
        priority='P1 · 현재 이탈 확인' if current else 'P2 · 추세 점검' if early else 'P3 · 반복 이력 점검'
        factors=sorted({q['factor'] for r in current for q in r['readings'] if q['step']==step and q['margin']>1} | {r['인자'] for r in early})
        from .maintenance import CHECKS
        result['recommendations'].append({'우선순위':priority,'설비':eq,'공정':step,'근거':' / '.join(factors) or '해당 공정 이탈과 ABF 대표 불량이 함께 기록된 LOT 3건 이상',
                                          '권장 점검 부품':' / '.join(c[0] for c in CHECKS.get(step,[])) or '등록 부품 정보 확인',
                                          'Engineer Recommendation':'기준 계측기 대조 → 관련 부품·교체/교정 이력 점검 → 조치 전후 동일 모델 확인시험. 원인 확정 전 임의 조건 변경 금지.',
                                          '최근 이탈 LOT':len(current),'ABF 대표 비율(%)':eqrow['ABF 대표 비율(%)']})
    result['recommendations'].sort(key=lambda r:(r['우선순위'],-r['ABF 대표 비율(%)']))
    if len(rows)<40: return result
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error
    import shap
    # Three expanding chronological folds; label availability is purged at each boundary.
    initial=max(25,int(len(rows)*.4)); folds=np.array_split(np.arange(initial,len(rows)),3)
    first_boundary=ts(rows[initial]['start'])
    initial_train=[r for r in rows[:initial] if ts(r['time'])<first_boundary]
    names=sorted({k for r in initial_train for k,v in r['features'].items() if v is not None})
    if len(initial_train)<20 or not names: return result
    labels=names+[k+' / 기록 결측' for k in names]
    def matrix(rr): return np.array([[r['features'].get(k) if r['features'].get(k) is not None else np.nan for k in names] for r in rr],float)
    observed=[]; predictions=[]; baselines=[]; shap_values=[]; audits=[]; errors=[]
    for indexes in folds:
        if len(indexes)<3: continue
        boundary=ts(rows[int(indexes[0])]['start'])
        train=[r for r in rows[:int(indexes[0])] if ts(r['time'])<boundary]
        test=[rows[int(i)] for i in indexes]
        if len(train)<20: continue
        x=matrix(train); xt=matrix(test); med=np.nanmedian(x,axis=0)
        x=np.concatenate([np.where(np.isnan(x),med,x),np.isnan(x).astype(float)],axis=1)
        xt=np.concatenate([np.where(np.isnan(xt),med,xt),np.isnan(xt).astype(float)],axis=1)
        y=np.array([r['y'] for r in train]); yt=np.array([r['y'] for r in test])
        estimator=RandomForestRegressor(n_estimators=100,max_depth=4,min_samples_leaf=4,random_state=2026,n_jobs=1)
        estimator.fit(x,y); predicted=estimator.predict(xt)
        explanation=shap.TreeExplainer(estimator)(xt)
        values=np.asarray(explanation.values)
        errors.append(float(np.max(np.abs(explanation.base_values+values.sum(axis=1)-predicted))))
        observed.extend(yt); predictions.extend(predicted); baselines.extend([float(y.mean())]*len(yt)); shap_values.extend(values)
        audits.append({'학습 LOT':len(train),'검증 LOT':len(test),'학습 마지막 검사':max(r['time'] for r in train),'검증 첫 제조 시작':test[0]['start']})
    if not observed: return result
    yt=np.array(observed); positive=yt>0; values=np.asarray(shap_values)
    mae=float(mean_absolute_error(yt,predictions)); baseline=float(mean_absolute_error(yt,baselines))
    supported=int(positive.sum())>=3 and int((~positive).sum())>=3
    passed=supported and mae<baseline*.9
    result['validation']={'state':'시간순 검증에서 평균 기준 대비 개선 · 외부 검증 필요' if passed else '예측 활용 보류: 검증 불량·정상 표본 또는 평균 기준 대비 성능 부족',
                          '시간순 검증 구간':len(audits),'검증 LOT':len(yt),'모델 MAE(%p)':round(mae*100,3),'평균 기준 MAE(%p)':round(baseline*100,3),
                          '검증 중 ABF 대표 불량 LOT':int(positive.sum()),'SHAP 합산 최대 오차':max(errors),
                          '해석':'검증 LOT 모델 설명. 인과 효과·부품 고장 확률·잔여 수명이 아님.'}
    result['folds']=audits
    result['shap']=[{'인자':name,'평균 절대 SHAP(%p)':round(float(np.abs(values[:,i]).mean())*100,5),
                     '평균 방향 SHAP(%p)':round(float(values[:,i].mean())*100,5),
                     'ABF 대표 불량 LOT 평균 절대 SHAP(%p)':round(float(np.abs(values[positive,i]).mean())*100,5) if positive.any() else None} for i,name in enumerate(labels)]
    result['shap'].sort(key=lambda r:-(r['ABF 대표 불량 LOT 평균 절대 SHAP(%p)'] if int(positive.sum())>=3 else r['평균 절대 SHAP(%p)']))
    result['shap']=result['shap'][:10]
    for rec in result['recommendations']:
        matched=[r['인자'] for r in result['shap'][:5] if r['인자'].startswith(rec['공정']+' / ')]
        rec['모델 참고']=' / '.join(matched) if passed and matched else '모델 근거 미채택 · 관찰·추세 기준으로 점검'
    return result


def render_panel(result):
    import streamlit as st
    import pandas as pd
    st.write(f"동일 모델·개정 완전 검사 {result['lots']} LOT · {result['scope']['as_of']}까지")
    st.caption('LOT 단위 분석입니다. ABF가 최초 대표 코드인 PCS만 집계하므로 전체 ABF 존재율이 아닙니다. 같은 LOT이 여러 공정 설비를 거치므로 공정 간 PCS를 합산하지 마세요.')
    st.subheader('설비별 예방보전 점검 우선순위')
    st.dataframe(result['recommendations'],hide_index=True,width='stretch')
    st.caption('P1: 최근 3 LOT 중 등록 기준 이탈. P2: 최근 8 LOT 추세가 유지되면 다음 3 LOT 내 기준 이탈 가능. P3: 해당 공정 이탈과 ABF 대표 불량 동반 LOT 3건 이상. 공정별 비교이며 우선순위는 고장 확률이 아닙니다.')
    st.subheader('설비별 ABF 대표 불량 집계')
    st.dataframe(result['equipment'],hide_index=True,width='stretch')
    st.subheader('등록 기준 이탈과 ABF 대표 불량의 관찰 관계')
    st.dataframe(result['factors'],hide_index=True,width='stretch')
    st.caption('이탈군·기준 내 군 각각 3 LOT 이상일 때만 비율 차이를 표시합니다. 표본 수·동시 이탈·설비·자재 차이로 인한 영향을 분리한 인과 비교는 아닙니다.')
    st.subheader('시간순 모델 검증 · SHAP')
    st.dataframe([result['validation']],hide_index=True,width='stretch')
    if result['shap']:
        st.dataframe(result['shap'],hide_index=True,width='stretch')
        st.bar_chart(pd.DataFrame(result['shap']).set_index('인자')[['평균 절대 SHAP(%p)']])
    st.caption('목표값: LOT의 ABF 대표 불량 비율. 제조 시작 순서로 초기 40% 이후를 3구간으로 나누어 순차 검증하며, 각 검증 구간 제조 시작 이후에 확인된 검사 결과는 해당 학습에서 제외합니다. SHAP는 모델 설명이며 실제 원인 기여율이 아닙니다.')
    st.subheader('다음 LOT 순서의 추세 시나리오')
    display=[{k:v for k,v in r.items() if k!='early'} for r in result['trends']]
    st.dataframe(display,hide_index=True,width='stretch')
    st.caption('기준 경계 지수=1. 최근 8 LOT의 선형 추세를 3 LOT까지만 연장합니다. R²≥0.6·상승·현재 기준 이내 조건에서 접근 신호를 냅니다. 유지된다는 가정이며 발생 확률이나 남은 일수가 아닙니다.')
