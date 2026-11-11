# Open questions

| # | Question | Status |
|---|---|---|
| Q1 | Is P14 assigned to us / still available? | Requires professor confirmation |
| Q2 | Group size and composition (individual or group work?) | Requires professor confirmation |
| Q3 | Deadlines, exam dates, intermediate checkpoints | Requires professor confirmation |
| Q4 | Format and language of the final report and presentation | Requires professor confirmation |
| Q5 | Relation between the AI Puzzle project and the formal-modelling part of the course (BPMN / Petri nets / UPPAAL): separate assessments or one project? Is a formal model of our piece expected? | Requires professor confirmation |
| Q6 | How will the final composition phase work (shared environment, required protocol, live demo)? | Requires professor confirmation |
| Q7 | Must the case study use real organizational documents, or are public/synthetic corpora acceptable? | Requires professor confirmation |
| Q8 | Are paid LLM APIs allowed/expected, or is a fully local solution preferred? | Requires professor confirmation |
| Q9 | Grading criteria and weights | Requires professor confirmation |
| Q10 | P25 sheet says "P14 Search: feeds the knowledge base" while the P14 sheet says P14 "provides retrieval" to P25. Is the P14-P25 connection bidirectional (P25 cards indexed by P14, P14 retrieval used by P25)? | Requires professor confirmation |
| Q11 | Gazzetta Ufficiale issues used as PDFs contain unrelated acts naming private individuals (published officially). Is keeping them in a local research corpus acceptable, or should non-target acts be removed? | Requires professor confirmation |
| Q12 | Are LLM-drafted queries and relevance judgments acceptable for the evaluation if reviewed by the student, or is an independent human annotation required? | Requires professor confirmation |
| Q13 | The synthetic Ente Demo documents were written with an LLM: is this acceptable as the "selected case study", given Q7? | Requires professor confirmation |
| Q14 | What is the course policy on AI assistants (code, documentation, synthetic data, relevance judgments)? How should their use be declared in the report? | Requires professor confirmation |

## UniBridge

| # | Question | Status |
|---|---|---|
| U1 | `www.studiare-in-italia.it` (official MUR site for international students) returned HTTP 502 on 2026-11-11. The ministerial circular 2026-2028 is taken from the University of Ferrara copy. Re-check the official source before the exam. | Open: retry later |
| U2 | `questure.poliziadistato.it` serves an HTML page instead of the study-permit PDF to scripts (bot protection). The document is not in the corpus; residence-permit questions rely on the UNICAM tutorial, the MUR circular and the ERDIS rules. | Open: could be downloaded by hand if the licence is confirmed |
| U3 | www.unicam.it pages are "protected by copyright" (note legali) and have no open licence. They are used locally for a university project and not redistributed. Is this acceptable for the course, and would UNICAM authorise a public demo? | Requires professor / UNICAM confirmation |
| U4 | Arabic and English translations of official FAQ questions were produced by an LLM. They need review by a native speaker (eval/review/unibridge_review.csv). | Requires Ahmad's review |
| U5 | Relevance judgments come from Italian FAQ answers. English questions retrieve many passages of the English versions of the call and of the teaching regulation, which the qrels rarely grade (see REPORT_UNIBRIDGE, S3 experiment). Should equivalent passages of the English versions be graded as relevant? | Requires Ahmad's review of the qrels |
| U6 | The answer faithfulness check is the verifier's own LLM call; an independent check needs the human review of eval/review/unibridge_answers_review.csv (30 answers). | Requires Ahmad's review |
| U7 | Extension asked by Ahmad (2026-11-11): all languages of international students, and help on all university rules. Languages: done (17 languages, src/p14_search/i18n.py; evaluated on eval/queries/unibridge_queries_ml.jsonl). The fixed texts in the 14 added languages are LLM translations (eval/review/unibridge_i18n_review.csv). Corpus: not extended yet; more documents need a licence check each. | Languages done; corpus open |
| U8 | Questions and interface texts in the 14 added languages (French ... Chinese) were translated by the LLM; none was checked by a native speaker (eval/review/unibridge_ml_review.csv, eval/review/unibridge_i18n_review.csv). | Requires native speakers |
