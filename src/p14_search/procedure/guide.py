"""Scholarship guide: deterministic eligibility rules + the workflow net as state machine + personal checklist
and .ics deadlines. No LLM is involved and the student's facts are not stored or logged.

State machine: the guide replays the workflow net of model.py. A transition is fired only when it is enabled
in the net AND the student's facts or the reference date say it has happened (e.g. the provisional ranking is
fired from its indicative date on). The enabled transitions of the final marking are the "next steps". Because
the net is sound, every marking the guide can reach can still complete.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections import Counter

from p14_search.indexing.store import Store
from p14_search.models import (
    ChecklistItem,
    Deadline,
    ProcedureRequest,
    ProcedureResponse,
    ProcedureStatus,
    ProcedureStep,
    RuleCitation,
    RuleResult,
)
from p14_search.procedure import rules as R
from p14_search.procedure.ics import calendar
from p14_search.procedure.model import SINK, SOURCE, build_net
from p14_search.procedure.soundness import enabled, fire

log = logging.getLogger("p14.procedure")

VERDICT = {
    "eligible": {"it": "In base ai dati inseriti risulti in possesso dei requisiti del bando.",
                 "en": "Based on the data you entered, you meet the requirements of the call.",
                 "ar": "بناءً على البيانات التي أدخلتها، تستوفي شروط الإعلان."},
    "not_eligible": {"it": "In base ai dati inseriti almeno un requisito del bando non è soddisfatto.",
                     "en": "Based on the data you entered, at least one requirement of the call is not met.",
                     "ar": "بناءً على البيانات التي أدخلتها، هناك شرط واحد على الأقل من شروط الإعلان غير مستوفى."},
    "check_with_office": {"it": "Alcuni requisiti non si possono verificare automaticamente: controlla con l'ufficio ERDIS.",
                          "en": "Some requirements cannot be checked automatically: check with the ERDIS office.",
                          "ar": "لا يمكن التحقق من بعض الشروط تلقائيًا: تحقق مع مكتب ERDIS."},
}
DISCLAIMER = {
    "it": "Guida informativa basata sul bando ERDIS 2026/2027. Fa fede solo l'esito pubblicato da ERDIS. I dati inseriti non vengono salvati.",
    "en": "Information guide based on the ERDIS call 2026/2027. Only the outcome published by ERDIS is binding. Your data is not stored.",
    "ar": "دليل معلوماتي مبني على إعلان ERDIS 2026/2027. النتيجة الرسمية هي فقط ما ينشره ERDIS. لا يتم حفظ بياناتك.",
}
# checklist texts: (it, en, ar)
TEXTS = {
    "isee": ("Sottoscrivi la DSU e ottieni l'ISEE per il diritto allo studio universitario entro il 28/8/2026.",
             "Sign the DSU and obtain the ISEE for university study benefits by 28/8/2026.",
             "وقّع إقرار DSU واحصل على مؤشر ISEE الخاص بمزايا الدراسة الجامعية قبل 28/8/2026."),
    "parificato": ("Presenta i documenti per l'ISEE parificato (nucleo familiare, redditi 2024, patrimoni al 31/12/2024), legalizzati o con apostille e tradotti in italiano, entro il 28/8/2026.",
                   "Submit the documents for the ISEE parificato (household, 2024 income, assets at 31/12/2024), legalised or with apostille and translated into Italian, by 28/8/2026.",
                   "قدّم وثائق ISEE المعادل (تكوين الأسرة، دخل 2024، الممتلكات في 31/12/2024) مصدّقة أو بختم الأبوستيل ومترجمة إلى الإيطالية قبل 28/8/2026."),
    "integration": ("Se i documenti per l'ISEE parificato sono incompleti, puoi completarli entro il 18/9/2026 (valutati per le graduatorie definitive).",
                    "If the ISEE parificato documents are incomplete, you can complete them by 18/9/2026 (assessed for the final rankings).",
                    "إذا كانت وثائق ISEE المعادل ناقصة، يمكنك استكمالها حتى 18/9/2026 (تُقيَّم في القوائم النهائية)."),
    "apply": ("Compila, conferma e invia la domanda online entro il 28/8/2026.",
              "Fill in, confirm and send the online application by 28/8/2026.",
              "املأ الطلب عبر الإنترنت وأكّده وأرسله قبل 28/8/2026."),
    "bonus": ("Chiedi l'uso dei crediti bonus nella domanda.", "Request the use of bonus credits in the application.",
              "اطلب استخدام الساعات المعتمدة الإضافية (البونص) في الطلب."),
    "permit": ("Consegna la copia del permesso di soggiorno per l'a.a. 2026/2027 entro il 3/5/2027: fino ad allora i pagamenti sono sospesi.",
               "Hand in a copy of the residence permit for 2026/2027 by 3/5/2027: payments are suspended until then.",
               "سلّم نسخة من تصريح الإقامة للعام 2026/2027 قبل 3/5/2027: تُعلَّق المدفوعات حتى ذلك الحين."),
    "ranking": ("Controlla la graduatoria provvisoria nella tua area personale (indicativamente entro il 15/9/2026): non riceverai avvisi individuali.",
                "Check the provisional ranking in your personal area (indicatively by 15/9/2026): you will not be notified individually.",
                "تحقق من قائمة الترتيب المؤقتة في منطقتك الشخصية (تقريبًا حتى 15/9/2026): لن يصلك إشعار فردي."),
    "review": ("Se sei escluso o i dati sono errati, presenta un'istanza di revisione entro 5 giorni dalla pubblicazione.",
               "If you are excluded or the data is wrong, submit a request for review within 5 days of publication.",
               "إذا تم استبعادك أو كانت البيانات خاطئة، قدّم طلب مراجعة خلال 5 أيام من النشر."),
    "iban": ("Comunica un IBAN di un conto intestato o cointestato a te (italiano o SEPA) entro il 31/10/2026.",
             "Give the IBAN of an account in your name (Italian or SEPA) by 31/10/2026.",
             "قدّم رقم IBAN لحساب باسمك (إيطالي أو ضمن SEPA) قبل 31/10/2026."),
    "credits_first_year": ("Consegui almeno 20 crediti (10 a tempo parziale) entro il 10/8/2027 per il saldo; entro il 30/11/2027 al più tardi, altrimenti la borsa è revocata.",
                           "Earn at least 20 credits (10 part-time) by 10/8/2027 for the balance; by 30/11/2027 at the latest, otherwise the scholarship is revoked.",
                           "احصل على 20 ساعة معتمدة على الأقل (10 بدوام جزئي) قبل 10/8/2027 للدفعة الأخيرة، وفي موعد أقصاه 30/11/2027 وإلا تُلغى المنحة."),
    "non_eu_first_year": ("Come studente extra-UE al primo anno, la prima rata è pagata al raggiungimento dei crediti richiesti, salvo garanzia.",
                          "As a non-EU first-year student, the first instalment is paid when you reach the required credits, unless you give a guarantee.",
                          "بصفتك طالبًا من خارج الاتحاد الأوروبي في السنة الأولى، تُدفع الدفعة الأولى عند تحقيق الساعات المعتمدة المطلوبة، ما لم تقدّم ضمانًا."),
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'")).strip().lower()


class ScholarshipGuide:
    def __init__(self, store: Store | None):
        self.net = build_net()
        self.passages: dict[str, str | None] = {}
        rows = store.query("SELECT passage_id, text FROM passages WHERE indexed = 1 AND document_id = ?", (R.CALL,)) if store else []
        normed = [(r["passage_id"], _norm(r["text"])) for r in rows]
        for key, src in R.SOURCES.items():
            q = _norm(src.quote)
            self.passages[key] = next((pid for pid, t in normed if q in t), None)

    def cite(self, key: str) -> RuleCitation:
        s = R.SOURCES[key]
        return RuleCitation(document_id=s.document_id, section=s.section, quote=s.quote, passage_id=self.passages.get(key))

    # --- rules -------------------------------------------------------------------------------
    def evaluate(self, f: ProcedureRequest, today: dt.date) -> list[RuleResult]:
        out: list[RuleResult] = []

        def add(rid, title, outcome, detail, key):
            out.append(RuleResult(id=rid, title=title, outcome=outcome, detail=detail, citation=self.cite(key)))

        # application deadline (Art. 10.1)
        if f.application_submitted:
            add("deadline", "Application by 28/8/2026", "pass", "Application submitted.", "deadline")
        elif f.application_submitted is False and today > R.DEADLINE_APPLICATION:
            add("deadline", "Application by 28/8/2026", "fail", "The deadline has passed and it cannot be extended.", "deadline")
        elif f.application_submitted is False:
            add("deadline", "Application by 28/8/2026", "check", f"Not submitted yet: {(R.DEADLINE_APPLICATION - today).days} days left.", "deadline")
        else:
            add("deadline", "Application by 28/8/2026", "info", "Application status not given.", "deadline")
        # economic condition (Art. 8.2)
        for rid, value, limit, key in (("isee", f.isee, R.ISEE_MAX, "economic"), ("ispe", f.ispe, R.ISPE_MAX, "ispe")):
            label = rid.upper()
            if value is None:
                detail = ("Computed by ERDIS from your documents (ISEE parificato, Art. 8.8)." if f.family_abroad
                          else f"{label} not given: it must be at most {limit:,.2f} EUR.")
                add(rid, f"{label} at most {limit:,.0f} EUR", "check", detail, key)
            else:
                add(rid, f"{label} at most {limit:,.0f} EUR", "pass" if value <= limit else "fail",
                    f"{label} {value:,.2f} EUR {'<=' if value <= limit else '>'} {limit:,.2f} EUR.", key)
        # previous degree (Art. 20.c)
        add("prior_degree", "No previous degree of the same or a higher level", "fail" if f.prior_degree_same_level else "pass",
            "You declared a previous degree of the same or a higher level." if f.prior_degree_same_level else "No previous degree declared.",
            "prior_degree")
        # duration (Art. 4.1)
        legal = R.LEGAL_YEARS[f.level]
        dkey = {"L": "duration_l", "LM": "duration_lm"}.get(f.level, "duration_lmcu")
        if f.part_time:
            add("duration", "Within the duration of the benefit", "check", "Part-time durations (Art. 4.1 e) are not computed by the guide.", dkey)
        elif f.year > legal or (f.extra_semester and f.year != legal):
            add("duration", "Within the duration of the benefit", "fail",
                f"Year {f.year}{' + extra semester' if f.extra_semester else ''} is beyond the legal duration ({legal} years) plus one semester.", dkey)
        else:
            add("duration", "Within the duration of the benefit", "pass",
                f"Year {f.year}{' (extra semester)' if f.extra_semester else ''} of {legal} + one extra semester.", dkey)
        # merit (Art. 7)
        if f.year == 1 and not f.extra_semester:
            add("merit", "Merit requirement", "info", "First year: merit is assessed afterwards (20 credits by 10/8/2027).", "merit_first_year")
        elif f.disability_66:
            add("merit", "Merit requirement", "check", "Requirements 40% lower for students with disability (Art. 7.11): check with ERDIS.", "disability")
        elif f.differentiated_merit_course:
            add("merit", "Merit requirement", "check", "Your course has proportional requirements (Art. 7.6, Annexes A-C).", "differentiated")
        elif f.part_time:
            add("merit", "Merit requirement", "check", "Part-time requirements (Art. 7.5 table) are not computed by the guide.", "merit_table")
        else:
            need = R.required_credits(f.level, f.year, f.extra_semester)
            if need is None:
                add("merit", "Merit requirement", "check", "No fixed requirement for this year in the guide's table.", "merit_table")
            elif f.credits is None:
                add("merit", "Merit requirement", "check", f"{need} credits are required by 10/8/2026; credits not given.", "merit_table")
            else:
                bonus = min(f.bonus_credits, R.bonus_cap(f.level, f.year))
                total = f.credits + bonus
                note = f" (bonus capped at {bonus})" if bonus < f.bonus_credits else ""
                add("merit", "Merit requirement", "pass" if total >= need else "fail",
                    f"{f.credits} credits + {bonus} bonus{note} = {total}; required {need} by 10/8/2026.", "merit_table" if not bonus else "bonus")
        # residence permit (Art. 20.p, 11.e)
        if f.non_eu:
            if f.has_residence_permit:
                add("permit", "Residence permit for 2026/2027", "pass", "Residence permit declared.", "permit_exclusion")
            else:
                add("permit", "Residence permit for 2026/2027", "check",
                    "Without a residence permit for 2026/2027 you are excluded; a copy can be handed in by 3/5/2027.", "permit_exclusion")
        else:
            add("permit", "Residence permit for 2026/2027", "not_applicable", "Not required for EU students.", "permit_exclusion")
        # amount category (Art. 12): foreign students with the family abroad are always "fuori sede"
        category = f.residence or ("fuori_sede" if f.family_abroad else None)
        if category:
            add("amount", "Amount category", "info",
                f"{category}: full amount {R.AMOUNTS[category]:,.2f} EUR, reduced according to the ISEE bands of Art. 12.",
                "foreign_off_campus" if f.family_abroad and not f.residence else "amounts")
        return out

    # --- state machine (replay of the workflow net) ------------------------------------------
    def replay(self, f: ProcedureRequest, today: dt.date, eligible: bool | None) -> tuple[Counter, list[str]]:
        happened = {
            "t_call": True, "t_split": True,
            "t_dsu": bool(f.application_submitted) and not f.family_abroad,
            "t_parificato": bool(f.application_submitted) and f.family_abroad,
            "t_apply": bool(f.application_submitted),
            "t_enrol": f.enrolled,
            "t_join": today > R.DEADLINE_APPLICATION, "t_check": today > R.DEADLINE_APPLICATION,
            "t_provisional": today >= R.PROVISIONAL_RANKING,
            "t_review_request": f.review_requested,
            "t_review_decision": f.review_requested and today >= R.FINAL_RANKING,
            "t_no_review": not f.review_requested and today > R.PROVISIONAL_RANKING + dt.timedelta(days=5),
            "t_final": today >= R.FINAL_RANKING,
            "t_awarded": eligible is True, "t_not_awarded": eligible is False,
            "t_pay_first": today >= (R.FIRST_INSTALMENT_FIRST_YEAR if f.year == 1 and f.level != "LM" and not f.extra_semester else R.INSTALMENT_DEC)
            and not (f.non_eu and f.year == 1),
            # later years: merit was assessed ex ante, so the balance follows the payment calendar
            "t_merit_ok": f.year > 1 or f.extra_semester, "t_merit_fail": False,
            "t_pay_balance": today >= R.SECOND_INSTALMENT_LATER_YEARS, "t_revoke": False,
        }
        m, fired = Counter({SOURCE: 1}), []
        progress = True
        while progress:
            progress = False
            for tid in enabled(self.net, m):
                if happened.get(tid):
                    m = fire(self.net, m, tid)
                    fired.append(tid)
                    progress = True
                    break
        return m, fired

    def step(self, tid: str) -> ProcedureStep:
        t = self.net.transitions[tid]
        return ProcedureStep(id=t.id, name=t.name, lane=t.lane, article=t.article)

    # --- main --------------------------------------------------------------------------------
    def guide(self, f: ProcedureRequest, request_id: str) -> ProcedureResponse:
        today = dt.date.fromisoformat(f.today) if f.today else dt.date.today()
        lang = f.language
        li = {"it": 0, "en": 1, "ar": 2}[lang]
        results = self.evaluate(f, today)
        outcomes = {r.outcome for r in results}
        verdict = "not_eligible" if "fail" in outcomes else "check_with_office" if "check" in outcomes else "eligible"
        marking, fired = self.replay(f, today, {"eligible": True, "not_eligible": False}.get(verdict))
        status = ProcedureStatus(
            reference_date=today.isoformat(), marking=sorted(p for p, n in marking.items() if n),
            done=[self.step(t) for t in fired], next=[self.step(t) for t in enabled(self.net, marking)],
            finished=marking[SINK] == 1,
        )
        checklist: list[ChecklistItem] = []

        def item(iid, due, key, done=False, info=False):
            st = "done" if done else "info" if info else ("overdue" if due and today > due else "todo")
            checklist.append(ChecklistItem(id=iid, text=TEXTS[iid][li], due=due.isoformat() if due else None, status=st, citation=self.cite(key)))

        submitted = bool(f.application_submitted)
        if f.family_abroad:
            item("parificato", R.DEADLINE_APPLICATION, "parificato", done=submitted)
            item("integration", R.INTEGRATION_PARIFICATO, "integration", info=True)
        else:
            item("isee", R.DEADLINE_APPLICATION, "dsu_late", done=submitted)
        item("apply", R.DEADLINE_APPLICATION, "deadline", done=submitted)
        if f.bonus_credits and f.year > 1:
            item("bonus", R.DEADLINE_APPLICATION, "bonus", done=submitted)
        if f.non_eu:
            item("permit", R.PERMIT_COPY, "permit_copy", done=bool(f.has_residence_permit))
        item("ranking", R.PROVISIONAL_RANKING, "provisional", done=today > R.PROVISIONAL_RANKING)
        item("review", None, "review", info=True)
        item("iban", R.IBAN, "iban", info=submitted)  # the IBAN is asked in the application; the date is for who had none
        if f.year == 1 and not f.extra_semester:
            item("credits_first_year", R.MERIT_FIRST_YEAR, "merit_first_year")
            if f.non_eu:
                item("non_eu_first_year", None, "pay_non_eu", info=True)

        deadlines = [
            Deadline(date=R.DEADLINE_APPLICATION.isoformat(), title="Application deadline (online, confirmed)", indicative=False, citation=self.cite("deadline")),
            Deadline(date=R.PROVISIONAL_RANKING.isoformat(), title="Provisional ranking (indicative); request for review within 5 days", indicative=True, citation=self.cite("provisional")),
            Deadline(date=R.FINAL_RANKING.isoformat(), title="Final ranking (first half of October 2026)", indicative=True, citation=self.cite("final")),
            Deadline(date=R.IBAN.isoformat(), title="Last day to give your IBAN", indicative=False, citation=self.cite("iban")),
        ]
        if f.family_abroad:
            deadlines.insert(1, Deadline(date=R.INTEGRATION_PARIFICATO.isoformat(), title="Last day to complete ISEE parificato documents",
                                         indicative=False, citation=self.cite("integration")))
        if f.year == 1 and f.level != "LM" and not f.extra_semester:
            deadlines.append(Deadline(date=R.FIRST_INSTALMENT_FIRST_YEAR.isoformat(), title="First instalment (20%) at the latest",
                                      indicative=False, citation=self.cite("pay_first_year_nov")))
        deadlines.append(Deadline(date=R.INSTALMENT_DEC.isoformat(),
                                  title="Instalment at the latest" if f.year == 1 and not f.extra_semester else "First instalment (50%) at the latest",
                                  indicative=False, citation=self.cite("pay_later_years" if f.year > 1 or f.extra_semester else "pay_first_year")))
        if f.non_eu:
            deadlines.append(Deadline(date=R.PERMIT_COPY.isoformat(), title="Copy of the residence permit", indicative=False, citation=self.cite("permit_copy")))
        if f.year > 1 or f.extra_semester:
            deadlines.append(Deadline(date=R.SECOND_INSTALMENT_LATER_YEARS.isoformat(), title="Second instalment at the latest",
                                      indicative=False, citation=self.cite("pay_later_years")))
        else:
            deadlines += [
                Deadline(date=R.MERIT_FIRST_YEAR.isoformat(), title="20 credits for the balance", indicative=False, citation=self.cite("merit_first_year")),
                Deadline(date=R.MERIT_FIRST_YEAR_LAST.isoformat(), title="Last date for 20 credits, otherwise revocation", indicative=False,
                         citation=self.cite("revoke_first_year")),
            ]
        deadlines.sort(key=lambda d: d.date)
        ics = calendar([(d.date, f"ERDIS: {d.title}", f"{d.citation.section} - {d.citation.quote}" + (" (indicative date)" if d.indicative else ""))
                        for d in deadlines], today)
        category = f.residence or ("fuori_sede" if f.family_abroad else None)
        log.info("procedure guide", extra={"request_id": request_id, "verdict": verdict})  # facts are NOT logged
        return ProcedureResponse(
            request_id=request_id, language=lang, verdict=verdict, verdict_text=VERDICT[verdict][lang], rules=results,
            amount_category=category, amount_full_eur=R.AMOUNTS.get(category) if category else None, status=status,
            checklist=checklist, deadlines=deadlines, ics=ics, disclaimer=DISCLAIMER[lang],
        )
