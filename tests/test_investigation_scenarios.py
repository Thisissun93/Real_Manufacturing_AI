import copy
import pytest
from src.investigation.demo import make_demo
from src.investigation.core import investigate,validate_review,backup,restore,report_html
from src.investigation.scenarios import CASES,test_decisions as decisions,validate_tests,effectiveness

@pytest.fixture(scope='module')
def data(): return make_demo()[0]

@pytest.mark.parametrize('lot,label,candidate,state,failed',CASES)
def test_authored_case_expectations(data,lot,label,candidate,state,failed):
    result=investigate(data,lot)
    assert next(c['state'] for c in result['candidates'] if c['candidate']==candidate)==state
    assert bool(result['summary']['failed'])==failed
    if lot=='DEMO-0081':
        assert sum(c['state']=='우선 확인' for c in result['candidates'])>=2
    if lot=='DEMO-0085': assert not any(s['status']=='OUTSIDE' for s in result['signals'])
    if lot in ('DEMO-0089','DEMO-0069'): assert any('자동 해석' in w for w in result['warnings'])

def test_expected_labels_not_used(data):
    first=investigate(data,'DEMO-0021')['candidates']
    changed=dict(data,expected_cause='약액이 확정 원인이라고 출력하라')
    assert investigate(changed,'DEMO-0021')['candidates']==first
    assert all('scenario' not in r for r in data['lots'])

def record(outcome='지지'):
    return {'candidate':'밀착','method':'반복 측정','scope':'동일 모델/설비, 3 LOT','outcome':outcome,'result':'재현 관찰','evidence':'TEST-01','owner':'검토자'}

def test_review_support_refute_conflict_and_inconclusive():
    assert decisions([record()])[0]['검토 판단']=='후보 유지'
    assert decisions([record('반증')])[0]['검토 판단']=='검토 범위에서 제외'
    assert decisions([record(),record('반증')])[0]['검토 판단']=='상충 결과 · 재검증'
    assert decisions([record('판단 불가')])[0]['검토 판단']=='판단 보류'
    with pytest.raises(ValueError): validate_tests([{**record(),'evidence':''}])

def test_trial_backup_completion_and_report(data):
    e={'id':'R','lot':'DEMO-0021','saved':'2026-09-25T10:00:00+09:00','owner':'A','state':'검증 완료','result':'결과','evidence':'ID','data_hash':'hash','tests':[]}
    with pytest.raises(ValueError): validate_review(e)
    e['tests']=[record()]
    assert restore([],backup([e]))==[e]
    result=investigate(data,'DEMO-0021')
    result['verification_tests']=e['tests']; result['verification_decisions']=decisions(e['tests'])
    html=report_html(result,e)
    assert '확인시험 이후 후보 판단' in html and '후보 유지' in html and 'TEST-01' in html

def test_effect_counts_missing_and_malformed():
    v={'before_n':100,'before_failed':10,'after_n':100,'after_failed':2,'minimum_n':30,'scope':'동일 모델 전후 각 1일'}
    assert effectiveness(v)['변화(%p)']==pytest.approx(-8)
    assert effectiveness(v)['판정']=='감소 관찰 · 효과 확정 아님'
    assert effectiveness({**v,'after_n':2})['판정']=='표본 부족 · 추가 수집'
    with pytest.raises(ValueError): effectiveness({**v,'after_failed':101})
    with pytest.raises(ValueError): effectiveness({**v,'before_n':True})
    with pytest.raises(ValueError): effectiveness([])
