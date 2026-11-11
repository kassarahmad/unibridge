// Builds deliverables/UniBridge_Presentation_Ahmad_Kassar.pptx, the PowerPoint twin of UniBridge_Presentation.html
// (same sections and design). Every number is read from eval/results/unibridge/*.json.
// Usage (from this folder): npm install && node build_presentation.js [path/to/apply_theme.js]

const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..", "..");
const RES = path.join(ROOT, "eval", "results", "unibridge");
const read = (name) => JSON.parse(fs.readFileSync(path.join(RES, name), "utf-8"));
const ev = read("eval_latest.json");
const tr = read("translation_latest.json");
const ans = read("answers_latest.json");
const ml = read("multilingual_latest.json");
const proc = read("procedure_eval.json");
const cost = read("llm_cost.json");
const corpus = read("corpus_stats.json");
// English and Arabic are evaluated on the main test split, the other languages on the multilingual one
const N_LANGS = new Set([...ml.languages, "en", "ar"]).size;
const OUT = path.join(ROOT, "deliverables", "UniBridge_Presentation_Ahmad_Kassar.pptx");
const IMG = path.join(__dirname, "img");
const f2 = (x) => Number(x).toFixed(2);
const pct = (x, d = 0) => `${(Number(x) * 100).toFixed(d)}%`;

const THEME = {
  name: "UniBridge",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1D2230", lt1: "FFFFFF", dk2: "1D2230", lt2: "FBFBFD",
    accent1: "8E1B33", accent2: "34507A", accent3: "A8720C", accent4: "B4BCCB", accent5: "5A6274", accent6: "D9DCE5",
    hlink: "34507A", folHlink: "8E1B33",
  },
};
const K = { ink: "1D2230", muted: "5A6274", line: "D9DCE5", paper: "FBFBFD", accent: "8E1B33", slate: "34507A", slateSoft: "E6ECF5",
  amber: "A8720C", amberSoft: "FBF1DC", white: "FFFFFF", barA: "B4BCCB" };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
pres.author = "Ahmad Kassar";
pres.title = "UniBridge";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "SHEET",
  background: { color: K.paper },
  objects: [
    { line: { x: 1.25, y: 0, w: 0, h: 7.5, line: { color: K.line, width: 0.75 } } },
    { placeholder: { options: { name: "title", type: "title", x: 1.65, y: 0.75, w: 9.0, h: 0.75, fontFace: "Calibri", fontSize: 32, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 12.3, y: 7.05, w: 0.6, h: 0.3, fontSize: 9, color: "5A6274", align: "right" },
});

let count = 0;
function text(s, t, o) { s.addText(t, { isTextBox: true, margin: 0, valign: "top", ...o }); }
function box(s, x, y, w, h, fill, name, line) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: line || fill, width: 0.75 }, objectName: name });
}
function sheet(section, no, seconds, kicker, title, sub) {
  const s = pres.addSlide({ masterName: "SHEET", sectionTitle: section });
  count += 1;
  text(s, no, { x: 0.15, y: 0.45, w: 0.95, h: 0.6, fontSize: 30, color: K.accent, align: "center", objectName: "section number" });
  text(s, section.toUpperCase(), { x: -2.4, y: 3.5, w: 6.0, h: 0.35, fontSize: 10, bold: true, color: K.muted, align: "center", charSpacing: 4, rotate: 270, objectName: "section name" });
  text(s, typeof seconds === "number" ? `${seconds} sec` : seconds, { x: 0.15, y: 6.95, w: 0.95, h: 0.3, fontSize: 9, color: K.muted, align: "center", fontFace: "Consolas", objectName: "time" });
  if (kicker) text(s, kicker.toUpperCase(), { x: 1.65, y: 0.42, w: 9, h: 0.3, fontSize: 11, bold: true, color: K.slate, charSpacing: 3, objectName: "kicker" });
  if (title) s.addText(title, { placeholder: "title" });
  if (sub) text(s, sub, { x: 1.65, y: 1.5, w: 10.5, h: 0.4, fontSize: 15, color: K.muted, objectName: "subtitle" });
  return s;
}
function card(s, x, y, w, h, label, head, body, style = "card") {
  const fills = { card: [K.white, K.line, K.accent, K.ink, K.muted], soft: [K.slateSoft, K.slateSoft, K.slate, K.ink, K.muted],
    amber: [K.amberSoft, K.amberSoft, K.amber, K.ink, K.ink], ink: [K.ink, K.ink, "C9CCD6", K.white, "E6E8EE"], accent: [K.accent, K.accent, "F3D6DC", K.white, "F6E7EA"] };
  const [fill, line, cl, ch, cb] = fills[style];
  box(s, x, y, w, h, fill, `card ${label || ""}`, line);
  const runs = [];
  if (label) runs.push({ text: label.toUpperCase(), options: { fontSize: 10, color: cl, fontFace: "Consolas", breakLine: true } });
  if (head) runs.push({ text: head, options: { fontSize: 18, bold: true, color: ch, breakLine: true, paraSpaceBefore: 4 } });
  if (body) runs.push({ text: body, options: { fontSize: 13, color: cb, paraSpaceBefore: 4 } });
  if (runs.length) text(s, runs, { x: x + 0.2, y: y + 0.18, w: w - 0.4, h: h - 0.3 });
}
function rule(s, x, y, w, label, body) {
  s.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color: K.ink, width: 0.75 } });
  text(s, [{ text: label, options: { fontSize: 10, color: K.accent, fontFace: "Consolas", breakLine: true } }, { text: body, options: { fontSize: 13, color: K.muted, paraSpaceBefore: 4 } }],
    { x, y: y + 0.1, w, h: 0.9 });
}
function chart(s, data, o) {
  s.addChart(pres.charts.BAR, data, {
    barDir: "col", barGapWidthPct: 55, catAxisLabelColor: K.muted, valAxisLabelColor: K.muted, catAxisLabelFontFace: "+mn-lt",
    valAxisLabelFontFace: "+mn-lt", catAxisLabelFontSize: 11, valAxisLabelFontSize: 10, dataLabelFontFace: "+mn-lt", dataLabelFontSize: 9,
    dataLabelColor: K.ink, valGridLine: { color: "E3E5EC", size: 0.5 }, catGridLine: { style: "none" }, showValue: true, dataLabelFormatCode: "0.00",
    legendFontFace: "+mn-lt", legendFontSize: 11, legendColor: K.ink, showLegend: true, legendPos: "t", valAxisMinVal: 0, valAxisMaxVal: 0.8,
    showTitle: true, titleFontFace: "+mn-lt", titleFontSize: 12, titleColor: K.ink, ...o,
  });
}

