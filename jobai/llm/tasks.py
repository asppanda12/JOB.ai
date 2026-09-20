"""Every LLM-backed feature, expressed once, on top of the single Ollama client.

Each task degrades rather than crashes: if Ollama is down, extraction tasks
fall back to the deterministic normalizers and generation tasks raise
:class:`LLMUnavailable` with an actionable message for the UI to show.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from jobai.llm import prompts
from jobai.llm.client import LLMError, LLMUnavailable, get_llm
from jobai.normalize.experience import parse_experience
from jobai.normalize.skills import extract_skills_from_text, normalize_skills

logger = logging.getLogger(__name__)

_PROFILE_KEYS = {
    "name": None,
    "email": None,
    "phone": None,
    "target_roles": list,
    "skills": list,
    "languages": list,
    "frameworks": list,
    "cloud": list,
    "databases": list,
    "years_experience": None,
    "industries": list,
    "preferred_locations": list,
    "remote_preference": None,
    "education": list,
    "projects": list,
    "experience": list,
}


def _coerce_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """Guarantee the full profile shape regardless of what the model returned."""
    out: Dict[str, Any] = {}
    for key, kind in _PROFILE_KEYS.items():
        value = data.get(key)
        if kind is list:
            out[key] = value if isinstance(value, list) else ([] if value in (None, "") else [value])
        else:
            out[key] = value
    for key in ("skills", "languages", "frameworks", "cloud", "databases"):
        out[key] = normalize_skills(out[key])
    # Every language/framework/cloud/database is also a skill.
    out["skills"] = normalize_skills(
        out["skills"] + out["languages"] + out["frameworks"] + out["cloud"] + out["databases"]
    )
    try:
        out["years_experience"] = float(out.get("years_experience") or 0)
    except (TypeError, ValueError):
        out["years_experience"] = 0.0
    out["target_roles"] = [str(r).strip() for r in out["target_roles"] if str(r).strip()]
    return out


def parse_resume(resume_text: str) -> Dict[str, Any]:
    """Resume text -> structured profile.

    Falls back to deterministic skill extraction when the LLM is unavailable so
    registration never dead-ends on a stopped Ollama.
    """
    if not resume_text or not resume_text.strip():
        raise ValueError("resume text is empty")
    try:
        data = get_llm().json(
            prompts.RESUME_PROFILE.format(resume_text=resume_text[:24000]),
            system=prompts.SYSTEM_EXTRACTOR,
            max_tokens=2600,
        )
    except (LLMError, LLMUnavailable) as exc:
        logger.warning("Resume parsing fell back to rule-based extraction: %s", exc)
        return _coerce_profile(
            {
                "skills": extract_skills_from_text(resume_text),
                "years_experience": 0,
                "_degraded": True,
            }
        )
    if not isinstance(data, dict):
        raise LLMError("resume parser did not return a JSON object")
    profile = _coerce_profile(data)
    # The model sometimes misses skills that are plainly in the text.
    profile["skills"] = normalize_skills(profile["skills"] + extract_skills_from_text(resume_text))
    return profile


def understand_job(job_text: str) -> Dict[str, Any]:
    """Job posting -> required/preferred skills, category, experience band.

    Rule-based extraction runs first and the LLM only adds to it, so ingestion
    keeps working (with slightly coarser data) when Ollama is down.
    """
    baseline = {
        "required_skills": extract_skills_from_text(job_text),
        "preferred_skills": [],
        "job_category": "",
        "industry": None,
        "employment_type": None,
        "remote": None,
        "education": [],
        "experience_min_years": None,
        "experience_max_years": None,
    }
    lo, hi = parse_experience(job_text[:600])
    baseline["experience_min_years"], baseline["experience_max_years"] = lo, hi
    if not job_text or not job_text.strip():
        return baseline
    try:
        data = get_llm().json(
            prompts.JOB_UNDERSTANDING.format(job_text=job_text[:12000]),
            system=prompts.SYSTEM_EXTRACTOR,
            max_tokens=900,
            default={},
        )
    except (LLMError, LLMUnavailable) as exc:
        logger.debug("Job understanding fell back to rules: %s", exc)
        return baseline
    if not isinstance(data, dict):
        return baseline
    merged = dict(baseline)
    merged["required_skills"] = normalize_skills(
        list(data.get("required_skills") or []) + baseline["required_skills"]
    )
    merged["preferred_skills"] = normalize_skills(data.get("preferred_skills") or [])
    for key in ("job_category", "industry", "employment_type", "remote"):
        if data.get(key) not in (None, ""):
            merged[key] = data[key]
    if data.get("education"):
        merged["education"] = [str(e) for e in data["education"]]
    for src, dst in (("experience_min_years", "experience_min_years"), ("experience_max_years", "experience_max_years")):
        value = data.get(src)
        if isinstance(value, (int, float)):
            merged[dst] = float(value)
    return merged


def expand_query(query: str) -> Dict[str, List[str]]:
    """Widen a natural-language search into related tech and role titles.

    The original query is always preserved by the caller; expansions only ever
    contribute an *additional* lexical retrieval arm, so a bad expansion cannot
    displace literal matches (see ``jobai.retrieval.pipeline``).
    """
    empty = {"original": query, "expansions": [], "role_titles": []}
    if not query or not query.strip():
        return empty
    try:
        data = get_llm().json(
            prompts.QUERY_EXPANSION.format(query=query[:500]),
            system=prompts.SYSTEM_EXTRACTOR,
            max_tokens=400,
            default={},
        )
    except (LLMError, LLMUnavailable) as exc:
        logger.debug("Query expansion unavailable, using the literal query: %s", exc)
        return empty
    if not isinstance(data, dict):
        return empty
    return {
        "original": query,
        "expansions": normalize_skills(data.get("expansions") or [])[:12],
        "role_titles": [str(r).strip() for r in (data.get("role_titles") or [])][:5],
    }


def explain_matches(profile: Dict[str, Any], scored_jobs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Final reasoning pass over the already-ranked top 10-20.

    This is the only place the LLM sees jobs, and it sees at most a couple of
    dozen — retrieval, fusion and the cross-encoder have already done the
    ranking. The LLM explains; it does not rank.
    """
    if not scored_jobs:
        return {"recommendations": []}
    compact = []
    for item in scored_jobs:
        job = item.get("job", {})
        compact.append(
            {
                "job_id": item.get("job_id") or job.get("job_id"),
                "title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "experience": job.get("experience_raw"),
                "required_skills": (job.get("required_skills") or job.get("skills") or [])[:15],
                "signals": item.get("signals", {}),
                "matched_skills": item.get("matched_skills", []),
                "missing_skills": item.get("missing_skills", []),
            }
        )
    slim_profile = {
        "target_roles": profile.get("target_roles"),
        "skills": (profile.get("skills") or [])[:40],
        "years_experience": profile.get("years_experience"),
        "preferred_locations": profile.get("preferred_locations"),
    }
    data = get_llm().json(
        prompts.MATCH_REASONING.format(
            profile=json.dumps(slim_profile, ensure_ascii=False, default=str),
            jobs=json.dumps(compact, ensure_ascii=False, default=str),
        ),
        system=prompts.SYSTEM_WRITER,
        max_tokens=2400,
        default={"recommendations": []},
    )
    return data if isinstance(data, dict) else {"recommendations": []}


