"""Shared backing for the per-source ``create_json_*.py`` / cleaning scripts.

Those scripts each carried their own copy of "read a JSON file, loop, call an
LLM, write a JSON file", with the input and output paths hard-coded to
``E:\\JOB.ai\\JOB.ai\\...``. They are now thin wrappers over the two functions
here, so the behaviour is identical but the paths are arguments and the LLM is
the shared local one.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from jobai.config import PROJECT_ROOT
from jobai.ingest.legacy import _read_records, job_from_legacy_record

logger = logging.getLogger(__name__)


def parse_records(
    input_path: Path,
    output_path: Path,
    source: str,
    *,
    limit: Optional[int] = None,
    use_llm: bool = True,
) -> List[Dict[str, Any]]:
    """Normalize a scraper's raw JSON into canonical job dicts.

    One bad record is logged and skipped; the run continues.
    """
    records = _read_records(Path(input_path))
    if limit:
        records = records[:limit]
    logger.info("Read %d records from %s", len(records), input_path)

    parser = None
    if use_llm:
        from genrativeai.response_llama import parse_job_data_llama

        parser = parse_job_data_llama

    output: List[Dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        try:
            if parser is not None:
                output.append(parser(record))
            else:
                job = job_from_legacy_record(record, source)
                if job is None:
                    continue
                output.append(job.finalize().to_legacy_metadata())
        except Exception as exc:
            logger.error("Skipping record %d: %s", index, exc)
            continue
        if index % 25 == 0:
            logger.info("Processed %d/%d", index, len(records))

    write_json(output_path, output)
    logger.info("Wrote %d jobs to %s", len(output), output_path)
    return output


def write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def resolve(path: str) -> Path:
    """Resolve a path relative to the repository root when it is not absolute."""
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate)


def build_arg_parser(description: str, default_in: str, default_out: str):
    import argparse

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input", default=default_in, help="raw scraper JSON (relative paths resolve to the repo root)")
    parser.add_argument("--output", default=default_out, help="where to write the normalized jobs")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-llm", action="store_true", help="rule-based normalization only (no Ollama)")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_script(description: str, source: str, default_in: str, default_out: str, argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser(description, default_in, default_out).parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    input_path = resolve(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        return 1
    parse_records(input_path, resolve(args.output), source, limit=args.limit, use_llm=not args.no_llm)
    return 0