// 1 · Title ------------------------------------------------------------------------------
pres.addSection({ title: "Title" });
{
  const s = sheet("Title", "01", 20);
  s.addImage({ path: path.join(ROOT, "docs", "images", "unicam_logo.png"), x: 1.65, y: 1.3, w: 0.6, h: 0.72, altText: "University of Camerino logo" });
  text(s, "UNIVERSITY OF CAMERINO · FINAL PROJECT", { x: 2.4, y: 1.55, w: 6, h: 0.3, fontSize: 11, bold: true, color: K.slate, charSpacing: 3 });
  text(s, [{ text: "Uni", options: { color: K.ink } }, { text: "Bridge", options: { color: K.accent } }], { x: 1.6, y: 2.2, w: 6.5, h: 1.3, fontSize: 72, bold: true });
  text(s, "A multilingual assistant that answers international students from official Italian documents, in their own language, with the Italian source of every sentence.",
    { x: 1.65, y: 3.6, w: 6.2, h: 1.2, fontSize: 18, color: K.ink });
  s.addShape(pres.shapes.LINE, { x: 1.65, y: 5.05, w: 6.2, h: 0, line: { color: K.ink, width: 0.75 } });
  [["COURSE", "Complex Systems Design"], ["AUTHOR", "Ahmad Kassar"], ["SUPERVISOR", "Prof. Flavio Corradini"]].forEach(([l, v], i) => {
    text(s, [{ text: l, options: { fontSize: 9, color: K.muted, fontFace: "Consolas", breakLine: true } }, { text: v, options: { fontSize: 14, color: K.ink } }],
      { x: 1.65 + i * 2.15, y: 5.2, w: 2.1, h: 0.7 });
  });
  card(s, 8.4, 1.55, 4.3, 1.15, "Student asks · Arabic", null, null);
  text(s, "متى آخر موعد لتقديم طلب المنحة الدراسية؟", { x: 8.6, y: 2.0, w: 3.9, h: 0.5, fontSize: 17, color: K.ink, align: "right", rtlMode: true, lang: "ar-SA" });
  card(s, 8.4, 2.85, 4.3, 1.75, "UniBridge answers · Arabic", null, null);
  text(s, "الموعد النهائي هو 28 أغسطس 2026. [1]", { x: 8.6, y: 3.3, w: 3.9, h: 0.5, fontSize: 17, color: K.ink, align: "right", rtlMode: true, lang: "ar-SA" });
  text(s, "[1] ERDIS call 2026/2027, Art. 10 · «entro il 28 agosto 2026, pena l'esclusione dal concorso»", { x: 8.6, y: 3.85, w: 3.9, h: 0.6, fontSize: 11, color: K.muted });
  box(s, 8.4, 4.85, 1.75, 0.42, K.paper, "languages stamp", K.accent);
  text(s, `${N_LANGS} LANGUAGES`, { x: 8.4, y: 4.85, w: 1.75, h: 0.42, fontSize: 11, color: K.accent, fontFace: "Consolas", align: "center", valign: "middle" });
  text(s, "it en ar fr es pt de ro sq uk ru tr fa ur hi bn zh", { x: 10.3, y: 4.9, w: 2.4, h: 0.4, fontSize: 9, color: K.muted, fontFace: "Consolas" });
  s.addNotes("UniBridge helps international students in Camerino with the rules they must follow: fees, career, admission and the regional scholarship. A student asks in their own language; the answer comes back in the same language, and each sentence points to the Italian passage it comes from. Here a question in Arabic and the deadline found in Article 10 of the call.");
}

