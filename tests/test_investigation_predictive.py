import json
from pathlib import Path
from copy import deepcopy
import pytest
from src.investigation.predictive import analyze,dataset,trend_projection,margin
from src.investigation.core import investigate,ts


@pytest.fixture(scope='module')
def data():
    from src.investigation.demo import make_demo
    return make_demo()[0]


def test_projection_is_bounded_and_no_constant_warning():
    assert trend_projection([.2]*7) is None
    assert trend_projection([.2]*8)['crossing'] is None
    tr=trend_projection([.15+.095*i for i in range(8)])
    assert tr['crossing']==2 and len(tr['next'])==3
    assert trend_projection([1.1]*8)['crossing'] is None
    assert margin({'value':None,'lower':0,'upper':1}) is None


def test_complete_scope_and_future_exclusion(data):
    scope={'layer':1,'side':'TOP','inspection':1}; cutoff=data['lots'][35]['end']
    rows=dataset(data,'MODEL-A',scope,cutoff)
    assert rows and all(ts(r['time'])<=ts(cutoff) for r in rows)
    d=deepcopy(data)
    for g in d['inspection_groups']:
        if g['layer']==2: g['codes']=['ABF']*len(g['codes'])
    assert dataset(d,'MODEL-A',scope,cutoff)==rows


def test_temporal_shap_and_priority(data):
    r=investigate(data,'DEMO-0046')
    p=analyze(data,r['lot']['model'],r['selection'],r['as_of'],r['lot']['recipe'])
    assert p['lots']==80 and p['shap']
    assert all(ts(f['학습 마지막 검사'])<ts(f['검증 첫 제조 시작']) for f in p['folds'])
    assert p['validation']['SHAP 합산 최대 오차']<1e-8
    assert p['validation']['검증 중 ABF 대표 불량 LOT']>0
    assert any(t['설비']=='LAMINATION-2' and t['early'] for t in p['trends'])
    assert any(t['설비']=='LAMINATION-2' and t['우선순위'].startswith('P2') for t in p['recommendations'])
    assert not any(t['공정']=='AOI' for t in p['recommendations'])
    assert any(s['ABF 대표 불량 LOT 평균 절대 SHAP(%p)'] is not None for s in p['shap'])


def test_insufficient_data_no_made_up_shap(data):
    r=analyze(data,'MODEL-A',{'layer':1,'side':'TOP','inspection':1},data['lots'][10]['end'],'MODEL-A-R1')
    assert not r['shap'] and '보류' in r['validation']['state']


def test_public_maintenance_has_no_vendor_column():
    from src.investigation.maintenance import recommendations
    rows=recommendations({},[{'step':'CURE','equipment':'THERMAL-1','end':'2026-01-01T00:00:00+09:00'}])
    assert all('제조사·형식' not in r for r in rows)
