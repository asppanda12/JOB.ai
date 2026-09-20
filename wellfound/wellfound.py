"""Wellfound source - NOT IMPLEMENTED.

This file previously contained a byte-for-byte copy of the Cuvette scraper:
the function was still called ``scrape_cuvette_jobs``, it navigated to
``cuvette.tech/app/dashboard/other-jobs``, and it wrote ``cuvette_jobs.json``.
It contained no reference to Wellfound at all, so running it silently
re-scraped Cuvette under a misleading name and double-counted those jobs.

The duplicate body has been removed rather than left as a trap. No Wellfound
integration is written here, because adding a source is only worth doing when
it can be done reliably, and reliability matters more than the number of
platforms.

To add Wellfound properly, subclass :class:`jobai.ingest.base.JobSource`,
yield :class:`jobai.schema.Job` instances, and register it in
``jobai/ingest/runner.py:build_sources``. Failure isolation, deduplication,
normalization and indexing are then handled for you.

To scrape Cuvette - which is what this file actually did - use:

    python -m cuvete.start_scrapping
"""

from __future__ import annotations

NOT_IMPLEMENTED_MESSAGE = (
    "wellfound/wellfound.py was a mislabelled duplicate of the Cuvette scraper "
    "and has been retired. Run `python -m cuvete.start_scrapping` for Cuvette, "
    "or implement a real Wellfound JobSource (see this module's docstring)."
)


def scrape_wellfound_jobs():
    raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)


if __name__ == "__main__":
    print(NOT_IMPLEMENTED_MESSAGE)
    raise SystemExit(1)
