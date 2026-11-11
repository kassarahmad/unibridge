"""Deterministic language identification for it / en / ar, and the fixed messages in each language."""

from __future__ import annotations

import re

LANGS = ("it", "en", "ar")
NAMES = {"it": "Italian", "en": "English", "ar": "Arabic"}
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_IT = set("il lo la gli le un una di da del della dei delle che non per con sono come quando dove posso devo cosa "
          "quale quali è ho mi si al alla nel nella anche ma se entro borsa domanda".split())
_EN = set("the a an of to in on for and or is are be can do does how what when where which who with my i "
          "need have get should must from there".split())


def detect(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if _ARABIC.match(c)) / len(letters) >= 0.3:
        return "ar"
    words = re.findall(r"[a-zà-ü']+", text.lower())
    it = sum(w in _IT for w in words)
    en = sum(w in _EN for w in words)
    return "en" if en > it else "it"


I_DONT_KNOW = {
    "it": "Non lo so: nei documenti ufficiali disponibili non ho trovato informazioni sufficienti per rispondere in modo affidabile.",
    "en": "I don't know: I could not find enough information in the available official documents to answer reliably.",
    "ar": "لا أعرف: لم أجد في الوثائق الرسمية المتاحة معلومات كافية للإجابة بشكل موثوق.",
}
EXTRACTIVE_NOTE = {
    "it": "Risposta estrattiva: frasi copiate dai documenti ufficiali, senza testo generato.",
    "en": "Extractive answer: sentences copied from the official Italian documents; no text was generated in your language.",
    "ar": "إجابة مستخرجة: جمل منسوخة من الوثائق الرسمية الإيطالية، دون توليد نص بلغتك.",
}
HANDOFF_NOTE = {
    "it": "Puoi scrivere all'ufficio competente: ho preparato una bozza in italiano che puoi controllare e inviare tu.",
    "en": "You can write to the responsible office: I prepared a draft in Italian that you can check and send yourself.",
    "ar": "يمكنك مراسلة المكتب المختص: أعددت مسودة باللغة الإيطالية يمكنك مراجعتها وإرسالها بنفسك.",
}
OUT_OF_SCOPE_NOTE = {
    "it": "La domanda sembra fuori dall'ambito di UniBridge (studio, borse e servizi per studenti a Camerino).",
    "en": "The question seems outside the scope of UniBridge (study, scholarships and student services in Camerino).",
    "ar": "يبدو أن السؤال خارج نطاق UniBridge (الدراسة والمنح وخدمات الطلاب في كاميرينو).",
}
