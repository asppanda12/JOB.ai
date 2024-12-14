from dotenv import load_dotenv
import os
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from telegram import Update
import json
# Load environment variables from .env file
load_dotenv()

# Access the variables
TOKEN = os.getenv('TOKEN')
application = ApplicationBuilder().token(TOKEN).build()
FIRST, SECOND, THIRD, FOURTH, FIFTH = range(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Welcome! One stop solution for all your job needs. Please enter your full name:')
    return FIRST  # Move to the FIRST state

async def first_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_name = update.message.text
    context.user_data['full_name'] = full_name 
    await update.message.reply_text(
            f'Hi {full_name}. Hope you are having a great time here. Please enter your phone number:'
    )
    return SECOND  # Move to the SECOND state

async def second_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_no = update.message.text
    context.user_data['phone_number'] = phone_no  # Save phone number in context
    await update.message.reply_text(f'Thank you for your phone number. Please enter your email:')
    return THIRD  # Move to the THIRD state

async def third_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text
    context.user_data['email'] = email  # Save email in context
    await update.message.reply_text(f'Thank you for your email. Please enter your Year Of Experience, in format of years eg: 2-3:')
    return FOURTH  # Move to the FOURTH state

async def fourth_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    yoe = update.message.text
    context.user_data['years_of_experience'] = yoe  # Save YOE in context
    await update.message.reply_text(f'Thank you! Your YOE has been updated to {yoe}. Please provide us with your latest CV:')
    return FIFTH  # Move to the FIFTH state

async def fifth_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        resume = update.message.document
        # Check if the document is a PDF
        if resume.mime_type == 'application/pdf':
            file = await resume.get_file()
            chat_id = update.message.chat.id  # Get the chat ID
            local_folder = 'JOB.ai/job_resume' 
            local_folder1 = 'JOB.ai/data_for_bot' 
            full_name = context.user_data.get('full_name')
            os.makedirs(local_folder, exist_ok=True)  # Create the directory if it doesn't exist
            file_path = os.path.join(local_folder, f'{full_name}_{chat_id}.pdf')  # Use chat ID as the filename
            await file.download_to_drive(file_path)  # Save the resume in the specified local folder
            await update.message.reply_text('Thank you! Your resume has been received.')
            map={}
            map['chat_id']=chat_id
            map['full_name']=context.user_data.get('full_name')
            map['phone_number']=context.user_data.get('phone_number')
            map['email']=context.user_data.get('email')
            map['years_of_experience']=context.user_data.get('years_of_experience')
            map['resume_path']=file_path
            os.makedirs(local_folder1, exist_ok=True)
            file_path1 = os.path.join(local_folder1, f'{full_name}_{chat_id}_info.json')
            json.dump(map, open(file_path1, 'w'))
        else:
            await update.message.reply_text('Please send a valid PDF document.')
    else:
        await update.message.reply_text('Please send a valid PDF document.')


# Add the conversation handler to your application
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        FIRST: [MessageHandler(filters.TEXT, first_response)],
        SECOND: [MessageHandler(filters.TEXT, second_response)],
        THIRD: [MessageHandler(filters.TEXT, third_response)],
        FOURTH: [MessageHandler(filters.TEXT, fourth_response)],
        FIFTH: [MessageHandler(filters.Document.ALL, fifth_response)],
    },
    fallbacks=[CommandHandler('cancel', ConversationHandler.END)],
)

# Add the button handler to your application
application.add_handler(conv_handler)
# application.add_handler(CallbackQueryHandler(button_handler))

# Run the bot
print("Bot is running...")
application.run_polling()