"""The end-to-end ingestion run.

    sources -> canonical schema -> dedup -> MongoDB -> FAISS -> BM25 -> graph

Each stage is isolated: a source that fails is reported and skipped, a Mongo
outage still lets the vector index update, and a graph failure never blocks
the rest. The run always returns a report rather than raising.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from jobai.config import get_settings
from jobai.dedup import deduplicate
from jobai.index_builder import index_jobs
from jobai.ingest.base import JobSource, SourceResult, all_jobs, run_sources
from jobai.schema import Job

logger = logging.getLogger(__name__)


def build_sources(names: Optional[Sequence[str]] = None) -> List[JobSource]:
    """Construct the requested sources. Unknown names are reported, not fatal."""
    from jobai.ingest.legacy import FaissArchiveSource, LegacyMongoSource, legacy_sources
    from jobai.ingest.linkedin import LinkedInSource
    from jobai.ingest.naukri import NaukriSource

    builders = {
        "linkedin": LinkedInSource,
        "naukri": NaukriSource,
        "mongo_archive": LegacyMongoSource,
        "faiss_archive": FaissArchiveSource,
    }
    if not names:
        names = ["linkedin", "naukri"]

    sources: List[JobSource] = []
    for name in names:
        if name == "legacy":
            sources.extend(legacy_sources())
        elif name in builders:
            sources.append(builders[name]())
        else:
            logger.warning("Unknown source %r; skipping.", name)
    return sources


def ingest(
    names: Optional[Sequence[str]] = None,
    *,
    limit_per_source: Optional[int] = None,
    semantic_dedup: bool = False,
    write_store: bool = True,
    build_index: bool = True,
) -> Dict[str, Any]:
    """Run ingestion and return a report of every stage."""
    settings = get_settings()
    sources = build_sources(names)
    if not sources:
        return {"error": "no sources selected", "sources": {}}

    results: Dict[str, SourceResult] = run_sources(sources, limit_per_source=limit_per_source)
    harvested: List[Job] = all_jobs(results)

    report: Dict[str, Any] = {
        "sources": {name: result.summary() for name, result in results.items()},
        "harvested": len(harvested),
    }
    if not harvested:
        report["warning"] = "no jobs harvested; every source failed or returned nothing"
        return report

    embedder = None
    if semantic_dedup:
        try:
            from jobai.retrieval.dense import get_embeddings

            embedder = get_embeddings().embed_documents
        except Exception as exc:
            logger.warning("Semantic dedup unavailable: %s", exc)

    canonical, dedup_stats = deduplicate(harvested, embedder=embedder)
    report["dedup"] = dedup_stats

    if write_store:
        try:
            from jobai.store import get_store

            store = get_store()
            store.require()
            store.ensure_indexes()
            report["store"] = store.upsert_jobs(canonical)
        except Exception as exc:
            # A Mongo outage must not cost us the vector index update.
            logger.error("Could not write to MongoDB: %s", exc)
            report["store"] = {"error": str(exc)}

    if build_index:
        try:
            report["index"] = index_jobs(canonical)
        except Exception as exc:
            logger.error("Indexing failed: %s", exc)
            report["index"] = {"error": str(exc)}

    return report
