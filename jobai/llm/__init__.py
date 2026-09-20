"""The one LLM interface in JOB.ai.

Local Ollama only. Every feature — resume parsing, profile extraction, job
understanding, query expansion, match reasoning, skill-gap analysis, the
Telegram conversation, cover letters, referral and cold emails — goes through
:func:`get_llm`. There are no per-feature clients and no external API keys.
"""

from jobai.llm.client import LLMError, LLMUnavailable, OllamaClient, get_llm

__all__ = ["OllamaClient", "get_llm", "LLMError", "LLMUnavailable"]
