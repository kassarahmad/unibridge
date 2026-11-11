# Scholarship procedure: BPMN model, workflow net, guide

The UniBridge scholarship guide follows the ERDIS Marche call for the scholarship a.y. 2026/2027
(`ub:erdis-bando-borsa-2026-27`, "the call"). The procedure is defined **once** in
`src/p14_search/procedure/model.py`; the BPMN diagram, the PNML workflow net and the guide's state machine
are all derived from it, so they cannot disagree.

```
python scripts/build_scholarship_model.py     # writes docs/bpmn/scholarship.bpmn, docs/bpmn/scholarship.pnml
                                               # and eval/results/unibridge/procedure_soundness.json
python eval/unibridge/eval_procedure.py       # 15 scenarios -> eval/results/unibridge/procedure_eval.json
```

## 1. Steps and deadlines (with the words of the call)

| Step (BPMN element) | Lane | Date | Source in the call |
|---|---|---|---|
| Call published (`start`) | ERDIS | - | ART. 1 |
| Sign DSU, obtain ISEE for university study (`t_dsu`) | Student | by 28/8/2026 | ART. 20 l): excluded who signed the DSU "successivamente al termine di scadenza per la presentazione della domanda" |
| Documents for the ISEE parificato, family abroad (`t_parificato`) | Student | by 28/8/2026; completion by 18/9/2026 | ART. 8.8: "entro lo stesso termine di scadenza della domanda del 28/8/2026"; "entro il 18 settembre 2026"; ART. 11.2 legalisation / apostille and Italian translation |
| Submit and confirm the online application (`t_apply`) | Student | 28/8/2026 | Art. 10.1: "entro il 28 agosto 2026, pena l'esclusione dal concorso" |
| Enrol at the university (`t_enrol`) | Student | dates of each university | ART. 3 |
| Check merit and economic requirements (`t_check`) | ERDIS | after 28/8/2026 | ART. 7 (merit), ART. 8 (ISEE <= 24,000 EUR, ISPE <= 50,000 EUR), ART. 14 |
| Provisional ranking (`t_provisional`) | ERDIS | ~15/9/2026 (indicative) | ART. 15.1: "Indicativamente entro il 15 settembre 2026" |
| Request for review, optional (`t_review_request`) | Student | 5 days after publication | ART. 15.2: "Entro il quinto giorno successivo alla data di pubblicazione sul sito dell'avviso" |
| Decision on the review (`t_review_decision`) | ERDIS | with the final ranking | ART. 15.2 |
| Final ranking (`t_final`) | ERDIS | first half of October 2026 | ART. 15.3: "entro la prima metà del mese di ottobre 2026" |
| Not awarded / excluded (`end_not_awarded`) | ERDIS | - | ART. 20 (causes of exclusion) |
| First instalment(s) (`t_pay_first`) | ERDIS | first year L/LMCU: 20 % by 10/11, 30 % by 31/12; later years: 50 % by 31/12/2026 | ART. 17.3; non-EU first-year students: first instalment when the credits are reached, unless a guarantee is given |
| Merit for the balance (`g_merit`) | ERDIS | first year: 20 credits by 10/8/2027, at the latest 30/11/2027 | ART. 7.16; ART. 21 f) revocation |
| Balance (`t_pay_balance`) | ERDIS | later years: by 30/6/2027; first year: when 20 credits are reached | ART. 17.3 |
| Revocation and recovery (`t_revoke`) | ERDIS | after 30/11/2027 | ART. 21, ART. 22 |

Other dates used by the guide: IBAN by 31/10/2026 if not given in the application (ART. 17.3);
copy of the residence permit for 2026/2027 by 3/5/2027 (ART. 11 e), without it non-EU students are
excluded (ART. 20 p).

## 2. BPMN model

`docs/bpmn/scholarship.bpmn` is BPMN 2.0 XML with diagram information (one pool, lanes *Student* and *ERDIS
Marche*). It opens in bpmn.io or Camunda Modeler. Elements: 1 start event, 11 tasks, 4 exclusive split /
merge gateways, 2 parallel gateways, 3 end events (24 nodes, 26 sequence flows).

Gateways:
- `g_and_split` / `g_and_join` (parallel): the economic documents and the enrolment are prepared
  independently; ERDIS checks the requirements only when the application is closed.
