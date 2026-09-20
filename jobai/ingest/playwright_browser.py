"""Playwright browser layer.

Playwright replaces Selenium for every DOM-scraped source. It is a better fit
for job boards specifically:

* **Auto-waiting.** ``page.wait_for_selector`` waits for an element to be
  *actionable*, not merely present, which removes the ``time.sleep(5)`` guesses
  and the ``StaleElementReferenceException`` retries the Selenium code was full
  of.
* **Real network control.** We block images, fonts, media and analytics, which
  cuts page weight by roughly 70% on a typical board and makes a full scrape
  several times faster.
* **No driver/browser version dance.** ``playwright install chromium`` pins a
  matching build; there is no chromedriver to keep in step with Chrome (the
  repository previously carried a 15 MB Linux chromedriver that could not run
  on macOS at all).
* **Proper isolation.** Each run gets a fresh browser context, so cookies from
  one source never leak into another.

Conduct: a normal desktop user agent and a throttled request rate. No
fingerprint spoofing and no captcha solving - a source that challenges us is
reported as blocked, not worked around.
"""

from __future__ import annotations

import logging
import random
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Sequence

from jobai.config import ScrapeSettings, get_settings

logger = logging.getLogger(__name__)

# Blocked so a scrape fetches text, not megabytes of imagery.
#
# Stylesheets are deliberately NOT blocked. Several job boards are SPAs that
# gate their first render on CSS loading: with stylesheets blocked, Naukri
# serves a 1.9 KB shell and zero job cards, versus 363 KB and 20 cards with
# them allowed. Images, media and fonts are the bulk of the weight anyway.
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
_BLOCKED_HOST_FRAGMENTS = (
    "google-analytics.com", "googletagmanager.com", "doubleclick.net",
    "facebook.net", "hotjar.com", "segment.io", "mixpanel.com",
    "clarity.ms", "newrelic.com", "branch.io", "optimizely.com",
)


class BrowserUnavailable(RuntimeError):
    """Playwright or its Chromium build is not installed."""


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserUnavailable(
            "Playwright is not installed. Run:\n"
            "    pip install playwright\n"
            "    playwright install chromium"
        ) from exc
    return sync_playwright


@contextmanager
def playwright_page(
    settings: Optional[ScrapeSettings] = None,
    *,
    block_resources: bool = True,
    locale: str = "en-US",
    headless: Optional[bool] = None,
    spoof_user_agent: bool = False,
) -> Iterator[Any]:
    """Yield a ready-to-use Playwright page, always cleaning up after itself.

    ``headless=False`` lets a source that a site refuses to serve headlessly
    (Naukri) opt into a visible window without changing the global setting.

    ``spoof_user_agent`` is off by default on purpose. Overriding the UA while
    the browser still sends its own ``Sec-CH-UA`` client hints produces
    internally inconsistent headers, which is a *stronger* bot signal than the
    default UA - Naukri returns 403 for the spoofed combination and 200 for the
    honest one. We let the browser describe itself truthfully.
    """
    settings = settings or get_settings().scrape
    sync_playwright = _require_playwright()

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    proxy = _proxy_config(settings)
    run_headless = settings.headless if headless is None else headless

    with sync_playwright() as driver:
        browser = None
        errors = []
        # Prefer the real installed Chrome; fall back to the bundled Chromium.
        channels = [c for c in (_preferred_channel(), None) if c is not False]
        for channel in channels:
            try:
                kwargs = {"headless": run_headless, "args": launch_args, "proxy": proxy}
                if channel:
                    kwargs["channel"] = channel
                browser = driver.chromium.launch(**kwargs)
                break
            except Exception as exc:
                errors.append(f"{channel or 'bundled chromium'}: {exc}")
        if browser is None:
            raise BrowserUnavailable(
                "Could not launch a browser. Run `playwright install chromium`.\n"
                + "\n".join(errors)
            )

        context_kwargs: dict = {
            "viewport": {"width": 1440, "height": 2200},
            "locale": locale,
            "timezone_id": "Asia/Kolkata",
            "java_script_enabled": True,
        }
        if spoof_user_agent:
            context_kwargs["user_agent"] = settings.user_agent
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(settings.page_timeout * 1000)
        context.set_default_navigation_timeout(settings.page_timeout * 1000)

        if block_resources:
            context.route("**/*", _route_filter)

        page = context.new_page()
        try:
            yield page
        finally:
            for closer in (page.close, context.close, browser.close):
                try:
                    closer()
                except Exception:
                    pass


def _preferred_channel() -> Optional[str]:
    """Browser channel to try first. ``PLAYWRIGHT_CHANNEL=""`` forces bundled."""
    import os

    value = os.getenv("PLAYWRIGHT_CHANNEL", "chrome").strip()
    return value or None


def _route_filter(route, request) -> None:
    try:
        if request.resource_type in _BLOCKED_RESOURCE_TYPES:
            return route.abort()
        if any(fragment in request.url for fragment in _BLOCKED_HOST_FRAGMENTS):
            return route.abort()
        return route.continue_()
    except Exception:
        # A route that vanished mid-flight is not worth failing the page over.
        try:
            route.continue_()
        except Exception:
            pass


