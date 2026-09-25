import copy
from datetime import timedelta
import pytest
from src.investigation.demo import make_demo
from src.investigation.core import investigate, ts, validate
from src.investigation.materials import assess
from src.investigation.custody import request, transition, entries


@pytest.fixture(scope='module')
def data(): return make_demo()[0]


def test_material_valid_and_6_lot_completion(data):
    assert all(assess(data,l['id'],l['end'])['status']=='등록 기준 충족' for l in data['lots'])
    units=[u for u in data['material_units'] if sum(e['stage']=='USE' for e in u['events'])==6]
    assert units
    e=units[0]['events'][-1]
    a=assess(data,e['lot'],e['end'])
    assert a['uses']==6 and a['remaining_lots']==0 and a['thaws']==3
    assert a['storage']=='사용 종료 · 잔량 없음'


def test_material_missing_and_future_not_counted(data):
    d=copy.deepcopy(data); d.pop('material_units')
    assert assess(d,d['lots'][0]['id'],d['lots'][0]['end'])['status']=='기록 부족'
    u=next(u for u in data['material_units'] if len(u['events'])>4)
    first=next(e for e in u['events'] if e['stage']=='USE')
    assert assess(data,first['lot'],first['end'])['uses']==1


def test_material_wait_matching_and_order(data):
    d=copy.deepcopy(data); u=d['material_units'][0]; lot=next(e['lot'] for e in u['events'] if e['stage']=='USE')
    u['events'][0]['start']=(ts(u['events'][0]['end'])-timedelta(hours=47)).isoformat()
    u['type']='WRONG'
    a=assess(d,lot,d['lots'][-1]['end'])
    assert any('48시간 미달' in x for x in a['issues'])
    assert '모델 지정 자재 불일치' in a['issues']
    u['events'].append({'stage':'COLD','start':d['lots'][-1]['end'],'end':(ts(d['lots'][-1]['end'])+timedelta(hours=24)).isoformat()})
    # Construct third-thaw boundary independently from total use count.
    u['events']=[{'stage':s,'start':'2026-01-01T00:00:00+09:00','end':'2026-01-01T00:00:00+09:00','lot':lot} for s in ['FROZEN','COLD','THAW','USE','COLD','THAW','USE','COLD','THAW','USE','COLD','THAW']]
    a=assess(d,lot,d['lots'][-1]['end'])
    assert '3회 해동 후 재냉장 금지 위반' in a['issues'] and '최대 해동 3회 초과' in a['issues']


def test_custody_transaction_and_re_request(tmp_path):
    path=tmp_path/'samples.db'; ctx={'data_hash':'a','lot':'L1','panel':'P1'}
    r=request(ctx,'엔지니어','A구역',path=path)
    with pytest.raises(ValueError,match='이미'): request(ctx,'다른 엔지니어','B구역',path=path)
    with pytest.raises(ValueError,match='가능한'): transition(r['id'],0,'수령 완료','E',path=path)
    r=transition(r['id'],0,'불출 완료','검사자','B구역',path=path)
    with pytest.raises(ValueError,match='먼저'): transition(r['id'],0,'불출 완료','검사자','A구역',path=path)
    r=transition(r['id'],1,'수령 완료','김 엔지니어',path=path)
    assert r['owner']=='김 엔지니어' and r['location']=='김 엔지니어 엔지니어 보관'
    with pytest.raises(ValueError,match='수령자'): transition(r['id'],2,'반납 완료','다른 사람','C구역',path=path)
    r=transition(r['id'],2,'반납 완료','김 엔지니어','C구역',path=path)
    request(ctx,'E','A구역',path=path)
    assert len(entries(path))==2 and len(r['events'])==4


def test_pdf_and_report_material(data):
    from src.investigation.pdf_report import create_pdf
    from src.investigation.core import report_html
    result=investigate(data,'DEMO-0045')
    assert create_pdf(result).startswith(b'%PDF-')
    assert '모델 지정 자재 및 취급 이력' in report_html(result)
