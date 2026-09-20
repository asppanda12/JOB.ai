"""The added job sources: ATS boards, aggregator feeds, and the Playwright layer.

Parsing is tested offline against captured payload shapes, so the suite stays
fast and deterministic. The ``network`` marker covers the live endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from jobai.ingest.ats import (
    ATS_SOURCES,
    AshbySource,
    GreenhouseSource,
    LeverSource,
    RecruiteeSource,
    SmartRecruitersSource,
    WorkableSource,
    _lever_salary,
    strip_html,
)
from jobai.ingest.boards import (
    BOARD_SOURCES,
    ArbeitnowSource,
    HimalayasSource,
    JobicySource,
    RemoteOKSource,
    RemotiveSource,
    WeWorkRemotelySource,
)
from jobai.ingest.runner import SOURCE_GROUPS, available_sources, build_sources, expand_groups


# ------------------------------------------------------------- registration


def test_every_source_is_registered():
    names = available_sources()
    for expected in [
        "linkedin", "naukri",
        "greenhouse", "lever", "ashby", "smartrecruiters", "workable", "recruitee",
        "remoteok", "remotive", "arbeitnow", "himalayas", "jobicy", "weworkremotely",
    ]:
        assert expected in names, f"{expected} is not registered"


def test_groups_only_reference_real_sources():
    names = set(available_sources()) | {"legacy"}
    for group, members in SOURCE_GROUPS.items():
        for member in members:
            assert member in names, f"group {group!r} references unknown source {member!r}"


def test_expand_groups_dedupes_and_preserves_order():
    assert expand_groups(["ats", "greenhouse"])[0] == "greenhouse"
    assert len(expand_groups(["ats", "ats"])) == len(SOURCE_GROUPS["ats"])


def test_unknown_source_is_skipped_not_fatal(caplog):
    sources = build_sources(["greenhouse", "does-not-exist"])
    assert [s.name for s in sources] == ["greenhouse"]


def test_all_group_builds():
    # Constructing every source must not touch the network.
    assert len(build_sources(["all"])) == len(SOURCE_GROUPS["all"])


# -------------------------------------------------------------- ATS parsing


def test_greenhouse_parsing():
    job = GreenhouseSource(companies=["acme"]).parse(
        {
            "id": 4567, "title": "Senior ML Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4567?utm_source=x",
            "content": "<p>Requires 5+ years of Python and PyTorch.</p>",
            "location": {"name": "Bengaluru, India"},
            "departments": [{"name": "Engineering"}],
            "updated_at": "2026-09-01T10:00:00Z",
        },
        "acme",
    ).finalize()
    assert job.title == "Senior ML Engineer"
    assert job.source == "greenhouse" and job.source_job_id == "4567"
    assert job.location == "Bengaluru, India"
    assert job.job_category == "Engineering"
    assert (job.experience_min, job.experience_max) == (5.0, 60.0)
    assert {"Python", "PyTorch"} <= set(job.skills)
    assert "<p>" not in job.description
    assert "utm_source" not in job.application_url


def test_lever_parsing_and_salary():
    job = LeverSource(companies=["acme"]).parse(
        {
            "id": "abc-123", "text": "Backend Engineer",
            "hostedUrl": "https://jobs.lever.co/acme/abc-123",
            "descriptionPlain": "Build services. 3-6 years experience with Go and Kubernetes.",
            "categories": {"location": "Remote", "commitment": "Full-time", "team": "Platform"},
            "salaryRange": {"min": 150000, "max": 200000, "currency": "USD"},
            "createdAt": 1750000000000,
            "lists": [{"text": "Requirements", "content": "<li>Kafka</li>"}],
        },
        "acme",
    ).finalize()
    assert job.source_job_id == "abc-123"
    assert (job.experience_min, job.experience_max) == (3.0, 6.0)
    assert job.employment_type == "Full-time"
    assert job.salary == "USD 150,000 - 200,000"
    assert job.posted_date is not None
    assert job.remote is True


def test_lever_salary_edge_cases():
    assert _lever_salary(None) == ""
    assert _lever_salary({}) == ""
    assert _lever_salary({"min": 100000, "currency": "USD"}) == "USD 100,000"


def test_ashby_parsing():
    job = AshbySource(companies=["acme"]).parse(
        {
            "id": "u-1", "title": "Data Scientist",
            "jobUrl": "https://jobs.ashbyhq.com/acme/u-1",
            "descriptionPlain": "Analytics work. 2+ years of SQL required.",
            "location": "New York, NY", "employmentType": "FullTime", "team": "Data",
            "publishedAt": "2026-08-15T00:00:00Z",
            "compensation": {"compensationTierSummary": "$180K – $220K"},
        },
        "acme",
    ).finalize()
    assert job.title == "Data Scientist"
    assert job.salary == "$180K – $220K"
    assert (job.experience_min, job.experience_max) == (2.0, 60.0)


def test_smartrecruiters_parsing():
    job = SmartRecruitersSource(companies=["acme"]).parse(
        {
            "id": "sr-9", "name": "QA Engineer",
            "company": {"name": "Acme Corp"},
            "location": {"city": "Pune", "region": "MH", "country": "India"},
            "applyUrl": "https://jobs.smartrecruiters.com/acme/sr-9",
            "jobAd": {"sections": {"jobDescription": {"text": "Test things. 4 years experience."}}},
            "typeOfEmployment": {"label": "Permanent"},
            "department": {"label": "Quality"},
            "releasedDate": "2026-07-01T00:00:00Z",
        },
        "acme",
    ).finalize()
    assert job.company == "Acme Corp"
    assert job.location == "Pune, MH, India"
    assert job.employment_type == "Permanent"


def test_workable_parsing():
    job = WorkableSource(companies=["acme"]).parse(
        {
            "shortcode": "WK1", "title": "DevOps Engineer", "company": "Acme",
            "city": "Berlin", "country": "Germany",
            "url": "https://apply.workable.com/acme/j/WK1",
            "description": "Run infrastructure with Terraform and Kubernetes.",
            "employment_type": "Full-time", "department": "Infra",
            "published_on": "2026-06-01",
        },
        "acme",
    ).finalize()
    assert job.source_job_id == "WK1"
    assert job.location == "Berlin, Germany"
    assert {"Terraform", "Kubernetes"} <= set(job.skills)


def test_recruitee_parsing():
    job = RecruiteeSource(companies=["acme"]).parse(
        {
            "id": 77, "title": "Frontend Engineer", "company_name": "Acme",
            "city": "Amsterdam", "country": "Netherlands",
            "careers_url": "https://acme.recruitee.com/o/frontend-engineer",
            "description": "<p>Build UIs.</p>", "requirements": "<p>React and TypeScript.</p>",
            "published_at": "2026-05-20T00:00:00Z",
        },
        "acme",
    ).finalize()
    assert job.source_job_id == "77"
    assert {"React", "TypeScript"} <= set(job.skills)


@pytest.mark.parametrize("name,cls", sorted(ATS_SOURCES.items()))
def test_ats_rejects_records_without_a_title_or_id(name, cls):
    assert cls(companies=["acme"]).parse({}, "acme") is None


def test_ats_companies_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("ATS_GREENHOUSE", "alpha, beta ,gamma")
    assert GreenhouseSource().companies == ["alpha", "beta", "gamma"]


def test_strip_html():
    assert strip_html("<p>Hello&nbsp;<b>world</b></p>") == "Hello world"
    assert strip_html(None) == ""


# ------------------------------------------------------------ board parsing


def test_remoteok_skips_the_attribution_record():
    source = RemoteOKSource()
    records = source._records([{"legal": "notice"}, {"id": 1, "position": "Engineer"}])
    assert len(records) == 1 and records[0]["id"] == 1


def test_remoteok_parsing():
    job = RemoteOKSource().parse(
        {
            "id": 999, "position": "Backend Engineer", "company": "Acme",
            "description": "Build APIs with Go.", "tags": ["golang", "backend"],
            "url": "https://remoteOK.com/remote-jobs/x-999",
            "date": "2026-09-19T20:00:01+00:00",
            "salary_min": 80000, "salary_max": 120000, "location": "",
        }
    ).finalize()
    assert job.source_job_id == "999"
    assert "Go" in job.skills          # curated tag, trusted
    assert job.salary == "$80,000 - $120,000"
    assert job.remote is True          # empty location defaults to Remote


def test_remotive_parsing():
    job = RemotiveSource().parse(
        {
            "id": 12, "title": "Django Developer", "company_name": "Acme",
            "description": "<p>Work with Django.</p>", "tags": ["Python", "Django"],
            "url": "https://remotive.com/job/12", "job_type": "full_time",
            "candidate_required_location": "Worldwide", "salary": "$90k - $105k",
            "publication_date": "2026-09-18T16:43:22", "category": "Software Development",
        }
    ).finalize()
    assert {"Python", "Django"} <= set(job.skills)
    assert job.posted_date.year == 2026


def test_arbeitnow_parsing_with_epoch():
    job = ArbeitnowSource().parse(
        {
            "slug": "acme-engineer-1", "title": "Engineer", "company_name": "Acme",
            "description": "<div>Build things with C++.</div>", "tags": ["Engineering"],
            "url": "https://www.arbeitnow.com/jobs/companies/acme/engineer-1",
            "location": "Berlin", "job_types": ["Full Time"], "created_at": 1789934686,
        }
    ).finalize()
    assert job.source_job_id == "acme-engineer-1"
    assert job.posted_date is not None
    assert job.employment_type == "Full Time"


def test_himalayas_parsing_with_epoch_and_salary():
    job = HimalayasSource().parse(
        {
            "guid": "h-1", "title": "Architect", "companyName": "Acme",
            "description": "<p>Design systems.</p>", "applicationLink": "https://himalayas.app/jobs/h-1",
            "categories": ["Distributed-Systems"], "parentCategories": ["Engineering"],
            "employmentType": "Full Time", "seniority": ["Senior"],
            "minSalary": 130000, "maxSalary": 160000, "currency": "USD",
            "locationRestrictions": ["United States"], "pubDate": 1789928116,
        }
    ).finalize()
    assert job.salary == "USD 130,000 - 160,000"
    assert job.posted_date is not None
    assert (job.experience_min, job.experience_max) == (5.0, 60.0)  # "Senior"


def test_jobicy_parsing():
    job = JobicySource().parse(
        {
            "id": 153765, "jobTitle": "Business Development Manager", "companyName": "Acme",
            "jobDescription": "<p>Sell things.</p>", "url": "https://jobicy.com/jobs/153765-x",
            "jobGeo": "APAC", "jobIndustry": ["Business Development"],
            "jobType": ["Full-Time"], "jobLevel": "Senior", "pubDate": "2026-09-20T11:30:36+00:00",
        }
    ).finalize()
    assert job.source_job_id == "153765"
    assert job.employment_type == "Full-Time"


def test_weworkremotely_splits_company_from_title():
    job = WeWorkRemotelySource().parse(
        {
            "title": "Legion: Chief Architect",
            "link": "https://weworkremotely.com/remote-jobs/12345-chief-architect",
            "description": "<p>Lead architecture with Python and AWS.</p>",
            "region": "Anywhere in the World",
            "pubDate": "Sun, 07 Sep 2026 12:00:00 +0000",
        }
    ).finalize()
    assert job.company == "Legion"
    assert job.title == "Chief Architect"
    assert job.source_job_id == "12345"
    assert job.posted_date is not None


def test_weworkremotely_title_without_a_company():
    job = WeWorkRemotelySource().parse(
        {"title": "Chief Architect", "link": "https://weworkremotely.com/remote-jobs/1-x"}
    )
    assert job.company == "" and job.title == "Chief Architect"


def test_weworkremotely_handles_broken_rss():
    source = WeWorkRemotelySource()
    assert source._records("<not xml") == []
    assert source._partial is True


@pytest.mark.parametrize("name,cls", sorted(BOARD_SOURCES.items()))
def test_boards_reject_empty_records(name, cls):
    assert cls().parse({}) is None


# ------------------------------------------------------------- Playwright


def test_playwright_module_imports_without_a_browser():
    from jobai.ingest import playwright_browser

    assert hasattr(playwright_browser, "playwright_page")
    assert hasattr(playwright_browser, "goto_status")


def test_stylesheets_are_not_blocked():
    """Blocking CSS leaves Naukri a 1.9 KB shell with zero job cards."""
    from jobai.ingest.playwright_browser import _BLOCKED_RESOURCE_TYPES

    assert "stylesheet" not in _BLOCKED_RESOURCE_TYPES
    assert {"image", "media", "font"} <= _BLOCKED_RESOURCE_TYPES


@pytest.mark.integration
@pytest.mark.slow
def test_playwright_can_launch_and_navigate():
    from jobai.ingest.playwright_browser import BrowserUnavailable, goto_status, playwright_page

    try:
        with playwright_page() as page:
            ok, status = goto_status(page, "https://example.com")
    except BrowserUnavailable as exc:
        pytest.skip(str(exc))
    assert ok and status == 200


# ------------------------------------------------------------- live network


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.parametrize("name", ["greenhouse", "lever", "ashby", "recruitee"])
def test_ats_sources_return_live_jobs(name):
    result = ATS_SOURCES[name]().run(limit=2)
    assert result.ok, result.error
    if result.count == 0:
        pytest.skip(f"{name}: configured companies have no open roles right now")
    job = result.jobs[0]
    assert job.title and job.source_job_id and job.application_url.startswith("https://")


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.parametrize("name", sorted(BOARD_SOURCES))
def test_board_feeds_return_live_jobs(name):
    result = BOARD_SOURCES[name]().run(limit=2)
    assert result.ok, result.error
    if result.count == 0:
        pytest.skip(f"{name}: feed returned nothing right now")
    job = result.jobs[0]
    assert job.title and job.company and job.source_job_id


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.slow
def test_naukri_via_playwright():
    from jobai.ingest.naukri import NaukriSource
    from jobai.ingest.playwright_browser import BrowserUnavailable

    try:
        result = NaukriSource(keywords=["machine learning engineer"], locations=["bangalore"]).run(limit=2)
    except BrowserUnavailable as exc:
        pytest.skip(str(exc))
    if not result.ok or result.count == 0:
        pytest.skip("Naukri blocked or markup changed; it needs a headed browser")
    job = result.jobs[0]
    assert job.source_job_id and job.title
    assert len(job.description) > 200, "detail page fetch did not run"


# --------------------------------------------- detail fetching regressions


def test_workable_detail_merge_does_not_clobber_the_location():
    """Workable v2 reuses ``state`` for publication status.

    A blind merge turned "Austin, Texas, United States" into
    "Austin, published, United States".
    """
    source = WorkableSource(companies=["acme"])
    listing = {"shortcode": "X1", "title": "Advisor", "city": "Austin",
               "state": "Texas", "country": "United States"}
    detail = {"state": "published", "description": "<p>Advise people.</p>",
              "requirements": "<p>5+ years.</p>", "remote": True}
    merged = source.merge_detail(listing, detail)
    assert merged["state"] == "Texas"
    assert "Advise people" in merged["description"]

    job = source.parse(merged, "acme").finalize()
    assert job.location == "Austin, Texas, United States"
    assert len(job.description) > 20


def test_workable_uses_its_explicit_structured_fields():
    job = WorkableSource(companies=["acme"]).parse(
        {"shortcode": "X2", "title": "SDR", "city": "Austin", "country": "US",
         "telecommuting": True, "education": "High School or equivalent",
         "experience": "Associate", "industry": "E-Learning",
         "description": "Sell things."},
        "acme",
    ).finalize()
    assert job.remote is True                      # stated, not inferred
    assert job.education == ["High School or equivalent"]
    assert job.industry == "E-Learning"
    assert (job.experience_min, job.experience_max) == (1.0, 3.0)   # "Associate"


def test_smartrecruiters_concatenates_every_jobad_section():
    job = SmartRecruitersSource(companies=["acme"]).parse(
        {"id": "s1", "name": "Technician", "location": {"city": "Palmyra", "country": "us"},
         "jobAd": {"sections": {
             "jobDescription": {"text": "<p>Fix tyres.</p>"},
             "qualifications": {"text": "<p>Needs a CDL.</p>"},
             "additionalInformation": {"text": "<p>Shift work.</p>"},
             "companyDescription": {"text": "<p>About us.</p>"}}}},
        "acme",
    ).finalize()
    for fragment in ("Fix tyres", "Needs a CDL", "Shift work", "About us"):
        assert fragment in job.description


def test_detail_fields_whitelist_is_honoured():
    source = SmartRecruitersSource(companies=["acme"])
    merged = source.merge_detail({"name": "Keep me"}, {"name": "Overwrite", "jobAd": {"x": 1}})
    assert merged["name"] == "Keep me"     # not whitelisted, so preserved
    assert merged["jobAd"] == {"x": 1}     # whitelisted, so taken


def test_age_requirement_is_not_read_as_experience():
    """"Must be 18 years or older" previously produced a band of (18, 18)."""
    from jobai.ingest.ats import _experience_phrase

    phrase = _experience_phrase("Must be 18 years or older. Requires 3+ years of Python.")
    assert "older" not in phrase
    assert "3+ years" in phrase
    assert _experience_phrase("Must be 21 years of age.") == ""


def test_detail_fetch_failure_degrades_to_the_summary(monkeypatch):
    source = WorkableSource(companies=["acme"])
    monkeypatch.setattr(source, "_get", lambda url: None)
    record = {"shortcode": "X1", "title": "Advisor", "city": "Austin"}
    assert source._with_detail(record, "acme") == record
    assert source._partial is True


def test_unicode_whitespace_is_normalized():
    """&nbsp; reached the embedder and the BM25 tokenizer as a literal \\xa0."""
    assert strip_html("<p>Hello&nbsp;<b>world</b></p>") == "Hello world"
    assert " " not in strip_html("a b​c")
