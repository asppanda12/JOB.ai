"""Deterministic years-of-experience parsing.

The legacy pipeline had three near-identical regex ladders (one per cleaning
script) plus an LLM round-trip per job in ``llama/create_yoe.py`` just to turn
"2+ years" into ``(24, 500)``.  That is one network call per job for something
a regex settles; the ladders are consolidated here and the LLM is out of the
loop.  Values are in **years**, matching what the FAISS ``yoe`` metadata and
the Telegram filter already assume.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Upper sentinel for "and above". 60 is what the existing vector-store metadata
# uses ("0,60"), so keep it for compatibility with the persisted index.
OPEN_ENDED = 60.0

_NUM = r"(\d+(?:\.\d+)?)"
_YEAR = r"(?:years?|yrs?|y)\b"

_PATTERNS: list[tuple[str, callable]] = [
    # "2 - 5 years", "2-5 yrs", "2 to 5 years"
    (rf"{_NUM}\s*(?:-|–|—|to)\s*{_NUM}\s*\+?\s*{_YEAR}", lambda m: (float(m.group(1)), float(m.group(2)))),
    # "minimum 3 years", "at least 3 years"
    (rf"(?:min(?:imum)?|at\s*least|over|more\s*than|greater\s*than)\s*{_NUM}\s*\+?\s*{_YEAR}",
     lambda m: (float(m.group(1)), OPEN_ENDED)),
    # "3+ years"
    (rf"{_NUM}\s*\+\s*{_YEAR}", lambda m: (float(m.group(1)), OPEN_ENDED)),
    # "up to 5 years", "less than 5 years", "under 5 years"
    (rf"(?:up\s*to|less\s*than|under|below|max(?:imum)?)\s*{_NUM}\s*{_YEAR}",
     lambda m: (0.0, float(m.group(1)))),
    # "5 years of experience"
    (rf"{_NUM}\s*{_YEAR}", lambda m: (float(m.group(1)), float(m.group(1)))),
    # Bare "2 - 5" with no unit, e.g. Naukri's "2-5 Yrs" after unit stripping.
    (rf"^{_NUM}\s*(?:-|–|to)\s*{_NUM}$", lambda m: (float(m.group(1)), float(m.group(2)))),
]

# Level labels the old code paid an LLM call to decode.
_LEVEL_BANDS: dict[str, Tuple[float, float]] = {
    "intern": (0.0, 1.0),
    "internship": (0.0, 1.0),
    "fresher": (0.0, 1.0),
    "entry level": (0.0, 2.0),
    "entry-level": (0.0, 2.0),
    "graduate": (0.0, 2.0),
    "junior": (0.0, 2.0),
    "associate": (1.0, 3.0),
    "mid level": (2.0, 5.0),
    "mid-level": (2.0, 5.0),
    "mid senior": (3.0, 7.0),
    "mid-senior level": (3.0, 7.0),
    "senior": (5.0, OPEN_ENDED),
    "staff": (8.0, OPEN_ENDED),
    "principal": (10.0, OPEN_ENDED),
    "lead": (6.0, OPEN_ENDED),
    "manager": (6.0, OPEN_ENDED),
    "director": (10.0, OPEN_ENDED),
    "sde1": (0.0, 3.0),
    "sde 1": (0.0, 3.0),
    "sde-1": (0.0, 3.0),
    "sde2": (3.0, 6.0),
    "sde 2": (3.0, 6.0),
    "sde-2": (3.0, 6.0),
    "sde3": (6.0, OPEN_ENDED),
    "sde 3": (6.0, OPEN_ENDED),
    "ic2": (1.0, 3.0),
    "ic3": (3.0, 6.0),
    "ic4": (5.0, 9.0),
    "l3": (0.0, 3.0),
    "l4": (2.0, 5.0),
    "l5": (5.0, 9.0),
}


def parse_experience(text: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """Return ``(min_years, max_years)``, or ``(None, None)`` when unknown.

    ``(None, None)`` is deliberately distinct from ``(0, 60)``: the caller
    decides whether "unknown" should mean "matches everyone" (the legacy
    behaviour, preserved in :meth:`Job.experience_band`) or be surfaced as a
    missing field.
    """
    if not text:
        return None, None
    normalized = re.sub(r"\s+", " ", str(text)).strip().lower()
    if not normalized or normalized in {"n/a", "na", "not specified", "not disclosed", "none"}:
        return None, None

    # Months, e.g. "6 months".
    month = re.search(rf"{_NUM}\s*months?\b", normalized)
    if month and not re.search(_YEAR, normalized):
        years = round(float(month.group(1)) / 12.0, 2)
        return 0.0, max(years, 0.5)

    for pattern, builder in _PATTERNS:
        match = re.search(pattern, normalized)
        if match:
            lo, hi = builder(match)
            if lo > hi:
                lo, hi = hi, lo
            return _clamp(lo), _clamp(hi)

    for label, band in _LEVEL_BANDS.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(label) + r"(?![a-z0-9])", normalized):
            return band

    return None, None


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), OPEN_ENDED))


def experience_overlap(
    user_years: Optional[float],
    job_min: Optional[float],
    job_max: Optional[float],
) -> float:
    """Score in ``[0, 1]`` for how well a candidate fits a job's band.

    Inside the band scores 1.0; outside it decays linearly over two years, so a
    candidate one year short is still a near-miss rather than a hard reject.
    """
    if user_years is None:
        return 0.5
    lo = 0.0 if job_min is None else job_min
    hi = OPEN_ENDED if job_max is None else job_max
    if lo <= user_years <= hi:
        return 1.0
    distance = lo - user_years if user_years < lo else user_years - hi
    return max(0.0, 1.0 - distance / 2.0)
