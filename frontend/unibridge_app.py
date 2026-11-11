"""UniBridge demo UI (Streamlit). Talks to the UniBridge API over HTTP like any other consumer.

Run:  uvicorn p14_search.unibridge_main:app --port 8001
      streamlit run frontend/unibridge_app.py
"""

from __future__ import annotations

import requests
import streamlit as st
from unibridge_common import LANGS, ROLES, api_url

st.set_page_config(page_title="UniBridge", page_icon=":material/school:", layout="wide")

if "lang" not in st.session_state:
    st.session_state.lang = "en"
    st.session_state.role = "visitor"
    st.session_state.messages = []

with st.sidebar:
    st.header("UniBridge")
    st.segmented_control("Language / Lingua / اللغة", list(LANGS), format_func=LANGS.get, key="lang", required=True)
    st.selectbox("Role", [r["name"] for r in ROLES], key="role",
                 help="visitor = public documents; student = + student-only notices; office roles = + that office's internal notes.")
    try:
        health = requests.get(f"{api_url()}/v1/health", timeout=3).json()
        st.caption(f"API {health['status']} · {api_url()}")
    except requests.RequestException:
        st.error("API not reachable: start `uvicorn p14_search.unibridge_main:app --port 8001`")
    st.caption("Prototype for a university project (Complex Systems Design, UNICAM). Not an official service of UNICAM or ERDIS.")

page = st.navigation([
    st.Page("unibridge_pages/ask.py", title="Ask", icon=":material/chat:", default=True),
    st.Page("unibridge_pages/scholarship_guide.py", title="Scholarship guide", icon=":material/checklist:"),
])
page.run()
