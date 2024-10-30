from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Retrieve the variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Debug: Check if the variables are loaded correctly
print(f"Bot Token: {BOT_TOKEN}")
print(f"Mongo URI: {MONGO_URI}")
# Core Python imports
import asyncio  # For asynchronous operations and event loops
import logging  # For logging messages and debugging
from datetime import datetime, timedelta  # For handling dates and time calculations
import os  # For interacting with the environment and loading environment variables
import calendar  # For working with calendar dates

# Aiogram core imports and filter handlers
from aiogram import Bot, Dispatcher, types, F  # Core aiogram imports
from aiogram.filters import Command  # Command filter for registering commands
from aiogram.client.session.aiohttp import AiohttpSession  # HTTP session management
from aiogram.client.bot import DefaultBotProperties  # Set default bot properties

# Telegram bot-related types and Command setup
from aiogram.types import (
    InlineKeyboardMarkup,  # For inline keyboards
    InlineKeyboardButton,  # For individual buttons
    BotCommand,  # For setting bot commands
    CallbackQuery,  # Handling callback queries from inline buttons
    PollAnswer  # Handling poll answers (if your quiz uses Telegram polls)
)

# MongoDB async driver
from motor.motor_asyncio import AsyncIOMotorClient  # Asynchronous MongoDB driver

# Load environment variables from .env files
from dotenv import load_dotenv
import re
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage  # In-memory FSM storage
import random
from datetime import datetime, timedelta
import uuid  # For generating unique session IDs



# Ensure environment variables are loaded correctly
load_dotenv()

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Load environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Initialize bot with default properties
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode='HTML')  # Use HTML parsing by default
)

# Use in-memory FSM storage instead of Redis
memory_storage = MemoryStorage()  # In-memory FSM storage
dp = Dispatcher(storage=memory_storage)  # Initialize Dispatcher with in-memory storage

# Initialize MongoDB client
client = AsyncIOMotorClient(MONGO_URI, maxPoolSize=100)  # Handle 100 concurrent connections
db = client["govtprepbuddy_database"]
users_collection = db["users"]
polls_collection = db["polls"]

# Configuration constants
ADMIN_ID = 201319134  # Replace with your admin chat ID
QUIZ_TIMEOUT = 300  # 5 minutes timeout for quiz sessions
poll_tracking = {}  # Track poll_id to correct_option_id mapping

### Function Definitions Start Here ###

async def set_bot_commands():
    """Set commands for the bot's menu."""
    commands = [
        BotCommand(command="start", description="🔥 Start the Quiz"),
        BotCommand(command="track_plan", description="📋 Track Plan Details"),
        BotCommand(command="pay", description="✅ Pay for Unlimited Access"),
        BotCommand(command="result", description="📊 View Your Last Quiz Result"),
        BotCommand(command="leaderboard", description="🏆 View the Leaderboard"),
    ]
    await bot.set_my_commands(commands)

def is_admin(user_id: int) -> bool:
    """Check if the user is an admin."""
    return user_id == ADMIN_ID

def create_keyboard(button_texts, row_width=2):
    """Create inline keyboard with specified number of buttons per row."""
    buttons = [InlineKeyboardButton(text=btn, callback_data=btn) for btn in button_texts]

    if not buttons:
        raise ValueError("No buttons provided for the keyboard")  # Safety check

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            buttons[i:i + row_width] for i in range(0, len(buttons), row_width)
        ]
    )
    return keyboard

class QuizStates(StatesGroup):
    selecting_year = State()
    selecting_month = State()
    selecting_day = State()
    selecting_category = State()
    waiting_for_question_count = State()
    answering_quiz = State()

@dp.message(Command("start"))
async def start(message: types.Message):
    """Handler for the /start command."""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    # Check if the user is a member of the required channel
    is_member = await check_channel_membership(user_id)
    if not is_member:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Join @CurrentAdda", url="https://t.me/CurrentAdda")],
                [InlineKeyboardButton(text="I've joined, check now", callback_data="check_membership")]
            ]
        )
        await message.answer(
            "⚠️ You must join our channel to use this bot. Please join and click 'I've joined' to proceed.",
            reply_markup=keyboard
        )
        return  # Stop further execution if not a member

    today = datetime.now().date()
    user = await users_collection.find_one({"user_id": user_id})

    if not user or user.get("last_active_date") != str(today):
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_active_date": str(today), "correct_answers_today": []}},
            upsert=True
        )

    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"username": username}},
        upsert=True
    )

    await message.answer(f"Welcome, {username}! Let's get started.")
    await show_main_menu(message)

@dp.callback_query(lambda call: call.data == "check_membership")
async def handle_join_check(call: types.CallbackQuery):
    """Handle the join confirmation from the user."""
    user_id = call.from_user.id

    if await check_channel_membership(user_id):
        await call.answer("✅ Membership confirmed!", show_alert=True)
        await show_main_menu(call.message)
    else:
        await call.answer("❌ You haven't joined yet. Please join and try again.", show_alert=True)

