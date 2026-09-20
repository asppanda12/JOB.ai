"""Adapters for the pre-existing sources.

Cuvette, Instahyre and Wellfound already had working scrapers whose output sits
in JSON files under the source folders. Rather than rewrite them, this module
adapts whatever they produced into the canonical :class:`Job`, so those sources
keep contributing to retrieval with no change to their own code.

``LegacyMongoSource`` does the same for jobs already in ``USER_1.JOB_Data``:
it is what lets the 3,298 jobs in the committed FAISS index be re-normalized
into the canonical schema without re-scraping anything.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from jobai.config import PROJECT_ROOT
from jobai.ingest.base import JobSource
from jobai.normalize.experience import parse_experience
from jobai.normalize.skills import extract_skills_from_text, normalize_skills, parse_skill_blob
from jobai.schema import Job, _parse_date, canonical_url

logger = logging.getLogger(__name__)

# Where each legacy scraper writes. Missing files are skipped, not an error.
LEGACY_FILES: Dict[str, List[str]] = {
    "cuvette": ["cuvete/cuevete_parsed_jobs.json", "cleaned/cleaned_cuvete.json"],
    "instahyre": [
        "cleaned/instahyre_jobs.json", "cleaned/instahyre_jobs_1.json",
        "cleaned/instahyre_jobs_2.json", "cleaned/instahyre_jobs_3.json",
    ],
    "linkedin_archive": ["Linkedin/linkedin_parsed_jobs.json", "cleaned/linkedin.json"],
    "naukri_archive": ["naukri/naukri_parsed_jobs.json", "cleaned/naukri.json"],
    "wellfound": ["wellfound/wellfound_jobs.json"],
}


def job_from_legacy_record(record: Dict[str, Any], source: str) -> Optional[Job]:
    """Map one legacy record onto the canonical schema.

    Handles every key spelling the old scripts produced: the raw scraper output
    (``Job Title``, ``Company Name``), the LLM-parsed output (``job_title``,
    ``company_name``) and the cleaned output that added ``yoe``/``Source``.
    """
    def pick(*names: str, default: Any = "") -> Any:
        for name in names:
            value = record.get(name)
            if value not in (None, "", [], "N/A"):
                return value
        return default

    title = str(pick("job_title", "Job Title", "title", "Title")).strip()
    if not title:
        return None

    url = str(pick("job_link", "Job Link", "link", "url", "apply_link"))
    description = str(pick("job_description", "Job Description", "description", "desc"))
    raw_skills = pick("skills", "Skills", "skill", default=[])
    if isinstance(raw_skills, str):
        skills = parse_skill_blob(raw_skills)
    else:
        skills = normalize_skills(raw_skills)
    if not skills and description:
        skills = extract_skills_from_text(f"{title}\n{description}")

    experience_raw = str(pick("experience", "Experience", "years_of_experience", default=""))
    experience_min, experience_max = parse_experience(experience_raw)
    if experience_min is None:
        band = record.get("yoe")
        if isinstance(band, (list, tuple)) and len(band) == 2:
            try:
                experience_min, experience_max = float(band[0]), float(band[1])
            except (TypeError, ValueError):
                pass
        elif isinstance(band, str) and "," in band:
            lo, _, hi = band.partition(",")
            try:
                experience_min, experience_max = float(lo), float(hi)
            except ValueError:
                pass

    return Job(
        title=title,
        company=str(pick("company_name", "Company Name", "company", default="")).strip(),
        description=description,
        source=str(pick("Source", "source", default=source)).strip().lower() or source,
        source_job_id=str(pick("source_job_id", "job_id", default="")),
        source_url=canonical_url(url),
        application_url=canonical_url(url),
        skills=skills,
        experience_min=experience_min,
        experience_max=experience_max,
        experience_raw=experience_raw,
        location=str(pick("location", "Location", default="")).strip(),
        salary=str(pick("salary", "Salary", default="")),
        employment_type=str(pick("employment_type", "job_type_raw", default="")),
        job_category=str(pick("job_type", "Job Type", "job_category", default="")),
        posted_date=_parse_date(pick("Posted_date", "posted_date", "date", default=None)),
        raw_text=str(pick("text", default=description)),
    )


class LegacyFileSource(JobSource):
    """Reads a previous scraper's JSON output from disk."""

    def __init__(self, name: str, paths: Optional[Sequence[str]] = None, settings=None):
        super().__init__(settings)
        self.name = name
        self.paths = list(paths or LEGACY_FILES.get(name, []))
        self._pages_fetched = 0
        self._partial = False

    def fetch(self, limit: Optional[int] = None) -> Iterator[Job]:
        emitted = 0
        for relative in self.paths:
            path = PROJECT_ROOT / relative
            if not path.exists():
                logger.debug("Legacy file not present, skipping: %s", relative)
                continue
            for record in _read_records(path):
                try:
                    job = job_from_legacy_record(record, self.name)
                except Exception as exc:
                    logger.debug("Bad legacy record in %s: %s", relative, exc)
                    self._partial = True
                    continue
                if job is None:
                    continue
                yield job
                emitted += 1
                if limit and emitted >= limit:
                    return
            self._pages_fetched += 1


class LegacyMongoSource(JobSource):
    """Re-reads jobs already in ``USER_1.JOB_Data`` as canonical jobs.

    This is the migration path: it normalizes existing data in place, with no
    re-scraping and no data loss.
    """

    name = "mongo_archive"

    def __init__(self, limit: Optional[int] = None, settings=None):
        super().__init__(settings)
        self.limit = limit
        self._pages_fetched = 0
        self._partial = False

    def fetch(self, limit: Optional[int] = None) -> Iterator[Job]:
        from jobai.store import get_store

        store = get_store()
        store.require()
        emitted = 0
        for record in store.all_jobs(limit=limit or self.limit):
            try:
                job = Job.from_legacy(record)
            except Exception as exc:
                logger.debug("Skipping bad Mongo job row: %s", exc)
                self._partial = True
                continue
            if not job.title:
                continue
            yield job
            emitted += 1
            if limit and emitted >= limit:
                return
        self._pages_fetched = 1


class FaissArchiveSource(JobSource):
    """Re-reads the committed FAISS docstore as canonical jobs.

    Lets the upgrade run end-to-end on the 3,298 jobs already in the repository
    even when MongoDB has not been populated.
    """

    name = "faiss_archive"

    def fetch(self, limit: Optional[int] = None) -> Iterator[Job]:
        from jobai.retrieval.dense import DenseIndex

        emitted = 0
        for metadata in DenseIndex().all_metadata():
            try:
                job = Job.from_legacy(metadata)
            except Exception:
                self._partial = True
                continue
            if not job.title:
                continue
            yield job
            emitted += 1
            if limit and emitted >= limit:
                return


def _read_records(path: Path) -> List[Dict[str, Any]]:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            payload = json.loads(path.read_text(encoding=encoding))
        except UnicodeDecodeError:
            continue
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in %s: %s", path, exc)
            return []
        if isinstance(payload, dict):
            for key in ("job_listings", "jobs", "data", "results"):
                if isinstance(payload.get(key), list):
                    return payload[key]
            return [payload]
        return payload if isinstance(payload, list) else []
    logger.warning("Could not decode %s with any known encoding", path)
    return []


def legacy_sources() -> List[LegacyFileSource]:
    """Every legacy file source that actually has data on disk."""
    sources = []
    for name, paths in LEGACY_FILES.items():
        if any((PROJECT_ROOT / p).exists() for p in paths):
            sources.append(LegacyFileSource(name, paths))
    return sources
