"""Normalize raw linkedin scraper output into the canonical job schema.

Previously this file hard-coded its input and output paths to
``E:\\JOB.ai\\JOB.ai\\...`` and called a hosted LLM once per job. It is now a
thin wrapper over :mod:`jobai.ingest.scripts` with configurable paths and the
shared local model.

    python -m Linkedin/create_json_linkedin --input <raw.json> --output <parsed.json>
    python -m Linkedin/create_json_linkedin --no-llm      # rule-based only, no Ollama needed

For a full run, prefer: ``python -m jobai ingest --sources linkedin``
"""

from __future__ import annotations

from jobai.ingest.scripts import run_script

DEFAULT_INPUT = "Linkedin/linkedin_raw_jobs.json"
DEFAULT_OUTPUT = "Linkedin/linkedin_parsed_jobs.json"


def main() -> int:
    return run_script(
        "Normalize raw linkedin jobs into the canonical schema",
        source="linkedin",
        default_in=DEFAULT_INPUT,
        default_out=DEFAULT_OUTPUT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
