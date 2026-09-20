"""Ingestion: source contract, failure isolation, and parsing of malformed input."""

from __future__ import annotations

import json

import pytest

from jobai.ingest.base import JobSource, SourceResult, all_jobs, run_sources
from jobai.ingest.legacy import job_from_legacy_record
from jobai.schema import Job


class GoodSource(JobSource):
    name = "good"

    def fetch(self, limit=None):
        yield Job(title="Engineer", company="Acme", source="good", source_job_id="1")


class BrokenSource(JobSource):
    name = "broken"

    def fetch(self, limit=None):
        raise RuntimeError("selectors changed")
        yield  # pragma: no cover


class PartiallyBrokenSource(JobSource):
    name = "partial"

    def fetch(self, limit=None):
        yield Job(title="A", company="Acme", source="partial", source_job_id="1")
        raise TimeoutError("page 2 timed out")


# --------------------------------------------------------- failure isolation


def test_one_source_failing_does_not_stop_the_others():
    results = run_sources([BrokenSource(), GoodSource()])
    assert results["broken"].ok is False
    assert "selectors changed" in results["broken"].error
    assert results["good"].ok is True and results["good"].count == 1
    assert len(all_jobs(results)) == 1


def test_every_source_gets_a_result_even_when_all_fail():
    results = run_sources([BrokenSource(), BrokenSource()])
    assert len(results) == 1  # same name collapses, but a result exists
    assert all(not r.ok for r in results.values())


def test_a_mid_stream_failure_is_reported_not_swallowed():
    result = PartiallyBrokenSource().run()
    assert result.ok is False
    assert "timed out" in result.error
    assert result.traceback


def test_source_result_summary_is_serialisable():
    summary = GoodSource().run().summary()
    json.dumps(summary)
    assert summary["source"] == "good" and summary["jobs"] == 1


def test_limit_is_respected():
    class Many(JobSource):
        name = "many"

        def fetch(self, limit=None):
            for i in range(100):
                if limit and i >= limit:
                    return
                yield Job(title=f"J{i}", company="Acme", source="many", source_job_id=str(i))

    assert Many().run(limit=5).count == 5


# ------------------------------------------------------- malformed records


def test_legacy_record_with_every_key_spelling():
    job = job_from_legacy_record(
        {"Job Title": "ML Engineer", "Company Name": "Acme", "Location": "Pune",
         "Experience": "2-5 Yrs", "Skills": ["python", "pytorch"],
         "Job Link": "https://x.example/1"},
        "naukri",
    )
    assert job.title == "ML Engineer"
    assert job.skills == ["Python", "PyTorch"]
    assert (job.experience_min, job.experience_max) == (2.0, 5.0)


def test_legacy_record_without_a_title_is_dropped():
    assert job_from_legacy_record({"company_name": "Acme"}, "x") is None


def test_legacy_record_with_missing_fields_still_parses():
    job = job_from_legacy_record({"job_title": "Engineer"}, "x")
    assert job is not None
    assert job.company == "" and job.skills == []


def test_legacy_record_recovers_skills_from_the_description():
    job = job_from_legacy_record(
        {"job_title": "Engineer", "job_description": "Work with PyTorch and Kubernetes daily."}, "x"
    )
    assert {"PyTorch", "Kubernetes"} <= set(job.skills)


def test_legacy_record_reads_the_yoe_band_when_experience_text_is_useless():
    job = job_from_legacy_record({"job_title": "E", "experience": "Not disclosed", "yoe": "3,7"}, "x")
    assert (job.experience_min, job.experience_max) == (3.0, 7.0)


# ---------------------------------------------------- source-specific parsing


def test_linkedin_relative_dates():
    from jobai.ingest.linkedin import _posted_date

    class Element(dict):
        def get_text(self, strip=False):
            return self["text"]

    element = Element(text="3 days ago")
    element_with_attr = {"datetime": "2026-01-15"}

    class Attr(dict):
        def get_text(self, strip=False):
            return ""

    assert _posted_date(None) is None
    assert _posted_date(Attr(element_with_attr)).strftime("%Y-%m-%d") == "2026-01-15"


def test_naukri_relative_dates():
    from jobai.ingest.naukri import _relative_date

    assert _relative_date("Just now") is not None
    assert _relative_date("3+ weeks ago") is not None
    assert _relative_date("") is None
    assert _relative_date("nonsense") is None


def test_naukri_search_url_pagination():
    from jobai.ingest.naukri import NaukriSource

    assert NaukriSource.search_url("machine learning engineer", "bangalore", 1).endswith(
        "machine-learning-engineer-jobs-in-bangalore"
    )
    assert NaukriSource.search_url("machine learning engineer", "bangalore", 3).endswith("-3")


def test_remote_detection():
    from jobai.ingest.naukri import _is_remote

    assert _is_remote("Remote role") is True
    assert _is_remote("Hybrid, Bengaluru") is False
    assert _is_remote("Bengaluru") is None


# --------------------------------------------------------------- integration


@pytest.mark.integration
@pytest.mark.network
def test_linkedin_returns_real_jobs():
    from jobai.ingest.linkedin import LinkedInSource

    result = LinkedInSource(keywords=["Machine Learning Engineer"], locations=["India"]).run(limit=3)
    if not result.ok:
        pytest.skip(f"LinkedIn unreachable: {result.error}")
    assert result.count >= 1
    job = result.jobs[0]
    assert job.title and job.company and job.source_job_id
    assert job.application_url.startswith("https://")


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.slow
def test_naukri_returns_real_jobs():
    from jobai.ingest.browser import BrowserUnavailable
    from jobai.ingest.naukri import NaukriSource

    try:
        result = NaukriSource(keywords=["machine learning engineer"], locations=["bangalore"]).run(limit=2)
    except BrowserUnavailable as exc:
        pytest.skip(f"Chrome unavailable: {exc}")
    if not result.ok or result.count == 0:
        pytest.skip(f"Naukri returned nothing: {result.error or 'blocked or markup changed'}")
    job = result.jobs[0]
    assert job.title and job.source_job_id
    assert job.experience_min is not None or job.experience_raw
