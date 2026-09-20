"""Shared fixtures.

Tests are split by what they need:

* unit tests (schema, normalization, dedup, fusion, filters, scoring) need
  nothing external and always run;
* tests marked ``integration`` need a live Ollama, MongoDB or network and are
  skipped automatically when those are absent.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from jobai.schema import Job


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: needs a live external service")
    config.addinivalue_line("markers", "network: needs internet access")
    config.addinivalue_line("markers", "slow: loads a transformer model")


@pytest.fixture
def job_factory():
    def make(**overrides) -> Job:
        defaults = dict(
            title="Machine Learning Engineer",
            company="Acme Technologies",
            description="Build ML systems with Python and PyTorch on AWS.",
            source="linkedin",
            source_job_id="1001",
            application_url="https://in.linkedin.com/jobs/view/ml-engineer-1001",
            skills=["Python", "PyTorch", "AWS"],
            experience_min=2.0,
            experience_max=5.0,
            experience_raw="2-5 years",
            location="Bengaluru, Karnataka, India",
            posted_date=datetime.now(timezone.utc),
        )
        defaults.update(overrides)
        return Job(**defaults).finalize()

    return make


@pytest.fixture
def profile():
    return {
        "target_roles": ["Machine Learning Engineer"],
        "skills": ["Python", "PyTorch", "AWS", "LangChain"],
        "years_experience": 3.0,
        "preferred_locations": ["Bengaluru"],
    }


def _ollama_up() -> bool:
    try:
        from jobai.llm import get_llm

        return get_llm().health()["model_installed"]
    except Exception:
        return False


def _mongo_up() -> bool:
    try:
        from jobai.store import get_store

        return get_store().ping()
    except Exception:
        return False


@pytest.fixture(scope="session")
def ollama():
    if not _ollama_up():
        pytest.skip("Ollama is not running, or the configured model is not pulled")
    from jobai.llm import get_llm

    return get_llm()


@pytest.fixture(scope="session")
def store():
    if not _mongo_up():
        pytest.skip("MongoDB is not reachable")
    from jobai.store import get_store

    return get_store()


@pytest.fixture(scope="session")
def dense_index():
    from jobai.retrieval.dense import DenseIndex

    index = DenseIndex()
    if not index.exists():
        pytest.skip("No FAISS index at VECTOR_DB_PATH")
    return index
