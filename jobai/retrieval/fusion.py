"""Reciprocal Rank Fusion.

RRF is used rather than score averaging because the retrievers produce
incomparable numbers: FAISS gives a cosine similarity in [0, 1], BM25 gives an
unbounded Okapi score whose scale depends on the corpus, and the graph gives a
skill-overlap ratio. Averaging those would let whichever retriever happens to
have the largest numeric range dominate. RRF uses only each retriever's
*ordering*, which is the part that is actually comparable.

    score(d) = sum over retrievers of  weight_r / (k + rank_r(d))
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

Ranking = Sequence[Tuple[Dict[str, Any], float]]

DEFAULT_WEIGHTS: Dict[str, float] = {
    "dense": 1.0,
    "lexical": 0.9,
    "graph": 0.6,
    "expanded": 0.5,  # query-expansion arm, deliberately the weakest voice
}


def _job_key(metadata: Mapping[str, Any]) -> str:
    return str(metadata.get("job_id") or metadata.get("id") or metadata.get("job_link") or "")


def reciprocal_rank_fusion(
    rankings: Mapping[str, Ranking],
    *,
    k: int = 60,
    weights: Optional[Mapping[str, float]] = None,
    top_n: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fuse named rankings into one candidate list.

    Each entry keeps ``retriever_scores`` and ``retriever_ranks`` so the
    downstream scorer can report *why* a job surfaced, instead of handing the
    user an opaque number.
    """
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    fused: Dict[str, Dict[str, Any]] = {}

    for retriever, ranking in rankings.items():
        weight = float(weights.get(retriever, 1.0))
        if weight <= 0:
            continue
        for rank, (metadata, score) in enumerate(ranking, start=1):
            key = _job_key(metadata)
            if not key:
                continue
            entry = fused.get(key)
            if entry is None:
                entry = {
                    "job_id": key,
                    "metadata": dict(metadata),
                    "rrf_score": 0.0,
                    "retriever_scores": {},
                    "retriever_ranks": {},
                }
                fused[key] = entry
            entry["rrf_score"] += weight / (k + rank)
            entry["retriever_scores"][retriever] = float(score)
            entry["retriever_ranks"][retriever] = rank
            # Prefer the richest metadata seen for this job.
            if len(metadata) > len(entry["metadata"]):
                entry["metadata"] = dict(metadata)

    ordered = sorted(fused.values(), key=lambda e: e["rrf_score"], reverse=True)
    return ordered[:top_n] if top_n else ordered
