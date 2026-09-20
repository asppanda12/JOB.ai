"""LinkedIn job source.

Uses LinkedIn's public *guest* job-search endpoints - the same pages an anonymous
visitor sees - so no account, no credentials and no session cookies are
involved. Two endpoints do the work:

* ``/jobs-guest/jobs/api/seeMoreJobPostings/search`` - a paginated HTML fragment
  of job cards, 25 per page. This is what the page itself calls as you scroll,
  and it is far more stable than scraping the React shell.
* ``/jobs-guest/jobs/api/jobPosting/{id}`` - the full description for one job.

Because both return plain HTML fragments, this source runs on ``requests`` +
BeautifulSoup and needs no browser at all, which removes the entire class of
failures the old Selenium implementation had (driver startup, sign-in modals,
scroll timing, stale elements).

What was broken before and is fixed here:
  * ``jobs-search__results-list`` / ``base-card`` selectors that the logged-out
    page no longer renders the same way -> guest API fragments instead;
  * a fresh Chrome + proxy per page, with the driver leaked on exception;
  * ``while len(jobs) < max_jobs`` with no page cap - an infinite loop whenever
    a page returned nothing;
  * descriptions fetched by navigating the same driver, losing the results page;
  * no dedup, no posted date, no skills, tracking-laden URLs.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Iterator, List, Optional
from urllib.parse import urlencode

import requests

from jobai.ingest.base import JobSource
from jobai.normalize.experience import parse_experience
from jobai.normalize.skills import extract_skills_from_text
from jobai.schema import Job, canonical_url

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
PAGE_SIZE = 25

_JOB_ID = re.compile(r"-(\d{6,})(?:\?|$)")


class LinkedInSource(JobSource):
    name = "linkedin"

    def __init__(
        self,
        keywords: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        *,
        posted_within_seconds: int = 7 * 86400,
        settings=None,
    ):
        super().__init__(settings)
        self.keywords = keywords or [k.strip() for k in self.settings.linkedin_keywords.split("|") if k.strip()]
        self.locations = locations or [l.strip() for l in self.settings.linkedin_locations.split("|") if l.strip()]
        self.posted_within_seconds = posted_within_seconds
        self._pages_fetched = 0
        self._partial = False
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.settings.user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    # ------------------------------------------------------------------ http

    def _get(self, url: str, params: Optional[Dict[str, object]] = None) -> Optional[str]:
        """GET with retries. Returns None instead of raising on a dead page."""
        for attempt in range(self.settings.max_retries + 1):
            self.throttle()
            try:
                response = self._session.get(url, params=params, timeout=self.settings.page_timeout)
            except requests.RequestException as exc:
                logger.warning("LinkedIn request error (attempt %d): %s", attempt + 1, exc)
                continue
            if response.status_code == 429:
                # Rate limited: back off hard rather than hammering.
                logger.warning("LinkedIn rate-limited us; backing off.")
                self.throttle(factor=4 * (attempt + 1))
                continue
            if response.status_code == 404:
                return None
            if response.status_code >= 400:
                logger.warning("LinkedIn returned %s for %s", response.status_code, url)
                continue
            return response.text
        self._partial = True
        return None

    # ------------------------------------------------------------- traversal

    def fetch(self, limit: Optional[int] = None) -> Iterator[Job]:
        limit = limit or self.settings.max_jobs_per_source
        seen: set[str] = set()
        emitted = 0

        for keyword in self.keywords:
            for location in self.locations:
                for job in self._search(keyword, location):
                    if job.source_job_id in seen:
                        continue
                    seen.add(job.source_job_id)
                    yield job
                    emitted += 1
                    if emitted >= limit:
                        logger.info("LinkedIn hit the %d-job limit.", limit)
                        return

    def _search(self, keyword: str, location: str) -> Iterator[Job]:
        from bs4 import BeautifulSoup

        for page in range(self.settings.max_pages):
            params = {
                "keywords": keyword,
                "location": location,
                "start": page * PAGE_SIZE,
                "f_TPR": f"r{self.posted_within_seconds}",
            }
            html = self._get(SEARCH_URL, params)
            if not html:
                # A dead page ends this keyword/location, not the whole run.
                break
            self._pages_fetched += 1
            cards = BeautifulSoup(html, "html.parser").find_all("li")
            if not cards:
                break
            for card in cards:
                job = self._parse_card(card, keyword)
                if job is not None:
                    yield job

    # --------------------------------------------------------------- parsing

    def _parse_card(self, card, keyword: str) -> Optional[Job]:
        title_el = card.find(["h3", "h4"], class_=re.compile("result-card__title|base-search-card__title"))
        link_el = card.find("a", class_=re.compile("result-card__full-card-link|base-card__full-link")) or card.find("a", href=True)
        if not title_el or not link_el:
            return None

        url = (link_el.get("href") or "").split("?")[0]
        source_job_id = self._job_id(url) or self._entity_id(card)
        if not source_job_id:
            return None

        company_el = card.find(["h4", "a"], class_=re.compile("result-card__subtitle|base-search-card__subtitle"))
        location_el = card.find("span", class_=re.compile("job-result-card__location|job-search-card__location"))
        date_el = card.find("time")

        description = self._description(source_job_id)
        title = title_el.get_text(strip=True)
        blob = f"{title}\n{description}"

        # Parse the band from the matched phrase first: it can sit anywhere in a
        # long description, so scanning only the head misses most postings.
        experience_raw = _experience_phrase(description)
        experience_min, experience_max = parse_experience(experience_raw)
        if experience_min is None:
            experience_min, experience_max = parse_experience(f"{title} {description[:3000]}")
        return Job(
            title=title,
            company=company_el.get_text(strip=True) if company_el else "",
            location=location_el.get_text(strip=True) if location_el else "",
            description=description,
            source=self.name,
            source_job_id=str(source_job_id),
            source_url=canonical_url(url),
            application_url=canonical_url(url),
            skills=extract_skills_from_text(blob),
            experience_min=experience_min,
            experience_max=experience_max,
            experience_raw=experience_raw,
            posted_date=_posted_date(date_el),
            job_category=keyword,
            remote=_is_remote(f"{title} {location_el.get_text(strip=True) if location_el else ''} {description[:1500]}"),
            raw_text=description,
        )

    def _description(self, source_job_id: str) -> str:
        from bs4 import BeautifulSoup

        html = self._get(DETAIL_URL.format(job_id=source_job_id))
        if not html:
            # A missing description is a partial result, not a failure: the
            # card's title/company/location are still worth indexing.
            return ""
        soup = BeautifulSoup(html, "html.parser")
        container = soup.find("div", class_=re.compile("show-more-less-html__markup|description__text"))
        if container is None:
            container = soup.find("section", class_=re.compile("description"))
        return container.get_text("\n", strip=True) if container else ""

    @staticmethod
    def _job_id(url: str) -> str:
        match = _JOB_ID.search(url or "")
        return match.group(1) if match else ""

    @staticmethod
    def _entity_id(card) -> str:
        holder = card.find(attrs={"data-entity-urn": True}) or card.find(attrs={"data-id": True})
        if holder is None:
            return ""
        value = holder.get("data-entity-urn") or holder.get("data-id") or ""
        match = re.search(r"(\d{6,})", value)
        return match.group(1) if match else ""


def _posted_date(element) -> Optional[datetime]:
    if element is None:
        return None
    raw = element.get("datetime") or element.get_text(strip=True)
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    # "3 days ago", "2 weeks ago"
    match = re.search(r"(\d+)\s*(hour|day|week|month)", raw, re.IGNORECASE)
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2).lower()
    days = {"hour": amount / 24, "day": amount, "week": amount * 7, "month": amount * 30}[unit]
    return datetime.now(timezone.utc) - timedelta(days=days)


_EXPERIENCE_PHRASE = re.compile(
    r"[^.\n]{0,60}?\b\d+\+?\s*(?:-|–|to)?\s*\d*\s*(?:years?|yrs?)\b[^.\n]{0,40}", re.IGNORECASE
)


def _experience_phrase(text: str) -> str:
    match = _EXPERIENCE_PHRASE.search(text or "")
    return match.group(0).strip() if match else ""


def _is_remote(text: str) -> Optional[bool]:
    blob = (text or "").lower()
    if re.search(r"\bremote\b|work from home|\bwfh\b", blob):
        return True
    if re.search(r"\bon[- ]?site\b|\bin[- ]office\b|\bhybrid\b", blob):
        return False
    return None
