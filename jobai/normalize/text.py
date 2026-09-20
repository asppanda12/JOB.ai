"""The canonical text representation that gets embedded.

Stability is the whole point.  The legacy pipeline embedded
``f"{title} {company} {description} {location}"`` assembled inline in each
cleaning script, so the three scripts disagreed and re-running a cleaner could
change a job's vector without its content changing.  One function owns it now,
and :meth:`Job.compute_content_hash` decides when a re-embed is actually due.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:  # pragma: no cover
    from jobai.schema import Job

_MAX_DESCRIPTION_CHARS = 4000


# Non-breaking and other exotic spaces; see jobai.ingest.ats.strip_html.
_UNICODE_SPACE = re.compile(r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000\u200b\ufeff]")


def _clean(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = _UNICODE_SPACE.sub(" ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def canonical_job_text(job: "Job") -> str:
    """Deterministic, labelled representation of a job.

    Labelled sections (rather than a bare concatenation) keep the embedding
    from confusing a company called "Python" with the language, and give BM25
    the same tokens the dense model sees.
    """
    lines = [
        f"Job Title: {_clean(job.title)}",
        f"Company: {_clean(job.company)}",
    ]
    if job.job_category:
        lines.append(f"Role Category: {_clean(job.job_category)}")
    if job.industry:
        lines.append(f"Industry: {_clean(job.industry)}")
    if job.required_skills:
        lines.append(f"Required Skills: {', '.join(job.required_skills)}")
    if job.preferred_skills:
        lines.append(f"Preferred Skills: {', '.join(job.preferred_skills)}")
    if job.skills:
        lines.append(f"Skills: {', '.join(job.skills)}")
    band = job.experience_band()
    lines.append(f"Experience: {band.replace(',', ' to ')} years")
    if job.location:
        lines.append(f"Location: {_clean(job.location)}")
    if job.remote is not None:
        lines.append(f"Remote: {'yes' if job.remote else 'no'}")
    if job.employment_type:
        lines.append(f"Employment Type: {_clean(job.employment_type)}")
    description = _clean(job.description)
    if description:
        lines.append(f"Description: {description[:_MAX_DESCRIPTION_CHARS]}")
    return "\n".join(lines)


def canonical_profile_text(profile: Dict[str, Any]) -> str:
    """The retrieval query built from a structured user profile."""
    parts = []
    roles = profile.get("target_roles") or []
    if roles:
        parts.append(f"Target Roles: {', '.join(map(str, roles))}")
    for key, label in (
        ("skills", "Skills"),
        ("languages", "Languages"),
        ("frameworks", "Frameworks"),
        ("cloud", "Cloud"),
        ("databases", "Databases"),
    ):
        values = profile.get(key) or []
        if values:
            parts.append(f"{label}: {', '.join(map(str, values))}")
    years = profile.get("years_experience")
    if years is not None:
        parts.append(f"Experience: {years} years")
    industries = profile.get("industries") or []
    if industries:
        parts.append(f"Industries: {', '.join(map(str, industries))}")
    locations = profile.get("preferred_locations") or []
    if locations:
        parts.append(f"Location: {', '.join(map(str, locations))}")
    if profile.get("remote_preference"):
        parts.append(f"Remote: {profile['remote_preference']}")
    return "\n".join(parts)
