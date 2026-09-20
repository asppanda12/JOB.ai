"""End-to-end: resume -> profile -> hybrid retrieval -> rerank -> Qwen -> output.

These exercise the real FAISS index committed to the repository, so they need
the index present; each test skips cleanly when a dependency is missing.
"""

from __future__ import annotations

import pytest

from jobai.retrieval.filters import JobFilter


@pytest.fixture(scope="module")
def pipeline(dense_index):
    from jobai.retrieval.pipeline import RetrievalPipeline

    return RetrievalPipeline(dense=dense_index)


@pytest.mark.integration
@pytest.mark.slow
def test_every_retrieval_arm_contributes(pipeline, profile):
    result = pipeline.retrieve(profile, query="Machine Learning Engineer", top_k=5)
    stages = result.diagnostics["stages"]
    assert stages["dense"] > 0, "FAISS returned nothing"
    assert stages["lexical"] > 0, "BM25 returned nothing"
    assert stages["graph"] > 0, "graph returned nothing"
    assert stages["fused"] >= max(stages["dense"], stages["lexical"])
    assert stages["final"] <= 5


@pytest.mark.integration
@pytest.mark.slow
def test_funnel_narrows_monotonically(pipeline, profile):
    """1000s -> fused -> ~80 candidates -> ~20 reranked -> top_k."""
    result = pipeline.retrieve(profile, query="Data Scientist", top_k=10)
    stages = result.diagnostics["stages"]
    assert stages["candidates"] <= stages["fused"]
    assert stages["reranked"] <= stages["candidates"]
    assert stages["final"] <= stages["reranked"]


@pytest.mark.integration
@pytest.mark.slow
def test_reranker_runs_and_scores(pipeline, profile):
    result = pipeline.retrieve(profile, query="Backend Engineer", top_k=5)
    if not result.diagnostics.get("reranked"):
        pytest.skip("cross-encoder weights unavailable")
    assert all(0.0 <= job["signals"]["reranker_score"] <= 1.0 for job in result.jobs)


@pytest.mark.integration
@pytest.mark.slow
def test_results_carry_every_transparency_signal(pipeline, profile):
    result = pipeline.retrieve(profile, query="Machine Learning Engineer", top_k=3)
    assert result.jobs, "no results at all"
    for job in result.jobs:
        assert 0.0 <= job["match_score"] <= 1.0
        assert job["explanation"]
        for signal in ("semantic_match", "lexical_match", "graph_similarity",
                       "reranker_score", "required_skill_match", "experience_match",
                       "location_match", "role_match", "freshness"):
            assert signal in job["signals"]


@pytest.mark.integration
@pytest.mark.slow
def test_results_are_ordered_by_match_score(pipeline, profile):
    jobs = pipeline.retrieve(profile, query="Machine Learning Engineer", top_k=8).jobs
    scores = [j["match_score"] for j in jobs]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.integration
@pytest.mark.slow
def test_metadata_filter_is_applied(pipeline, profile):
    result = pipeline.retrieve(
        profile, query="Engineer", job_filter=JobFilter(experience_years=3.0), top_k=10
    )
    if result.diagnostics.get("filter_relaxed"):
        pytest.skip("filter was relaxed; too few matches to assert on")
    for job in result.jobs:
        band = job["metadata"].get("yoe")
        if band and "," in band:
            low, high = (float(x) for x in band.split(","))
            assert low <= 3.0 <= high


@pytest.mark.integration
@pytest.mark.slow
def test_graph_failure_does_not_break_retrieval(dense_index, profile, monkeypatch):
    """The stated requirement: graph down -> FAISS + BM25 + metadata continue."""
    from jobai.retrieval.pipeline import RetrievalPipeline

    pipeline = RetrievalPipeline(dense=dense_index)

    class DeadGraph:
        using_neo4j = False

        def search(self, *args, **kwargs):
            raise RuntimeError("neo4j down")

        def missing_skills(self, *args, **kwargs):
            raise RuntimeError("neo4j down")

    pipeline._graph = DeadGraph()
    result = pipeline.retrieve(profile, query="Machine Learning Engineer", top_k=5)
    assert result.jobs, "retrieval must survive a dead graph"
    assert result.diagnostics["stages"]["graph"] == 0


@pytest.mark.integration
@pytest.mark.slow
def test_reranker_failure_falls_back_to_fused_order(dense_index, profile, monkeypatch):
    import jobai.retrieval.pipeline as pipeline_module
    from jobai.retrieval.pipeline import RetrievalPipeline

    monkeypatch.setattr(pipeline_module, "rerank", lambda q, c, **kw: c[: kw.get("top_k", 20)])
    result = RetrievalPipeline(dense=dense_index).retrieve(profile, query="Engineer", top_k=5)
    assert result.jobs


@pytest.mark.integration
@pytest.mark.slow
def test_empty_profile_and_query_is_handled(pipeline):
    result = pipeline.retrieve({}, query=None)
    assert result.jobs == []
    assert "error" in result.diagnostics


@pytest.mark.integration
@pytest.mark.slow
def test_qwen_reasoning_is_attached_last(pipeline, profile, ollama):
    """Qwen sees only the reranked survivors and explains, never re-ranks."""
    result = pipeline.retrieve(
        profile, query="Machine Learning Engineer", top_k=3, explain_with_llm=True
    )
    if result.diagnostics.get("llm_reasoning") != "ok":
        pytest.skip(f"LLM reasoning unavailable: {result.diagnostics.get('llm_reasoning')}")
    scores = [j["match_score"] for j in result.jobs]
    assert scores == sorted(scores, reverse=True), "Qwen must not reorder the results"
    assert any(j.get("llm_verdict") for j in result.jobs)


@pytest.mark.integration
@pytest.mark.slow
def test_resume_to_recommendation(dense_index, ollama):
    """The full advertised flow, on a real resume PDF from the repository."""
    from pathlib import Path

    from jobai.config import PROJECT_ROOT
    from jobai.profile import build_profile, extract_pdf_text
    from jobai.recommend import recommend_for_profile

    resumes = sorted((PROJECT_ROOT / "telegram_bot/JOB.ai/job_resume").glob("*.pdf"))
    if not resumes:
        pytest.skip("no sample resume in the repository")

    profile = build_profile(extract_pdf_text(str(resumes[0])))
    assert profile["skills"], "resume parsing produced no skills"

    outcome = recommend_for_profile(profile, top_k=5, explain=False)
    assert outcome["jobs"], "no recommendations for a real resume"
    assert all(job["metadata"].get("job_title") for job in outcome["jobs"])


# ------------------------------------------------------- store integration


@pytest.mark.integration
def test_recommendation_lookup_tolerates_string_and_int_indices(store):
    """The legacy bug: job_indx was stored as a string but queried as an int."""
    chat_id = -999_001
    store.save_recommendations(chat_id, [{"metadata": {"job_indx": "7", "job_title": "X"}}])
    try:
        assert store.find_recommendation(chat_id, 7) is not None
        assert store.find_recommendation(chat_id, "7") is not None
        assert store.find_recommendation(chat_id, 8) is None
    finally:
        store.recommendations.delete_many({"chat_id": chat_id})


@pytest.mark.integration
def test_upsert_skips_unchanged_jobs(store, job_factory):
    job = job_factory(source="pytest", source_job_id="dedup-1")
    try:
        store.upsert_jobs([job])
        second = store.upsert_jobs([job])
        assert second["unchanged"] == 1 and second["inserted"] == 0
    finally:
        store.jobs.delete_many({"job_id": job.job_id})
