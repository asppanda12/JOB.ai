"""Ingestion contract and the failure-isolating runner.

The hard rule: **one source failing must never stop the others**. LinkedIn
changing a class name, Naukri rate-limiting, a Selenium binary missing - each
is caught per source, recorded on that source's :class:`SourceResult`, and the
run continues with whatever the other sources returned.
"""

from __future__ import annotations

import logging
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from jobai.config import ScrapeSettings, get_settings
from jobai.schema import Job

logger = logging.getLogger(__name__)


@dataclass
class SourceResult:
    source: str
    jobs: List[Job] = field(default_factory=list)
    ok: bool = True
    error: str = ""
    traceback: str = ""
    duration: float = 0.0
    pages_fetched: int = 0
    partial: bool = False  # some pages worked, some did not

    @property
    def count(self) -> int:
        return len(self.jobs)

    def summary(self) -> Dict[str, Any]:
        return {
            "source": self.source, "ok": self.ok, "jobs": self.count,
            "pages": self.pages_fetched, "partial": self.partial,
            "duration_s": round(self.duration, 1), "error": self.error,
        }


class JobSource(ABC):
    """Base class for a job source."""

    name: str = "unknown"

    def __init__(self, settings: Optional[ScrapeSettings] = None):
        self.settings = settings or get_settings().scrape
        self._last_request = 0.0

    def throttle(self, factor: float = 1.0) -> None:
        """Keep request rates polite. Never removed, never configurable to zero."""
        delay = max(0.5, self.settings.request_delay * factor)
        elapsed = time.monotonic() - self._last_request
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.monotonic()

    @abstractmethod
    def fetch(self, limit: Optional[int] = None) -> Iterable[Job]:
        """Yield canonical jobs. May raise; the runner isolates the failure."""

    def run(self, limit: Optional[int] = None) -> SourceResult:
        result = SourceResult(source=self.name)
        started = time.monotonic()
        try:
            result.jobs = [job.finalize() for job in self.fetch(limit=limit)]
        except Exception as exc:
            result.ok = False
            result.error = f"{type(exc).__name__}: {exc}"
            result.traceback = traceback.format_exc()
            logger.error("Source %s failed: %s", self.name, result.error)
        finally:
            result.duration = time.monotonic() - started
            result.pages_fetched = getattr(self, "_pages_fetched", 0)
            result.partial = getattr(self, "_partial", False)
        logger.info("Source %s: %s", self.name, result.summary())
        return result


def run_sources(
    sources: Sequence[JobSource],
    *,
    limit_per_source: Optional[int] = None,
) -> Dict[str, SourceResult]:
    """Run every source, isolating failures. Always returns one entry per source."""
    results: Dict[str, SourceResult] = {}
    for source in sources:
        try:
            results[source.name] = source.run(limit=limit_per_source)
        except Exception as exc:
            # Defence in depth: even a broken run() must not abort the batch.
            logger.exception("Source %s crashed outside run()", source.name)
            results[source.name] = SourceResult(
                source=source.name, ok=False, error=f"{type(exc).__name__}: {exc}"
            )
    succeeded = [r for r in results.values() if r.ok]
    logger.info(
        "Ingestion complete: %d/%d sources ok, %d jobs",
        len(succeeded), len(results), sum(r.count for r in results.values()),
    )
    return results


def all_jobs(results: Dict[str, SourceResult]) -> List[Job]:
    out: List[Job] = []
    for result in results.values():
        out.extend(result.jobs)
    return out
