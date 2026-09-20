"""Experience-label parsing.

This used to send one request per job to ``meta-llama/llama-3.1-8b-instruct``
through OpenRouter - with the API key hard-coded in the source - purely to turn
strings like ``"2+ years"`` or ``"SDE2"`` into a numeric range. That is a
network round trip for something a regex settles, so it now calls
:func:`jobai.normalize.experience.parse_experience`.

The function keeps its old name and tuple return so
``data_cleaning/clean_data_linkedin.py`` is unaffected. Note the unit change:
the old prompt asked for **months** and returned ``(24, 500)`` for "2+ years",
while the rest of the pipeline (the FAISS ``yoe`` metadata, the Telegram
filter) has always worked in **years**. This returns years, which is what every
consumer actually expected.
"""

from __future__ import annotations

from typing import Tuple, Union

from jobai.normalize.experience import parse_experience


def parse_job_data_llama(job_label: str) -> Tuple[Union[float, str], Union[float, str]]:
    """``"2-5 Yrs"`` -> ``(2.0, 5.0)``; unrecognised -> ``("unknown", "unknown")``."""
    low, high = parse_experience(job_label)
    if low is None:
        return ("unknown", "unknown")
    return (low, high)


if __name__ == "__main__":
    for label in ["2+ years", "0-2 years", "5+ yrs", "SDE2", "Senior", "Not disclosed"]:
        print(f"{label!r} -> {parse_job_data_llama(label)}")
