"""Second-stage cross-encoder reranking.

First-stage retrieval scores the query and the document independently, so it
can only ever approximate relevance. A cross-encoder reads the pair together
and is markedly more accurate - but it costs a forward pass per candidate, so
it runs on the ~50-100 survivors of fusion, never on the corpus.

The model is local and configurable via ``RERANKER_MODEL``. If it cannot be
loaded (no weights cached, no network on first run), reranking is skipped and
the fused RRF order is used as-is.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from jobai.config import get_settings

logger = logging.getLogger(__name__)

_model_cache: Dict[str, Any] = {}
_failed: set[str] = set()


def get_reranker(model_name: Optional[str] = None):
    """Load and cache the cross-encoder. Returns None when unavailable."""
    name = model_name or get_settings().retrieval.reranker_model
    if name in _failed:
        return None
    if name not in _model_cache:
        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading reranker %s", name)
            _model_cache[name] = CrossEncoder(name, max_length=512)
        except Exception as exc:
            logger.warning("Reranker %s unavailable (%s); keeping the fused order.", name, exc)
            _failed.add(name)
            return None
    return _model_cache[name]


def _document_text(metadata: Dict[str, Any]) -> str:
    """What the cross-encoder reads. Front-load the fields that decide relevance."""
    skills = metadata.get("skills_list") or metadata.get("skills") or []
    skills_text = skills if isinstance(skills, str) else ", ".join(map(str, skills))
    parts = [
        str(metadata.get("job_title") or metadata.get("title") or ""),
        f"at {metadata.get('company_name') or metadata.get('company') or ''}",
        f"in {metadata.get('location') or ''}",
        f"Skills: {skills_text}",
        str(metadata.get("text") or metadata.get("normalized_text") or "")[:1200],
    ]
    return ". ".join(p for p in parts if p.strip(". "))


def rerank(
    query: str,
    candidates: Sequence[Dict[str, Any]],
    *,
    top_k: int = 20,
    model_name: Optional[str] = None,
    batch_size: int = 32,
) -> List[Dict[str, Any]]:
    """Re-order fused candidates with the cross-encoder.

    Each returned entry gains ``reranker_score`` (min-max normalized to
    ``[0, 1]`` across this candidate set) and ``reranked=True``. On failure the
    input order is preserved and ``reranked=False``, so the caller's contract
    does not change.
    """
    candidates = list(candidates)
    if not candidates or not query.strip():
        return candidates[:top_k]

    settings = get_settings()
    if not settings.retrieval.reranker_enabled:
        return _passthrough(candidates, top_k)

    model = get_reranker(model_name)
    if model is None:
        return _passthrough(candidates, top_k)

    pairs = [(query, _document_text(c.get("metadata", c))) for c in candidates]
    try:
        scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False)
    except Exception as exc:
        logger.warning("Reranking failed (%s); keeping the fused order.", exc)
        return _passthrough(candidates, top_k)

    raw = [float(s) for s in scores]
    lo, hi = min(raw), max(raw)
    span = (hi - lo) or 1.0
    for candidate, score in zip(candidates, raw):
        candidate["reranker_raw"] = score
        candidate["reranker_score"] = (score - lo) / span
        candidate["reranked"] = True

    candidates.sort(key=lambda c: c["reranker_raw"], reverse=True)
    return candidates[:top_k]


def _passthrough(candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """Fused order, with a neutral reranker score so weighting still works."""
    for candidate in candidates:
        candidate.setdefault("reranker_score", 0.5)
        candidate["reranked"] = False
    return candidates[:top_k]
