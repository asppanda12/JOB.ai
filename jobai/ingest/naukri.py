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

Driven by Playwright rather than Selenium: auto-waiting removes the fixed
``time.sleep`` guesses and the stale-element retries, and blocking images and
fonts makes each results page markedly lighter.

**Naukri requires a headed browser.** Every headless configuration - bundled
Chromium and the real Chrome channel alike - is answered with HTTP 403, while
the same request from a visible window returns 200. So this source opens a real
window regardless of ``SCRAPER_HEADLESS``; set ``NAUKRI_HEADLESS=1`` to override
that and accept the likely 403. We do not try to disguise the browser: a 403 is
reported as "blocked", not worked around.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator, List, Optional

from jobai.ingest.base import JobSource
from jobai.ingest.playwright_browser import (
    BrowserUnavailable,
    attr_of,
    autoscroll,
    goto_status,
    is_blocked,
    playwright_page,
    text_of,
    texts_of,
    wait_for_any,
)
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
        self.headless = os.getenv("NAUKRI_HEADLESS", "0").lower() in {"1", "true", "yes"}
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

        # headless=False: see the module docstring. Naukri 403s every headless
        # configuration, so opening a window is the only honest way in.
        with playwright_page(self.settings, headless=self.headless) as page:
            for keyword in self.keywords:
                for location in self.locations:
                    for page_number in range(1, self.settings.max_pages + 1):
                        cards = self._load_page(page, keyword, location, page_number)
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
                                self._add_detail(page, job)
                            yield job
                            emitted += 1
                            if emitted >= limit:
                                logger.info("Naukri hit the %d-job limit.", limit)
                                return

    def _load_page(self, page, keyword: str, location: str, page_number: int) -> List:
        """Load one results page and return its job-card locators."""
        url = self.search_url(keyword, location, page_number)
        self.throttle()
        ok, status = goto_status(page, url)
        if not ok:
            if status in (403, 429):
                logger.warning(
                    "Naukri refused the request (HTTP %s). It blocks headless browsers; "
                    "run with NAUKRI_HEADLESS=0 (the default) and a desktop session.",
                    status,
                )
            else:
                logger.warning("Naukri page load failed (HTTP %s): %s", status, url)
            self._partial = True
            return []

        if is_blocked(page):
            logger.warning("Naukri served a captcha/verification page; stopping this query.")
            self._partial = True
            return []

        # Auto-wait for whichever card container this deploy renders.
        selector = wait_for_any(page, CARD_SELECTORS, timeout_ms=self.settings.page_timeout * 1000)
        if selector is None:
            logger.info("No Naukri cards on page %d for %r; markup may have changed.",
                        page_number, keyword)
            return []

        autoscroll(page, rounds=3, pause_ms=800)
        locator = page.locator(selector)
        self._pages_fetched += 1
        return [locator.nth(i) for i in range(locator.count())]

    # --------------------------------------------------------------- parsing

    def _parse_card(self, card, keyword: str) -> Optional[Job]:
        source_job_id = (card.get_attribute("data-job-id") or "").strip()
        title = text_of(card, TITLE_SELECTORS)
        url = attr_of(card, TITLE_SELECTORS, "href")
        if not title or not url:
            return None
        if not source_job_id:
            match = re.search(r"-(\d{8,})(?:\?|$)", url)
            source_job_id = match.group(1) if match else ""
        if not source_job_id:
            return None

        experience_raw = text_of(card, EXPERIENCE_SELECTORS)
        location = text_of(card, LOCATION_SELECTORS)
        salary = text_of(card, SALARY_SELECTORS)
        snippet = text_of(card, SNIPPET_SELECTORS)
        posted_raw = text_of(card, POSTED_SELECTORS)
        tags = texts_of(card, TAG_SELECTORS)

        experience_min, experience_max = parse_experience(experience_raw)
        skills = normalize_skills(tags) or extract_skills_from_text(f"{title} {snippet}")

        return Job(
            title=title,
            company=text_of(card, COMPANY_SELECTORS),
            location=location,
            description=snippet,
            source=self.name,
            source_job_id=source_job_id,
            source_url=canonical_url(url),
            application_url=canonical_url(url),
            company_url=attr_of(card, COMPANY_SELECTORS, "href"),
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

    def _add_detail(self, page, job: Job) -> None:
        """Open the job's own page in a second tab for the full description.

        Card snippets are truncated at ~120 characters, far too little to embed
        or to extract skills from. A failure here leaves the snippet in place
        rather than dropping the job.
        """
        self.throttle()
        detail = None
        try:
            detail = page.context.new_page()
            ok, status = goto_status(detail, job.application_url)
            if not ok:
                logger.debug("Naukri detail %s returned HTTP %s", job.source_job_id, status)
                self._partial = True
                return
            # Wait for the description container rather than guessing a sleep.
            wait_for_any(detail, DETAIL_SELECTORS, timeout_ms=10000)
            description = text_of(detail, DETAIL_SELECTORS)
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
            if detail is not None:
                try:
                    detail.close()
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
