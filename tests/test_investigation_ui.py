from streamlit.testing.v1 import AppTest
from pathlib import Path


def test_direct_lot_search_switches_model_and_handles_unknown():
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'src/dashboard/app.py',default_timeout=60).run()
    next(t for t in app.text_input if t.label=='LOT ID 직접 검색').input(' demo-0001 ')
    next(b for b in app.button if b.label=='LOT 검색').click().run()
    assert not app.exception
    assert app.session_state['investigation_lot']=='DEMO-0001'
    assert app.session_state['investigation_model']=='MODEL-B'
    next(t for t in app.text_input if t.label=='LOT ID 직접 검색').input('NOT-EXISTS')
    next(b for b in app.button if b.label=='LOT 검색').click().run()
    assert app.session_state['investigation_lot']=='DEMO-0001'
    assert any('일치하는 LOT' in e.value for e in app.error)


def test_investigation_navigation_and_review_gate():
    app = AppTest.from_file(Path(__file__).resolve().parents[1]/'src/dashboard/app.py', default_timeout=60).run()
    assert not app.exception
    assert app.metric[0].value == '1600'
    state = next(s for s in app.selectbox if s.label == '검토 상태')
    state.select('검증 완료').run()
    next(b for b in app.button if b.label == '검토 기록 추가').click().run()
    assert any('담당자' in e.value for e in app.error)
    assert app.session_state['investigation_reviews'] == []
    next(s for s in app.selectbox if s.label == '검토 상태').select('진행 중').run()
    next(t for t in app.text_input if t.label == '담당자').input('UI TEST')
    next(b for b in app.button if b.label == '검토 기록 추가').click().run()
    assert len(app.session_state['investigation_reviews']) == 1
    next(s for s in app.selectbox if s.label == '조사 LOT').select('DEMO-0066').run()
    assert not app.exception
    assert next(t for t in app.text_input if t.label == '담당자').value == ''
    assert any('미수집' in i.value for i in app.info)
    next(s for s in app.selectbox if s.label == '제품 모델').select('MODEL-B').run()
    assert not app.exception
    assert app.metric[0].value == '784'
    assert next(s for s in app.selectbox if s.label == '조사 LOT').value != 'DEMO-0066'
    assert not app.code and not app.json
    next(b for b in app.button if b.label=='밀착 압력·시간 이탈').click().run()
    assert next(s for s in app.selectbox if s.label=='조사 LOT').value=='DEMO-0021'
    next(t for t in app.text_input if t.label=='담당자').input('검토자')
    next(t for t in app.text_input if t.label=='실시한 시험 방법').input('설비별 압력 반복 측정')
    next(t for t in app.text_input if t.label=='검증 범위·비교 조건·표본').input('동일 모델 3 LOT')
    next(t for t in app.text_area if t.label=='실제로 실시한 조치와 결과').input('압력 저하 재현')
    next(t for t in app.text_area if t.label=='증거 문서 번호·측정 결과·검토자').input('TEST-UI-01')
    next(c for c in app.checkbox if c.label=='이번 기록에 실제 확인시험 결과를 포함').check()
    next(s for s in app.selectbox if s.label=='검증할 원인 후보').select('적층 조건 또는 자재 상태')
    next(s for s in app.selectbox if s.label=='시험에 대한 엔지니어 판정').select('지지')
    next(b for b in app.button if b.label=='검토 기록 추가').click().run()
    assert not app.exception
    assert app.session_state['investigation_reviews'][-1]['tests'][0]['evidence']=='TEST-UI-01'
