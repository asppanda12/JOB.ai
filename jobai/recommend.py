"""The recommendation service.

One place that owns "given a user, produce ranked jobs with explanations".
The Telegram bot, the CLI and any future interface call this; none of them
carry their own copy of the retrieval logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from jobai.config import get_settings
from jobai.llm.client import LLMError, LLMUnavailable
from jobai.profile import profile_for_user
from jobai.retrieval.filters import JobFilter
from jobai.retrieval.pipeline import RetrievalPipeline, get_pipeline
from jobai.store import get_store

logger = logging.getLogger(__name__)


def filter_for_profile(profile: Dict[str, Any], **overrides: Any) -> JobFilter:
    """Default metadata filter implied by a user's profile."""
    job_filter = JobFilter(
        experience_years=profile.get("years_experience"),
        locations=list(profile.get("preferred_locations") or []),
    )
    if profile.get("remote_preference") == "remote":
        job_filter.remote = True
    for key, value in overrides.items():
        if hasattr(job_filter, key) and value is not None:
            setattr(job_filter, key, value)
    return job_filter


def recommend_for_profile(
    profile: Dict[str, Any],
    *,
    query: Optional[str] = None,
    top_k: Optional[int] = None,
    job_filter: Optional[JobFilter] = None,
    explain: bool = True,
    pipeline: Optional[RetrievalPipeline] = None,
) -> Dict[str, Any]:
    """Run the full funnel for one profile."""
    pipeline = pipeline or get_pipeline()
    job_filter = job_filter if job_filter is not None else filter_for_profile(profile)
    result = pipeline.retrieve(
        profile,
        query=query,
        job_filter=job_filter,
        top_k=top_k,
        explain_with_llm=explain,
    )
    return {"jobs": result.jobs, "diagnostics": result.diagnostics}


def recommend_for_user(
    chat_id: Any,
    *,
    query: Optional[str] = None,
    top_k: Optional[int] = None,
    explain: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """Recommend for a registered user and persist the result for pagination.

    The stored shape is the legacy one - a list of ``{"page_content", "metadata"}``
    entries under ``job_recommendation`` - so the existing Telegram pagination
    and the Referral/Cover Letter/Cold Email buttons keep working unchanged.
    The new signals ride along on each entry.
    """
    store = get_store()
    store.require()
    user = store.get_user(chat_id)
    if not user:
        raise LookupError(f"No registered user with chat_id={chat_id}")

    profile = profile_for_user(user)
    outcome = recommend_for_profile(profile, query=query, top_k=top_k, explain=explain)

    if persist:
        store.save_recommendations(chat_id, [to_legacy_entry(job) for job in outcome["jobs"]])
        try:
            get_pipeline().graph.upsert_user(chat_id, profile.get("skills") or [])
        except Exception as exc:
            logger.debug("Graph user upsert skipped: %s", exc)

    outcome["profile"] = profile
    return outcome


def to_legacy_entry(scored: Dict[str, Any]) -> Dict[str, Any]:
    """Convert one scored candidate into the persisted recommendation shape."""
    metadata = dict(scored.get("metadata", {}))
    metadata.setdefault("job_indx", metadata.get("job_indx", 0))
    return {
        "page_content": metadata.get("text", ""),
        "metadata": metadata,
        # New, additive fields. Legacy readers ignore them.
        "job_id": scored.get("job_id"),
        "match_score": scored.get("match_score"),
        "signals": scored.get("signals", {}),
        "explanation": scored.get("explanation", []),
        "matched_skills": scored.get("matched_skills", []),
        "missing_skills": scored.get("missing_skills", []),
        "llm_verdict": scored.get("llm_verdict", ""),
        "llm_reasons": scored.get("llm_reasons", []),
        "how_to_prepare": scored.get("how_to_prepare", ""),
    }


def generate_document(chat_id: Any, job_indx: Any, kind: str) -> str:
    """Produce a cover letter, referral message or cold email for one job.

    ``kind`` is one of ``cover_letter``, ``referral``, ``cold_email``.
    """
    from jobai.llm import tasks

    writers = {
        "cover_letter": tasks.write_cover_letter,
        "referral": tasks.write_referral_message,
        "cold_email": tasks.write_cold_email,
    }
    if kind not in writers:
        raise ValueError(f"unknown document kind {kind!r}; expected one of {sorted(writers)}")

    store = get_store()
    user = store.get_user(chat_id)
    if not user:
        raise LookupError(f"No registered user with chat_id={chat_id}")
    entry = store.find_recommendation(chat_id, job_indx)
    if not entry:
        raise LookupError(f"No recommended job {job_indx!r} for chat_id={chat_id}")

    profile = profile_for_user(user)
    job = entry.get("metadata", entry)
    return writers[kind](profile, job)


def skill_gap_for_user(chat_id: Any, top_n: int = 20) -> Dict[str, Any]:
    """Aggregate skill gap across a user's current recommendations."""
    from jobai.llm.tasks import skill_gap
    from jobai.normalize.skills import skills_from_metadata

    store = get_store()
    user = store.get_user(chat_id)
    if not user:
        raise LookupError(f"No registered user with chat_id={chat_id}")
    profile = profile_for_user(user)

    wanted: List[str] = []
    for entry in store.get_recommendations(chat_id)[:top_n]:
        wanted.extend(skills_from_metadata(entry.get("metadata", entry)))
    return skill_gap(profile.get("skills") or [], wanted)
