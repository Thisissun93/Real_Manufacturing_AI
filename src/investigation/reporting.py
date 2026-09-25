import html
from .maintenance import for_candidate
from .presentation import table_html, profile_svg, duration_table, display_value, STEPS, STATUS


def build_report(result, review=None):
    from .core import summary_text
    esc=lambda x:html.escape(display_value(x))
    sel=result['selection']; lot=result['lot']; s=result['summary']
    body=f"<h1>제조 이력 조사 보고서</h1><p class='meta'>제작자: 김태양 · Ver1.0 · 엔지니어 검토 초안</p><h2>{esc(lot['model'])} / {esc(lot['id'])}</h2>"
    body+=f"<p>{sel['layer']}층 · {esc(sel['side'])} · {sel['inspection']}회 검사 · 조회 시점 {esc(result['as_of'])}</p>"
    body+='<div class="summary">'+esc(summary_text(result))+'</div>'
    body+=table_html([{'검사 PCS':s['inspected'],'전체 불량 PCS':s['failed'],'ABF 대표 PCS':s['abf_first'],'타 코드·ABF 미확인 PCS':s['other_first_abf_unknown']}])
    predictive=result.get('predictive')
    if predictive:
        body+='<h2>종합 분석 · 예방보전 점검 우선순위</h2><p>관찰 관계와 모델 설명이며 원인 확률·부품 고장 확률이 아닙니다. 공정 간 동일 LOT 중복 집계에 유의하세요.</p>'
        body+=table_html(predictive['recommendations'])
        body+='<h3>시간순 검증</h3>'+table_html([{'항목':k,'결과':v} for k,v in predictive['validation'].items()])
        body+='<h3>SHAP 모델 기여도</h3>'+table_html(predictive['shap'])
        body+='<h3>접근 추세 시나리오</h3>'+table_html([{k:v for k,v in r.items() if k!='early'} for r in predictive['trends'] if r['early']])
    mat=result.get('material_assessment')
    if mat:
        body+='<h2>모델 지정 자재 및 취급 이력</h2>'+table_html([{'자재 개체':mat.get('unit'),'판정':mat['status'],'사용 LOT 수':mat.get('uses'),'해동 횟수':mat.get('thaws'),'보관':mat.get('storage')}])
        body+='<p>'+esc(' / '.join(mat['issues']))+'</p>'+table_html(mat['history'])
    if result.get('custody_summary'):
        body+='<h2>시료 보관 상태</h2>'+table_html(result['custody_summary'])
    body+='<h2>공정 이력</h2>'+table_html([{'공정':STEPS.get(r['step'],r['step']),'설비':r['equipment'],'시작':r['start'],'종료':r['end']} for r in result['runs']])
    body+='<h2>정상 LOT 대비 소요 시간</h2>'+table_html(duration_table(result))
    body+='<p class="caption">동일 모델·개정 AOI PASS LOT 기준. 관측 범위는 관리 규격이 아니며 비교군 3 LOT 미만은 판단 보류합니다.</p>'
    body+='<h2>공정 측정값과 기준</h2>'+table_html([{'공정':STEPS.get(r['step'],r['step']),'인자':r['factor'],'측정값':r['value'],'단위':r['unit'],'하한':r['lower'],'상한':r['upper'],'판정':STATUS.get(r['status'],r['status'])} for r in result['signals']])
    for run in result['runs']:
        p=run.get('profile')
        if isinstance(p,dict):
            body+='<h2>'+esc(STEPS.get(run['step'],run['step']))+' 제품 온도</h2>'+profile_svg(p)
    body+='<h2>Quad별 검사 결과</h2>'
    quads=[]
    for panel in sorted({r['panel'] for r in result['aoi']}):
        for q in range(1,5):
            rr=[r for r in result['aoi'] if r['panel']==panel and r['quad']==q]
            if rr:
                quads.append({'Panel':panel,'Quad':chr(64+q),'검사 PCS':len(rr),'PASS':sum(r['code']=='PASS' for r in rr),'FAIL':sum(r['code']!='PASS' for r in rr)})
    body+=table_html(quads)
    selected=result.get('selected_unit')
    if selected:
        layout=lot.get('layout',{}); loc=selected.get('defect_location')
        body+='<h3>선택 유닛</h3>'+table_html([{'Quad':chr(64+selected['quad']),'Unit':selected['unit'],'대표 판정':selected['code'],
            'X(mm)':loc['x']*layout['unit_width_mm'] if loc and layout else None,'Y(mm)':loc['y']*layout['unit_height_mm'] if loc and layout else None}])
    body+='<h2>원인 후보와 확인시험</h2>'
    for c in result['candidates']:
        body+='<h3>'+esc(c['candidate'])+' · '+esc(c['state'])+'</h3>'+table_html([
            {'항목':'이탈 근거','내용':c['support']}, {'항목':'추가 대조할 정상 LOT','내용':c['counter']},
            {'항목':'부족한 기록','내용':c['missing']}, {'항목':'확인시험','내용':c['next_action']}])
        body+=table_html(for_candidate(result,c['candidate']))
    if result['confirmations']:
        body+='<h2>추가 분석 결과</h2>'+table_html([{'Quad':chr(64+r['quad']),'Unit':r['unit'],'방법':r['method'],'ABF 확인':r['abf_confirmed'],'시각':r['time']} for r in result['confirmations']])
    if result.get('verification_decisions'):
        body+='<h2>확인시험 이후 후보 판단</h2>'+table_html(result['verification_decisions'])
        body+='<p class="caption">엔지니어가 입력한 시험 판정의 집계입니다. 반증은 기록된 검증 범위 내 판단이며 근본 원인 자동 확정이 아닙니다.</p>'
        body+=table_html([{'후보':t['candidate'],'방법':t['method'],'범위':t['scope'],'판정':t['outcome'],'실제 결과':t['result'],'증거':t['evidence'],'담당자':t['owner']} for t in result.get('verification_tests',[])])
    if result.get('effectiveness_results'):
        body+='<h2>조치 전후 관찰 결과</h2>'+table_html(result['effectiveness_results'])
        body+='<p class="caption">엔지니어 입력 수량의 비교이며 통계적 유의성·인과적 개선 효과를 확인한 결과가 아닙니다.</p>'
    if review:
        fields={'owner':'담당자','state':'상태','hypothesis':'원인 가설','action':'확인시험·조치 계획','result':'실제 결과','evidence':'증거·검토자','followup':'효과성 확인 계획','saved':'기록 시각'}
        rows=[{'항목':label,'내용':review.get(k)} for k,label in fields.items() if review.get(k)]
        if rows: body+='<h2>엔지니어 검토</h2>'+table_html(rows)
    body+='<h2>해석 시 유의사항</h2><ul>'+''.join('<li>'+esc(w)+'</li>' for w in result['warnings'])+'</ul>'
    body+='<p class="caption">검토 기준 데이터 식별값: '+esc(result['data_hash'])+'</p>'
    css='body{max-width:1120px;margin:32px auto;padding:0 24px;font-family:Arial,"Malgun Gothic",sans-serif;color:#203747;line-height:1.6}h1,h2{color:#16495a}h2{margin-top:30px;border-bottom:2px solid #cbdde4;padding-bottom:8px}table{border-collapse:collapse;width:100%;font-size:12px;margin:12px 0;table-layout:fixed}td,th{border:1px solid #d6e2e7;padding:8px;text-align:left;overflow-wrap:anywhere;vertical-align:top}th{background:#edf5f7}tbody tr:nth-child(even){background:#fafcfd}.summary{padding:18px;background:#eef7fa;border-left:4px solid #007d85}.caption,.meta{color:#5b7380;font-size:12px;overflow-wrap:anywhere}svg{width:100%;height:auto}button{padding:10px 16px;margin-right:8px}@media print{.toolbar{display:none}body{margin:0;padding:0}thead{display:table-header-group}tr,svg{break-inside:avoid}h2,h3{break-after:avoid}}'
    toolbar='<div class="toolbar"><button onclick="window.print()">인쇄 / PDF</button><button id="save">수정본 HTML 저장</button><p>본문은 직접 편집할 수 있습니다. 변경 후 수정본을 저장하세요.</p></div>'
    script='<script>document.getElementById("save").onclick=()=>{const u=URL.createObjectURL(new Blob(["<!doctype html>"+document.documentElement.outerHTML],{type:"text/html"}));const a=document.createElement("a");a.href=u;a.download="Engineer_Review_Edited.html";a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};</script>'
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>제조 이력 조사 보고서</title><style>'+css+'</style>'+toolbar+'<main contenteditable="true">'+body+'</main>'+script+'</html>'
