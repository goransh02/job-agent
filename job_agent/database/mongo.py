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

    def delete_many(self, criteria: dict[str, Any] | None = None) -> SimpleNamespace:
        expected = criteria or {}
        before = len(self._documents)
        self._documents = [
            document
            for document in self._documents
            if not _matches(document, expected)
        ]
        return SimpleNamespace(deleted_count=before - len(self._documents))

    def count_documents(self, criteria: dict[str, Any] | None = None) -> int:
        return len(self.find(criteria))

    def clear(self) -> None:
        self._documents.clear()


client = None
db = None
resume_bucket = None

_memory_collections = {
    "profile": InMemoryCollection(),
    "answers": InMemoryCollection(),
    "resume_chunks": InMemoryCollection(),
    "field_mappings": InMemoryCollection(),
    "applications": InMemoryCollection(),
}


def _create_mongo_collections() -> dict[str, Any] | None:
    global client, db, resume_bucket

    try:
        from pymongo import MongoClient
    except ImportError:
        return None

    try:
        temp_client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS,
        )
        temp_client.admin.command("ping")
    except Exception:
        # MongoDB not available, close client and return None
        try:
            temp_client.close()
        except Exception:
            pass
        return None

    # MongoDB is available, set global client
    client = temp_client
    db = client[DATABASE_NAME]

    try:
        from gridfs import GridFSBucket

        resume_bucket = GridFSBucket(db, bucket_name="resumes")
    except Exception:
        resume_bucket = None

    return {
        "profile": db["profile"],
        "answers": db["answers"],
        "resume_chunks": db["resume_chunks"],
        "field_mappings": db["field_mappings"],
        "applications": db["applications"],
    }


_mongo_collections = _create_mongo_collections()
_collections = _mongo_collections or _memory_collections

profile_collection = _collections["profile"]
answers_collection = _collections["answers"]
resume_chunks_collection = _collections["resume_chunks"]
field_mapping_collection = _collections["field_mappings"]
applications_collection = _collections["applications"]


def using_in_memory_storage() -> bool:
    return _mongo_collections is None


def has_mongo_storage() -> bool:
    return _mongo_collections is not None


def has_resume_bucket() -> bool:
    return resume_bucket is not None


def reset_in_memory_storage() -> None:
    for collection in _memory_collections.values():
        collection.clear()


def close_mongo_client() -> None:
    """Close the MongoDB client and clean up resources."""
    global client
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
        finally:
            client = None


# Register cleanup on exit
import atexit
atexit.register(close_mongo_client)
