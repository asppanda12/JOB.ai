"""JOB.ai core package.

Houses the reusable backend services that the Telegram bot, the ingestion
scripts and the CLI all share: configuration, the canonical job schema,
normalization, the hybrid retrieval pipeline and the single Ollama LLM
interface.

The legacy top-level packages (``Data_base``, ``resume_cold_mail``,
``genrativeai``, ``llama``, the per-source scraper folders) are still the
entry points they always were; they now delegate here instead of carrying
their own copies of this logic.
"""

__all__ = ["config", "schema"]
