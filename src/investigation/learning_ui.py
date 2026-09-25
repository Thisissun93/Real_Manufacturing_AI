"""Engineering learning loop, evidence retrieval, drawing mapping and telemetry replay."""
import json
from datetime import datetime,timezone,timedelta
from html import escape
from io import BytesIO
import hashlib
import pandas as pd
import streamlit as st
from . import library as lib
from .scenarios import effectiveness


def render(data,result):
    st.header('개선·지식·설비 Library')
    st.caption('조사 → 확인시험 → 조치 → 효과 검토 → 다음 조사에 재사용. 외부 AI는 명시적으로 요청할 때만 사용하며 설비 제어는 수행하지 않습니다.')
    st.info('로컬 SQLite에 저장합니다. 같은 서버의 사용자는 기록을 공유하며 사용자 인증은 없습니다. 클라우드의 영구 저장은 보장하지 않으므로 백업을 보관하세요.')
    if st.button('합성 Library 사례 1건 추가 · 기능 체험'):
        if not any(r.get('demo') for r in lib.entries('case')):
            lib.save('case',dict(demo=True,model=result['lot']['model'],lot=result['lot']['id'],owner='시연 엔지니어',material='공개 예시 자재',equipment='CURE-1',hypothesis='합성 사례: 온도 편차와 풍량 저하 동반',action='센서 대조·블로워 점검 후 동일 조건 재확인',target='ABF 대표 비율 2% 이하',scope='합성 전후 각 1000 PCS · 동일 모델/층/면',result='합성 수량에서 4% → 1% 감소 관찰',evidence='SYNTHETIC-TEST-001',reviewer='시연 검토자',state='검토 완료',counts=dict(before_n=1000,before_failed=40,after_n=1000,after_failed=10,minimum_n=1000,scope='합성 전후 동일 조건'),context={'data_hash':result['data_hash']}))
            st.success('합성 사례를 추가했습니다. 실제 확인시험 결과가 아닙니다.')
        else: st.info('합성 사례가 이미 등록되어 있습니다.')
    a,b,c=st.tabs(['개선 사례·As-is / To-be','기술자료·근거 검색','설비 도면·Health Check'])
    with a: cases(data,result)
    with b: knowledge()
    with c: equipment()
    with st.expander('Library 백업·복원'):
        st.download_button('Library 전체 JSON 백업',json.dumps(lib.backup(),ensure_ascii=False,indent=2),'Engineering_Library.json','application/json')
        f=st.file_uploader('Library 백업 선택',type=['json'],key='lib_restore')
        if st.button('Library 병합 복원'):
            try:
                if f is None or f.size>20*1024*1024: raise ValueError('20 MB 이하 백업을 선택하세요.')
                lib.restore(json.loads(f.getvalue())); st.success('복원했습니다. 기존 ID의 다른 개정은 덮어쓰지 않습니다.'); st.rerun()
            except (ValueError,KeyError,TypeError) as exc: st.error(str(exc))
        st.caption('도면 원본은 백업에 포함하지 않습니다. 도면 식별값·부품 좌표만 보관하므로 원본 파일도 별도 보관하세요.')