// 2 · Objectives -------------------------------------------------------------------------
pres.addSection({ title: "Objectives" });
{
  const s = sheet("Objectives", "02", 55, "Purpose and research question", "Objectives and research question",
    "Can an assistant help international students with Italian rules without inventing anything?");
  card(s, 1.65, 2.05, 3.45, 2.6, "Problem", null, "Fees, career rules, admission and the regional scholarship are described in Italian documents. Missing a deadline excludes a student from the scholarship (Art. 10 of the call). General chatbots do not show their source and can invent dates.");
  card(s, 5.25, 2.05, 7.45, 1.2, "Research question", null, "How well can search over official documents, a translation step and a verified language-model answer serve questions asked in many languages, and when must the system say \"I don't know\"?", "ink");
  card(s, 5.25, 3.4, 3.65, 1.25, "O1", "Cited answers", "Each sentence ends with its passage; the Italian original next to it.");
  card(s, 9.05, 3.4, 3.65, 1.25, "O2", "Every language", "Detect it, search across languages, answer in it.");
  card(s, 1.65, 4.8, 3.45, 1.25, "O3", "Scholarship guide", "Eligibility, checklist and calendar from fixed rules.");
  card(s, 5.25, 4.8, 3.65, 1.25, "O4", "Knowing the limits", "Decline out-of-scope questions; e-mail to the right office.");
  card(s, 9.05, 4.8, 3.65, 1.25, "Primary metrics", null, "nDCG@10 · recall@10 · citation precision · answer language", "soft");
  card(s, 1.65, 6.2, 11.05, 0.7, "Diagnostic metrics", null, "false \"I don't know\" · permission leaks · cost per answer · latency", "amber");
  s.addNotes("The problem: rules in Italian, students who read other languages, and chatbots that do not cite. The research question asks how far search, translation and a verified answer can go, and when the system must stop and say 'I don't know'. Four objectives, each with the metric that measures it.");
}

