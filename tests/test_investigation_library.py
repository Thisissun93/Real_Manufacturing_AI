import copy
import pytest
from src.investigation import library as l

def case():
    return dict(model='M',lot='L',owner='engineer',hypothesis='온도 편차',action='센서 확인',scope='동일 조건 전후',state='계획',counts=dict(before_n=100,before_failed=10,after_n=100,after_failed=2,minimum_n=100,scope='동일 조건'))

def test_case_validation_and_conflict(tmp_path):
    path=tmp_path/'library.db'; c=case(); ident=l.save('case',c,path=path)
    c['state']='검토 완료'
    with pytest.raises(ValueError): l.save('case',c,ident,1,path)
    c.update(result='감소 관찰',evidence='TEST1',reviewer='engineer2'); l.save('case',c,ident,1,path)
    with pytest.raises(ValueError): l.save('case',c,ident,1,path)
    assert l.entries(path=path)[0]['revision']==2

def test_backup_restore_integrity_atomic(tmp_path):
    a=tmp_path/'a.db';b=tmp_path/'b.db';l.save('case',case(),path=a)
    blob=l.backup(a);l.restore(blob,b);l.restore(blob,b)
    assert len(l.entries(path=b))==1
    corrupt=copy.deepcopy(blob);corrupt['records'][0]['action']='changed'
    with pytest.raises(ValueError):l.restore(corrupt,b)
    row=l.entries(path=a)[0];c=case();c['action']='new';l.save('case',c,row['id'],1,a)
    with pytest.raises(ValueError):l.restore(l.backup(a),b)
    assert l.entries(path=b)[0]['action']==case()['action']

def test_literal_retrieval_abstains():
    docs=[dict(id='1',title='온도 확인',source='page 2',category='시험',text='Cure 온도 센서 교정 결과와 블로워 풍량을 확인한다.')]
    assert l.retrieve('온도 센서',docs)[0]['source']=='page 2'
    assert l.retrieve('zzzzqqqq',docs)==[]
    assert l.retrieve('온도',[])==[]

def test_health_missing_stale_bad_and_future():
    r=dict(time='2026-01-01T00:00:00+00:00',value=12,quality='GOOD')
    assert l.health(r,0,10,'2026-01-01T00:00:30+00:00')=='기준 이탈'
    assert l.health(r,0,10,'2026-01-01T00:02:00+00:00')=='통신 지연·기록 오래됨'
    assert l.health(r,0,10,'2025-01-01T00:00:00+00:00')=='시각 오류'
    assert l.health(dict(r,quality='BAD'),0,10,'2026-01-01T00:00:30+00:00')=='품질 불량·판정 보류'
    assert l.health(r,None,None,'2026-01-01T00:00:30+00:00')=='기준 미등록'

def test_equipment_counts_not_averaged():
    rows=[dict(equipment={'CZ':'C1'},n=100,abf=10,y=.1),dict(equipment={'CZ':'C1'},n=900,abf=0,y=0)]
    out=l.equipment_comparison(rows,'CZ')[0]
    assert out['ABF 대표 비율(%)']==1
    assert out['판정']=='표본 부족'


def test_library_ui_case_and_retrieval(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    monkeypatch.setattr(l,'DEFAULT_DB',tmp_path/'ui.db')
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'src/dashboard/app.py',default_timeout=60).run()
    assert not app.exception
    next(b for b in app.button if b.label=='합성 Library 사례 1건 추가 · 기능 체험').click().run()
    assert not app.exception
    assert len(l.entries('case'))==1
    next(t for t in app.text_input if t.label=='예: Cure 온도 편차와 블로워 점검 근거는?').input('블로워 온도 편차')
    next(b for b in app.button if b.label=='등록 자료와 검토 완료 사례에서 찾기').click().run()
    assert not app.exception
    assert any('합성 사례' in t.value for t in app.text)