async def show_main_menu(message: types.Message):
    """Display the main menu with DateWise and CategoryWise options."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="DateWise", callback_data="DateWise")],
            [InlineKeyboardButton(text="CategoryWise", callback_data="CategoryWise")],
            [InlineKeyboardButton(text="Track Plan Details", callback_data="track_plan")],
            [InlineKeyboardButton(text="Pay for Unlimited Access", callback_data="pay_for_access")]
        ]
    )
    await message.answer("Choose an option:", reply_markup=keyboard)




    

async def show_years(message: types.Message):
    """Display available years for DateWise quiz."""
    keyboard = create_keyboard(["2024", "2025"], row_width=2)
    await message.answer("Select a year:", reply_markup=keyboard)


@dp.callback_query(lambda call: call.data in ["2024", "2025"])
async def show_months(call: types.CallbackQuery, state: FSMContext):
    """Display months for the selected year."""
    await state.update_data(selected_year=int(call.data))  # Store in FSM context

    months = [calendar.month_abbr[i] for i in range(1, 13)]
    keyboard = create_keyboard(months, row_width=4)
    await call.message.answer(f"Select a month in {call.data}:", reply_markup=keyboard)
    await state.set_state(QuizStates.selecting_month)


@dp.callback_query(lambda call: call.data in [calendar.month_abbr[i] for i in range(1, 13)])
async def show_days(call: types.CallbackQuery, state: FSMContext):
    """Display days for the selected month."""
    month_index = list(calendar.month_abbr).index(call.data)
    await state.update_data(selected_month=month_index)  # Store in FSM context

    days = [str(i) for i in range(1, 32)]
    keyboard = create_keyboard(days, row_width=7)
    await call.message.answer(f"Select a day in {call.data}:", reply_markup=keyboard)
    await state.set_state(QuizStates.selecting_day)


@dp.callback_query(lambda call: call.data.isdigit() and 1 <= int(call.data) <= 31)
async def set_selected_day(call: types.CallbackQuery, state: FSMContext):
    """Store the selected day and move to language selection."""
    await state.update_data(selected_day=int(call.data))  # Store in FSM context
    await show_languages(call.message)  # Proceed to show language options


def get_categories():
    """Return a list of quiz categories."""
    return [
        "Agriculture", "Awards and Honours", "Bills and Acts", "Defence", "Education",
        "Art and Culture", "Banking", "Business", "Economy", "Environment", "Festivity",
        "Important Days", "National", "Persons", "Politics", "Finance", "International",
        "Obituary", "Places", "Science", "Sports", "State", "Talkies", "Technology", "Miscellaneous"
    ]

async def show_categories(message: types.Message):
    """Display available quiz categories."""
    categories = get_categories()
    keyboard = create_keyboard(categories)
    await message.answer("Select a category:", reply_markup=keyboard)

@dp.callback_query(lambda call: call.data in get_categories())
async def set_selected_category(call: types.CallbackQuery, state: FSMContext):
    """Store the selected category in the state."""
    category = normalize_category(call.data)  # Normalize the category
    await state.update_data(selected_category=category)  # Store normalized category
    await show_languages(call.message)  # Proceed to the next step

async def show_languages(message: types.Message):
    """Show language options for the quiz."""
    languages = ["English", "Hindi", "Gujarati"]
    keyboard = create_keyboard(languages, row_width=3)  # All buttons in one row
    await message.answer("Select a language for the quiz:", reply_markup=keyboard)


@dp.callback_query(lambda call: call.data in ["English", "Hindi", "Gujarati"])
async def ask_question_count(call: types.CallbackQuery, state: FSMContext):
    """Ask the user how many questions they want."""
    language_code = {"English": "en", "Hindi": "hi", "Gujarati": "gu"}[call.data]

    # Store the selected language in the state
    await state.update_data(language=language_code)

    await call.message.answer(
        "How many questions do you want? (Maximum 15 per session and 30 per day)"
    )

    # Set the next state to waiting for the question count
    await state.set_state(QuizStates.waiting_for_question_count)

@dp.message(QuizStates.waiting_for_question_count)
async def process_question_count(message: types.Message, state: FSMContext):
    """Process the number of questions requested by the user."""
    user_id = message.from_user.id

    # Retrieve FSM data and user details from the database
    data = await state.get_data()
    language = data.get("language")

    # Check if the user has unlimited access and validate the daily limit
    has_unlimited_access = await has_valid_unlimited_access(user_id)
    daily_questions = await get_user_daily_questions(user_id)

    # Parse the requested number of questions
    try:
        count = int(message.text)
        if not (1 <= count <= 15):
            raise ValueError
    except ValueError:
        await message.reply("❌ Please enter a valid number between 1 and 15.")
        return

    # If the user has unlimited access, check the hourly limit.
    if has_unlimited_access:
        can_request, wait_message = await can_request_more_questions(user_id)
        if not can_request:
            await message.reply(wait_message)
            return
        # Update the hourly question count.
        await update_hourly_request_count(user_id, count)

    # Ensure the user does not exceed the daily limit (only for non-unlimited users).
    if not has_unlimited_access and daily_questions + count > 30:
        remaining = max(0, 30 - daily_questions)
        if remaining > 0:
            await message.reply(f"⚠️ You can only request {remaining} more questions today.")
        else:
            await message.answer(
                "🚫 You've reached the daily limit of 30 questions.\n"
                "🔓 *Unlock Unlimited Access* for just ₹49 For 1 Month to continue playing without limits!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="💳 Buy Unlimited Access", callback_data="pay_for_access"
                        )
                    ]]
                )
            )
        return

    # Fetch questions based on the user's selection
    questions = await fetch_questions_by_category_or_date(state)
    if not questions:
        await message.reply("❌ No questions found for your selection.")
        await show_main_menu(message)
        await state.clear()
        return

    # Send the quiz to the user and update the daily question count for non-unlimited users.
    selected_questions = random.sample(questions, min(count, len(questions)))
    await send_quiz(message, selected_questions, count, language)

    # Increment the daily question count only for non-unlimited users.
    if not has_unlimited_access:
        await update_user_daily_questions(user_id, count)
        await message.reply(
            f"✅ {count} questions sent! {30 - daily_questions - count} questions remaining today."
        )

    # Clear the state after sending the quiz.
    await state.clear()



async def fetch_questions_by_category_or_date(state: FSMContext):
    """Fetch questions based on the user's selection."""
    data = await state.get_data()  # Retrieve user session data

    if "selected_category" in data:
        category = data["selected_category"]
        return await fetch_questions_by_category(category)  # Use the improved function

    if {"selected_year", "selected_month", "selected_day"} <= data.keys():
        return await fetch_questions_by_date(
            data["selected_year"], data["selected_month"], data["selected_day"]
        )

    return []  # Return empty list if no valid selection





