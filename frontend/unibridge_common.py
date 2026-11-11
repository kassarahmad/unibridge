"""Shared helpers of the UniBridge UI: roles, API calls, interface texts in every UniBridge language."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import dotenv_values

from p14_search.i18n import LANGS, NATIVE, RTL, localize

ROOT = Path(__file__).resolve().parents[1]
ENV = {**dotenv_values(ROOT / ".env"), **os.environ}
ROLES = json.loads((ROOT / "config" / "principals_unibridge.json").read_text(encoding="utf-8"))["principals"]

_UI = {
    "ask_title": {"it": "Chiedi a UniBridge", "en": "Ask UniBridge", "ar": "اسأل UniBridge"},
    "ask_caption": {
        "it": "Risposte dai documenti ufficiali UNICAM ed ERDIS, con la fonte italiana di ogni frase.",
        "en": "Answers from official UNICAM and ERDIS documents, with the Italian source of every sentence.",
        "ar": "إجابات من الوثائق الرسمية لجامعة كاميرينو وERDIS، مع المصدر الإيطالي لكل جملة.",
    },
    "placeholder": {"it": "Scrivi la tua domanda nella tua lingua", "en": "Type your question in your own language",
                    "ar": "اكتب سؤالك بلغتك"},
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
    # scholarship guide form
    "course": {"it": "Corso", "en": "Course", "ar": "المسار الدراسي"},
    "year": {"it": "Anno di corso nel 2026/2027", "en": "Year of course in 2026/2027", "ar": "سنة الدراسة في 2026/2027"},
    "ref_date": {"it": "Data di riferimento", "en": "Reference date", "ar": "التاريخ المرجعي"},
    "credits": {"it": "Crediti (CFU) entro il 10/8/2026", "en": "Credits (CFU) by 10/8/2026", "ar": "الساعات المعتمدة (CFU) حتى 10/8/2026"},
    "bonus": {"it": "Crediti bonus da usare", "en": "Bonus credits to use", "ar": "الساعات الإضافية (البونص) المراد استخدامها"},
    "residence": {"it": "Condizione abitativa", "en": "Residence status", "ar": "وضع السكن"},
    "isee": {"it": "ISEE per il diritto allo studio (EUR, 0 = non noto)", "en": "ISEE for university study (EUR, 0 = not known)",
             "ar": "مؤشر ISEE للدراسة الجامعية (يورو، 0 = غير معروف)"},
    "ispe": {"it": "ISPE (EUR, 0 = non noto)", "en": "ISPE (EUR, 0 = not known)", "ar": "مؤشر ISPE (يورو، 0 = غير معروف)"},
    "situation": {"it": "La tua situazione", "en": "Your situation", "ar": "وضعك"},
    "flag_family_abroad": {"it": "famiglia all'estero", "en": "family abroad", "ar": "الأسرة في الخارج"},
    "flag_non_eu": {"it": "cittadino extra UE", "en": "non-EU citizen", "ar": "مواطن من خارج الاتحاد الأوروبي"},
    "flag_permit": {"it": "permesso di soggiorno per il 2026/2027", "en": "residence permit for 2026/2027", "ar": "تصريح إقامة للعام 2026/2027"},
    "flag_submitted": {"it": "domanda inviata", "en": "application submitted", "ar": "تم تقديم الطلب"},
    "flag_extra_semester": {"it": "semestre aggiuntivo", "en": "extra semester", "ar": "فصل دراسي إضافي"},
    "flag_part_time": {"it": "tempo parziale", "en": "part-time", "ar": "دوام جزئي"},
    "flag_disability": {"it": "disabilità >= 66%", "en": "disability >= 66%", "ar": "إعاقة >= 66%"},
    "flag_prior_degree": {"it": "titolo precedente dello stesso livello", "en": "previous degree of same level", "ar": "شهادة سابقة من نفس المستوى"},
    "flag_differentiated": {"it": "corso elencato all'Art. 7.6", "en": "course listed in Art. 7.6", "ar": "مسار مذكور في المادة 7.6"},
    "flag_review": {"it": "istanza di revisione presentata", "en": "asked for review", "ar": "تم طلب المراجعة"},
    "level_L": {"it": "Laurea triennale", "en": "Bachelor (laurea)", "ar": "بكالوريوس (laurea)"},
    "level_LM": {"it": "Laurea magistrale", "en": "Master (laurea magistrale)", "ar": "ماجستير (laurea magistrale)"},
    "level_LMCU5": {"it": "Ciclo unico, 5 anni", "en": "Single-cycle, 5 years", "ar": "مسار موحد، 5 سنوات"},
    "level_LMCU6": {"it": "Ciclo unico, 6 anni", "en": "Single-cycle, 6 years", "ar": "مسار موحد، 6 سنوات"},
    # sidebar and answers
    "language": {"it": "Lingua", "en": "Language", "ar": "اللغة"},
    "role": {"it": "Ruolo", "en": "Role", "ar": "الدور"},
    "role_help": {"it": "visitor = documenti pubblici; student = + avvisi per gli iscritti; ruoli d'ufficio = + note interne di quell'ufficio.",
                  "en": "visitor = public documents; student = + student-only notices; office roles = + that office's internal notes.",
                  "ar": "visitor = الوثائق العامة؛ student = + إشعارات الطلاب المسجلين؛ أدوار المكاتب = + الملاحظات الداخلية لذلك المكتب."},
    "disclaimer": {"it": "Prototipo per un progetto universitario (Complex Systems Design, UNICAM). Non è un servizio ufficiale di UNICAM o ERDIS.",
                   "en": "Prototype for a university project (Complex Systems Design, UNICAM). Not an official service of UNICAM or ERDIS.",
                   "ar": "نموذج أولي لمشروع جامعي (Complex Systems Design، جامعة كاميرينو). ليس خدمة رسمية من UNICAM أو ERDIS."},
    "subject": {"it": "Oggetto", "en": "Subject", "ar": "الموضوع"},
    "text": {"it": "Testo", "en": "Text", "ar": "النص"},
    "ask_page": {"it": "Chiedi", "en": "Ask", "ar": "اسأل"},
    "guide_page": {"it": "Guida alla borsa", "en": "Scholarship guide", "ar": "دليل المنحة"},
}
UI = {key: localize(f"ui.{key}", texts) for key, texts in _UI.items()}


def browser_language() -> str:
    """The UI starts in the language of the browser when UniBridge supports it, else English."""
    locale = (st.context.locale or "").split("-")[0].lower()
    return locale if locale in LANGS else "en"


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
    """Arabic, Persian and Urdu are shown right-to-left (no native Streamlit option for text direction)."""
    if lang in RTL:
        st.html(f'<div dir="rtl" style="text-align:right">{html.escape(text)}</div>')
    else:
        st.markdown(text)
