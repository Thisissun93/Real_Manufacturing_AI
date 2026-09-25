"""Streamlit investigation UI; per-browser-session review state, explicit backup."""
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st
from .core import FORMAT, KST, ROUTE, aoi_summary, backup, fingerprint, investigate, report_html, restore, shift_at, summary_text, ts, validate, validate_review
from .demo import make_demo
from .scenarios import CASES, test_decisions, effectiveness
from .records import inspection_summary
from .presentation import render_profiles, render_aoi, duration_table, STEPS, display_value


ROOT = Path(__file__).resolve().parents[2]


@st.cache_data(max_entries=4,show_spinner=False)
def predictive_summary(data_hash, model, selection, as_of, recipe, _data):
    from .predictive import analyze
    return analyze(_data,model,selection,as_of,recipe)


@st.cache_data
def demo():
    return make_demo()[0]


def frame(rows):
    if rows:
        labels = {"id":"기록 ID", "step":"공정", "equipment":"설비", "start":"시작", "end":"종료", "available_at":"기록 확정 시각", "tank":"탱크", "type":"작업", "cycle":"전체 교체 구간", "dosing_end":"보충 투입 종료", "quantity":"투입량", "quantity_unit":"투입 단위", "record":"근거 기록", "factor":"인자", "value":"측정값", "unit":"단위", "lower":"하한", "upper":"상한", "target":"목표", "status":"판정", "basis":"기준 출처", "lot":"LOT", "model":"모델", "reasons":"연결 근거", "inspected":"검사 PCS", "failed":"불량 PCS", "abf_first":"ABF 대표 PCS", "other_first_abf_unknown":"타 코드·ABF 미확인 PCS", "defect_rate":"전체 불량률", "abf_first_rate":"ABF 대표 불량률", "records":"근거 기록", "reason":"선정 근거", "material":"자재 LOT", "panel":"Panel", "quad":"Quad", "layer":"층", "side":"면", "inspection":"검사 회차", "code":"대표 코드", "time":"시각", "method":"확인 방법", "abf_confirmed":"ABF 확인", "interface":"계면", "selection":"검사 범위", "saved":"저장 시각", "owner":"담당자", "state":"검토 상태", "result":"조치 결과"}
        states = {"OUTSIDE":"기준 이탈", "WITHIN":"등록 기준 이내", "MISSING":"결측", "NO_LIMIT":"기준 미등록", "REPLACE":"전체 교체", "REFILL":"보충", "DAY":"주간", "NIGHT":"야간"}
        display = [{("Unit ID" if k == "unit" and "quad" in r else labels.get(k,k)): states.get(v,STEPS.get(v,display_value(v))) if isinstance(v,str) else display_value(v) if isinstance(v,(list,dict)) or v is None else round(v,3) if isinstance(v,float) else v for k,v in r.items()} for r in rows]
        df=pd.DataFrame(display)
        for column in df.columns:
            if df[column].map(lambda value:isinstance(value,str)).any():
                df[column]=df[column].map(display_value)
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("조건에 맞는 기록이 없습니다.")


