"""Incremental indexing: only changed jobs get re-embedded."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

import pytest

from jobai.index_builder import assign_indices, index_jobs


class FakeDense:
    """Stands in for the FAISS index so the test needs no model."""

    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.embed_calls: List[List[str]] = []
        self.deleted: List[str] = []
        self.saved = 0

    def existing_hashes(self) -> Dict[str, str]:
        return {job_id: doc["content_hash"] for job_id, doc in self.docs.items()}

    def vector_ids_for(self, job_ids: Sequence[str]) -> List[str]:
        return [j for j in job_ids if j in self.docs]

    def add(self, texts, metadatas, ids):
        self.embed_calls.append(list(texts))
        for text, metadata, job_id in zip(texts, metadatas, ids):
            self.docs[job_id] = {"text": text, "content_hash": metadata["content_hash"]}

    def delete(self, ids):
        self.deleted.extend(ids)
        for job_id in ids:
            self.docs.pop(job_id, None)

    def save(self):
        self.saved += 1

    def count(self):
        return len(self.docs)

    def all_metadata(self):
        return []


def test_first_run_embeds_everything(job_factory):
    dense = FakeDense()
    stats = index_jobs([job_factory(source_job_id="1"), job_factory(source_job_id="2")],
                       dense=dense, rebuild_derived=False)
    assert stats["added"] == 2 and stats["unchanged"] == 0
    assert len(dense.embed_calls[0]) == 2


def test_unchanged_jobs_are_not_re_embedded(job_factory):
    dense = FakeDense()
    jobs = [job_factory(source_job_id="1")]
    index_jobs(jobs, dense=dense, rebuild_derived=False)
    dense.embed_calls.clear()

    stats = index_jobs([job_factory(source_job_id="1")], dense=dense, rebuild_derived=False)
    assert stats["unchanged"] == 1 and stats["added"] == 0
    assert dense.embed_calls == [], "an unchanged job must not be re-embedded"


def test_cosmetic_change_does_not_trigger_a_re_embed(job_factory):
    dense = FakeDense()
    index_jobs([job_factory(source_job_id="1")], dense=dense, rebuild_derived=False)
    dense.embed_calls.clear()

    stats = index_jobs([job_factory(source_job_id="1", salary="Rs. 40 LPA")],
                       dense=dense, rebuild_derived=False)
    assert stats["unchanged"] == 1
    assert dense.embed_calls == []


def test_meaningful_change_replaces_the_old_vector(job_factory):
    dense = FakeDense()
    index_jobs([job_factory(source_job_id="1")], dense=dense, rebuild_derived=False)
    dense.embed_calls.clear()

    stats = index_jobs([job_factory(source_job_id="1", description="A totally new role.")],
                       dense=dense, rebuild_derived=False)
    assert stats["updated"] == 1
    assert dense.deleted == ["linkedin:1"], "the stale vector must be removed"
    assert len(dense.embed_calls[0]) == 1


def test_jobs_without_text_are_skipped():
    from jobai.schema import Job

    dense = FakeDense()
    stats = index_jobs([Job()], dense=dense, rebuild_derived=False)
    assert stats["skipped"] == 1 or stats["added"] == 0


def test_indices_are_assigned_and_stable(job_factory):
    jobs = [job_factory(source_job_id=str(i)) for i in range(3)]
    assign_indices(jobs, start=10)
    assert [j.job_indx for j in jobs] == [10, 11, 12]
    assign_indices(jobs, start=99)
    assert [j.job_indx for j in jobs] == [10, 11, 12], "existing indices must not be reshuffled"
