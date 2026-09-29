# 24/7 Background Review Bot (Ban-Proof Architecture) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable CRG Review Bot to operate 24/7 in the background fetching, drafting, and posting review replies safely without custom Google Business Profile API developer approvals and with zero risk of account suspension.

**Architecture:** Implement a dual-mode integration layer: (1) An incoming/outgoing Webhook gateway that interfaces with pre-verified Google Enterprise Partners (Make.com / Zapier) to poll reviews and post replies using official Google-approved partner tokens, and (2) a resilient 24/7 background worker with persistent state and health monitoring on free-tier cloud hosting.

**Tech Stack:** Python 3.10+, Flask, SQLite (WAL mode), Groq API (`openai/gpt-oss-120b`), Telegram Bot API, Make.com (free tier Google Business Profile integration), APScheduler / Systemd / PM2.

---

### Comparison of Approaches for 24/7 Operation

| Approach | 24/7 Autonomous? | Ban Risk | Google Dev Approval Needed? | Monthly Cost | Reliability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A. Verified Partner Bridge (Make.com)** | **Yes (100%)** | **0% (Official OAuth)** | **No** (uses Make's Google license) | **$0** (Free tier < 1,000 ops) | **High** |
| **B. Headless Browser (Playwright/Puppeteer)** | Yes | **Extremely High (Profile Bans)** | No | $0 | Low (breaks on CAPTCHA/CSS) |
| **C. Official GBP API Fast-Track** | **Yes (100%)** | **0% (Official API)** | Yes (2–4 day form approval) | **$0** | **High** |
| **D. Gmail Notification Webhook** | Partial (Needs click) | **0% (Read-only)** | No | **$0** | **High** |

> [!IMPORTANT]
> **Recommended Path:** **Approach A (Verified Partner Bridge)**.
> Make.com is an officially verified Google Workspace/Cloud Enterprise Partner. Connecting your Google Business Profile through Make.com takes 3 minutes, requires **zero API approvals from Google**, and allows your existing Python bot to receive review triggers and execute owner replies 24/7 without risking Google account suspensions or CAPTCHA blocks.

---

### Task 1: Fix Database Concurrency & Timestamp Handling for 24/7 Uptime

**Files:**
- Modify: `db.py:1-35`
- Modify: `worker.py:30-45, 50-60`

**Step 1: Write SQLite WAL mode and connection timeout test**
Verify that multi-threaded access from Flask and APScheduler does not throw `sqlite3.OperationalError: database is locked`.

**Step 2: Update `db.py` to enable WAL mode and connection timeout**
```python
# db.py
import sqlite3
from datetime import datetime, timezone

DB_PATH = "reviews.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn
```

**Step 3: Fix offset-naive vs. offset-aware datetime bug in `worker.py`**
Ensure all fallback timestamps use `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow()`, and ensure `parse_time` always attaches UTC timezone if missing.

---

### Task 2: Implement Make.com / Webhook Gateway in `app.py`

**Files:**
- Modify: `app.py`
- Modify: `worker.py`
- Modify: `.env.example`

**Step 1: Add Webhook Endpoints for Incoming Reviews and Outgoing Replies**
Create a secure endpoint that Make.com calls when a new review arrives:
- Route: `POST /api/webhook/review-received`
  - Payload: `{ "review_id": "...", "reviewer_name": "...", "star_rating": 5, "comment": "...", "review_time": "..." }`
  - Stores review in SQLite.
  - If 4–5 stars: Groq drafts reply, returns reply in response payload for Make.com to post directly to Google Business Profile.
  - If 1–3 stars: Groq drafts reply, stores as `ai_drafted`, sends Telegram alert with dashboard link.
- Route: `POST /api/webhook/poll-approved`
  - Returns pending approved replies for Make.com to publish to Google.

**Step 2: Add API Key authentication for the webhook**
Secure webhook endpoints using a shared `WEBHOOK_SECRET` header.

---

### Task 3: Configure Make.com 24/7 Google Business Profile Scenario

**Setup Steps:**
1. Create a free account at [make.com](https://www.make.com).
2. Create **Scenario 1: New Review Ingestion & Auto-Reply (24/7)**:
   - **Trigger:** Module `Google My Business` -> `Watch Reviews` (Interval: every 15 minutes).
   - **Action 1:** Module `HTTP` -> `Make a request` (Send review payload to `https://your-bot-url/api/webhook/review-received`).
   - **Router:**
     - Path 1 (If rating >= 4): Module `Google My Business` -> `Create/Update a Reply` using the response from your Python bot.
     - Path 2 (If rating <= 3): End of scenario (Bot handles Telegram notification to manager).
3. Create **Scenario 2: Approved Reply Publisher (24/7)**:
   - **Trigger:** Module `HTTP` -> Polls `https://your-bot-url/api/webhook/poll-approved` every 10 minutes (or webhook triggered on dashboard approval).
   - **Action:** Module `Google My Business` -> `Create/Update a Reply`.

---

### Task 4: 24/7 Server Daemonization & Self-Healing Watchdog

**Files:**
- Create: `crg-bot.service` (for Linux systemd)
- Modify: `render.yaml`
- Modify: `app.py`

**Step 1: Add a lightweight health-check endpoint**
Add `/health` route to `app.py` returning `{"status": "ok", "uptime": ...}` for free uptime monitors (e.g. UptimeRobot) to keep free cloud tiers awake.

**Step 2: Create a systemd service file for 24/7 self-restart on VM reboot**
```ini
[Unit]
Description=CRG Review Bot 24/7 Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/crg-review-bot
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=10
EnvironmentFile=/home/ubuntu/crg-review-bot/.env

[Install]
WantedBy=multi-user.target
```

---

### Task 5: End-to-End Verification & Dry Run

**Test Cases:**
1. **Concurrency test:** Simultaneous review write and dashboard read without SQLite locking.
2. **Auto-reply pipeline:** Synthetic 5-star review processed through Groq and logged as ready to post.
3. **Escalation pipeline:** Synthetic 2-star review triggers Telegram alert and displays in dashboard awaiting manager approval.
4. **Failure recovery:** Process killed (`kill -9`) and verified to auto-resume via PM2 / systemd without corrupted SQLite state.
