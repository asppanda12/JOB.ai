"""Resume PDF -> structured profile.

``extract_pdf_text(path)`` keeps its original name and return value (the parsed
profile dict) because ``telegram_bot.py`` stores the result as ``resume_json``.

Three things changed underneath:

* the Groq ``llama-3.3-70b-versatile`` call is gone; parsing runs on local
  Ollama through :mod:`jobai.llm`, so no external API key is needed;
* the result is cached by a hash of the resume text, so re-registering or
  re-running does not re-parse the same document;
* it no longer writes every user's profile over a shared ``Ruddhis_job.json``
  in the working directory.

The returned dict is a superset of the old shape: the legacy ``Skills`` and
``area_of_expertise`` keys are still present for existing consumers, alongside
the richer canonical profile.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from jobai.profile import build_profile, extract_pdf_text as _extract_text

logger = logging.getLogger(__name__)


def extract_text(pdf_path: str) -> str:
    """Raw text of a PDF resume."""
    return _extract_text(pdf_path)


def entity_search(resume_text: str, api_key: Any = None) -> Dict[str, Any]:
    """Resume text -> structured profile.

    ``api_key`` is accepted and ignored so old call sites keep working; the
    local model needs no key.
    """
    if api_key:
        logger.debug("Ignoring the api_key argument: JOB.ai runs on local Ollama.")
    return _with_legacy_keys(build_profile(resume_text))


def extract_pdf_text(pdf_path: str) -> Dict[str, Any]:
    """Read a resume PDF and return its structured profile (cached)."""
    return _with_legacy_keys(build_profile(_extract_text(pdf_path)))


def _with_legacy_keys(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Add the old key spellings so pre-upgrade consumers keep working."""
    enriched = dict(profile)
    enriched.setdefault("Skills", profile.get("skills", []))
    enriched.setdefault("area_of_expertise", profile.get("target_roles", []))
    enriched.setdefault("Years_of_experience", profile.get("years_experience", 0))
    enriched.setdefault("Name", profile.get("name"))
    enriched.setdefault("Phone_number", profile.get("phone"))
    enriched.setdefault("Education", profile.get("education", []))
    enriched.setdefault("professional_experience", profile.get("experience", []))
    return enriched


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m resume_cold_mail.pdf_data_extractor <resume.pdf>")
        raise SystemExit(2)
    print(json.dumps(extract_pdf_text(sys.argv[1]), indent=2, ensure_ascii=False))
