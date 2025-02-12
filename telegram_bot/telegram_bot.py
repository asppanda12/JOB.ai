import os
import sys
sys.path.append('E:/JOB.ai/JOB.ai')  
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import os
import sys
from pathlib import Path
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
)
from resume_cold_mail.pdf_data_extractor import extract_pdf_text
from Data_base.mongodb import create_a_database, create_a_job_database_specific_user
from Data_base.schema_for_mongo_db import User
from Data_base.faiss_db_v2 import JobSearchEngine
from resume_cold_mail.cold_referall_ import create_referral_mail,create_cover_letter_mail,create_cold_mail
# Constants
JOBS_PER_PAGE = 10
STATES = {
    'FIRST': 0,
    'SECOND': 1,
    'THIRD': 2,
    'FOURTH': 3,
    'FIFTH': 4
}

@dataclass
class Config:
    token: str
    mongo_uri: str
    resume_folder: Path
    data_folder: Path
    vector_store_path: Path

def load_config() -> Config:
    """Load configuration from environment variables."""
    load_dotenv()
    return Config(
        token=os.getenv('TOKEN'),
        mongo_uri=os.getenv('MONGO_DB_URI'),
        resume_folder=Path('JOB.ai/job_resume'),
        data_folder=Path('JOB.ai/data_for_bot'),
        vector_store_path=Path('E:/JOB.ai/JOB.ai/vector_store')
    )

