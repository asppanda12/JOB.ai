"""Applicant-tracking-system job boards.

Six platforms - Greenhouse, Lever, Ashby, SmartRecruiters, Workable and
Recruitee - host the careers pages of a very large share of tech companies.
They all expose the same thing in the same way: a public, documented,
unauthenticated JSON endpoint keyed by a company slug. So they are one source
class with six adapters rather than six scrapers (ADAPTER > DUPLICATE).

These are read over plain HTTP, not Playwright, and that is deliberate: the
endpoints return JSON directly, so rendering them in a browser would add a
page load and a JS engine to fetch bytes we already have, and would make the
source *more* fragile rather than less. Playwright is used where a DOM has to
be rendered - Naukri, Cuvette, Instahyre - which is where it earns its keep.

These boards are also the highest-signal sources in the system: the data is
first-party (the employer wrote it), structurally complete, and carries a real
posting date and a stable id, so deduplication and freshness both work properly.

Which companies are tracked is configuration, not code:

    ATS_GREENHOUSE=stripe,figma,databricks,anthropic
    ATS_LEVER=palantir
    ATS_ASHBY=ramp,notion,linear
"""

from __future__ import annotations

import html
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional

import requests

from jobai.ingest.base import JobSource
from jobai.normalize.experience import parse_experience
from jobai.normalize.skills import extract_skills_from_text, normalize_skills
from jobai.schema import Job, _parse_date, canonical_url

logger = logging.getLogger(__name__)

_TAGS = re.compile(r"<[^>]+>")


# Non-breaking and other exotic spaces, which HTML job posts are full of. Left
# in place they reach the embedding and the BM25 tokenizer as literal \xa0.
_UNICODE_SPACE = re.compile(r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000\u200b\ufeff]")


def strip_html(value: Any) -> str:
    """HTML -> clean plain text, with whitespace normalized."""
    if value is None:
        return ""
    text = html.unescape(_TAGS.sub(" ", str(value)))
    text = _UNICODE_SPACE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# Default company slugs, each verified to return live postings. Override any of
# them with the matching ATS_* environment variable.
DEFAULT_COMPANIES: Dict[str, List[str]] = {
    "greenhouse": ["stripe", "figma", "databricks", "anthropic", "discord"],
    "lever": ["palantir"],
    "ashby": ["ramp", "notion", "linear"],
    "smartrecruiters": ["Continental"],
    "workable": ["scalable"],
    "recruitee": ["hygraph"],
}


