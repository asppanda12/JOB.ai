"""Canonical schema, legacy round-tripping and URL canonicalization."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from jobai.schema import Job, canonical_url, url_dedup_key


def test_finalize_fills_derived_fields(job_factory):
    job = job_factory()
    assert job.job_id == "linkedin:1001"
    assert job.content_hash and len(job.content_hash) == 64
    assert "Job Title: Machine Learning Engineer" in job.normalized_text
    assert job.sources == [
        {"source": "linkedin", "source_job_id": "1001",
         "url": "https://in.linkedin.com/jobs/view/ml-engineer-1001"}
    ]


def test_finalize_is_idempotent(job_factory):
    job = job_factory()
    first = (job.job_id, job.content_hash, job.normalized_text)
    job.finalize().finalize()
    assert (job.job_id, job.content_hash, job.normalized_text) == first


def test_content_hash_ignores_cosmetic_change(job_factory):
    """A re-scrape that only changes the salary must not trigger a re-embed."""
    a = job_factory()
    b = job_factory(salary="Rs. 20 LPA")
    assert a.content_hash == b.content_hash


def test_content_hash_tracks_meaningful_change(job_factory):
    a = job_factory()
    b = job_factory(description="Completely different responsibilities.")
    assert a.content_hash != b.content_hash


def test_experience_band_defaults_to_open_range():
    job = Job(title="X", company="Y").finalize()
    assert job.experience_band() == "0,60"


def test_legacy_round_trip(job_factory):
    original = job_factory()
    restored = Job.from_legacy(original.to_legacy_metadata())
    assert restored.title == original.title
    assert restored.company == original.company
    assert restored.job_id == original.job_id
    assert restored.experience_band() == original.experience_band()
    assert set(restored.skills) == set(original.skills)


def test_legacy_metadata_keeps_the_old_contract(job_factory):
    metadata = job_factory().to_legacy_metadata()
    for key in ("job_title", "job_link", "company_name", "experience", "salary",
                "location", "job_description", "years_of_experience", "skills",
                "job_type", "id", "text", "Posted_date", "Source", "yoe", "job_indx"):
        assert key in metadata, f"legacy key {key} disappeared"
    assert isinstance(metadata["skills"], str), "legacy consumers expect a joined string"


def test_reads_raw_scraper_key_spellings():
    job = Job.from_legacy(
        {"Job Title": "Data Scientist", "Company Name": "Globex",
         "Location": "Pune", "Skills": ["python", "sql"], "yoe": "1,4"}
    )
    assert job.title == "Data Scientist"
    assert job.company == "Globex"
    assert job.skills == ["Python", "SQL"]
    assert (job.experience_min, job.experience_max) == (1.0, 4.0)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.naukri.com/job-x-1?refId=A&utm_source=b", "https://www.naukri.com/job-x-1"),
        ("https://in.linkedin.com/jobs/view/a-123?position=1&trackingId=z", "https://in.linkedin.com/jobs/view/a-123"),
        ("", ""),
    ],
)
def test_canonical_url_strips_tracking(url, expected):
    assert canonical_url(url) == expected


def test_canonical_url_keeps_www_but_dedup_key_folds_it():
    """The application link must stay valid; only the dedup key is folded."""
    assert canonical_url("https://www.naukri.com/x").startswith("https://www.naukri.com")
    assert url_dedup_key("https://www.naukri.com/x") == url_dedup_key("https://naukri.com/x")
    assert url_dedup_key("https://in.linkedin.com/jobs/view/a-1") == url_dedup_key(
        "https://www.linkedin.com/jobs/view/a-1"
    )


def test_missing_and_malformed_fields_do_not_raise():
    assert Job.from_legacy({}).title == ""
    assert Job.from_legacy({"job_title": "X", "yoe": "garbage"}).experience_min is None
    assert Job.from_legacy({"job_title": "X", "skills": None}).skills == []
    assert Job.from_legacy({"job_title": "X", "Posted_date": "not-a-date"}).posted_date is None
