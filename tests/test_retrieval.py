"""Fusion, filtering, scoring and the funnel wiring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jobai.config import ScoringWeights
from jobai.retrieval.filters import JobFilter, apply_filter
from jobai.retrieval.fusion import reciprocal_rank_fusion
from jobai.retrieval.graph import InMemoryJobGraph
from jobai.retrieval.lexical import BM25Index, tokenize
from jobai.scoring import freshness_score, rank, score_candidate


def meta(job_id, **kw):
    base = {
        "job_id": job_id, "job_title": "Machine Learning Engineer",
        "company_name": "Acme", "location": "Bengaluru",
        "skills_list": ["Python", "PyTorch"], "yoe": "2,5",
        "text": "Machine Learning Engineer at Acme using Python and PyTorch in Bengaluru",
        "Source": "linkedin", "Posted_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    base.update(kw)
    return base


# ------------------------------------------------------------------- fusion


def test_rrf_prefers_the_job_every_retriever_ranks():
    fused = reciprocal_rank_fusion({
        "dense":   [(meta("a"), 0.9), (meta("b"), 0.8)],
        "lexical": [(meta("a"), 1.0), (meta("c"), 0.5)],
        "graph":   [(meta("a"), 0.7)],
    })
    assert fused[0]["job_id"] == "a"
    assert set(fused[0]["retriever_ranks"]) == {"dense", "lexical", "graph"}


def test_rrf_uses_rank_not_raw_score():
    """BM25's unbounded scale must not be able to dominate the fusion."""
    fused = reciprocal_rank_fusion({
        "dense":   [(meta("a"), 0.9)],
        "lexical": [(meta("b"), 999999.0)],
    })
    assert fused[0]["job_id"] == "a"  # dense has the higher weight at equal rank


def test_rrf_records_each_retriever_score():
    fused = reciprocal_rank_fusion({"dense": [(meta("a"), 0.42)]})
    assert fused[0]["retriever_scores"]["dense"] == pytest.approx(0.42)


def test_rrf_ignores_a_zero_weighted_arm():
    fused = reciprocal_rank_fusion({"dense": [(meta("a"), 1.0)], "graph": [(meta("b"), 1.0)]},
                                   weights={"graph": 0.0})
    assert [f["job_id"] for f in fused] == ["a"]


def test_rrf_on_empty_input():
    assert reciprocal_rank_fusion({}) == []
    assert reciprocal_rank_fusion({"dense": []}) == []


# ------------------------------------------------------------------ lexical


def test_tokenizer_keeps_exact_technology_tokens():
    tokens = tokenize("C++ and C# with Node.js")
    assert "c++" in tokens and "c#" in tokens and "node.js" in tokens and "node" in tokens


def test_bm25_finds_an_exact_skill_a_dense_model_would_blur():
    index = BM25Index().build([
        meta("a", skills_list=["LangGraph"], text="Agent orchestration with LangGraph"),
        meta("b", skills_list=["LangChain"], text="RAG pipelines with LangChain"),
    ])
    assert index.search("LangGraph", k=2)[0][0]["job_id"] == "a"


def test_bm25_on_an_empty_corpus_returns_nothing():
    assert BM25Index().build([]).search("anything") == []


# -------------------------------------------------------------------- graph


def test_graph_scores_by_weighted_skill_overlap():
    graph = InMemoryJobGraph().build([
        meta("a", skills_list=["Python", "PyTorch"]),
        meta("b", skills_list=["Java", "Spring"]),
    ])
    results = graph.search(["Python", "PyTorch"], k=5)
    assert results[0][0]["job_id"] == "a"


def test_graph_reports_missing_skills():
    graph = InMemoryJobGraph().build([meta("a", skills_list=["Python", "Kubernetes"])])
    assert graph.missing_skills(["Python"], "a") == ["Kubernetes"]


def test_graph_finds_companies_hiring_for_a_skill_set():
    graph = InMemoryJobGraph().build([
        meta("a", company_name="Acme", skills_list=["Python"]),
        meta("b", company_name="Acme", skills_list=["Python"]),
        meta("c", company_name="Globex", skills_list=["Java"]),
    ])
    assert graph.companies_hiring(["Python"])[0] == ("acme", 2)