// 3 · Work plan --------------------------------------------------------------------------
pres.addSection({ title: "Work plan" });
{
  const s = sheet("Work plan", "03", 60, "How the work was organised", "Three phases, one author", "Each phase ends with a check that the next one depends on");
  box(s, 1.65, 2.05, 11.05, 3.45, K.white, "gantt", K.line);
  const x0 = 4.6, colW = 2.6;
  ["PHASE 1", "PHASE 2", "PHASE 3"].forEach((h, i) => text(s, h, { x: x0 + i * colW, y: 2.2, w: colW, h: 0.3, fontSize: 10, color: K.muted, fontFace: "Consolas" }));
  s.addShape(pres.shapes.LINE, { x: 1.85, y: 2.55, w: 10.65, h: 0, line: { color: K.ink, width: 0.75 } });
  const rows = [
    ["Search and evaluation method", "hybrid search, permissions, frozen test sets", 0, 1.7, K.slate],
    ["Documents and questions", "official sources, FAQ questions, translations", 1, 1.0, K.accent],
    ["Search by language", "keyword, dense, hybrid; the Arabic test", 1.2, 0.8, K.accent],
    ["Answers and verification", "model answer, verifier, e-mail draft", 2, 0.75, K.ink],
    ["Scholarship guide and languages", `fixed rules, checklist, ${N_LANGS} languages`, 2.15, 0.85, K.ink],
    ["Demo and documents", "screenshots, report, presentation", 2, 1.0, K.amber],
  ];
  rows.forEach(([h, b, start, len, c], i) => {
    const y = 2.68 + i * 0.46;
    text(s, [{ text: h, options: { fontSize: 12, bold: true, color: K.ink, breakLine: true } }, { text: b, options: { fontSize: 9, color: K.muted } }], { x: 1.85, y, w: 2.7, h: 0.44 });
    box(s, x0 + start * colW, y + 0.12, len * colW, 0.13, c, `bar ${i + 1}`);
  });
  rule(s, 1.65, 5.75, 3.5, "Gate 1", "Search tested (permissions, contracts); evaluation method reproducible.");
  rule(s, 5.42, 5.75, 3.5, "Gate 2", "Test questions frozen with a SHA-256 hash before any tuning.");
  rule(s, 9.2, 5.75, 3.5, "Gate 3", "All tests green; every number checked against the result files.");
  s.addNotes("I organised the work in three phases and did it alone. Phase one: the search and the evaluation method. Phase two: the documents and the questions, and the search measured by language. Phase three: the answers with verification, the scholarship guide, the extension to seventeen languages, and the demo and documents. Each phase ends with a check the next one relies on.");
}
{
  const s = sheet("Work plan", "03", 60, "How the work was organised", "What each phase delivered");
  card(s, 1.65, 1.75, 3.55, 4.6, "Phase 1", "Foundation", "Safe parsing of PDF, Word and HTML; passages with stable ids; keyword and multilingual search with rank fusion; permissions applied inside the search; citations; a REST API with frozen contracts; the evaluation method.");
  card(s, 5.4, 1.75, 3.55, 4.6, "Phase 2", "Data and first findings", `${corpus.source.ub.documents} official documents with licence and hash; roles for visitors, students and offices; real questions from official FAQ pages; English and Arabic versions; search measured by language. Finding: keyword search fails on Arabic.`, "soft");
  card(s, 9.15, 1.75, 3.55, 4.6, "Phase 3", "The assistant", `Answers with a verifier and an extractive fallback; "I don't know" with an office e-mail; the scholarship guide; ${N_LANGS} languages; demo, report and presentation. Shown on Friday.`, "accent");
  s.addNotes("What each phase produced. The foundation was reused unchanged; the data phase gave the first finding about Arabic; the last phase built the assistant itself.");
}

