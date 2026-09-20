"""Ollama client: the single LLM abstraction for the whole application.

Talks to the Ollama HTTP API directly with ``requests`` rather than going
through LangChain, because the only things needed are ``/api/chat`` and
``/api/tags`` and that keeps the dependency surface (and the failure modes)
small.

Failure policy: when Ollama is unreachable or the model is missing, callers get
an :class:`LLMUnavailable` carrying an actionable message ("ollama pull
qwen2.5:7b"). Nothing in the retrieval path crashes — hybrid retrieval and
reranking work without the LLM, only the reasoning layer degrades.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from jobai.config import LLMSettings, get_settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The LLM was reachable but could not produce a usable answer."""


class LLMUnavailable(LLMError):
    """Ollama is not reachable, or the configured model is not installed."""


def _strip_code_fence(text: str) -> str:
    fenced = re.match(r"^\s*```(?:json|JSON)?\s*(.*?)\s*```\s*$", text, re.DOTALL)
    return fenced.group(1) if fenced else text


def extract_json(text: str) -> Any:
    """Pull a JSON value out of a model response.

    Qwen is well-behaved with ``format=json`` but still occasionally wraps the
    object in prose or a code fence, so parse defensively instead of failing
    the whole recommendation.
    """
    if text is None:
        raise LLMError("empty LLM response")
    candidate = _strip_code_fence(str(text).strip())
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost balanced object or array.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        end = candidate.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"could not parse JSON from LLM response: {candidate[:200]!r}")


class OllamaClient:
    """Thin, retrying wrapper over the local Ollama server."""

    def __init__(self, settings: Optional[LLMSettings] = None):
        self.settings = settings or get_settings().llm
        if self.settings.provider != "ollama":
            raise LLMError(
                f"LLM_PROVIDER={self.settings.provider!r} is not supported; "
                "JOB.ai runs on local Ollama only (LLM_PROVIDER=ollama)."
            )
        self.base_url = self.settings.base_url
        self.model = self.settings.model
        self._session = requests.Session()
        self._availability: Optional[str] = None

    # ------------------------------------------------------------- lifecycle

    def health(self) -> Dict[str, Any]:
        """Check the server and whether the configured model is present."""
        try:
            response = self._session.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LLMUnavailable(
                f"Cannot reach Ollama at {self.base_url}: {exc}. "
                "Start it with `ollama serve`, or set OLLAMA_BASE_URL."
            ) from exc
        payload = response.json()
        names = [m.get("name", "") for m in payload.get("models", [])]
        installed = any(n == self.model or n.split(":")[0] == self.model.split(":")[0] for n in names)
        return {"reachable": True, "models": names, "model": self.model, "model_installed": installed}

    def ensure_ready(self) -> None:
        status = self.health()
        if not status["model_installed"]:
            raise LLMUnavailable(
                f"Ollama is running but the model {self.model!r} is not installed. "
                f"Run: ollama pull {self.model}"
            )

    # ------------------------------------------------------------ generation

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
    ) -> str:
        options: Dict[str, Any] = {
            "temperature": self.settings.temperature if temperature is None else temperature,
            "num_ctx": self.settings.num_ctx,
        }
        if max_tokens:
            options["num_predict"] = max_tokens
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if json_mode:
            body["format"] = "json"

        last_error: Optional[Exception] = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._session.post(
                    f"{self.base_url}/api/chat", json=body, timeout=self.settings.timeout
                )
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Ollama request failed (attempt %s): %s", attempt + 1, exc)
                time.sleep(min(2**attempt, 8))
                continue

            if response.status_code == 404:
                raise LLMUnavailable(
                    f"Ollama does not have the model {self.model!r}. Run: ollama pull {self.model}"
                )
            if response.status_code >= 500:
                last_error = LLMError(f"Ollama returned {response.status_code}: {response.text[:200]}")
                time.sleep(min(2**attempt, 8))
                continue
            response.raise_for_status()
            content = (response.json().get("message") or {}).get("content", "")
            if content.strip():
                return content
            last_error = LLMError("Ollama returned an empty message")

        raise LLMUnavailable(
            f"Ollama at {self.base_url} did not answer after "
            f"{self.settings.max_retries + 1} attempts: {last_error}"
        )

    def complete(self, prompt: str, *, system: Optional[str] = None, **kwargs: Any) -> str:
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, **kwargs)

    def json(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        default: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Ask for JSON. Returns ``default`` on a parse failure if one is given."""
        kwargs.setdefault("json_mode", True)
        kwargs.setdefault("temperature", 0.0)
        raw = self.complete(prompt, system=system, **kwargs)
        try:
            return extract_json(raw)
        except LLMError:
            if default is not None:
                logger.warning("LLM returned unparseable JSON; using default.")
                return default
            raise


_client: Optional[OllamaClient] = None
_lock = threading.Lock()


def get_llm(refresh: bool = False) -> OllamaClient:
    """Process-wide singleton. One client, one HTTP session, one config."""
    global _client
    with _lock:
        if _client is None or refresh:
            _client = OllamaClient()
    return _client