def test_graph_with_no_user_skills_returns_nothing():
    assert InMemoryJobGraph().build([meta("a")]).search([]) == []


# ------------------------------------------------------------------ filters


def test_experience_filter_excludes_an_out_of_band_job():
    assert not JobFilter(experience_years=10.0).matches(meta("a", yoe="0,2"))
    assert JobFilter(experience_years=3.0).matches(meta("a", yoe="2,5"))


def test_unknown_metadata_never_excludes():
    """Missing data must not silently drop a job from the results."""
    assert JobFilter(experience_years=3.0).matches(meta("a", yoe=None))
    assert JobFilter(min_salary=20.0).matches(meta("a", salary="Not disclosed"))


def test_location_and_company_filters():
    assert JobFilter(locations=["bengaluru"]).matches(meta("a"))
    assert not JobFilter(locations=["pune"]).matches(meta("a"))
    assert not JobFilter(exclude_companies=["acme"]).matches(meta("a"))


def test_remote_filter_falls_back_to_a_text_sniff():
    assert JobFilter(remote=True).matches(meta("a", location="Remote, India"))
    assert not JobFilter(remote=True).matches(meta("a", location="Bengaluru"))


def test_posted_within_days():
    old = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    assert not JobFilter(posted_within_days=30).matches(meta("a", Posted_date=old))


def test_filter_relaxes_rather_than_returning_nothing():
    candidates = [{"metadata": meta("a", location="Bengaluru")}]
    kept, relaxed = apply_filter(candidates, JobFilter(locations=["Reykjavik"]), min_results=1)
    assert relaxed is True and len(kept) == 1


def test_empty_filter_is_a_passthrough():
    candidates = [{"metadata": meta("a")}]
    kept, relaxed = apply_filter(candidates, JobFilter())
    assert kept == candidates and relaxed is False


# ------------------------------------------------------------------ scoring


def test_score_exposes_every_signal(profile):
    scored = score_candidate({"job_id": "a", "metadata": meta("a"), "retriever_scores": {"dense": 0.9}}, profile)
    for signal in ("semantic_match", "skill_match", "required_skill_match", "experience_match",
                   "location_match", "role_match", "freshness", "graph_similarity", "reranker_score"):
        assert signal in scored["signals"]
    assert 0.0 <= scored["match_score"] <= 1.0
    assert scored["explanation"]


def test_related_skill_counts_as_a_partial_match(profile):
    """Having PyTorch when the job wants TensorFlow is a near miss, not a zero."""
    scored = score_candidate({"job_id": "a", "metadata": meta("a", skills_list=["TensorFlow"])}, profile)
    assert 0.0 < scored["signals"]["required_skill_match"] < 1.0


def test_missing_skills_are_reported(profile):
    scored = score_candidate({"job_id": "a", "metadata": meta("a", skills_list=["Python", "Kubernetes"])}, profile)
    assert "Kubernetes" in scored["missing_skills"]


def test_weights_are_configurable(profile):
    candidate = {"job_id": "a", "metadata": meta("a"), "reranker_score": 1.0,
                 "retriever_scores": {"dense": 0.0}}
    only_reranker = ScoringWeights(
        reranker_score=1.0, semantic_match=0.0, required_skill_match=0.0,
        preferred_skill_match=0.0, skill_match=0.0, experience_match=0.0,
        location_match=0.0, role_match=0.0, graph_similarity=0.0, freshness=0.0,
    )
    assert score_candidate(dict(candidate), profile, only_reranker)["match_score"] == pytest.approx(1.0)


def test_freshness_decays_but_never_reaches_zero():
    now = datetime.now(timezone.utc)
    fresh = freshness_score(now.strftime("%Y-%m-%d"))
    old = freshness_score((now - timedelta(days=365)).strftime("%Y-%m-%d"))
    assert fresh > old > 0.0
    assert freshness_score(None) == 0.5


def test_rank_orders_by_match_score(profile):
    ranked = rank([
        {"job_id": "weak", "metadata": meta("weak", skills_list=["COBOL"], yoe="15,20")},
        {"job_id": "strong", "metadata": meta("strong", skills_list=["Python", "PyTorch"])},
    ], profile)
    assert ranked[0]["job_id"] == "strong"
