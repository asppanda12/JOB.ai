"""Job parsing, formerly via the Hugging Face hosted inference API.

The endpoint call is gone; this now delegates to
:func:`genrativeai.response_llama.parse_job_data_llama`, which runs on local
Ollama. The name and signature are unchanged because
``Linkedin/create_json_linkedin.py`` and ``naukri/create_json_naukri.py``
import it directly.
"""

from __future__ import annotations

from genrativeai.response_llama import parse_job_data_llama

__all__ = ["parse_job_data_llama"]