// 4 · Architecture -----------------------------------------------------------------------
pres.addSection({ title: "Architecture" });
{
  const s = sheet("Architecture", "04", 120, "Architecture", "System flow and software architecture", "One service · four components · an optional language model");
  [["01", "Documents", `Official sources parsed into passages with document, section and page. ${corpus.totals.passages.toLocaleString("en-US")} passages.`, "card"],
   ["02", "Search", "Keyword + multilingual embeddings, rank fusion; the user's permissions applied inside the search.", "card"],
   ["03", "Answer", "The model answers only from the numbered passages; a verifier drops unsupported sentences.", "soft"],
   ["04", "Student or office", "Answer with Italian sources, or \"I don't know\" and an Italian e-mail draft. Nothing is sent automatically.", "card"]].forEach(([l, h, b, st], i) => {
    card(s, 1.65 + i * 2.8, 2.05, 2.6, 2.4, l, h, b, st);
  });
  rule(s, 1.65, 4.85, 3.5, "Without a key", "No model configured: extractive answers, Italian sentences from the documents.");
  rule(s, 5.42, 4.85, 3.5, "Passages are data", "Wrapped in tags the text cannot close; the prompt says they are never instructions.");
  rule(s, 9.2, 4.85, 3.5, "Cost control", "Temperature 0, cached responses, every call logged, hard stop at 5 USD.");
  s.addNotes("Four steps: documents become passages, the search finds them with the user's permissions, the model answers only from them and a verifier checks every sentence, and the student gets the answer or a draft for the office. Without a key the system still works with extractive answers.");
}
{
  const s = sheet("Architecture", "04", 120, "Architecture", "Components and contracts");
  card(s, 1.65, 1.75, 11.05, 0.8, "Presentation", null, "Web demo · chat with roles and language selector · scholarship guide · e-mail draft download", "ink");
  card(s, 1.65, 2.7, 11.05, 0.8, "Service API", null, "POST /v1/answer · POST /v1/handoff · POST /v1/procedure/scholarship · POST /v1/search · GET /v1/health");
  [["Answer", "language detection, translation, answer, verifier, extractive fallback"], ["Handoff", "office rule table, Italian e-mail"],
   ["Scholarship guide", "fixed rules, checklist, calendar; no language model"], ["Language model · optional", "OpenAI or Anthropic, cache, usage log, budget"]].forEach(([h, b], i) => {
    card(s, 1.65 + i * 2.8, 3.65, 2.6, 1.3, h, null, b, "soft");
  });
  card(s, 1.65, 5.1, 5.45, 0.85, "Search", null, "keyword index + multilingual embeddings, rank fusion, permissions, citations");
  card(s, 7.25, 5.1, 5.45, 0.85, "Storage", null, "SQLite (documents, passages, logs) · Qdrant (vectors) · Docker");
  text(s, "Contracts frozen as OpenAPI and JSON Schema; every response names the index and model versions. Roles: visitor (public) · student (+ student-only notices) · office staff (+ own internal notes).",
    { x: 1.65, y: 6.2, w: 11.05, h: 0.6, fontSize: 12, color: K.muted });
  s.addNotes("The components: a web demo on top of one REST API; three services behind it; an optional language model with cache and budget; the search with permissions; and two stores. The contracts are frozen, so other clients can rely on them.");
}

// 5 · Student journey --------------------------------------------------------------------
pres.addSection({ title: "Student journey" });
{
  const s = sheet("Student journey", "05", 60, "From question to answer", "A question and its constraints", "One question follows the same route in every language");
  [["01", "Language", `Detected offline among ${N_LANGS} languages.`, "card"], ["02", "Search as written", "Passages that share meaning or words with the question.", "card"],
   ["03", "Translate and fuse", "Italian translation, second search, rankings fused.", "soft"], ["04", "Answer and verify", "One claim per sentence, each with [Pn]; unsupported sentences removed.", "soft"],
   ["05", "Show", "Answer in the student's language next to the Italian original.", "card"]].forEach(([l, h, b, st], i) => {
    card(s, 1.65 + i * 2.23, 2.05, 2.1, 2.3, l, h, b, st);
  });
  rule(s, 1.65, 4.75, 3.5, "Weak evidence", "No passage passes the threshold: \"I don't know\" in the student's language + e-mail draft.");
  rule(s, 5.42, 4.75, 3.5, "Out of scope", "A question about football or a gym: \"I don't know\", no e-mail.");
  rule(s, 9.2, 4.75, 3.5, "Permissions", "A visitor never gets an answer built from a student-only notice.");
  s.addNotes("Every question follows the same route. The translation step matters most for languages far from Italian. Three constraints: weak evidence leads to 'I don't know' and an e-mail; out-of-scope questions get 'I don't know' without e-mail; and permissions are never crossed.");
}
{
  const s = sheet("Student journey", "05", 60, "From question to answer", "In the demo");
  s.addImage({ path: path.join(IMG, "ub_08_answer_fr.png"), x: 1.65, y: 1.75, w: 5.4, h: 5.4 * 500 / 1110, altText: "French question answered in French" });
  s.addImage({ path: path.join(IMG, "ub_04_role_visitor.png"), x: 7.3, y: 1.75, w: 5.4, h: 5.4 * 860 / 1140, altText: "I don't know with an Italian e-mail draft" });
  text(s, "Left: a French question, answered in French with the Italian source. Right: a visitor asks about a student-only programme and gets \"I don't know\" with a draft for the international office.",
    { x: 1.65, y: 4.5, w: 5.4, h: 1.2, fontSize: 13, color: K.muted });
  s.addNotes("Two moments from the demo. A French question answered in French, with the Italian passage shown next to it. And a visitor asking about the buddy programme, which is described only in a student-only notice: the visitor gets 'I don't know' and a draft e-mail.");
}
{
  const s = sheet("Student journey", "05", 60, "From question to answer", "Scholarship guide");
  s.addImage({ path: path.join(IMG, "ub_07_scholarship_guide.png"), x: 1.65, y: 1.75, w: 5.2, h: 5.2 * 1035 / 1110, altText: "Scholarship guide screenshot" });
  rule(s, 7.2, 1.85, 5.5, "No language model", "Credits by year, ISEE and ISPE limits, previous degree, residence permit and deadlines are checked by code, each rule with its article.");
  rule(s, 7.2, 3.05, 5.5, "Where you are", "The steps done and the next ones, from the student's facts and the date.");
  rule(s, 7.2, 4.25, 5.5, `${proc.scenarios_fully_correct} of ${proc.n_scenarios} test scenarios correct`, "Fictional students with the checklist written from the call.");
  rule(s, 7.2, 5.45, 5.5, "Nothing stored", "Credits and ISEE stay in the request; never logged, never sent to the language model.");
  s.addNotes("The guide is the part with no language model: eligibility has consequences, so the rules are code, each with its article of the call. Fifteen fictional students with their expected checklist are all correct.");
}

