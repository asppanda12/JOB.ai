"""JOB.ai Telegram bot.

The user-facing flow is unchanged: /start registration (name, phone, email,
years of experience, CV), /update for recommendations, ten jobs per page with a
"Send More Jobs" button, and Referral / Cover Letter / Cold Emails buttons on
every job.

What changed is that the bot no longer holds any retrieval or LLM logic of its
own. It calls :mod:`jobai.recommend`, which owns the hybrid funnel, so the CLI
and the bot cannot drift apart. Other fixes:

* the hard-coded ``sys.path.append('E:/JOB.ai/JOB.ai')`` and the Windows
  ``vector_store`` path are gone; paths come from :mod:`jobai.config`;
* ``CallbackQueryHandler`` ordering no longer matters - previously the generic
  handler and the ``more_jobs`` handler both matched and pagination fired twice;
* registration validates the email and years-of-experience instead of storing
  whatever was typed and failing later inside Pydantic;
* a failure in one button reports a useful message rather than echoing a raw
  traceback into the chat;
* recommendations are computed once per ``/update`` and paginated from the
  stored result, rather than re-running retrieval on page 0 only.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from jobai.config import get_settings
from jobai.llm.client import LLMUnavailable
from jobai.profile import build_profile, extract_pdf_text, merge_registration
from jobai.recommend import generate_document, recommend_for_user, skill_gap_for_user
from jobai.store import get_store

logger = logging.getLogger(__name__)

JOBS_PER_PAGE = 10
NAME, PHONE, EMAIL, EXPERIENCE, RESUME = range(5)
# Kept as a dict because the original module exported it under this name.
STATES = {"FIRST": NAME, "SECOND": PHONE, "THIRD": EMAIL, "FOURTH": EXPERIENCE, "FIFTH": RESUME}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


@dataclass
class Config:
    token: str
    mongo_uri: str
    resume_folder: Path
    data_folder: Path
    vector_store_path: Path


def load_config() -> Config:
    """Configuration, read from the environment via :mod:`jobai.config`."""
    settings = get_settings()
    if not settings.telegram_token:
        raise RuntimeError("TELEGRAM_TOKEN (or TOKEN) is not set. See .env.example.")
    return Config(
        token=settings.telegram_token,
        mongo_uri=settings.store.mongo_uri,
        resume_folder=settings.resume_dir,
        data_folder=settings.raw_data_dir,
        vector_store_path=settings.retrieval.vector_db_path,
    )


class TelegramBot:
    def __init__(self, config: Config):
        self.config = config
        self.application = ApplicationBuilder().token(config.token).build()
        self.bot = self.application.bot
        self.store = get_store(config.mongo_uri)
        self.setup_handlers()

    # ---------------------------------------------------------------- wiring

    def setup_handlers(self) -> None:
        conversation = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.first_response)],
                PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.second_response)],
                EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.third_response)],
                EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.fourth_response)],
                RESUME: [MessageHandler(filters.Document.ALL | filters.TEXT, self.fifth_response)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True,
        )
        self.application.add_handler(conversation)
        self.application.add_handler(CommandHandler("update", self.broadcast_command))
        self.application.add_handler(CommandHandler("search", self.search_command))
        self.application.add_handler(CommandHandler("gaps", self.gaps_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        # Patterns are disjoint, so exactly one handler fires per callback.
        self.application.add_handler(CallbackQueryHandler(self.more_jobs_callback, pattern=r"^more_jobs:"))
        self.application.add_handler(
            CallbackQueryHandler(self.document_callback, pattern=r"^(referral|cover_letter|cold_email):")
        )

    # ---------------------------------------------------------- registration

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text(
            "Welcome to JOB.ai - one stop for your job search.\nPlease enter your full name:"
        )
        return NAME

    async def first_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data["full_name"] = update.message.text.strip()
        await update.message.reply_text(
            f"Hi {context.user_data['full_name']}. Please enter your phone number:"
        )
        return PHONE

    async def second_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data["phone_number"] = update.message.text.strip()
        await update.message.reply_text("Thanks. Please enter your email:")
        return EMAIL

    async def third_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        email = update.message.text.strip()
        if not _EMAIL_RE.match(email):
            await update.message.reply_text("That does not look like an email address. Please try again:")
            return EMAIL
        context.user_data["email"] = email
        await update.message.reply_text(
            "Thanks. How many years of professional experience do you have? "
            "Use a decimal, for example 1.3 (enter 0 if you are a fresher):"
        )
        return EXPERIENCE

    async def fourth_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            years = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Please enter a number, for example 1.3:")
            return EXPERIENCE
        context.user_data["years_of_experience"] = years
        await update.message.reply_text(
            f"Noted: {years} years. Now please upload your latest CV as a PDF:"
        )
        return RESUME

    async def fifth_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        document = update.message.document
        if not document or document.mime_type != "application/pdf":
            await update.message.reply_text("Please send your CV as a PDF document.")
            return RESUME

        chat_id = update.message.chat.id
        self.config.resume_folder.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w.-]+", "_", context.user_data.get("full_name", "user"))
        resume_path = self.config.resume_folder / f"{safe_name}_{chat_id}.pdf"

        telegram_file = await document.get_file()
        await telegram_file.download_to_drive(str(resume_path))
        await update.message.reply_text("Got your CV. Reading it now, this takes a few seconds...")

        try:
            # Parsing runs a local model, so keep it off the event loop.
            profile = await asyncio.to_thread(self._parse_resume, str(resume_path))
        except LLMUnavailable as exc:
            await update.message.reply_text(f"Could not read your CV right now.\n{exc}")
            return ConversationHandler.END
        except Exception as exc:
            logger.exception("Resume parsing failed for chat %s", chat_id)
            await update.message.reply_text(f"Could not read that PDF: {exc}")
            return RESUME

        registration = {
            "chat_id": chat_id,
            "full_name": context.user_data.get("full_name"),
            "phone_number": context.user_data.get("phone_number"),
            "email": context.user_data.get("email"),
            "years_of_experience": context.user_data.get("years_of_experience"),
        }
        merged = merge_registration(profile, registration)
        self.store.upsert_user(
            {
                **registration,
                "resume_path": str(resume_path),
                "resume_json": profile,   # legacy key, still read by older code
                "profile": merged,        # canonical structured profile
            }
        )

        skills = ", ".join(merged.get("skills", [])[:12]) or "none detected"
        await update.message.reply_text(
            f"Registration complete.\n\nSkills I picked up: {skills}\n\n"
            "Send /update to get your job recommendations."
        )
        return ConversationHandler.END

    @staticmethod
    def _parse_resume(resume_path: str) -> Dict[str, Any]:
        return build_profile(extract_pdf_text(resume_path))

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Cancelled. Send /start to begin again.")
        return ConversationHandler.END

    # ------------------------------------------------------- recommendations

    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.message.chat.id
        if not self.store.get_user(chat_id):
            await update.message.reply_text("You are not registered yet. Send /start to register.")
            return
        await update.message.reply_text("Finding jobs for you. This takes a moment...")
        try:
            outcome = await asyncio.to_thread(recommend_for_user, chat_id, top_k=20, explain=True)
        except LLMUnavailable as exc:
            await update.message.reply_text(f"The local model is not available.\n{exc}")
            return
        except Exception as exc:
            logger.exception("Recommendation failed for chat %s", chat_id)
            await update.message.reply_text(f"Could not build recommendations: {exc}")
            return

        if not outcome["jobs"]:
            await update.message.reply_text(
                "No matching jobs found. Try /search <role>, or re-upload a CV with more detail."
            )
            return
        await self.broadcast_message(chat_id, 0)

    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.message.chat.id
        query = " ".join(context.args or []).strip()
        if not query:
            await update.message.reply_text("Usage: /search GenAI Engineer")
            return
        if not self.store.get_user(chat_id):
            await update.message.reply_text("You are not registered yet. Send /start to register.")
            return
        await update.message.reply_text(f"Searching for: {query}")
        try:
            await asyncio.to_thread(recommend_for_user, chat_id, query=query, top_k=20, explain=True)
        except Exception as exc:
            logger.exception("Search failed for chat %s", chat_id)
            await update.message.reply_text(f"Search failed: {exc}")
            return
        await self.broadcast_message(chat_id, 0)

    async def gaps_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.message.chat.id
        try:
            gaps = await asyncio.to_thread(skill_gap_for_user, chat_id)
        except Exception as exc:
            await update.message.reply_text(f"Could not analyse your skill gaps: {exc}")
            return
        critical = ", ".join(gaps.get("missing_critical", [])[:10]) or "none"
        nice = ", ".join(gaps.get("missing_nice_to_have", [])[:10]) or "none"
        message = f"<b>Skill gaps</b>\n\nWorth learning: {html.escape(critical)}\nNice to have: {html.escape(nice)}"
        if gaps.get("advice"):
            message += f"\n\n{html.escape(gaps['advice'])}"
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "/start - register or update your details\n"
            "/update - get personalised job recommendations\n"
            "/search <role> - search for a specific role\n"
            "/gaps - see which skills you are missing\n"
            "/cancel - cancel the current step"
        )

    async def broadcast_message(self, chat_id: int, start_index: int) -> None:
        """Send one page of the stored recommendations."""
        jobs: List[Dict[str, Any]] = self.store.get_recommendations(chat_id)
        if not jobs:
            await self.bot.send_message(chat_id, text="No job recommendations found. Send /update first.")
            return

        total = len(jobs)
        for entry in jobs[start_index : start_index + JOBS_PER_PAGE]:
            await self._send_job_message(chat_id, entry)

        next_index = start_index + JOBS_PER_PAGE
        if next_index < total:
            keyboard = [[InlineKeyboardButton("Send More Jobs", callback_data=f"more_jobs:{next_index}")]]
            await self.bot.send_message(
                chat_id,
                text=f"Showing {min(next_index, total)} of {total}.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await self.bot.send_message(chat_id, text="You have reached the end of your recommendations.")

    async def _send_job_message(self, chat_id: int, entry: Dict[str, Any]) -> None:
        job = entry.get("metadata", entry)
        job_ref = job.get("job_indx", 0)
        keyboard = [[
            InlineKeyboardButton("Referral", callback_data=f"referral:{job_ref}"),
            InlineKeyboardButton("Cover Letter", callback_data=f"cover_letter:{job_ref}"),
            InlineKeyboardButton("Cold Email", callback_data=f"cold_email:{job_ref}"),
        ]]

        def esc(value: Any) -> str:
            return html.escape(str(value or "")) or "-"

        lines = [
            f"<b>{esc(job.get('job_title'))}</b>",
            f"Company: {esc(job.get('company_name'))}",
            f"Experience: {esc(job.get('experience'))}",
            f"Location: {esc(job.get('location'))}",
            f"Source: {esc(job.get('Source'))}",
        ]
        link = job.get("job_link")
        if link and link != "N/A":
            lines.append(f"<a href='{html.escape(str(link), quote=True)}'>Apply here</a>")

        skills = job.get("skills_list") or job.get("skills")
        if skills:
            text = ", ".join(skills) if isinstance(skills, list) else str(skills)
            lines.append(f"Skills: {esc(text[:300])}")

        # The new transparency signals, when present.
        if entry.get("explanation"):
            lines.append(f"\n<b>Why:</b> {esc(', '.join(entry['explanation']))}")
        if entry.get("llm_verdict"):
            lines.append(f"<i>{esc(entry['llm_verdict'])}</i>")
        if entry.get("missing_skills"):
            lines.append(f"Missing: {esc(', '.join(entry['missing_skills'][:5]))}")
        if entry.get("match_score") is not None:
            lines.append(f"Match: {entry['match_score']:.0%}")

        await self.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    # --------------------------------------------------------------- buttons

    async def more_jobs_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        try:
            start_index = int(query.data.split(":", 1)[1])
        except (IndexError, ValueError):
            return
        await self.broadcast_message(query.message.chat_id, start_index)

    async def document_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        chat_id = update.effective_chat.id
        kind, _, job_ref = query.data.partition(":")

        await self.bot.send_message(chat_id, text="Writing that for you...")
        try:
            text = await asyncio.to_thread(generate_document, chat_id, job_ref, kind)
        except LLMUnavailable as exc:
            await self.bot.send_message(chat_id, text=f"The local model is not available.\n{exc}")
            return
        except LookupError as exc:
            await self.bot.send_message(chat_id, text=str(exc))
            return
        except Exception as exc:
            logger.exception("Document generation failed (%s) for chat %s", kind, chat_id)
            await self.bot.send_message(chat_id, text=f"Could not generate that: {exc}")
            return

        # Telegram caps a message at 4096 characters.
        for chunk in _chunk(text or "Nothing was generated.", 4000):
            await self.bot.send_message(chat_id=chat_id, text=chunk)

    def run(self) -> None:
        logger.info("Bot is running...")
        self.application.run_polling()


def _chunk(text: str, size: int) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    TelegramBot(load_config()).run()


if __name__ == "__main__":
    main()
