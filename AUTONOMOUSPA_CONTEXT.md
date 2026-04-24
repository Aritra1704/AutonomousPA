🧠 AUTONOMOUSPA — SYSTEM CONTEXT (MASTER FILE)

🎯 PROJECT GOAL

Build a 24/7 autonomous personal assistant that:

- Runs on Railway
- Controlled via Telegram
- Uses Gemini API (cost-efficient)
- Stores memory in Supabase
- Executes tasks safely with human-in-loop

---

🧱 CURRENT ARCHITECTURE

Telegram Bot
→ Python Service (Railway)
→ Gemini API (LLM)
→ Supabase (Postgres DB)

---

⚙️ TECH STACK

- Language: Python 3.11
- Framework: python-telegram-bot
- LLM: Google Gemini (gemini-1.5-flash)
- DB: Supabase (Postgres)
- Hosting: Railway
- IDE: VS Code + Codex

---

🔐 ENV VARIABLES (EXPECTED)

TELEGRAM_BOT_TOKEN=
GOOGLE_API_KEY=
DATABASE_URL=

---

🧠 DATABASE STRUCTURE

logs table

- id (uuid)
- action (text)
- result (text)
- created_at (timestamp)

tasks table (future)

- id
- task
- status
- created_at

memory table (future)

- id
- key
- value
- created_at

---

🚨 CURRENT STATUS

- Telegram bot created ✅
- Gemini API key created ✅
- Supabase DB created ✅
- Tables created ✅
- Railway deployment ❌ (FAILED — needs fix)

---

⚠️ KNOWN ISSUES

- Railway deployment failing (likely start command or runtime issue)
- DB connection may not be verified
- Need stable polling process for Telegram bot

---

🔐 CONSTRAINTS (VERY IMPORTANT)

- Monthly budget: ₹1000
- Must avoid excessive API calls
- No autonomous destructive actions
- No auto email sending (future feature)
- Human approval required for critical actions

---

🧭 DESIGN PRINCIPLES

- Keep system SIMPLE and controllable
- Prefer polling over webhooks (Railway friendly)
- Log everything to DB
- Fail gracefully (no crashes)
- Avoid heavy frameworks (no OpenClaw dependency)

---

🚀 PHASE PLAN

PHASE 1 (CURRENT)

- Fix Railway deployment
- Ensure Telegram bot responds
- Ensure Gemini API works
- Ensure DB logging works

---

PHASE 2

- Add "/code" command (coding agent)
- Add structured memory retrieval
- Add task tracking system

---

PHASE 3

- Gmail integration (read + draft)
- Google Calendar integration
- Notification system

---

PHASE 4

- Autonomous task execution (cron based)
- Daily summaries via Telegram
- Smart prioritization

---

🧪 EXPECTED BEHAVIOR

User sends message → Telegram
→ Python service receives
→ Calls Gemini
→ Stores response in Supabase
→ Replies back in Telegram

---

🔧 REQUIRED FIXES (IMMEDIATE)

1. Fix Railway deployment:
   
   - Ensure correct start command:
     python main.py

2. Ensure requirements.txt installed

3. Validate DATABASE_URL connection

4. Ensure polling mode is active:
   app.run_polling()

---

🧠 CODING RULES FOR CODEX

- Always use simple Python (no overengineering)
- Prefer sync HTTP (requests)
- Handle API failures safely
- Limit response size (Telegram limit ~4000 chars)
- Always log input/output to DB
- Do NOT introduce new frameworks unless necessary

---

🔥 NEXT TASK (FOR CODEX)

Fix deployment failure and ensure:

- Bot runs continuously on Railway
- No crashes
- Responds to "hi" message
- Logs response to Supabase

---

📌 SUCCESS CRITERIA

- Telegram bot replies reliably
- Gemini API returns valid response
- Logs stored in DB
- Service runs continuously on Railway

---

🧠 FUTURE VISION

Turn this into:

- AI coding assistant
- Personal productivity system
- Passive income automation engine

---

⚠️ FINAL NOTE

Do NOT:

- Introduce OpenClaw again
- Use OAuth-based Gemini auth
- Add unnecessary complexity

Keep system lean, stable, and scalable.