// 6 · Data & evaluation ------------------------------------------------------------------
pres.addSection({ title: "Data & evaluation" });
{
  const s = sheet("Data & evaluation", "06", 150, "Evidence", "Data sources and protocol");
  const head = ["DATA SOURCE", "INTENDED USE", "REMAINING GAP"].map((t) => ({ text: t, options: { fontSize: 10, color: K.muted, fontFace: "Consolas" } }));
  const rows = [
    [`${corpus.source.ub.documents} official documents`, `Corpus: ${corpus.totals.passages.toLocaleString("en-US")} passages with section, page and offsets`, "One university and one call; a snapshot"],
    [`Official FAQ questions (${ev.n_by_lang.it} Italian)`, "Questions with known answers: the FAQ answer and the article it cites", "Few questions per topic"],
    [`Translations: ${ev.n_by_lang.en} English, ${ev.n_by_lang.ar} Arabic, ${ml.n_new_language_questions} in 14 more languages`, "The same questions in every language", "Machine translations; native review pending"],
    [`${corpus.source.ubsyn.documents} synthetic notes (labelled)`, "Test the roles: student-only and office-only content", "Not real notices"],
  ].map((r) => r.map((t, i) => ({ text: t, options: { fontSize: 13, bold: i === 0, color: K.ink } })));
  s.addTable([head, ...rows], { x: 1.65, y: 1.8, w: 11.05, colW: [3.7, 4.35, 3.0], border: { type: "solid", color: K.line, pt: 0.75 }, rowH: 0.62, valign: "middle", fill: { color: K.white } });
  card(s, 1.65, 5.2, 11.05, 0.8, "Evaluation protocol", null, "Tune on one split · freeze the test split with a SHA-256 hash · measure once · compare systems with paired randomization tests.", "soft");
  s.addNotes("The corpus is official documents; the Italian test questions come from official FAQ pages, so the answer is known. The other languages are machine translations and still need native speakers. The test sets were frozen before any tuning.");
}
{
  const s = sheet("Data & evaluation", "06", 150, "Evidence", "Keyword search fails on Arabic");
  const langs = [["it", "Italian"], ["en", "English"], ["ar", "Arabic"]];
  chart(s, [["B0", "Keyword"], ["S1", "Dense"], ["S2", "Hybrid"]].map(([k, name]) => ({ name, labels: langs.map((l) => l[1]), values: langs.map(([l]) => ev.by_lang[l][k]["ndcg@10"]) })),
    { x: 1.65, y: 1.7, w: 7.0, h: 4.9, chartColors: [K.barA, K.slate, K.accent], title: "nDCG@10 by question language" });
  const h = ev.hypothesis_bm25_arabic;
  card(s, 9.0, 1.8, 3.7, 2.2, null, null, null, "amber");
  text(s, [{ text: pct(h.B0_no_relevant_in_top10_share_ar), options: { fontSize: 44, color: K.amber, breakLine: true } },
    { text: `of the ${h.n_arabic_in_scope_test} Arabic test questions: keyword search finds no relevant passage in the top 10.`, options: { fontSize: 13, color: K.ink } }],
  { x: 9.2, y: 1.95, w: 3.3, h: 1.95 });
  rule(s, 9.0, 4.35, 3.7, "Permissions", `0 leaks in ${ev.acl_leakage.passages_checked.toLocaleString("en-US")} checked passages.`);
  s.addNotes("The first finding. For every Arabic test question, keyword search finds nothing relevant: the languages share no words. Multilingual embeddings recover part of it, but Arabic stays far below Italian.");
}
{
  const s = sheet("Data & evaluation", "06", 150, "Evidence", "Translate the question, then fuse");
  chart(s, [["S2", "As written"], ["S3", "Translated only"], ["S3f", "Fused"]].map(([k, name]) => ({ name, labels: ["English", "Arabic"], values: ["en", "ar"].map((l) => tr.by_lang[l][k]["ndcg@10"]) })),
    { x: 1.65, y: 1.7, w: 7.0, h: 4.9, chartColors: [K.barA, K.slate, K.accent], title: "nDCG@10 · English and Arabic test questions" });
  card(s, 9.0, 1.8, 3.7, 1.9, `All ${tr.n_test_queries} questions`, null, null, "ink");
  text(s, [{ text: `${f2(tr.overall.S2["ndcg@10"])} → ${f2(tr.overall.S3f["ndcg@10"])}`, options: { fontSize: 34, color: K.white, breakLine: true } },
    { text: `nDCG@10 with fusion · p = ${tr.randomization_tests["S3f_vs_S2_ndcg@10_all"].p_value}`, options: { fontSize: 12, color: "E6E8EE" } }],
  { x: 9.2, y: 2.3, w: 3.3, h: 1.3 });
  rule(s, 9.0, 4.0, 3.7, "English", "Translation alone is worse: English questions find the English version of the call, which the ground truth rarely marks. Measured, not yet confirmed.");
  s.addNotes("The model translates the question into Italian before the search. For Arabic this roughly doubles the score. For English translation alone is worse, probably because of the English version of the call. Fusing both rankings is the robust choice and is significant overall.");
}
{
  const s = sheet("Data & evaluation", "06", 150, "Evidence", `${N_LANGS} languages`);
  const langs = ml.languages;
  chart(s, [["S2", "As written"], ["S3f", "Fused with the Italian translation"]].map(([k, name]) => ({ name, labels: langs, values: langs.map((l) => ml.by_lang[l].retrieval[k]["ndcg@10"]) })),
    { x: 1.65, y: 1.7, w: 7.4, h: 4.9, chartColors: [K.barA, K.accent], title: "nDCG@10 by language · same questions · it = Italian originals", showValue: false, barGapWidthPct: 40 });
  const nl = ml.new_languages;
  [[pct(nl.detection_accuracy, 1), "questions whose language is detected correctly"], [pct(nl.answer_language_correct, 1), "answers written in the language of the question"]].forEach(([big, lab], i) => {
    card(s, 9.3, 1.8 + i * 1.45, 3.4, 1.3, null, null, null);
    text(s, [{ text: big, options: { fontSize: 30, color: K.slate, breakLine: true } }, { text: lab, options: { fontSize: 12, color: K.muted } }], { x: 9.5, y: 1.9 + i * 1.45, w: 3.0, h: 1.1 });
  });
  card(s, 9.3, 4.75, 3.4, 1.5, "Without fusion", null, `"Insufficient evidence" for ${pct(nl.retrieval.S2.false_abstention_rate)} of in-scope questions; ${pct(nl.retrieval.S3f.false_abstention_rate)} with fusion (p = ${ml.randomization_tests["S3f_vs_S2_ndcg@10_new_languages"].p_value}).`, "amber");
  s.addNotes(`After the first evaluation I extended UniBridge to ${N_LANGS} languages and evaluated the same questions, translated and frozen, without any tuning. Fusion improves the ranking in every one of the fourteen added languages; without it the system would wrongly say 'insufficient evidence' for most of their questions.`);
}
{
  const s = sheet("Data & evaluation", "06", 150, "Evidence", "Answers: extractive, model, model + verifier");
  const cf = ans.configs;
  const cols = [["extractive", "Extractive (no model)"], ["llm", "Model, no verifier"], ["llm_verified", "Model + verifier"]];
  const rows = [
    ["Answered (not \"I don't know\")", (c) => `${c.answered} of ${c.n}`], ["Citation precision", (c) => f2(c.citation_precision)],
    ["Sentences without a valid citation", (c) => pct(c.uncited_sentence_rate)], ["Answer in the language of the question", (c) => pct(c.answer_language_correct)],
    ["\"I don't know\" on out-of-scope questions", (c) => pct(c.idk_correct_oos)], ["Cost per answer (USD)", (c) => (c.cost_usd_per_answer ? c.cost_usd_per_answer.toFixed(5) : "0")],
    ["Latency, median (ms)", (c) => Math.round(c.latency_ms_p50).toLocaleString("en-US")],
  ];
  const head = [{ text: `${ans.n_test_queries} TEST QUESTIONS`, options: { fontSize: 10, color: K.muted, fontFace: "Consolas" } },
    ...cols.map(([, h]) => ({ text: h.toUpperCase(), options: { fontSize: 10, color: K.muted, fontFace: "Consolas", align: "center" } }))];
  const body = rows.map(([l, fn]) => [{ text: l, options: { bold: true, color: K.ink } },
    ...cols.map(([k]) => ({ text: fn(cf[k]), options: { align: "center", color: k === "llm_verified" ? K.accent : K.ink, bold: k === "llm_verified" } }))]);
  s.addTable([head, ...body], { x: 1.65, y: 1.75, w: 11.05, colW: [4.4, 2.2, 2.2, 2.25], fontSize: 14, rowH: 0.5, border: { type: "solid", color: K.line, pt: 0.75 }, valign: "middle", fill: { color: K.white } });
  text(s, `The verifier's check uses the same model, so it is not an independent measure of faithfulness; a human review of 30 answers is the independent check (pending). In the 14 added languages citation precision is ${f2(ml.new_languages.citation_precision)}.`,
    { x: 1.65, y: 6.0, w: 11.05, h: 0.7, fontSize: 12, color: K.muted });
  s.addNotes("With the model, citation precision roughly doubles compared with sentences copied from the documents, and many more questions get an answer. The verifier removes every sentence without a valid citation, at the price of a few more 'I don't know' and a longer wait. Every out-of-scope question gets 'I don't know'. The cost is a fraction of a cent per answer.");
}

