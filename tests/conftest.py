"""Shared fixtures: an in-process P14 with in-memory SQLite, Qdrant local mode and a hashing embedder.
No model download and no Docker needed for the unit/API tests."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from fixtures import make_txt
from p14_search.api.app import create_app
from p14_search.config import Settings
from p14_search.indexing.embedder import HashingEmbedder
from p14_search.indexing.store import Store
from p14_search.models import AccessLevel
from p14_search.security.principals import Principal, PrincipalRegistry
from p14_search.services import build_services

PRINCIPALS = {
    "key-public": Principal("p24-external-assistant", "consumer", AccessLevel.public, ()),
    "key-internal": Principal("employee", "employee", AccessLevel.internal, ()),
    "key-hr": Principal("hr-officer", "officer", AccessLevel.restricted, ("hr",)),
    "key-it": Principal("it-officer", "officer", AccessLevel.restricted, ("it",)),
    "key-admin": Principal("admin", "admin", AccessLevel.restricted, ("*",)),
}

# Each document carries a unique sentinel word so tests can query exactly one access level.
CORPUS = [
    ("pub-faq", "public", "legal", "FAQ pubblica", "Lo sportello pubblico apre alle nove. Parola sentinella: alfapubblico. Orari e contatti."),
    ("int-agile", "internal", "hr", "Regolamento lavoro agile", "Il lavoro agile prevede 10 giornate al mese. Parola sentinella: betainterno. Disconnessione serale."),
    ("res-budget", "restricted", "hr", "Budget formazione", "Il budget riservato della formazione è di 48.000 euro. Parola sentinella: gammahr. Formazione riservata."),
    ("res-incident", "restricted", "it", "Piano incidenti", "La sala crisi riservata è la stanza 3.12. Parola sentinella: deltait. Incidenti informatici."),
]


def ingest_payload(external_id: str, access: str, office: str, title: str, text: str) -> dict:
    return {
        "source_id": "test",
        "external_id": external_id,
        "title": title,
        "file": {"filename": f"{external_id}.txt", "media_type": "text/plain", "content_base64": base64.b64encode(make_txt(text)).decode()},
        "metadata": {"office": office, "type": "test"},
        "access_level": access,
        "owner": f"owner of {office}",
    }


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Tests never call a real LLM API: drop any LLM configuration coming from the environment."""
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def services():
    settings = Settings(_env_file=None, display_system="S2", shadow_system="B0", llm_provider="")
    return build_services(
        settings,
        store=Store(":memory:"),
        qdrant=QdrantClient(":memory:"),
        embedder=HashingEmbedder(),
        registry=PrincipalRegistry(PRINCIPALS),
    )


@pytest.fixture
def client(services):
    return TestClient(create_app(services.settings, services=services))


@pytest.fixture
def loaded(client):
    """Client with the four-document corpus ingested and approved by the admin."""
    for item in CORPUS:
        r = client.post("/v1/documents", json=ingest_payload(*item), headers={"X-API-Key": "key-admin"})
        assert r.status_code == 202, r.text
        r = client.post(f"/v1/documents/test:{item[0]}/approve", json={"note": "test approval"}, headers={"X-API-Key": "key-admin"})
        assert r.status_code == 200, r.text
    return client
