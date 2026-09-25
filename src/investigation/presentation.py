"""Human-readable views and figures; no raw dictionaries in the report."""
import html
import math
from datetime import datetime, timezone, timedelta
import pandas as pd
import altair as alt
import streamlit as st
from .thermal import analyze

STEPS={'CZ':'CZ 전처리','PREBAKE':'Pre-bake','LAMINATION':'ABF 밀착','CURE':'ABF Cure','LASER':'Laser Drill','DESMEAR':'Desmear','PLATING':'도금','PATTERN':'회로 형성','HIGH_BAKE':'고온 Baking','AOI':'AOI 검사'}
STATUS={'OUTSIDE':'기준 이탈','WITHIN':'등록 기준 이내','MISSING':'결측','NO_LIMIT':'기준 미등록'}


def profile_chart(profile):
    rows=[]
    zones=profile['zones']
    for t,v,ref in zip(profile['elapsed_s'],profile['temperature_c'],profile['reference_c']):
        z=next((z for z in zones if z['start_s']<=t<z['end_s']),zones[-1])
        for label,value in [('제품 측정 온도',v),('제품 기준 프로파일',ref),('Zone 설정 온도',z['setpoint_c'])]:
            rows.append({'경과 시간(분)':t/60,'경과 초':t,'온도(°C)':value,'계열':label,'Zone':f"Z{z['zone']}"})
    chart=alt.Chart(pd.DataFrame(rows)).mark_line(clip=True).encode(
        x=alt.X('경과 시간(분):Q',axis=alt.Axis(grid=True),scale=alt.Scale(domain=[0,profile['elapsed_s'][-1]/60],nice=False)), y=alt.Y('온도(°C):Q',scale=alt.Scale(zero=False)),
        color=alt.Color('계열:N',scale=alt.Scale(domain=['제품 측정 온도','제품 기준 프로파일','Zone 설정 온도'],range=['#007d85','#8497a5','#e39c28'])),
        tooltip=['경과 초:Q','Zone:N','계열:N',alt.Tooltip('온도(°C):Q',format='.2f')])
    ticks=pd.DataFrame([{'경과 시간(분)':z['start_s']/60,'Zone':f"Z{z['zone']}"} for z in zones])
    rules=alt.Chart(ticks).mark_rule(strokeDash=[3,4],color='#b6c6ce',clip=True).encode(x='경과 시간(분):Q')
    labels=alt.Chart(ticks).mark_text(align='left',dx=4,dy=10,color='#516776',clip=True).encode(x='경과 시간(분):Q',y=alt.value(0),text='Zone:N')
    layers=[]
    for state,color in [('저온','#3182ce'),('고온','#ed8936')]:
        intervals=[{'시작':a['start_s']/60,'종료':a['end_s']/60,'구분':state} for a in analyze(profile)['intervals'] if a['state']==state]
        if intervals:
            layers.append(alt.Chart(pd.DataFrame(intervals)).mark_rect(color=color,opacity=.18,clip=True).encode(x='시작:Q',x2='종료:Q',tooltip=['구분:N','시작:Q','종료:Q']))
    return alt.layer(*layers,chart,rules,labels).properties(height=330).interactive()


def render_profiles(runs):
    for r in runs:
        p=r.get('profile')
        if not isinstance(p,dict):
            if p:
                st.caption('이전 자료에는 연속 온도 기록이 없습니다. 새 예시 데이터를 사용하세요.')
            continue
        with st.expander(STEPS.get(r['step'],r['step'])+' · 연속 제품 온도프로파일',expanded=True):
            # Inline data avoids Altair's default 5,000-row transform limit.
            with alt.data_transformers.enable('default',max_rows=None):
                st.altair_chart(profile_chart(p),width='stretch')
            analysis=analyze(p)
            st.caption('파랑 음영: 기준보다 낮음 · 주황 음영: 기준보다 높음. '+analysis['note'])
            if analysis['zones']:
                df=pd.DataFrame(analysis['zones'])
                st.dataframe(df.style.apply(lambda row:['background-color: #fff0dc' if row['판정']!='기준 이내' else '' for _ in row],axis=1),hide_index=True,width='stretch')
            st.caption('1초 간격 기록 · X축: 경과 시간(분), 점선: Zone 진입. 설정 온도와 제품 측정값은 승온·냉각 지연 때문에 다를 수 있습니다. 판정은 제품 기준 프로파일과 비교합니다.')
            st.dataframe(pd.DataFrame([{'Zone':f"Z{z['zone']}",'진입(분)':round(z['start_s']/60,2),'종료(분)':round(z['end_s']/60,2),'설정 온도(°C)':z['setpoint_c']} for z in p['zones']]),hide_index=True,width='stretch')


