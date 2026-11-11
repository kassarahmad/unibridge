"""Build the UniBridge question set: eval/queries/unibridge_queries.jsonl and eval/review/unibridge_review.csv.

Provenance of every query (field `source`):
- official_faq: the question text is copied from an official FAQ page (ERDIS Marche FAQ 2026/2027 or the
  UNICAM International FAQ; UNICAM writes its questions in capitals, here in sentence case). Ground truth =
  the official FAQ answer plus, where the FAQ restates the call, the article of the ERDIS call.
- llm_translation: English or Arabic translation of an official FAQ question, written by an LLM (Claude,
  the coding assistant of this project). Same targets as the original. `needs_native_review: true`.
- llm_paraphrase: everyday-language variant written by the LLM, with targets chosen from the documents.
- out_of_scope: questions the corpus cannot answer (LLM-written); no targets.

Split: whole groups (a FAQ question with all its translations and paraphrases) go to the same split, so
that tuning never sees a variant of a test question. ~1/3 of the groups are tuning (seeded shuffle,
stratified: in-scope groups and out-of-scope questions separately).

Usage:
    python eval/unibridge/make_queries.py
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "queries" / "unibridge_queries.jsonl"
REVIEW = ROOT / "eval" / "review" / "unibridge_review.csv"
SEED = 14
TUNING_SHARE = 1 / 3

B = "ub:erdis-bando-borsa-2026-27"
EN = "ub:erdis-call-scholarship-2026-27-en"
FB = "ub:erdis-faq-borsa-2026-27"
FI = "ub:erdis-faq-studenti-internazionali-2026-27"
FA = "ub:erdis-faq-alloggio-2026-27"
FR = "ub:erdis-faq-ristorazione-2026-27"
IF = "ub:intl-faq"


def t(doc: str, snippet: str, section: str | None = None) -> dict:
    return {"document_id": doc, "section": section, "snippet": snippet}


# group id -> (official question, language of the official text, FAQ document, targets,
#              {"en": translation, "ar": translation}, [(lang, paraphrase), ...])
GROUPS: dict[str, dict] = {
    "G01": dict(
        q="Quando posso presentare la domanda di benefici?", lang="it", faq=FB,
        targets=[t(FB, "il periodo va dalla pubblicazione dei bandi fino alla scadenza"),
                 t(B, "entro il 28 agosto 2026, pena l’esclusione dal concorso", "Art. 10")],
        tr={"en": "When can I submit the application for benefits?", "ar": "متى يمكنني تقديم طلب الحصول على المزايا؟"},
        para=[("it", "fino a quando posso fare la domanda per la borsa erdis?")],
    ),
    "G02": dict(
        q="Posso fare domanda di borsa di studio entro la scadenza se ho il test di ammissione in data successiva?", lang="it", faq=FB,
        targets=[t(FB, "può essere presentata indipendentemente dall’avvenuta iscrizione e/o superamento del test di ammissione")],
        tr={"ar": "هل يمكنني التقدم لطلب المنحة الدراسية قبل الموعد النهائي إذا كان امتحان القبول في تاريخ لاحق؟"},
        para=[],
    ),
    "G03": dict(
        q="Non ho presentato la domanda di borsa di studio entro la scadenza prevista dal bando, si può fare qualcosa?", lang="it", faq=FB,
        targets=[t(FB, "è perentorio ed inderogabile, non è pertanto possibile accettare domande oltre tale data"),
                 t(B, "che abbiano presentato la domanda oltre il termine di scadenza previsto dal presente bando", "ART. 20")],
        tr={"en": "I did not submit the scholarship application by the deadline in the call. Can anything be done?",
            "ar": "لم أقدم طلب المنحة الدراسية قبل الموعد النهائي المحدد في الإعلان، هل يمكن فعل شيء؟"},
        para=[("en", "i missed the scholarship deadline, can i still apply late?")],
    ),
    "G04": dict(
        q="Chi è lo studente \"in sede\", \"pendolare\", e \"fuori sede\"?", lang="it", faq=FB,
        targets=[t(B, "sono considerati in sede gli studenti residenti nel comune sede del corso di studio frequentato", "ART. 12"),
                 t(B, "gli studenti stranieri sono considerati comunque studenti fuori sede", "ART. 12"),
                 t(EN, "foreign students are, in any case, considered off-campus students", "ART. 12")],
        tr={"en": "Who counts as an \"on-campus\", \"commuter\" and \"off-campus\" student?",
            "ar": "من هو الطالب \"المقيم في مدينة الجامعة\" و\"المتنقل يوميًا\" و\"المقيم خارج مدينة الجامعة\"؟"},
        para=[("ar", "أنا طالب أجنبي، هل أعتبر طالبًا من خارج مدينة الجامعة؟")],
    ),
    "G05": dict(
        q="Per quanti anni posso richiedere la borsa di studio?", lang="it", faq=FB,
        targets=[t(FB, "per un periodo di sette semestri, a partire dall’anno di prima immatricolazione"),
                 t(B, "per un periodo di sette semestri, a partire dall’anno di prima immatricolazione", "ART. 4"),
                 t(EN, "for a period of seven semesters, starting from the year of initial enrolment", "ART. 4")],
        tr={"en": "For how many years can I apply for the scholarship?", "ar": "لكم سنة يمكنني طلب المنحة الدراسية؟"},
        para=[],
    ),
    "G06": dict(
        q="Se sono vincitore di borsa di studio, per confermare il beneficio per l’anno accademico successivo devo rifare la domanda?", lang="it", faq=FB,
        targets=[t(FB, "ha validità per un anno accademico, pertanto va ripresentata anno per anno")],
        tr={"en": "If I win a scholarship, do I have to apply again to keep it for the next academic year?",
            "ar": "إذا فزت بالمنحة الدراسية، هل يجب أن أقدم الطلب من جديد للحفاظ عليها في السنة الأكاديمية التالية؟"},
        para=[("it", "la borsa si rinnova da sola o devo rifare la domanda ogni anno?")],
    ),
    "G07": dict(
        q="Ho già una laurea: posso presentare domanda di borsa di studio?", lang="it", faq=FB,
        targets=[t(FB, "solo per il conseguimento del primo titolo per ciascun livello di studio"),
                 t(B, "che siano in possesso di altra laurea di pari o superiore livello", "ART. 20")],
        tr={"en": "I already have a degree: can I apply for a scholarship?", "ar": "لدي شهادة جامعية بالفعل: هل يمكنني التقدم بطلب للحصول على منحة دراسية؟"},
        para=[],
    ),
    "G08": dict(
        q="Quali sono i requisiti di accesso alla borsa di studio per 1° anno di corso?", lang="it", faq=FB,
        targets=[t(FB, "entro la scadenza del bando al disotto delle soglie isee ed ispe previste dal bando stesso"),
                 t(B, "isee fino a € 24.000,00", "ART. 8"),
                 t(EN, "isee up to € 24,000.00", "ART. 8")],
        tr={"en": "What are the requirements to get the scholarship in the first year of a course?",
            "ar": "ما هي شروط الحصول على المنحة الدراسية في السنة الأولى من الدراسة؟"},
        para=[("it", "qual è il limite di isee per avere la borsa di studio?"),
              ("ar", "ما هو الحد الأقصى لمؤشر ISEE للحصول على منحة ERDIS؟")],
    ),
    "G09": dict(
        q="Quali sono i requisiti di accesso alla borsa di studio per il 2° anno di corso?", lang="it", faq=FB,
        targets=[t(FB, "avere assolto gli ofa (obblighi formativi aggiuntivi) entro la data del 10 agosto"),
                 t(B, "oltre ad aver maturato i crediti indicati in tabella per poter concorrere alla borsa di studio", "ART. 7")],
        tr={"en": "What are the requirements to get the scholarship in the second year?",
            "ar": "ما هي شروط الحصول على المنحة الدراسية في السنة الثانية؟"},
        para=[("en", "how many credits do i need by august to keep the scholarship in second year?")],
    ),
    "G10": dict(
        q="Come posso utilizzare i punti bonus?", lang="it", faq=FB,
        targets=[t(B, "5 crediti, se utilizzato per la prima volta per il conseguimento dei benefici per il secondo anno accademico", "ART. 7"),
                 t(EN, "claiming bonus credits for the sole purpose of meeting the minimum merit requirements", "ART. 7")],
        tr={"en": "How can I use the bonus points?", "ar": "كيف يمكنني استخدام نقاط المكافأة (البونص)؟"},
        para=[],
    ),
    "G11": dict(
        q="Se i crediti inseriti in domanda non vengono registrati come sostenuti entro il 10 agosto cosa succede?", lang="it", faq=FB,
        targets=[t(FB, "essi non saranno considerati ai fini del conteggio per il conseguimento del requisito di merito")],
        tr={"ar": "ماذا يحدث إذا لم تُسجَّل الساعات المعتمدة التي أدخلتها في الطلب قبل 10 أغسطس؟"},
        para=[],
    ),
    "G12": dict(
        q="Di quali benefici si compone la borsa di studio?", lang="it", faq=FB,
        targets=[t(FB, "ha diritto ad una quota contante in base alla propria condizione economica e ad un pasto gratuito giornaliero")],
        tr={"en": "What benefits does the scholarship include?", "ar": "ما هي المزايا التي تتضمنها المنحة الدراسية؟"},
        para=[],
    ),
    "G13": dict(
        q="Quando viene erogata la quota contante spettante della borsa di studio?", lang="it", faq=FB,
        targets=[t(B, "la prima rata della borsa, in misura pari al 20% del totale", "ART. 17"),
                 t(FB, "la prima rata della borsa, in misura pari al 20% del totale"),
                 t(EN, "the first instalment of the grant, amounting to 20 per cent of the total", "ART. 17")],
        tr={"en": "When is the cash part of the scholarship paid?", "ar": "متى يتم صرف الجزء النقدي من المنحة الدراسية؟"},
        para=[("ar", "متى سأستلم أول دفعة من المنحة؟")],
    ),
    "G14": dict(
        q="Cosa si intende per studente indipendente?", lang="it", faq=FB,
        targets=[t(FB, "residenza esterna a quella della famiglia d’origine da almeno due anni"),
                 t(B, "redditi dello studente da lavoro dipendente o assimilati fiscalmente dichiarati, da almeno due anni", "ART. 8")],
        tr={"en": "What is meant by an independent student?", "ar": "ما المقصود بالطالب المستقل؟"},
        para=[],
    ),
    "G15": dict(
        q="Verrò avvisato della pubblicazione della graduatoria?", lang="it", faq=FB,
        targets=[t(FB, "non verrà inviata nessuna comunicazione individuale riguardo l’esito dei concorsi")],
        tr={},
        para=[],
    ),
    "G16": dict(
        q="Come posso comunicare con l’Ufficio Diritto allo studio per avere informazioni sui benefici?", lang="it", faq=FB,
        targets=[t(FB, "lo studente deve utilizzare il nuovo modulo srm")],
        tr={"ar": "كيف يمكنني التواصل مع مكتب الحق في الدراسة للحصول على معلومات حول المزايا؟"},
        para=[],
    ),
    "G17": dict(
        q="Come viene erogata la quota monetaria?", lang="it", faq=FB,
        targets=[t(FB, "accredito su conto corrente (aperto presso un istituto di credito italiano"),
                 t(B, "accredito su conto corrente (aperto presso un istituto di credito italiano", "ART. 17")],
        tr={"ar": "كيف يتم دفع المبلغ النقدي للمنحة؟"},
        para=[("en", "do i need an italian bank account to receive the scholarship money?")],
    ),
    "G18": dict(
        q="Se, con la graduatoria definitiva, mi viene revocata la borsa di studio, a quali conseguenze vado incontro?", lang="it", faq=FB,
        targets=[t(FB, "restituire le somme eventualmente percepite")],
        tr={},
        para=[],
    ),
    "G19": dict(
        q="Ho deciso di rinunciare agli studi universitari o di trasferirmi presso un Ateneo fuori regione, che conseguenze avrò considerando che attualmente risulto beneficiario di Borsa di studio?", lang="it", faq=FB,
        targets=[t(FB, "se rinuncio agli studi o mi trasferisco prima del giorno 31 di agosto"),
                 t(B, "aver rinunciato agli studi (prima del 31 agosto)", "ART. 21")],
        tr={"ar": "قررت ترك الدراسة الجامعية أو الانتقال إلى جامعة خارج المنطقة، ما العواقب علي بما أنني مستفيد حاليًا من منحة دراسية؟"},
        para=[],
    ),
    "G20": dict(
        q="Quando vengono pubblicate le graduatorie?", lang="it", faq=FB,
        targets=[t(FB, "indicativamente entro metà settembre"),
                 t(B, "indicativamente entro il 15 settembre 2026", "ART. 15"),
                 t(EN, "by 15 september 2026, following a decision by the relevant head of department", "ART. 15")],
        tr={"en": "When are the rankings published?", "ar": "متى يتم نشر قوائم الترتيب؟"},
        para=[("it", "quando escono i risultati della borsa erdis?")],
    ),
    "G21": dict(
        q="Come posso inoltrare una istanza di revisione?", lang="it", faq=FB,
        targets=[t(FB, "entro il quinto giorno successivo alla data di pubblicazione"),
                 t(B, "entro il quinto giorno successivo alla data di pubblicazione", "ART. 15"),
                 t(EN, "by the fifth day following the date of publication", "ART. 15")],
        tr={"en": "How can I submit a request for review?", "ar": "كيف يمكنني تقديم طلب مراجعة؟"},
        para=[("en", "i was excluded from the provisional ranking, how do i appeal?")],
    ),
    "G22": dict(
        q="Qual è la scadenza per la presentazione della domanda ai vari benefici?", lang="it", faq=FI,
        targets=[t(FI, "per l’a.a. 2026/2027 la scadenza è fissata al 28 agosto 2026"),
                 t(B, "entro il 28 agosto 2026, pena l’esclusione dal concorso", "Art. 10")],
        tr={"en": "What is the deadline for applying for the various benefits?", "ar": "ما هو الموعد النهائي لتقديم طلب المزايا المختلفة؟"},
        para=[("ar", "آخر موعد لتقديم طلب منحة ERDIS؟")],
    ),
    "G23": dict(
        q="I documenti possono essere scritti nella lingua del mio Paese?", lang="it", faq=FI,
        targets=[t(FI, "deve essere allegata una traduzione in lingua italiana"),
                 t(B, "deve essere allegata una traduzione in lingua italiana certificata conforme al testo straniero", "ART. 11")],
        tr={"en": "Can the documents be written in the language of my country?", "ar": "هل يمكن أن تكون الوثائق مكتوبة بلغة بلدي؟"},
        para=[],
    ),
    "G24": dict(
        q="Posso avvalermi della facoltà di autocertificazione?", lang="it", faq=FI,
        targets=[t(FI, "gli studenti stranieri non possono avvalersi della facoltà di autocertificazione"),
                 t(B, "non è possibile avvalersi della facoltà di autocertificazione", "ART. 11"),
                 t(EN, "it is not possible to make use of the self-certification option", "ART. 11")],
        tr={"en": "Can I use a self-declaration instead of certificates?", "ar": "هل يمكنني الاعتماد على الإقرار الذاتي بدلًا من الشهادات؟"},
        para=[],
    ),
    "G25": dict(
        q="A quali Autorità del mio Paese devo rivolgermi per la legalizzazione dei documenti richiesti?", lang="it", faq=FI,
        targets=[t(FI, "ammesso l’utilizzo dell’apostille"),
                 t(B, "è ammesso l’utilizzo dell’apostille in luogo della legalizzazione", "ART. 11"),
                 t(EN, "the use of an apostille is permitted in place of legalisation by the italian embassy", "ART. 11")],
        tr={"en": "Which authorities of my country must legalise the required documents?",
            "ar": "إلى أي سلطات في بلدي يجب أن أتوجه لتصديق الوثائق المطلوبة؟"},
        para=[("ar", "هل يكفي الأبوستيل بدل تصديق السفارة الإيطالية؟")],
    ),
    "G26": dict(
        q="In caso non vi siano redditi percepiti o patrimoni immobiliari di proprietà devo ugualmente presentare certificati?", lang="it", faq=FI,
        targets=[t(FI, "per i componenti il nucleo familiare maggiorenni sono ugualmente necessari i certificati")],
        tr={"ar": "إذا لم يكن هناك دخل أو عقارات مملوكة، هل يجب علي تقديم شهادات على أي حال؟"},
        para=[],
    ),
    "G27": dict(
        q="Entro quando devo presentare il permesso di soggiorno?", lang="it", faq=FI,
        targets=[t(FI, "purché entro la data del 3/5/2027"),
                 t(B, "purché entro la data del 3/5/2027", "ART. 11"),
                 t(EN, "provided this is done by 3 may 2027", "ART. 11")],
        tr={"en": "By when must I submit my residence permit?", "ar": "ما هو آخر موعد لتقديم تصريح الإقامة؟"},
        para=[("it", "non ho ancora il permesso di soggiorno, perdo la borsa?")],
    ),
    "G28": dict(
        q="I valori di reddito e di patrimoni dei soggetti del nucleo familiare riportati debbono essere espressi in moneta del mio Paese o in Euro?", lang="it", faq=FI,
        targets=[t(FI, "debbono essere espressi nella moneta del proprio paese di provenienza")],
        tr={"en": "Must the income and assets of my family be stated in the currency of my country or in euro?",
            "ar": "هل يجب أن تُذكر قيم دخل وممتلكات أفراد الأسرة بعملة بلدي أم باليورو؟"},
        para=[],
    ),
    "G29": dict(
        q="Sono previste ulteriori scadenze?", lang="it", faq=FI,
        targets=[t(FI, "potrà inviare ulteriore documentazione integrativa della precedente entro il 21/10/2026")],
        tr={},
        para=[("it", "ho mandato documenti incompleti per l'isee parificato, posso integrarli dopo?")],
    ),
    "G30": dict(
        q="Se sono vincitore di borsa di studio ho diritto all’alloggio gratuito?", lang="it", faq=FA,
        targets=[t(FA, "ha diritto all’alloggio gratuito se è nella condizione di studente fuori sede")],
        tr={"en": "If I win a scholarship, am I entitled to free accommodation?", "ar": "إذا فزت بالمنحة الدراسية، هل يحق لي الحصول على سكن مجاني؟"},
        para=[],
    ),
    "G31": dict(
        q="Sono risultato “Assegnatario posto letto” con le graduatorie provvisorie, entro quanto tempo devo confermare che accetto l’alloggio?", lang="it", faq=FA,
        targets=[t(FA, "lo studente vincitore di posto alloggio deve comunicare l’accettazione del posto letto")],
        tr={"ar": "حصلت على سرير في السكن في القوائم المؤقتة، خلال كم من الوقت يجب أن أؤكد قبولي للسكن؟"},
        para=[],
    ),
    "G32": dict(
        q="Per quanto tempo posso usufruire dell’alloggio gratuito?", lang="it", faq=FA,
        targets=[t(FA, "per un periodo di dieci mesi a partire dall’inizio delle attività didattiche"),
                 t(B, "il servizio alloggio verrà concesso per un periodo di 10 mesi", "ART. 17")],
        tr={},
        para=[],
    ),
    "G33": dict(
        q="Posso scegliere la tipologia di alloggio?", lang="it", faq=FA,
        targets=[t(FA, "non è possibile scegliere la tipologia di alloggio")],
        tr={},
        para=[],
    ),
    "G34": dict(
        q="Quale certificato devo presentare al momento dell’assegnazione?", lang="it", faq=FA,
        targets=[t(FA, "un certificato medico, non anteriore a 15 giorni rispetto alla data di entrata")],
        tr={},
        para=[],
    ),
    "G35": dict(
        q="Cosa posso fare se i posti non sono sufficienti a coprire tutte le richieste dei vincitori e rimango senza alloggio?", lang="it", faq=FA,
        targets=[t(FA, "alla data del 19/10/2026 non sia in grado di alloggiarli"),
                 t(B, "alla data del 19/10/2026 non sia in grado di alloggiarli", "ART. 17"),
                 t(EN, "as at 19 october 2026, it is unable to accommodate them", "ART. 17")],
        tr={},
        para=[],
    ),
    "G36": dict(
        q="A quale importo corrisponde la tariffa agevolata?", lang="it", faq=FR,
        targets=[t(FR, "6,50 per il pasto intero/completo")],
        tr={},
        para=[],
    ),
    "G37": dict(
        q="Sono uno studente vincitore di posto letto a pagamento, ho diritto al pasto gratuito?", lang="it", faq=FR,
        targets=[t(FR, "gli studenti che non hanno la borsa di studio possono accedere al servizio ristorazione a tariffa agevolata")],
        tr={},
        para=[],
    ),
    "G38": dict(
        q="Sono uno studente intollerante al glutine, posso consumare pasti “gluten free” a mensa?", lang="it", faq=FR,
        targets=[t(FR, "è possibile fruire di pasti per celiaci o per intolleranti")],
        tr={},
        para=[],
    ),
    # --- UNICAM International FAQ (official questions in English) ---
    "G39": dict(
        q="I am a prospective student. When should I apply for the pre-admission?", lang="en", faq=IF,
        targets=[t(IF, "international students interested in enrolling at unicam must apply for pre-admission")],
        tr={"it": "Sono un futuro studente. Quando devo fare domanda di pre-ammissione?", "ar": "أنا طالب مستقبلي. متى يجب أن أتقدم بطلب القبول المسبق؟"},
        para=[],
    ),
    "G40": dict(
        q="Are the admission procedures the same for EU and non-EU students?", lang="en", faq=IF,
        targets=[t(IF, "whether eu or non-eu, are invited to partecipate in the pre-admission procedure")],
        tr={},
        para=[],
    ),
    "G41": dict(
        q="How to obtain the official fiscal code", lang="en", faq=IF,
        targets=[t(IF, "the welcome office of unicam offers support to apply for it")],
        tr={"it": "Come si ottiene il codice fiscale ufficiale?", "ar": "كيف أحصل على الرمز الضريبي الرسمي (الكوديتشي فيسكالي)؟"},
        para=[],
    ),
    "G42": dict(
        q="I want to apply for a degree course taught in Italian. Which level of Italian should I have?", lang="en", faq=IF,
        targets=[t(IF, "by law it is required a proficiency at level min b2"),
                 t("ub:intl-pre-admissions-2026-27", "must upload an official certificate of italian proficiency at level min. b2")],
        tr={"it": "Voglio iscrivermi a un corso di laurea in italiano. Quale livello di italiano devo avere?", "ar": "أريد التسجيل في برنامج يُدرَّس باللغة الإيطالية. ما هو مستوى اللغة الإيطالية المطلوب؟"},
        para=[],
    ),
    "G43": dict(
        q="Do I need to provide any English language proficiency certificate?", lang="en", faq=IF,
        targets=[t(IF, "is warmly recommended but not mandatory")],
        tr={},
        para=[],
    ),
    "G44": dict(
        q="Does the university provide any help for getting the visa?", lang="en", faq=IF,
        targets=[t(IF, "the application for an entry visa for study is under personal responsibility")],
        tr={"it": "L'università offre aiuto per ottenere il visto?", "ar": "هل تقدم الجامعة أي مساعدة للحصول على التأشيرة؟"},
        para=[],
    ),
    "G45": dict(
        q="How much is the average living cost for a single person per month?", lang="en", faq=IF,
        targets=[t(IF, "ranges between €500 and €800")],
        tr={"ar": "كم يبلغ متوسط تكلفة المعيشة لشخص واحد في الشهر؟"},
        para=[("it", "quanto si spende al mese per vivere a camerino?")],
    ),
    "G46": dict(
        q="Does the university provide any insurance coverage?", lang="en", faq=IF,
        targets=[t(IF, "covered by law by an insurance in case of accidents occurring inside the university structures")],
        tr={"it": "L'università offre una copertura assicurativa?", "ar": "هل توفر الجامعة أي تغطية تأمينية؟"},
        para=[],
    ),
    "G47": dict(
        q="From where do I pick up the residence permit application and to where must I submit it?", lang="en", faq=IF,
        targets=[t(IF, "within 8 working days from your arrival in italy, the request for the residence permit must be sent by post")],
        tr={"it": "Dove ritiro la domanda di permesso di soggiorno e dove devo presentarla?", "ar": "من أين أحصل على طلب تصريح الإقامة وإلى أين يجب أن أرسله؟"},
        para=[("en", "how many days do i have after arriving in italy to ask for the residence permit?")],
    ),
    "G48": dict(
        q="I am a European student, do I need to apply for a residence permit?", lang="en", faq=IF,
        targets=[t(IF, "eu/eaa citizens do not need to apply for a residence permit")],
        tr={"it": "Sono uno studente europeo, devo chiedere il permesso di soggiorno?", "ar": "أنا طالب أوروبي، هل أحتاج إلى التقدم بطلب للحصول على تصريح إقامة؟"},
        para=[],
    ),
    "G49": dict(
        q="Is there an Italian language course for new students?", lang="en", faq=IF,
        targets=[t(IF, "contact the language office")],
        tr={},
        para=[],
    ),
    "G50": dict(
        q="How can I get the free bus ticket?", lang="en", faq=IF,
        targets=[t(IF, "you must go to the ticket office of the local bus company")],
        tr={"it": "Come posso avere l'abbonamento gratuito per l'autobus?", "ar": "كيف يمكنني الحصول على تذكرة الحافلة المجانية؟"},
        para=[],
    ),
    "G51": dict(
        q="From where can I get my canteen card and how much does it cost?", lang="en", faq=IF,
        targets=[t(IF, "students get their canteen card at the erdis cash desk")],
        tr={"it": "Dove ritiro la tessera mensa e quanto costa?"},
        para=[],
    ),
    "G52": dict(
        q="I have been awarded of an ERDIS scholarship. To complete the documentation required, where can I make my ISEEU, and how?", lang="en", faq=IF,
        targets=[t(IF, "it is issued by the caaf (fiscal assistance centre)")],
        tr={"it": "Ho vinto una borsa ERDIS. Per completare i documenti richiesti, dove e come posso fare l'ISEEU?", "ar": "حصلت على منحة ERDIS. لاستكمال الوثائق المطلوبة، أين وكيف يمكنني إصدار شهادة ISEEU؟"},
        para=[],
    ),
    # --- groups made only of LLM paraphrases (UNICAM pages without an official FAQ) ---
    "P01": dict(
        q=None, lang="it", faq=None,
        targets=[t("ub:unicam-tasse", "è previsto l’esonero dal contributo onnicomprensivo annuale per chi ha un isee-u fino a 26.000 euro")],
        tr={}, para=[("it", "con isee basso devo pagare le tasse universitarie a unicam?"),
                     ("en", "is there a no-tax area at unicam for students with low isee?")],
    ),
    "P02": dict(
        q=None, lang="it", faq=None,
        targets=[t("ub:unicam-decadenza-rinuncia", "è possibile in ogni momento rinunciare allo status di studente")],
        tr={}, para=[("it", "come faccio a rinunciare agli studi a unicam?")],
    ),
    "P03": dict(
        q=None, lang="en", faq=None,
        targets=[t("ub:intl-tuition-fees", "payment of tuition fees can be carried out only by pagopa")],
        tr={}, para=[("ar", "كيف أدفع الرسوم الدراسية في جامعة كاميرينو؟")],
    ),
}

OUT_OF_SCOPE = [
    ("it", "Come si rinnova la patente di guida italiana?"),
    ("it", "Qual è il miglior ristorante di pesce ad Ancona?"),
    ("it", "Quanto costa un abbonamento in palestra a Macerata?"),
    ("it", "Come si apre una partita IVA come freelance?"),
    ("it", "Chi ha vinto il campionato di calcio di Serie A?"),
    ("en", "How do I get a SIM card with an Italian phone number?"),
    ("en", "What is the weather forecast for Rome tomorrow?"),
    ("en", "Can you recommend a good laptop for programming?"),
    ("en", "How do I file a tax return in Germany?"),
    ("ar", "كيف أحضّر طبق الكسكس بالخضار؟"),
    ("ar", "ما هي أفضل جامعة لدراسة الطب في ألمانيا؟"),
    ("ar", "كم سعر تذكرة الطيران من القاهرة إلى روما؟"),
    ("ar", "كيف أتعلم البرمجة بلغة بايثون من الصفر؟"),
]


def build() -> list[dict]:
    rows: list[dict] = []
    rng = random.Random(SEED)
    tuning: set[str] = set()
    # stratified: in-scope groups and out-of-scope questions are split separately
    for groups in (list(GROUPS), [f"OOS{i + 1:02d}" for i in range(len(OUT_OF_SCOPE))]):
        rng.shuffle(groups)
        tuning.update(groups[: round(len(groups) * TUNING_SHARE)])

    def add(group: str, query: str, lang: str, qtype: str, source: str, targets: list[dict], **extra) -> None:
        rows.append({
            "qid": f"U{len(rows) + 1:03d}", "query": query, "lang": lang, "type": qtype, "source": source, "group": group,
            "principal": "visitor", "split": "tuning" if group in tuning else "test", "targets": targets,
            "llm_generated": source != "official_faq", "needs_native_review": lang == "ar" or source == "llm_translation",
            **extra,
        })

    for gid, g in GROUPS.items():
        orig = None
        if g["q"]:
            add(gid, g["q"], g["lang"], "faq", "official_faq", g["targets"], faq_document=g["faq"])
            orig = rows[-1]["qid"]
        for lang, text in g["tr"].items():
            add(gid, text, lang, "translation", "llm_translation", g["targets"], translation_of=orig)
        for lang, text in g["para"]:
            add(gid, text, lang, "paraphrase", "llm_paraphrase", g["targets"])
    for i, (lang, text) in enumerate(OUT_OF_SCOPE):
        add(f"OOS{i + 1:02d}", text, lang, "out_of_scope", "out_of_scope", [])
    return rows


def main() -> int:
    rows = build()
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["qid", "lang", "source", "query", "original_query", "why_review", "reviewer_ok (y/n)", "corrected_text", "notes"])
        by_qid = {r["qid"]: r for r in rows}
        for r in rows:
            if r["lang"] == "ar" or r["llm_generated"]:
                why = "Arabic" if r["lang"] == "ar" else ""
                why += (" + " if why else "") + ("LLM-drafted" if r["llm_generated"] else "")
                orig = by_qid[r["translation_of"]]["query"] if r.get("translation_of") else ""
                w.writerow([r["qid"], r["lang"], r["source"], r["query"], orig, why, "", "", ""])
    n = len(rows)
    by = lambda k: {v: sum(1 for r in rows if r[k] == v) for v in sorted({r[k] for r in rows})}  # noqa: E731
    print(f"{n} queries; lang {by('lang')}; source {by('source')}; split {by('split')}")
    print(f"-> {OUT.relative_to(ROOT)}, {REVIEW.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