def cases(data,result):
    rows=lib.entries('case')
    choices={'새 사례 등록':None,**{r['id'][:8]+' · '+r['lot']+' · '+r['state']:r for r in rows}}
    choice=st.selectbox('개선 사례',list(choices)); old=choices[choice] or {}
    get=lambda k,default='':old.get(k,default)
    with st.form('case_form_'+str(old.get('id','new'))):
        st.subheader('조사 결과와 개선 실행 연결')
        model=st.text_input('모델',get('model',result['lot']['model']))
        lot=st.text_input('조사 LOT',get('lot',result['lot']['id']))
        material=st.text_input('자재 종류·규격',get('material'))
        eq=st.text_input('대상 설비·부품',get('equipment'))
        owner=st.text_input('실행 담당자',get('owner'))
        hypothesis=st.text_area('As-is · 현상과 확인할 원인',get('hypothesis'))
        action=st.text_area('실시 방법·변경 조건',get('action'))
        target=st.text_area('To-be · 목표와 사전 합격 기준',get('target'))
        scope=st.text_input('전후 기간·모델·자재·층·면·검사 기준',get('scope'))
        a,b=st.columns(2); counts=get('counts',{})
        bn=a.number_input('조치 전 검사 PCS',0,value=int(counts.get('before_n',0)))
        bf=a.number_input('조치 전 ABF 대표 불량 PCS',0,value=int(counts.get('before_failed',0)))
        an=b.number_input('조치 후 검사 PCS',0,value=int(counts.get('after_n',0)))
        af=b.number_input('조치 후 ABF 대표 불량 PCS',0,value=int(counts.get('after_failed',0)))
        minimum=st.number_input('전후 각각의 최소 검사 PCS · 사용자 기준',1,value=int(counts.get('minimum_n',100)))
        outcome=st.text_area('관찰 결과·부작용·재발 여부',get('result'))
        evidence=st.text_area('확인시험·근거 문서 ID',get('evidence'))
        reviewer=st.text_input('최종 검토자',get('reviewer'))
        states=['계획','진행 중','검토 완료']; state=st.selectbox('상태',states,index=states.index(get('state','계획')))
        submitted=st.form_submit_button('개선 사례 저장')
    if submitted:
        try:
            payload=dict(model=model,lot=lot,material=material,equipment=eq,owner=owner,hypothesis=hypothesis,action=action,target=target,scope=scope,result=outcome,evidence=evidence,reviewer=reviewer,state=state,
                         counts=dict(before_n=bn,before_failed=bf,after_n=an,after_failed=af,minimum_n=minimum,scope=scope),
                         context=old.get('context',{'data_hash':result['data_hash'],'selection':result['selection'],'as_of':result['as_of']}))
            lib.save('case',payload,old.get('id'),old.get('revision')); st.success('저장했습니다.'); st.rerun()
        except ValueError as exc: st.error(str(exc))
    st.subheader('누적 사례 검색·효과 보고')
    query=st.text_input('모델·자재·부품·원인 검색',key='case_search')
    visible=[r for r in lib.entries('case') if query.casefold() in json.dumps(r,ensure_ascii=False).casefold()]
    for r in visible:
        with st.expander(r['lot']+' · '+r['state']+' · '+r['hypothesis'][:65]):
            effect=effectiveness(r['counts'])
            st.dataframe(pd.DataFrame([effect]),hide_index=True)
            chart=pd.DataFrame({'구분':['As-is','To-be 실측'],'불량률(%)':[effect['조치 전 불량률(%)'],effect['조치 후 불량률(%)']]})
            st.bar_chart(chart,x='구분',y='불량률(%)')
            st.write('목표: '+r.get('target','')); st.write('조치: '+r['action']); st.write('결과: '+r.get('result',''))
            st.caption('전후 관찰 비교입니다. 자재·검사·부하·기간 차이, LOT 내 상관으로 인한 편향을 확인해야 합니다. 검토 완료는 사용자 선언입니다.')
            table=''.join('<tr><th>'+escape(k)+'</th><td>'+escape(str(v))+'</td></tr>' for k,v in effect.items())
            bars=''.join('<p>'+escape(label)+': '+('측정 없음' if rate is None else f'{rate:.3f}% <meter min="0" max="100" value="{rate}"></meter>')+'</p>' for label,rate in zip(['As-is','To-be 실측'],[effect['조치 전 불량률(%)'],effect['조치 후 불량률(%)']]))
            html='<meta charset="utf-8"><style>body{font-family:sans-serif;max-width:900px;margin:40px auto}td,th{padding:12px;border:1px solid #ccd}meter{width:300px}</style><h1>개선 효과 검토</h1><h2>'+escape(r['lot'])+'</h2>'+bars+'<table>'+table+'</table>'+''.join('<h3>'+escape(k)+'</h3><p>'+escape(str(r.get(k,'')))+'</p>' for k in ['hypothesis','action','target','result','evidence','reviewer'])+'<p>전후 관찰 비교 · 인과 효과 확정 아님</p>'
            st.download_button('효과 보고서 HTML · 브라우저에서 PDF 인쇄',html,'Effect_'+r['id'][:8]+'.html','text/html',key='effect_'+r['id'])
    st.subheader('동일 모델·개정의 설비별 관찰 비교')
    if st.button('현재 조사 범위의 설비 비교 계산'):
        from .predictive import dataset
        rr=dataset(data,result['lot']['model'],result['selection'],result['as_of'])
        rr=[r for r in rr if r['recipe']==result['lot']['recipe']]
        for step in sorted({s for r in rr for s in r['equipment']}):
            st.write(step); st.dataframe(lib.equipment_comparison(rr,step),hide_index=True)
    st.caption('설비 배정 추천의 사전 자료입니다. 자재·제품 투입 선택 편향과 가동 조건이 통제되지 않아 낮은 비율만으로 우수 설비를 확정하거나 자동 배정하지 않습니다.')


