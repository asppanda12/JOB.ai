"""Job ingestion. Every source produces :class:`jobai.schema.Job`, nothing else."""

from jobai.ingest.base import JobSource, SourceResult, run_sources

__all__ = ["JobSource", "SourceResult", "run_sources"]
