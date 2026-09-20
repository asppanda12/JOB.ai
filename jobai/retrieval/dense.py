"""Dense retrieval over the existing FAISS store.

FAISS stays. The store on disk (``vector_store/index.faiss`` +
``index.pkl``) is a LangChain ``FAISS`` with an ``InMemoryDocstore``,
``IndexFlatL2``, 1024 dimensions, built with ``BAAI/bge-large-en-v1.5`` and
normalized embeddings. All of that is preserved: this module loads the same
files with the same loader, and writes back in the same format, so the index
already committed to the repository keeps working untouched.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from jobai.config import get_settings

logger = logging.getLogger(__name__)

_embeddings_cache: Dict[str, Any] = {}


def get_embeddings(model_name: Optional[str] = None):
    """Load (and cache) the sentence-transformer embedder.

    ``normalize_embeddings=True`` matches how the persisted index was built;
    changing it would silently invalidate every stored vector.
    """
    from langchain_huggingface import HuggingFaceEmbeddings

    name = model_name or get_settings().retrieval.embedding_model
    if name not in _embeddings_cache:
        logger.info("Loading embedding model %s", name)
        _embeddings_cache[name] = HuggingFaceEmbeddings(
            model_name=name,
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings_cache[name]


class DenseIndex:
    """Thin wrapper over the LangChain FAISS store."""

    def __init__(self, path: Optional[Path] = None, embeddings=None):
        settings = get_settings()
        self.path = Path(path or settings.retrieval.vector_db_path)
        self.embeddings = embeddings or get_embeddings()
        self._store = None

    # ---------------------------------------------------------------- loading

    @property
    def store(self):
        if self._store is None:
            self._store = self._load_or_create()
        return self._store

    def exists(self) -> bool:
        return (self.path / "index.faiss").exists() and (self.path / "index.pkl").exists()

    def _load_or_create(self):
        from langchain_community.vectorstores import FAISS

        if self.exists():
            logger.info("Loading FAISS index from %s", self.path)
            # allow_dangerous_deserialization: the pickle is ours, written by
            # this project's own indexer. Same flag the legacy loader used.
            return FAISS.load_local(
                str(self.path), self.embeddings, allow_dangerous_deserialization=True
            )
        logger.info("No FAISS index at %s; creating an empty one.", self.path)
        return self._empty_store()

    def _empty_store(self):
        import faiss
        from langchain_community.docstore.in_memory import InMemoryDocstore
        from langchain_community.vectorstores import FAISS

        dim = len(self.embeddings.embed_query("hello world"))
        return FAISS(
            embedding_function=self.embeddings,
            index=faiss.IndexFlatL2(dim),
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )

    def save(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self.store.save_local(str(self.path))
        logger.info("Saved FAISS index (%d vectors) to %s", self.count(), self.path)

    def count(self) -> int:
        try:
            return int(self.store.index.ntotal)
        except Exception:
            return 0

    # --------------------------------------------------------------- contents

    def existing_hashes(self) -> Dict[str, str]:
        """``job_id -> content_hash`` for everything already indexed.

        This is what makes indexing incremental: a job whose content hash is
        unchanged is never re-embedded.
        """
        out: Dict[str, str] = {}
        docstore = getattr(self.store, "docstore", None)
        mapping = getattr(docstore, "_dict", {}) or {}
        for doc in mapping.values():
            metadata = getattr(doc, "metadata", {}) or {}
            job_id = metadata.get("job_id") or metadata.get("id")
            if job_id:
                out[str(job_id)] = str(metadata.get("content_hash") or "")
        return out

    def vector_ids_for(self, job_ids: Sequence[str]) -> List[str]:
        """Docstore keys for the given canonical job ids."""
        wanted = set(map(str, job_ids))
        docstore = getattr(self.store, "docstore", None)
        mapping = getattr(docstore, "_dict", {}) or {}
        return [
            key
            for key, doc in mapping.items()
            if str((getattr(doc, "metadata", {}) or {}).get("job_id", "")) in wanted
        ]

    # ------------------------------------------------------------- mutations

    def add(self, texts: Sequence[str], metadatas: Sequence[Dict[str, Any]], ids: Sequence[str]) -> None:
        if not texts:
            return
        self.store.add_texts(texts=list(texts), metadatas=list(metadatas), ids=list(ids))

    def delete(self, ids: Sequence[str]) -> None:
        if not ids:
            return
        try:
            self.store.delete(list(ids))
        except Exception as exc:
            logger.warning("FAISS delete failed for %d ids: %s", len(ids), exc)

    # ------------------------------------------------------------- retrieval

    def search(self, query: str, k: int = 100) -> List[Tuple[Dict[str, Any], float]]:
        """Return ``(metadata, similarity)`` pairs, best first.

        LangChain hands back an L2 distance on normalized vectors; convert it to
        a bounded ``[0, 1]`` similarity so downstream scoring has a consistent
        scale. For unit vectors ``d^2 = 2 - 2*cos``, hence ``cos = 1 - d^2/2``.
        """
        if not query.strip() or self.count() == 0:
            return []
        try:
            hits = self.store.similarity_search_with_score(query, k=k)
        except Exception as exc:
            logger.error("Dense search failed: %s", exc)
            return []
        out: List[Tuple[Dict[str, Any], float]] = []
        for doc, distance in hits:
            similarity = max(0.0, min(1.0, 1.0 - (float(distance) ** 2) / 2.0))
            metadata = dict(getattr(doc, "metadata", {}) or {})
            metadata.setdefault("text", getattr(doc, "page_content", ""))
            out.append((metadata, similarity))
        return out

    def all_metadata(self) -> List[Dict[str, Any]]:
        """Every indexed job's metadata. Used to build BM25 and the graph."""
        docstore = getattr(self.store, "docstore", None)
        mapping = getattr(docstore, "_dict", {}) or {}
        out = []
        for doc in mapping.values():
            metadata = dict(getattr(doc, "metadata", {}) or {})
            metadata.setdefault("text", getattr(doc, "page_content", ""))
            out.append(metadata)
        return out
