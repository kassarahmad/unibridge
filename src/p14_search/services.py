"""Wiring of the application services (one place, so tests and scripts can build the same objects)."""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import QdrantClient

from p14_search.answer.llm import LLMClient, Provider, build_llm
from p14_search.answer.service import AnswerService
from p14_search.config import Settings
from p14_search.handoff.service import HandoffService
from p14_search.indexing.embedder import Embedder, SentenceTransformerEmbedder
from p14_search.indexing.store import Store
from p14_search.indexing.vector_index import VectorIndex
from p14_search.ingestion.service import IngestionService
from p14_search.procedure.guide import ScholarshipGuide
from p14_search.retrieval.retrievers import BM25Retriever, DenseRetriever
from p14_search.retrieval.service import SearchService
from p14_search.security.principals import PrincipalRegistry


@dataclass
class Services:
    settings: Settings
    store: Store
    qdrant: QdrantClient
    index: VectorIndex
    embedder: Embedder
    registry: PrincipalRegistry
    ingestion: IngestionService
    search: SearchService
    llm: LLMClient | None = None
    handoff: HandoffService | None = None
    answer: AnswerService | None = None
    procedure: ScholarshipGuide | None = None


def build_services(
    settings: Settings,
    *,
    store: Store | None = None,
    qdrant: QdrantClient | None = None,
    embedder: Embedder | None = None,
    registry: PrincipalRegistry | None = None,
    llm_provider: Provider | None = None,
) -> Services:
    """llm_provider: inject a provider (tests use FakeProvider); None = from settings (None when not configured)."""
    store = store or Store(settings.sqlite_path)
    qdrant = qdrant or QdrantClient(url=settings.qdrant_url, timeout=30)
    embedder = embedder or SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_device)
    registry = registry or PrincipalRegistry.from_config(settings.principals_path)
    index = VectorIndex(qdrant, settings.qdrant_collection, embedder.name, embedder.dim)
    index.ensure_collection()
    search = SearchService(store, BM25Retriever(store), DenseRetriever(index, embedder), settings)
    llm = build_llm(settings, llm_provider)
    handoff = HandoffService(llm)
    return Services(
        settings=settings,
        store=store,
        qdrant=qdrant,
        index=index,
        embedder=embedder,
        registry=registry,
        ingestion=IngestionService(store, index, embedder, settings.max_upload_mb * 1024 * 1024),
        search=search,
        llm=llm,
        handoff=handoff,
        answer=AnswerService(search, llm, handoff, settings),
        procedure=ScholarshipGuide(store),
    )
