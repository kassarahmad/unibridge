"""UniBridge demo UI (Streamlit). Talks to the UniBridge API over HTTP like any other consumer.

Run:  uvicorn p14_search.unibridge_main:app --port 8001
      streamlit run frontend/unibridge_app.py
"""

from __future__ import annotations

import requests
import streamlit as st
from unibridge_common import LANGS, NATIVE, ROLES, api_url, browser_language, t

st.set_page_config(page_title="UniBridge", page_icon=":material/school:", layout="wide")

if "lang" not in st.session_state:
    st.session_state.lang = browser_language()
    st.session_state.role = "visitor"
    st.session_state.messages = []

with st.sidebar:
    st.header("UniBridge")
    st.selectbox(f"{t('language')} / Language", LANGS, format_func=NATIVE.get, key="lang",
                 help="UniBridge answers in the language of your question; this sets the interface language.")
    st.selectbox(t("role"), [r["name"] for r in ROLES], key="role", help=t("role_help"))
    try:
        health = requests.get(f"{api_url()}/v1/health", timeout=3).json()
        st.caption(f"API {health['status']} · {api_url()}")
    except requests.RequestException:
        st.error("API not reachable: start `uvicorn p14_search.unibridge_main:app --port 8001`")
    st.caption(t("disclaimer"))

page = st.navigation([
    st.Page("unibridge_pages/ask.py", title=t("ask_page"), icon=":material/chat:", default=True, url_path="ask"),
    st.Page("unibridge_pages/scholarship_guide.py", title=t("guide_page"), icon=":material/checklist:", url_path="scholarship_guide"),
])
page.run()