@dp.callback_query(lambda call: call.data in ["DateWise", "CategoryWise"])
async def handle_quiz_selection(call: types.CallbackQuery):
    """Handle the selection between DateWise and CategoryWise."""
    global selected_category, selected_year, selected_month, selected_day

    selected_category = None
    selected_year = None
    selected_month = None
    selected_day = None

    if call.data == "DateWise":
        await show_years(call.message)
    elif call.data == "CategoryWise":
        await show_categories(call.message)


@dp.callback_query(F.data == "Track Plan Details")
async def handle_track_plan(call: types.CallbackQuery):
    """Handler for tracking plan details."""
    user = await users_collection.find_one({"user_id": call.from_user.id})

    if user and user.get("unlimited_access"):
        expiry_date = user.get("unlimited_access_expiry")
        await call.message.answer(
            f"📅 Your unlimited access is valid until {expiry_date.strftime('%d %B %Y')}."
        )
    else:
        await call.message.answer("You don't have an active unlimited access plan.")

@dp.callback_query(F.data == "pay_for_access")
async def handle_pay_for_access(call: types.CallbackQuery):
    """Handler to send the payment QR code with detailed instructions."""
    await call.message.answer_photo(
        photo="https://i.ibb.co/9pLgchY/photo-2024-10-21-09-43-32.jpg",
        caption=(
            "💳 *Unlock Unlimited Access*\n\n"
            "🔥 **Pay ₹49** to enjoy unlimited quiz access for *30 days!* 🔓\n\n"
            "📲 **Payment Methods**:\n"
            "1️⃣ *Google Pay*: `8000212153`\n"
            "2️⃣ *Scan the QR Code* above ⬆️\n\n"
            "📥 *After Payment*: Send a screenshot to [@Ajay_ambaliya](https://t.me/Ajay_ambaliya) for verification.\n\n"
            "🎁 _Your unlimited access will be activated within minutes._\n\n"
            "⚠️ *Note*: If you encounter any issues, feel free to contact us via the above link."
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📧 Contact Support", url="https://t.me/Ajay_ambaliya"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 I've Paid, Verify Now", callback_data="verify_payment"
                    )
                ],
            ]
        ),
    )



@dp.message(Command("broadcast"))
async def broadcast_message(message: types.Message):
    """Broadcast a message to all users."""
    if not is_admin(message.from_user.id):
        await message.reply("This command is restricted to admins.")
        return

    users = await users_collection.find({}, {"user_id": 1}).to_list(length=None)

    async def send_message(user):
        try:
            await bot.send_message(user["user_id"], message.text)
        except Exception as e:
            logging.error(f"Failed to send message to {user['user_id']}: {e}")

    await asyncio.gather(*(send_message(user) for user in users))
    await message.answer("Broadcast completed!")




@dp.message(Command("result"))
async def show_result(message: types.Message):
    """Display the user's last quiz result."""
    user_id = message.from_user.id
    user = await users_collection.find_one({"user_id": user_id})

    if not user or "last_result" not in user:
        await message.answer("No results found for your account.")
        return

    last_result = user["last_result"]
    await message.answer(
        f"📊 Your Last Quiz Result:\n"
        f"Correct Answers: {last_result['correct_answers']}\n"
        f"Total Questions: {last_result['total_questions']}\n"
        f"Score: {last_result['score']} points"
    )

