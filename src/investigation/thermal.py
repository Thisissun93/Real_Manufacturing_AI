"""Compare measured product temperatures to a product reference, never infer cure state."""
def analyze(profile):
    tolerance=profile.get('tolerance_c')
    if tolerance is None:
        return {'zones':[], 'intervals':[], 'note':'제품 기준 프로파일 허용 편차 미등록 · 온도 이탈 판정 보류'}
    times=profile['elapsed_s']; values=profile['temperature_c']; refs=profile['reference_c']
    rows=[]; intervals=[]
    for zone in profile['zones']:
        low=high=0.0; diffs=[]
        for i,t in enumerate(times[:-1]):
            dt=max(0,min(times[i+1],zone['end_s'])-max(t,zone['start_s']))
            if not dt: continue
            diff=values[i]-refs[i]; diffs.append(diff)
            state='저온' if diff < -tolerance else '고온' if diff > tolerance else None
            if state:
                low+=dt if state=='저온' else 0; high+=dt if state=='고온' else 0
                start=max(t,zone['start_s']); end=min(times[i+1],zone['end_s'])
                if intervals and intervals[-1]['end_s']==start and intervals[-1]['state']==state and intervals[-1]['zone']==zone['zone']:
                    intervals[-1]['end_s']=end
                else: intervals.append({'start_s':start,'end_s':end,'state':state,'zone':zone['zone']})
        rows.append({'Zone':zone.get('label',f"Z{zone['zone']}"),'Zone 설정(°C)':zone['setpoint_c'],
                     '저온 노출(초)':round(low,1),'고온 노출(초)':round(high,1),
                     '최저 편차(°C)':round(min(diffs),2) if diffs else None,'최고 편차(°C)':round(max(diffs),2) if diffs else None,
                     '판정':'저온·고온' if low and high else '저온' if low else '고온' if high else '기준 이내'})
    return {'zones':rows,'intervals':intervals,'note':f'제품 기준 프로파일 ±{tolerance:g}°C 대비. 온도 이탈은 미경화·과경화 확정 판정이 아닙니다.'}


def high_bake_profile(hot=190, abnormal=False):
    times=list(range(7201)); reference=[]; actual=[]; ref=measured=26.0
    for t in times:
        target=hot if t<5400 else 30
        ref+=(target-ref)/180
        offset=(-9 if 1800<=t<4800 else 8 if 5700<=t<6900 else 0) if abnormal else 0
        measured+=(target+offset-measured)/180
        reference.append(round(ref,2)); actual.append(round(measured,2))
    return {'elapsed_s':times,'reference_c':reference,'temperature_c':actual,'sample_interval_s':1,
            'tolerance_c':4,'tolerance_basis':'시연용 제품 기준 편차 ±4°C · 양산 사양 미검증',
            'zones':[{'zone':1,'label':'Hot Zone','start_s':0,'end_s':5400,'setpoint_c':hot},
                     {'zone':2,'label':'Cooling Zone','start_s':5400,'end_s':7200,'setpoint_c':30}]}
