"""Inspection suggestions are not diagnoses or universal replacement intervals."""
from .core import ts, finite

OVEN='https://www.despatch.com/pdfs/PM-TAD-TFD-Elect.pdf'
SENSOR='https://support.watlow.com/epm/en-us/Content/E-Maintenance/Calibrating_IO.htm'
HEPA='https://www.camfil.com/damdocuments/29914/29840/faq-hepas-and-ulpas-technical-bulletin.pdf'
USER='사용자 제공 부품 목록 · 아래 점검 주기는 초기 관리안, 제조사 교체 수명 아님'
# component, engineering check, evidence. No universal lifespan values are assigned.
CHECKS={
 'CZ':[
 ('카트리지 필터','매교대 차압·유량 확인 / 주 1회 추세 검토. 제조사 최종 차압 또는 여과 성능 기준 이탈 시 교체 검토',USER),
 ('Hot dry HEPA 필터','매교대 차압·풍량 확인. 내열 등급·누설·손상과 제조사 최종 차압 기준으로 교체 판단',HEPA),
 ('롤러 오링','매교대 미끄럼·이송 자국 확인 / 주 1회 경화·팽윤·균열 점검. 손상 또는 이송 성능 이탈 시 교체 검토',USER),
 ('롤러 샤프트 부싱·헬리컬 기어','주 1회 유격·마모분·소음 확인 / 월 1회 편심·맞물림 점검. 허용 공차 이탈 시 교체 검토',USER),
 ('제품 감지 센서','매교대 감지·알람 기능 확인 / 주 1회 렌즈·정렬 확인. 반복 오감지 시 세척·조정 후 재시험',USER),
 ('디지털 공압·수압·온도·농도 센서','매교대 추세 대조 / 월 1회 기준 계측기 대조. 교정 허용오차 이탈 시 교정·수리·교체 검토',USER),
 ('피커 패드','매교대 흡착·진공 누설 확인 / 주 1회 마모·찢김 확인. 유지력 저하 시 교체 검토',USER),
 ('오리발형 노즐','매교대 분사 패턴 확인 / 주 1회 막힘·마모 확인. 세척 후에도 분사 불균일이면 교체 검토',USER)],
 'LAMINATION':[
 ('SUS Plate','매교대 표면 오염·찍힘 확인 / 월 1회 평탄도 확인. 제품 전사 자국·허용 평탄도 이탈 시 보수·교체 검토',USER),
 ('Rubber Plate','매교대 오염·찍힘 확인 / 주 1회 균열·경화·압축 변형 확인. 가압 균일성 이탈 시 교체 검토',USER),
 ('온도 센서','월 1회 기준 계측기 대조 / 지정 교정기한 확인. 드리프트·교정 허용오차 이탈 시 조치',SENSOR),
 ('정밀 위치 센서','매교대 원점·알람 확인 / 월 1회 반복 정밀도 확인. 설정값과 실제 Plate 위치 편차 점검',USER)],
 'PREBAKE':[], 'CURE':[], 'HIGH_BAKE':[]}
COMMON=[('온도 센서','월 1회 기준 계측기 대조 / 지정 교정기한 확인. 부착 위치·배선·제품 프로파일과 대조',SENSOR),
 ('HEPA 필터','매교대 차압·풍량 확인. 내열 등급·누설·손상 및 제조사 최종 차압 기준으로 교체 판단',HEPA),
 ('기판 낙하 센서','매교대 감지·인터록 기능 확인 / 주 1회 렌즈·정렬 확인. 반복 오감지 원인 점검',USER),
 ('냉각·히팅 블로워','매교대 소음·풍량 확인 / 월 1회 진동·전류·회전 방향 점검. 베어링 상태·덕트 막힘 확인',OVEN),
 ('히터','월 1회 출력·전류 및 승온 시간 비교. 출력 저하 원인 확인 후 수리·교체 검토',OVEN)]
TUNNEL=[('행거','매교대 체결·기판 접촉 확인 / 월 1회 변형·수평 확인. 체결력·위치별 제품 온도와 대조',USER),
 ('SUS 타공판','주 1회 오염·막힘·변형 확인. 풍량 분포와 제품 위치별 온도 차이 대조',USER),
 ('칠러','매교대 공급·환수 온도와 알람 확인 / 월 1회 냉각 성능·유량·누설 확인',USER)]
