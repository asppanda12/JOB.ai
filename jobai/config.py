"""Centralized configuration for JOB.ai.

Everything tunable lives here and is read from the environment (see
``.env.example``).  Nothing in the codebase should hard-code a model name, a
filesystem path, a database URI or a scoring weight; import ``settings``
instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

load_dotenv()

# Repository root, resolved from this file so the project works from any cwd.
# The legacy code hard-coded ``E:/JOB.ai/JOB.ai`` which only ever worked on one
# Windows machine.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return default if value is None or value == "" else value


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    return _env(key, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def _env_path(key: str, default: Path) -> Path:
    raw = _env(key)
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path)


@dataclass(frozen=True)
class LLMSettings:
    """Local Ollama is the only LLM provider. No external API keys."""

    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "ollama"))
    base_url: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"))
    model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5:7b"))
    temperature: float = field(default_factory=lambda: _env_float("OLLAMA_TEMPERATURE", 0.2))
    num_ctx: int = field(default_factory=lambda: _env_int("OLLAMA_NUM_CTX", 8192))
    timeout: int = field(default_factory=lambda: _env_int("OLLAMA_TIMEOUT", 180))
    max_retries: int = field(default_factory=lambda: _env_int("OLLAMA_MAX_RETRIES", 2))


@dataclass(frozen=True)
class RetrievalSettings:
    embedding_model: str = field(default_factory=lambda: _env("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5"))
    reranker_model: str = field(
        default_factory=lambda: _env("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    )
    vector_db_path: Path = field(default_factory=lambda: _env_path("VECTOR_DB_PATH", PROJECT_ROOT / "vector_store"))
    bm25_path: Path = field(default_factory=lambda: _env_path("BM25_INDEX_PATH", PROJECT_ROOT / "vector_store" / "bm25.pkl"))
    profile_cache_path: Path = field(
        default_factory=lambda: _env_path("PROFILE_CACHE_PATH", PROJECT_ROOT / ".cache" / "profiles")
    )

    # Candidate-set sizes for each stage of the funnel.
    dense_k: int = field(default_factory=lambda: _env_int("DENSE_K", 150))
    lexical_k: int = field(default_factory=lambda: _env_int("LEXICAL_K", 150))
    graph_k: int = field(default_factory=lambda: _env_int("GRAPH_K", 150))
    fusion_k: int = field(default_factory=lambda: _env_int("FUSION_K", 80))
    rerank_k: int = field(default_factory=lambda: _env_int("RERANK_K", 20))
    rrf_k: int = field(default_factory=lambda: _env_int("RRF_K", 60))

    reranker_enabled: bool = field(default_factory=lambda: _env_bool("RERANKER_ENABLED", True))
    graph_enabled: bool = field(default_factory=lambda: _env_bool("GRAPH_ENABLED", True))
    query_expansion_enabled: bool = field(default_factory=lambda: _env_bool("QUERY_EXPANSION_ENABLED", True))

    freshness_half_life_days: float = field(default_factory=lambda: _env_float("FRESHNESS_HALF_LIFE_DAYS", 21.0))


@dataclass(frozen=True)
class ScoringWeights:
    """Weights for the transparent match score.

    Every signal is stored alongside the score so a recommendation can explain
    itself. Override any of them from the environment as ``WEIGHT_<NAME>``.
    """

    reranker_score: float = field(default_factory=lambda: _env_float("WEIGHT_RERANKER_SCORE", 0.30))
    semantic_match: float = field(default_factory=lambda: _env_float("WEIGHT_SEMANTIC_MATCH", 0.15))
    required_skill_match: float = field(default_factory=lambda: _env_float("WEIGHT_REQUIRED_SKILL_MATCH", 0.18))
    preferred_skill_match: float = field(default_factory=lambda: _env_float("WEIGHT_PREFERRED_SKILL_MATCH", 0.05))
    skill_match: float = field(default_factory=lambda: _env_float("WEIGHT_SKILL_MATCH", 0.10))
    experience_match: float = field(default_factory=lambda: _env_float("WEIGHT_EXPERIENCE_MATCH", 0.08))
    location_match: float = field(default_factory=lambda: _env_float("WEIGHT_LOCATION_MATCH", 0.05))
    role_match: float = field(default_factory=lambda: _env_float("WEIGHT_ROLE_MATCH", 0.05))
    graph_similarity: float = field(default_factory=lambda: _env_float("WEIGHT_GRAPH_SIMILARITY", 0.02))
    freshness: float = field(default_factory=lambda: _env_float("WEIGHT_FRESHNESS", 0.02))

    def as_dict(self) -> Dict[str, float]:
        return {
            "reranker_score": self.reranker_score,
            "semantic_match": self.semantic_match,
            "required_skill_match": self.required_skill_match,
            "preferred_skill_match": self.preferred_skill_match,
            "skill_match": self.skill_match,
            "experience_match": self.experience_match,
            "location_match": self.location_match,
            "role_match": self.role_match,
            "graph_similarity": self.graph_similarity,
            "freshness": self.freshness,
        }


@dataclass(frozen=True)
class GraphSettings:
    uri: str = field(default_factory=lambda: _env("GRAPH_DB_URI", "bolt://localhost:7687"))
    user: str = field(default_factory=lambda: _env("GRAPH_DB_USER", "neo4j"))
    password: str = field(default_factory=lambda: _env("GRAPH_DB_PASSWORD", ""))
    database: str = field(default_factory=lambda: _env("GRAPH_DB_DATABASE", "neo4j"))
    # When Neo4j is unreachable the retrieval pipeline transparently falls back
    # to an equivalent in-process graph built from the job store.
    fallback_path: Path = field(
        default_factory=lambda: _env_path("GRAPH_FALLBACK_PATH", PROJECT_ROOT / ".cache" / "graph.json")
    )


@dataclass(frozen=True)
class StoreSettings:
    mongo_uri: str = field(default_factory=lambda: _env("MONGO_DB_URI", "mongodb://localhost:27017"))
    user_db: str = field(default_factory=lambda: _env("MONGO_USER_DB", "USER"))
    user_collection: str = field(default_factory=lambda: _env("MONGO_USER_COLLECTION", "JOB_USER"))
    job_db: str = field(default_factory=lambda: _env("MONGO_JOB_DB", "USER_1"))
    job_collection: str = field(default_factory=lambda: _env("MONGO_JOB_COLLECTION", "JOB_Data"))
    recommendation_collection: str = field(
        default_factory=lambda: _env("MONGO_RECOMMENDATION_COLLECTION", "Job_specific")
    )


@dataclass(frozen=True)
class ScrapeSettings:
    headless: bool = field(default_factory=lambda: _env_bool("SCRAPER_HEADLESS", True))
    request_delay: float = field(default_factory=lambda: _env_float("SCRAPER_REQUEST_DELAY", 2.5))
    page_timeout: int = field(default_factory=lambda: _env_int("SCRAPER_PAGE_TIMEOUT", 25))
    max_retries: int = field(default_factory=lambda: _env_int("SCRAPER_MAX_RETRIES", 2))
    max_pages: int = field(default_factory=lambda: _env_int("SCRAPER_MAX_PAGES", 5))
    max_jobs_per_source: int = field(default_factory=lambda: _env_int("SCRAPER_MAX_JOBS_PER_SOURCE", 200))
    user_agent: str = field(
        default_factory=lambda: _env(
            "SCRAPER_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        )
    )
    chromedriver_path: str = field(default_factory=lambda: _env("CHROMEDRIVER_PATH", ""))
    # Optional proxy list file. Absent -> direct connections, which is the
    # default; proxies are never required for the pipeline to run.
    proxy_file: str = field(default_factory=lambda: _env("SCRAPER_PROXY_FILE", ""))
    linkedin_locations: str = field(default_factory=lambda: _env("LINKEDIN_LOCATIONS", "India"))
    linkedin_keywords: str = field(
        default_factory=lambda: _env("LINKEDIN_KEYWORDS", "Software Engineer|Data Scientist|Machine Learning Engineer")
    )
    naukri_keywords: str = field(
        default_factory=lambda: _env("NAUKRI_KEYWORDS", "software engineer|data scientist|machine learning engineer")
    )
    naukri_locations: str = field(default_factory=lambda: _env("NAUKRI_LOCATIONS", "india"))


@dataclass(frozen=True)
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    graph: GraphSettings = field(default_factory=GraphSettings)
    store: StoreSettings = field(default_factory=StoreSettings)
    scrape: ScrapeSettings = field(default_factory=ScrapeSettings)
    telegram_token: str = field(default_factory=lambda: _env("TELEGRAM_TOKEN", _env("TOKEN")))
    resume_dir: Path = field(default_factory=lambda: _env_path("RESUME_DIR", PROJECT_ROOT / "data" / "resumes"))
    raw_data_dir: Path = field(default_factory=lambda: _env_path("RAW_DATA_DIR", PROJECT_ROOT / "data" / "raw"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Re-read the environment. Used by tests that monkeypatch env vars."""
    get_settings.cache_clear()
    load_dotenv(override=True)
    return get_settings()


settings = get_settings()