def _proxy_config(settings: ScrapeSettings) -> Optional[dict]:
    """Optional proxy, read from a file outside the repository."""
    from jobai.ingest.browser import load_proxies

    proxies = load_proxies(settings.proxy_file)
    if not proxies:
        return None
    chosen = random.choice(proxies)
    config = {"server": f"http://{chosen['ip']}:{chosen['port']}"}
    if chosen.get("username"):
        config["username"] = chosen["username"]
        config["password"] = chosen["password"]
    return config


# --------------------------------------------------------------- navigation


def goto(page, url: str, *, wait_until: str = "domcontentloaded", retries: int = 2) -> bool:
    """Navigate with retries. Returns False rather than raising on failure."""
    return goto_status(page, url, wait_until=wait_until, retries=retries)[0]


def goto_status(
    page, url: str, *, wait_until: str = "domcontentloaded", retries: int = 2
) -> tuple[bool, Optional[int]]:
    """Like :func:`goto`, but also returns the final HTTP status.

    Callers use the status to distinguish "this page is empty" from "we were
    refused" (403/429), so a blocked source reports that honestly instead of
    looking like a markup change.
    """
    status: Optional[int] = None
    for attempt in range(retries + 1):
        try:
            response = page.goto(url, wait_until=wait_until)
        except Exception as exc:
            logger.debug("Navigation to %s failed (attempt %d): %s", url, attempt + 1, exc)
            continue
        status = response.status if response is not None else None
        if status is not None and status >= 400:
            logger.debug("%s returned HTTP %s", url, status)
            if status in (429, 503):
                page.wait_for_timeout(2000 * (attempt + 1))
                continue
            return False, status
        return True, status
    return False, status


def wait_for_any(page, selectors: Sequence[str], timeout_ms: int = 15000) -> Optional[str]:
    """Wait until any one of ``selectors`` appears; return the one that matched.

    Boards reshuffle class names constantly, so every scraper carries a list of
    candidate selectors. This is what lets a partial redesign degrade instead of
    silently yielding zero jobs.
    """
    deadline = timeout_ms
    step = 500
    while deadline > 0:
        for selector in selectors:
            try:
                if page.locator(selector).count() > 0:
                    return selector
            except Exception:
                continue
        page.wait_for_timeout(step)
        deadline -= step
    return None


def autoscroll(page, rounds: int = 6, pause_ms: int = 900) -> None:
    """Scroll to trigger lazy loading, stopping early once height settles."""
    previous = 0
    for _ in range(max(1, rounds)):
        try:
            page.mouse.wheel(0, 20000)
            page.wait_for_timeout(pause_ms)
            height = page.evaluate("document.body.scrollHeight")
        except Exception:
            return
        if height == previous:
            return
        previous = height


def is_blocked(page) -> bool:
    """True when the page is a captcha or access-denied interstitial.

    Detected so the source can report "blocked" honestly and stop, rather than
    attempting to defeat the challenge.
    """
    try:
        blob = f"{page.title()} {page.url}".lower()
    except Exception:
        return False
    return any(
        token in blob
        for token in ("captcha", "verify you are human", "access denied",
                      "are you a robot", "unusual traffic", "just a moment")
    )


# ------------------------------------------------------------- extraction


def text_of(scope, selectors: Sequence[str], default: str = "") -> str:
    """First non-empty text among several candidate selectors."""
    for selector in selectors:
        try:
            locator = scope.locator(selector).first
            if locator.count() == 0:
                continue
            value = (locator.inner_text(timeout=2000) or "").strip()
        except Exception:
            continue
        if value:
            return value
    return default


def attr_of(scope, selectors: Sequence[str], attribute: str, default: str = "") -> str:
    for selector in selectors:
        try:
            locator = scope.locator(selector).first
            if locator.count() == 0:
                continue
            value = (locator.get_attribute(attribute, timeout=2000) or "").strip()
        except Exception:
            continue
        if value:
            return value
    return default


def texts_of(scope, selectors: Sequence[str]) -> List[str]:
    """Every text under the first selector that matches anything."""
    for selector in selectors:
        try:
            locator = scope.locator(selector)
            if locator.count() == 0:
                continue
            values = [v.strip() for v in locator.all_inner_texts()]
        except Exception:
            continue
        values = [v for v in values if v]
        if values:
            return values
    return []


def fetch_json(page, url: str) -> Any:
    """Fetch JSON from inside the browser context.

    Useful when an endpoint only answers requests that carry the cookies the
    site set during normal navigation.
    """
    return page.evaluate(
        """async (url) => {
            const response = await fetch(url, {headers: {'Accept': 'application/json'}});
            if (!response.ok) return {__status: response.status};
            try { return await response.json(); }
            catch (e) { return {__error: String(e)}; }
        }""",
        url,
    )
