"""Clean and deduplicate cuvette jobs.

The three original cleaning scripts each had their own regex ladder for
years-of-experience, their own ``clean_company_name`` and their own
``id``/``text`` construction - which is why the same job could get a different
embedding depending on which script last touched it. All of that now lives in
:mod:`jobai.normalize` and :mod:`jobai.dedup`, so every source is cleaned
identically.

    python -m data_cleaning/clean_data_cuvete --input <parsed.json> --output <cleaned.json>

For a full run, prefer: ``python -m jobai ingest --sources cuvette``
"""

from __future__ import annotations

import json
import logging

from jobai.dedup import deduplicate
from jobai.ingest.legacy import _read_records, job_from_legacy_record
from jobai.ingest.scripts import build_arg_parser, resolve, write_json

logger = logging.getLogger(__name__)

DEFAULT_INPUT = "cuvete/cuevete_parsed_jobs.json"
DEFAULT_OUTPUT = "cleaned/cleaned_cuvete.json"
SOURCE = "cuvette"


def main() -> int:
    args = build_arg_parser(
        "Clean and deduplicate cuvette jobs", DEFAULT_INPUT, DEFAULT_OUTPUT
    ).parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s"
    )

    input_path = resolve(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        return 1

    records = _read_records(input_path)
    if args.limit:
        records = records[: args.limit]

    jobs = []
    for record in records:
        try:
            job = job_from_legacy_record(record, SOURCE)
        except Exception as exc:
            logger.debug("Skipping bad record: %s", exc)
            continue
        if job is not None:
            jobs.append(job)

    canonical, stats = deduplicate(jobs)
    logger.info("Dedup: %s", stats)
    write_json(resolve(args.output), [job.to_legacy_metadata() for job in canonical])
    logger.info("Wrote %d cleaned jobs to %s", len(canonical), resolve(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
