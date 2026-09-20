"""FAISS-backed job search.

``JobSearchEngine`` keeps its original constructor and its ``query(chat_id)``
entry point, because ``telegram_bot.py`` calls exactly that. What changed is
what happens underneath: instead of a bare ``similarity_search`` followed by a
years-of-experience filter, ``query`` now runs the full hybrid funnel

    FAISS + BM25 + graph -> RRF -> metadata filters -> cross-encoder -> scoring

via :mod:`jobai.recommend`, and writes the results to the same MongoDB
collection in the same shape as before.

The vector store itself is untouched: same path, same ``BAAI/bge-large-en-v1.5``
embeddings, same ``IndexFlatL2`` at 1024 dimensions, same LangChain docstore
format. The index committed to this repository loads as-is.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from jobai.config import get_settings
from jobai.retrieval.dense import DenseIndex
from jobai.retrieval.pipeline import RetrievalPipeline

logger = logging.getLogger(__name__)


class JobSearchEngine:
    """Backwards-compatible facade over the hybrid retrieval pipeline."""

    def __init__(
        self,
        json_data: Optional[List[Dict[str, Any]]] = None,
        embeddings_model: Optional[str] = None,
        vector_store_path: Optional[str] = None,
    ):
        settings = get_settings()
        self.settings = settings
        self.embeddings_model = embeddings_model or settings.retrieval.embedding_model
        self.index = DenseIndex(path=vector_store_path or settings.retrieval.vector_db_path)
        self._pipeline: Optional[RetrievalPipeline] = None

        if json_data:
            self.job_data = self._load_and_preprocess_job_data(json_data)
            self._populate_vector_store()

    # ------------------------------------------------------------- legacy API

    @property
    def vector_store(self):
        """The underlying LangChain FAISS store (unchanged format)."""
        return self.index.store

    @property
    def pipeline(self) -> RetrievalPipeline:
        if self._pipeline is None:
            self._pipeline = RetrievalPipeline(dense=self.index)
        return self._pipeline

    @staticmethod
    def _load_and_preprocess_job_data(job_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize ``yoe`` into the ``"min,max"`` string the metadata uses."""
        for job in job_data:
            yoe = job.get("yoe")
            if yoe is None or (isinstance(yoe, float) and math.isnan(yoe)):
                job["yoe"] = "0,60"
            elif isinstance(yoe, (list, tuple)) and len(yoe) == 2:
                job["yoe"] = ",".join(map(str, yoe))
        return job_data

    def _populate_vector_store(self) -> None:
        """Index raw job dicts.

        Prefer ``jobai.index_builder.index_jobs``: it is incremental, whereas
        this path re-embeds everything it is given. Kept for compatibility with
        the original bulk-load script.
        """
        from jobai.schema import Job

        jobs = [Job.from_legacy(record) for record in self.job_data]
        texts, metadatas, ids = [], [], []
        for job in jobs:
            job = job.finalize()
            if not job.normalized_text.strip():
                continue
            texts.append(job.normalized_text)
            metadatas.append(job.to_legacy_metadata())
            ids.append(job.job_id or str(uuid4()))
        self.index.add(texts, metadatas, ids)
        logger.info("Added %d documents to the vector store.", len(texts))

    def save_vector_store(self, save_path: Optional[str] = None) -> None:
        if save_path:
            self.index.path = type(self.index.path)(save_path)
        self.index.save()

    def query(self, chat_id: Any, k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Recommend jobs for a registered user and persist them.

        Same signature and same side effect as before - the results land in
        ``USER_1.Job_specific`` under ``job_recommendation`` - but the ranking
        now comes from the full hybrid funnel rather than raw vector distance.

        The old implementation also crashed on ``filtered_results[0]`` whenever
        a user had no matches; this returns an empty list instead.
        """
        from jobai.recommend import recommend_for_user

        top_k = k or self.settings.retrieval.rerank_k
        outcome = recommend_for_user(chat_id, top_k=top_k, explain=False, persist=True)
        jobs = outcome["jobs"]
        logger.info("Found %d results for chat_id %s", len(jobs), chat_id)
        return jobs

    # -------------------------------------------------------------- utilities

    def save_results_to_json(self, results: List[Dict[str, Any]], output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=4, default=json_serializable)

    def save_results_to_mongo_db(self, chat_id: Any, results: List[Dict[str, Any]]) -> None:
        from jobai.store import get_store

        get_store().save_recommendations(chat_id, results)

    def delete_results_for_chat_id(self, data_base, chat_id: Any) -> None:
        result = data_base.delete_many({"chat_id": int(chat_id)})
        logger.info("Deleted %d documents for chat_id %s", result.deleted_count, chat_id)


def json_serializable(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


if __name__ == "__main__":
    # Prefer the CLI: `python -m jobai recommend --chat-id <id>`
    import sys

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage: python -m Data_base.faiss_db_v2 <chat_id>")
        raise SystemExit(2)
    engine = JobSearchEngine()
    for job in engine.query(sys.argv[1]):
        metadata = job.get("metadata", {})
        print(f"[{job.get('match_score'):.3f}] {metadata.get('job_title')} @ {metadata.get('company_name')}")
