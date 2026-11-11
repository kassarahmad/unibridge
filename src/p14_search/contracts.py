"""Frozen exchange contracts: which models are exported as JSON Schemas in contracts/schemas/."""

from __future__ import annotations

from pydantic import BaseModel

from p14_search import models

CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "IngestDocument": models.IngestDocument,
    "IngestResult": models.IngestResult,
    "SearchRequest": models.SearchRequest,
    "SearchResponse": models.SearchResponse,
    "Citation": models.Citation,
    "Evidence": models.Evidence,
    "Versions": models.Versions,
    "DocumentInfo": models.DocumentInfo,
    "PassageInfo": models.PassageInfo,
    "FeedbackRequest": models.FeedbackRequest,
    "Problem": models.Problem,
    # UniBridge
    "AnswerRequest": models.AnswerRequest,
    "AnswerResponse": models.AnswerResponse,
    "HandoffRequest": models.HandoffRequest,
    "HandoffResponse": models.HandoffResponse,
}

SCHEMA_ID_BASE = "https://p14.example/contracts/v1/"


def schema_for(name: str) -> dict:
    schema = CONTRACT_MODELS[name].model_json_schema(mode="serialization")
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"{SCHEMA_ID_BASE}{name}.json", **schema}
