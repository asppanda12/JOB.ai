"""Transparent match scoring.

The final ordering is not a black box: every signal below is computed
separately, stored on the result, and combined with weights that live in
:class:`jobai.config.ScoringWeights` (all overridable from the environment).
That is what lets a recommendation say "strong skill match, experience
aligned, 2 missing skills, recently posted" instead of "score: 0.73".
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from jobai.config import ScoringWeights, get_settings
from jobai.normalize.experience import experience_overlap
from jobai.normalize.skills import normalize_skills, related_skills, skills_from_metadata
from jobai.schema import _parse_date, _split_band


def freshness_score(posted: Any, half_life_days: Optional[float] = None) -> float:
    """Exponential time decay, configurable half-life.

    Old jobs are down-weighted, never deleted - the decay floors at 0.05 so a
    strong old match can still surface above a weak new one.
    """
    settings = get_settings()
    half_life = half_life_days or settings.retrieval.freshness_half_life_days
    date = _parse_date(posted)
    if date is None or half_life <= 0:
        return 0.5
    age_days = max(0.0, (datetime.now(timezone.utc) - date).total_seconds() / 86400.0)
    return max(0.05, math.pow(0.5, age_days / half_life))


def _skill_coverage(user_skills: set[str], job_skills: Sequence[str]) -> tuple[float, List[str], List[str]]:
    """Fraction of the job's skills the candidate has, plus the matched/missing split.

    A related-but-not-identical skill counts as half a match, so "has PyTorch,
    job wants TensorFlow" is scored as a partial fit rather than a total miss.
    """
    job_skills = [s for s in job_skills if s]
    if not job_skills:
        return 0.5, [], []
    matched: List[str] = []
    missing: List[str] = []
    credit = 0.0
    for skill in job_skills:
        if skill.lower() in user_skills:
            matched.append(skill)
            credit += 1.0
        elif any(r.lower() in user_skills for r in related_skills(skill)):
            matched.append(f"{skill} (related)")
            credit += 0.5
            missing.append(skill)
        else:
            missing.append(skill)
    return credit / len(job_skills), matched, missing


def score_candidate(
    candidate: Dict[str, Any],
    profile: Dict[str, Any],
    weights: Optional[ScoringWeights] = None,
) -> Dict[str, Any]:
    """Attach ``signals``, ``match_score``, ``matched_skills`` and ``missing_skills``."""
    weights = weights or get_settings().weights
    metadata = candidate.get("metadata", candidate)

    user_skills = {s.lower() for s in normalize_skills(profile.get("skills") or [])}
    job_all = skills_from_metadata(metadata)
    job_required = normalize_skills(metadata.get("required_skills") or []) or job_all
    job_preferred = normalize_skills(metadata.get("preferred_skills") or [])

    required_match, matched_req, missing_req = _skill_coverage(user_skills, job_required)
    preferred_match, _, _ = _skill_coverage(user_skills, job_preferred)
    overall_match, matched_all, missing_all = _skill_coverage(user_skills, job_all)

    lo, hi = metadata.get("experience_min"), metadata.get("experience_max")
    if lo is None and hi is None:
        lo, hi = _split_band(metadata.get("yoe"))
    experience_match = experience_overlap(profile.get("years_experience"), lo, hi)

    location_match = _location_match(metadata.get("location"), profile.get("preferred_locations") or [])
    role_match = _role_match(metadata, profile.get("target_roles") or [])

    retriever_scores = candidate.get("retriever_scores", {})
    signals = {
        "semantic_match": float(retriever_scores.get("dense", 0.0)),
        "lexical_match": float(retriever_scores.get("lexical", 0.0)),
        "graph_similarity": float(retriever_scores.get("graph", 0.0)),
        "reranker_score": float(candidate.get("reranker_score", 0.5)),
        "skill_match": overall_match,
        "required_skill_match": required_match,
        "preferred_skill_match": preferred_match,
        "experience_match": experience_match,
        "location_match": location_match,
        "role_match": role_match,
        "freshness": freshness_score(metadata.get("Posted_date") or metadata.get("posted_date")),
        "rrf_score": float(candidate.get("rrf_score", 0.0)),
    }

    weight_map = weights.as_dict()
    total_weight = sum(weight_map.values()) or 1.0
    match_score = sum(weight_map[name] * signals.get(name, 0.0) for name in weight_map) / total_weight

    candidate["signals"] = signals
    candidate["match_score"] = round(match_score, 4)
    candidate["matched_skills"] = matched_req or matched_all
    candidate["missing_skills"] = missing_req[:8]
    candidate["explanation"] = explain(signals, candidate["missing_skills"])
    return candidate


def explain(signals: Dict[str, float], missing_skills: Sequence[str]) -> List[str]:
    """Short, human-readable reasons derived straight from the signals."""
    reasons: List[str] = []
    required = signals.get("required_skill_match", 0.0)
    if required >= 0.75:
        reasons.append("Strong skill match")
    elif required >= 0.45:
        reasons.append("Partial skill match")
    else:
        reasons.append("Limited skill overlap")

    if signals.get("role_match", 0.0) >= 0.7:
        reasons.append("Strong role match")
    experience = signals.get("experience_match", 0.0)
    if experience >= 0.95:
        reasons.append("Experience aligned")
    elif experience <= 0.4:
        reasons.append("Experience band is a stretch")
    if signals.get("location_match", 0.0) >= 0.9:
        reasons.append("Preferred location")
    if signals.get("freshness", 0.0) >= 0.7:
        reasons.append("Recently posted")
    if missing_skills:
        count = len(missing_skills)
        reasons.append(f"{count} missing skill{'s' if count != 1 else ''}")
    return reasons


def _location_match(job_location: Any, preferred: Sequence[str]) -> float:
    if not preferred:
        return 0.5  # no stated preference -> neutral, never penalising
    text = str(job_location or "").lower()
    if not text:
        return 0.3
    for location in preferred:
        location = str(location).strip().lower()
        if location and (location in text or text in location):
            return 1.0
    if "remote" in text or "anywhere" in text:
        return 0.8
    return 0.2


def _role_match(metadata: Dict[str, Any], target_roles: Sequence[str]) -> float:
    if not target_roles:
        return 0.5
    haystack = " ".join(
        [
            str(metadata.get("job_title") or metadata.get("title") or ""),
            str(metadata.get("job_category") or metadata.get("job_type") or ""),
        ]
    ).lower()
    if not haystack.strip():
        return 0.3
    best = 0.0
    for role in target_roles:
        tokens = [t for t in str(role).lower().split() if len(t) > 2]
        if not tokens:
            continue
        overlap = sum(1 for t in tokens if t in haystack) / len(tokens)
        best = max(best, overlap)
    return best


def rank(
    candidates: Sequence[Dict[str, Any]],
    profile: Dict[str, Any],
    weights: Optional[ScoringWeights] = None,
) -> List[Dict[str, Any]]:
    scored = [score_candidate(dict(c), profile, weights) for c in candidates]
    scored.sort(key=lambda c: c["match_score"], reverse=True)
    return scored
