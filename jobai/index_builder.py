"""Incremental indexing.

The legacy flow deleted ``vector_store/`` and re-embedded every job from
scratch on each run - thousands of forward passes to add a handful of postings.
Here a job is re-embedded only when its **content hash** changes:

    new job            -> embed, add to FAISS, add to the graph
    changed job        -> drop the old vector, embed the new text, re-add
    unchanged job      -> reuse the existing vector, touch nothing

BM25 and the graph are cheap to rebuild and are derived from the FAISS
docstore, so they are regenerated after any change to stay perfectly in sync.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

from jobai.config import get_settings
from jobai.retrieval.dense import DenseIndex
from jobai.retrieval.graph import JobGraph
from jobai.retrieval.lexical import BM25Index
from jobai.schema import Job

logger = logging.getLogger(__name__)


def assign_indices(jobs: Sequence[Job], start: int = 0) -> None:
    """Give each job the stable integer the Telegram buttons address it by."""
    for offset, job in enumerate(jobs):
        if job.job_indx is None:
            job.job_indx = start + offset


def index_jobs(
    jobs: Iterable[Job],
    *,
    dense: Optional[DenseIndex] = None,
    rebuild_derived: bool = True,
    save: bool = True,
) -> Dict[str, int]:
    """Add or refresh jobs in FAISS, then rebuild BM25 and the graph."""
    settings = get_settings()
    dense = dense or DenseIndex()
    known = dense.existing_hashes()

    new_texts: List[str] = []
    new_metadatas: List[Dict[str, Any]] = []
    new_ids: List[str] = []
    stale_job_ids: List[str] = []
    stats = {"added": 0, "updated": 0, "unchanged": 0, "skipped": 0}

    jobs = list(jobs)
    assign_indices(jobs, start=len(known))

    for job in jobs:
        job = job.finalize()
        # A title is the minimum viable job. Without one the canonical text is
        # just the field labels, which would put a meaningless vector in the
        # index and surface as an untitled result in Telegram.
        if not job.title.strip() or not job.normalized_text.strip():
            stats["skipped"] += 1
            continue
        previous = known.get(job.job_id)
        if previous == job.content_hash:
            stats["unchanged"] += 1
            continue
        if previous is not None:
            stale_job_ids.append(job.job_id)
            stats["updated"] += 1
        else:
            stats["added"] += 1
        new_texts.append(job.normalized_text)
        new_metadatas.append(job.to_legacy_metadata())
        new_ids.append(job.job_id)

    if stale_job_ids:
        dense.delete(dense.vector_ids_for(stale_job_ids))

    if new_texts:
        logger.info("Embedding %d new/changed jobs", len(new_texts))
        dense.add(new_texts, new_metadatas, new_ids)
        if save:
            dense.save()
    else:
        logger.info("Vector index already up to date; nothing re-embedded.")

    if rebuild_derived and (new_texts or stale_job_ids):
        rebuild_derived_indexes(dense)

    stats["total_indexed"] = dense.count()
    logger.info("Indexing: %s", stats)
    return stats


def rebuild_derived_indexes(dense: Optional[DenseIndex] = None) -> Dict[str, int]:
    """Rebuild BM25 and the graph from the FAISS docstore.

    Derived from FAISS rather than from the ingest batch so the three arms can
    never drift apart, whatever partial failures happened upstream.
    """
    dense = dense or DenseIndex()
    corpus = dense.all_metadata()

    bm25 = BM25Index().build(corpus)
    try:
        bm25.save()
    except Exception as exc:
        logger.warning("Could not persist BM25 index: %s", exc)

    graph_jobs = 0
    if get_settings().retrieval.graph_enabled:
        try:
            graph = JobGraph(corpus)
            graph_jobs = len(graph.fallback.job_to_meta)
        except Exception as exc:
            # A graph failure must never take the vector/lexical path down.
            logger.warning("Graph indexing failed (%s); retrieval continues without it.", exc)

    logger.info("Rebuilt derived indexes: %d BM25 docs, %d graph jobs", len(corpus), graph_jobs)
    return {"bm25": len(corpus), "graph": graph_jobs}
