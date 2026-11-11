"""Scholarship guide page: facts -> deterministic rules, position in the procedure, checklist and .ics."""

from __future__ import annotations

import datetime as dt

import streamlit as st
from unibridge_common import post, show_text, t

st.title(t("guide_title"))
st.caption(t("guide_caption"))
lang = st.session_state.lang
LEVELS = {"L": "Bachelor (laurea)", "LM": "Master (laurea magistrale)", "LMCU5": "Single-cycle, 5 years", "LMCU6": "Single-cycle, 6 years"}
OUTCOME_ICON = {"pass": ":material/check_circle:", "fail": ":material/cancel:", "check": ":material/help:", "info": ":material/info:",
                "not_applicable": ":material/remove:"}
STATUS_ICON = {"done": ":material/check_box:", "todo": ":material/check_box_outline_blank:", "overdue": ":material/warning:",
               "info": ":material/info:"}

with st.form("facts"):
    c1, c2, c3 = st.columns(3)
    level = c1.selectbox("Course", list(LEVELS), format_func=LEVELS.get)
    year = c2.number_input("Year of course in 2026/2027", 1, 6, 2)
    today = c3.date_input("Reference date", dt.date.today())
    c1, c2, c3 = st.columns(3)
    credits = c1.number_input("Credits (CFU) by 10/8/2026", 0, 400, 30)
    bonus = c2.number_input("Bonus credits to use", 0, 15, 0)
    residence = c3.selectbox("Residence status", ["fuori_sede", "pendolare", "in_sede"])
    c1, c2 = st.columns(2)
    isee = c1.number_input("ISEE for university study (EUR, 0 = not known)", 0.0, 200000.0, 0.0, step=500.0)
    ispe = c2.number_input("ISPE (EUR, 0 = not known)", 0.0, 500000.0, 0.0, step=500.0)
    flags = st.pills("Your situation", ["family abroad", "non-EU citizen", "residence permit for 2026/2027", "application submitted",
                                        "extra semester", "part-time", "disability >= 66%", "previous degree of same level",
                                        "course listed in Art. 7.6", "asked for review"], selection_mode="multi")
    submitted = st.form_submit_button(t("check"), type="primary", icon=":material/fact_check:", key="check")

if submitted:
    facts = {
        "language": lang, "today": today.isoformat(), "level": level, "year": int(year), "credits": int(credits),
        "bonus_credits": int(bonus), "isee": isee or None, "ispe": ispe or None, "residence": residence,
        "family_abroad": "family abroad" in flags, "non_eu": "non-EU citizen" in flags,
        "has_residence_permit": "residence permit for 2026/2027" in flags, "application_submitted": "application submitted" in flags,
        "extra_semester": "extra semester" in flags, "part_time": "part-time" in flags, "disability_66": "disability >= 66%" in flags,
        "prior_degree_same_level": "previous degree of same level" in flags, "differentiated_merit_course": "course listed in Art. 7.6" in flags,
        "review_requested": "asked for review" in flags,
    }
    code, body = post("/v1/procedure/scholarship", facts)
    if code != 200:
        st.error(f"{code}: {body.get('title')} - {body.get('detail')}")
    else:
        st.session_state.guide = body

body = st.session_state.get("guide")
if body:
    alert = {"eligible": st.success, "not_eligible": st.error, "check_with_office": st.warning}[body["verdict"]]
    alert(body["verdict_text"])
    if body.get("amount_full_eur"):
        st.caption(f"{body['amount_category']}: full amount {body['amount_full_eur']:,.2f} EUR (Art. 12.2, reduced by ISEE bands)")
    for r in body["rules"]:
        with st.expander(f"{r['title']} — {r['outcome']}", icon=OUTCOME_ICON[r["outcome"]]):
            st.write(r["detail"])
            st.caption(f"{r['citation']['section']}: “{r['citation']['quote']}” (passage {r['citation']['passage_id']})")
    st.subheader(t("where"))
    s = body["status"]
    st.markdown(" → ".join(x["name"] for x in s["done"][-4:]) + (" → **" + " / ".join(x["name"] for x in s["next"]) + "**" if s["next"] else " ✓"))
    st.subheader(t("checklist"))
    for c in body["checklist"]:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(STATUS_ICON[c["status"]])
            show_text(c["text"] + (f" ({c['due']})" if c["due"] and lang != "ar" else ""), lang)
    st.subheader(t("deadlines"))
    st.dataframe([{"date": d["date"], "what": d["title"], "indicative": d["indicative"], "source": d["citation"]["section"]}
                  for d in body["deadlines"]], hide_index=True, alt="Deadlines of the ERDIS scholarship procedure")
    st.download_button(t("ics"), body["ics"], file_name="erdis_scholarship_2026_27.ics", mime="text/calendar", icon=":material/event:")
    st.caption(body["disclaimer"])
