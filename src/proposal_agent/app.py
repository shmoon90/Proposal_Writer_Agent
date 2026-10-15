"""Streamlit 진입점.

실행: ``streamlit run src/proposal_agent/app.py``
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Proposal Writer Agent", page_icon=":material/description:", layout="wide"
)

pages = [
    st.Page("ui/app_pages/home.py", title="시작", icon=":material/home:", default=True),
    st.Page("ui/app_pages/project.py", title="프로젝트", icon=":material/folder_open:"),
]
page = st.navigation(pages, position="sidebar")
page.run()