class ATSBoardSource(JobSource):
    """One ATS platform, across however many company boards are configured."""

    platform: str = ""
    # Filled in by each subclass.
    endpoint: str = ""
    payload_key: Optional[str] = None

    def __init__(self, companies: Optional[List[str]] = None, settings=None):
        super().__init__(settings)
        self.name = self.platform
        self.companies = companies or self._configured_companies()
        self._pages_fetched = 0
        self._partial = False
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": self.settings.user_agent, "Accept": "application/json"}
        )

    def _configured_companies(self) -> List[str]:
        raw = os.getenv(f"ATS_{self.platform.upper()}", "")
        if raw.strip():
            return [c.strip() for c in raw.split(",") if c.strip()]
        return list(DEFAULT_COMPANIES.get(self.platform, []))

    # ------------------------------------------------------------------ http

    def _get(self, url: str) -> Optional[Any]:
        for attempt in range(self.settings.max_retries + 1):
            self.throttle(factor=0.4)  # JSON endpoints are cheap; stay polite anyway
            try:
                response = self._session.get(url, timeout=self.settings.page_timeout)
            except requests.RequestException as exc:
                logger.debug("%s request failed (attempt %d): %s", self.platform, attempt + 1, exc)
                continue
            if response.status_code == 404:
                logger.info("%s: no board at %s (wrong company slug?)", self.platform, url)
                return None
            if response.status_code == 429:
                self.throttle(factor=4 * (attempt + 1))
                continue
            if response.status_code >= 400:
                logger.warning("%s returned HTTP %s for %s", self.platform, response.status_code, url)
                continue
            try:
                return response.json()
            except ValueError:
                logger.warning("%s returned non-JSON; the API may have changed.", self.platform)
                self._partial = True
                return None
        self._partial = True
        return None

    # ------------------------------------------------------------- traversal

    def fetch(self, limit: Optional[int] = None) -> Iterator[Job]:
        limit = limit or self.settings.max_jobs_per_source
        emitted = 0
        seen: set[str] = set()

        for company in self.companies:
            payload = self._get(self.endpoint.format(company=company))
            if payload is None:
                # One dead board never costs us the others.
                self._partial = True
                continue
            self._pages_fetched += 1
            for record in self._records(payload):
                try:
                    job = self.parse(self._with_detail(record, company), company)
                except Exception as exc:
                    logger.debug("%s: unparseable record: %s", self.platform, exc)
                    self._partial = True
                    continue
                if job is None or job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                yield job
                emitted += 1
                if emitted >= limit:
                    logger.info("%s hit the %d-job limit.", self.platform, limit)
                    return

    def _records(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and self.payload_key:
            value = payload.get(self.payload_key)
            if isinstance(value, list):
                return value
        return []

    def parse(self, record: Dict[str, Any], company: str) -> Optional[Job]:
        raise NotImplementedError

    # Some platforms return only a summary in the list call and keep the job
    # body behind a per-posting URL. Those subclasses set ``detail_endpoint``.
    detail_endpoint: Optional[str] = None

    def needs_detail(self, record: Dict[str, Any]) -> bool:
        return self.detail_endpoint is not None

    def detail_url(self, record: Dict[str, Any], company: str) -> str:
        return (self.detail_endpoint or "").format(
            company=company, job_id=record.get("id") or record.get("shortcode") or ""
        )

    # Keys to take from the detail payload. ``None`` merges everything, which is
    # only safe when the two payloads agree on field meanings - Workable's v2
    # reuses ``state`` for publication status, so a blind merge turned
    # "Austin, Texas, United States" into "Austin, published, United States".
    detail_fields: Optional[tuple] = None

    def merge_detail(self, record: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
        """Fold the detail payload into the list record."""
        merged = dict(record)
        if self.detail_fields is None:
            merged.update(detail or {})
        else:
            for key in self.detail_fields:
                if (detail or {}).get(key) not in (None, "", [], {}):
                    merged[key] = detail[key]
        return merged

    def _with_detail(self, record: Dict[str, Any], company: str) -> Dict[str, Any]:
        """Fetch the job body when the list call did not include it.

        A failed detail fetch degrades to the summary record rather than
        dropping the job - a title and location still beat nothing.
        """
        if not self.needs_detail(record):
            return record
        url = self.detail_url(record, company)
        if not url:
            return record
        detail = self._get(url)
        if not isinstance(detail, dict):
            self._partial = True
            return record
        return self.merge_detail(record, detail)

    # -------------------------------------------------------------- helpers

    def _build(
        self,
        *,
        record: Dict[str, Any],
        company: str,
        title: str,
        company_name: str,
        description: str,
        source_job_id: str,
        url: str,
        location: str = "",
        employment_type: str = "",
        posted: Optional[datetime] = None,
        salary: str = "",
        department: str = "",
        skills: Optional[List[str]] = None,
    ) -> Optional[Job]:
        if not title or not source_job_id:
            return None
        description = strip_html(description)
        blob = f"{title}\n{department}\n{description}"
        experience_min, experience_max = parse_experience(_experience_phrase(description))
        if experience_min is None:
            experience_min, experience_max = parse_experience(f"{title} {description[:2500]}")
        return Job(
            title=strip_html(title),
            company=strip_html(company_name) or company,
            description=description,
            source=self.platform,
            source_job_id=str(source_job_id),
            source_url=canonical_url(url),
            application_url=canonical_url(url),
            skills=normalize_skills(skills or []) or extract_skills_from_text(blob),
            experience_min=experience_min,
            experience_max=experience_max,
            experience_raw=_experience_phrase(description),
            location=strip_html(location),
            employment_type=strip_html(employment_type),
            salary=strip_html(salary),
            posted_date=posted,
            job_category=strip_html(department),
            remote=_is_remote(f"{title} {location} {description[:1500]}"),
            raw_text=description,
        )


# --------------------------------------------------------------- adapters


class GreenhouseSource(ATSBoardSource):
    platform = "greenhouse"
    endpoint = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
    payload_key = "jobs"

    def parse(self, record, company):
        offices = record.get("offices") or []
        location = (record.get("location") or {}).get("name") or ", ".join(
            o.get("name", "") for o in offices if o.get("name")
        )
        departments = record.get("departments") or []
        return self._build(
            record=record, company=company,
            title=record.get("title", ""),
            company_name=company,
            description=record.get("content", ""),
            source_job_id=record.get("id", ""),
            url=record.get("absolute_url", ""),
            location=location,
            posted=_parse_date(record.get("updated_at") or record.get("first_published")),
            department=(departments[0].get("name") if departments else ""),
        )


class LeverSource(ATSBoardSource):
    platform = "lever"
    endpoint = "https://api.lever.co/v0/postings/{company}?mode=json"
    payload_key = None  # returns a bare list

    def parse(self, record, company):
        categories = record.get("categories") or {}
        description = "\n\n".join(
            [record.get("descriptionPlain") or record.get("description") or ""]
            + [
                f"{item.get('text','')}\n" + strip_html(item.get("content", ""))
                for item in (record.get("lists") or [])
            ]
        )
        posted = record.get("createdAt")
        return self._build(
            record=record, company=company,
            title=record.get("text", ""),
            company_name=company,
            description=description,
            source_job_id=record.get("id", ""),
            url=record.get("hostedUrl") or record.get("applyUrl", ""),
            location=categories.get("location", ""),
            employment_type=categories.get("commitment", ""),
            department=categories.get("team") or categories.get("department", ""),
            salary=_lever_salary(record.get("salaryRange")),
            posted=_epoch_ms(posted),
        )


class AshbySource(ATSBoardSource):
    platform = "ashby"
    endpoint = "https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
    payload_key = "jobs"

    def parse(self, record, company):
        compensation = record.get("compensation") or {}
        summary = compensation.get("compensationTierSummary") or ""
        return self._build(
            record=record, company=company,
            title=record.get("title", ""),
            company_name=company,
            description=record.get("descriptionPlain") or record.get("descriptionHtml", ""),
            source_job_id=record.get("id", ""),
            url=record.get("jobUrl") or record.get("applyUrl", ""),
            location=record.get("location", ""),
            employment_type=record.get("employmentType", ""),
            department=record.get("department") or record.get("team", ""),
            salary=summary,
            posted=_parse_date(record.get("publishedAt")),
        )


class SmartRecruitersSource(ATSBoardSource):
    platform = "smartrecruiters"
    endpoint = "https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100"
    payload_key = "content"
    # The list call returns metadata only; the body lives on the posting itself.
    detail_endpoint = "https://api.smartrecruiters.com/v1/companies/{company}/postings/{job_id}"
    detail_fields = ("jobAd", "applyUrl", "postingUrl")

    def parse(self, record, company):
        location = record.get("location") or {}
        location_text = ", ".join(
            str(location.get(k, "")) for k in ("city", "region", "country") if location.get(k)
        )
        sections = (record.get("jobAd") or {}).get("sections") or {}
        # Concatenate every section: requirements matter as much as the blurb.
        description = "\n\n".join(
            (sections.get(key) or {}).get("text", "")
            for key in ("jobDescription", "qualifications", "additionalInformation", "companyDescription")
        )
        return self._build(
            record=record, company=company,
            title=record.get("name", ""),
            company_name=(record.get("company") or {}).get("name") or company,
            description=description,
            source_job_id=record.get("id", ""),
            url=record.get("applyUrl") or record.get("postingUrl") or record.get("ref", ""),
            location=location_text,
            employment_type=(record.get("typeOfEmployment") or {}).get("label", ""),
            department=(record.get("department") or {}).get("label", ""),
            posted=_parse_date(record.get("releasedDate")),
        )


class WorkableSource(ATSBoardSource):
    platform = "workable"
    endpoint = "https://apply.workable.com/api/v1/widget/accounts/{company}"
    payload_key = "jobs"
    # v1 lists jobs without a body; v2 carries description/requirements/benefits.
    detail_endpoint = "https://apply.workable.com/api/v2/accounts/{company}/jobs/{job_id}"
    detail_fields = ("description", "requirements", "benefits", "remote")

    def detail_url(self, record, company):
        shortcode = record.get("shortcode") or record.get("code") or ""
        return self.detail_endpoint.format(company=company, job_id=shortcode) if shortcode else ""

    def parse(self, record, company):
        location = ", ".join(
            filter(None, [record.get("city", ""), record.get("state", ""), record.get("country", "")])
        )
        description = "\n\n".join(
            filter(None, [record.get("description", ""), record.get("requirements", ""),
                          record.get("benefits", "")])
        )
        remote_flag = record.get("telecommuting")
        job = self._build(
            record=record, company=company,
            title=record.get("title", ""),
            company_name=company,
            description=description,
            source_job_id=record.get("shortcode") or record.get("id", ""),
            url=record.get("url") or record.get("shortlink") or record.get("application_url", ""),
            location=location,
            employment_type=record.get("employment_type", ""),
            department=record.get("department") or record.get("function", ""),
            posted=_parse_date(record.get("published_on") or record.get("created_at")),
        )
        if job is not None:
            # Workable states these explicitly, so prefer them over inference.
            if isinstance(remote_flag, bool):
                job.remote = remote_flag
            if record.get("industry"):
                job.industry = str(record["industry"])
            if record.get("education"):
                job.education = [str(record["education"])]
            if record.get("experience") and not job.experience_raw:
                job.experience_raw = str(record["experience"])
                job.experience_min, job.experience_max = parse_experience(job.experience_raw)
        return job


class RecruiteeSource(ATSBoardSource):
    platform = "recruitee"
    endpoint = "https://{company}.recruitee.com/api/offers/"
    payload_key = "offers"

    def parse(self, record, company):
        location = ", ".join(
            filter(None, [record.get("city", ""), record.get("country", "")])
        )
        return self._build(
            record=record, company=company,
            title=record.get("title", ""),
            company_name=record.get("company_name") or company,
            description=(record.get("description") or "") + "\n\n" + (record.get("requirements") or ""),
            source_job_id=record.get("id", ""),
            url=record.get("careers_url") or record.get("careers_apply_url", ""),
            location=location,
            employment_type=record.get("employment_type_code") or record.get("options_cv", ""),
            department=record.get("department", ""),
            posted=_parse_date(record.get("published_at") or record.get("created_at")),
        )


ATS_SOURCES: Dict[str, Callable[[], ATSBoardSource]] = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
    "ashby": AshbySource,
    "smartrecruiters": SmartRecruitersSource,
    "workable": WorkableSource,
    "recruitee": RecruiteeSource,
}


# --------------------------------------------------------------- utilities

_EXPERIENCE_PHRASE = re.compile(
    r"[^.\n]{0,70}?\b\d+\+?\s*(?:-|–|to)?\s*\d*\s*(?:years?|yrs?)\b[^.\n]{0,40}", re.IGNORECASE
)

# "Must be 18 years or older" is an age requirement, not work experience;
# matching it produced an experience band of (18, 18).
_AGE_PHRASE = re.compile(
    r"years?\s*(?:or\s*(?:older|above)|of\s*age)|age\s*of\s*\d+|\bolder\b", re.IGNORECASE
)


def _experience_phrase(text: str) -> str:
    """First phrase that states a work-experience requirement, if any."""
    for match in _EXPERIENCE_PHRASE.finditer(text or ""):
        phrase = match.group(0).strip()
        if _AGE_PHRASE.search(phrase):
            continue
        return phrase
    return ""


def _lever_salary(salary_range: Any) -> str:
    """Lever gives ``{"min": .., "max": .., "currency": ..}``; render it readably."""
    if not isinstance(salary_range, dict):
        return ""
    low, high = salary_range.get("min"), salary_range.get("max")
    currency = salary_range.get("currency") or ""
    if low and high:
        return f"{currency} {low:,} - {high:,}".strip()
    if low or high:
        return f"{currency} {low or high:,}".strip()
    return ""


def _epoch_ms(value: Any) -> Optional[datetime]:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    seconds = value / 1000 if value > 1e12 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _is_remote(text: str) -> Optional[bool]:
    blob = (text or "").lower()
    if re.search(r"\bremote\b|work from home|\bwfh\b|distributed team", blob):
        return True
    if re.search(r"\bon[- ]?site\b|\bin[- ]office\b|\bhybrid\b", blob):
        return False
    return None
