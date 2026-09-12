import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")
DASHBOARD  = os.getenv("DASHBOARD_URL", "http://YOUR_SERVER_IP:5000")


def _send(text: str, parse_mode: str = "Markdown"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    })


def alert_low_star_review(reviewer_name, star_rating, comment, ai_draft, review_id):
    """
    Sends you a Telegram alert for 1-3 star reviews.
    Includes the AI draft and a link to approve/edit on dashboard.
    """
    stars = "⭐" * star_rating
    msg = f"""
🔴 *New {star_rating}-Star Review — Action Required*

👤 *Reviewer:* {reviewer_name}
{stars}

💬 *Their Review:*
_{comment or "(No written comment)"}_

🤖 *AI Draft Reply:*
_{ai_draft}_

👉 [Review & Approve on Dashboard]({DASHBOARD}/review/{review_id})

_Reply within 24h is ideal. Edit the draft if needed before approving._
"""
    _send(msg)


def notify_auto_posted(reviewer_name, star_rating, reply_preview):
    """
    Silent confirmation when a 4-5 star reply is auto-posted.
    """
    stars = "⭐" * star_rating
    _send(
        f"✅ *Auto-replied* to {star_rating}★ review by {reviewer_name}\n"
        f"{stars}\n\n"
        f"_{reply_preview[:100]}..._"
    )


def notify_error(review_id, error_msg):
    """Alert if posting a reply fails."""
    _send(
        f"⚠️ *Failed to post reply*\n"
        f"Review ID: `{review_id}`\n"
        f"Error: `{error_msg}`"
    )
