"""Current investigation PDF, generated in memory with an embedded Korean font."""
from io import BytesIO
from pathlib import Path
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, PolyLine, Line, String, Rect
from .presentation import STEPS, STATUS, display_value, duration_table
from .core import summary_text
from .thermal import analyze
from .maintenance import for_candidate


def create_pdf(result):
    pdfmetrics.registerFont(TTFont('Nanum',str(Path(__file__).resolve().parents[2]/'assets/fonts/NanumGothic.ttf')))
    normal=ParagraphStyle('body',fontName='Nanum',fontSize=9,leading=14,wordWrap='CJK',spaceAfter=7)
    heading=ParagraphStyle('heading',parent=normal,fontSize=15,leading=21,spaceBefore=10,spaceAfter=10,keepWithNext=True,textColor=colors.HexColor('#143750'))
    candidate_style=ParagraphStyle('candidate',parent=normal,keepWithNext=True)
    story=[]
    def p(value,style=normal): return Paragraph(escape(display_value(value)),style)
    def title(value): story.append(p(value,heading))
    def table(rows):
        if not rows: return
        keys=list(rows[0]); data=[[p(k) for k in keys]]+[[p(r.get(k)) for k in keys] for r in rows]
        t=Table(data,colWidths=[499/len(keys)]*len(keys),repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6f0f5')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#cbd5df')),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6)]))
        story.extend([t,Spacer(1,10)])
    title('제조 이력 조사 요약')
    story.append(p('제작자: 김태양 · Ver1.0 · 가상 데이터 기반 엔지니어 검토 초안'))
    title(result['lot']['model']+' / '+result['lot']['id'])
    s=result['summary']; sel=result['selection']
    story.append(p(f"{sel['layer']}층 / {sel['side']} / {sel['inspection']}회 검사 · 조회 {result['as_of']}"))
    story.append(p(summary_text(result)))
    table([{'검사 PCS':s['inspected'],'불량 PCS':s['failed'],'ABF 대표 PCS':s['abf_first'],'타 코드 PCS':s['other_first_abf_unknown']}])
    predictive=result.get('predictive')
    if predictive:
        title('Engineer Recommendation · 예방보전 우선순위')
        story.append(p('현재 이탈 → 추세 접근 → 이탈·ABF 대표 불량 반복 이력 순서의 점검 제안입니다. 실제 원인이나 고장 확률 순위가 아닙니다. 동일 LOT의 공정별 불량 PCS를 합산하지 마세요.'))
        table([{k:r[k] for k in ('우선순위','설비','근거','권장 점검 부품')} for r in predictive['recommendations']])
        title('모델 검증과 SHAP')
        table([{'항목':k,'결과':v} for k,v in predictive['validation'].items()])
        table([{'인자':r['인자'],'전체 평균 절대 SHAP(%p)':r['평균 절대 SHAP(%p)'],'ABF 대표 불량 LOT 평균 절대 SHAP(%p)':r['ABF 대표 불량 LOT 평균 절대 SHAP(%p)']} for r in predictive['shap'][:6]])
        title('현재 기준 이내의 접근 추세')
        story.append(p('최근 8 LOT의 선형 추세가 유지된다는 조건부 시나리오입니다. 단위는 기준 경계=1인 지수이며 발생 순서·확률·남은 수명의 확정 예측이 아닙니다.'))
        table([{k:r[k] for k in ('설비','인자','다음 1 LOT','다음 2 LOT','다음 3 LOT','추세 신호')} for r in predictive['trends'] if r['early']])
    title('Quad별 결과')
    rows=[]
    for panel in sorted({r['panel'] for r in result['aoi']}):
        for q in range(1,5):
            rr=[r for r in result['aoi'] if r['panel']==panel and r['quad']==q]
            rows.append({'Panel':panel,'Quad':chr(64+q),'검사 PCS':len(rr),'불량 PCS':sum(r['code']!='PASS' for r in rr)})
    table(rows)
    panel=(result.get('selected_unit') or {}).get('panel') or next(iter(sorted({r['panel'] for r in result['aoi']})),None)
    if panel:
        d=Drawing(499,158)
        layout=result['lot'].get('layout',{}); nr=layout.get('rows',4); nc=layout.get('columns',3)
        for r in result['aoi']:
            if r['panel']!=panel: continue
            q=r['quad']-1; index=r['unit']-1
            x=q*125+(index%nc)*110/nc; y=28+(nr-1-index//nc)*110/nr
            d.add(Rect(x,y,110/nc,110/nr,fillColor=colors.HexColor('#d9e8ea' if r['code']=='PASS' else '#c94349'),strokeColor=colors.white,strokeWidth=.15))
        for q in range(4): d.add(String(q*125,145,'Quad '+chr(65+q),fontName='Nanum',fontSize=9))
        d.add(String(0,8,panel+' · 유닛별 PASS: 연회색 / FAIL: 빨강 · 유닛 내부 좌표와 구분',fontName='Nanum',fontSize=8))
        story.append(d)
    title('우선 확인할 원인 후보')
    story.append(p('점검 제안은 실제 설치 부품·설비 매뉴얼 대조 후 적용합니다. 일·주·월 단위 점검 주기는 초기 관리 제안이며 제조사 교체 수명이 아닙니다. 수명 기준과 이력이 없으면 교체 시점을 추정하지 않습니다.'))
    for c in result['candidates']:
        story.append(p(c['candidate']+' · '+c['state'],candidate_style))
        story.append(p('근거: '+(' / '.join(c['support']) or '등록된 이탈 근거 없음')))
        story.append(p('확인: '+c['next_action']))
        if c['state']=='우선 확인': table(for_candidate(result,c['candidate']))
    mat=result.get('material_assessment')
    if mat:
        title('지정 자재 및 취급 이력')
        story.append(p('해당 LOT 사용 완료 시점까지의 노출 조건. 이후 사용 이력은 제외합니다.'))
        table([{'자재 개체':mat.get('unit'),'판정':mat['status'],'사용 LOT':mat.get('uses'),'해동 횟수':mat.get('thaws')}])
        story.append(p(' / '.join(mat['issues']) or mat.get('storage','')))
        table(mat['history'])
    title('정상 LOT 대비 공정 소요 시간')
    table([{k:r[k] for k in ('공정','실제(분)','정상 중앙값(분)','차이(%)','비교')} for r in duration_table(result)])
    title('측정 이탈 및 기록 부족')
    table([{'공정':STEPS.get(r['step'],r['step']),'인자':r['factor'],'측정':r['value'],'단위':r['unit'],'판정':STATUS.get(r['status'],r['status'])} for r in result['signals'] if r['status']!='WITHIN'])
    for run in result['runs']:
        profile=run.get('profile')
        if not profile: continue
        story.append(PageBreak())
        title(STEPS.get(run['step'],run['step'])+' 제품 온도 프로파일')
        d=Drawing(499,210); left,bottom,w,h=42,32,440,150
        values=profile['temperature_c']+profile['reference_c']; low=min(values)-5; high=max(values)+5
        duration=profile['elapsed_s'][-1]
        analysis=analyze(profile)
        for a in analysis['intervals']:
            d.add(Rect(left+w*a['start_s']/duration,bottom,w*(a['end_s']-a['start_s'])/duration,h,
                       fillColor=colors.HexColor('#d8eaff' if a['state']=='저온' else '#ffe4c5'),strokeColor=None))
        for n in range(5):
            y=bottom+h*n/4
            d.add(Line(left,y,left+w,y,strokeColor=colors.HexColor('#dde5ec')))
            d.add(String(0,y-3,f'{low+(high-low)*n/4:.0f} °C',fontName='Nanum',fontSize=8))
        for zone in profile['zones']:
            x=left+w*zone['start_s']/duration
            d.add(Line(x,bottom,x,bottom+h,strokeColor=colors.HexColor('#e7edf2')))
            d.add(String(x,bottom-12,zone.get('label',str(zone['zone'])),fontName='Nanum',fontSize=7))
        for key,color in [('reference_c','#8d99a5'),('temperature_c','#087d95')]:
            indexes=list(range(0,len(profile[key]),max(1,len(profile[key])//900)))
            if indexes[-1]!=len(profile[key])-1: indexes.append(len(profile[key])-1)
            points=[(left+w*profile['elapsed_s'][i]/duration,bottom+h*(profile[key][i]-low)/(high-low)) for i in indexes]
            d.add(PolyLine(points,strokeColor=colors.HexColor(color),strokeWidth=1))
        d.add(String(left,2,f'Zone / 경과 시간 0 ~ {duration/60:.1f}분 · 청록: 측정 / 회색: 기준',fontName='Nanum',fontSize=8))
        story.append(d)
        story.append(p('파랑 음영: 저온 · 주황 음영: 고온. '+analysis['note']))
        table(analysis['zones'])
    if any(result.get(k) for k in ('verification_decisions','verification_tests','effectiveness_results','custody_summary')):
        title('확인시험과 시료 이동')
    table(result.get('verification_decisions',[]))
    for test in result.get('verification_tests',[]):
        story.append(p(' / '.join(str(test.get(k,'')) for k in ('candidate','method','scope','outcome','result','evidence','owner'))))
    table(result.get('effectiveness_results',[]))
    table(result.get('custody_summary',[]))
    review=result.get('engineer_review')
    if review:
        details=[{'항목':label,'내용':review[key]} for key,label in [('owner','담당자'),('state','검토 상태'),('hypothesis','원인 가설'),('action','확인·조치 계획'),('result','실시 결과'),('evidence','증거'),('followup','추적 계획')] if review.get(key)]
        if details: title('엔지니어 검토'); table(details)
    title('해석 범위')
    for warning in result['warnings']: story.append(p(warning))
    story.append(p('데이터 식별값: '+result['data_hash']))
    out=BytesIO()
    def footer(canvas,doc):
        canvas.setFont('Nanum',8); canvas.drawString(48,25,result['lot']['id']); canvas.drawRightString(547,25,str(doc.page))
    SimpleDocTemplate(out,pagesize=(595,842),leftMargin=48,rightMargin=48,topMargin=38,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
