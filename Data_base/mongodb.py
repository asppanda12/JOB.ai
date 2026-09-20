"""MongoDB access helpers.

The three factory functions below are the original public API and keep their
exact names, signatures and return values (a ``pymongo`` collection), so every
existing caller works unchanged. They now delegate to
:class:`jobai.store.JobStore` so the whole application shares one connection
pool instead of opening a new :class:`MongoClient` on every call.

Two fixes came with the move:

* ``tls=True`` is no longer forced on every connection. It is required by Atlas
  but breaks a plain local ``mongod``, so it is now inferred from the URI.
* failures raise instead of printing and returning ``None``; the old behaviour
  turned an unreachable database into an ``AttributeError`` several frames later.
"""

from __future__ import annotations

from typing import Optional

from jobai.store import get_store


def create_a_database(str_uri: Optional[str] = None):
    """The user collection (``USER.JOB_USER``)."""
    return get_store(str_uri).users


def create_a_job_database(str_uri: Optional[str] = None):
    """The canonical job collection (``USER_1.JOB_Data``)."""
    return get_store(str_uri).jobs


def create_a_job_database_specific_user(str_uri: Optional[str] = None):
    """Per-user recommendations (``USER_1.Job_specific``)."""
    return get_store(str_uri).recommendations