- `g_econ_split` (exclusive): family income in Italy -> ISEE via DSU; family abroad -> ISEE parificato.
- `g_review_split` (exclusive): optional request for review of the provisional ranking.
- `g_outcome` (exclusive): awarded or not.
- `g_merit` (exclusive): merit for the balance reached or not (first-year students).

## 3. Workflow net and soundness

The workflow net (`docs/bpmn/scholarship.pnml`, 18 places, 20 transitions, 42 arcs) uses the standard mapping:
task -> transition; exclusive split -> place with several output transitions; exclusive merge -> place with
several input transitions; parallel split/join -> transition with several output/input places; the three end
events -> transitions into the single sink place `o`. "No request for review", "awarded" and the merit
outcomes are silent transitions for gateway branches.

Soundness is checked twice (`eval/results/unibridge/procedure_soundness.json`):

| Check | Result |
|---|---|
| Workflow net: one source `i`, one sink `o`, every node on a path from `i` to `o` | yes |
| Reachable markings from `[i]` | 19 (bounded) |
| Option to complete, proper completion, no dead transitions (own code, `procedure/soundness.py`) | sound |
| pm4py 2.7.23.12, Woflan, on the exported PNML file | sound |

The tests (`tests/test_procedure.py`) also show that the checker is not trivially "sound": removing the review
decision leaves a student stuck in `p_review`, and an AND-join waiting for a place that is never marked gives
dead transitions; both are reported as not sound.

### How to verify it in WoPeD (manual step for Ahmad)

1. Install WoPeD (https://woped.dhbw-karlsruhe.de, Java). 2. *File -> Open* `docs/bpmn/scholarship.pnml`.
3. The layout is a simple grid by distance from `i`; move nodes if needed. 4. *Analyse -> Semantical
analysis* (soundness): WoPeD should report a workflow net that is sound (bounded, live after short-circuiting
`o` to `i`). 5. Take a screenshot of the net and of the analysis result and save it as
`docs/evidence/unibridge/woped_soundness.png`. *Not done in this session: WoPeD is a desktop application.*

## 4. The guide (state machine + rules)

`POST /v1/procedure/scholarship` (`src/p14_search/procedure/guide.py`) receives the student's facts (level,
year, credits, bonus, ISEE, ISPE, family abroad, non-EU, residence permit, ...), evaluates deterministic rules
and replays the workflow net:

- **Rules** (`procedure/rules.py`): application deadline, ISEE and ISPE limits, previous degree, duration of
  the benefit, merit table of Art. 7.5 with bonus credits (Art. 7.15, capped at 5 / 12 / 15), residence
  permit, amount category (Art. 12; foreign students with the family abroad are always *fuori sede*). Every
  rule carries the section and the exact quote of the call; at start-up the quote is matched to the indexed
  passage, so the citation is verifiable (28 quotes, all resolved). Cases the guide does not compute
  (disability, part-time, courses with proportional requirements of Art. 7.6) give `check`, never a guess.
- **State machine**: a transition fires only if it is enabled in the net and the facts or the date say it
  happened (e.g. the provisional ranking from 15/9/2026). The enabled transitions of the resulting marking
  are the next steps. Because the net is sound, every marking the guide reaches can still complete.
- **Output**: verdict (`eligible`, `not_eligible`, `check_with_office`), rules with citations, position in
  the procedure, personal checklist (done / todo / overdue / info) in Italian, English or Arabic, deadlines
  and an `.ics` calendar.
- **Privacy**: no LLM is involved; the facts are not stored and not logged (test
  `test_procedure_facts_are_not_logged_or_sent_to_an_llm`).

## 5. Evaluation

15 fictional students (`eval/unibridge/procedure_scenarios.json`), each with the expected verdict, rule
outcomes, checklist, net marking and next steps written from the call. Result
(`eval/results/unibridge/procedure_eval.json`): **15 of 15 scenarios fully correct**, all five fields at
1.0, 28 of 28 rule quotes resolved to passages.

Limit of this evaluation: the expected values and the code were written by the same author (the LLM coding
assistant) from the same reading of the call, so the test shows internal consistency, not independent
correctness. Ahmad should re-check the expected values against the call; the table of Art. 7.5 and the
payment calendar of Art. 17.3 are the parts most worth a second reading.
