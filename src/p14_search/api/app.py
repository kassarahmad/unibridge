"""FastAPI application: P14 search/retrieval API (contract: contracts/openapi/p14-search.yaml)."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from p14_search import __version__
from p14_search.config import Settings, get_settings
from p14_search.ingestion.parser import ParseError
from p14_search.ingestion.service import NotAllowed, NotFound
from p14_search.models import (
    AnswerRequest,
    AnswerResponse,
    Citation,
    DocumentInfo,
    DocumentMetadata,
    FeedbackRequest,
    FeedbackResult,
    HandoffRequest,
    HandoffResponse,
    HandoffSource,
    IngestDocument,
    IngestResult,
    PassageInfo,
    Problem,
    SearchRequest,
    SearchResponse,
    Versions,
)
from p14_search.observability.logging import configure_logging
from p14_search.security import acl
from p14_search.security.principals import Principal
from p14_search.services import Services, build_services

log = logging.getLogger("p14.api")
PROBLEM_JSON = "application/problem+json"
ERRORS = {code: {"model": Problem, "content": {PROBLEM_JSON: {}}} for code in (401, 403, 404, 413, 415, 422, 503)}


class ApproveRequest(BaseModel):
    note: str | None = Field(None, max_length=500, description="Why the owner approves (stored in approval_log).")


class HealthResponse(BaseModel):
    status: str = Field(..., description="ok | degraded")
    components: dict[str, str]


class ApiError(Exception):
    def __init__(self, status: int, title: str, detail: str | None = None):
        self.status, self.title, self.detail = status, title, detail


def problem(request: Request, status: int, title: str, detail: str | None = None) -> JSONResponse:
    body = Problem(title=title, status=status, detail=detail, instance=request.url.path).model_dump()
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers={"X-Request-ID": getattr(request.state, "request_id", "")})


def _is_backend_error(exc: Exception) -> bool:
    name = type(exc).__name__
    return isinstance(exc, (ConnectionError, TimeoutError)) or name in ("ResponseHandlingException", "UnexpectedResponse", "ConnectError")


def create_app(settings: Settings | None = None, services: Services | None = None, init_services: bool = True) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.services is None and init_services:
            app.state.services = build_services(settings)
        yield

    app = FastAPI(
        title="P14 Knowledge Search API",
        version=__version__,
        description=(
            "Search across organizational knowledge with verifiable citations (AI Puzzle piece P14). "
            "Errors use RFC 9457 problem+json. Authentication: X-API-Key header."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.services = services

    # --- middleware and error handlers -------------------------------------------------------
    @app.middleware("http")
    async def request_log(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return problem(request, exc.status, exc.title, exc.detail)

    @app.exception_handler(ParseError)
    async def _parse_error(request: Request, exc: ParseError):
        titles = {413: "Payload too large", 415: "Unsupported media type"}
        return problem(request, exc.status, titles.get(exc.status, "Invalid document"), str(exc))

    @app.exception_handler(NotAllowed)
    async def _not_allowed(request: Request, exc: NotAllowed):
        return problem(request, 403, "Forbidden", str(exc))

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound):
        return problem(request, 404, "Not found", f"unknown id: {exc}")

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        detail = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
        return problem(request, 422, "Validation error", detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return problem(request, exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        if _is_backend_error(exc):
            log.error("backend unavailable", extra={"error": type(exc).__name__})
            return problem(request, 503, "Index backend unavailable", "the vector index is not reachable; retry later")
        log.exception("unhandled error")
        return problem(request, 500, "Internal error")

    # --- dependencies ------------------------------------------------------------------------
    def get_services(request: Request) -> Services:
        if request.app.state.services is None:
            raise ApiError(503, "Service not initialised")
        return request.app.state.services

    def get_principal(request: Request, services: Services = Depends(get_services)) -> Principal:
        principal = services.registry.authenticate(request.headers.get("X-API-Key"))
        if principal is None:
            raise ApiError(401, "Unauthorized", "missing or unknown X-API-Key")
        return principal

    # --- meta --------------------------------------------------------------------------------
    @app.get("/v1/health", tags=["meta"], response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        services: Services | None = request.app.state.services
        if services is None:
            return HealthResponse(status="degraded", components={"services": "not initialised"})
        components = {}
        try:
            services.store.query("SELECT 1")
            components["sqlite"] = "ok"
        except Exception:
            components["sqlite"] = "unavailable"
        try:
            services.qdrant.get_collections()
            components["qdrant"] = "ok"
        except Exception:
            components["qdrant"] = "unavailable"
        status = "ok" if all(v == "ok" for v in components.values()) else "degraded"
        return HealthResponse(status=status, components=components)

    @app.get("/v1/version", tags=["meta"], response_model=Versions)
    def version(services: Services = Depends(get_services)) -> Versions:
        return services.search.versions()

    # --- search ------------------------------------------------------------------------------
    @app.post("/v1/search", tags=["search"], response_model=SearchResponse, responses=ERRORS)
    def search(
        request: Request,
        body: SearchRequest,
        principal: Principal = Depends(get_principal),
        services: Services = Depends(get_services),
    ) -> SearchResponse:
        return services.search.search(body, principal, request.state.request_id)

    # --- UniBridge: answers and handoff ------------------------------------------------------
    @app.post("/v1/answer", tags=["answer"], response_model=AnswerResponse, responses=ERRORS)
    def answer(
        request: Request,
        body: AnswerRequest,
        principal: Principal = Depends(get_principal),
        services: Services = Depends(get_services),
    ) -> AnswerResponse:
        """Answer in the student's language (it, en, ar); every sentence cites a passage, shown with its Italian original.
        Without a configured LLM the answer is extractive. Weak evidence -> 'I don't know' + a draft for the right office."""
        return services.answer.answer(body, principal, request.state.request_id)

    @app.post("/v1/handoff", tags=["answer"], response_model=HandoffResponse, responses=ERRORS)
    def handoff(
        request: Request,
        body: HandoffRequest,
        principal: Principal = Depends(get_principal),
        services: Services = Depends(get_services),
    ) -> HandoffResponse:
        """Draft (never send) a formal Italian message to the office responsible for the question."""
        sources = []
        for pid in body.passage_ids:
            rows = services.store.query(
                """SELECT p.passage_id, p.section, p.page, d.title, d.source_url, d.access_level, d.office
                   FROM passages p JOIN documents d ON d.document_id = p.document_id WHERE p.passage_id = ? AND p.indexed = 1""",
                (pid,),
            )
            if not rows or not acl.allows(principal, rows[0]["access_level"], rows[0]["office"]):
                raise NotFound(pid)
            r = rows[0]
            sources.append(HandoffSource(passage_id=pid, title=r["title"], section=r["section"], page=r["page"], source_url=r["source_url"]))
        return services.handoff.draft(body.query, body.language, sources, request.state.request_id, office_id=body.office_id)

    # --- documents ---------------------------------------------------------------------------
    @app.post("/v1/documents", tags=["documents"], response_model=IngestResult, status_code=202, responses=ERRORS)
    def ingest(body: IngestDocument, principal: Principal = Depends(get_principal), services: Services = Depends(get_services)) -> IngestResult:
        """Ingest a document. It stays NOT searchable until an owner approves it (human oversight)."""
        return services.ingestion.ingest(body, principal)

    @app.post("/v1/documents/{document_id}/approve", tags=["documents"], response_model=IngestResult, responses=ERRORS)
    def approve(
        document_id: str,
        body: ApproveRequest = Body(default_factory=ApproveRequest),
        principal: Principal = Depends(get_principal),
        services: Services = Depends(get_services),
    ) -> IngestResult:
        """Owner approval: indexes the current version and makes it searchable."""
        return services.ingestion.approve(document_id, principal, body.note)

    @app.get("/v1/documents/{document_id}", tags=["documents"], response_model=DocumentInfo, responses=ERRORS)
    def get_document(document_id: str, principal: Principal = Depends(get_principal), services: Services = Depends(get_services)) -> DocumentInfo:
        rows = services.store.query("SELECT * FROM documents WHERE document_id = ?", (document_id,))
        if not rows or not _visible(principal, rows[0], approved=rows[0]["status"] == "approved"):
            raise NotFound(document_id)  # same answer for "absent" and "not allowed": no existence leak
        d = rows[0]
        versions = services.store.query(
            "SELECT document_version FROM document_versions WHERE document_id = ? ORDER BY ingested_at", (document_id,)
        )
        return DocumentInfo(
            document_id=d["document_id"],
            source_id=d["source_id"],
            external_id=d["external_id"],
            title=d["title"],
            access_level=d["access_level"],
            metadata=DocumentMetadata(
                office=d["office"], type=d["type"], author=d["author"], date=d["date"], project=d["project"], source_url=d["source_url"]
            ),
            owner=d["owner"],
            source_piece=d["source_piece"],
            validated_by=d["validated_by"],
            synthetic=bool(d["synthetic"]),
            llm_generated=bool(d["llm_generated"]),
            status=d["status"],
            current_version=d["current_version"],
            versions=[v["document_version"] for v in versions],
        )

    @app.get("/v1/passages/{passage_id}", tags=["documents"], response_model=PassageInfo, responses=ERRORS)
    def get_passage(passage_id: str, principal: Principal = Depends(get_principal), services: Services = Depends(get_services)) -> PassageInfo:
        """Resolve a cited passage, also from superseded versions (active=false)."""
        rows = services.store.query(
            """SELECT p.*, d.title, d.office, d.access_level, d.source_url, v.status AS version_status
               FROM passages p JOIN documents d ON d.document_id = p.document_id
               JOIN document_versions v ON v.document_id = p.document_id AND v.document_version = p.document_version
               WHERE p.passage_id = ?""",
            (passage_id,),
        )
        if not rows or not _visible(principal, rows[0], approved=rows[0]["version_status"] in ("approved", "superseded")):
            raise NotFound(passage_id)
        r = rows[0]
        return PassageInfo(
            passage_id=r["passage_id"],
            text=r["text"],
            citation=Citation(
                document_id=r["document_id"],
                document_version=r["document_version"],
                title=r["title"],
                section=r["section"],
                page=r["page"],
                char_start=r["char_start"],
                char_end=r["char_end"],
                source_url=r["source_url"],
            ),
            active=bool(r["active"]),
        )

    # --- feedback ----------------------------------------------------------------------------
    @app.post("/v1/feedback", tags=["feedback"], response_model=FeedbackResult, status_code=201, responses=ERRORS)
    def feedback(body: FeedbackRequest, principal: Principal = Depends(get_principal), services: Services = Depends(get_services)) -> FeedbackResult:
        """Store the user's judgement on a returned passage (operator's final decision, for traceability)."""
        if not services.store.query("SELECT 1 FROM query_log WHERE request_id = ?", (body.request_id,)):
            raise NotFound(body.request_id)
        fid = services.store.add_feedback(body.request_id, body.passage_id, body.judgement.value, body.comment, principal.pseudonym)
        return FeedbackResult(feedback_id=fid)

    return app


def _visible(principal: Principal, row, approved: bool) -> bool:
    """Approved content follows the ACL; pending content is visible only to who may approve it."""
    if approved:
        return acl.allows(principal, row["access_level"], row["office"])
    return principal.can_manage(row["office"])
