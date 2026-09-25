import streamlit as st
from src.investigation.custody import render_queue
st.title("시료 불출·수령 관리")
render_queue()
