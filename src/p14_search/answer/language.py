"""Deterministic language identification over the UniBridge languages, and the fixed messages in each language.

Identification uses lingua (statistical n-gram models, offline, deterministic) restricted to the languages of
p14_search.i18n.LANGS; text it cannot classify is treated as Italian, the language of the documents.
"""

from __future__ import annotations

from functools import lru_cache

from lingua import IsoCode639_1, Language, LanguageDetectorBuilder

from p14_search.i18n import LANGS, NAMES, localize

__all__ = ["EXTRACTIVE_NOTE", "HANDOFF_NOTE", "I_DONT_KNOW", "LANGS", "NAMES", "OUT_OF_SCOPE_NOTE", "detect"]


@lru_cache(maxsize=1)
def _detector():
    return LanguageDetectorBuilder.from_languages(*(Language.from_iso_code_639_1(getattr(IsoCode639_1, c.upper())) for c in LANGS)).build()


def detect(text: str) -> str:
    found = _detector().detect_language_of(text) if text.strip() else None
    return found.iso_code_639_1.name.lower() if found else "it"


I_DONT_KNOW = localize("answer.i_dont_know", {
    "it": "Non lo so: nei documenti ufficiali disponibili non ho trovato informazioni sufficienti per rispondere in modo affidabile.",
    "en": "I don't know: I could not find enough information in the available official documents to answer reliably.",
    "ar": "لا أعرف: لم أجد في الوثائق الرسمية المتاحة معلومات كافية للإجابة بشكل موثوق.",
})
EXTRACTIVE_NOTE = localize("answer.extractive_note", {
    "it": "Risposta estrattiva: frasi copiate dai documenti ufficiali, senza testo generato.",
    "en": "Extractive answer: sentences copied from the official Italian documents; no text was generated in your language.",
    "ar": "إجابة مستخرجة: جمل منسوخة من الوثائق الرسمية الإيطالية، دون توليد نص بلغتك.",
})
HANDOFF_NOTE = localize("answer.handoff_note", {
    "it": "Puoi scrivere all'ufficio competente: ho preparato una bozza in italiano che puoi controllare e inviare tu.",
    "en": "You can write to the responsible office: I prepared a draft in Italian that you can check and send yourself.",
    "ar": "يمكنك مراسلة المكتب المختص: أعددت مسودة باللغة الإيطالية يمكنك مراجعتها وإرسالها بنفسك.",
})
OUT_OF_SCOPE_NOTE = localize("answer.out_of_scope_note", {
    "it": "La domanda sembra fuori dall'ambito di UniBridge (studio, borse e servizi per studenti a Camerino).",
    "en": "The question seems outside the scope of UniBridge (study, scholarships and student services in Camerino).",
    "ar": "يبدو أن السؤال خارج نطاق UniBridge (الدراسة والمنح وخدمات الطلاب في كاميرينو).",
})
