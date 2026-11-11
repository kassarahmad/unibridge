"""Ask page: chat in the student's language; every sentence shows its source, with the Italian original."""

from __future__ import annotations

import streamlit as st
from unibridge_common import post, show_text, t

st.title(t("ask_title"))
st.caption(t("ask_caption"))


def show_draft(handoff: dict, key: str) -> None:
    if handoff.get("message"):
        show_text(handoff["message"], handoff["language"])
    draft = handoff.get("draft")
    if not draft:
        return
    with st.container(border=True):
        st.markdown(f"**{t('draft')}** · {draft['office_name']}")
        st.caption(f"{draft['how_to_send']} (source: {draft['contact_source']})")
        st.text_input("Subject", draft["subject"], key=f"subj_{key}", disabled=True)
        st.text_area("Text", draft["body"], height=280, key=f"body_{key}")
        st.download_button(t("download_draft"), f"{draft['subject']}\n\n{draft['body']}", file_name="unibridge_draft.txt",
                           icon=":material/download:", key=f"dl_{key}")


def show_answer(msg: dict, idx: int) -> None:
    body = msg["body"]
    lang = body["language"]
    if body["insufficient_evidence"]:
        st.warning(body["message"], icon=":material/help:")
        if body.get("handoff"):
            show_draft(body["handoff"], f"a{idx}")
        return
    numbers = {s["passage_id"]: i + 1 for i, s in enumerate(body["sources"])}
    lines = [f"{s['text']} " + " ".join(f"[{numbers[p]}]" for p in s["passage_ids"] if p in numbers) for s in body["sentences"]]
    show_text("\n\n".join(lines), "it" if body["mode"] == "extractive" else lang)  # extractive sentences are Italian
    st.caption(f"mode: {body['mode']}" + (f" · {body['message']}" if body.get("message") else "")
               + (f" · LLM {body['llm']['model']}, {body['llm']['calls']} calls" if body.get("llm") else ""))
    cited = {p for s in body["sentences"] for p in s["passage_ids"]}
    with st.expander(t("sources"), icon=":material/menu_book:"):
        for s in body["sources"]:
            if s["passage_id"] not in cited:
                continue
            c = s["citation"]
            where = " · ".join(x for x in (c.get("section"), c.get("page") and f"p. {c['page']}") if x)
            st.markdown(f"**[{numbers[s['passage_id']]}] {c['title']}**" + (f" — {where}" if where else ""))
            st.text(s["text"])
            if c.get("source_url"):
                st.caption(c["source_url"])
    if st.button(t("draft_button"), key=f"draft_{idx}", icon=":material/mail:"):
        code, handoff = post("/v1/handoff", {"query": body["query"], "language": lang, "passage_ids": sorted(cited)[:5]})
        if code == 200:
            msg["handoff"] = handoff
        else:
            st.error(f"{code}: {handoff.get('title')} - {handoff.get('detail')}")
    if msg.get("handoff"):
        show_draft(msg["handoff"], f"b{idx}")


for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            show_text(msg["text"], msg.get("lang", "en"))
        else:
            show_answer(msg, i)

if prompt := st.chat_input(t("placeholder"), submit_mode="disable", key="prompt"):
    st.session_state.messages.append({"role": "user", "text": prompt, "lang": "ar" if any("؀" <= c <= "ۿ" for c in prompt) else "en"})
    with st.chat_message("user"):
        show_text(prompt, st.session_state.messages[-1]["lang"])
    with st.chat_message("assistant"):
        with st.spinner(""):
            code, body = post("/v1/answer", {"query": prompt})
    if code == 200:
        st.session_state.messages.append({"role": "assistant", "body": body})
    else:
        st.session_state.messages.append({"role": "assistant", "body": {
            "language": st.session_state.lang, "insufficient_evidence": True,
            "message": f"Error {code}: {body.get('title')} - {body.get('detail')}"}})
    st.rerun()