def unit_geometry(rows,layout):
    nc=layout.get('columns') if layout else None
    nr=layout.get('rows') if layout else None
    if not nc:
        nc=max(1,len({r['x'] for r in rows})); nr=max(1,len({r['y'] for r in rows}))
    return [dict(r,행=r.get('row',(r['unit']-1)//nc+1),열=r.get('column',(r['unit']-1)%nc+1),판정='PASS' if r['code']=='PASS' else 'FAIL') for r in rows],nc,nr


def render_aoi(result):
    st.subheader('Quad → 유닛 → 대표 불량 위치')
    if not result['aoi']:
        st.info('선택 조건에 검사 기록이 없습니다.'); return None
    layout=result['lot'].get('layout',{})
    panel=st.selectbox('Panel',sorted({r['panel'] for r in result['aoi']}))
    quads=[]
    for q in range(1,5):
        rr=[r for r in result['aoi'] if r['quad']==q and r['panel']==panel]
        quads.append({'Quad':chr(64+q),'검사 PCS':len(rr),'PASS':sum(r['code']=='PASS' for r in rr),'FAIL':sum(r['code']!='PASS' for r in rr)})
    st.dataframe(pd.DataFrame(quads),hide_index=True,width='stretch')
    quad=st.radio('상세 Quad',['A','B','C','D'],horizontal=True)
    rows=[r for r in result['aoi'] if r['panel']==panel and r['quad']==ord(quad)-64]
    if not rows:
        st.info('해당 Quad 기록이 없습니다.'); return None
    geometry,nc,nr=unit_geometry(rows,layout)
    context=f"{result['data_hash'][:10]}-{result['lot']['id']}-{result['selection']}-{panel}-{quad}"
    pick=alt.selection_point(name='unit_pick',fields=['unit'],on='click',clear='dblclick')
    cells=alt.Chart(pd.DataFrame(geometry)).mark_rect(stroke='white',strokeWidth=1).encode(
        x=alt.X('열:O',axis=alt.Axis(labelAngle=0,title='유닛 열')),
        y=alt.Y('행:O',axis=alt.Axis(title='유닛 행')),
        color=alt.Color('판정:N',scale=alt.Scale(domain=['PASS','FAIL'],range=['#d9ebe5','#d74444'])),
        opacity=alt.condition(pick,alt.value(1),alt.value(.65)),
        tooltip=[alt.Tooltip('unit:Q',title='Unit ID'),'행:Q','열:Q','판정:N',alt.Tooltip('code:N',title='대표 불량')]).add_params(pick)
    labels=alt.Chart(pd.DataFrame(geometry)).mark_text(fontSize=9,color='#20384c').encode(x='열:O',y='행:O',text='unit:Q')
    event=st.altair_chart((cells+labels).properties(height=max(350,nr*23)),width='stretch',on_select='rerun',selection_mode='unit_pick',key='map-'+context)
    st.caption('격자의 유닛을 클릭하면 아래에 해당 유닛의 위치를 표시합니다. 초록은 PASS, 빨강은 FAIL입니다.')
    selected=event.selection.get('unit_pick',[])
    initial=next((r['unit'] for r in rows if r['code']!='PASS'),rows[0]['unit'])
    if selected and selected[0].get('unit') in {r['unit'] for r in rows}:
        initial=int(selected[0]['unit'])
    row=next(r for r in rows if r['unit']==initial)
    st.markdown(f"#### Quad {quad} · Unit {initial} · {'PASS' if row['code']=='PASS' else 'FAIL'}")
    location=row.get('defect_location')
    w,h=layout.get('unit_width_mm'),layout.get('unit_height_mm')
    if row['code']=='PASS':
        st.success('AOI PASS · 저장된 대표 불량 위치가 없습니다.')
    elif not location or not w or not h:
        st.warning('대표 불량 코드는 있으나 유닛 내부 위치 또는 치수 기록이 없습니다. 위치를 추정하지 않았습니다.')
    else:
        st.write(f"대표 불량: **{row['code']}** · 유닛 크기: **{w} × {h} mm**")
        point=pd.DataFrame([{'X(mm)':location['x']*w,'Y(mm)':location['y']*h,'대표 불량':row['code']}])
        detail=alt.Chart(point).mark_point(size=220,color='#d74444',filled=True).encode(
            x=alt.X('X(mm):Q',scale=alt.Scale(domain=[0,w],nice=False),axis=alt.Axis(grid=True)),
            y=alt.Y('Y(mm):Q',scale=alt.Scale(domain=[h,0],nice=False),axis=alt.Axis(grid=True)),
            tooltip=[alt.Tooltip('X(mm):Q',format='.3f'),alt.Tooltip('Y(mm):Q',format='.3f'),'대표 불량:N']).properties(height=380,width=380)
        st.altair_chart(detail,width='content')
        st.caption('원점은 유닛 좌측 상단입니다. 저장된 최초 대표 불량의 위치만 표시하며 다른 결함 유무·위치는 추정하지 않습니다. 앞·뒷면은 각각 검사 좌표계로 표시합니다.')
    return row


def duration_table(result):
    return [{'공정':STEPS.get(r['step'],r['step']),'실제(분)':round(r['actual_min'],2),'정상 LOT 수':r['normal_n'],
             '정상 중앙값(분)':round(r['normal_median_min'],2) if r['normal_median_min'] is not None else None,
             '정상 최소(분)':round(r['normal_min'],2) if r['normal_min'] is not None else None,
             '정상 최대(분)':round(r['normal_max'],2) if r['normal_max'] is not None else None,
             '차이(분)':round(r['difference_min'],2) if r['difference_min'] is not None else None,
             '차이(%)':round(r['difference_pct'],1) if r['difference_pct'] is not None else None,'비교':r['comparison']} for r in result.get('durations',[])]


def display_value(value):
    if value is None: return '—'
    if isinstance(value,bool): return '확인' if value else '미확인'
    if isinstance(value,float): return f'{value:,.3f}'.rstrip('0').rstrip('.') if math.isfinite(value) else '—'
    if isinstance(value,list): return ' · '.join(display_value(v) for v in value) or '없음'
    if isinstance(value,str) and len(value)>18 and value[4]=='-' and 'T' in value:
        try:
            stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
            if stamp.tzinfo:
                return stamp.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    return str(value)


def table_html(rows):
    if not rows: return '<p>해당 기록 없음</p>'
    esc=lambda v:html.escape(display_value(v))
    keys=list(rows[0])
    return '<table><thead><tr>'+''.join('<th>'+esc(k)+'</th>' for k in keys)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(r.get(k))+'</td>' for k in keys)+'</tr>' for r in rows)+'</tbody></table>'


def profile_svg(p):
    width,height,left,top=900,250,55,25
    xmax=max(p['elapsed_s']); ymin=0; ymax=max(max(p['temperature_c']),max(z['setpoint_c'] for z in p['zones']))+12
    x=lambda t:left+t/xmax*(width-left-15)
    y=lambda v:height-35-v/ymax*(height-top-35)
    svg=f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="제품 온도프로파일">'
    for a in analyze(p)['intervals']:
        color='#3182ce' if a['state']=='저온' else '#ed8936'
        svg+=f'<rect x="{x(a["start_s"]):.1f}" y="{top}" width="{x(a["end_s"])-x(a["start_s"]):.1f}" height="{height-35-top}" fill="{color}" opacity="0.18"/>'
    for v in range(0,int(ymax)+1,25):
        svg+=f'<path d="M{left} {y(v):.1f}H{width-15}" stroke="#dde4e8"/><text x="5" y="{y(v):.1f}" font-size="11">{v}°C</text>'
    for z in p['zones']:
        xx=x(z['start_s'])
        svg+=f'<path d="M{xx:.1f} {top}V{height-35}" stroke="#aabcc5" stroke-dasharray="3 4"/><text x="{xx+3:.1f}" y="15" font-size="11">Z{z["zone"]}</text><text x="{xx:.1f}" y="{height-10}" font-size="10">{z["start_s"]/60:.1f}분</text>'
    for key,color in [('reference_c','#8497a5'),('temperature_c','#007d85')]:
        points=' '.join(f'{x(t):.1f},{y(v):.1f}' for t,v in zip(p['elapsed_s'],p[key]))
        svg+=f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.6"/>'
    return svg+'</svg><p class="caption">청록: 측정 · 회색: 기준 · 파랑 음영: 저온 · 주황 음영: 고온</p><p>'+html.escape(analyze(p)['note'])+'</p>'+table_html(analyze(p)['zones'])
