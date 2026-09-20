"""Merge every cleaned source into MongoDB and the search indexes.

The original script listed seven absolute ``E:\\JOB.ai\\JOB.ai\\cleaned\\*.json``
paths, wiped ``USER_1.JOB_Data`` with ``delete_many({})`` on every run, and
re-inserted everything with a fresh ``job_indx`` - which invalidated every
Telegram callback button that referenced the old indices and forced a full
re-embed downstream.

It now discovers the cleaned files, normalizes and deduplicates them, and
*upserts* by ``job_id``, so existing data survives and only changed jobs are
re-embedded.

    python -m combined_single_data.master_data
    python -m combined_single_data.master_data --files cleaned/linkedin.json cleaned/naukri.json
    python -m combined_single_data.master_data --no-index      # store only
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List

from jobai.config import PROJECT_ROOT
from jobai.dedup import deduplicate
from jobai.index_builder import index_jobs
from jobai.ingest.legacy import _read_records, job_from_legacy_record
from jobai.ingest.scripts import resolve, write_json
from jobai.schema import Job

logger = logging.getLogger(__name__)

DEFAULT_GLOBS = ["cleaned/*.json"]
DEFAULT_OUTPUT = "combined_single_data/concatenated_jobs.json"


def discover(globs: List[str]) -> List[Path]:
    found: List[Path] = []
    for pattern in globs:
        found.extend(sorted(PROJECT_ROOT.glob(pattern)))
    return [p for p in found if p.is_file()]


def concatenate_job_files(paths: List[Path]) -> List[Job]:
    jobs: List[Job] = []
    for path in paths:
        records = _read_records(path)
        source = path.stem.replace("cleaned_", "").replace("_jobs", "")
        count = 0
        for record in records:
            try:
                job = job_from_legacy_record(record, source)
            except Exception as exc:
                logger.debug("Bad record in %s: %s", path.name, exc)
                continue
            if job is not None:
                jobs.append(job)
                count += 1
        logger.info("Loaded %d jobs from %s", count, path.name)
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge cleaned jobs into MongoDB and the indexes")
    parser.add_argument("--files", nargs="*", default=None, help="explicit cleaned JSON files")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--no-store", action="store_true")
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s"
    )

    paths = [resolve(f) for f in args.files] if args.files else discover(DEFAULT_GLOBS)
    if not paths:
        logger.error("No cleaned job files found. Run the per-source cleaning scripts first.")
        return 1

    jobs = concatenate_job_files(paths)
    if not jobs:
        logger.error("No usable jobs in %d file(s).", len(paths))
        return 1

    canonical, stats = deduplicate(jobs)
    logger.info("Dedup: %s", stats)
    write_json(resolve(args.output), [job.to_legacy_metadata() for job in canonical])

    if not args.no_store:
        from jobai.store import get_store

        store = get_store()
        store.require()
        store.ensure_indexes()
        logger.info("Store: %s", store.upsert_jobs(canonical))

    if not args.no_index:
        logger.info("Index: %s", index_jobs(canonical))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