class TelegramBot:
    def __init__(self, config: Config):
        self.config = config
        self.bot = Bot(token=config.token)
        self.application = ApplicationBuilder().token(config.token).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Set up all message and callback handlers."""
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                STATES['FIRST']: [MessageHandler(filters.TEXT, self.first_response)],
                STATES['SECOND']: [MessageHandler(filters.TEXT, self.second_response)],
                STATES['THIRD']: [MessageHandler(filters.TEXT, self.third_response)],
                STATES['FOURTH']: [MessageHandler(filters.TEXT, self.fourth_response)],
                STATES['FIFTH']: [MessageHandler(
                    filters.Document.ALL | filters.TEXT | filters.VIDEO | filters.PHOTO,
                    self.fifth_response
                )],
            },
            fallbacks=[CommandHandler('cancel', ConversationHandler.END)],
            allow_reentry=True
        )

        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler('update', self.broadcast_command))
        self.application.add_handler(CallbackQueryHandler(self.more_jobs_callback, pattern=r"^more_jobs:"))
        self.application.add_handler(CallbackQueryHandler(self.button_click))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the conversation and ask for name."""
        await update.message.reply_text('Welcome! One stop solution for all your job needs. Please enter your full name:')
        return STATES['FIRST']

    async def first_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle name input and ask for phone number."""
        context.user_data['full_name'] = update.message.text
        await update.message.reply_text(
            f'Hi {context.user_data["full_name"]}. Hope you are having a great time here. Please enter your phone number:'
        )
        return STATES['SECOND']

    async def second_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle phone number input and ask for email."""
        context.user_data['phone_number'] = update.message.text
        await update.message.reply_text('Thank you for your phone number. Please enter your email:')
        return STATES['THIRD']

    async def third_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle email input and ask for years of experience."""
        context.user_data['email'] = update.message.text
        await update.message.reply_text(
            'Thank you for your email. Please enter your Year Of Experience, in format of years in decimal  eg: 1.3 Please provide this in decimals:'
        )
        return STATES['FOURTH']

    async def fourth_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle years of experience input and ask for CV."""
        context.user_data['years_of_experience'] = update.message.text
        await update.message.reply_text(
            f'Thank you! Your YOE has been updated to {update.message.text}. Please provide us with your latest CV:'
        )
        return STATES['FIFTH']

    async def fifth_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle CV upload and complete registration."""
        if not update.message.document or update.message.document.mime_type != 'application/pdf':
            await update.message.reply_text('Please send a valid PDF document.')
            return STATES['FIFTH']

        resume = update.message.document
        file = await resume.get_file()
        chat_id = update.message.chat.id
        full_name = context.user_data.get('full_name')

        # Set up directories and save resume
        self.config.resume_folder.mkdir(parents=True, exist_ok=True)
        self.config.data_folder.mkdir(parents=True, exist_ok=True)
        
        resume_path = self.config.resume_folder / f'{full_name}_{chat_id}.pdf'
        await file.download_to_drive(str(resume_path))
        
        # Create user record
        user_data = User(
            chat_id=chat_id,
            full_name=full_name,
            phone_number=context.user_data.get('phone_number'),
            years_of_experience=context.user_data.get('years_of_experience'),
            email=context.user_data.get('email'),
            resume_json=extract_pdf_text(str(resume_path))
        )

        # Save to database
        db = create_a_database(self.config.mongo_uri)
        db.insert_one(user_data.model_dump())
        
        await update.message.reply_text('Thank you! Your resume has been received.')
        return ConversationHandler.END

    async def broadcast_message(self, chat_id: int, start_index: int):
        """Send job recommendations to user."""
        if start_index == 0:
            search_engine = JobSearchEngine(vector_store_path=str(self.config.vector_store_path))
            search_engine.query(chat_id)

        job_db = create_a_job_database_specific_user(self.config.mongo_uri)
        document = job_db.find_one({'chat_id': chat_id})
        
        if not document or 'job_recommendation' not in document:
            await self.bot.send_message(chat_id, text="No job recommendations found.")
            return

        jobs = document['job_recommendation']
        total_jobs = len(jobs)
        
        for i in range(start_index, min(start_index + JOBS_PER_PAGE, total_jobs)):
            job = jobs[i]['metadata']
            await self._send_job_message(chat_id, job)

        if start_index + JOBS_PER_PAGE < total_jobs:
            keyboard = [[InlineKeyboardButton("Send More Jobs", callback_data=f"more_jobs:{start_index + JOBS_PER_PAGE}")]]
            await self.bot.send_message(
                chat_id,
                text="Click below to load more jobs:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await self.bot.send_message(chat_id, text="You have reached the end of job recommendations.")

    async def _send_job_message(self, chat_id: int, job: Dict[str, Any]):
        """Helper method to send formatted job message."""
        keyboard = [[
            InlineKeyboardButton("Referral", callback_data=f"referral:{job['job_indx']}:{chat_id}"),
            InlineKeyboardButton("Cover Letter", callback_data=f"Cover_Letter:{job['job_indx']}:{chat_id}"),
            InlineKeyboardButton("Cold Emails", callback_data=f"Cold_Emails:{job['job_indx']}:{chat_id}")
        ]]

        message = (
            f"<b>{job['job_title']}</b>\n"
            f"Company: {job['company_name']}\n"
            f"Experience: {job['experience']}\n"
            f"link: <a href='{job['job_link']}'>Apply here</a>\n"
            f"Location: {job['location']}\n"
            f"Skills: {job['skills']}"
        )

        await self.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /update command."""
        chat_id = update.message.chat.id
        db = create_a_database(self.config.mongo_uri)
        
        if not db.find_one({"chat_id": chat_id}):
            await update.message.reply_text("You're not registered yet. Starting registration process...")
            return

        await self.broadcast_message(chat_id, 0)
        await update.message.reply_text('Job recommendations sent.')

    async def button_click(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button clicks on job listings."""
        query = update.callback_query
        
        try:
            # Get the user's chat_id from the update
            chat_id = update.effective_chat.id
            
            # Split the data and handle different formats
            parts = query.data.split(":")
            action = parts[0]
            
            # Answer the callback query first to prevent "Query is too old" error
            try:
                await query.answer()
            except:
                pass  # Ignore if query answer fails
            
            if action == "more_jobs":
                start_index = int(parts[1])
                await self.broadcast_message(chat_id, start_index)
            elif action in ["referral", "Cover_Letter", "Cold_Emails"]:
                job_id = parts[1]
                
                # Call the appropriate function based on action
                if action == "referral":
                    val = create_referral_mail(chat_id, job_id)
                elif action == "Cover_Letter":
                    val = create_cover_letter_mail(chat_id, job_id)
                else:  # Cold_Emails
                    val = create_cold_mail(chat_id, job_id)
                    
                # Send as a new message instead of replying to the callback
                try:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=val if val else "Sorry, couldn't generate the email at this time.",
                        parse_mode="HTML"
                    )
                except Exception as msg_error:
                    print(f"Error sending message: {msg_error}")
                    # Try sending without parse_mode if HTML parsing fails
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=val if val else "Sorry, couldn't generate the email at this time."
                    )
                    
            else:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"Unknown action: {action}"
                )
                
        except Exception as e:
            error_message = f"Error processing button click: {str(e)}"
            print(error_message)  # For logging
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=error_message
                )
            except:
                print(f"Failed to send error message to chat {chat_id}")

    async def more_jobs_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle 'Send More Jobs' button click."""
        query = update.callback_query
        await query.answer()
        
        action, start_index = query.data.split(':')
        if action == 'more_jobs':
            await self.broadcast_message(query.message.chat_id, int(start_index))

    def run(self):
        """Start the bot."""
        print("Bot is running...")
        self.application.run_polling()

def main():
    """Main entry point."""
    config = load_config()
    bot = TelegramBot(config)
    bot.run()

if __name__ == "__main__":
    main()