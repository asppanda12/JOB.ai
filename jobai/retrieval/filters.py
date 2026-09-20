"""Structured metadata filtering.

Applied *after* fusion rather than before it so that a filter which matches
nothing can be relaxed and reported, instead of silently returning an empty
recommendation list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from jobai.normalize.skills import normalize_skills, skills_from_metadata
from jobai.schema import _parse_date, _split_band


@dataclass
class JobFilter:
    """All filters are optional; an unset field never excludes anything."""

    locations: List[str] = field(default_factory=list)
    remote: Optional[bool] = None
    experience_years: Optional[float] = None
    min_salary: Optional[float] = None
    roles: List[str] = field(default_factory=list)
    companies: List[str] = field(default_factory=list)
    exclude_companies: List[str] = field(default_factory=list)
    employment_types: List[str] = field(default_factory=list)
    posted_within_days: Optional[int] = None
    required_skills: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            [
                self.locations, self.remote is not None, self.experience_years is not None,
                self.min_salary is not None, self.roles, self.companies, self.exclude_companies,
                self.employment_types, self.posted_within_days is not None,
                self.required_skills, self.sources,
            ]
        )

    def matches(self, metadata: Dict[str, Any]) -> bool:
        if self.locations and not _any_contains(metadata.get("location"), self.locations):
            return False

        if self.remote is not None:
            value = metadata.get("remote")
            if value is None:
                # Fall back to a text sniff rather than dropping the job.
                blob = f"{metadata.get('location', '')} {metadata.get('text', '')}".lower()
                value = bool(re.search(r"\bremote\b|work from home|\bwfh\b", blob))
            if bool(value) != self.remote:
                return False

        if self.experience_years is not None:
            lo, hi = _band(metadata)
            if lo is not None and hi is not None and not (lo <= self.experience_years <= hi):
                return False

        if self.min_salary is not None:
            salary = _salary_lpa(metadata.get("salary"))
            if salary is not None and salary < self.min_salary:
                return False

        if self.roles:
            haystack = f"{metadata.get('job_title', '')} {metadata.get('job_category') or metadata.get('job_type', '')}"
            if not _any_contains(haystack, self.roles):
                return False

        company = str(metadata.get("company_name") or metadata.get("company") or "")
        if self.companies and not _any_contains(company, self.companies):
            return False
        if self.exclude_companies and _any_contains(company, self.exclude_companies):
            return False

        if self.employment_types and not _any_contains(metadata.get("employment_type"), self.employment_types):
            return False

        if self.sources and str(metadata.get("Source") or metadata.get("source") or "").lower() not in {
            s.lower() for s in self.sources
        }:
            return False

        if self.posted_within_days is not None:
            posted = _parse_date(metadata.get("Posted_date") or metadata.get("posted_date"))
            if posted is not None:
                cutoff = datetime.now(timezone.utc) - timedelta(days=self.posted_within_days)
                if posted < cutoff:
                    return False

        if self.required_skills:
            job_skills = {s.lower() for s in _skills(metadata)}
            if not all(s.lower() in job_skills for s in normalize_skills(self.required_skills)):
                return False

        return True


def apply_filter(
    candidates: Sequence[Dict[str, Any]],
    job_filter: Optional[JobFilter],
    *,
    min_results: int = 10,
) -> tuple[List[Dict[str, Any]], bool]:
    """Filter candidates, relaxing to the unfiltered list if too few survive.

    Returns ``(results, relaxed)`` so the caller can tell the user their filter
    was too narrow rather than just showing them nothing.
    """
    if job_filter is None or job_filter.is_empty():
        return list(candidates), False
    kept = [c for c in candidates if job_filter.matches(c.get("metadata", c))]
    if len(kept) < min_results and len(candidates) > len(kept):
        return list(candidates), True
    return kept, False


def _skills(metadata: Dict[str, Any]) -> List[str]:
    return skills_from_metadata(metadata)


def _band(metadata: Dict[str, Any]):
    lo, hi = metadata.get("experience_min"), metadata.get("experience_max")
    if lo is not None or hi is not None:
        return lo, hi
    return _split_band(metadata.get("yoe"))


def _any_contains(haystack: Any, needles: Sequence[str]) -> bool:
    text = str(haystack or "").lower()
    if not text:
        return False
    return any(str(n).lower().strip() in text for n in needles if str(n).strip())


_SALARY = re.compile(r"(\d+(?:\.\d+)?)\s*(?:lpa|lakh|lac|l\b)", re.IGNORECASE)


def _salary_lpa(value: Any) -> Optional[float]:
    """Best-effort salary in LPA. Returns None when unparseable (never filters)."""
    if value is None:
        return None
    matches = _SALARY.findall(str(value))
    if not matches:
        return None
    try:
        return min(float(m) for m in matches)
    except ValueError:
        return None
