import os
from datetime import datetime

import requests
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

SUPABASE_DB_URL = os.getenv("DATABASE_URL")  # use Supabase connection string

# ---- Memory Helpers ----
def truncate_for_memory(text, limit=800):
    if text is None:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."

def fetch_recent_logs(limit=5):
    if not SUPABASE_DB_URL:
        return []

    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()
        cur.execute(
            "SELECT action, result FROM logs ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return list(reversed(rows))
    except Exception as e:
        print("DB fetch error:", e)
        return []

def format_memory_context(entries):
    if not entries:
        return ""

    lines = ["Context from recent interactions:"]
    for idx, (action, result) in enumerate(entries, start=1):
        lines.append(f"{idx}. User: {truncate_for_memory(action)}")
        lines.append(f"   Assistant: {truncate_for_memory(result)}")
    lines.append("")
    return "\n".join(lines)

# ---- Gemini Call ----
def call_gemini(prompt, memory_entries=None):
    memory_prefix = format_memory_context(memory_entries)
    final_prompt = f"{memory_prefix}{prompt}" if memory_prefix else prompt

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    body = {
        "contents": [
            {
                "parts": [{"text": final_prompt}]
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

# ---- Task Helpers ----
def add_task_to_db(task_text, status="pending"):
    if not SUPABASE_DB_URL:
        print("Task insert skipped: DATABASE_URL not configured.")
        return None

    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tasks (task, status) VALUES (%s, %s) RETURNING id, status, created_at",
            (task_text, status),
        )
        task_row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return task_row
    except Exception as e:
        print("Task insert error:", e)
        return None


def fetch_recent_tasks(limit=10):
    if not SUPABASE_DB_URL:
        return []

    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, task, status, created_at FROM tasks ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print("Task fetch error:", e)
        return []


def format_tasks_list(tasks):
    if not tasks:
        return "No tasks recorded yet."

    lines = ["Recent tasks:"]
    for task_id, task_text, status, created_at in tasks:
        if isinstance(created_at, datetime):
            created_at_str = created_at.strftime("%Y-%m-%d %H:%M")
        else:
            created_at_str = str(created_at)
        lines.append(f"{task_id} [{status}] {task_text} — {created_at_str}")
    return "\n".join(lines)

# ---- Handlers ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Assistant is live.\n"
        "Use /code for coding help, /task to add a task, and /tasks to review recent tasks."
    )

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text or ""
    task_text = message_text.partition(" ")[2].strip()

    if not task_text:
        await update.message.reply_text("Please provide a description after /task to save a task.")
        return

    task_row = add_task_to_db(task_text)
    if not task_row:
        await update.message.reply_text("Could not save the task. Please try again later.")
        return

    task_id, status, created_at = task_row
    if isinstance(created_at, datetime):
        created_at_str = created_at.strftime("%Y-%m-%d %H:%M")
    else:
        created_at_str = str(created_at)

    reply = f"Task #{task_id} recorded ({status}) at {created_at_str}."
    log_to_db(f"/task {task_text}", reply)

    await update.message.reply_text(reply)

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text or ""
    limit_text = message_text.partition(" ")[2].strip()

    limit = 10
    if limit_text.isdigit():
        limit = max(1, min(int(limit_text), 30))

    tasks = fetch_recent_tasks(limit=limit)
    reply = format_tasks_list(tasks)

    log_to_db(f"/tasks limit={limit}", reply)

    await update.message.reply_text(reply[:4000])

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

    memory_entries = fetch_recent_logs(limit=5)
    reply = call_gemini(gemini_prompt, memory_entries=memory_entries)

    log_to_db(f"/code {request_text}", reply)

    await update.message.reply_text(reply[:4000])  # Telegram limit

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    memory_entries = fetch_recent_logs(limit=5)
    reply = call_gemini(user_text, memory_entries=memory_entries)

    log_to_db(user_text, reply)

    await update.message.reply_text(reply[:4000])  # Telegram limit

# ---- App ----
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("task", task_command))
app.add_handler(CommandHandler("tasks", tasks_command))
app.add_handler(CommandHandler("code", code))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()