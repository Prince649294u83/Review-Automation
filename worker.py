import os
import logging
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

import db
import gbp_client
import ai_client
import notifier

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

REPLY_DELAY_HOURS = int(os.getenv("REPLY_DELAY_HOURS", 24))
AUTO_MIN_STARS    = int(os.getenv("AUTO_REPLY_MIN_STARS", 4))

STAR_MAP = {
    "ONE": 1, "TWO": 2, "THREE": 3,
    "FOUR": 4, "FIVE": 5
}


def parse_time(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


# ══════════════════════════════════════════════════════
# JOB 1 — Fetch & store new reviews (every 30 minutes)
# ══════════════════════════════════════════════════════
def fetch_and_store():
    log.info("📥 Fetching reviews from Google Business Profile...")
    try:
        raw_reviews = gbp_client.fetch_reviews()
        new = 0

        for r in raw_reviews:
            review_id    = r.get("reviewId", "")
            reviewer     = r.get("reviewer", {}).get("displayName", "Guest")
            star_rating  = STAR_MAP.get(r.get("starRating", "FIVE"), 5)
            comment      = r.get("comment", "")
            review_time  = r.get("createTime", datetime.utcnow().isoformat())
            already_replied = "reviewReply" in r  # Already has an owner reply

            # Only store if: new to us AND not already replied to
            if not db.review_exists(review_id) and not already_replied:
                db.insert_review(
                    review_id, reviewer, star_rating,
                    comment, review_time
                )
                new += 1
                log.info(f"  ➕ Stored: '{reviewer}' ({star_rating}★)")

        log.info(f"✅ Done. {new} new reviews stored.")

    except Exception as e:
        log.error(f"❌ Fetch failed: {e}")


# ══════════════════════════════════════════════════════
# JOB 2 — Process pending reviews (every 30 minutes)
# ══════════════════════════════════════════════════════
def process_pending():
    log.info("⚙️  Processing pending reviews...")
    now = datetime.now(timezone.utc)

    for review in db.get_pending_reviews():
        review_id   = review["review_id"]
        reviewer    = review["reviewer_name"]
        stars       = review["star_rating"]
        comment     = review["comment"]
        review_time = parse_time(review["review_time"])

        # ── 24-HOUR DELAY CHECK ──────────────────────────
        age_hours = (now - review_time).total_seconds() / 3600
        if age_hours < REPLY_DELAY_HOURS:
            remaining = REPLY_DELAY_HOURS - age_hours
            log.info(
                f"  ⏳ '{reviewer}' — "
                f"{remaining:.1f}h remaining before reply window"
            )
            continue
        # ─────────────────────────────────────────────────

        # ── Generate AI reply ─────────────────────────────
        log.info(f"  🤖 Generating reply for: '{reviewer}' ({stars}★)")
        try:
            draft = ai_client.generate_reply(reviewer, stars, comment)
        except Exception as e:
            log.error(f"  ❌ AI generation failed: {e}")
            db.update_review(review_id, error_message=str(e))
            continue

        # ── Route based on star rating ────────────────────
        if stars >= AUTO_MIN_STARS:
            # 4 or 5 stars → Auto-post immediately
            review_name = f"{os.getenv('GBP_LOCATION_NAME')}/reviews/{review_id}"
            success, msg = gbp_client.post_reply(review_name, draft)

            if success:
                db.update_review(
                    review_id,
                    status         = "posted",
                    ai_draft       = draft,
                    approved_reply = draft,
                    posted_at      = datetime.utcnow().isoformat()
                )
                notifier.notify_auto_posted(reviewer, stars, draft)
                log.info(f"  ✅ Auto-posted reply to '{reviewer}'")
            else:
                db.update_review(
                    review_id,
                    status        = "pending",
                    error_message = msg
                )
                notifier.notify_error(review_id, msg)
                log.error(f"  ❌ Post failed: {msg}")

        else:
            # 1-3 stars → Save draft, send to Telegram for approval
            db.update_review(
                review_id,
                status   = "ai_drafted",
                ai_draft = draft
            )
            notifier.alert_low_star_review(
                reviewer, stars, comment, draft, review_id
            )
            log.info(
                f"  📲 Sent {stars}★ review to Telegram for approval"
            )


# ══════════════════════════════════════════════════════
# JOB 3 — Post approved replies (every 10 minutes)
# ══════════════════════════════════════════════════════
def post_approved():
    """
    Picks up reviews you approved on the dashboard and posts them.
    """
    for review in db.get_awaiting_approval():
        review_id      = review["review_id"]
        approved_reply = review["approved_reply"]

        # Only post if you've actually approved a reply text
        if not approved_reply:
            continue

        review_name = (
            f"{os.getenv('GBP_LOCATION_NAME')}/reviews/{review_id}"
        )
        success, msg = gbp_client.post_reply(review_name, approved_reply)

        if success:
            db.update_review(
                review_id,
                status    = "posted",
                posted_at = datetime.utcnow().isoformat()
            )
            log.info(f"✅ Posted approved reply for review {review_id}")
        else:
            notifier.notify_error(review_id, msg)
            log.error(f"❌ Failed to post approved reply: {msg}")


# ══════════════════════════════════════════════════════
# Scheduler setup
# ══════════════════════════════════════════════════════
def start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)

    # Fetch reviews every 30 minutes, run immediately on startup
    scheduler.add_job(
        fetch_and_store,
        "interval",
        minutes=30,
        id="fetch",
        next_run_time=datetime.now()
    )

    # Process pending reviews every 30 minutes (5 min offset so fetch runs first)
    scheduler.add_job(
        process_pending,
        "interval",
        minutes=30,
        id="process",
        next_run_time=datetime.now() + timedelta(minutes=5)
    )

    # Check for approved replies every 10 minutes
    scheduler.add_job(
        post_approved,
        "interval",
        minutes=10,
        id="post_approved"
    )

    scheduler.start()
    log.info("🚀 Scheduler running — CRG Meridian review bot is LIVE")
    return scheduler