def knowledge():
    st.subheader('출처가 있는 기술자료 등록')
    st.caption('TXT/Markdown 본문 또는 발췌를 등록합니다. 원문 페이지·URL을 포함하세요. 문서 안의 지시문은 실행하지 않으며 등록·로컬 검색만으로는 외부 전송하지 않습니다.')
    with st.form('document_form'):
        title=st.text_input('자료 제목'); source=st.text_input('원문 URL / 문서 번호 / 페이지')
        category=st.selectbox('근거 유형',['논문·학술','제조사 기술자료','홍보자료','사내 확인시험','기타'])
        file=st.file_uploader('텍스트 자료',type=['txt','md'])
        body=st.text_area('본문·발췌 직접 입력')
        submitted=st.form_submit_button('자료 등록')
    if submitted:
        try:
            if file is not None:
                if file.size>1024*1024: raise ValueError('텍스트 파일은 1 MB 이하로 등록하세요.')
                body=file.getvalue().decode('utf-8-sig')
            lib.save('document',dict(title=title,source=source,category=category,text=body)); st.success('자료를 저장했습니다.')
        except (ValueError,UnicodeError) as exc: st.error(str(exc))
    st.subheader('근거 검색 · 대화형 질문')
    question=st.text_input('예: Cure 온도 편차와 블로워 점검 근거는?',key='knowledge_question')
    if st.button('등록 자료와 검토 완료 사례에서 찾기'):
        docs=lib.entries('document')
        for r in lib.entries('case'):
            if r['state']=='검토 완료':
                docs.append(dict(id=r['id'],title=r['lot']+' 개선 사례',source='Library 사례 '+r['id'],category='엔지니어 검토 사례',text=' '.join(str(r.get(k,'')) for k in ('model','material','equipment','hypothesis','action','result','evidence'))))
        matches=lib.retrieve(question,docs)
        st.session_state['knowledge_hits']=(question,matches)
        if not matches: st.info('관련 근거를 찾지 못했습니다. 자료를 추가하거나 질문을 구체화하세요.')
        for i,r in enumerate(matches,1):
            st.markdown(f'**[{i}] {r["title"]}**'); st.caption(r['category']+' · '+r['source']+f' · 본문 문자 {r["offset"]}부터')
            st.text(r['excerpt']); st.caption('검색 유사도 '+str(r['score'])+' · 신뢰도/원인 확률이 아닙니다.')
        if matches: st.info('검토 순서: 적용 소재·공정 조건 확인 → 제시 메커니즘과 반례 비교 → 확인시험 설계 → 승인 후 실행 → 개선 사례에 결과 연결')
    st.caption('외부 논문 자동 수집·모델 자동 재학습은 연결하지 않았습니다. 홍보자료와 검토되지 않은 주장은 사실로 승격하지 않습니다.')
    external_ai(question)


