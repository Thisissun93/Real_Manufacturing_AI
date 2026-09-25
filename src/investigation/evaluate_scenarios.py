"""Acceptance checks against authored expectations, not field diagnostic accuracy."""
import json
from pathlib import Path
from .demo import make_demo
from .core import investigate
from .scenarios import CASES

def run():
    checks=[]
    for seed in (721,991,1823):
        d,_=make_demo(seed=seed)
        for lot,label,candidate,state,failed in CASES:
            r=investigate(d,lot)
            observed=next(c['state'] for c in r['candidates'] if c['candidate']==candidate)
            ok=observed==state and bool(r['summary']['failed'])==failed
            if lot=='DEMO-0081': ok=ok and sum(c['state']=='우선 확인' for c in r['candidates'])>=2
            if lot=='DEMO-0085': ok=ok and not any(s['status']=='OUTSIDE' for s in r['signals'])
            checks.append({'seed':seed,'lot':lot,'case':label,'expected':state,'observed':observed,'passed':ok})
    result={'scope':'작성된 합성 시나리오 수용 검증. 현장 원인 진단 정확도·독립 외부 검증 아님.','passed':sum(c['passed'] for c in checks),'total':len(checks),'checks':checks}
    p=Path(__file__).resolve().parents[2]/'docs/scenario_validation.json'
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Scenario acceptance: {result['passed']}/{result['total']}")
    if result['passed']!=result['total']: raise AssertionError('시나리오 기대 결과 불일치')
    return result

if __name__=='__main__': run()
