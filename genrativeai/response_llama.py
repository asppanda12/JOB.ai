"""Job-posting understanding.

``parse_job_data_llama`` keeps its name and return shape (a flat job dict) so
the ``create_json_*.py`` scripts keep working. It now runs on local Ollama via
:mod:`jobai.llm` instead of Groq's ``llama-3.3-70b-versatile``, and the
``groq_api_key`` argument is accepted and ignored.

``parse_job_data_gemini`` is kept as an alias: it previously pointed at
``gemma2-9b-it`` on Groq, which was a second external provider for the same
task. There is one model now, configured by ``OLLAMA_MODEL``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from jobai.schema import Job

logger = logging.getLogger(__name__)


def parse_job_data_llama(job_data: Dict[str, Any], groq_api_key: Any = None) -> Dict[str, Any]:
    """Normalize one raw scraped job dict into the canonical flat shape.

    Skills, the experience band and the role category come from the local model
    where free text requires it, and from the deterministic normalizers
    otherwise - so this works, with slightly coarser output, even when Ollama
    is stopped.
    """
    if groq_api_key:
        logger.debug("Ignoring groq_api_key: JOB.ai runs on local Ollama.")

    from jobai.ingest.legacy import job_from_legacy_record
    from jobai.llm.tasks import understand_job

    job: Job = job_from_legacy_record(job_data, source=str(job_data.get("Source") or "unknown"))
    if job is None:
        raise ValueError("job_data has no usable title")

    understanding = understand_job(f"{job.title}\n{job.company}\n{job.description}")
    job.required_skills = understanding.get("required_skills") or job.skills
    job.preferred_skills = understanding.get("preferred_skills") or []
    job.job_category = understanding.get("job_category") or job.job_category
    job.industry = understanding.get("industry") or job.industry
    job.employment_type = understanding.get("employment_type") or job.employment_type
    if understanding.get("remote") is not None:
        job.remote = understanding["remote"]
    if job.experience_min is None:
        job.experience_min = understanding.get("experience_min_years")
        job.experience_max = understanding.get("experience_max_years")

    return job.finalize().to_legacy_metadata()


# One model, one code path. Kept so old imports resolve.
parse_job_data_gemini = parse_job_data_llama
