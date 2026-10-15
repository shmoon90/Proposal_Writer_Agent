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
    st.Page("ui/app_pages/extraction.py", title="문서 추출", icon=":material/document_scanner:"),
    st.Page("ui/app_pages/requirements.py", title="요구사항", icon=":material/checklist:"),
    st.Page("ui/app_pages/agents.py", title="에이전트·조사", icon=":material/smart_toy:"),
    st.Page("ui/app_pages/deliverables.py", title="산출물", icon=":material/inventory_2:"),
    st.Page(
        "ui/app_pages/build_baseline.py", title="구축: 기준 문서", icon=":material/upload_file:"
    ),
    st.Page(
        "ui/app_pages/changes.py", title="구축: 변경 관리", icon=":material/published_with_changes:"
    ),
]
page = st.navigation(pages, position="sidebar")
page.run()