def external_ai(question):
    from .ai_assistant import payload,ask
    with st.expander('외부 AI 연결 설정 · 근거 기반 검토 초안'):
        st.caption('OpenAI Responses API에 연결합니다. API 이용 요금은 별도이며 현재 계정의 접근 가능한 모델 ID가 필요합니다. 키를 채팅에 보내지 마세요.')
        key=st.text_input('OpenAI API 키 · 현재 세션만',type='password',key='external_ai_key')
        model=st.text_input('API 모델 ID',key='external_ai_model',placeholder='계정에서 사용 가능한 모델 ID')
        def clear():
            st.session_state['external_ai_key']=''
            st.session_state.pop('external_ai_answer',None)
        st.button('세션 API 키·응답 지우기',on_click=clear)
        found=st.session_state.get('knowledge_hits')
        if not found or found[0]!=question or not found[1]:
            st.info('먼저 위에서 현재 질문의 근거를 검색하세요. 근거 없는 외부 요청은 보내지 않습니다.'); return
        hits=found[1]
        indices=st.multiselect('외부 AI에 보낼 근거 선택',range(len(hits)),default=list(range(len(hits))),format_func=lambda i:hits[i]['title']+' · '+hits[i]['source'],key='ai_sources_'+hashlib.sha256(json.dumps(hits,ensure_ascii=False).encode()).hexdigest()[:12])
        sources=[hits[i] for i in indices]
        if not sources: return
        try: request=payload(question,sources,model)
        except ValueError as exc: st.info(str(exc)); return
        token=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
        st.markdown('**실제 전송 내용: 질문 + 아래 선택한 발췌 + 엔지니어 검토용 지시문**')
        st.text(request['input'])
        st.caption('함께 전송하는 지시문')
        st.text(request['instructions'])
        st.caption('도면·전체 DB·API 키를 근거 본문에 넣지 않습니다. store=false는 서비스의 모든 보관을 없앤다는 뜻은 아닙니다. 승인된 자료만 선택하세요.')
        consent=st.checkbox('위 근거의 외부 전송과 API 호출 비용을 확인했습니다.',key='ai_consent_'+token)
        if st.button('선택 근거로 외부 AI 검토 초안 요청',disabled=not consent or not key):
            st.session_state.pop('external_ai_answer',None)
            try:
                with st.spinner('선택한 근거로 AI 검토 초안을 요청 중입니다…'):
                    answer=ask(key,request,len(sources))
                st.session_state['external_ai_answer']=(token,answer)
            except ValueError as exc: st.error(str(exc))
        answer=st.session_state.get('external_ai_answer')
        if answer and answer[0]==token:
            st.warning('AI 검토 초안 · 원문과 인용의 실제 의미를 엔지니어가 확인하세요. 자동 원인 확정·조치 실행·Library 학습은 하지 않습니다.')
            st.text(answer[1])
            for i,source in enumerate(sources,1): st.caption(f'[{i}] '+source['title']+' · '+source['source'])
            st.download_button('AI 검토 초안 TXT 저장',answer[1]+'\n\n'+'\n'.join(f'[{i}] '+r['title']+' / '+r['source'] for i,r in enumerate(sources,1)),'AI_Review_Draft.txt','text/plain')


