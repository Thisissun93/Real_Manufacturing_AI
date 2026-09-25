import copy
import pytest
from src.investigation.demo import make_demo, temperature_profile
from src.investigation.core import validate, investigate, report_html
from src.investigation.records import inspection_rows, inspection_summary


@pytest.fixture(scope='module')
def detailed():
    return make_demo(count=6)[0]


def test_model_counts_and_explicit_pass(detailed):
    assert detailed['lots'][0]['expected_units']==784
    assert detailed['lots'][2]['expected_units']==1600
    for lot in detailed['lots']:
        rows=inspection_rows(detailed,lot['id'],1,'TOP',1)
        assert len(rows)==lot['expected_units']
        assert len({(r['quad'],r['unit']) for r in rows})==len(rows)
        assert inspection_summary(detailed,lot['id'],1,'TOP',1)['inspected']==len(rows)


def test_continuous_seconds_celsius_zone_boundaries():
    p=temperature_profile(36,11)
    assert len(p['temperature_c'])==2161
    assert p['elapsed_s']==list(range(2161))
    assert max(p['temperature_c'])>100
    assert max(abs(a-b) for a,b in zip(p['temperature_c'],p['temperature_c'][1:]))<1
    assert p['zones'][0]['start_s']==0 and p['zones'][-1]['end_s']==2160
    assert all(a['end_s']==b['start_s'] for a,b in zip(p['zones'],p['zones'][1:]))


def test_resistance_one_sided_limit(detailed):
    for r in detailed['runs']:
        if r['step']=='CZ':
            p=r['parameters']['순수 저항계 표시값']
            assert p['lower']==1 and p['upper'] is None and p['unit']=='MΩ'
            assert p['value'] is not None


def test_internal_location_only_for_fail(detailed):
    rows=inspection_rows(detailed,'DEMO-0001',1,'TOP',1)
    assert any(r['defect_location'] for r in rows)
    for r in rows:
        if r['code']=='PASS': assert r['defect_location'] is None
        elif r['defect_location']:
            assert all(0<=r['defect_location'][k]<=1 for k in ('x','y'))


@pytest.mark.parametrize('corruption',['count','duplicate','location','profile'])
def test_new_input_validation(detailed,corruption):
    d=copy.deepcopy(detailed)
    if corruption=='count': d['inspection_groups'][0]['codes'].pop()
    if corruption=='duplicate': d['inspection_groups'].append(d['inspection_groups'][0].copy())
    if corruption=='location': d['inspection_groups'][0]['locations']['999999']={'x':.5,'y':.5}
    if corruption=='profile': next(r for r in d['runs'] if r['step']=='CURE')['profile']['elapsed_s'][2]=0
    with pytest.raises(ValueError): validate(d)


def test_time_comparison_hand_calculated_and_asof(detailed):
    d=copy.deepcopy(detailed)
    # Same MODEL-B, all PASS, distinct CZ durations: two normal LOTs is insufficient.
    for g in d['inspection_groups']: g['codes']=['PASS']*len(g['codes']); g['locations']={}
    r=investigate(d,'DEMO-0001')
    cz=r['durations'][0]
    assert cz['normal_n']==1
    assert cz['comparison']=='비교군 부족'
    assert cz['difference_min']==pytest.approx(cz['actual_min']-cz['normal_median_min'])
    early=investigate(d,'DEMO-0001',as_of=d['lots'][0]['start'])
    assert early['summary']['inspected']==0 and early['durations']==[]


def test_report_contains_tables_not_raw_code(detailed):
    r=investigate(detailed,'DEMO-0001')
    out=report_html(r,{'owner':'<script>bad()</script>','result':'완료'})
    assert '<table>' in out and '<svg' in out
    assert '<pre>' not in out and 'python -m' not in out
    assert 'product_deviation_pct' not in out and "'layer':" not in out
    assert '<script>bad()' not in out and '&lt;script&gt;' in out
    assert '>A<' in out and '>D<' in out
