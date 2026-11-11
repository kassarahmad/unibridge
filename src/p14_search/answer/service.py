"""Answers in the student's language with a citation for every sentence.

Pipeline: language -> retrieval (S2 hybrid; for en/ar queries also an Italian LLM translation of the query,
fused with RRF) -> answer step -> verifier -> response with the Italian original of every cited passage.
Answer modes:
- extractive: no LLM; sentences copied from the passages (Italian), each with its passage.
- llm: generated answer, citations parsed but NOT verified (evaluation baseline only).
- llm_verified: generated answer; sentences without a valid citation are dropped; optionally the same LLM
  checks that each cited passage supports its sentence (yes/no). Nothing left -> "I don't know" + handoff.
If the LLM is not configured, fails or the budget is reached, the answer falls back to extractive.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from p14_search.answer import prompts
from p14_search.answer.language import EXTRACTIVE_NOTE, I_DONT_KNOW, detect
from p14_search.answer.llm import LLMClient, LLMError, LLMResult
from p14_search.answer.verifier import Claim, is_yes, parse_claims, verify_citations
from p14_search.config import Settings
from p14_search.handoff.service import HandoffService
from p14_search.indexing.store import dumps
from p14_search.models import (
    AnswerRequest,
    AnswerResponse,
    AnswerSentence,
    HandoffSource,
    LLMUsage,
    SourcePassage,
    VerificationReport,
)
from p14_search.retrieval.retrievers import rrf_fuse
from p14_search.retrieval.service import SearchService
from p14_search.retrieval.summary import _SENT_SPLIT, extractive_summary
from p14_search.security.principals import Principal

log = logging.getLogger("p14.answer")
SYSTEM = "S2"


@dataclass
class _Usage:
    results: list[LLMResult] = field(default_factory=list)

    def add(self, r: LLMResult) -> LLMResult:
        self.results.append(r)
        return r

    def report(self) -> LLMUsage | None:
        if not self.results:
            return None
        fresh = [r for r in self.results if not r.cached]
        costs = [r.cost_usd for r in fresh]
        return LLMUsage(
            provider=self.results[0].provider, model=self.results[0].model, calls=len(self.results),
            cached_calls=len(self.results) - len(fresh), input_tokens=sum(r.input_tokens for r in fresh),
            output_tokens=sum(r.output_tokens for r in fresh),
            cost_usd=None if any(c is None for c in costs) else round(sum(costs), 8),
        )


class AnswerService:
    def __init__(self, search: SearchService, llm: LLMClient | None, handoff: HandoffService, settings: Settings):
        self.search = search
        self.llm = llm
        self.handoff = handoff
        self.settings = settings

    # --- retrieval ---------------------------------------------------------------------------
    def retrieve(self, query: str, lang: str, principal: Principal, k: int, use_llm: bool, usage: _Usage):
        """(hits, insufficient_evidence, italian query or None)."""
        first = self.search.rank_all(query, principal, k, (SYSTEM,))[SYSTEM]
        italian = None
        if use_llm and lang != "it" and self.settings.answer_query_translation:
            try:
                italian = usage.add(self.llm.complete(prompts.TRANSLATE_SYSTEM, query, 200, "query_translation")).text.strip()
            except LLMError:
                italian = None
        if not italian:
            return first.hits, first.insufficient_evidence, None
        second = self.search.rank_all(italian, principal, k, (SYSTEM,))[SYSTEM]
        hits = rrf_fuse({"original": first.hits, "italian": second.hits}, k)
        return hits, first.insufficient_evidence and second.insufficient_evidence, italian

    # --- main --------------------------------------------------------------------------------
    def answer(self, req: AnswerRequest, principal: Principal, request_id: str) -> AnswerResponse:
        start = time.perf_counter()
        lang = req.language or detect(req.query)
        mode = req.mode if req.mode != "auto" else ("llm_verified" if self.llm else "extractive")
        if mode != "extractive" and self.llm is None:
            mode = "extractive"
        k = req.top_k or self.settings.answer_top_k
        usage = _Usage()
        hits, insufficient, italian = self.retrieve(req.query, lang, principal, k, mode != "extractive", usage)
        docs = self.search.hydrate(hits, principal)
        ordered = sorted((p for d in docs for p in d.passages), key=lambda p: p.evidence.rank)[:k]
        sources = [SourcePassage(passage_id=p.passage_id, alias=f"P{i + 1}", rank=i + 1, text=p.text, citation=p.citation)
                   for i, p in enumerate(ordered)]

        sentences: list[AnswerSentence] = []
        verification = None
        message = None
        if not sources or insufficient:
            pass
        elif mode == "extractive":
            sentences, message = self._extractive(req.query, italian, sources), EXTRACTIVE_NOTE[lang]
        else:
            try:
                sentences, verification = self._generate(req.query, lang, sources, mode == "llm_verified", usage)
            except LLMError as exc:
                log.warning("llm unavailable, extractive fallback", extra={"request_id": request_id, "error": str(exc)})
                mode = "extractive"
                sentences, message = self._extractive(req.query, italian, sources), EXTRACTIVE_NOTE[lang]

        idk = not sentences
        handoff = None
        if idk:
            message = I_DONT_KNOW[lang]
            if req.with_handoff:
                refs = [HandoffSource(passage_id=s.passage_id, title=s.citation.title, section=s.citation.section,
                                      page=s.citation.page, source_url=s.citation.source_url) for s in sources[:3]]
                top_office = docs[0].metadata.office if docs else None
                handoff = self.handoff.draft(req.query, lang, refs, request_id, top_office=top_office)
        response = AnswerResponse(
            request_id=request_id, query=req.query, language=lang, mode="insufficient_evidence" if idk else mode,
            answer_text=" ".join(s.text for s in sentences), sentences=sentences, sources=sources, insufficient_evidence=idk,
            message=message, handoff=handoff, verification=verification, llm=usage.report(), retrieval_system=SYSTEM,
            query_italian=italian, latency_ms=round((time.perf_counter() - start) * 1000, 1), versions=self.search.versions(),
        )
        self.search.store.log_query(
            request_id=request_id, principal_hash=principal.pseudonym, query=req.query, filters_json=None,
            system=f"answer:{response.mode}", versions_json=dumps(response.versions.model_dump()),
            results_json=dumps([[s.passage_id, s.rank] for s in sources]), insufficient_evidence=int(idk),
            latency_ms=response.latency_ms,
        )
        log.info("answer", extra={"request_id": request_id, "mode": response.mode, "lang": lang, "sentences": len(sentences),
                                  "llm_calls": len(usage.results), "latency_ms": response.latency_ms})
        return response

    # --- answer modes ------------------------------------------------------------------------
    def _extractive(self, query: str, italian: str | None, sources: list[SourcePassage]) -> list[AnswerSentence]:
        summary = extractive_summary(italian or query, [(s.passage_id, s.text) for s in sources])
        if summary:
            return [AnswerSentence(text=x.text, passage_ids=[x.passage_id]) for x in summary.sentences]
        # No term overlap (e.g. an Arabic query and no translation): first sentence of the two best passages.
        out = []
        for s in sources[:2]:
            first = next((x.strip() for x in _SENT_SPLIT.split(s.text) if len(x.strip()) >= 30), None)
            if first:
                out.append(AnswerSentence(text=first, passage_ids=[s.passage_id]))
        return out

    def _generate(self, query: str, lang: str, sources: list[SourcePassage], verify: bool, usage: _Usage):
        by_alias = {s.alias: s for s in sources}
        label = {s.alias: " - ".join(x for x in (s.citation.title, s.citation.section) if x) for s in sources}
        system, user = prompts.answer_prompt(query, lang, [(s.alias, label[s.alias], s.text) for s in sources])
        out = usage.add(self.llm.complete(system, user, self.settings.llm_max_output_tokens, "answer")).text.strip()
        if out.startswith(prompts.NO_ANSWER) or not out:
            report = VerificationReport(generated_sentences=0, dropped_uncited=0, dropped_invalid_citation=0,
                                        dropped_unsupported=0, support_checked=False)
            return [], report if verify else None

        def ids(c: Claim) -> list[str]:
            return [by_alias[a].passage_id for a in c.aliases if a in by_alias]

        if not verify:
            claims, uncited = parse_claims(out)
            sentences = [AnswerSentence(text=c.text, passage_ids=ids(c)) for c in claims]
            sentences += [AnswerSentence(text=u, passage_ids=[]) for u in uncited]
            return sentences, None
        v = verify_citations(out, set(by_alias))
        kept: list[AnswerSentence] = []
        unsupported = 0
        for c in v.kept:
            supported = None
            if self.settings.answer_verify_support:
                supported = all(self._supports(by_alias[a].text, c.text, usage) for a in c.aliases)
                if not supported:
                    unsupported += 1
                    continue
            kept.append(AnswerSentence(text=c.text, passage_ids=ids(c), supported=supported))
        report = VerificationReport(
            generated_sentences=len(v.kept) + len(v.dropped_invalid) + len(v.dropped_uncited),
            dropped_uncited=len(v.dropped_uncited), dropped_invalid_citation=len(v.dropped_invalid),
            dropped_unsupported=unsupported, support_checked=self.settings.answer_verify_support,
        )
        return kept, report

    def _supports(self, passage: str, statement: str, usage: _Usage) -> bool:
        system, user = prompts.support_prompt(passage, statement)
        return is_yes(usage.add(self.llm.complete(system, user, 3, "support_check")).text)
