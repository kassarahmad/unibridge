# UniBridge data

All numbers in this file come from `eval/results/unibridge/corpus_stats.json` (written by
`python scripts/corpus_stats.py --profile unibridge`) and from `data/raw/unibridge/fetch_record.json`
(written by `scripts/fetch_corpus_unibridge.py`).

## 1. Sources

The corpus has **42 real public documents** and **6 synthetic documents** (48 documents, 2,330 passages,
snapshot `idx-87d61fa1037b8705`). The full list with URLs is in `data/unibridge_manifest.json`; the
download record (URL, fetch date, SHA-256 of the original response and of the ingested file) is
`data/raw/unibridge/fetch_record.json`, recreated by:

```
python scripts/fetch_corpus_unibridge.py    # downloads into data/raw/unibridge/ (not committed)
python scripts/ingest_unibridge.py          # ingests and approves into the UniBridge profile
python scripts/corpus_stats.py --profile unibridge
```

| Publisher | Real documents | What |
|---|---|---|
| ERDIS Marche (regional right-to-study body) | 13 | Scholarship call 2026/2027 (Italian and English), FAQ on scholarship, international students, housing and canteen, guides to the call and to the online application, housing regulation, canteen rules and prices |
| Università di Camerino (UNICAM) | 17 | Manifesto degli studi 2026/2027 (main text, reductions, course offer), student guide 2026/2027, student career regulation, student contribution regulation, teaching regulation (IT and EN), exam guide, calls (studentato diffuso, Talenti), web pages on fees, withdrawal and interruption, transfers, scholarships, certificates, housing |
| UNICAM International Office | 10 | FAQ for international students, tuition fees, pre-admission 2026/2027, lump-sum enrolment payment, residence permit tutorial (page and PDF), pre-arrival information, scholarships, how to prepare, food and lodging |
| Ministero dell'Università e della Ricerca | 1 | Circular on entry, stay and enrolment of international students, a.y. 2026/2027 and 2027/2028 |
| Repubblica Italiana (Normattiva) | 1 | D.Lgs. 68/2012 (right to university study) |

By language: 30 documents in Italian, 12 in English. By type: 9 regulations, 4 calls, 5 FAQ, 7 guides,
14 web pages, 1 circular, 1 law, 1 notice (`real_documents_by_*` in `corpus_stats.json`).

**Not reachable (recorded in `fetch_record.json` -> `failures`, see `docs/OPEN_QUESTIONS.md` U1-U2):**
- `questure.poliziadistato.it` notice on study residence permits: the server returns an HTML page instead
  of the PDF to a script (bot protection). Not used.
- `www.studiare-in-italia.it` (official MUR site for international students) returned HTTP 502 on
  2026-11-11. The same ministerial circular is taken from the University of Ferrara copy
  (`unife.it`), which publishes the signed ministerial PDF; this is stated in the manifest `note`.

## 2. Licences and conditions of use

Checked on 2026-11-11; the licence key of every document is in the manifest.

| Key | Documents | Basis |
|---|---|---|
| `erdis` | 13 | erdis.it/note-legali: "open by default ai sensi dell'art. 52 D.Lgs. 82/2005 ... rilasciati con licenza CC-BY 4.0". Attribution: ERDIS Marche. |
| `unicam_act` | 9 | Regulations, manifesto and calls adopted by rector's decree: official acts of a public administration, excluded from copyright by art. 5 L. 633/1941. |
| `unicam_web` | 18 | www.unicam.it/note-legali states that site contents are protected by copyright and gives no open licence. Used locally for a non-commercial university project; raw files are not committed or redistributed; only short quotations (art. 70 L. 633/1941) appear in committed evaluation files. Permission would be needed for any public deployment (OPEN_QUESTIONS U3). |
| `state_act` | 2 | Law and ministerial circular: official acts of the State, art. 5 L. 633/1941. |

## 3. Processing

- PDFs are ingested as served. The P14 PDF parser was extended with one rule: an article number followed by
  an upper-case title on the same line (e.g. `ART. 7 REQUISITI DI MERITO`, `Art. 10 TERMINI E MODALITÀ ...`)
  starts a section. This lets citations name the article of the ERDIS call. The rule does not change any
  P14 document: all 57 D1 raw files parse to identical blocks before and after the change (checked in the
  session that added it; the test `test_pdf_long_upper_case_article_titles_start_sections` covers the rule).
- HTML pages: the script keeps only the page content region (CSS selector in the manifest) and turns FAQ
  questions written in bold at the start of a paragraph into `<h3>` headings, so each FAQ answer becomes a
  section whose title is the question.
- D.Lgs. 68/2012 is downloaded from Normattiva with the P14 fetcher.
- Everything else is the P14 pipeline: same document and passage ids, same chunker (`chunker-1`), same
  ACL, same citations, same human-approval step (simulated owner approval, logged in `approval_log`).

## 4. Roles and synthetic documents

UniBridge roles reuse the P14 access levels (`config/principals_unibridge.json`):

| Role | P14 level | Sees |
|---|---|---|
| visitor | public | the 42 real public documents |
| student | internal | + 3 student-only notices |
| scholarship / student / international office | restricted, own office | + that office's internal note |
| unibridge-admin | restricted, all offices | everything |

The 6 restricted documents (3 `internal`, 3 `restricted`; 25 passages) are **synthetic**: written by an LLM
(Claude, in the coding session), flagged `synthetic: true` and `llm_generated: true`, titled `[SINTETICO]`,
and each states in its first lines that it is not an act of UNICAM or ERDIS. They contain fictional codes
(e.g. `TRIAGE-BORSE-7`) used by the ACL leakage tests. No public document is synthetic. Sources:
`data/unibridge_synthetic/`.

## 5. Statistics and quality

From `corpus_stats.json`:

- 2,330 passages, mean 659.1 characters; 67.7 % of passages have a section (article or FAQ question).
- Largest documents: ERDIS call (426 passages), English call (423), Manifesto degli studi (169).
- Non-prose passages in the real documents (long passages with almost no function words: tables,
  lists): 27 of 2,305 (1.2 %), same heuristic as P14.

Known quality limits:
- ERDIS FAQ PDFs put questions in bold but on the same text line as the answer; the parser cannot split
  them, so FAQ passages carry a page number but no question title.
- The ERDIS call has a table of contents whose lines also look like article headings; they produce a few
  short passages labelled with the article title.
- Tables (credit requirements per year, amounts) are flattened into text in reading order.
- Some UNICAM regulations are older than the current academic year (career regulation 2022,
  contribution regulation 2019): they are the versions linked from the current UNICAM pages.

## 6. Privacy

- The real documents are public institutional texts. They contain names of officials (e.g. heads of
  procedure, contact persons) published by the institutions themselves; they are kept as published.
- No student data is in the corpus. The scholarship guide (`src/p14_search/procedure/`) receives the
  student's credits, ISEE and year only in the request, checks them with deterministic code, does not store
  them and never sends them to the LLM (rule 5 of the project).
- Logs store the query text, a pseudonym of the API principal and result ids (as in P14).
