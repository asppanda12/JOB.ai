"""BM25 lexical retrieval.

Dense embeddings blur exact tokens: a bge vector cannot reliably tell
"LangGraph" from "LangChain", or "C++" from "C". For a job search those exact
strings are precisely what a candidate is filtering on, so BM25 runs beside
FAISS and contributes its own ranking to the fusion step.
"""

from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Keep +, # and . inside tokens so "c++", "c#" and "node.js" survive tokenization.
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")


def tokenize(text: str) -> List[str]:
    tokens = _TOKEN.findall((text or "").lower())
    out: List[str] = []
    for token in tokens:
        token = token.strip(".-")
        if not token:
            continue
        out.append(token)
        # "node.js" should also match a query for "node".
        if "." in token or "-" in token:
            out.extend(p for p in re.split(r"[.\-]", token) if p)
    return out


class BM25Index:
    """Okapi BM25 over the canonical job text plus the skill list.

    Skills are appended a second time on purpose: it is a crude but effective
    field boost that makes an exact skill hit outrank an incidental mention of
    the same word in a description.
    """

    def __init__(self, path: Optional[Path] = None):
        from jobai.config import get_settings

        self.path = Path(path or get_settings().retrieval.bm25_path)
        self._bm25 = None
        self.job_ids: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []

    @staticmethod
    def _document_text(metadata: Dict[str, Any]) -> str:
        from jobai.normalize.skills import skills_from_metadata

        # Index both the raw blob and the parsed canonical tokens, so a query
        # for "PyTorch" hits whether the row is legacy or canonical.
        raw = metadata.get("skills") or ""
        raw_text = raw if isinstance(raw, str) else " ".join(map(str, raw))
        skills_text = " ".join([raw_text, " ".join(skills_from_metadata(metadata))]).strip()
        return " ".join(
            [
                str(metadata.get("job_title") or metadata.get("title") or ""),
                str(metadata.get("company_name") or metadata.get("company") or ""),
                str(metadata.get("job_category") or metadata.get("job_type") or ""),
                str(metadata.get("location") or ""),
                skills_text,
                skills_text,  # deliberate field boost
                str(metadata.get("text") or metadata.get("normalized_text") or ""),
            ]
        )

    def build(self, metadatas: Sequence[Dict[str, Any]]) -> "BM25Index":
        # BM25Plus, not BM25Okapi. Okapi's IDF is log((N - df + 0.5) / (df + 0.5)),
        # which is exactly 0 when a term appears in half the corpus and negative
        # above that - so a genuinely matching query can score 0 and return
        # nothing. BM25Plus uses log((N + 1) / df), which stays positive for
        # every term that occurs at all.
        from rank_bm25 import BM25Plus

        self.metadatas = [dict(m) for m in metadatas]
        self.job_ids = [str(m.get("job_id") or m.get("id") or i) for i, m in enumerate(self.metadatas)]
        corpus = [tokenize(self._document_text(m)) for m in self.metadatas]
        if not corpus:
            self._bm25 = None
            return self
        self._bm25 = BM25Plus(corpus)
        logger.info("Built BM25 index over %d jobs", len(corpus))
        return self

    def search(self, query: str, k: int = 100) -> List[Tuple[Dict[str, Any], float]]:
        if self._bm25 is None or not query.strip():
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        best = float(scores[top[0]]) if top and scores[top[0]] > 0 else 0.0
        results = []
        for i in top:
            score = float(scores[i])
            if score <= 0:
                continue
            # Normalize against the best hit so the value is comparable to the
            # dense similarity; fusion uses ranks, but scoring uses the value.
            results.append((self.metadatas[i], score / best if best else 0.0))
        return results

    # ---------------------------------------------------------- persistence

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "wb") as handle:
            pickle.dump({"metadatas": self.metadatas, "job_ids": self.job_ids}, handle)

    def load(self) -> bool:
        """Rebuild from the cached corpus. Returns False when there is none."""
        if not self.path.exists():
            return False
        try:
            with open(self.path, "rb") as handle:
                payload = pickle.load(handle)
        except Exception as exc:
            logger.warning("Could not load BM25 cache: %s", exc)
            return False
        self.build(payload.get("metadatas", []))
        return self._bm25 is not None
