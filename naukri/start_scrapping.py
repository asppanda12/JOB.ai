"""Scrape Naukri jobs.

The scraping itself lives in :mod:`jobai.ingest.naukri`; this stays as the
familiar entry point. It drives a real browser over Naukri's public search pages; the module docstring explains why the JSON API is not used.

    python -m naukri.start_scrapping
    python -m naukri.start_scrapping --keywords "machine learning engineer" --locations bangalore --limit 50

Credentials are never read from source: configure behaviour through the
environment (see ``.env.example``).
"""

from __future__ import annotations

import argparse
import json
import logging

from jobai.ingest.naukri import NaukriSource
from jobai.ingest.scripts import resolve, write_json

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = "naukri/naukri_job_listings.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Naukri job postings")
    parser.add_argument("--keywords", nargs="*", default=None)
    parser.add_argument("--locations", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None, help="max jobs (default: SCRAPER_MAX_JOBS_PER_SOURCE)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--index", action="store_true", help="also store and index the results")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s"
    )

    result = NaukriSource(keywords=args.keywords, locations=args.locations).run(limit=args.limit)
    print(json.dumps(result.summary(), indent=2))

    write_json(resolve(args.output), [job.to_legacy_metadata() for job in result.jobs])
    logger.info("Wrote %d jobs to %s", result.count, resolve(args.output))

    if args.index and result.jobs:
        from jobai.dedup import deduplicate
        from jobai.index_builder import index_jobs
        from jobai.store import get_store

        canonical, _ = deduplicate(result.jobs)
        try:
            store = get_store()
            store.require()
            store.upsert_jobs(canonical)
        except Exception as exc:
            logger.error("Could not write to MongoDB: %s", exc)
        logger.info("Index: %s", index_jobs(canonical))

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
