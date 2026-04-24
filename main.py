import os
import requests
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

SUPABASE_DB_URL = os.getenv("DATABASE_URL")  # use Supabase connection string

# ---- Gemini Call ----
def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    body = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }

    res = requests.post(url, json=body)
    data = res.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return str(data)

# ---- DB Logging ----
def log_to_db(prompt, response):
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO logs (action, result) VALUES (%s, %s)",
            (prompt, response)
        )

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("DB error:", e)

# ---- Handlers ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Assistant is live")

async def code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text or ""
    request_text = message_text.partition(" ")[2].strip()

    if not request_text:
        await update.message.reply_text("Please provide details after /code to describe the coding task.")
        return

    gemini_prompt = (
        "You are an expert software engineer. Provide a concise, code-focused answer.\n"
        f"Task: {request_text}"
    )

    reply = call_gemini(gemini_prompt)

    log_to_db(f"/code {request_text}", reply)

    await update.message.reply_text(reply[:4000])  # Telegram limit

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    reply = call_gemini(user_text)

    log_to_db(user_text, reply)

    await update.message.reply_text(reply[:4000])  # Telegram limit

# ---- App ----
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("code", code))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()