def render():
    st.markdown('<style>[data-testid="stMetric"]{background:#f0f6f8;border-radius:10px;padding:14px} h3{color:#173e50} [data-testid="stCaptionContainer"]{line-height:1.6} </style>',unsafe_allow_html=True)
    left, right = st.columns([3, 2])
    left.title("제조 이력 조사 · Ver1.0")
    build = ROOT/"BUILD.json"
    stamp = json.loads(build.read_text(encoding="utf-8"))["built_at"] if build.exists() else "개발 작업본"
    right.caption(f"제작자: 김태양 · 빌드: {stamp}\n\n공개용 합성 조건을 사용하는 시연 프로그램입니다. 참고용으로 사용하세요.")
    st.caption("약액 상태·보충 전후 → 영향 LOT → AOI 위치 → 검증 기록. 전체 스캔 후 최초 대표 코드만 보존하는 AOI를 가정합니다.")
    uploaded = st.sidebar.file_uploader("조사 데이터 JSON (선택)", type="json", key="investigation_upload")
    try:
        if uploaded is not None:
            if uploaded.size > 35*1024*1024:
                raise ValueError("데이터 파일은 35 MB 이하로 제한합니다.")
            data = json.loads(uploaded.getvalue())
            validate(data)
        else:
            data = demo()
    except (ValueError, TypeError, KeyError, OverflowError) as e:
        st.error(f"입력 확인 필요: {e}")
        st.stop()
    with st.sidebar.expander('설비 정비 이력 가져오기 (선택)'):
        maintenance_file=st.file_uploader('정비 이력 JSON 목록',type='json',key='maintenance_records')
        st.caption('설비·부품·기록 시점·교체/교정 기한·수명 근거를 연결합니다. 입력 구조는 재배포 안내를 참고하세요.')
    if maintenance_file is not None:
        try:
            if maintenance_file.size>2*1024*1024: raise ValueError('정비 이력은 2 MB 이하로 제한합니다.')
            from .maintenance import validate_maintenance
            data=dict(data)
            data['maintenance']=json.loads(maintenance_file.getvalue())
            validate_maintenance(data)
        except (ValueError,TypeError,KeyError) as e:
            st.error('정비 이력 확인 필요: '+str(e)); st.stop()
    st.sidebar.download_button("현재 조사 데이터 받기", json.dumps(data, ensure_ascii=False, separators=(",",":")), "Manufacturing_Investigation.json", "application/json")
    with st.sidebar.form('lot_direct_search'):
        query=st.text_input('LOT ID 직접 검색',placeholder='예: DEMO-0046')
        submitted=st.form_submit_button('LOT 검색')
    if submitted:
        hits=[r for r in data['lots'] if r['id'].casefold()==query.strip().casefold()]
        if hits:
            st.session_state['investigation_model']=hits[0]['model']
            st.session_state['investigation_lot']=hits[0]['id']
        else:
            st.sidebar.error('일치하는 LOT ID가 없습니다. 기존 조회를 유지합니다.')
    models=sorted({r['model'] for r in data['lots']})
    if st.session_state.get('investigation_model') not in models:
        st.session_state['investigation_model']=models[0]
    model=st.sidebar.selectbox('제품 모델',models,key='investigation_model')
    model_lots=[r for r in data['lots'] if r['model']==model]
    layout=model_lots[0].get('layout',{})
    if layout:
        st.sidebar.caption(f"{layout['unit_width_mm']} × {layout['unit_height_mm']} mm · Quad당 {layout['pcs_per_quad']:,} PCS · Panel당 {4*layout['pcs_per_quad']:,} PCS")
    choices = [r["id"] for r in model_lots]
    inspections=data['aoi']+data.get('inspection_groups',[])
    if st.session_state.get('investigation_lot') not in choices:
        st.session_state['investigation_lot']='DEMO-0045' if 'DEMO-0045' in choices else choices[0]
    lot = st.sidebar.selectbox("조사 LOT", choices,key='investigation_lot')
    if uploaded is None:
        def open_case(case_lot):
            st.session_state['investigation_model']=next(r['model'] for r in data['lots'] if r['id']==case_lot)
            st.session_state['investigation_lot']=case_lot
        with st.sidebar.expander('원인별 사례·반례 열기'):
            for case_lot,label,*_ in CASES:
                st.button(label,key='case-'+case_lot,on_click=open_case,args=(case_lot,))
    layer = st.sidebar.selectbox("검사층", sorted({r["layer"] for r in inspections}) or [1])
    side = st.sidebar.selectbox("검사면", ["TOP", "BOTTOM"])
    inspection = st.sidebar.selectbox("검사 회차", sorted({r["inspection"] for r in inspections}) or [1])
    latest = max((r["time"] for r in inspections), key=ts, default=data["lots"][-1]["end"])
    as_of = st.sidebar.text_input("조회 기준 시각 (시간대 포함)", latest)
    try:
        result = investigate(data, lot, layer, side, inspection, as_of)
    except (ValueError, TypeError) as e:
        st.error(str(e)); st.stop()
    for warning in result["warnings"]:
        st.warning(warning)
    s = result["summary"]
    columns = st.columns(4)
    for col, label, value in zip(columns, ["검사 PCS", "전체 불량 PCS", "ABF 최초 검출 PCS", "타 코드 · ABF 동반 미확인"], [s["inspected"], s["failed"], s["abf_first"], s["other_first_abf_unknown"]]):
        col.metric(label, value)
    st.caption(f"전체 불량률: {s['defect_rate']:.2%} / AOI ABF 대표 불량률: {s['abf_first_rate']:.2%}" if s["inspected"] else "분모 없음: 불량률 계산 보류")
    st.info(summary_text(result))
    tabs = st.tabs(["1 · 약액·공정 이력", "2 · AOI 위치", "3 · 영향 LOT·비교군", "4 · 근거·확인시험", "5 · 검토·보고서", "검증 및 사용 기준", "6 · 종합·예방보전", "7 · 개선·지식·설비 Library"])
    with tabs[7]:
        from .learning_ui import render as render_learning
        render_learning(data,result)
    with tabs[6]:
        st.subheader('ABF 대표 불량 종합 · Engineer Recommendation')
        context=(result['data_hash'],model,layer,side,inspection,result['as_of'],result['lot']['recipe'])
        if st.button('종합·예방보전 분석 실행'):
            with st.spinner('설비 집계·시간순 검증·SHAP 계산 중'):
                calculated=predictive_summary(result['data_hash'],model,result['selection'],result['as_of'],result['lot']['recipe'],data)
                st.session_state['predictive_result']=(context,calculated)
        saved=st.session_state.get('predictive_result')
        if saved and saved[0]==context:
            result['predictive']=saved[1]
            from .predictive import render_panel
            render_panel(saved[1])
        else:
            st.info('현재 조사 범위에 대해 실행하세요. 다른 모델·검사 조건의 분석은 재사용하지 않습니다.')
    with tabs[0]:
        st.subheader("공정 순서 및 설비 이력")
        frame([{**{k: r[k] for k in ("id", "step", "equipment", "start", "end")}, "교대": shift_at(r["start"])["shift"], "탱크": r.get("tank", ""), "누적 LOT(투입 전)": r.get("bath_lots_before")} for r in result["runs"]])
        st.subheader('정상 LOT 대비 공정 소요 시간')
        timing=duration_table(result)
        if timing:
            df=pd.DataFrame(timing)
            st.dataframe(df.style.map(lambda v:'color:#bd3326;font-weight:bold' if v in ('정상 관측 범위보다 김','정상 관측 범위보다 짧음') else '',subset=['비교']),hide_index=True,width='stretch')
        st.caption('동일 모델·개정의 AOI PASS LOT와 비교합니다. 3 LOT 미만이면 판단을 보류합니다. 관측 최소·최대 범위는 관리 상·하한이 아닙니다. 차이(%) = (실제−정상 중앙값) / 정상 중앙값 × 100.')
        st.subheader("탱크 보충 전후")
        cz = next((r for r in result["runs"] if r["step"] == "CZ"), None)
        if cz and cz.get("tank"):
            events = [e for e in data["tank_events"] if e["tank"] == cz["tank"] and e["cycle"] == cz["cycle"] and ts(e["available_at"]) <= ts(result["as_of"])]
            frame(events)
            tank_rows = []
            for r in data["runs"]:
                if r.get("tank") != cz["tank"] or r.get("cycle") != cz["cycle"] or ts(r["available_at"]) > ts(result["as_of"]):
                    continue
                b = next(b for b in data["lots"] if b["id"] == r["lot"])
                su = inspection_summary(data,r['lot'],layer,side,inspection,result['as_of'])
                tank_rows.append({"LOT": r["lot"], "모델": b["model"], "개정": b["recipe"], "시작": r["start"], "무게 감소 지수": r["parameters"].get("Cu 시편 무게 감소 정규화 지수", {}).get("value"),
                                  "처리 누적": r.get("bath_lots_before"), "검사 PCS": su["inspected"], "불량 PCS": su["failed"], "ABF 대표 PCS": su["abf_first"]})
            tank_rows.sort(key=lambda r: ts(r["시작"]))
            chart = pd.DataFrame(tank_rows).set_index("LOT")[["무게 감소 지수"]]
            limits = cz["parameters"].get("Cu 시편 무게 감소 정규화 지수", {})
            for key, label in (("lower", "선택 LOT 하한"), ("upper", "선택 LOT 상한")):
                if limits.get(key) is not None:
                    chart[label] = limits[key]
            st.line_chart(chart)
            st.caption("점에 마우스를 올리면 LOT·값을 확인할 수 있습니다. 우측 전체 화면 버튼으로 확대하세요. 기준선은 선택 LOT의 등록 기준입니다.")
            frame(tank_rows)
            refills = [e for e in events if e["type"] == "REFILL"]
            if refills:
                event_id = st.selectbox("전후 비교할 보충 이벤트", [e["id"] for e in refills])
                event = next(e for e in refills if e["id"] == event_id)
                n = st.slider("동일 모델 전후 최대 LOT 수", 2, 12, 6)
                model_rows = [r for r in tank_rows if r["모델"] == result["lot"]["model"] and r["개정"] == result["lot"]["recipe"]]
                before = [r for r in model_rows if ts(r["시작"]) < ts(event["start"])][-n:]
                after = [r for r in model_rows if ts(r["시작"]) >= ts(event["end"])][:n]
                aggregates = []
                for label, rows in (("보충 전", before), ("보충 후", after)):
                    vals = [r["무게 감소 지수"] for r in rows if r["무게 감소 지수"] is not None]
                    denominator = sum(r["검사 PCS"] for r in rows)
                    aggregates.append({"구간": label, "LOT 수": len(rows), "지수 평균": sum(vals)/len(vals) if vals else None,
                        "검사 PCS": denominator, "전체 불량률": sum(r["불량 PCS"] for r in rows)/denominator if denominator else None,
                        "ABF 대표 불량률": sum(r["ABF 대표 PCS"] for r in rows)/denominator if denominator else None})
                frame(aggregates)
                st.info("관찰된 전후 차이입니다. 약액 보충 효과의 인과 증거는 아닙니다. 설비·자재·열처리 변경과 검사 수량을 함께 확인하세요.")
            else:
                st.info("조회 시점에 해당 약액 교체 구간의 보충 기록이 없습니다.")
            coupon=cz.get('coupon',{})
            frame([{'처리 전 무게':coupon.get('before'),'처리 후 무게':coupon.get('after'),'기준 무게':coupon.get('reference'),'질량 단위':coupon.get('mass_unit')}])
            st.caption("(처리 전 무게 − 처리 후 무게) ÷ 기준 무게. 동일 질량 단위일 때 무차원. 누락·음수·0 기준값이면 계산 보류.")
        from .presentation import STATUS
        measured=pd.DataFrame([{'공정':STEPS.get(r['step'],r['step']),'인자':r['factor'],'측정값':r['value'],'단위':r['unit'],'하한':r['lower'],'상한':r['upper'],'판정':STATUS.get(r['status'],r['status'])} for r in result['signals']])
        if not measured.empty:
            st.dataframe(measured.style.apply(lambda row:['background-color: #ffe5db; color: #862a13' if row['판정']=='기준 이탈' else 'background-color: #fff3cf' if row['판정']=='결측' else '' for _ in row],axis=1),hide_index=True,width='stretch')
        render_profiles(result['runs'])
    with tabs[1]:
        result['selected_unit']=render_aoi(result)
        from .custody import render_request
        render_request(result)
        st.subheader('단면·추가 분석 결과')
        frame([{**r,'quad':chr(64+r['quad'])} for r in result['confirmations']])
        st.caption('의심 유닛의 선택 검사 결과를 전체 생산 PCS의 ABF 존재율로 확대하지 않습니다.')
    with tabs[2]:
        st.subheader('모델 지정 자재 · 사용 개체 추적')
        material=result['material_assessment']
        st.caption('해당 LOT 자재 사용 완료 시점까지의 노출 조건입니다. 이후 LOT의 사용·해동은 현재 LOT 원인 판단에 포함하지 않습니다.')
        frame([{'모델 지정 자재':material.get('designated'),'사용 자재':material.get('type'),'자재 개체':material.get('unit'),
                '사용 LOT 수':material.get('uses'),'해동 횟수':material.get('thaws'),'판정':material['status'],'보관 상태':material.get('storage')}])
        for issue in material['issues']: st.warning(issue)
        with st.expander('자재 취급 상세 이력'):
            frame(material['history'])
        st.caption('최초 냉동 48h → 냉장 24h → 해동 12h. 재사용 냉장 24h → 해동 12h. 모두 최소 시간. 개체당 6 LOT 사용 종료·잔량 없음, 최대 3회 해동 후 재냉장 금지. 사용자 제공 시연 기준입니다.')
        st.subheader("영향 가능 LOT · 직접 공유 관계")
        st.caption("동일 자재 LOT, 동일 탱크 교체 구간, 동일 공정 설비를 공유한 기록입니다. 공유 관계가 불량 또는 원인을 의미하지 않습니다. 연결을 무한히 확장하지 않습니다.")
        frame(result["related"])
        st.subheader("정상 비교군 · AOI PASS 기준")
        frame(result["controls"])
        frame([{'비교군 제외 사유':k,'LOT 수':v} for k,v in result['exclusions'].items()])
    with tabs[3]:
        for c in result["candidates"]:
            with st.expander(c["candidate"]+" · "+c["state"], expanded=True):
                st.write("지지하는 이탈 기록", " · ".join(c["support"]) or "없음")
                st.write("추가 대조할 정상 LOT", " · ".join(c["counter"]) or "없음")
                st.caption("일부 설비/탱크를 공유한 정상 LOT이며 모든 노출 조건이 같은 것은 아닙니다.")
                st.write("부족한 정보", " · ".join(c["missing"]) or "등록 필드에서 누락 없음. 미수집 인자는 별도 확인 필요.")
                st.write("확인시험 제안", c["next_action"])
                from .maintenance import for_candidate
                checks=for_candidate(result,c['candidate'])
                if checks:
                    st.markdown('**권장 설비 점검·개선 검토**')
                    st.caption('매교대·주간·월간 점검은 초기 관리안입니다. 제조사 권장 교체 수명과 구분하며, 실제 운전 조건으로 검토 후 적용하세요.')
                    frame(checks)
                st.caption(c["limitation"])
        with st.expander('설비별 점검 근거·교체/교정 기한'):
            frame(result['maintenance_recommendations'])
            st.caption('실제 설치 부품과 적용 매뉴얼을 먼저 대조하세요. 기한 경과는 원인 확정이나 자동 교체 지시가 아닙니다. 근거 없는 보편 수명은 생성하지 않습니다.')
        st.warning("AOI 대표 코드만으로 실제 계면 Delamination 여부를 확정하거나 원인 확률을 계산하지 않습니다.")
    with tabs[4]:
        records = st.session_state.setdefault("investigation_reviews", [])
        st.info("검토 기록은 현재 브라우저 세션에만 보관됩니다. 새로고침·서버 재시작 전 백업을 내려받으세요. 서버 공용 파일에는 저장하지 않습니다.")
        context_key = fingerprint({"data": result["data_hash"], "lot": lot, "selection": result["selection"], "as_of": result["as_of"]})[:16]
        with st.form("review_"+context_key):
            owner = st.text_input("담당자")
            state = st.selectbox("검토 상태", ["제안", "진행 중", "검증 완료"])
            hypothesis = st.text_area("원인 가설 및 배제할 대안")
            action = st.text_area("확인시험·조치 계획")
            outcome = st.text_area("실제로 실시한 조치와 결과")
            evidence = st.text_area("증거 문서 번호·측정 결과·검토자")
            followup = st.text_area("효과성 확인 계획: 기간·표본·판정 기준")
            st.markdown('**확인시험 결과 연결**')
            include_test=st.checkbox('이번 기록에 실제 확인시험 결과를 포함')
            test_candidate=st.selectbox('검증할 원인 후보',[c['candidate'] for c in result['candidates']])
            test_method=st.text_input('실시한 시험 방법')
            test_scope=st.text_input('검증 범위·비교 조건·표본')
            test_outcome=st.selectbox('시험에 대한 엔지니어 판정',['판단 불가','지지','반증'])
            st.caption('실제 결과·증거·담당자는 위 입력을 사용합니다. 반증은 입력한 검증 범위에서만 후보를 제외하며 원인 부재를 보증하지 않습니다.')
            with st.expander('조치 후 효과 확인 수량 입력 (선택)'):
                include_effect=st.checkbox('이번 기록에 조치 전후 수량을 포함')
                effect_scope=st.text_input('조치 전후 기간·동일 모델·층·면·검사 기준')
                before_n=st.number_input('조치 전 검사 PCS',min_value=0,value=0,step=1)
                before_failed=st.number_input('조치 전 불량 PCS',min_value=0,value=0,step=1)
                after_n=st.number_input('조치 후 검사 PCS',min_value=0,value=0,step=1)
                after_failed=st.number_input('조치 후 불량 PCS',min_value=0,value=0,step=1)
                minimum_n=st.number_input('전후 각각 필요한 최소 검사 PCS (검토용)',min_value=1,value=30,step=1)
                st.caption('입력한 수량의 관찰 비교입니다. 기본 30은 시연값이며 통계적 표본 설계가 아닙니다. 검증된 개선 효과나 인과성을 의미하지 않습니다.')
            submit = st.form_submit_button("검토 기록 추가")
        if submit:
            entry = {"id": str(uuid4()), "lot": lot, "saved": datetime.now(KST).isoformat(), "owner": owner, "state": state,
                     "result": outcome, "evidence": evidence, "hypothesis": hypothesis, "action": action, "followup": followup,
                     "data_hash": result["data_hash"], "selection": result["selection"], "as_of": result["as_of"],
                     "summary": result["summary"], "signals": result["signals"], "source_records": [r["id"] for r in result["runs"]],
                     'tests':[{'candidate':test_candidate,'method':test_method,'scope':test_scope,'outcome':test_outcome,'result':outcome,'evidence':evidence,'owner':owner}] if include_test else [],
                     'effectiveness':{'before_n':before_n,'before_failed':before_failed,'after_n':after_n,'after_failed':after_failed,'minimum_n':minimum_n,'scope':effect_scope} if include_effect else None}
            try:
                validate_review(entry)
                records.append(entry)
                st.success("기록을 추가했습니다. 백업을 다운로드하세요. 완료 상태는 사용자 선언입니다.")
            except ValueError as e:
                st.error(str(e))
        frame([{k: r.get(k) for k in ("saved", "lot", "owner", "state", "result")} for r in records])
        st.download_button("검토 이력 백업 JSON", json.dumps(backup(records), ensure_ascii=False), "Manufacturing_Review_Backup.json", "application/json")
        restore_file = st.file_uploader("백업 복원", type="json", key="review_restore")
        if st.button("선택 백업을 기존 이력에 병합"):
            try:
                if restore_file is None or restore_file.size > 20*1024*1024:
                    raise ValueError("20 MB 이하 백업을 선택하세요.")
                merged = restore(records, json.loads(restore_file.getvalue()))
                st.session_state["investigation_reviews"] = merged
                st.success(f"복원 완료: {len(merged)}건. 동일 기록은 중복 추가하지 않았습니다.")
            except (ValueError, TypeError, KeyError) as e:
                st.error(str(e))
        records = st.session_state["investigation_reviews"]
        matching = [r for r in records if r["lot"] == lot and r["data_hash"] == result["data_hash"] and r.get("selection") == result["selection"] and r.get("as_of") == result["as_of"]]
        result['verification_tests']=[t for r in matching for t in r.get('tests',[])]
        result['verification_decisions']=test_decisions(result['verification_tests'])
        st.subheader('확인시험 이후 후보 판단')
        frame(result['verification_decisions'])
        effects=[{'저장 시각':r['saved'],**effectiveness(r['effectiveness'])} for r in matching if r.get('effectiveness')]
        result['effectiveness_results']=effects
        if effects:
            st.subheader('조치 전후 효과 확인')
            frame(effects)
        st.caption('같은 데이터·LOT·검사 범위·조회 시점의 시험만 합산합니다. 지지와 반증이 함께 있으면 자동 제외하지 않고 재검증합니다. 자동 원인 확정 기능은 아닙니다.')
        from .custody import entries
        result['engineer_review']=matching[-1] if matching else None
        result['custody_summary']=[{'PANEL':r['context']['panel'],'상태':r['state'],'보관 위치':r['location'],'수령자':r['owner']} for r in entries() if r['context']['data_hash']==result['data_hash'] and r['context']['lot']==lot]
        st.download_button("편집 가능한 조사 보고서 HTML", report_html(result, matching[-1] if matching else None), f"Engineer_Review_{lot}.html", "text/html")
        st.session_state['current_investigation']=result
        if st.button('현재 조사 PDF 준비'):
            from .pdf_report import create_pdf
            st.download_button('현재 조사 요약 PDF 다운로드',create_pdf(result),f'Investigation_{lot}.pdf','application/pdf')
        st.caption("보고서는 내려받아 본문 편집·수정본 저장·인쇄/PDF가 가능합니다. 조건이 다른 과거 검토는 현재 보고서에 자동 삽입하지 않습니다.")
    with tabs[5]:
        st.subheader('시연 사례와 기대 조사 방향')
        frame([{'LOT':c[0],'시연 사례':c[1],'기대 확인 대상':c[2],'기대 표시':c[3]} for c in CASES])
        st.caption('위 목록은 시연 설명용입니다. 조사 규칙은 사례 이름·평가 정답을 읽지 않고 실제 등록값과 검사 이력만 사용합니다.')
        st.markdown("""**분석 및 표시 기준**

- 모델 A: 12 × 12 mm, Quad당 400 PCS. 모델 B: 17 × 17 mm, Quad당 196 PCS. 배열 예시이며 실제 유효 배치 수량 산정은 아닙니다.
- 순수 저항계 표시값은 MΩ 단위로 하한 1을 적용합니다. 비저항(MΩ·cm)으로 변환하지 않습니다.
- 온도는 1초 간격 기록이며 °C로 표시합니다. Zone 설정 온도와 제품 기준·측정 프로파일을 구분합니다.
- AOI 전체 스캔 후 최초 대표 코드만 저장하는 가정입니다. 다른 대표 코드 유닛의 ABF 상태는 미확인입니다.
- 유닛 내부 위치는 해당 대표 불량의 저장 좌표입니다. 위치가 없으면 추정하지 않습니다.
- 약액 보충은 24 LOT, 전체 교체는 48 LOT, 공회전은 12분으로 구성했습니다.
- 검토 기록은 세션에 보관됩니다. 종료 전 백업을 저장하세요.
- 구체적인 계산 검증 방법은 전달된 사용 안내에 수록했습니다.""")
