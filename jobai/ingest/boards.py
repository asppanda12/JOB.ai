"""Public job-board feeds.

Six aggregators that publish an open feed: RemoteOK, Remotive, Arbeitnow,
Himalayas, Jobicy (JSON) and We Work Remotely (RSS). They share a shape - one
request returns a page of complete postings - so they share one base class and
differ only in a field mapping.

These complement the ATS boards rather than overlapping with them: ATS feeds
are per-company and deep, aggregators are cross-company and broad, and they
skew heavily remote, which fills a real gap in a corpus that was otherwise
almost entirely India-onsite.

Read over HTTP for the same reason as the ATS boards: they are documented feeds
that return structured data, so a browser would add cost and fragility without
adding information. Deduplication handles the overlap between them (the same
posting is often syndicated to three of these at once).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional

import requests

from jobai.ingest.ats import _experience_phrase, _is_remote, strip_html
from jobai.ingest.base import JobSource
from jobai.normalize.experience import parse_experience
from jobai.normalize.skills import extract_skills_from_text, normalize_skills
from jobai.schema import Job, _parse_date, canonical_url

logger = logging.getLogger(__name__)


class BoardFeedSource(JobSource):
    """A public feed of postings. Subclasses supply the URL and field mapping."""

    feed_url: str = ""
    payload_key: Optional[str] = None
    accept: str = "application/json"

    def __init__(self, settings=None):
        super().__init__(settings)
        self._pages_fetched = 0
        self._partial = False
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": self.settings.user_agent, "Accept": self.accept}
        )

    def _fetch_payload(self) -> Optional[Any]:
        for attempt in range(self.settings.max_retries + 1):
            self.throttle(factor=0.4)
            try:
                response = self._session.get(self.feed_url, timeout=self.settings.page_timeout)
            except requests.RequestException as exc:
                logger.debug("%s request failed (attempt %d): %s", self.name, attempt + 1, exc)
                continue
            if response.status_code == 429:
                self.throttle(factor=4 * (attempt + 1))
                continue
            if response.status_code >= 400:
                logger.warning("%s returned HTTP %s", self.name, response.status_code)
                continue
            return self._decode(response)
        self._partial = True
        return None

    def _decode(self, response) -> Any:
        try:
            return response.json()
        except ValueError:
            logger.warning("%s returned non-JSON; the feed format may have changed.", self.name)
            self._partial = True
            return None

    def _records(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and self.payload_key:
            value = payload.get(self.payload_key)
            if isinstance(value, list):
                return value
        return []

    def fetch(self, limit: Optional[int] = None) -> Iterator[Job]:
        limit = limit or self.settings.max_jobs_per_source
        payload = self._fetch_payload()
        if payload is None:
            return
        self._pages_fetched += 1
        emitted = 0
        seen: set[str] = set()
        for record in self._records(payload):
            try:
                job = self.parse(record)
            except Exception as exc:
                logger.debug("%s: unparseable record: %s", self.name, exc)
                self._partial = True
                continue
            if job is None or job.source_job_id in seen:
                continue
            seen.add(job.source_job_id)
            yield job
            emitted += 1
            if emitted >= limit:
                logger.info("%s hit the %d-job limit.", self.name, limit)
                return

    def parse(self, record: Dict[str, Any]) -> Optional[Job]:
        raise NotImplementedError

    def _build(
        self,
        *,
        title: str,
        company: str,
        description: str,
        source_job_id: str,
        url: str,
        location: str = "",
        tags: Optional[List[str]] = None,
        employment_type: str = "",
        salary: str = "",
        posted: Optional[datetime] = None,
        category: str = "",
        seniority: str = "",
    ) -> Optional[Job]:
        if not title or not source_job_id:
            return None
        description = strip_html(description)
        experience_raw = _experience_phrase(description) or seniority
        experience_min, experience_max = parse_experience(experience_raw)
        if experience_min is None:
            experience_min, experience_max = parse_experience(f"{title} {description[:2500]}")
        # Feed tags are curated by the board, so they are trusted as explicit
        # skill labels; free-text extraction only fills the gaps.
        skills = normalize_skills(tags or [])
        skills += [s for s in extract_skills_from_text(f"{title}\n{description}") if s not in skills]
        return Job(
            title=strip_html(title),
            company=strip_html(company),
            description=description,
            source=self.name,
            source_job_id=str(source_job_id),
            source_url=canonical_url(url),
            application_url=canonical_url(url),
            skills=skills,
            experience_min=experience_min,
            experience_max=experience_max,
            experience_raw=experience_raw,
            location=strip_html(location),
            employment_type=strip_html(employment_type),
            salary=strip_html(salary),
            posted_date=posted,
            job_category=strip_html(category),
            remote=_is_remote(f"{title} {location} {description[:1200]}"),
            raw_text=description,
        )


# ---------------------------------------------------------------- adapters


class RemoteOKSource(BoardFeedSource):
    name = "remoteok"
    feed_url = "https://remoteok.com/api"

    def _records(self, payload):
        records = super()._records(payload)
        # The first element is a legal/attribution notice, not a job.
        return [r for r in records if isinstance(r, dict) and r.get("id") and r.get("position")]

    def parse(self, record):
        salary_min, salary_max = record.get("salary_min") or 0, record.get("salary_max") or 0
        salary = f"${salary_min:,} - ${salary_max:,}" if salary_min and salary_max else ""
        return self._build(
            title=record.get("position", ""),
            company=record.get("company", ""),
            description=record.get("description", ""),
            source_job_id=record.get("id", ""),
            url=record.get("url") or record.get("apply_url", ""),
            location=record.get("location") or "Remote",
            tags=record.get("tags") or [],
            salary=salary,
            posted=_parse_date(record.get("date")),
        )


class RemotiveSource(BoardFeedSource):
    name = "remotive"
    feed_url = "https://remotive.com/api/remote-jobs?limit=200"
    payload_key = "jobs"

    def parse(self, record):
        return self._build(
            title=record.get("title", ""),
            company=record.get("company_name", ""),
            description=record.get("description", ""),
            source_job_id=record.get("id", ""),
            url=record.get("url", ""),
            location=record.get("candidate_required_location") or "Remote",
            tags=record.get("tags") or [],
            employment_type=record.get("job_type", ""),
            salary=record.get("salary", ""),
            posted=_parse_date(record.get("publication_date")),
            category=record.get("category", ""),
        )


class ArbeitnowSource(BoardFeedSource):
    name = "arbeitnow"
    feed_url = "https://www.arbeitnow.com/api/job-board-api"
    payload_key = "data"

    def parse(self, record):
        created = record.get("created_at")
        posted = None
        if isinstance(created, (int, float)) and created > 0:
            try:
                posted = datetime.fromtimestamp(created, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                posted = None
        job_types = record.get("job_types") or []
        return self._build(
            title=record.get("title", ""),
            company=record.get("company_name", ""),
            description=record.get("description", ""),
            source_job_id=record.get("slug", ""),
            url=record.get("url", ""),
            location=record.get("location", ""),
            tags=record.get("tags") or [],
            employment_type=job_types[0] if job_types else "",
            posted=posted,
        )


class HimalayasSource(BoardFeedSource):
    name = "himalayas"
    feed_url = "https://himalayas.app/jobs/api?limit=200"
    payload_key = "jobs"

    def parse(self, record):
        seniority = record.get("seniority") or []
        locations = record.get("locationRestrictions") or []
        low, high = record.get("minSalary"), record.get("maxSalary")
        currency = record.get("currency") or ""
        salary = f"{currency} {low:,} - {high:,}".strip() if low and high else ""
        return self._build(
            title=record.get("title", ""),
            company=record.get("companyName", ""),
            description=record.get("description") or record.get("excerpt", ""),
            source_job_id=record.get("guid", ""),
            url=record.get("applicationLink", ""),
            location=", ".join(map(str, locations)) or "Remote",
            tags=[t.replace("-", " ") for t in (record.get("categories") or [])],
            employment_type=record.get("employmentType", ""),
            salary=salary,
            posted=_parse_date(record.get("pubDate")),
            category=", ".join(record.get("parentCategories") or []),
            seniority=seniority[0] if seniority else "",
        )


class JobicySource(BoardFeedSource):
    name = "jobicy"
    feed_url = "https://jobicy.com/api/v2/remote-jobs?count=50"
    payload_key = "jobs"

    def parse(self, record):
        job_types = record.get("jobType") or []
        return self._build(
            title=record.get("jobTitle", ""),
            company=record.get("companyName", ""),
            description=record.get("jobDescription") or record.get("jobExcerpt", ""),
            source_job_id=record.get("id", ""),
            url=record.get("url", ""),
            location=record.get("jobGeo") or "Remote",
            tags=record.get("jobIndustry") or [],
            employment_type=job_types[0] if job_types else "",
            posted=_parse_date(record.get("pubDate")),
            category=", ".join(record.get("jobIndustry") or []),
            seniority=record.get("jobLevel", ""),
        )


class WeWorkRemotelySource(BoardFeedSource):
    """We Work Remotely publishes RSS rather than JSON."""

    name = "weworkremotely"
    feed_url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
    accept = "application/rss+xml, application/xml, text/xml"

    def _decode(self, response):
        return response.text

    def _records(self, payload):
        if not isinstance(payload, str):
            return []
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(payload)
        except Exception as exc:
            logger.warning("%s: could not parse RSS: %s", self.name, exc)
            self._partial = True
            return []
        records = []
        for item in root.iter("item"):
            records.append({child.tag: (child.text or "") for child in item})
        return records

    def parse(self, record):
        # WWR titles read "Company: Job Title".
        raw_title = record.get("title", "")
        company, _, title = raw_title.partition(":")
        if not title:
            company, title = "", raw_title
        link = record.get("link", "")
        identifier = re.search(r"/(\d+)-", link) or re.search(r"/([^/]+)$", link)
        return self._build(
            title=title.strip(),
            company=company.strip(),
            description=record.get("description", ""),
            source_job_id=identifier.group(1) if identifier else link,
            url=link,
            location=record.get("region") or "Remote",
            category=record.get("category", ""),
            employment_type=record.get("type", ""),
            posted=_parse_date(_rfc822(record.get("pubDate", ""))),
        )


def _rfc822(value: str) -> Optional[str]:
    """RSS dates are RFC-822; convert to ISO so ``_parse_date`` can read them."""
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(value).isoformat()
    except Exception:
        return None


BOARD_SOURCES: Dict[str, Callable[[], BoardFeedSource]] = {
    "remoteok": RemoteOKSource,
    "remotive": RemotiveSource,
    "arbeitnow": ArbeitnowSource,
    "himalayas": HimalayasSource,
    "jobicy": JobicySource,
    "weworkremotely": WeWorkRemotelySource,
}
