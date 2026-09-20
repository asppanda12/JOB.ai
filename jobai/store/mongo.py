"""MongoDB adapter.

Wraps the *existing* databases and collections (``USER.JOB_USER``,
``USER_1.JOB_Data``, ``USER_1.Job_specific``) rather than introducing new ones,
so data already in the cluster keeps working. Collection names are
configurable but default to exactly what the legacy code used.

``Data_base/mongodb.py`` still exposes its three original factory functions;
they now delegate here so there is one connection pool instead of one client
per call.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from jobai.config import get_settings
from jobai.schema import Job

logger = logging.getLogger(__name__)


class StoreUnavailable(RuntimeError):
    """MongoDB could not be reached."""


class JobStore:
    """Thin, lazily-connected accessor over the three legacy collections."""

    def __init__(self, uri: Optional[str] = None):
        settings = get_settings().store
        self.settings = settings
        self.uri = uri or settings.mongo_uri
        self._client = None

    # ------------------------------------------------------------ connection

    @property
    def client(self):
        if self._client is None:
            from pymongo import MongoClient
            from pymongo.server_api import ServerApi

            kwargs: Dict[str, Any] = {"serverSelectionTimeoutMS": 8000}
            # ServerApi v1 is required by Atlas and harmless locally, but the
            # legacy code also passed tls=True unconditionally, which breaks a
            # plain local mongod. Only enable TLS for mongodb+srv / explicit tls.
            if self.uri.startswith("mongodb+srv://") or "tls=true" in self.uri.lower():
                kwargs["server_api"] = ServerApi("1")
            self._client = MongoClient(self.uri, **kwargs)
        return self._client

    def ping(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception as exc:
            logger.error("MongoDB unreachable at %s: %s", _redact(self.uri), exc)
            return False

    def require(self) -> None:
        if not self.ping():
            raise StoreUnavailable(
                f"Cannot reach MongoDB at {_redact(self.uri)}. "
                "Start it (`brew services start mongodb-community`) or set MONGO_DB_URI."
            )

    # ----------------------------------------------------------- collections

    @property
    def users(self):
        return self.client[self.settings.user_db][self.settings.user_collection]

    @property
    def jobs(self):
        return self.client[self.settings.job_db][self.settings.job_collection]

    @property
    def recommendations(self):
        return self.client[self.settings.job_db][self.settings.recommendation_collection]

    def ensure_indexes(self) -> None:
        """Indexes the legacy code never created; all are idempotent."""
        try:
            self.users.create_index("chat_id", unique=True)
            self.jobs.create_index("job_id", unique=True, sparse=True)
            self.jobs.create_index("content_hash")
            self.jobs.create_index([("Source", 1), ("Posted_date", -1)])
            self.recommendations.create_index("chat_id")
        except Exception as exc:
            logger.warning("Could not create Mongo indexes: %s", exc)

    # ------------------------------------------------------------------ jobs

    def upsert_jobs(self, jobs: Iterable[Job]) -> Dict[str, int]:
        """Upsert by ``job_id``. Returns inserted/updated/unchanged counts.

        Unchanged jobs (same content hash) are left alone so the indexer can
        skip re-embedding them.
        """
        from pymongo import UpdateOne

        operations = []
        stats = {"inserted": 0, "updated": 0, "unchanged": 0}
        existing = self.content_hashes()
        for job in jobs:
            job = job.finalize()
            previous = existing.get(job.job_id)
            if previous == job.content_hash:
                stats["unchanged"] += 1
                continue
            stats["updated" if previous else "inserted"] += 1
            document = job.to_legacy_metadata()
            document["job_id"] = job.job_id
            operations.append(UpdateOne({"job_id": job.job_id}, {"$set": document}, upsert=True))

        for start in range(0, len(operations), 500):
            self.jobs.bulk_write(operations[start : start + 500], ordered=False)
        logger.info("Job upsert: %s", stats)
        return stats

    def content_hashes(self) -> Dict[str, str]:
        try:
            cursor = self.jobs.find({}, {"job_id": 1, "content_hash": 1, "_id": 0})
            return {str(d["job_id"]): str(d.get("content_hash", "")) for d in cursor if d.get("job_id")}
        except Exception as exc:
            logger.warning("Could not read content hashes: %s", exc)
            return {}

    def all_jobs(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        cursor = self.jobs.find({}, {"_id": 0})
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def find_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.jobs.find_one({"job_id": str(job_id)}, {"_id": 0})

    # ----------------------------------------------------------------- users

    def get_user(self, chat_id: Any) -> Optional[Dict[str, Any]]:
        try:
            return self.users.find_one({"chat_id": int(chat_id)})
        except (TypeError, ValueError):
            return self.users.find_one({"chat_id": chat_id})

    def upsert_user(self, document: Dict[str, Any]) -> None:
        self.users.update_one({"chat_id": document["chat_id"]}, {"$set": document}, upsert=True)

    def set_user_profile(self, chat_id: Any, profile: Dict[str, Any]) -> None:
        """Cache the parsed profile on the user so the resume is parsed once."""
        self.users.update_one({"chat_id": int(chat_id)}, {"$set": {"profile": profile}})

    # ------------------------------------------------------- recommendations

    def save_recommendations(self, chat_id: Any, results: List[Dict[str, Any]]) -> None:
        """Replace this user's recommendations.

        Stored under ``job_recommendation`` with a ``metadata`` key per entry,
        which is the exact shape ``telegram_bot.py`` already reads.
        """
        chat_id = int(chat_id)
        self.recommendations.delete_many({"chat_id": chat_id})
        self.recommendations.insert_one({"chat_id": chat_id, "job_recommendation": results})

    def get_recommendations(self, chat_id: Any) -> List[Dict[str, Any]]:
        document = self.recommendations.find_one({"chat_id": int(chat_id)})
        return (document or {}).get("job_recommendation", [])

    def find_recommendation(self, chat_id: Any, job_indx: Any) -> Optional[Dict[str, Any]]:
        """Look up one recommended job by its index.

        Compares as strings because the legacy index stored ``job_indx`` as a
        string while ``master_data.py`` wrote it as an int - the old exact-match
        Mongo query silently failed whenever the two disagreed.
        """
        wanted = str(job_indx)
        for entry in self.get_recommendations(chat_id):
            metadata = entry.get("metadata", entry)
            if str(metadata.get("job_indx")) == wanted or str(metadata.get("job_id")) == wanted:
                return entry
        return None


def _redact(uri: str) -> str:
    import re

    return re.sub(r"://[^@/]+@", "://***@", uri or "")


_store: Optional[JobStore] = None


def get_store(uri: Optional[str] = None) -> JobStore:
    global _store
    if _store is None or (uri and uri != _store.uri):
        _store = JobStore(uri)
    return _store