def equipment():
    st.subheader('도면 부품 Mapping')
    with st.expander('실제 도면 없이 체험하기'):
        from PIL import Image,ImageDraw
        sketch=Image.new('RGB',(900,400),'white');pen=ImageDraw.Draw(sketch)
        pen.rectangle((50,60,850,330),outline='#244b60',width=4)
        for label,box in [('HEATER',(100,120,270,270)),('BLOWER',(370,120,530,270)),('SENSOR',(650,120,760,270))]:
            pen.rectangle(box,outline='#1b8190',width=3);pen.text((box[0]+20,box[1]+55),label,fill='black')
        buf=BytesIO();sketch.save(buf,format='PNG')
        st.download_button('가상 설비 개념도 PNG 받기',buf.getvalue(),'Synthetic_Equipment.png','image/png')
        st.caption('이 개념도를 아래에 업로드하면 부품 좌표와 기록 재생을 체험할 수 있습니다. 실제 설비 도면이 아닙니다.')
    drawing=st.file_uploader('도면 PNG/JPEG · PDF/CAD는 이미지로 내보낸 후 등록',type=['png','jpg','jpeg'],key='drawing_upload')
    if drawing is not None:
        if drawing.size>10*1024*1024: st.error('10 MB 이하 도면을 사용하세요.'); return
        from PIL import Image,ImageDraw
        try:
            im=Image.open(BytesIO(drawing.getvalue()))
            if im.width*im.height>25000000: raise ValueError('도면 해상도는 2,500만 화소 이하로 사용하세요.')
            im.load()
            digest=hashlib.sha256(drawing.getvalue()).hexdigest(); shown=im.convert('RGB')
            pen=ImageDraw.Draw(shown)
            for index,c in enumerate(lib.entries('component'),1):
                if c['drawing']==digest:
                    x=c['x']/100*shown.width;y=c['y']/100*shown.height
                    pen.ellipse((x-10,y-10,x+10,y+10),fill='orange',outline='black');pen.text((x+12,y),str(index),fill='red')
            st.image(shown,caption='표시 번호는 아래 부품 목록의 번호입니다. 좌표 기준: 좌상단 0%, 우하단 100%.',width='stretch')
        except (ValueError,OSError,Image.DecompressionBombError) as exc: st.error(str(exc)); return
        with st.form('component_mapping'):
            eq=st.text_input('설비 호기'); family=st.text_input('공통 설비 형식 · 제조사 대신 내부 식별자')
            part=st.text_input('부품 이름'); tag=st.text_input('센서 태그 ID')
            x=st.number_input('X 위치 (%)',0.,100.,50.); y=st.number_input('Y 위치 (%)',0.,100.,50.)
            unit=st.text_input('측정 단위',value='A')
            limits=st.checkbox('측정 관리 기준 등록'); lo=st.number_input('하한',value=0.); hi=st.number_input('상한',value=10.)
            failure=st.text_area('가능한 고장 양상·확인 방법')
            if st.form_submit_button('도면에 부품 등록'):
                try:
                    lib.save('component',dict(equipment=eq,family=family,part=part,tag=tag,x=x,y=y,unit=unit,lower=lo if limits else None,upper=hi if limits else None,drawing=digest,failure=failure)); st.rerun()
                except ValueError as exc: st.error(str(exc))
    components=lib.entries('component')
    if components:
        st.dataframe([{'번호':i,'설비':r['equipment'],'형식':r.get('family',''),'부품':r['part'],'태그':r.get('tag',''),'도면 ID':r['drawing'][:10],'X(%)':r['x'],'Y(%)':r['y'],'점검':r.get('failure','')} for i,r in enumerate(components,1)],hide_index=True)
    if components:
        family=st.selectbox('동일 형식 횡전개 검토',sorted({r.get('family','미등록') or '미등록' for r in components}))
        linked={r['equipment'] for r in components if (r.get('family') or '미등록')==family}
        related=[r for r in lib.entries('case') if r.get('equipment') in linked]
        st.caption('동일 내부 형식의 호기: '+', '.join(sorted(linked)))
        if related: st.dataframe([{'설비':r['equipment'],'원인 가설':r['hypothesis'],'조치':r['action'],'결과':r.get('result',''),'검토 상태':r['state']} for r in related],hide_index=True)
        else: st.caption('연결된 개선 사례 없음 · 사례의 대상 설비를 호기 ID와 동일하게 입력하면 연결됩니다.')
    st.subheader('Health Check · 기록 재생')
    st.caption('실제 PLC 연결은 없습니다. 시간대가 있는 time, value, quality(GOOD/BAD) 배열 JSON을 사용합니다. 장비 정지·제어 기능은 없습니다.')
    if not components: st.info('도면에 부품을 먼저 등록하면 측정 기록을 연결할 수 있습니다.'); return
    selected=st.selectbox('상태 확인 부품',components,format_func=lambda r:r['equipment']+' / '+r['part'])
    telemetry=st.file_uploader('측정 기록 JSON',type=['json'],key='telemetry_upload')
    sample=[{'time':(datetime.now(timezone.utc)+timedelta(seconds=i-60)).isoformat(),'value':5+i*.08,'quality':'GOOD'} for i in range(61)]
    st.download_button('합성 측정 기록 예시 다운로드',json.dumps(sample,indent=2),'telemetry_example.json','application/json')
    if telemetry is not None:
        try:
            if telemetry.size>2*1024*1024: raise ValueError('2 MB 이하 기록만 지원합니다.')
            records=json.loads(telemetry.getvalue())
            if not isinstance(records,list) or not 1<=len(records)<=10000: raise ValueError('1~10000개 측정값 배열이 필요합니다.')
            times=[datetime.fromisoformat(r['time']) for r in records]
            if any(t.tzinfo is None for t in times) or times!=sorted(times): raise ValueError('시간대가 있는 오름차순 시각이 필요합니다.')
            cursor=st.slider('재생 위치',0,len(records)-1,0) if len(records)>1 else 0
            now=st.text_input('판정 기준 시각',datetime.now(timezone.utc).isoformat())
            status=lib.health(records[cursor],selected['lower'],selected['upper'],now)
            st.metric('선택 기록 상태',status)
            st.line_chart(pd.DataFrame(records[:cursor+1]),x='time',y='value')
            st.caption('단위: '+selected['unit']+' · 수신 후 60초 초과는 지연 표시. GOOD은 입력 품질 코드이며 센서 고장 부재를 보증하지 않습니다.')
        except (ValueError,TypeError,KeyError) as exc: st.error(str(exc))
