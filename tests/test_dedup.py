"""Multi-level deduplication."""

from __future__ import annotations

from jobai.dedup import company_key, deduplicate, title_key


def test_same_source_id_collapses(job_factory):
    jobs = [job_factory(), job_factory(salary="Rs. 30 LPA")]
    out, stats = deduplicate(jobs)
    assert len(out) == 1
    assert stats["source_id"] == 1


def test_same_url_across_sources_collapses(job_factory):
    a = job_factory(source="linkedin", source_job_id="1",
                    application_url="https://in.linkedin.com/jobs/view/x-99")
    b = job_factory(source="naukri", source_job_id="2",
                    application_url="https://www.linkedin.com/jobs/view/x-99?refId=z")
    out, stats = deduplicate([a, b])
    assert len(out) == 1
    assert stats["url"] == 1


def test_company_title_location_collapses_with_cosmetic_noise(job_factory):
    a = job_factory(source="linkedin", source_job_id="1", application_url="https://a.example/1",
                    company="Acme Technologies Pvt Ltd", location="Bengaluru, Karnataka, India")
    b = job_factory(source="naukri", source_job_id="2", application_url="https://b.example/2",
                    title="Machine Learning Engineer (Urgent Hiring)",
                    company="Acme Technologies", location="Bengaluru")
    out, stats = deduplicate([a, b])
    assert len(out) == 1
    assert stats["company_title"] == 1


def test_different_companies_are_never_merged(job_factory):
    a = job_factory(source="linkedin", source_job_id="1", application_url="https://a.example/1",
                    company="Acme")
    b = job_factory(source="naukri", source_job_id="2", application_url="https://b.example/2",
                    company="Globex")
    out, _ = deduplicate([a, b])
    assert len(out) == 2


def test_merge_keeps_every_source_and_the_richer_fields(job_factory):
    a = job_factory(source="linkedin", source_job_id="1", application_url="https://a.example/1",
                    description="Short.", skills=["Python"], salary="")
    b = job_factory(source="naukri", source_job_id="2", application_url="https://b.example/2",
                    description="A much longer and more complete description of the role.",
                    skills=["AWS"], salary="Rs. 25 LPA")
    out, _ = deduplicate([a, b])
    merged = out[0]
    assert {s["source"] for s in merged.sources} == {"linkedin", "naukri"}
    assert merged.description.startswith("A much longer")
    assert {"Python", "AWS"} <= set(merged.skills)
    assert merged.salary == "Rs. 25 LPA"


def test_semantic_pass_is_restricted_to_one_company(job_factory):
    """A fake embedder that calls everything identical must still not merge
    across companies - that is the guard against losing genuine jobs."""
    a = job_factory(source="a", source_job_id="1", application_url="https://a.example/1",
                    company="Acme", title="Backend Engineer")
    b = job_factory(source="b", source_job_id="2", application_url="https://b.example/2",
                    company="Globex", title="Backend Engineer")
    out, stats = deduplicate([a, b], embedder=lambda texts: [[1.0, 0.0]] * len(texts))
    assert len(out) == 2
    assert stats["semantic"] == 0


def test_semantic_pass_merges_within_a_company(job_factory):
    a = job_factory(source="a", source_job_id="1", application_url="https://a.example/1",
                    company="Acme", title="Backend Engineer")
    b = job_factory(source="b", source_job_id="2", application_url="https://b.example/2",
                    company="Acme", title="Backend Developer", location="Pune")
    out, stats = deduplicate([a, b], embedder=lambda texts: [[1.0, 0.0]] * len(texts))
    assert len(out) == 1
    assert stats["semantic"] == 1


def test_empty_input():
    out, stats = deduplicate([])
    assert out == [] and stats["output"] == 0


def test_keys_strip_boilerplate():
    assert company_key("Acme Technologies Pvt Ltd") == company_key("Acme")
    assert title_key("Senior Engineer (Urgent Hiring)") == title_key("Senior Engineer")