@dp.callback_query(F.data == "I've joined, check now")
async def handle_join_check(call: types.CallbackQuery):
    """Handle the join confirmation from the user."""
    user_id = call.from_user.id

    if await check_channel_membership(user_id):
        await call.answer("✅ Membership confirmed!")
        await show_main_menu(call.message)
    else:
        await call.answer("❌ You haven't joined yet. Please join and try again.")

async def check_channel_membership(user_id: int) -> bool:
    """Check if the user is a member of the required channel."""
    try:
        # Ensure the bot can check this channel's members
        member = await bot.get_chat_member("@CurrentAdda", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except aiogram.exceptions.ChatNotFound:
        logging.error("Channel not found or bot is not an admin.")
        return False  # Bot is not able to access the channel's data
    except aiogram.exceptions.BotKicked:
        logging.error("Bot has been kicked from the channel.")
        return False
    except Exception as e:
        logging.error(f"Error checking membership: {e}")
        return False





@dp.poll_answer()
async def handle_poll_answer(poll_answer: PollAnswer):
    """Handle poll answers."""
    user_id = poll_answer.user.id
    poll_id = poll_answer.poll_id
    selected_option = poll_answer.option_ids[0]  # User’s selected option

    # Retrieve the correct option for this poll
    correct_option_id = poll_tracking.get(poll_id)

    # Fetch user session from the database
    session = await db["user_sessions"].find_one({"user_id": user_id})

    if not session:
        await bot.send_message(user_id, "❌ No active session found.")
        return

    answered = session.get("answered", 0)
    sent = session.get("sent", 0)

    # Award points if the answer is correct
    if correct_option_id is not None and selected_option == correct_option_id:
        await db["user_sessions"].update_one(
            {"user_id": user_id}, {"$addToSet": {"correct_questions": poll_id}}
        )

    # Increment the answered count
    await db["user_sessions"].update_one(
        {"user_id": user_id}, {"$inc": {"answered": 1}}
    )

    # If all questions are answered, show the result
    if answered + 1 >= sent:
        await store_and_show_result(user_id, poll_answer.user.id)  # Corrected function call


async def store_and_show_result(user_id, chat_id):
    """Store the quiz result and display it to the user."""
    session = await db["user_sessions"].find_one({"user_id": user_id})

    if not session:
        await bot.send_message(chat_id, "❌ No session found.")
        return

    question_ids = session.get("question_ids", [])
    correct_answers_today = session.get("correct_questions", [])
    total_answered = session.get("answered", 0)
    sent = session.get("sent", 0)
    score = len(correct_answers_today)

    selected_language = session.get("selected_language", "en")
    explanations = []

    for question_id in question_ids:
        question = await polls_collection.find_one({"_id": question_id})
        if question:
            lang_data = question['languages'].get(selected_language, {})
            explanation = (
                f"Q: {lang_data.get('question', 'N/A')}\n"
                f"Explanation: {lang_data.get('explanation', 'No explanation available.')}"
            )
            explanations.append(explanation)

    explanation_text = "\n\n".join(explanations)
    result_message = (
        f"📊 Quiz Summary:\n"
        f"Total Questions Answered: {total_answered}\n"
        f"Score: {score}/{sent}\n\n"
        f"📄 Explanations:\n{explanation_text}"
    )

    chunks = chunk_text(result_message, 4096)

    for chunk in chunks:
        await bot.send_message(chat_id, chunk)

    result = {
        "user_id": user_id,
        "score": score,
        "total_questions": sent,
        "correct_answers": score,
        "date": datetime.now()
    }
    await db["results"].insert_one(result)

    await users_collection.update_one(
        {"user_id": user_id},
        {
            "$inc": {"daily_score": score, "monthly_score": score, "total_score": score},
            "$set": {"last_result": result}
        },
        upsert=True
    )

    await db["user_sessions"].delete_one({"user_id": user_id})


def chunk_text(text, max_length=4096):
    """Split long text into chunks within Telegram's message limit."""
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_index = text.rfind('\n', 0, max_length)
        if split_index == -1:
            split_index = max_length
        chunks.append(text[:split_index])
        text = text[split_index:].strip()
    return chunks

async def check_quiz_timeout(user_id, session_id, chat_id, timeout_duration):
    """Check if the quiz has timed out and display the result if necessary."""
    try:
        # Wait for the dynamically calculated timeout duration
        await asyncio.sleep(timeout_duration)

        # Re-fetch the session to ensure it's still valid
        session = await db["user_sessions"].find_one({"user_id": user_id, "session_id": session_id})

        # If the session is still active and not all questions are answered
        if session and session.get("answered", 0) < session.get("sent", 0):
            await bot.send_message(chat_id, "⏳ Time's up! Here's your quiz summary:")
            await store_and_show_result(user_id, chat_id)

    except Exception as e:
        logging.error(f"Error in check_quiz_timeout: {e}")


@dp.message(Command("track_plan"))
async def handle_track_plan_command(message: types.Message):
    """Handle /track_plan command to display the user's plan details and free questions left."""
    user_id = message.from_user.id
    user = await users_collection.find_one({"user_id": user_id})

    # Check if the user has unlimited access
    if user and user.get("unlimited_access"):
        expiry_date = user.get("unlimited_access_expiry")
        await message.answer(
            f"🎉 *You are an Unlimited User!* \n"
            f"🗓 *Your Access Valid Until* : {expiry_date.strftime('%d %B %Y')}.\n"
            "Enjoy unlimited quizzes without restrictions! 🚀"
        )
        return  # Stop further execution for unlimited users

    # Fetch free questions left today
    daily_questions = await get_user_daily_questions(user_id)
    questions_left = max(0, 30 - daily_questions)  # Ensure non-negative

    # Prepare message for free users
    free_user_message = (
        f"📋 *You are a Free User.*\n"
        f"🎯 *Daily Limit*: 30 questions per day.\n"
        f"📊 *Questions Left Today*: {questions_left}.\n\n"
        "🔓 Unlock unlimited access to continue playing without limits!"
    )

    # Reply with the message and show a button to pay for unlimited access
    await message.answer(
        free_user_message,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💳 Pay for Unlimited Access", callback_data="pay_for_access"
                    )
                ]
            ]
        )
    )