// 7 · Questions --------------------------------------------------------------------------
pres.addSection({ title: "Questions" });
{
  const s = sheet("Questions", "07", "30 sec + Q&A", "Outcome", "What is done and what comes next");
  rule(s, 1.65, 1.8, 2.3, "01 · Assistant", `Answers in ${N_LANGS} languages, each sentence with its Italian source.`);
  rule(s, 4.15, 1.8, 2.3, "02 · Guide", "Eligibility, checklist and calendar from fixed rules.");
  rule(s, 6.65, 1.8, 2.3, "03 · Evidence", "Frozen test sets, results per language, reproducible numbers.");
  card(s, 1.65, 3.0, 7.3, 1.35, "Limits", null, "Non-Italian questions are machine translations; the ground truth misses some relevant passages; the verifier sometimes removes too much; one university, one call.", "amber");
  card(s, 1.65, 4.5, 7.3, 1.45, "Next steps", null, "Questions written by real international students and checked by native speakers; human review of answers; more documents after licence checks; per-language \"I don't know\" thresholds.");
  text(s, `Use of AI tools: a coding assistant for code and documents; a language model for translations and answers (${cost.estimated_cost_usd.toFixed(2)} USD for the whole project). Declared in the report.`,
    { x: 1.65, y: 6.15, w: 7.3, h: 0.6, fontSize: 11, color: K.muted });
  card(s, 9.25, 1.8, 3.45, 5.0, "Discussion", null, null, "accent");
  text(s, [{ text: "Questions?", options: { fontSize: 40, bold: true, color: K.white, breakLine: true } }, { text: "Demo, report and code ready to show on Friday.", options: { fontSize: 14, color: "F6E7EA" } }],
    { x: 9.5, y: 2.5, w: 3.0, h: 2.0 });
  text(s, "Ahmad Kassar · Complex Systems Design", { x: 9.5, y: 6.25, w: 3.0, h: 0.3, fontSize: 10, color: "F6E7EA", fontFace: "Consolas" });
  s.addNotes("What is done: the assistant, the guide and the evidence. The main limit is the data: the non-Italian questions are machine translations. Next: real questions from international students, checked by native speakers. Thank you, I am happy to show the demo.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  if (process.argv[2]) {
    const { applyTheme } = require(process.argv[2]);
    await applyTheme(OUT, THEME);
  }
  console.log(`wrote ${path.relative(ROOT, OUT)} (${count} slides)`);
})();
