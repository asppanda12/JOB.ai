"""Shared Selenium plumbing for the browser-driven sources.

Everything here was previously copy-pasted into each scraper: the driver
options, the proxy-extension builder, the retry loop. One copy now, with the
hard-coded Windows paths and bundled credentials removed.

Notes on conduct: the user agent is a normal desktop UA and the request rate is
throttled by :meth:`JobSource.throttle`. There is no anti-bot evasion beyond
looking like an ordinary browser, and no credential handling - if a site
requires a login, the scraper reports that and stops rather than trying to work
around it.
"""

from __future__ import annotations

import logging
import os
import random
import tempfile
import zipfile
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from jobai.config import ScrapeSettings, get_settings

logger = logging.getLogger(__name__)


class BrowserUnavailable(RuntimeError):
    """Chrome or chromedriver could not be started."""


def load_proxies(path: str) -> List[Dict[str, str]]:
    """Read ``ip:port:user:pass`` lines. Missing file simply means no proxy."""
    if not path or not os.path.exists(path):
        return []
    proxies = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.strip().split(":")
            if len(parts) == 4:
                proxies.append(dict(zip(("ip", "port", "username", "password"), parts)))
            elif len(parts) == 2:
                proxies.append({"ip": parts[0], "port": parts[1], "username": "", "password": ""})
    return proxies


def _proxy_extension(proxy: Dict[str, str]) -> str:
    """Build the MV2 auth-proxy extension Chrome needs for authenticated proxies.

    Written to a temp file rather than the repo root, so credentials never land
    next to the source (the old ``proxy_auth.zip`` was committed).
    """
    manifest = """
    {"version":"1.0.0","manifest_version":2,"name":"JOB.ai Proxy",
     "permissions":["proxy","tabs","unlimitedStorage","storage","<all_urls>",
                    "webRequest","webRequestBlocking"],
     "background":{"scripts":["background.js"]},"minimum_chrome_version":"22.0.0"}
    """
    background = """
    var config = {mode:"fixed_servers", rules:{singleProxy:{scheme:"http",
      host:"%s", port:parseInt(%s)}, bypassList:["localhost"]}};
    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
    chrome.webRequest.onAuthRequired.addListener(
      function(details) { return {authCredentials: {username:"%s", password:"%s"}}; },
      {urls: ["<all_urls>"]}, ['blocking']);
    """ % (proxy["ip"], proxy["port"], proxy.get("username", ""), proxy.get("password", ""))

    handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(handle.name, "w") as archive:
        archive.writestr("manifest.json", manifest)
        archive.writestr("background.js", background)
    return handle.name


def build_driver(settings: Optional[ScrapeSettings] = None, proxy: Optional[Dict[str, str]] = None):
    """Start Chrome. Raises :class:`BrowserUnavailable` rather than hanging."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    settings = settings or get_settings().scrape
    options = Options()
    if settings.headless:
        options.add_argument("--headless=new")
    for argument in (
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-notifications",
        "--disable-popup-blocking",
        "--window-size=1440,2400",
        "--lang=en-US",
    ):
        options.add_argument(argument)
    options.add_argument(f"--user-agent={settings.user_agent}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if proxy and proxy.get("username"):
        options.add_extension(_proxy_extension(proxy))
    elif proxy:
        options.add_argument(f"--proxy-server=http://{proxy['ip']}:{proxy['port']}")

    try:
        service = Service(settings.chromedriver_path) if settings.chromedriver_path else Service()
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as exc:
        raise BrowserUnavailable(
            f"Could not start Chrome ({exc}). Install Google Chrome, or set "
            "CHROMEDRIVER_PATH to a matching chromedriver."
        ) from exc

    driver.set_page_load_timeout(settings.page_timeout)
    driver.implicitly_wait(2)
    return driver


@contextmanager
def chrome(settings: Optional[ScrapeSettings] = None):
    """Driver context manager that always quits, even on an exception."""
    settings = settings or get_settings().scrape
    proxies = load_proxies(settings.proxy_file)
    proxy = random.choice(proxies) if proxies else None
    driver = build_driver(settings, proxy)
    try:
        yield driver
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def scroll_page(driver, rounds: int = 5, pause: float = 1.5) -> None:
    """Scroll to trigger lazy loading, stopping early once height settles."""
    import time

    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(max(1, rounds)):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        height = driver.execute_script("return document.body.scrollHeight")
        if height == last_height:
            break
        last_height = height


def text_of(element, default: str = "") -> str:
    try:
        return (element.text or "").strip() or default
    except Exception:
        return default


def first_text(scope, selectors: List[str], default: str = "") -> str:
    """Try several CSS selectors in order.

    Sites reshuffle class names constantly; a list of candidates is what keeps
    a scraper alive across a redesign instead of silently returning "N/A".
    """
    from selenium.webdriver.common.by import By

    for selector in selectors:
        try:
            found = scope.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            continue
        for element in found:
            value = text_of(element)
            if value:
                return value
    return default


def first_attr(scope, selectors: List[str], attribute: str, default: str = "") -> str:
    from selenium.webdriver.common.by import By

    for selector in selectors:
        try:
            found = scope.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            continue
        for element in found:
            try:
                value = (element.get_attribute(attribute) or "").strip()
            except Exception:
                continue
            if value:
                return value
    return default