@dp.message(Command("pay"))
async def handle_pay_command(message: types.Message):
    """Handle /pay command to display payment instructions."""
    user_id = message.from_user.id
    user = await users_collection.find_one({"user_id": user_id})

    # Check if the user already has unlimited access
    if user and user.get("unlimited_access"):
        expiry_date = user.get("unlimited_access_expiry")
        if expiry_date and datetime.now() <= expiry_date:
            await message.answer(
                f"🎉 *You already have unlimited access!* 🎉\n"
                f"🗓 *Valid Until*: {expiry_date.strftime('%d %B %Y')}.\n"
                "No need to pay now!"
            )
            return
        elif not expiry_date:
            await message.answer("🎉 *You have lifetime unlimited access!* No need to pay now!")
            return

    # If no active access, send payment instructions
    await message.answer_photo(
        photo="https://i.ibb.co/9pLgchY/photo-2024-10-21-09-43-32.jpg",
        caption=(
            "💳 *Unlock Unlimited Access Now!* 🔥\n\n"
            "📥 **Pay ₹49** to get *30 days of unlimited quiz access*!\n\n"
            "📲 **Payment Methods**:\n"
            "1️⃣ *Google Pay*: `8000212153`\n"
            "2️⃣ *Scan the QR Code* above ⬆️\n\n"
            "✅ *After Payment*: Send a screenshot to [@Ajay_ambaliya](https://t.me/Ajay_ambaliya) for verification.\n"
            "🎁 _Your access will be activated within minutes._\n\n"
            "⚠️ *Note*: If you encounter any issues, feel free to reach out using the button below."
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📧 Contact Support", url="https://t.me/Ajay_ambaliya"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 I've Paid, Verify Now", callback_data="verify_payment"
                    )
                ]
            ]
        )
    )

@dp.callback_query(lambda call: call.data == "verify_payment")
async def handle_verify_payment(call: types.CallbackQuery):
    """Handler to confirm payment verification process."""
    await call.answer("🕵️ Verification request received! Please wait while we verify your payment.", show_alert=True)

    # Notify admin (you can customize this as per your use case)
    admin_chat_id = 201319134  # Replace with your admin chat ID
    user_id = call.from_user.id
    username = call.from_user.username or call.from_user.first_name

    try:
        await bot.send_message(
            admin_chat_id,
            f"📩 *Payment Verification Request* \n\n"
            f"🧑‍💻 *User* : {username} (ID: {user_id})\n"
            f"✅ *Request* : User has paid and requests verification."
        )
        await call.message.answer("📨 Your request has been sent to the admin. You will receive confirmation shortly.")
    except Exception as e:
        logging.error(f"Failed to send verification request to admin: {e}")
        await call.message.answer("⚠️ Could not send your request. Please try again later.")

async def grant_access(user_id: int, duration_days: int = 30):
    """Grant unlimited access to a user."""
    expiry_date = datetime.now() + timedelta(days=duration_days)

    # Update the user’s access details in the database
    await users_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "unlimited_access": True,
                "unlimited_access_expiry": expiry_date,
                "daily_questions": float('inf')  # Set to unlimited
            }
        },
        upsert=True
    )

    # Try to send a notification message to the user
    try:
        await bot.send_message(
            user_id,
            f"🎉 Congratulations! You now have unlimited access until {expiry_date.strftime('%d %B %Y')}."
        )
    except Exception as e:
        # Handle the case where the message couldn't be sent
        logging.error(f"Failed to notify user {user_id}: {e}")

@dp.message(Command("grant_access"))
async def handle_grant_access(message: types.Message):
    """Admin command to grant unlimited access."""
    if not is_admin(message.from_user.id):
        await message.reply("This command is restricted to admins.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: /grant_access <username_or_user_id>")
        return

    target = args[1]
    if target.isdigit():
        user_id = int(target)
    else:
        user = await users_collection.find_one({"username": target})
        if not user:
            await message.reply("User not found.")
            return
        user_id = user["user_id"]

    # Grant access to the target user
    await grant_access(user_id)

    await message.reply(f"✅ Unlimited access granted to {target}.")


