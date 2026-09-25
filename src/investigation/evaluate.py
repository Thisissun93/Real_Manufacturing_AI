"""Synthetic observation-bias audit, not model accuracy or field validation."""
from collections import Counter
from pathlib import Path
import json
from .demo import make_demo
from .core import investigate


def run():
    results = []
    for seed in (721, 991, 1823):
        d, truth = make_demo(seed=seed)
        actual = sum(t["abf_present"] for t in truth)
        first = sum(g['codes'].count('ABF') for g in d['inspection_groups'])
        masked = sum(t["abf_present"] and t['representative_code'] != "ABF" for t in truth)
        results.append({"seed":seed,"AOI_records":sum(len(g['codes']) for g in d['inspection_groups']),"synthetic_ABF_present":actual,"ABF_first_code":first,"masked_by_other_first_code":masked,
                        "identity_check":actual == first+masked})
    r = investigate(d, "DEMO-0045")
    report = {"scope":"합성 데이터 관측 편향 검증. 실제 공정 성능·인과성·ML 정확도 검증 아님.",
              "seeds":results,"reference_case":{"lot":r["lot"]["id"],"inspected":r["summary"]["inspected"],"control_lots":len(r["controls"]),"candidates":[c["state"] for c in r["candidates"]]},
              "next_validation":["개발과 독립된 현업 시나리오 검토", "수작업 조사 대비 소요 시간 측정", "원료/설비 노출 효과 분리", "실제 데이터 검증 전 현장 성능 주장 금지"]}
    out = Path(__file__).resolve().parents[2]/"docs"/"investigation_validation.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
