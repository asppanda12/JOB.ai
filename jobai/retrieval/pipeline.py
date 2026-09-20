"""The retrieval funnel.

    profile / query
          |
    +-----+------+-------------+-------------+
    |            |             |             |
  FAISS        BM25          Graph      (expanded BM25)
    |            |             |             |
    +-----+------+-------------+-------------+
          |
    Reciprocal Rank Fusion  ->  metadata filters  ->  top 50-100
          |
    cross-encoder reranker  ->  top 10-20
          |
    transparent scoring (signals + weights)
          |
    Qwen 7B reasoning  (explanations only, never ranking)

Every arm is optional and every arm fails independently: if Neo4j is down the
graph arm is empty, if the cross-encoder will not load the fused order stands,
if Ollama is down the results come back with rule-based explanations. Only a
missing FAISS index leaves nothing to retrieve.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from jobai.config import get_settings
from jobai.llm.client import LLMError, LLMUnavailable
from jobai.normalize.skills import normalize_skills
from jobai.normalize.text import canonical_profile_text
from jobai.retrieval.dense import DenseIndex
from jobai.retrieval.filters import JobFilter, apply_filter
from jobai.retrieval.fusion import reciprocal_rank_fusion
from jobai.retrieval.graph import JobGraph
from jobai.retrieval.lexical import BM25Index
from jobai.retrieval.rerank import rerank
from jobai.scoring import rank

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    jobs: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.jobs)


class RetrievalPipeline:
    """Hybrid retrieval over the existing FAISS store.

    Construction is lazy: the FAISS index, BM25 corpus and graph are built on
    first use and then reused, so the Telegram bot pays the load cost once.
    """

    def __init__(
        self,
        dense: Optional[DenseIndex] = None,
        lexical: Optional[BM25Index] = None,
        graph: Optional[JobGraph] = None,
        *,
        autoload: bool = True,
    ):
        self.settings = get_settings()
        self.dense = dense or DenseIndex()
        self._lexical = lexical
        self._graph = graph
        self._corpus: Optional[List[Dict[str, Any]]] = None
        if autoload:
            self._ensure_corpus()

    # --------------------------------------------------------------- loading

    def _ensure_corpus(self) -> List[Dict[str, Any]]:
        """The indexed job metadata, read once from the FAISS docstore.

        FAISS is the single source of truth for what is retrievable, so BM25
        and the graph are built from exactly the same documents. That keeps the
        three arms in sync without a second ingestion path.
        """
        if self._corpus is None:
            self._corpus = self.dense.all_metadata()
            logger.info("Retrieval corpus: %d jobs", len(self._corpus))
        return self._corpus

    @property
    def lexical(self) -> BM25Index:
        if self._lexical is None:
            self._lexical = BM25Index().build(self._ensure_corpus())
        return self._lexical

    @property
    def graph(self) -> JobGraph:
        if self._graph is None:
            self._graph = JobGraph(self._ensure_corpus())
        return self._graph

    def refresh(self) -> None:
        """Drop cached indexes so the next query sees a rebuilt FAISS store."""
        self.dense._store = None
        self._corpus = None
        self._lexical = None
        self._graph = None

    # ------------------------------------------------------------- retrieval

    def retrieve(
        self,
        profile: Dict[str, Any],
        *,
        query: Optional[str] = None,
        job_filter: Optional[JobFilter] = None,
        top_k: Optional[int] = None,
        expand: Optional[bool] = None,
        explain_with_llm: bool = False,
    ) -> RetrievalResult:
        settings = self.settings.retrieval
        top_k = top_k or settings.rerank_k
        diagnostics: Dict[str, Any] = {"stages": {}}

        # The query is the profile unless the caller asked something specific.
        base_query = (query or canonical_profile_text(profile) or "").strip()
        if not base_query:
            return RetrievalResult([], {"error": "empty query and empty profile"})

        user_skills = normalize_skills(profile.get("skills") or [])
        rankings: Dict[str, Any] = {}

        # --- arm 1: dense ---------------------------------------------------
        try:
            rankings["dense"] = self.dense.search(base_query, k=settings.dense_k)
        except Exception as exc:
            logger.error("Dense arm failed: %s", exc)
            rankings["dense"] = []
        diagnostics["stages"]["dense"] = len(rankings["dense"])

        # --- arm 2: lexical (exact tokens: PyTorch, C++, LangGraph, ...) -----
        try:
            lexical_query = " ".join(filter(None, [base_query, " ".join(user_skills)]))
            rankings["lexical"] = self.lexical.search(lexical_query, k=settings.lexical_k)
        except Exception as exc:
            logger.error("Lexical arm failed: %s", exc)
            rankings["lexical"] = []
        diagnostics["stages"]["lexical"] = len(rankings["lexical"])

        # --- arm 3: graph ---------------------------------------------------
        if settings.graph_enabled and user_skills:
            try:
                rankings["graph"] = self.graph.search(user_skills, k=settings.graph_k)
                diagnostics["graph_backend"] = "neo4j" if self.graph.using_neo4j else "in-memory"
            except Exception as exc:
                logger.warning("Graph arm failed (%s); continuing without it.", exc)
                rankings["graph"] = []
        else:
            rankings["graph"] = []
        diagnostics["stages"]["graph"] = len(rankings["graph"])

        # --- arm 4: query expansion (weakest voice, original always kept) ----
        want_expansion = settings.query_expansion_enabled if expand is None else expand
        if want_expansion and query:
            expansion = self._expand(query)
            diagnostics["expansion"] = expansion
            terms = expansion.get("expansions", []) + expansion.get("role_titles", [])
            if terms:
                try:
                    # Expansion rides on its own arm rather than being mixed
                    # into the literal query, so it can add recall but cannot
                    # dilute an exact match.
                    rankings["expanded"] = self.lexical.search(
                        f"{query} {' '.join(terms)}", k=settings.lexical_k
                    )
                except Exception as exc:
                    logger.debug("Expanded arm failed: %s", exc)
        diagnostics["stages"]["expanded"] = len(rankings.get("expanded", []))

        # --- rank fusion ----------------------------------------------------
        fused = reciprocal_rank_fusion(rankings, k=settings.rrf_k)
        diagnostics["stages"]["fused"] = len(fused)

        # --- metadata filtering ---------------------------------------------
        filtered, relaxed = apply_filter(fused, job_filter)
        diagnostics["filter_relaxed"] = relaxed
        diagnostics["stages"]["filtered"] = len(filtered)

        candidates = filtered[: settings.fusion_k]
        diagnostics["stages"]["candidates"] = len(candidates)

        # --- cross-encoder rerank -------------------------------------------
        reranked = rerank(base_query, candidates, top_k=max(top_k, settings.rerank_k))
        diagnostics["reranked"] = bool(reranked and reranked[0].get("reranked"))
        diagnostics["stages"]["reranked"] = len(reranked)

        # --- transparent scoring ---------------------------------------------
        scored = rank(reranked, profile)[:top_k]
        diagnostics["stages"]["final"] = len(scored)

        # Graph-sourced skill gaps are more accurate than the scorer's guess.
        if settings.graph_enabled and user_skills:
            for item in scored:
                try:
                    gap = self.graph.missing_skills(user_skills, item["job_id"])
                except Exception:
                    gap = []
                if gap:
                    item["missing_skills"] = gap[:8]

        # --- Qwen reasoning, last and only on the survivors -------------------
        if explain_with_llm and scored:
            self._attach_llm_reasoning(profile, scored, diagnostics)

        return RetrievalResult(scored, diagnostics)

    # ------------------------------------------------------------- internals

    def _expand(self, query: str) -> Dict[str, Any]:
        from jobai.llm.tasks import expand_query

        try:
            return expand_query(query)
        except (LLMError, LLMUnavailable) as exc:
            logger.debug("Query expansion unavailable: %s", exc)
            return {"original": query, "expansions": [], "role_titles": []}

    def _attach_llm_reasoning(
        self, profile: Dict[str, Any], scored: List[Dict[str, Any]], diagnostics: Dict[str, Any]
    ) -> None:
        from jobai.llm.tasks import explain_matches

        payload = [
            {"job_id": item["job_id"], "job": item.get("metadata", {}),
             "signals": item.get("signals", {}),
             "matched_skills": item.get("matched_skills", []),
             "missing_skills": item.get("missing_skills", [])}
            for item in scored
        ]
        try:
            reasoning = explain_matches(profile, payload)
        except (LLMError, LLMUnavailable) as exc:
            diagnostics["llm_reasoning"] = f"unavailable: {exc}"
            return
        by_id = {str(r.get("job_id")): r for r in reasoning.get("recommendations", [])}
        for item in scored:
            match = by_id.get(str(item["job_id"]))
            if match:
                item["llm_verdict"] = match.get("verdict", "")
                item["llm_reasons"] = match.get("reasons", [])
                item["how_to_prepare"] = match.get("how_to_prepare", "")
                if match.get("missing_skills"):
                    item.setdefault("missing_skills", match["missing_skills"])
        diagnostics["llm_reasoning"] = "ok"


_pipeline: Optional[RetrievalPipeline] = None


def get_pipeline(refresh: bool = False) -> RetrievalPipeline:
    """Shared pipeline so the FAISS index and models load once per process."""
    global _pipeline
    if _pipeline is None or refresh:
        _pipeline = RetrievalPipeline()
    return _pipeline