@dp.message(Command("revoke_access"))
async def handle_revoke_access(message: types.Message):
    """Admin command to revoke a user's unlimited access."""
    if not is_admin(message.from_user.id):
        await message.reply("This command is restricted to admins.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: /revoke_access <user_id>")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.reply("Invalid user ID. Please provide a valid number.")
        return

    await users_collection.update_one(
        {"user_id": user_id},
        {
            "$unset": {"unlimited_access": "", "unlimited_access_expiry": ""},
            "$set": {"daily_questions": 30}  # Limit to 30 questions daily
        }
    )

    await message.reply(f"✅ Unlimited access revoked for user {user_id}.")

async def can_request_more_questions(user_id: int) -> tuple[bool, str | None]:
    """Check if the user with unlimited access can request more questions."""
    user = await users_collection.find_one({"user_id": user_id})

    if not user or not user.get("unlimited_access"):
        # This function only applies to unlimited users, other users are handled separately.
        return False, None

    now = datetime.now()
    session = user.get("hourly_request_session", {})

    # Retrieve session data or set defaults.
    first_request_time = session.get("first_request_time", now)
    question_count = session.get("question_count", 0)

    # If it's been more than an hour, reset the session.
    if now - first_request_time >= timedelta(hours=1):
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"hourly_request_session": {
                "first_request_time": now,
                "question_count": 0
            }}}
        )
        return True, None  # User can request more questions

    # If the user has requested 60 questions within the hour, deny further requests.
    if question_count >= 60:
        next_available_time = first_request_time + timedelta(hours=1)
        wait_time = next_available_time - now
        return False, f"⏳ You've reached your limit of 60 questions this hour. Please try again in {wait_time}."

    # User can still request more questions within the hour.
    return True, None

async def update_hourly_request_count(user_id: int, additional_count: int):
    """Update the user's hourly request count."""
    user = await users_collection.find_one({"user_id": user_id})
    session = user.get("hourly_request_session", {})

    # Update the question count in the session.
    new_count = session.get("question_count", 0) + additional_count

    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"hourly_request_session.question_count": new_count}}
    )


@dp.message(Command("leaderboard"))
async def leaderboard(message: types.Message):
    """Display the daily top 10 leaderboard."""
    try:
        # Fetch the top 10 users based on daily scores
        daily_leaderboard = await users_collection.find().sort("daily_score", -1).limit(10).to_list(length=None)

        # Build the leaderboard message
        leaderboard_message = "🏆 *Daily Top 10 Performers* 🏆\n\n"
        leaderboard_message += format_leaderboard_entries(daily_leaderboard, "daily_score")

        # Send the formatted leaderboard message
        await message.answer(leaderboard_message, parse_mode="MarkdownV2")

    except Exception as e:
        logging.error(f"Error generating leaderboard: {e}")
        await message.answer("❌ An error occurred while generating the leaderboard. Please try again later.")

def format_leaderboard_entries(users, score_field):
    """Format leaderboard entries into a readable string."""
    entries = ""
    for rank, user in enumerate(users, 1):
        username = escape_markdown(user.get("username", "Unknown"))
        score = user.get(score_field, 0)
        entries += f"{rank}\\. {username} \\- {score} points\n"
    return entries

def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram's MarkdownV2."""
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", text)




async def reset_daily_scores():
    """Reset daily scores at midnight."""
    await users_collection.update_many({}, {"$set": {"daily_score": 0}})
    logging.info("✅ Daily scores reset successfully.")





def normalize_category(category: str) -> str:
    """Normalize the category by converting to lowercase and replacing spaces with dashes."""
    return category.strip().lower().replace(" ", "-")

async def fetch_questions_by_category(category: str):
    """Fetch questions from the database by category."""
    normalized_category = normalize_category(category)  # Ensure proper normalization
    query = {"category": normalized_category}  # Query with normalized category
    questions = await polls_collection.find(query).to_list(length=None)
    return questions


async def fetch_questions_by_date(year, month, day):
    """Fetch questions from the database by a specific date."""
    query = {"year": int(year), "month": int(month), "day": int(day)}
    return await polls_collection.find(query).to_list(length=None)

async def get_user_daily_questions(user_id: int) -> int:
    """Ensure the daily questions are correctly tracked and reset if it's a new day."""
    today = datetime.now().date()

    # Use MongoDB's find_one_and_update to handle upserts efficiently
    user = await users_collection.find_one_and_update(
        {"user_id": user_id},
        {
            "$setOnInsert": {"last_request_date": str(today), "daily_questions": 0},  # Initialize on first insert
        },
        upsert=True,
        return_document=True  # Return the updated or inserted document
    )

    # If it's a new day, reset daily questions and last request date
    if user.get("last_request_date") != str(today):
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_request_date": str(today), "daily_questions": 0}}
        )
        return 0  # New day, so start with 0 daily questions

    # Return the current count of daily questions
    return user.get("daily_questions", 0)


