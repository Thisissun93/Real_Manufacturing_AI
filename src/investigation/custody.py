"""Transactional local panel custody. Actor names are declarations, not authentication."""
import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


def database(path=None):
    path=Path(path or os.environ.get('INVESTIGATION_CUSTODY_DB',Path(__file__).resolve().parents[2]/'instance'/'custody.sqlite3'))
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=10)
    db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS samples (id TEXT PRIMARY KEY, panel_key TEXT UNIQUE, revision INTEGER, payload TEXT)')
    return db


def entries(path=None):
    with database(path) as db:
        return [json.loads(r['payload']) for r in db.execute('SELECT payload FROM samples ORDER BY rowid DESC')]


def request(context, actor, destination, note='', path=None):
    if not actor.strip() or not destination.strip(): raise ValueError('요청자와 불출 요청 구역을 입력하세요.')
    key=json.dumps([context['data_hash'],context['lot'],context['panel']],ensure_ascii=False)
    entry={'id':str(uuid4()),'revision':0,'context':context,'state':'불출 요청','owner':None,
           'location':'검사 현장','destination':destination.strip(),'events':[]}
    entry['events'].append({'state':'불출 요청','actor':actor.strip(),'time':datetime.now(timezone.utc).isoformat(),'location':destination.strip(),'note':note})
    try:
        with database(path) as db:
            db.execute('INSERT INTO samples VALUES (?,?,?,?)',(entry['id'],key,0,json.dumps(entry,ensure_ascii=False)))
    except sqlite3.IntegrityError as exc:
        raise ValueError('이 PANEL의 요청이 이미 있습니다. 기존 이력에서 처리하세요.') from exc
    return entry


def transition(sample_id, revision, action, actor, location='', note='', path=None):
    if not actor.strip(): raise ValueError('처리자 이름을 입력하세요.')
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM samples WHERE id=?',(sample_id,)).fetchone()
        if not row: raise ValueError('요청을 찾을 수 없습니다.')
        if row['revision']!=revision: raise ValueError('다른 사용자가 먼저 처리했습니다. 새로고침 후 확인하세요.')
        entry=json.loads(row['payload'])
        allowed={'불출 요청':{'불출 완료','요청 취소'},'불출 완료':{'수령 완료'},'수령 완료':{'반납 완료'},'반납 완료':set(),'요청 취소':set()}
        if action not in allowed[entry['state']]: raise ValueError('현재 상태에서 가능한 처리가 아닙니다.')
        if action in {'불출 완료','반납 완료'} and not location.strip(): raise ValueError('실제 보관 구역을 입력하세요.')
        if action=='반납 완료' and actor.strip()!=entry['owner']: raise ValueError('현재 수령자의 이름으로 반납을 기록하세요.')
        entry['state']=action
        if action=='수령 완료': entry['owner']=actor.strip(); entry['location']=actor.strip()+' 엔지니어 보관'
        elif action in {'불출 완료','반납 완료'}: entry['location']=location.strip(); entry['owner']=None
        entry['revision']+=1
        entry['events'].append({'state':action,'actor':actor.strip(),'time':datetime.now(timezone.utc).isoformat(),'location':entry['location'],'note':note})
        db.execute('UPDATE samples SET revision=?,payload=? WHERE id=?',(entry['revision'],json.dumps(entry,ensure_ascii=False),sample_id))
        if action in {'반납 완료','요청 취소'}:
            db.execute('UPDATE samples SET panel_key=? WHERE id=?',('closed:'+sample_id,sample_id))
    return entry


def render_queue(data_hash=None):
    import streamlit as st
    st.caption('공유 서버의 로컬 DB에 저장됩니다. 이름은 직접 입력한 처리자 표시이며 로그인 인증은 아닙니다. 공개 서버에서는 실제 시료·개인정보를 입력하지 마세요.')
    all_rows=entries()
    rows=[r for r in all_rows if data_hash is None or r['context']['data_hash']==data_hash]
    if not rows: st.info('등록된 시료 요청이 없습니다. AOI에서 유닛을 선택해 요청하세요.'); return
    for row in rows:
        ctx=row['context']
        with st.expander(f"{ctx['lot']} / {ctx['panel']} · {row['state']} · {row['location']}",expanded=row['state']=='불출 완료'):
            st.write(f"요청 구역: {row['destination']} · Quad {ctx['quad']} / Unit {ctx['unit']} / {ctx['layer']}층 {ctx['side']}")
            if row['state']=='불출 완료': st.warning('불출 완료 · 엔지니어 회수 요망')
            st.dataframe(row['events'],hide_index=True)
            actions={'불출 요청':['불출 완료','요청 취소'],'불출 완료':['수령 완료'],'수령 완료':['반납 완료']}.get(row['state'],[])
            if actions:
                with st.form('custody_'+row['id']):
                    action=st.selectbox('처리',actions)
                    actor=st.text_input('처리자 이름 (불출: 검사자 / 수령·반납: 엔지니어)')
                    location=st.text_input('실제 보관 구역',value=row['destination'])
                    note=st.text_input('전달 사항')
                    submit=st.form_submit_button('시료 처리 기록')
                if submit:
                    try: transition(row['id'],row['revision'],action,actor,location,note); st.rerun()
                    except ValueError as e: st.error(str(e))
    st.download_button('시료 이동 이력 JSON 내보내기',json.dumps(rows,ensure_ascii=False,indent=2),'sample_custody.json','application/json')


def render_request(result):
    import streamlit as st
    unit=result.get('selected_unit')
    if not unit: return
    st.subheader('불량 시료 불출 요청')
    if unit['code']=='PASS': st.info('불출 요청은 불량 유닛을 선택한 후 진행하세요.')
    else:
        with st.form('sample_request'):
            st.write(f"{unit['panel']} / Quad {chr(64+unit['quad'])} / Unit {unit['unit']}")
            actor=st.text_input('요청 엔지니어')
            destination=st.text_input('불출 요청 구역')
            note=st.text_input('시료 요청 목적·주의사항')
            submit=st.form_submit_button('불량 시료 불출 요청')
        if submit:
            try:
                request({'data_hash':result['data_hash'],'lot':result['lot']['id'],'panel':unit['panel'],
                         'quad':chr(64+unit['quad']),'unit':unit['unit'],**result['selection']},actor,destination,note)
                st.success('검사자 확인 대기 상태로 등록했습니다.')
            except ValueError as e: st.error(str(e))
    render_queue(result['data_hash'])
