"""Handoff: when UniBridge cannot answer, choose the responsible office with a rule table and draft a formal
Italian message for the student to send. Nothing is ever sent automatically.

Office choice (deterministic, config/handoff_offices.json): keyword matches in the question per office; ties go
to the office of the best retrieved passage; no match = out of scope (no draft, the student is told why).
The question is translated into Italian by the LLM when one is configured (cached); the student's personal
data is never filled in: the draft has placeholders.
"""

from __future__ import annotations

import json
from pathlib import Path

from p14_search.answer.language import HANDOFF_NOTE, OUT_OF_SCOPE_NOTE, detect
from p14_search.answer.llm import LLMClient, LLMError
from p14_search.answer.prompts import TRANSLATE_SYSTEM
from p14_search.models import HandoffDraft, HandoffResponse, HandoffSource, Lang

CONFIG = Path(__file__).resolve().parents[3] / "config" / "handoff_offices.json"
LANG_IT = {"it": "italiano", "en": "inglese", "ar": "arabo"}


class HandoffService:
    def __init__(self, llm: LLMClient | None, config_path: Path = CONFIG):
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.offices: dict = cfg["offices"]
        self.rules: list[dict] = cfg["rules"]
        self.llm = llm

    # --- office choice -----------------------------------------------------------------------
    def choose_office(self, question: str, top_office: str | None = None) -> tuple[str | None, str]:
        q = question.lower()
        scores = {r["office"]: sorted({k for k in r["keywords"] if k.lower() in q}) for r in self.rules}
        best = max((len(v) for v in scores.values()), default=0)
        if best == 0:
            return None, "no keyword of the rule table matches the question"
        tied = [o for o, v in scores.items() if len(v) == best]
        office = top_office if top_office in tied else tied[0]
        why = f"keywords matched for {office}: {', '.join(scores[office])}"
        if len(tied) > 1:
            why += f" (tie with {', '.join(o for o in tied if o != office)}; broken by " + (
                "the office of the best retrieved passage)" if top_office in tied else "rule order)")
        return office, why

    # --- translation (optional LLM) ----------------------------------------------------------
    def to_italian(self, question: str, lang: str) -> str | None:
        if lang == "it":
            return question
        if self.llm is None:
            return None
        try:
            return self.llm.complete(TRANSLATE_SYSTEM, question, 200, "handoff_translation").text.strip() or None
        except LLMError:
            return None

    # --- draft -------------------------------------------------------------------------------
    def draft(self, question: str, language: Lang | None, sources: list[HandoffSource], request_id: str,
              top_office: str | None = None, office_id: str | None = None) -> HandoffResponse:
        lang = language or detect(question)
        if office_id:
            office, why = office_id, "office chosen by the caller"
        else:
            office, why = self.choose_office(question, top_office)
        if office is None:
            return HandoffResponse(request_id=request_id, language=lang, out_of_scope=True, message=OUT_OF_SCOPE_NOTE[lang], draft=None)
        o = self.offices[office]
        italian = self.to_italian(question, lang)
        topic = (italian or question).strip().rstrip("?")
        subject = "Richiesta di informazioni - " + (topic[:70] + ("..." if len(topic) > 70 else ""))
        lines = [f"Gentile {o['name']},", "",
                 "sono una studentessa / uno studente internazionale dell'Università di Camerino e vorrei chiedere un chiarimento.", ""]
        if lang == "it":
            lines += [f"Domanda: {question.strip()}"]
        elif italian:
            lines += [f"Domanda: {italian}", f"(Testo originale in {LANG_IT[lang]}: \"{question.strip()}\")"]
        else:
            lines += [f"Domanda (scritta in {LANG_IT[lang]}, traduzione non disponibile): \"{question.strip()}\""]
        lines += [""]
        if sources:
            lines += ["Ho consultato i seguenti documenti ufficiali, senza trovare una risposta certa:"]
            for s in sources:
                where = ", ".join(x for x in (s.section and f"sezione {s.section[:60]}", s.page and f"p. {s.page}") if x)
                lines += [f"- {s.title}" + (f" ({where})" if where else "") + (f" - {s.source_url}" if s.source_url else "")]
            lines += [""]
        lines += ["Vi ringrazio per l'attenzione e resto in attesa di un vostro riscontro.", "", "Cordiali saluti,",
                  "[Nome e cognome]", "[Matricola o numero di domanda, se disponibile]"]
        draft = HandoffDraft(
            office_id=office, office_name=o["name"], channel=o["channel"], to=o["to"], how_to_send=o["how_to_send"],
            contact_source=o["contact_source"], rule=why, subject=subject, body="\n".join(lines),
            question_original=question.strip(), question_italian=italian if lang != "it" else question.strip(),
            translated_by_llm=lang != "it" and italian is not None, sources=sources,
        )
        return HandoffResponse(request_id=request_id, language=lang, out_of_scope=False, message=HANDOFF_NOTE[lang], draft=draft)

