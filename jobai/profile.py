"""Structured user profiles, parsed once and cached.

The legacy flow re-ran the resume through an LLM on every interaction
(``extract_pdf_text`` called the model each time it was invoked, and even wrote
its output to a hard-coded ``Ruddhis_job.json``). Here the resume is parsed
once, keyed by a hash of its text, and the result is cached on disk and on the
user's Mongo document.

Cache keys are content hashes, so two users with different resumes can never
collide, and a user who uploads a revised resume gets it re-parsed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from jobai.config import get_settings
from jobai.normalize.skills import normalize_skills

logger = logging.getLogger(__name__)

EMPTY_PROFILE: Dict[str, Any] = {
    "target_roles": [], "skills": [], "languages": [], "frameworks": [], "cloud": [],
    "databases": [], "years_experience": 0.0, "industries": [], "preferred_locations": [],
    "remote_preference": None, "education": [], "projects": [], "experience": [],
}


def resume_fingerprint(resume_text: str) -> str:
    return hashlib.sha256((resume_text or "").strip().encode("utf-8")).hexdigest()[:32]


def _cache_path(fingerprint: str) -> Path:
    return get_settings().retrieval.profile_cache_path / f"{fingerprint}.json"


def load_cached(fingerprint: str) -> Optional[Dict[str, Any]]:
    path = _cache_path(fingerprint)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Ignoring unreadable profile cache %s: %s", path, exc)
        return None


def save_cached(fingerprint: str, profile: Dict[str, Any]) -> None:
    path = _cache_path(fingerprint)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not write profile cache: %s", exc)


def build_profile(resume_text: str, *, force: bool = False) -> Dict[str, Any]:
    """Resume text -> structured profile, cached by content fingerprint."""
    fingerprint = resume_fingerprint(resume_text)
    if not force:
        cached = load_cached(fingerprint)
        if cached:
            logger.info("Using cached profile %s", fingerprint)
            return cached

    from jobai.llm.tasks import parse_resume

    profile = parse_resume(resume_text)
    profile["_fingerprint"] = fingerprint
    save_cached(fingerprint, profile)
    return profile


def profile_from_pdf(pdf_path: str, *, force: bool = False) -> Dict[str, Any]:
    """Extract text from a PDF resume and build the structured profile."""
    text = extract_pdf_text(pdf_path)
    return build_profile(text, force=force)


def extract_pdf_text(pdf_path: str) -> str:
    """Plain text from a PDF. Raises on an unreadable or empty file."""
    try:
        import pymupdf as fitz
    except ImportError:  # older PyMuPDF
        import fitz

    with fitz.open(pdf_path) as document:
        text = "\n".join(page.get_text() for page in document)
    if not text.strip():
        raise ValueError(f"No extractable text in {pdf_path}. Is it a scanned image?")
    return text


def merge_registration(profile: Dict[str, Any], registration: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay what the user typed during registration onto the parsed resume.

    What the user stated explicitly wins over what the model inferred.
    """
    merged = {**EMPTY_PROFILE, **(profile or {})}
    if registration.get("years_of_experience") not in (None, ""):
        try:
            merged["years_experience"] = float(registration["years_of_experience"])
        except (TypeError, ValueError):
            pass
    for key, source in (("preferred_locations", "preferred_locations"), ("target_roles", "target_roles")):
        value = registration.get(source)
        if value:
            merged[key] = list(value) if isinstance(value, (list, tuple)) else [value]
    for key in ("full_name", "email", "phone_number"):
        if registration.get(key):
            merged.setdefault(key, registration[key])
    merged["skills"] = normalize_skills(merged.get("skills") or [])
    return merged


def profile_for_user(user_document: Dict[str, Any]) -> Dict[str, Any]:
    """Best available profile for a stored user document.

    Order of preference: the cached structured profile, then the legacy
    ``resume_json`` shape (``area_of_expertise`` + ``Skills``) so users who
    registered before this upgrade keep working without re-uploading.
    """
    if not user_document:
        return dict(EMPTY_PROFILE)

    profile = user_document.get("profile")
    if isinstance(profile, dict) and profile.get("skills"):
        return merge_registration(profile, user_document)

    legacy = user_document.get("resume_json") or {}
    converted = dict(EMPTY_PROFILE)
    converted["skills"] = normalize_skills(
        list(legacy.get("Skills") or []) + list(legacy.get("skills") or [])
    )
    converted["target_roles"] = [
        str(r) for r in (legacy.get("area_of_expertise") or legacy.get("target_roles") or [])
    ]
    try:
        converted["years_experience"] = float(
            user_document.get("years_of_experience") or legacy.get("Years_of_experience") or 0
        )
    except (TypeError, ValueError):
        converted["years_experience"] = 0.0
    return merge_registration(converted, user_document)
