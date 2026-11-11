"""Shared helpers of the UniBridge UI: roles, API calls, interface texts in it / en / ar."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV = {**dotenv_values(ROOT / ".env"), **os.environ}
ROLES = json.loads((ROOT / "config" / "principals_unibridge.json").read_text(encoding="utf-8"))["principals"]
LANGS = {"it": "Italiano", "en": "English", "ar": "العربية"}

UI = {
    "ask_title": {"it": "Chiedi a UniBridge", "en": "Ask UniBridge", "ar": "اسأل UniBridge"},
    "ask_caption": {
        "it": "Risposte dai documenti ufficiali UNICAM ed ERDIS, con la fonte italiana di ogni frase.",
        "en": "Answers from official UNICAM and ERDIS documents, with the Italian source of every sentence.",
        "ar": "إجابات من الوثائق الرسمية لجامعة كاميرينو وERDIS، مع المصدر الإيطالي لكل جملة.",
    },
    "placeholder": {"it": "Scrivi la tua domanda (italiano, inglese o arabo)", "en": "Type your question (Italian, English or Arabic)",
                    "ar": "اكتب سؤالك (بالإيطالية أو الإنجليزية أو العربية)"},
    "sources": {"it": "Fonti (testo originale italiano)", "en": "Sources (original Italian text)", "ar": "المصادر (النص الإيطالي الأصلي)"},
    "draft": {"it": "Bozza per l'ufficio (non viene inviata)", "en": "Draft for the office (never sent automatically)",
              "ar": "مسودة للمكتب (لا تُرسل تلقائيًا)"},
    "draft_button": {"it": "Prepara una e-mail all'ufficio", "en": "Draft an e-mail to the office", "ar": "أعدّ رسالة إلى المكتب"},
    "download_draft": {"it": "Scarica la bozza", "en": "Download the draft", "ar": "تنزيل المسودة"},
    "guide_title": {"it": "Guida alla borsa di studio ERDIS 2026/2027", "en": "ERDIS scholarship guide 2026/2027",
                    "ar": "دليل منحة ERDIS للعام 2026/2027"},
    "guide_caption": {
        "it": "Regole deterministiche del bando, nessun modello linguistico. I dati non vengono salvati.",
        "en": "Deterministic rules from the call, no language model. Your data is not stored.",
        "ar": "قواعد ثابتة من الإعلان، دون نموذج لغوي. لا يتم حفظ بياناتك.",
    },
    "check": {"it": "Controlla", "en": "Check", "ar": "تحقق"},
    "checklist": {"it": "La tua checklist", "en": "Your checklist", "ar": "قائمة المهام الخاصة بك"},
    "deadlines": {"it": "Scadenze", "en": "Deadlines", "ar": "المواعيد النهائية"},
    "ics": {"it": "Scarica le scadenze (.ics)", "en": "Download deadlines (.ics)", "ar": "تنزيل المواعيد (.ics)"},
    "where": {"it": "Dove sei nella procedura", "en": "Where you are in the procedure", "ar": "أين أنت في الإجراء"},
}


def t(key: str) -> str:
    return UI[key][st.session_state.get("lang", "en")]


def api_url() -> str:
    return ENV.get("UNIBRIDGE_URL", "http://127.0.0.1:8001")


def role() -> dict:
    return next(r for r in ROLES if r["name"] == st.session_state.get("role", "visitor"))


def post(path: str, payload: dict) -> tuple[int, dict]:
    key = ENV.get(role()["api_key_env"], "")
    try:
        r = requests.post(f"{api_url()}{path}", json=payload, headers={"X-API-Key": key}, timeout=120)
    except requests.RequestException as exc:
        return 0, {"title": "API not reachable", "detail": str(exc)}
    return r.status_code, r.json()


def show_text(text: str, lang: str) -> None:
    """Arabic is shown right-to-left (no native Streamlit option for text direction)."""
    if lang == "ar":
        st.html(f'<div dir="rtl" style="text-align:right">{html.escape(text)}</div>')
    else:
        st.markdown(text)
