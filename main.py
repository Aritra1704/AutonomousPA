import os
from datetime import datetime
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime

import requests
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

SUPABASE_DB_URL = os.getenv("DATABASE_URL")  # use Supabase connection string
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

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

    if not GEMINI_API_KEY:
        return "Gemini API key is not configured."

    url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"

    headers = {
        "Content-Type": "application/json"
    }

    body = {
        "contents": [
            {
                "parts": [{"text": final_prompt}]
            }
        ]
    }

    try:
        res = requests.post(
            url,
            headers=headers,
            params={"key": GEMINI_API_KEY},
            json=body,
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except requests.RequestException as exc:
        print("Gemini HTTP error:", exc)
        return f"Gemini HTTP error: {exc}"
    except (KeyError, IndexError, TypeError) as exc:
        print("Gemini parse error:", exc)
        return f"Gemini parse error: {exc}"

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

# ---- Gmail Helpers ----
def decode_mime_words(value):
    if not value:
        return ""
    decoded = decode_header(value)
    parts = []
    for text, encoding in decoded:
        if isinstance(text, bytes):
            parts.append(text.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(text)
    return "".join(parts)


def extract_plain_text(message):
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")
            if content_type == "text/plain" and "attachment" not in content_disposition:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                try:
                    return payload.decode(charset, errors="replace")
                except Exception:
                    return payload.decode("utf-8", errors="replace")
    else:
        payload = message.get_payload(decode=True)
        if payload is not None:
            charset = message.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except Exception:
                return payload.decode("utf-8", errors="replace")
        payload = message.get_payload()
        if isinstance(payload, str):
            return payload
    return ""


def fetch_gmail_messages(limit=5):
    if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
        print("Gmail credentials missing.")
        return []

    limit = max(1, min(limit, 20))
    imap = None
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        imap.select("INBOX")
        status, data = imap.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            status, data = imap.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            return []

        mail_ids = data[0].split()
        selected_ids = mail_ids[-limit:]
        messages = []
        for msg_id in reversed(selected_ids):
            status, msg_data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data:
                continue
            raw_email = msg_data[0][1]
            message = email.message_from_bytes(raw_email)
            subject = decode_mime_words(message.get("Subject"))
            sender = decode_mime_words(message.get("From"))
            date_raw = message.get("Date")

            try:
                date_obj = parsedate_to_datetime(date_raw) if date_raw else None
                if date_obj and date_obj.tzinfo:
                    date_obj = date_obj.astimezone()
            except Exception:
                date_obj = None

            date_display = date_obj.strftime("%Y-%m-%d %H:%M") if isinstance(date_obj, datetime) else (date_raw or "")
            body = extract_plain_text(message)
            snippet = " ".join(body.split())[:200] if body else ""

            messages.append(
                {
                    "subject": subject or "(no subject)",
                    "sender": sender or "(unknown sender)",
                    "date": date_display,
                    "snippet": snippet,
                }
            )
        return messages
    except Exception as exc:
        print("Gmail fetch error:", exc)
        return []
    finally:
        if imap is not None:
            try:
                imap.close()
            except Exception:
                pass
            try:
                imap.logout()
            except Exception:
                pass


def save_email_draft_to_db(recipient, subject, body, notes):
    if not SUPABASE_DB_URL:
        print("Draft insert skipped: DATABASE_URL not configured.")
        return None

    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO email_drafts (recipient, subject, body, notes) VALUES (%s, %s, %s, %s) RETURNING id, created_at",
            (recipient, subject, body, notes),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return row
    except Exception as e:
        print("Draft insert error:", e)
        return None

# ---- Handlers ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Assistant is live.\n"
        "Use /code for coding help, /task to add a task, /tasks to review tasks,\n"
        "/gmail to fetch recent emails, and /draft to generate an email draft."
    )

async def gmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text or ""
    limit_text = message_text.partition(" ")[2].strip()

    limit = 5
    if limit_text.isdigit():
        limit = max(1, min(int(limit_text), 20))

    emails = fetch_gmail_messages(limit=limit)
    if not emails:
        reply = (
            "No emails retrieved. Confirm Gmail credentials and IMAP access "
            "are configured."
        )
    else:
        lines = ["Recent Gmail messages:"]
        for idx, message_data in enumerate(emails, start=1):
            lines.append(f"{idx}. {message_data['subject']}")
            lines.append(f"   From: {message_data['sender']}")
            if message_data["date"]:
                lines.append(f"   Date: {message_data['date']}")
            if message_data["snippet"]:
                lines.append(f"   Snippet: {message_data['snippet']}")
        reply = "\n".join(lines)

    log_to_db(f"/gmail limit={limit}", reply)
    await update.message.reply_text(reply[:4000])

async def draft_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text or ""
    payload = message_text.partition(" ")[2]

    if not payload:
        await update.message.reply_text(
            "Usage: /draft recipient@example.com | Subject | brief instructions"
        )
        return

    parts = [part.strip() for part in payload.split("|", 2)]
    if len(parts) < 3 or not all(parts):
        await update.message.reply_text(
            "Please provide recipient, subject, and instructions separated by '|'."
        )
        return

    recipient, subject, instructions = parts

    gemini_prompt = (
        "Compose a clear, professional email draft.\n"
        f"Recipient: {recipient}\n"
        f"Subject: {subject}\n"
        f"Instructions: {instructions}\n"
        "Include greeting, body, and courteous closing with sender placeholder."
    )

    memory_entries = fetch_recent_logs(limit=5)
    draft_body = call_gemini(gemini_prompt, memory_entries=memory_entries)

    draft_row = save_email_draft_to_db(recipient, subject, draft_body, instructions)
    if draft_row:
        draft_id, created_at = draft_row
        if isinstance(created_at, datetime):
            created_at_str = created_at.strftime("%Y-%m-%d %H:%M")
        else:
            created_at_str = str(created_at)
        header = f"Draft #{draft_id} saved ({created_at_str})."
    else:
        header = "Draft generated (not saved due to database issue)."

    reply = f"{header}\n\n{draft_body}"
    log_to_db(f"/draft {recipient} | {subject}", draft_body)

    await update.message.reply_text(reply[:4000])

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
app.add_handler(CommandHandler("gmail", gmail_command))
app.add_handler(CommandHandler("draft", draft_command))
app.add_handler(CommandHandler("task", task_command))
app.add_handler(CommandHandler("tasks", tasks_command))
app.add_handler(CommandHandler("code", code))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.run_polling()