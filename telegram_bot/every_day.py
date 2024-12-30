from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, JobQueue
import json
from dotenv import load_dotenv
import os
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from telegram import Update
import json
import asyncio


# Sample job data
TOKEN = os.getenv('TOKEN')

jobs = [
    {
        "job_title": "Product Support Engineer",
        "company_name": "Razorpay",
        "experience": "Fresher",
        "salary": "Rs. 5 LPA - Rs. 8 LPA",
        "location": "Bangalore",
        "skills": ["Python", "MySQL"]
    },
    {
        "job_title": "Remote Fullstack Specialist",
        "company_name": "Turing",
        "experience": "Fresher",
        "salary": "Rs. 6 LPA - Rs. 10 LPA",
        "location": "Remote",
        "skills": ["Full Stack Development"]
    },
    {
        "job_title": "Frontend Developer",
        "company_name": "Adani AI Labs",
        "experience": "Fresher",
        "salary": "Rs. 4 LPA - Rs. 6.5 LPA",
        "location": "Kolkata",
        "skills": ["HTML", "CSS", "Javascript"]
    }
]

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /jobs to see job listings.")

# Send job messages with buttons
def send_job_message(context):
    chat_id = context.job.context
    for job in jobs:
        keyboard = [
            [
                InlineKeyboardButton("Risk", callback_data=json.dumps({"action": "risk", "job_title": job["job_title"]})),
                InlineKeyboardButton("Start", callback_data=json.dumps({"action": "start", "job_title": job["job_title"]})),
                InlineKeyboardButton("Mold", callback_data=json.dumps({"action": "mold", "job_title": job["job_title"]}))
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = (
            f"**{job['job_title']}**\n"
            f"Company: {job['company_name']}\n"
            f"Experience: {job['experience']}\n"
            f"Salary: {job['salary']}\n"
            f"Location: {job['location']}\n"
            f"Skills: {', '.join(job['skills'])}"
        )
        context.bot.send_message(chat_id="7748640302", text=message, reply_markup=reply_markup, parse_mode="Markdown")

# Button click handler
def button_click(update, context):
    query = update.callback_query
    query.answer()
    data = json.loads(query.data)
    action = data["action"]
    job_title = data["job_title"]
    
    # Mock API call
    response = f"API '{action}' called for job: {job_title}"
    query.edit_message_text(text=response)

# Schedule the job
def schedule_job(update, context):
    chat_id = update.message.chat_id
    context.job_queue.run_once(send_job_message, when=10, context=chat_id)
    update.message.reply_text("Job messages scheduled to be sent in 10 seconds.")

# Main function
async def main():
    # Initialize the application
    application = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler("schedule", schedule_job))
    application.add_handler(CallbackQueryHandler(button_click))

    # Start the bot
    print(asyncio.get_running_loop())

    await application.run_polling()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if str(e) == "This event loop is already running":
            loop = asyncio.get_event_loop()
            loop.create_task(main())
        else:
            raise
