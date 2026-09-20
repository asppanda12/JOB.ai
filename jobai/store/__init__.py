"""Persistence adapters. MongoDB stays the structured store; nothing moved."""

from jobai.store.mongo import JobStore, get_store

__all__ = ["JobStore", "get_store"]
