"""Multi-level job deduplication.

The same posting reaches us from LinkedIn, Naukri and a company careers page
with different titles, different URLs and different formatting.  We collapse
those into one canonical job that *remembers* every source it came from,
rather than dropping the extras, so a user can apply wherever they prefer.

The levels run cheapest-first and each is strictly more permissive than the
last:

1. ``(source, source_job_id)``  - the same posting re-scraped from one source.
2. canonical URL               - the same posting linked from two places.
3. content hash                - byte-identical meaningful content.
4. company + title + location  - the same role listed twice with cosmetic diffs.
5. semantic similarity         - optional; only applied *within* a company, and
                                 only above a high threshold.

Level 5 is the one that can merge genuinely different jobs, so it is gated on a
same-company check and a conservative default threshold, and it is skipped
entirely when no embedder is supplied.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from jobai.schema import Job, url_dedup_key

logger = logging.getLogger(__name__)

DEFAULT_SEMANTIC_THRESHOLD = 0.94

_TITLE_NOISE = re.compile(
    r"\b(urgent(ly)?|hiring|immediate joiner|walk[- ]?in|remote|work from home|wfh|"
    r"full[- ]?time|part[- ]?time|contract|permanent|fresher|experienced|"
    r"apply now|job|opening|openings|vacancy|opportunity)\b",
    re.IGNORECASE,
)
_COMPANY_NOISE = re.compile(
    r"\b(pvt|private|ltd|limited|inc|incorporated|llc|llp|technologies|technology|"
    r"solutions|services|systems|labs|software|india|global|group|corp|corporation)\b",
    re.IGNORECASE,
)


def _fold(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def title_key(title: str) -> str:
    """Title stripped of recruiter noise and seniority punctuation."""
    cleaned = _TITLE_NOISE.sub(" ", title or "")
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    return re.sub(r"\s+", " ", _fold(cleaned)).strip()


def company_key(company: str) -> str:
    """Company name stripped of legal suffixes and boilerplate."""
    cleaned = _COMPANY_NOISE.sub(" ", company or "")
    return re.sub(r"\s+", " ", _fold(cleaned)).strip()


def location_key(location: str) -> str:
    """First city token only: "Bengaluru, Karnataka, India" -> "bengaluru"."""
    primary = re.split(r"[,/|]", location or "")[0]
    return re.sub(r"\s+", " ", _fold(primary)).strip()


def _merge(primary: Job, duplicate: Job) -> Job:
    """Fold ``duplicate`` into ``primary``, keeping the richer field each time."""
    for entry in duplicate.sources or []:
        if entry not in primary.sources:
            primary.sources.append(entry)

    if len(duplicate.description or "") > len(primary.description or ""):
        primary.description = duplicate.description
        primary.raw_text = duplicate.raw_text or primary.raw_text

    for field in ("skills", "required_skills", "preferred_skills", "education"):
        merged = list(dict.fromkeys(getattr(primary, field) + getattr(duplicate, field)))
        setattr(primary, field, merged)

    for field in ("salary", "employment_type", "industry", "job_category", "company_url", "experience_raw"):
        if not getattr(primary, field) and getattr(duplicate, field):
            setattr(primary, field, getattr(duplicate, field))

    if primary.remote is None and duplicate.remote is not None:
        primary.remote = duplicate.remote
    if primary.experience_min is None and duplicate.experience_min is not None:
        primary.experience_min = duplicate.experience_min
        primary.experience_max = duplicate.experience_max

    # Keep the earliest known posting date: it is the truthful one.
    if duplicate.posted_date and (not primary.posted_date or duplicate.posted_date < primary.posted_date):
        primary.posted_date = duplicate.posted_date

    primary.normalized_text = ""
    return primary.finalize()


def deduplicate(
    jobs: Iterable[Job],
    *,
    embedder: Optional[Callable[[Sequence[str]], Sequence[Sequence[float]]]] = None,
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> Tuple[List[Job], Dict[str, int]]:
    """Collapse duplicates. Returns the canonical jobs and per-level counts."""
    stats = {"input": 0, "source_id": 0, "url": 0, "content_hash": 0, "company_title": 0, "semantic": 0}

    by_source_id: Dict[Tuple[str, str], Job] = {}
    by_url: Dict[str, Job] = {}
    by_hash: Dict[str, Job] = {}
    by_company_title: Dict[Tuple[str, str, str], Job] = {}
    canonical: List[Job] = []

    for job in jobs:
        stats["input"] += 1
        job = job.finalize()

        # Level 1: the source's own id.
        sid = (job.source.lower(), str(job.source_job_id)) if job.source_job_id else None
        if sid and sid in by_source_id:
            _merge(by_source_id[sid], job)
            stats["source_id"] += 1
            continue

        # Level 2: canonical URL, host-folded so country subdomains collapse.
        url = url_dedup_key(job.canonical_application_url())
        if url and url in by_url:
            _merge(by_url[url], job)
            stats["url"] += 1
            continue

        # Level 3: identical meaningful content.
        if job.content_hash in by_hash:
            _merge(by_hash[job.content_hash], job)
            stats["content_hash"] += 1
            continue

        # Level 4: same company + title + city.
        ck = (company_key(job.company), title_key(job.title), location_key(job.location))
        if all(ck) and ck in by_company_title:
            _merge(by_company_title[ck], job)
            stats["company_title"] += 1
            continue

        canonical.append(job)
        if sid:
            by_source_id[sid] = job
        if url:
            by_url[url] = job
        by_hash[job.content_hash] = job
        if all(ck):
            by_company_title[ck] = job

    if embedder is not None and len(canonical) > 1:
        canonical, semantic_merged = _semantic_pass(canonical, embedder, semantic_threshold)
        stats["semantic"] = semantic_merged

    stats["output"] = len(canonical)
    logger.info("Deduplication: %s", stats)
    return canonical, stats


def _semantic_pass(
    jobs: List[Job],
    embedder: Callable[[Sequence[str]], Sequence[Sequence[float]]],
    threshold: float,
) -> Tuple[List[Job], int]:
    """Near-duplicate merge, restricted to jobs at the same company.

    Restricting by company is what keeps this from merging "Backend Engineer at
    A" with "Backend Engineer at B", which are genuinely different jobs however
    similar their text.
    """
    import numpy as np

    buckets: Dict[str, List[int]] = defaultdict(list)
    for idx, job in enumerate(jobs):
        key = company_key(job.company)
        if key:
            buckets[key].append(idx)

    dropped: set[int] = set()
    merged = 0
    for indices in buckets.values():
        if len(indices) < 2:
            continue
        texts = [jobs[i].normalized_text[:2000] for i in indices]
        try:
            vectors = np.asarray(embedder(texts), dtype="float32")
        except Exception as exc:  # embedding is an optimisation, never a hard dep
            logger.warning("Semantic dedup skipped for one bucket: %s", exc)
            continue
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors = vectors / norms
        similarity = vectors @ vectors.T
        for a in range(len(indices)):
            if indices[a] in dropped:
                continue
            for b in range(a + 1, len(indices)):
                if indices[b] in dropped:
                    continue
                if float(similarity[a, b]) >= threshold:
                    _merge(jobs[indices[a]], jobs[indices[b]])
                    dropped.add(indices[b])
                    merged += 1

    return [job for i, job in enumerate(jobs) if i not in dropped], merged