CHECKS['PREBAKE']=COMMON+TUNNEL
CHECKS['CURE']=COMMON+TUNNEL
CHECKS['HIGH_BAKE']=COMMON+[
 ('Window Frame','매교대 체결·손상 확인 / 월 1회 변형·수평 확인. 제품 접촉·적재 방향 대조',USER),
 ('Window Frame 롤러 샤프트·오링','매교대 이송·미끄럼 확인 / 주 1회 마모·균열·편심 점검. 이송 반복성 이탈 시 교체 검토',USER),
 ('Window Frame 지지 링크발','매교대 체결·지지 상태 확인 / 월 1회 유격·마모·수평 점검. 허용 공차 이탈 시 교체 검토',USER)]


def status(record, at):
    if not record or not record.get('source'): return '수명 기준 미등록'
    flags=[]
    if record.get('due_at'):
        remain=(ts(record['due_at'])-ts(at)).total_seconds()/86400
        flags.append('기한 초과' if remain<0 else '기한 도달' if remain==0 else '기한 임박' if record.get('warning_days') is not None and remain<=record['warning_days'] else '등록 기한 전')
    used=record.get('used_hours'); limit=record.get('limit_hours')
    if finite(used) and finite(limit) and limit>0:
        remain=limit-used
        flags.append('사용시간 초과' if remain<0 else '사용시간 도달' if remain==0 else '사용시간 임박' if record.get('warning_hours') is not None and remain<=record['warning_hours'] else '등록 시간 이내')
    return ' / '.join(flags) or '수명 기준 미등록'


def recommendations(data,runs):
    rows=[]
    for run in runs:
        for component,action,source in CHECKS.get(run['step'],[]):
            records=[r for r in data.get('maintenance',[]) if r.get('equipment')==run['equipment'] and r.get('component')==component and ts(r['available_at'])<=ts(run['end'])]
            record=max(records,key=lambda r:ts(r['available_at']),default=None)
            rows.append({'공정':run['step'],'설비':run['equipment'],'점검 대상':component,'판정':status(record,run['end']),
                         '권장 검토·개선':action,'주기 성격':'점검 주기 초안 · 제조사 교체 수명 아님','점검 근거':source,'수명 기준 출처':record.get('source') if record else None,
                         '교체·교정 기한':record.get('due_at') if record else None})
    return rows


def validate_maintenance(data):
    rows=data.get('maintenance',[])
    if not isinstance(rows,list) or len(rows)>10000: raise ValueError('설비 정비 이력 형식 오류')
    for r in rows:
        if not isinstance(r,dict) or not all(isinstance(r.get(k),str) and r[k] for k in ('equipment','component','available_at')): raise ValueError('정비 이력 식별 정보 누락')
        ts(r['available_at'])
        if r.get('due_at'): ts(r['due_at'])
        for k in ('used_hours','limit_hours','warning_days','warning_hours'):
            if r.get(k) is not None and (not finite(r[k]) or r[k]<0): raise ValueError('정비 시간·임박 기준은 0 이상의 유한값이어야 합니다.')


def for_candidate(result,candidate):
    steps={'CZ'} if '약액' in candidate else {'LAMINATION'} if '적층' in candidate else {'PREBAKE','CURE','HIGH_BAKE'} if '열처리' in candidate else set()
    abnormal={r['step'] for r in result.get('signals',[]) if r['status']=='OUTSIDE'}
    if steps & abnormal: steps=steps & abnormal
    merged={}
    for row in result.get('maintenance_recommendations',[]):
        if row['공정'] not in steps: continue
        key=row['점검 대상']
        if key not in merged: merged[key]={'점검 대상':key,'권장 검토·개선':row['권장 검토·개선'],'수명·정비 상태':[]}
        merged[key]['수명·정비 상태'].append(row['설비']+': '+row['판정'])
    return [{**v,'수명·정비 상태':' / '.join(v['수명·정비 상태'])} for v in merged.values()]
