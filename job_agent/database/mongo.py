from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

from job_agent.config import (
    DATABASE_NAME,
    MONGO_SERVER_SELECTION_TIMEOUT_MS,
    MONGO_URI,
)


def _matches(document: dict[str, Any], criteria: dict[str, Any]) -> bool:
    for key, value in criteria.items():
        if document.get(key) != value:
            return False
    return True


class InMemoryCollection:
    def __init__(self) -> None:
        self._documents: list[dict[str, Any]] = []

    def find_one(self, criteria: dict[str, Any] | None = None) -> dict[str, Any] | None:
        for document in self.find(criteria):
            return document
        return None

    def find(self, criteria: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        expected = criteria or {}
        return [
            copy.deepcopy(document)
            for document in self._documents
            if _matches(document, expected)
        ]

    def insert_one(self, document: dict[str, Any]) -> SimpleNamespace:
        stored = copy.deepcopy(document)
        self._documents.append(stored)
        return SimpleNamespace(inserted_id=len(self._documents) - 1)

    def replace_one(
        self,
        criteria: dict[str, Any],
        replacement: dict[str, Any],
        upsert: bool = False,
    ) -> SimpleNamespace:
        for index, document in enumerate(self._documents):
            if _matches(document, criteria):
                self._documents[index] = copy.deepcopy(replacement)
                return SimpleNamespace(matched_count=1, modified_count=1)

        if upsert:
            self._documents.append(copy.deepcopy(replacement))
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=len(self._documents) - 1)

        return SimpleNamespace(matched_count=0, modified_count=0)

    def clear(self) -> None:
        self._documents.clear()


client = None
db = None

_memory_collections = {
    "profile": InMemoryCollection(),
    "answers": InMemoryCollection(),
    "field_mappings": InMemoryCollection(),
    "applications": InMemoryCollection(),
}


def _create_mongo_collections() -> dict[str, Any] | None:
    global client, db

    try:
        from pymongo import MongoClient
    except ImportError:
        return None

    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS,
    )

    try:
        client.admin.command("ping")
    except Exception:
        client = None
        return None

    db = client[DATABASE_NAME]
    return {
        "profile": db["profile"],
        "answers": db["answers"],
        "field_mappings": db["field_mappings"],
        "applications": db["applications"],
    }


_mongo_collections = _create_mongo_collections()
_collections = _mongo_collections or _memory_collections

profile_collection = _collections["profile"]
answers_collection = _collections["answers"]
field_mapping_collection = _collections["field_mappings"]
applications_collection = _collections["applications"]


def using_in_memory_storage() -> bool:
    return _mongo_collections is None


def reset_in_memory_storage() -> None:
    for collection in _memory_collections.values():
        collection.clear()
