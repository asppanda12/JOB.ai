"""Deterministic normalization: skills, experience, canonical text."""

from __future__ import annotations

import pytest

from jobai.normalize.experience import OPEN_ENDED, experience_overlap, parse_experience
from jobai.normalize.skills import (
    extract_skills_from_text,
    normalize_skill,
    normalize_skills,
    parse_skill_blob,
    related_skills,
    skills_from_metadata,
)
from jobai.normalize.text import canonical_job_text


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Py Torch", "PyTorch"), ("py-torch", "PyTorch"), ("pytorch", "PyTorch"),
        ("lang chain", "LangChain"), ("Amazon Web Services", "AWS"),
        ("Large Language Model", "LLM"), ("k8s", "Kubernetes"),
        ("python3", "Python"), ("C++", "C++"), ("nodejs", "Node.js"),
        ("retrieval augmented generation", "RAG"),
    ],
)
def test_aliases_map_to_canonical_spelling(raw, expected):
    assert normalize_skill(raw) == expected


def test_normalization_is_idempotent():
    once = normalize_skills(["py torch", "aws", "k8s"])
    assert normalize_skills(once) == once


def test_stopwords_and_noise_are_dropped():
    assert normalize_skills(["N/A", "none", "", "  ", "etc", "skills"]) == []


def test_known_skills_are_not_split_on_separators():
    assert normalize_skills(["CI/CD"]) == ["CI/CD"]
    assert normalize_skills(["Node.js"]) == ["Node.js"]


def test_compound_strings_are_split():
    assert normalize_skills(["Python, Django and SQL"]) == ["Python", "Django", "SQL"]


def test_parenthesised_acronym_is_kept():
    assert "NLP" in normalize_skills(["Natural Language Processing (NLP)"])


def test_duplicates_collapse_preserving_order():
    assert normalize_skills(["Python", "python3", "PYTHON", "AWS"]) == ["Python", "AWS"]


def test_related_skills_are_symmetric():
    assert "LangChain" in related_skills("LangGraph")
    assert "LangGraph" in related_skills("LangChain")


def test_extract_from_free_text():
    found = extract_skills_from_text("Strong PyTorch, k8s and retrieval augmented generation experience.")
    assert {"PyTorch", "Kubernetes", "RAG"} <= set(found)


def test_legacy_space_joined_blob_is_recovered():
    """The pre-upgrade store joined skills with single spaces and no delimiter."""
    assert set(parse_skill_blob("Python Generative AI LLMs NLP")) >= {"Python", "Generative AI", "NLP"}


def test_skills_from_metadata_handles_both_shapes():
    assert skills_from_metadata({"skills_list": ["py torch"]}) == ["PyTorch"]
    assert "PyTorch" in skills_from_metadata({"skills": "Machine Learning PyTorch AWS"})
    assert skills_from_metadata({}) == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2-5 Yrs", (2.0, 5.0)), ("2 to 5 years", (2.0, 5.0)),
        ("3+ years", (3.0, OPEN_ENDED)), ("minimum 3 years", (3.0, OPEN_ENDED)),
        ("0-2 years", (0.0, 2.0)), ("up to 4 years", (0.0, 4.0)),
        ("5 years", (5.0, 5.0)), ("6 months", (0.0, 0.5)),
        ("Senior", (5.0, OPEN_ENDED)), ("SDE2", (3.0, 6.0)), ("IC2", (1.0, 3.0)),
        ("Not disclosed", (None, None)), ("", (None, None)), (None, (None, None)),
    ],
)
def test_experience_parsing(raw, expected):
    assert parse_experience(raw) == expected


def test_experience_never_exceeds_the_open_ended_sentinel():
    low, high = parse_experience("200 years")
    assert high <= OPEN_ENDED


def test_experience_overlap_scoring():
    assert experience_overlap(3.0, 2.0, 5.0) == 1.0     # inside the band
    assert experience_overlap(None, 2.0, 5.0) == 0.5    # unknown -> neutral
    assert 0 < experience_overlap(1.0, 2.0, 5.0) < 1    # near miss
    assert experience_overlap(0.0, 10.0, 20.0) == 0.0   # far miss


def test_canonical_text_is_stable_and_labelled(job_factory):
    job = job_factory()
    assert canonical_job_text(job) == canonical_job_text(job)
    text = canonical_job_text(job)
    assert text.startswith("Job Title: ")
    assert "Company: Acme Technologies" in text
    assert "Skills: " in text


def test_canonical_text_strips_html(job_factory):
    job = job_factory(description="<p>Build <b>ML</b> systems</p>")
    assert "<p>" not in canonical_job_text(job)