async def update_user_daily_questions(user_id: int, additional_count: int):
    """Increment the user's daily question count correctly."""
    today = datetime.now().date()

    # Fetch the current user data
    user = await users_collection.find_one({"user_id": user_id})
    current_count = 0

    if user and user.get("last_request_date") == str(today):
        current_count = user.get("daily_questions", 0)

    # Calculate the new count, ensuring it stays non-negative
    new_count = max(0, current_count + additional_count)

    # Update the user's daily question count in the database
    await users_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "last_request_date": str(today),
                "daily_questions": new_count
            }
        },
        upsert=True  # Insert if the user does not exist
    )



async def has_valid_unlimited_access(user_id: int) -> bool:
    """Check if the user has valid unlimited access."""
    user = await users_collection.find_one({"user_id": user_id})

    if not user or not user.get("unlimited_access"):
        return False

    expiry_date = user.get("unlimited_access_expiry")
    if expiry_date and datetime.now() > expiry_date:
        # Revoke unlimited access if it expired
        await users_collection.update_one(
            {"user_id": user_id},
            {"$unset": {"unlimited_access": "", "unlimited_access_expiry": ""}}
        )
        return False

    return True



async def send_quiz(message, questions, requested_count, language):
    """Send quiz questions to the user."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    question_ids = [q['_id'] for q in questions]

    # Generate a unique session ID for this quiz session
    session_id = str(uuid.uuid4())

    # Calculate the dynamic timeout duration (30 seconds per question)
    timeout_duration = requested_count * 30  # e.g., 15 questions -> 450 seconds

    # Store the session in the database
    await db["user_sessions"].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "session_id": session_id,
                "question_ids": question_ids,
                "answered": 0,
                "sent": requested_count,
                "correct_questions": [],
                "selected_language": language
            }
        },
        upsert=True
    )

    # Function to send each poll question
    async def send_poll(question_id):
        question = await polls_collection.find_one({"_id": question_id})
        lang_data = question['languages'][language]
        correct_option_id = question['correct_answers'][language]

        try:
            poll = await bot.send_poll(
                chat_id=chat_id,
                question=lang_data['question'],
                options=lang_data['options'][:10],
                type='quiz',
                correct_option_id=correct_option_id,
                is_anonymous=False
            )
            poll_tracking[poll.poll.id] = correct_option_id
        except Exception as e:
            logging.error(f"Error sending poll: {e}")

    # Send all quiz questions concurrently
    await asyncio.gather(*(send_poll(q) for q in question_ids))

    # Start the timeout task with the calculated duration
    asyncio.create_task(check_quiz_timeout(user_id, session_id, chat_id, timeout_duration))

    await message.answer(f"✅ {requested_count} questions sent! Answer them quickly to avoid timeout And After answering all question you will get explnantions and your result will be uploadede to leaderboard.")

@dp.poll_answer()
async def handle_poll_answer(poll_answer: PollAnswer):
    """Handle poll answers submitted by the user."""
    user_id = poll_answer.user.id
    poll_id = poll_answer.poll_id
    selected_option = poll_answer.option_ids[0]

    correct_option_id = poll_tracking.get(poll_id)
    session = await db["user_sessions"].find_one({"user_id": user_id})

    if not session:
        await bot.send_message(user_id, "❌ No active session found.")
        return

    answered = session.get("answered", 0)
    sent = session.get("sent", 0)

    if correct_option_id is not None and selected_option == correct_option_id:
        await db["user_sessions"].update_one(
            {"user_id": user_id},
            {"$addToSet": {"correct_questions": poll_id}}
        )

    await db["user_sessions"].update_one(
        {"user_id": user_id},
        {"$inc": {"answered": 1}}
    )

    if answered + 1 >= sent:
        await store_and_show_result(user_id, poll_answer.user.id)

async def store_and_show_result(user_id, chat_id):
    """Store the quiz result and display it to the user."""
    session = await db["user_sessions"].find_one({"user_id": user_id})

    if not session:
        await bot.send_message(chat_id, "❌ No session found.")
        return

    question_ids = session.get("question_ids", [])
    correct_answers_today = session.get("correct_questions", [])
    total_answered = session.get("answered", 0)
    sent = session.get("sent", 0)
    score = len(correct_answers_today)

    selected_language = session.get("selected_language", "en")
    explanations = []

    for question_id in question_ids:
        question = await polls_collection.find_one({"_id": question_id})
        if question:
            lang_data = question['languages'].get(selected_language, {})
            explanation = (
                f"Q: {lang_data.get('question', 'N/A')}\n"
                f"Explanation: {lang_data.get('explanation', 'No explanation available.')}"
            )
            explanations.append(explanation)

    explanation_text = "\n\n".join(explanations)
    result_message = (
        f"📊 Quiz Summary:\n"
        f"Total Questions Answered: {total_answered}\n"
        f"Score: {score}/{sent}\n\n"
        f"📄 Explanations:\n{explanation_text}"
    )

    chunks = chunk_text(result_message, 4096)

    for chunk in chunks:
        await bot.send_message(chat_id, chunk)

    result = {
        "user_id": user_id,
        "score": score,
        "total_questions": sent,
        "correct_answers": score,
        "date": datetime.now()
    }
    await db["results"].insert_one(result)

    await users_collection.update_one(
        {"user_id": user_id},
        {
            "$inc": {"daily_score": score, "monthly_score": score, "total_score": score},
            "$set": {"last_result": result}
        },
        upsert=True
    )

    await db["user_sessions"].delete_one({"user_id": user_id})

def chunk_text(text, max_length=4096):
    """Split long text into chunks within Telegram's message limit."""
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_index = text.rfind('\n', 0, max_length)
        if split_index == -1:
            split_index = max_length
        chunks.append(text[:split_index])
        text = text[split_index:].strip()
    return chunks



