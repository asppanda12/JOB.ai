"""Normalize raw naukri scraper output into the canonical job schema.

Previously this file hard-coded its input and output paths to
``E:\\JOB.ai\\JOB.ai\\...`` and called a hosted LLM once per job. It is now a
thin wrapper over :mod:`jobai.ingest.scripts` with configurable paths and the
shared local model.

    python -m naukri/create_json_naukri --input <raw.json> --output <parsed.json>
    python -m naukri/create_json_naukri --no-llm      # rule-based only, no Ollama needed

For a full run, prefer: ``python -m jobai ingest --sources naukri``
"""

from __future__ import annotations

from jobai.ingest.scripts import run_script

DEFAULT_INPUT = "naukri/naukri_job_listings.json"
DEFAULT_OUTPUT = "naukri/naukri_parsed_jobs.json"


def main() -> int:
    return run_script(
        "Normalize raw naukri jobs into the canonical schema",
        source="naukri",
        default_in=DEFAULT_INPUT,
        default_out=DEFAULT_OUTPUT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
