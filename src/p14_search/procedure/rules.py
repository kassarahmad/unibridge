"""Deterministic eligibility rules for the ERDIS scholarship 2026/2027. Each rule names the article and the exact
words of the call that define it (the quote is resolved to an indexed passage by the guide). The student's
data is used only here, in code: it is never sent to an LLM and never stored.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

CALL = "ub:erdis-bando-borsa-2026-27"

DEADLINE_APPLICATION = dt.date(2026, 8, 28)
INTEGRATION_PARIFICATO = dt.date(2026, 9, 18)
PROVISIONAL_RANKING = dt.date(2026, 9, 15)  # "indicativamente"
FINAL_RANKING = dt.date(2026, 10, 15)  # "entro la prima metà del mese di ottobre 2026"
IBAN = dt.date(2026, 10, 31)
FIRST_INSTALMENT_FIRST_YEAR = dt.date(2026, 11, 10)
INSTALMENT_DEC = dt.date(2026, 12, 31)
PERMIT_COPY = dt.date(2027, 5, 3)
SECOND_INSTALMENT_LATER_YEARS = dt.date(2027, 6, 30)
MERIT_FIRST_YEAR = dt.date(2027, 8, 10)
MERIT_FIRST_YEAR_LAST = dt.date(2027, 11, 30)

ISEE_MAX = 24000.00
ISPE_MAX = 50000.00
# Art. 7.5, full-time students, credits by 10/8/2026 (table of the call). "extra" = ulteriore semestre.
MERIT_FULL_TIME = {
    "L": {2: 25, 3: 80, "extra": 135},
    "LM": {2: 30, "extra": 80},
    "LMCU5": {2: 25, 3: 80, 4: 135, 5: 190},
    "LMCU6": {2: 25, 3: 80, 4: 135, 5: 190, 6: 245},
}
LEGAL_YEARS = {"L": 3, "LM": 2, "LMCU5": 5, "LMCU6": 6}
# Art. 7.15: bonus credits usable the first time for the 2nd year (5), 3rd year (12), later years (15);
# master's students who never used it during the bachelor: at most 15 for the 2nd year.
BONUS_MAX = {2: 5, 3: 12}
AMOUNTS = {"fuori_sede": 7171.11, "pendolare": 4190.71, "in_sede": 2890.16}


@dataclass(frozen=True)
class Source:
    section: str
    quote: str  # exact words of the call (normalised whitespace), resolved to a passage id at start-up
    document_id: str = CALL


SOURCES = {
    "deadline": Source("Art. 10", "entro il 28 agosto 2026, pena l’esclusione dal concorso"),
    "economic": Source("ART. 8", "ISEE fino a € 24.000,00"),
    "ispe": Source("ART. 8", "ISPE fino a € 50.000,00"),
    "dsu_late": Source("ART. 20", "che abbiano sottoscritto la DSU per le prestazioni per il diritto allo studio successivamente al termine"),
    "parificato": Source("ART. 8", "entro lo stesso termine di scadenza della domanda del 28/8/2026"),
    "integration": Source("ART. 8", "entro il 18 settembre 2026"),
    "merit_table": Source("ART. 7", "i requisiti da acquisire entro il 10 agosto 2026 sono"),
    "merit_first_year": Source("ART. 7", "almeno 20 crediti (10 crediti in caso di iscrizione a tempo parziale)"),
    "bonus": Source("ART. 7", "5 crediti, se utilizzato per la prima volta per il conseguimento dei benefici per il secondo anno accademico"),
    "differentiated": Source("ART. 7", "i requisiti minimi di merito di cui agli Allegati A, B, C al presente bando"),
    "disability": Source("ART. 7", "si discostano del 40% da quelli previsti all’art. 7.5"),
    "duration_l": Source("ART. 4", "per un periodo di sette semestri, a partire dall’anno di prima immatricolazione"),
    "duration_lm": Source("ART. 4", "per un periodo cinque semestri a partire dall’anno di prima iscrizione"),
    "duration_lmcu": Source("ART. 4", "per un periodo pari alla durata prevista dai rispettivi ordinamenti didattici più un semestre"),
    "prior_degree": Source("ART. 20", "che siano in possesso di altra laurea di pari o superiore livello"),
    "permit_exclusion": Source("ART. 20", "di nazionalità straniera che non siano in possesso del permesso di soggiorno per l'a.a. 2026/2027"),
    "permit_copy": Source("ART. 11", "purché entro la data del 3/5/2027"),
    "foreign_off_campus": Source("ART. 12", "Gli studenti stranieri sono considerati comunque studenti fuori sede"),
    "amounts": Source("ART. 12", "studenti fuori sede e studenti indipendenti (art. 8.4 presente bando) €. 7.171,11"),
    "provisional": Source("ART. 15", "Indicativamente entro il 15 settembre 2026"),
    "review": Source("ART. 15", "Entro il quinto giorno successivo alla data di pubblicazione sul sito dell’avviso"),
    "final": Source("ART. 15", "entro la prima metà del mese di ottobre 2026"),
    "iban": Source("ART. 17", "entro il 31/10/2026 utilizzando esclusivamente la procedura on line"),
    "pay_first_year": Source("ART. 17", "la prima rata della borsa, in misura pari al 20% del totale"),
    "pay_first_year_nov": Source("ART. 17", "entro e non oltre il 10 novembre"),
    "pay_later_years": Source("ART. 17", "sarà erogata entro il 31 dicembre 2026 e la seconda rata entro il 30 giugno 2027"),
    "pay_non_eu": Source("ART. 17", "la prima rata della borsa di studio sarà erogata al conseguimento dei crediti richiesti"),
    "revoke_first_year": Source("ART. 21", "alla data del 30/11/2027 (studenti immatricolati nell’anno accademico 2026/2027) non abbiano conseguito i requisiti di merito"),
}


def required_credits(level: str, year: int, extra_semester: bool) -> int | None:
    table = MERIT_FULL_TIME[level]
    return table.get("extra" if extra_semester else year)


def bonus_cap(level: str, year: int) -> int:
    if level == "LM":
        return 15
    return BONUS_MAX.get(year, 15)
