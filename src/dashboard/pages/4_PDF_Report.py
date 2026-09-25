import streamlit as st
from src.investigation.pdf_report import create_pdf
st.title("조사 보고서 PDF")
result=st.session_state.get("current_investigation")
if not result:
    st.info("제조 이력 조사에서 모델과 LOT를 먼저 선택하세요.")
else:
    from src.investigation.custody import entries
    result=dict(result)
    result['custody_summary']=[{'PANEL':r['context']['panel'],'상태':r['state'],'보관 위치':r['location'],'수령자':r['owner']} for r in entries() if r['context']['data_hash']==result['data_hash'] and r['context']['lot']==result['lot']['id']]
    st.write(f"현재 조사: {result['lot']['model']} / {result['lot']['id']}")
    st.caption(f"조회 시점: {result['as_of']} · {result['selection']}")
    st.download_button("조사 요약 PDF 다운로드",create_pdf(result),f"Investigation_{result['lot']['id']}.pdf","application/pdf")
