"""Domain and API models. These Pydantic models are the source of the JSON Schemas in contracts/schemas/."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AccessLevel(str, Enum):
    public = "public"
    internal = "internal"
    restricted = "restricted"


ACCESS_ORDER = {AccessLevel.public: 0, AccessLevel.internal: 1, AccessLevel.restricted: 2}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Ingestion -------------------------------------------------------------------------------

class DocumentMetadata(_Strict):
    office: str = Field(..., min_length=1, max_length=40, description="Owning office, e.g. hr, it, legal.")
    type: str = Field(..., min_length=1, max_length=40, description="Document type, e.g. legislation, procedure, faq.")
    author: str | None = Field(None, max_length=200)
    date: str | None = Field(None, description="ISO date (YYYY-MM-DD) of the document.", pattern=r"^\d{4}-\d{2}-\d{2}$")
    project: str | None = Field(None, max_length=100)
    source_url: str | None = Field(None, max_length=2000, description="Where the original was obtained.")


class FileContent(_Strict):
    filename: str = Field(..., min_length=1, max_length=255)
    media_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/html",
        "text/plain",
    ]
    content_base64: str = Field(..., description="File bytes, base64-encoded.")


class IngestDocument(_Strict):
    """Inbound format shared by every producer (admin upload, P11, P15, P25)."""

    source_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$", description="Source/repository identifier.")
    external_id: str = Field(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", description="Id of the document in its source.")
    title: str = Field(..., min_length=1, max_length=500)
    file: FileContent
    metadata: DocumentMetadata
    access_level: AccessLevel
    owner: str = Field(..., min_length=1, max_length=200, description="Accountable owner (a role, not a person).")
    source_piece: str = Field("P14", pattern=r"^P\d{2}$", description="Puzzle piece that produced the document.")
    validated_by: str | None = Field(None, max_length=200, description="Expert validation (P25 knowledge cards).")
    synthetic: bool = False
    llm_generated: bool = False


class IngestResult(BaseModel):
    document_id: str
    document_version: str
    status: Literal["pending", "approved"]
    passages: int
    unchanged: bool = Field(False, description="True when the same version was already ingested.")


# --- Search ----------------------------------------------------------------------------------

class SearchFilters(_Strict):
    office: list[str] | None = None
    type: list[str] | None = None
    source_id: list[str] | None = None


class SearchRequest(_Strict):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(10, ge=1, le=50, description="Number of passages to return.")
    filters: SearchFilters | None = None
    with_summary: bool = True


class Citation(BaseModel):
    document_id: str
    document_version: str
    title: str
    section: str | None = Field(None, description="Section heading, e.g. 'Art. 18'.")
    page: int | None = Field(None, description="1-based page for paginated formats (PDF).")
    char_start: int = Field(..., description="Offset in the parsed document text.")
    char_end: int
    source_url: str | None = None


class Evidence(BaseModel):
    """Ranking evidence. Scores are NOT calibrated probabilities and must not be read as confidence."""

    score: float = Field(..., description="Score of the system that produced the ranking (RRF for hybrid).")
    rank: int = Field(..., ge=1)
    retriever_ranks: dict[str, int | None] = Field(..., description="Rank in each retriever (bm25, dense); null = not retrieved.")
    retriever_scores: dict[str, float | None]


class Passage(BaseModel):
    passage_id: str
    text: str
    citation: Citation
    evidence: Evidence


class ResultDocument(BaseModel):
    document_id: str
    document_version: str
    title: str
    access_level: AccessLevel
    metadata: DocumentMetadata
    owner: str
    synthetic: bool
    llm_generated: bool
    best_rank: int
    passages: list[Passage]


class SummarySentence(BaseModel):
    text: str
    passage_id: str


class Summary(BaseModel):
    method: Literal["extractive"] = "extractive"
    generated: bool = Field(False, description="False: sentences are copied verbatim from passages.")
    sentences: list[SummarySentence]


class Versions(BaseModel):
    pipeline_version: str
    chunker_version: str
    embedding_model: str
    reranker_model: str | None
    index_snapshot_id: str | None


class SearchResponse(BaseModel):
    request_id: str
    query: str
    system: str = Field(..., description="Retrieval system that produced the shown ranking (B0, S1, S2).")
    results: list[ResultDocument] = Field(..., description="Documents ranked by their best passage.")
    insufficient_evidence: bool
    summary: Summary | None
    versions: Versions


# --- Documents, passages, feedback ----------------------------------------------------------

class DocumentInfo(BaseModel):
    document_id: str
    source_id: str
    external_id: str
    title: str
    access_level: AccessLevel
    metadata: DocumentMetadata
    owner: str
    source_piece: str
    validated_by: str | None
    synthetic: bool
    llm_generated: bool
    status: Literal["pending", "approved"]
    current_version: str
    versions: list[str]


class PassageInfo(BaseModel):
    passage_id: str
    text: str
    citation: Citation
    active: bool = Field(..., description="False when the passage belongs to a superseded document version.")


class FeedbackJudgement(str, Enum):
    useful = "useful"
    not_useful = "not_useful"
    wrong_source = "wrong_source"


class FeedbackRequest(_Strict):
    request_id: str = Field(..., min_length=1, max_length=64)
    passage_id: str = Field(..., min_length=1, max_length=64)
    judgement: FeedbackJudgement
    comment: str | None = Field(None, max_length=1000)


class FeedbackResult(BaseModel):
    feedback_id: int
    stored: bool = True


class Problem(BaseModel):
    """RFC 9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


