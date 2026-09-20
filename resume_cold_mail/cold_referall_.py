"""Referral messages, cover letters and cold emails.

The three public functions keep their original names and
``(chat_id, job_id)`` signatures, because ``telegram_bot.py`` wires them
straight to its inline buttons.

Changes underneath:

* Groq is gone. All three run on local Ollama via :mod:`jobai.llm.tasks`.
* The job lookup no longer depends on ``metadata.job_indx`` being an ``int``.
  The persisted index stores it as a string while ``master_data.py`` wrote it
  as an integer, so the old exact-match Mongo query returned ``None`` and the
  buttons raised. The lookup now compares as strings.
* The whole job dict is no longer interpolated into the prompt as a Python
  ``repr``; the writer gets structured JSON, which produces noticeably better
  letters.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from jobai.profile import profile_for_user
from jobai.recommend import generate_document
from jobai.store import get_store

logger = logging.getLogger(__name__)


def get_resume_data(chat_id: Any) -> Dict[str, Any]:
    """The stored structured profile for a user."""
    user = get_store().get_user(chat_id)
    if not user:
        raise ValueError(f"No registered user with chat_id {chat_id}")
    return profile_for_user(user)


def get_job_data(chat_id: Any, job_id: Any) -> Dict[str, Any]:
    """One recommended job, looked up by its index."""
    entry = get_store().find_recommendation(chat_id, job_id)
    if entry is None:
        raise ValueError(f"No job data found for chat_id {chat_id} and job_id {job_id}")
    return entry


def create_cold_mail(chat_id: Any, job_id: Any) -> str:
    return generate_document(chat_id, job_id, "cold_email")


def create_referral_mail(chat_id: Any, job_id: Any) -> str:
    return generate_document(chat_id, job_id, "referral")


def create_cover_letter_mail(chat_id: Any, job_id: Any) -> str:
    return generate_document(chat_id, job_id, "cover_letter")
