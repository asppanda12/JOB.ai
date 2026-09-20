"""The canonical job schema plus adapters to and from the legacy dict shape.

Every source normalizes into :class:`Job`. Nothing downstream of ingestion
should ever see a source-specific dict again.

Backward compatibility matters more than tidiness here: the FAISS docstore
already on disk holds documents whose ``metadata`` is the legacy flat dict
(``job_title``, ``company_name``, ``job_link``, ``yoe`` as a ``"min,max"``
string, ``job_indx``, ...) and the Telegram bot reads exactly those keys.  So
:meth:`Job.to_legacy_metadata` emits that dict verbatim, and
:meth:`Job.from_legacy` reads it back.  New fields ride along as extra keys,
which the old consumers simply ignore.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlsplit, urlunsplit

# Query parameters that carry tracking noise rather than job identity. Dropping
# them is what lets the same posting scraped twice collapse to one canonical URL.
_TRACKING_PARAMS = {
    "refid", "trackingid", "position", "pagenum", "trk", "src", "source",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "originalsubdomain", "eburl", "referer", "referrer", "gclid", "fbclid",
}

_DEFAULT_YOE = (0.0, 60.0)


def canonical_url(url: str) -> str:
    """Strip tracking noise so the same posting yields the same URL."""
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.scheme and not parts.netloc:
        return url
    kept = []
    for chunk in parts.query.split("&"):
        if not chunk:
            continue
        key = chunk.split("=", 1)[0].lower()
        if key in _TRACKING_PARAMS:
            continue
        kept.append(chunk)
    # The host is lowercased but otherwise left alone: stripping "www." would
    # produce a tidier key at the cost of handing the user a link that some
    # sites reject. Host folding belongs in the dedup key, not here.
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", netloc, path, "&".join(sorted(kept)), ""))


def url_dedup_key(url: str) -> str:
    """Canonical URL folded further, for duplicate detection only.

    Drops the ``www.``/country subdomain so ``in.linkedin.com/jobs/view/123``
    and ``www.linkedin.com/jobs/view/123`` collapse to one job.
    """
    canonical = canonical_url(url)
    if not canonical:
        return ""
    try:
        parts = urlsplit(canonical)
    except ValueError:
        return canonical
    host = re.sub(r"^(?:www|in|uk|us|ca|au)\.", "", parts.netloc)
    return urlunsplit(("https", host, parts.path, parts.query, ""))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def _as_list(value: Any) -> List[str]:
    """Accept the several shapes the legacy pipeline used for skills."""
    if value is None:
        return []
    if isinstance(value, str):
        if not value.strip() or value.strip().upper() == "N/A":
            return []
        parts = re.split(r"[,;|\n]|\s{2,}", value)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            out.extend(_as_list(item))
        return out
    return [str(value)]


def _parse_date(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[: len(fmt) + 6], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Job:
    """One job posting, source-agnostic."""

    title: str = ""
    company: str = ""
    description: str = ""
    source: str = ""
    source_job_id: str = ""
    source_url: str = ""
    application_url: str = ""
    company_url: str = ""

    skills: List[str] = field(default_factory=list)
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)

    experience_min: Optional[float] = None
    experience_max: Optional[float] = None
    experience_raw: str = ""

    location: str = ""
    remote: Optional[bool] = None
    employment_type: str = ""
    salary: str = ""
    industry: str = ""
    job_category: str = ""
    education: List[str] = field(default_factory=list)

    posted_date: Optional[datetime] = None
    scraped_at: Optional[datetime] = None

    raw_text: str = ""
    normalized_text: str = ""
    content_hash: str = ""
    job_id: str = ""

    # Every source that carried this same posting, filled in by deduplication.
    sources: List[Dict[str, str]] = field(default_factory=list)
    # Stable integer the Telegram callback buttons address jobs by.
    job_indx: Optional[int] = None

    # ---------------------------------------------------------------- derived

    def canonical_application_url(self) -> str:
        return canonical_url(self.application_url or self.source_url)

    def experience_band(self) -> str:
        """The ``"min,max"`` string the existing FAISS metadata stores."""
        lo = _DEFAULT_YOE[0] if self.experience_min is None else self.experience_min
        hi = _DEFAULT_YOE[1] if self.experience_max is None else self.experience_max
        return f"{_trim(lo)},{_trim(hi)}"

    def compute_content_hash(self) -> str:
        """Stable fingerprint of the *meaningful* content.

        Only fields that change what the job means feed the hash, so cosmetic
        re-scrapes do not trigger a re-embed (see ``jobai.index_builder``).
        """
        payload = "␟".join(
            [
                _norm_key(self.title),
                _norm_key(self.company),
                _norm_key(self.location),
                _norm_key(self.description)[:4000],
                ",".join(sorted(_norm_key(s) for s in self.skills)),
                self.experience_band(),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def compute_job_id(self) -> str:
        """Deterministic id: prefer the source's own id, else the canonical URL."""
        if self.source and self.source_job_id:
            return f"{_slug(self.source)}:{_slug(str(self.source_job_id))}"
        url = self.canonical_application_url()
        if url:
            return "url:" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]
        return "hash:" + (self.content_hash or self.compute_content_hash())[:24]

    def finalize(self) -> "Job":
        """Fill in the derived fields. Idempotent; safe to call repeatedly."""
        from jobai.normalize.skills import normalize_skills
        from jobai.normalize.text import canonical_job_text

        self.skills = normalize_skills(self.skills)
        self.required_skills = normalize_skills(self.required_skills)
        self.preferred_skills = normalize_skills(self.preferred_skills)
        # Anything explicitly required or preferred is also simply a skill.
        merged = list(dict.fromkeys(self.skills + self.required_skills + self.preferred_skills))
        self.skills = merged

        if self.scraped_at is None:
            self.scraped_at = datetime.now(timezone.utc)
        if not self.raw_text:
            self.raw_text = self.description
        self.normalized_text = canonical_job_text(self)
        self.content_hash = self.compute_content_hash()
        if not self.job_id:
            self.job_id = self.compute_job_id()
        if not self.sources:
            self.sources = [
                {
                    "source": self.source,
                    "source_job_id": str(self.source_job_id or ""),
                    "url": self.canonical_application_url(),
                }
            ]
        return self

    # ------------------------------------------------------------- (de)serial

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key in ("posted_date", "scraped_at"):
            value = data.get(key)
            data[key] = value.isoformat() if isinstance(value, datetime) else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        allowed = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in (data or {}).items() if k in allowed}
        kwargs["posted_date"] = _parse_date(kwargs.get("posted_date"))
        kwargs["scraped_at"] = _parse_date(kwargs.get("scraped_at"))
        return cls(**kwargs)

    # ------------------------------------------------------------ legacy view

    def to_legacy_metadata(self) -> Dict[str, Any]:
        """The exact flat dict the FAISS docstore and Telegram bot expect.

        Keys ``job_title`` .. ``job_indx`` are the legacy contract and must not
        be renamed. Canonical fields are appended so new code can use them.
        """
        skills_text = " ".join(self.skills)
        return {
            # --- legacy contract (do not rename) ---
            "job_title": self.title or "N/A",
            "job_link": self.canonical_application_url() or "N/A",
            "company_name": self.company or "N/A",
            "experience": self.experience_raw or "N/A",
            "salary": self.salary or "N/A",
            "location": self.location or "N/A",
            "job_description": self.description or "",
            "years_of_experience": self.experience_raw or "",
            "skills": skills_text,
            "job_type": self.job_category or self.employment_type or "N/A",
            "id": self.job_id,
            "text": self.normalized_text,
            "Posted_date": self.posted_date.strftime("%Y-%m-%d") if self.posted_date else None,
            "Source": self.source or "N/A",
            "yoe": self.experience_band(),
            "job_indx": self.job_indx if self.job_indx is not None else 0,
            # --- canonical extras (ignored by legacy consumers) ---
            "job_id": self.job_id,
            "source_job_id": str(self.source_job_id or ""),
            "content_hash": self.content_hash,
            "skills_list": self.skills,
            "required_skills": self.required_skills,
            "preferred_skills": self.preferred_skills,
            "experience_min": self.experience_min,
            "experience_max": self.experience_max,
            "remote": self.remote,
            "employment_type": self.employment_type,
            "industry": self.industry,
            "job_category": self.job_category,
            "education": self.education,
            "sources": self.sources,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }

    @classmethod
    def from_legacy(cls, data: Dict[str, Any]) -> "Job":
        """Read a legacy job dict (Mongo ``JOB_Data`` row or FAISS metadata)."""
        data = dict(data or {})
        data.pop("_id", None)
        if "job_id" in data and "title" in data:  # already canonical
            return cls.from_dict(data)

        lo, hi = _split_band(data.get("yoe"))
        link = data.get("job_link") or data.get("Job Link") or ""
        indx = data.get("job_indx", data.get("indx"))
        try:
            indx = int(indx) if indx is not None and str(indx) != "" else None
        except (TypeError, ValueError):
            indx = None

        job = cls(
            title=str(data.get("job_title") or data.get("Job Title") or "").strip(),
            company=str(data.get("company_name") or data.get("Company Name") or "").strip(),
            description=str(data.get("job_description") or data.get("Job Description") or "").strip(),
            source=str(data.get("Source") or data.get("source") or "").strip().lower(),
            source_job_id=str(data.get("source_job_id") or ""),
            source_url=str(link),
            application_url=str(link),
            skills=_as_list(data.get("skills_list") or data.get("skills") or data.get("Skills")),
            required_skills=_as_list(data.get("required_skills")),
            preferred_skills=_as_list(data.get("preferred_skills")),
            experience_min=lo,
            experience_max=hi,
            experience_raw=str(data.get("experience") or data.get("Experience") or ""),
            location=str(data.get("location") or data.get("Location") or "").strip(),
            remote=data.get("remote"),
            employment_type=str(data.get("employment_type") or ""),
            salary=str(data.get("salary") or data.get("Salary") or ""),
            industry=str(data.get("industry") or ""),
            job_category=str(data.get("job_category") or data.get("job_type") or ""),
            education=_as_list(data.get("education")),
            posted_date=_parse_date(data.get("Posted_date") or data.get("posted_date")),
            scraped_at=_parse_date(data.get("scraped_at")),
            raw_text=str(data.get("text") or ""),
            content_hash=str(data.get("content_hash") or ""),
            job_id=str(data.get("job_id") or data.get("id") or ""),
            sources=list(data.get("sources") or []),
            job_indx=indx,
        )
        # The legacy ``id`` was a human-readable concatenation, not a stable id;
        # only keep it if it already looks like a canonical id.
        if job.job_id and ":" not in job.job_id:
            job.job_id = ""
        return job.finalize()


def _trim(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{float(value):g}"


def _norm_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _split_band(value: Any) -> tuple[Optional[float], Optional[float]]:
    """Read ``yoe`` in any of the shapes the legacy code produced."""
    if value is None or value == "":
        return None, None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None, None
    if isinstance(value, str) and "," in value:
        lo, _, hi = value.partition(",")
        try:
            return float(lo), float(hi)
        except ValueError:
            return None, None
    return None, None


def jobs_to_legacy(jobs: Sequence[Job]) -> List[Dict[str, Any]]:
    return [job.to_legacy_metadata() for job in jobs]