# --- UniBridge: answers and handoff ---------------------------------------------------------

Lang = Literal["it", "en", "ar"]


class AnswerRequest(_Strict):
    query: str = Field(..., min_length=1, max_length=1000)
    language: Lang | None = Field(None, description="Answer language; null = detected from the query (it, en, ar).")
    mode: Literal["auto", "extractive", "llm", "llm_verified"] = Field(
        "auto", description="auto = llm_verified when an LLM is configured, else extractive. 'llm' skips the verifier (evaluation only).")
    top_k: int | None = Field(None, ge=1, le=20, description="Passages given to the answer step; null = server default.")
    with_handoff: bool = Field(True, description="Draft an e-mail to the responsible office when the answer is 'I don't know'.")


class SourcePassage(BaseModel):
    passage_id: str
    alias: str = Field(..., description="Short id used in the prompt (P1, P2, ...).")
    rank: int = Field(..., ge=1)
    text: str = Field(..., description="Original passage text (usually Italian), shown next to the answer.")
    citation: Citation


class AnswerSentence(BaseModel):
    text: str
    passage_ids: list[str] = Field(..., description="Passages cited by this sentence (empty = uncited, shown only in mode 'llm').")
    supported: bool | None = Field(None, description="Result of the support check (null = not checked).")


class VerificationReport(BaseModel):
    generated_sentences: int
    dropped_uncited: int
    dropped_invalid_citation: int
    dropped_unsupported: int
    support_checked: bool


class LLMUsage(BaseModel):
    provider: str
    model: str
    calls: int
    cached_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = Field(..., description="Estimated cost of the non-cached calls (price table in answer/llm.py).")


class HandoffSource(BaseModel):
    passage_id: str
    title: str
    section: str | None
    page: int | None
    source_url: str | None


class HandoffDraft(BaseModel):
    office_id: Literal["scholarship", "student_office", "international"]
    office_name: str
    channel: Literal["email", "srm_ticket", "desk"]
    to: str | None = Field(..., description="Recipient address, only when published in the corpus; null otherwise.")
    how_to_send: str = Field(..., description="How the student can contact the office (from the official documents).")
    contact_source: str = Field(..., description="Document that publishes the contact channel.")
    rule: str = Field(..., description="Why this office was chosen (rule table config/handoff_offices.json).")
    subject: str
    body: str = Field(..., description="Formal Italian text. Placeholders [..] are for the student; nothing personal is filled in.")
    question_original: str
    question_italian: str | None = Field(..., description="Italian translation of the question (LLM), null if not available.")
    translated_by_llm: bool
    sources: list[HandoffSource]
    sent: bool = Field(False, description="Always false: UniBridge never sends messages, the student does.")


class HandoffRequest(_Strict):
    query: str = Field(..., min_length=1, max_length=1000)
    language: Lang | None = None
    passage_ids: list[str] = Field(default_factory=list, max_length=10, description="Passages to mention (ACL-checked).")
    office_id: Literal["scholarship", "student_office", "international"] | None = Field(None, description="Override the rule table.")


class HandoffResponse(BaseModel):
    request_id: str
    language: Lang
    out_of_scope: bool = Field(..., description="True when no office matches the question: no draft is produced.")
    message: str
    draft: HandoffDraft | None


class AnswerResponse(BaseModel):
    request_id: str
    query: str
    language: Lang
    mode: Literal["llm_verified", "llm", "extractive", "insufficient_evidence"]
    answer_text: str = Field(..., description="Sentences joined, without citation markers; empty for 'I don't know'.")
    sentences: list[AnswerSentence]
    sources: list[SourcePassage] = Field(..., description="Passages given to the answer step, in rank order, with citations.")
    insufficient_evidence: bool = Field(..., description="True when the answer is 'I don't know'.")
    message: str | None = Field(None, description="Note in the user's language ('I don't know', extractive note, fallback).")
    handoff: HandoffResponse | None = None
    verification: VerificationReport | None = None
    llm: LLMUsage | None = None
    retrieval_system: str
    query_italian: str | None = Field(None, description="LLM translation of the query used as a second retrieval query.")
    latency_ms: float
    versions: Versions
