"""The single Ollama interface: parsing, error handling, and that no external
provider is reachable from the codebase any more."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobai.config import PROJECT_ROOT, LLMSettings
from jobai.llm.client import LLMError, LLMUnavailable, OllamaClient, extract_json


# --------------------------------------------------- no external providers


def test_no_external_llm_provider_is_imported():
    """The whole point of the upgrade: nothing outside Ollama."""
    banned = [
        "langchain_groq", "ChatGroq", "GROQ_API_KEY", "langchain_openai",
        "ChatOpenAI", "HuggingFaceEndpoint", "llamaapi", "openrouter.ai",
        "OPENROUTER_BASE_URL", "HUGGINGFACE_TOKEN", "llama_cpp",
    ]
    offenders = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in {".venv", "tests", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in banned:
            # A mention inside a docstring explaining the removal is fine;
            # an actual import or key reference is not.
            for line in text.splitlines():
                stripped = line.strip()
                if token in line and (stripped.startswith(("import ", "from ")) or "=" in stripped and token.isupper()):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {stripped[:80]}")
    assert not offenders, "external LLM provider still referenced:\n" + "\n".join(offenders)


def test_no_hardcoded_api_keys():
    patterns = ["sk-or-v1-", "sk-ant-", "gsk_", "hf_"]
    offenders = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in {".venv", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            if pattern in text and "test_llm.py" not in str(path):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} contains {pattern!r}")
    assert not offenders, "\n".join(offenders)


# ------------------------------------------------------------ JSON handling


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Here you go: {"a": 1} hope that helps', {"a": 1}),
        ('[1, 2, 3]', [1, 2, 3]),
    ],
)
def test_extract_json_is_forgiving(raw, expected):
    assert extract_json(raw) == expected


def test_extract_json_raises_on_garbage():
    with pytest.raises(LLMError):
        extract_json("no json at all")


def test_non_ollama_provider_is_rejected():
    with pytest.raises(LLMError, match="local Ollama only"):
        OllamaClient(LLMSettings(provider="openai"))


def test_unreachable_server_gives_an_actionable_error():
    client = OllamaClient(LLMSettings(base_url="http://127.0.0.1:9", max_retries=0, timeout=2))
    with pytest.raises(LLMUnavailable) as exc:
        client.health()
    assert "ollama serve" in str(exc.value) or "Cannot reach Ollama" in str(exc.value)


# -------------------------------------------------- live model (integration)


@pytest.mark.integration
def test_model_is_installed(ollama):
    status = ollama.health()
    assert status["reachable"] and status["model_installed"], (
        f"run: ollama pull {status['model']}"
    )


@pytest.mark.integration
def test_structured_json_response(ollama):
    data = ollama.json('Return a JSON object with key "ok" set to true.')
    assert isinstance(data, dict)


@pytest.mark.integration
def test_query_expansion_keeps_the_original(ollama):
    from jobai.llm.tasks import expand_query

    result = expand_query("GenAI Engineer")
    assert result["original"] == "GenAI Engineer"
    assert isinstance(result["expansions"], list)


@pytest.mark.integration
def test_job_understanding_extracts_requirements(ollama):
    from jobai.llm.tasks import understand_job

    data = understand_job(
        "Senior ML Engineer. Requires 5+ years of Python and PyTorch. "
        "Nice to have: LangChain, Kubernetes. Remote friendly."
    )
    assert {"Python", "PyTorch"} <= set(data["required_skills"])
    assert data["experience_min_years"] == 5.0


@pytest.mark.integration
def test_resume_parsing_produces_the_full_profile_shape(ollama):
    from jobai.llm.tasks import parse_resume

    profile = parse_resume(
        "Jane Doe\nSenior Machine Learning Engineer\n"
        "5 years building recommender systems in Python, PyTorch and AWS.\n"
        "B.Tech, IIT Bombay, 2018. Based in Bengaluru."
    )
    for key in ("target_roles", "skills", "years_experience", "education", "experience"):
        assert key in profile
    assert any("python" in s.lower() for s in profile["skills"])


def test_job_understanding_degrades_without_ollama(monkeypatch):
    """Ingestion must keep working, with coarser data, when the model is down."""
    from jobai.llm import tasks

    def boom(*args, **kwargs):
        raise LLMUnavailable("down")

    monkeypatch.setattr(tasks, "get_llm", boom)
    data = tasks.understand_job("Requires Python and Kubernetes. 3+ years.")
    assert "Python" in data["required_skills"]
    assert data["experience_min_years"] == 3.0


def test_resume_parsing_degrades_without_ollama(monkeypatch):
    from jobai.llm import tasks

    def boom(*args, **kwargs):
        raise LLMUnavailable("down")

    monkeypatch.setattr(tasks, "get_llm", boom)
    profile = tasks.parse_resume("Experienced in Python, PyTorch and Kubernetes.")
    assert {"Python", "PyTorch", "Kubernetes"} <= set(profile["skills"])
