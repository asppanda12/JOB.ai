"""Naukri job source.

Naukri's JSON API (``/jobapi/v3/search``) answers ``{"message": "recaptcha
required", "statusCode": 406}`` to any plain HTTP client, and to in-page
``fetch`` as well. That is a deliberate anti-bot gate, and this project does
not try to defeat it. Instead we drive a real browser over the ordinary public
search pages - the same HTML a visitor sees - and read the rendered results.

Why this is more robust than the code it replaces:

* the old scraper guessed at ``jobTuple`` / ``cust-job-tuple`` / ``job-tuple``
  containers and then ``[class*='title']`` / ``[class*='comp']`` substrings.
  The live markup uses ``div.srp-jobtuple-wrapper[data-job-id]`` with semantic
  child classes, which is what we key on - with the old guesses kept as
  fallbacks so a partial redesign degrades instead of returning nothing;
* ``data-job-id`` gives a real source id, so deduplication works across runs;
* pagination follows Naukri's own ``-2``, ``-3`` URL suffixes instead of
  re-requesting page 1 forever;
* each result's own page is visited for the full description (the card text is
  truncated at ~120 characters), gated by ``NAUKRI_FETCH_DETAILS``;
* one bad card, one slow page or a captcha interstitial is recorded as a
  partial result; it never aborts the run or the other sources.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator, List, Optional

from jobai.ingest.base import JobSource
from jobai.ingest.browser import BrowserUnavailable, chrome, first_attr, first_text, scroll_page
from jobai.normalize.experience import parse_experience
from jobai.normalize.skills import extract_skills_from_text, normalize_skills
from jobai.schema import Job, canonical_url

logger = logging.getLogger(__name__)

BASE = "https://www.naukri.com"

# Ordered candidates: live markup first, historical markup as fallback.
CARD_SELECTORS = ["div.srp-jobtuple-wrapper", "article.jobTuple", "div.cust-job-tuple"]
TITLE_SELECTORS = ["a.title", "a.jobTupleHeader", "[class*='title'] a", "a[class*='title']"]
COMPANY_SELECTORS = ["a.comp-name", "a.subTitle", "[class*='comp-name']", "[class*='comp']"]
EXPERIENCE_SELECTORS = ["span.expwdth", "span.exp-wrap span", "[class*='expwdth']", "[class*='exp'] span"]
LOCATION_SELECTORS = ["span.locWdth", "span.loc-wrap span", "[class*='locWdth']", "[class*='loc'] span"]
SALARY_SELECTORS = ["span.sal-wrap span", "span.sal", "[class*='sal-wrap']", "[class*='sal']"]
SNIPPET_SELECTORS = ["span.job-desc", "div.job-description", "[class*='job-desc']"]
TAG_SELECTORS = ["ul.tags-gt li", "li.tag-li", "[class*='tag-li']"]
POSTED_SELECTORS = ["span.job-post-day", "[class*='job-post-day']", "[class*='postedDate']"]
DETAIL_SELECTORS = [
    "div.styles_JDC__dang-inner-html__h0K4t",
    "section.job-desc",
    "div.dang-inner-html",
    "[class*='JDC__dang-inner-html']",
]


class NaukriSource(JobSource):
    name = "naukri"

    def __init__(
        self,
        keywords: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        *,
        fetch_details: Optional[bool] = None,
        settings=None,
    ):
        super().__init__(settings)
        self.keywords = keywords or [k.strip() for k in self.settings.naukri_keywords.split("|") if k.strip()]
        self.locations = locations or [l.strip() for l in self.settings.naukri_locations.split("|") if l.strip()]
        if fetch_details is None:
            fetch_details = os.getenv("NAUKRI_FETCH_DETAILS", "1").lower() in {"1", "true", "yes"}
        self.fetch_details = fetch_details
        self._pages_fetched = 0
        self._partial = False

    # ----------------------------------------------------------------- urls

    @staticmethod
    def search_url(keyword: str, location: str, page: int) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-") + "-jobs"
        if location:
            slug += "-in-" + re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")
        return f"{BASE}/{slug}" + (f"-{page}" if page > 1 else "")

    # ------------------------------------------------------------- traversal

    def fetch(self, limit: Optional[int] = None) -> Iterator[Job]:
        limit = limit or self.settings.max_jobs_per_source
        seen: set[str] = set()
        emitted = 0

        try:
            driver_context = chrome(self.settings)
        except BrowserUnavailable:
            raise

        with driver_context as driver:
            for keyword in self.keywords:
                for location in self.locations:
                    for page in range(1, self.settings.max_pages + 1):
                        cards = self._load_page(driver, keyword, location, page)
                        if not cards:
                            break
                        for card in cards:
                            try:
                                job = self._parse_card(card, keyword)
                            except Exception as exc:
                                logger.debug("Skipping unparseable Naukri card: %s", exc)
                                self._partial = True
                                continue
                            if job is None or job.source_job_id in seen:
                                continue
                            seen.add(job.source_job_id)
                            if self.fetch_details:
                                self._add_detail(driver, job)
                            yield job
                            emitted += 1
                            if emitted >= limit:
                                logger.info("Naukri hit the %d-job limit.", limit)
                                return

    def _load_page(self, driver, keyword: str, location: str, page: int) -> List:
        from selenium.webdriver.common.by import By

        url = self.search_url(keyword, location, page)
        self.throttle()
        try:
            driver.get(url)
        except Exception as exc:
            logger.warning("Naukri page load failed (%s): %s", url, exc)
            self._partial = True
            return []

        if self._blocked(driver):
            logger.warning("Naukri served a captcha/verification page; stopping this query.")
            self._partial = True
            return []

        # The results render client-side; wait for cards rather than a fixed sleep.
        cards: List = []
        deadline = time.monotonic() + self.settings.page_timeout
        while time.monotonic() < deadline:
            for selector in CARD_SELECTORS:
                cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    break
            if cards:
                break
            time.sleep(0.5)

        if not cards:
            logger.info("No Naukri cards on page %d for %r; markup may have changed.", page, keyword)
            return []

        scroll_page(driver, rounds=3, pause=1.0)
        for selector in CARD_SELECTORS:
            found = driver.find_elements(By.CSS_SELECTOR, selector)
            if found:
                cards = found
                break
        self._pages_fetched += 1
        return cards

    @staticmethod
    def _blocked(driver) -> bool:
        try:
            blob = (driver.title or "").lower() + driver.current_url.lower()
        except Exception:
            return False
        return any(token in blob for token in ("captcha", "verify you are human", "access denied"))

    # --------------------------------------------------------------- parsing

    def _parse_card(self, card, keyword: str) -> Optional[Job]:
        source_job_id = (card.get_attribute("data-job-id") or "").strip()
        title = first_text(card, TITLE_SELECTORS)
        url = first_attr(card, TITLE_SELECTORS, "href")
        if not title or not url:
            return None
        if not source_job_id:
            match = re.search(r"-(\d{8,})(?:\?|$)", url)
            source_job_id = match.group(1) if match else ""
        if not source_job_id:
            return None

        experience_raw = first_text(card, EXPERIENCE_SELECTORS)
        location = first_text(card, LOCATION_SELECTORS)
        salary = first_text(card, SALARY_SELECTORS)
        snippet = first_text(card, SNIPPET_SELECTORS)
        posted_raw = first_text(card, POSTED_SELECTORS)
        tags = self._tags(card)

        experience_min, experience_max = parse_experience(experience_raw)
        skills = normalize_skills(tags) or extract_skills_from_text(f"{title} {snippet}")

        return Job(
            title=title,
            company=first_text(card, COMPANY_SELECTORS),
            location=location,
            description=snippet,
            source=self.name,
            source_job_id=source_job_id,
            source_url=canonical_url(url),
            application_url=canonical_url(url),
            company_url=first_attr(card, COMPANY_SELECTORS, "href"),
            skills=skills,
            experience_min=experience_min,
            experience_max=experience_max,
            experience_raw=experience_raw,
            salary=salary,
            posted_date=_relative_date(posted_raw),
            job_category=keyword,
            remote=_is_remote(f"{title} {location} {snippet}"),
            raw_text=snippet,
        )

    @staticmethod
    def _tags(card) -> List[str]:
        from selenium.webdriver.common.by import By

        for selector in TAG_SELECTORS:
            try:
                elements = card.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue
            values = [(e.text or "").strip() for e in elements]
            values = [v for v in values if v]
            if values:
                return values
        return []

    def _add_detail(self, driver, job: Job) -> None:
        """Open the job's own page for the full description.

        Card snippets are truncated at ~120 characters, which is far too little
        to embed or to extract skills from. A failure here leaves the snippet
        in place rather than dropping the job.
        """
        original = driver.current_window_handle
        self.throttle()
        try:
            driver.switch_to.new_window("tab")
            driver.get(job.application_url)
            time.sleep(1.5)
            description = first_text(driver, DETAIL_SELECTORS)
            if description and len(description) > len(job.description):
                job.description = description
                job.raw_text = description
                job.skills = normalize_skills(job.skills + extract_skills_from_text(description))
                if job.experience_min is None:
                    job.experience_min, job.experience_max = parse_experience(description[:2500])
        except Exception as exc:
            logger.debug("Could not load Naukri detail for %s: %s", job.source_job_id, exc)
            self._partial = True
        finally:
            try:
                if driver.current_window_handle != original:
                    driver.close()
                driver.switch_to.window(original)
            except Exception:
                pass


def _relative_date(text: str) -> Optional[datetime]:
    """Turn "3+ weeks ago" / "Just now" / "2 days ago" into a timestamp."""
    if not text:
        return None
    blob = text.strip().lower()
    now = datetime.now(timezone.utc)
    if "just now" in blob or "today" in blob or "few hours" in blob:
        return now
    match = re.search(r"(\d+)\s*\+?\s*(hour|day|week|month)", blob)
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    days = {"hour": amount / 24, "day": amount, "week": amount * 7, "month": amount * 30}[unit]
    return now - timedelta(days=days)


def _is_remote(text: str) -> Optional[bool]:
    blob = (text or "").lower()
    if re.search(r"\bremote\b|work from home|\bwfh\b", blob):
        return True
    if re.search(r"\bin[- ]office\b|\bon[- ]?site\b|\bhybrid\b", blob):
        return False
    return None