@dp.message(Command("grant_access"))
async def handle_grant_access(message: types.Message):
    """Admin command to grant unlimited access."""
    if not is_admin(message.from_user.id):
        await message.reply("This command is restricted to admins.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: /grant_access <username_or_user_id>")
        return

    # Handle both user ID and username inputs
    target = args[1]
    user_id = await get_user_id(target)  # Unified logic for both username and ID

    if not user_id:
        await message.reply("User not found.")
        return

    # Grant unlimited access
    await grant_access(user_id)
    await message.reply(f"✅ Unlimited access granted to user with ID: {user_id}.")

async def get_user_id(target: str) -> int | None:
    """Fetch the user ID from the database using either username or user ID."""
    if target.isdigit():
        return int(target)  # If it's already a user ID, return it as an integer

    # Try to find the user by username
    user = await users_collection.find_one({"username": target})
    if user:
        return user["user_id"]
    return None  # Return None if the user isn't found

async def grant_access(user_id: int, duration_days: int = 30):
    """Grant unlimited access to a user."""
    expiry_date = datetime.now() + timedelta(days=duration_days)

    await users_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "unlimited_access": True,
                "unlimited_access_expiry": expiry_date,
                "daily_questions": float('inf')
            }
        },
        upsert=True
    )

    # Notify the user
    try:
        await bot.send_message(
            user_id,
            f"🎉 Congratulations! You now have unlimited access until {expiry_date.strftime('%d %B %Y')}."
        )
    except Exception as e:
        logging.error(f"Failed to notify user {user_id}: {e}")


@dp.message(Command("revoke_access"))
async def handle_revoke_access(message: types.Message):
    """Admin command to revoke a user's unlimited access."""
    if not is_admin(message.from_user.id):
        await message.reply("This command is restricted to admins.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Usage: /revoke_access <username_or_user_id>")
        return

    # Handle both user ID and username inputs
    target = args[1]
    user_id = await get_user_id(target)  # Reuse the same logic for both inputs

    if not user_id:
        await message.reply("User not found.")
        return

    # Revoke access and reset daily questions to 30
    await users_collection.update_one(
        {"user_id": user_id},
        {
            "$unset": {"unlimited_access": "", "unlimited_access_expiry": ""},
            "$set": {"daily_questions": 30}
        }
    )

    # Notify the user about the revocation
    try:
        await bot.send_message(user_id, "⚠️ Your unlimited access has been revoked.")
    except Exception as e:
        logging.error(f"Failed to notify user {user_id}: {e}")
        await message.reply(f"⚠️ Could not notify user {user_id}. They might have blocked the bot.")

    # Confirm to the admin
    await message.reply(f"✅ Unlimited access revoked for user with ID: {user_id}.")




@dp.message(Command("reset_leaderboard"))
async def handle_reset_leaderboard(message: types.Message):
    """Admin command to reset all users' leaderboard scores."""
    if not is_admin(message.from_user.id):
        await message.reply("This command is restricted to admins.")
        return

    await users_collection.update_many({}, {"$set": {"total_score": 0}})
    await message.reply("Leaderboard has been reset.")

async def reset_daily_scores():
    """Reset daily scores at midnight."""
    await users_collection.update_many({}, {"$set": {"daily_score": 0}})
    logging.info("✅ Daily scores reset successfully.")




async def reset_daily_questions():
    """Reset daily questions for all users at midnight."""
    await users_collection.update_many(
        {"unlimited_access": {"$ne": True}},  # Reset only for non-unlimited users
        {"$set": {"daily_questions": 0}}
    )
    logging.info("✅ Daily questions reset successfully.")

async def schedule_resets():
    """Schedule daily resets for scores and questions at midnight."""
    while True:
        now = datetime.now()
        
        # Calculate the next midnight
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_midnight = (next_midnight - now).total_seconds()

        logging.info(f"Sleeping for {seconds_until_midnight} seconds until the next reset.")

        # Sleep until midnight
        await asyncio.sleep(seconds_until_midnight)

        # Perform the resets
        await reset_daily_questions()
        await reset_daily_scores()
        logging.info("✅ Daily questions and scores reset successfully.")



async def main():
    """Main entry point of the bot."""
    await set_bot_commands()
    asyncio.create_task(schedule_resets())  # Start reset scheduling

    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logging.error(f"Error during polling: {e}")

if __name__ == "__main__":
    asyncio.run(main())
