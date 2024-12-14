from dotenv import load_dotenv
import os
from telegram.ext import ApplicationBuilder,CommandHandler,MessageHandler,filters,ContextTypes,ConversationHandler,CallbackQueryHandler
from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # Ensure these imports are present

# Load environment variables from .env file
load_dotenv()

# Access the variables
TOKEN = os.getenv('TOKEN')
application = ApplicationBuilder().token(TOKEN).build()
FIRST, SECOND ,THIRD ,FOURTH , FIFTH = range(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Welcome! One stop solution for all your job needs<b> Please enter your full name</b>')
    return FIRST  # Move to the FIRST state

async def first_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    if 'correcting_name' in context.user_data and context.user_data['correcting_name']:
        context.user_data['correcting_name'] = False  # Reset correction flag
        full_name = update.message.text
        await update.message.reply_text(
            f'Thank you! Your name has been updated to {full_name}.\nPlease enter your phone number:',
        )
        return SECOND  # Proceed to the SECOND state
    else:
        # Save full name in context
        full_name = update.message.text
        context.user_data['full_name'] = full_name 
        await update.message.reply_text(
            f'Hi {full_name}. Hope you are having a great time here.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Please enter your phone number", callback_data='go_to_phone')],
                [InlineKeyboardButton("Filled the Name wrong. No worries. Please correct it", callback_data='go_to_name')],
            ])
        )
        return SECOND  # Move to the SECOND state




async def second_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data['correcting_name']==True:
        await update.message.reply_text(text='Please re-enter your full name:')
        return FIRST
    elif context.user_data['correcting_phone']==True:
        phone_no = update.message.text
        context.user_data['phone_number'] = phone_no
        context.user_data['correcting_phone'] = False  # Reset correction flag
        await update.message.reply_text(
            f'Thank you! Your phone number has been updated to {phone_no}.\nPlease enter your email:',
        )
        return THIRD  # Proceed to the THIRD state
    else:
            phone_no = update.message.text
            context.user_data['phone_number'] = phone_no  # Save phone number in context
            await update.message.reply_text(f'Thank you for your phone number.',
                                            reply_markup=InlineKeyboardMarkup([
                                                [InlineKeyboardButton("Filled the phone_no wrong. No worries. Please correct it", callback_data='go_to_phone')],
                                                [InlineKeyboardButton("Please enter your email", callback_data='go_to_email')],
                                            ]))
            return THIRD  # Move to the THIRD state

async def third_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data['correcting_phone']==True:
        await update.message.reply_text(text='Please re-enter your Phone Number:')
        return SECOND
    elif context.user_data['correcting_email']==True:
        email = update.message.text
        context.user_data['email'] = email
        context.user_data['correcting_email'] = False  # Reset correction flag
        await update.message.reply_text(
            f'Thank you! Your Email has been updated to {email}.\nPlease enter your yoe:',
        )
        return FOURTH
    else:
        email = update.message.text
        context.user_data['email'] = email  # Save email in context
        await update.message.reply_text(f'Thank you for your email.',
                                     reply_markup=InlineKeyboardMarkup([
                                         [InlineKeyboardButton("Filled the email wrong. No worries. Please correct it", callback_data='go_to_email')],
                                         [InlineKeyboardButton("Please enter your Year Of Experience, In format of years eg: 2-3", callback_data='go_to_yoe')],
                                     ]))
    return FOURTH  # Move to the FOURTH state

async def fourth_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data['correcting_email']==True:
        await update.message.reply_text(text='Please re-enter your email:')
        return THIRD
    elif context.user_data['correcting_yoe']==True:
        yoe = update.message.text
        context.user_data['years_of_experience'] = yoe
        context.user_data['correcting_email'] = False  # Reset correction flag
        await update.message.reply_text(
            f'Thank you! Your yoe has been updated to {yoe}.\nPlease provide us with your latest CV:',
        )
        return FIFTH
    else:
        yoe = update.message.text
        context.user_data['years_of_experience'] = yoe  # Save YOE in context
        await update.message.reply_text(f'Thank you for your YOE.',
                                     reply_markup=InlineKeyboardMarkup([
                                         [InlineKeyboardButton("Filled the Year Of Experience wrong. Please correct it", callback_data='go_to_yoe')],
                                         [InlineKeyboardButton("Please provide us with your latest CV so that we can proceed.", callback_data='go_to_resume')],
                                     ]))
        return FIFTH  # Move to the FIFTH state

async def fifth_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        resume = update.message.document
        # Check if the document is a PDF
        if resume.mime_type == 'application/pdf':
            file = await resume.get_file()
            chat_id = update.message.chat.id  # Get the chat ID
            local_folder = 'JOB.ai/job_resume' 
            full_name = context.user_data.get('full_name')
            os.makedirs(local_folder, exist_ok=True)  # Create the directory if it doesn't exist
            file_path = os.path.join(local_folder, f'{full_name}_{chat_id}.pdf')  # Use chat ID as the filename
            await file.download_to_drive(file_path)  # Save the resume in the specified local folder
            await update.message.reply_text('Thank you! Your resume has been received.')
        else:
            await update.message.reply_text('Please send a valid PDF document.')
    else:
        await update.message.reply_text('Please send a valid PDF document.')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['correcting_name']=False  
    context.user_data['correcting_phone']=False
    context.user_data['correcting_email']=False
    context.user_data['correcting_yoe']=False
    context.user_data['correcting_resume']=False
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    if query.data == 'go_to_name':
        context.user_data['correcting_name'] = True  # Set correction flag
        await query.edit_message_text(text='Please re-enter your full name:')
        return FIRST  # Redirect to FIRST state to re-enter the name


    elif query.data == 'go_to_phone':
        context.user_data['correcting_phone'] = True 
        await query.edit_message_text(text='Please enter your phone number:')
        return SECOND  # This should work if the conversation handler is set up correctly

    elif query.data == 'go_to_email':
        context.user_data['correcting_email'] = True 
        await query.edit_message_text(text='Please enter your email:')
        return THIRD  # This should work if the conversation handler is set up correctly

    elif query.data == 'go_to_yoe':
        context.user_data['correcting_yoe'] = True 
        await query.edit_message_text(text='Please enter your year of experience in format of years eg: 2-3')
        return FOURTH  # This should work if the conversation handler is set up correctly

    elif query.data == 'go_to_resume':
        context.user_data['correcting_resume'] = True 
        await query.edit_message_text(text='Please provide us with your latest CV so that we can proceed.')
        return FIFTH  # This should work if the conversation handler is set up correctly

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
application.add_handler(CallbackQueryHandler(button_handler))

# Run the bot
print("Bot is running...")
application.run_polling()


