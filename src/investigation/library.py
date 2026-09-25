"""Local engineering evidence library. No automatic training or equipment control."""
import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DEFAULT_DB = Path(__file__).resolve().parents[2] / 'instance' / 'engineering_library.sqlite3'

def connect(path=None):
    path=Path(path or DEFAULT_DB); path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, kind TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
    return db

def entries(kind=None,path=None):
    with connect(path) as db:
        rows=db.execute('SELECT id,kind,revision,payload FROM entries'+(' WHERE kind=?' if kind else '')+' ORDER BY rowid', (kind,) if kind else ()).fetchall()
    return [dict(id=i,kind=k,revision=r,**json.loads(p)) for i,k,r,p in rows]

def validate(kind,p):
    if kind not in ('case','document','component'): raise ValueError('지원하지 않는 기록 유형')
    if not isinstance(p,dict): raise ValueError('기록은 객체여야 합니다.')
    required={'case':['model','lot','owner','hypothesis','action','scope'], 'document':['title','source','text','category'], 'component':['equipment','part','drawing','unit']}[kind]
    if any(not isinstance(p.get(k),str) or not p[k].strip() for k in required): raise ValueError('필수 항목을 모두 입력하세요.')
    if kind=='case':
        from .scenarios import effectiveness
        effectiveness(p['counts'])
        if p.get('state') not in ('계획','진행 중','검토 완료'): raise ValueError('상태 오류')
        if p.get('state')=='검토 완료' and (not p.get('evidence','').strip() or not p.get('reviewer','').strip() or not p.get('result','').strip()): raise ValueError('검토 완료에는 결과·증거·검토자가 필요합니다.')
    if kind=='document' and len(p['text'])>250000: raise ValueError('문서는 25만 자 이하로 등록하세요.')
    if kind=='component':
        for k in ('x','y'):
            if type(p.get(k)) not in (int,float) or not math.isfinite(p[k]) or not 0<=p[k]<=100: raise ValueError('좌표는 0~100%입니다.')
        for k in ('lower','upper'):
            if p.get(k) is not None and (type(p[k]) not in (int,float) or not math.isfinite(p[k])): raise ValueError('기준값 오류')
        if p.get('lower') is not None and p.get('upper') is not None and p['lower']>p['upper']: raise ValueError('하한은 상한 이하이어야 합니다.')

def save(kind,p,record_id=None,revision=None,path=None):
    p=dict(p); validate(kind,p)
    p['saved']=datetime.now(timezone.utc).isoformat()
    ident=record_id or str(uuid4())
    with connect(path) as db:
        if record_id:
            cur=db.execute('UPDATE entries SET payload=?,revision=revision+1 WHERE id=? AND kind=? AND revision=?',(json.dumps(p,ensure_ascii=False,allow_nan=False),ident,kind,revision))
            if cur.rowcount!=1: raise ValueError('다른 작업에서 수정되었습니다. 목록을 새로 읽으세요.')
        else: db.execute('INSERT INTO entries VALUES(?,?,1,?)',(ident,kind,json.dumps(p,ensure_ascii=False,allow_nan=False)))
    return ident

def backup(path=None):
    rows=entries(path=path); raw=json.dumps(rows,sort_keys=True,ensure_ascii=False,allow_nan=False)
    return {'format':'engineering-library-1','records':rows,'sha256':hashlib.sha256(raw.encode()).hexdigest()}

def restore(blob,path=None):
    if blob.get('format')!='engineering-library-1': raise ValueError('백업 형식 오류')
    rows=blob.get('records'); raw=json.dumps(rows,sort_keys=True,ensure_ascii=False,allow_nan=False)
    if hashlib.sha256(raw.encode()).hexdigest()!=blob.get('sha256'): raise ValueError('백업 무결성 오류')
    prepared=[]
    for row in rows:
        p={k:v for k,v in row.items() if k not in ('id','kind','revision')}; validate(row['kind'],p)
        if type(row['revision']) is not int or row['revision']<1: raise ValueError('개정 오류')
        prepared.append((row['id'],row['kind'],row['revision'],json.dumps(p,ensure_ascii=False,allow_nan=False)))
    with connect(path) as db:
        for ident,kind,rev,p in prepared:
            existing=db.execute('SELECT kind,revision,payload FROM entries WHERE id=?',(ident,)).fetchone()
            if existing and (existing[0]!=kind or existing[1]!=rev or json.loads(existing[2])!=json.loads(p)): raise ValueError('같은 ID의 다른 개정이 있습니다. 원본을 덮어쓰지 않습니다.')
            db.execute('INSERT OR IGNORE INTO entries VALUES(?,?,?,?)',(ident,kind,rev,p))
    return len(prepared)

def retrieve(question,documents,limit=5):
    """Local char-ngram retrieval with literal excerpts; no LLM or generated citations."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    chunks=[]
    for d in documents:
        for start in range(0,len(d['text']),700):
            text=d['text'][start:start+900]
            if text.strip(): chunks.append({'id':d['id'],'title':d['title'],'source':d['source'],'category':d['category'],'offset':start+1,'excerpt':text})
    if not chunks or len(question.strip())<2: return []
    vec=TfidfVectorizer(analyzer='char',ngram_range=(2,4),max_features=30000)
    matrix=vec.fit_transform([r['excerpt'] for r in chunks]); scores=cosine_similarity(vec.transform([question]),matrix).ravel()
    return [dict(chunks[i],score=round(float(scores[i]),3)) for i in scores.argsort()[::-1][:limit] if scores[i]>.02]

def health(sample,lower,upper,now,max_age=60):
    def stamp(s):
        d=datetime.fromisoformat(s)
        if d.tzinfo is None: raise ValueError('시간대 필요')
        return d
    try:
        age=(stamp(now)-stamp(sample['time'])).total_seconds()
        if age<0: return '시각 오류'
        if age>max_age: return '통신 지연·기록 오래됨'
        if sample.get('quality')!='GOOD': return '품질 불량·판정 보류'
        v=sample['value']
        if type(v) not in (int,float) or not math.isfinite(v): return '측정값 오류'
        if lower is None and upper is None: return '기준 미등록'
        return '기준 이탈' if (lower is not None and v<lower) or (upper is not None and v>upper) else '등록 기준 이내'
    except (KeyError,TypeError,ValueError): return '기록 형식 오류'

def equipment_comparison(rows,step,minimum=10):
    """Descriptive same-model/recipe rows supplied by caller; no assignment optimizer."""
    from collections import defaultdict
    groups=defaultdict(list)
    for r in rows:
        if step in r['equipment']: groups[r['equipment'][step]].append(r)
    out=[]
    for eq,rr in groups.items():
        n=sum(r['n'] for r in rr); k=sum(r['abf'] for r in rr)
        rates=[r['y']*100 for r in rr]
        out.append({'설비':eq,'LOT 수':len(rr),'검사 PCS':n,'ABF 대표 PCS':k,'ABF 대표 비율(%)':100*k/n if n else None,
                    'LOT별 최소(%)':min(rates),'LOT별 최대(%)':max(rates),'판정':'비교 가능 · 배정 전 엔지니어 검토' if len(rr)>=minimum else '표본 부족'})
    return sorted(out,key=lambda r:r['ABF 대표 비율(%)'])