def skill_gap(user_skills: Sequence[str], job_skills: Sequence[str]) -> Dict[str, Any]:
    """Explain the gap between what the candidate has and what jobs ask for."""
    have = normalize_skills(user_skills)
    want = normalize_skills(job_skills)
    deterministic = [s for s in want if s not in set(have)]
    default = {
        "missing_critical": deterministic[:10],
        "missing_nice_to_have": deterministic[10:20],
        "transferable": [],
        "advice": "",
    }
    try:
        data = get_llm().json(
            prompts.SKILL_GAP.format(user_skills=", ".join(have), job_skills=", ".join(want)),
            system=prompts.SYSTEM_EXTRACTOR,
            max_tokens=700,
            default=default,
        )
    except (LLMError, LLMUnavailable):
        return default
    return data if isinstance(data, dict) else default


def _write(template: str, profile: Dict[str, Any], job: Dict[str, Any], max_tokens: int) -> str:
    # default=str because a job read back from MongoDB carries a real
    # ``datetime`` in Posted_date, and an ObjectId in _id, neither of which
    # json.dumps can encode.
    return get_llm().complete(
        template.format(
            profile=json.dumps(profile, ensure_ascii=False, default=str)[:8000],
            job=json.dumps(_writable(job), ensure_ascii=False, default=str)[:6000],
        ),
        system=prompts.SYSTEM_WRITER,
        temperature=0.6,
        max_tokens=max_tokens,
    ).strip()


# Fields that only add noise to a writing prompt, or that cannot be serialised.
_WRITE_EXCLUDED = {"_id", "text", "normalized_text", "raw_text", "content_hash", "page_content"}


def _writable(job: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a stored job down to what a writing prompt actually needs."""
    source = job.get("metadata", job)
    return {k: v for k, v in source.items() if k not in _WRITE_EXCLUDED}


def write_cover_letter(profile: Dict[str, Any], job: Dict[str, Any]) -> str:
    return _write(prompts.COVER_LETTER, profile, job, 1300)


def write_referral_message(profile: Dict[str, Any], job: Dict[str, Any]) -> str:
    return _write(prompts.REFERRAL_MESSAGE, profile, job, 500)


def write_cold_email(profile: Dict[str, Any], job: Dict[str, Any]) -> str:
    return _write(prompts.COLD_EMAIL, profile, job, 1300)
