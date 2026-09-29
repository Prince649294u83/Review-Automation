import os
from functools import wraps
from datetime import datetime, timezone

from flask import (
    Flask, render_template, redirect, url_for,
    request, session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

import db
import worker
import ai_client
import notifier

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change_this_secret")

PWD_HASH = generate_password_hash(os.getenv("APP_PASSWORD", "admin"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
AUTO_MIN_STARS = int(os.getenv("AUTO_REPLY_MIN_STARS", 4))

# ── Start DB and scheduler on launch ─────────────────
db.init_db()

# Only start scheduler if not disabled (e.g., during tests or CLI scripts)
if os.getenv("ENABLE_SCHEDULER", "true").lower() in ("true", "1") and not os.getenv("FLASK_TESTING"):
    scheduler = worker.start_scheduler()
else:
    scheduler = None



# ── Auth decorator ────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def check_webhook_auth():
    """Validates optional webhook authentication via header."""
    if not WEBHOOK_SECRET:
        return True
    auth = request.headers.get("X-Webhook-Secret") or request.headers.get("Authorization")
    if not auth:
        return False
    return auth == WEBHOOK_SECRET or auth == f"Bearer {WEBHOOK_SECRET}"


# ── Health Check ──────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for 24/7 uptime monitors (e.g., UptimeRobot, Render)."""
    return jsonify({
        "status": "healthy",
        "service": "crg-review-bot",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


# ── Login / Logout ────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if check_password_hash(PWD_HASH, request.form.get("password", "")):
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("❌ Wrong password. Try again.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────
@app.route("/")
@login_required
def dashboard():
    reviews = db.get_all_reviews(limit=100)
    counts  = {
        "pending":   sum(1 for r in reviews if r["status"] == "pending"),
        "drafts":    sum(1 for r in reviews if r["status"] == "ai_drafted"),
        "posted":    sum(1 for r in reviews if r["status"] == "posted"),
        "skipped":   sum(1 for r in reviews if r["status"] == "skipped"),
    }
    return render_template("dashboard.html", reviews=reviews, counts=counts)


# ── Review Detail + Approval ──────────────────────────
@app.route("/review/<review_id>", methods=["GET", "POST"])
@login_required
def review_detail(review_id):
    review = db.get_review_by_id(review_id)
    if not review:
        flash("Review not found.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "approve":
            edited = request.form.get("reply_text", "").strip()
            if not edited:
                flash("⚠️ Reply text cannot be empty.")
            else:
                db.update_review(
                    review_id,
                    approved_reply = edited,
                    status         = "ai_drafted"
                )
                
                # Attempt immediate post if direct GBP credentials exist
                posted_now = False
                try:
                    import gbp_client
                    if os.getenv("GBP_LOCATION_NAME") and os.path.exists(gbp_client.TOKEN_FILE) and os.path.getsize(gbp_client.TOKEN_FILE) > 0:
                        review_name = f"{os.getenv('GBP_LOCATION_NAME')}/reviews/{review_id}"
                        success, msg = gbp_client.post_reply(review_name, edited)
                        if success:
                            db.update_review(
                                review_id,
                                status    = "posted",
                                posted_at = datetime.now(timezone.utc).isoformat()
                            )
                            posted_now = True
                            flash("✅ Reply posted immediately to Google Business Profile!")
                except Exception as e:
                    posted_now = False

                if not posted_now:
                    flash("✅ Reply approved! Queued to post via background job / webhook.")

        elif action == "regenerate":
            try:
                new_draft = ai_client.generate_reply(
                    review["reviewer_name"],
                    review["star_rating"],
                    review["comment"]
                )
                db.update_review(review_id, ai_draft=new_draft)
                flash("🔄 Fresh AI draft generated!")
            except Exception as e:
                flash(f"❌ AI error: {e}")

        elif action == "skip":
            db.update_review(review_id, status="skipped")
            flash("⏭️ Review skipped.")
            return redirect(url_for("dashboard"))

        return redirect(url_for("review_detail", review_id=review_id))

    review = db.get_review_by_id(review_id)  # Refresh
    return render_template("review_detail.html", review=review)


# ── Webhook Gateway for 24/7 Partner Integrations (Make.com / Zapier) ──
@app.route("/api/webhook/review-received", methods=["POST"])
def webhook_review_received():
    """
    Receives incoming review from verified partner (e.g., Make.com).
    - Stores the review in database.
    - Runs Groq to draft an empathetic response.
    - If 4-5 stars: Returns draft directly to partner so partner can post immediately.
    - If 1-3 stars: Pushes Telegram notification for human review, holds for dashboard approval.
    """
    if not check_webhook_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    review_id = str(data.get("review_id", "")).strip()
    reviewer_name = str(data.get("reviewer_name", "Guest")).strip()
    
    raw_rating = data.get("star_rating", 5)
    star_map = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
    if isinstance(raw_rating, str) and raw_rating.strip().upper() in star_map:
        star_rating = star_map[raw_rating.strip().upper()]
    else:
        try:
            star_rating = int(str(raw_rating).strip())
        except (ValueError, TypeError):
            star_rating = 5

    comment = str(data.get("comment", "")).strip()
    review_time = str(data.get("review_time", "")).strip() or datetime.now(timezone.utc).isoformat()


    if not review_id:
        return jsonify({"ok": False, "error": "Missing review_id"}), 400

    # Detect existing owner reply in all possible formats from partner/Google
    existing_reply = ""
    if data.get("existing_reply"):
        existing_reply = str(data.get("existing_reply")).strip()
    elif isinstance(data.get("reviewReply"), dict):
        existing_reply = str(data.get("reviewReply", {}).get("comment", "")).strip()
    elif isinstance(data.get("review_reply"), dict):
        existing_reply = str(data.get("review_reply", {}).get("comment", "")).strip()

    # Normalize empty/null template strings from automation platforms
    if existing_reply.lower() in ("none", "null", "undefined", '""', "''"):
        existing_reply = ""

    has_reply_flag = False
    if "has_reply" in data:
        raw_hr = str(data.get("has_reply")).strip().lower()
        if raw_hr in ("true", "1", "yes"):
            has_reply_flag = True

    # Check if review already exists in our database
    existing = db.get_review_by_id(review_id)
    if existing:
        # If it was already replied / posted, NEVER re-reply or edit
        if existing.get("status") == "posted" or existing.get("approved_reply") or existing_reply or has_reply_flag:
            if existing_reply and not existing.get("approved_reply"):
                db.update_review(
                    review_id,
                    status="posted",
                    ai_draft=existing_reply,
                    approved_reply=existing_reply,
                    posted_at=existing.get("posted_at") or review_time
                )
            return jsonify({
                "ok": True,
                "action": "already_replied",
                "message": "Review already exists and has an owner reply. Skipped to prevent re-replying or editing.",
                "review_id": review_id,
                "status": "posted"
            }), 200

        return jsonify({
            "ok": True,
            "action": "pending",
            "message": "Review already queued in system",
            "review_id": review_id,
            "status": existing.get("status")
        }), 200

    # Store in database
    db.insert_review(review_id, reviewer_name, star_rating, comment, review_time)

    # If the review ALREADY has an owner reply on Google Maps, preserve history & DO NOT REPLY
    if existing_reply or has_reply_flag:
        reply_content = existing_reply if existing_reply else "(Owner replied on Google)"
        db.update_review(
            review_id,
            status="posted",
            ai_draft=reply_content,
            approved_reply=reply_content,
            posted_at=review_time
        )
        return jsonify({
            "ok": True,
            "action": "already_replied",
            "review_id": review_id,
            "message": "Historical review and existing owner reply preserved. Skipped to prevent re-replying or editing."
        }), 200

    # Only truly unreplied reviews proceed to AI generation
    try:
        draft = ai_client.generate_reply(reviewer_name, star_rating, comment)
    except Exception as e:
        db.update_review(review_id, error_message=str(e))
        return jsonify({"ok": False, "error": f"AI generation failed: {e}"}), 500


    if star_rating >= AUTO_MIN_STARS:
        # Mark as posted and return reply text for partner to publish
        db.update_review(
            review_id,
            status="posted",
            ai_draft=draft,
            approved_reply=draft,
            posted_at=datetime.now(timezone.utc).isoformat()
        )
        notifier.notify_auto_posted(reviewer_name, star_rating, draft)
        return jsonify({
            "ok": True,
            "action": "reply",
            "review_id": review_id,
            "reviewer_name": reviewer_name,
            "star_rating": star_rating,
            "reply_text": draft
        }), 200
    else:
        # Save draft, notify Telegram, hold for manager approval
        db.update_review(
            review_id,
            status="ai_drafted",
            ai_draft=draft
        )
        notifier.alert_low_star_review(reviewer_name, star_rating, comment, draft, review_id)
        return jsonify({
            "ok": True,
            "action": "hold_for_approval",
            "review_id": review_id,
            "message": "Sent to Telegram and dashboard for manager approval",
            "draft_preview": draft
        }), 200


@app.route("/api/webhook/pending-replies", methods=["GET"])
def webhook_pending_replies():
    """Returns approved replies awaiting publication by partner scenario."""
    if not check_webhook_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    awaiting = db.get_awaiting_approval()
    approved_items = [
        {
            "review_id": r["review_id"],
            "reviewer_name": r["reviewer_name"],
            "star_rating": r["star_rating"],
            "reply_text": r["approved_reply"]
        }
        for r in awaiting if r.get("approved_reply")
    ]
    return jsonify({"ok": True, "count": len(approved_items), "replies": approved_items}), 200


@app.route("/api/webhook/mark-posted", methods=["POST"])
def webhook_mark_posted():
    """Called by partner once it finishes posting an approved reply."""
    if not check_webhook_auth():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    review_id = str(data.get("review_id", "")).strip()
    if not review_id:
        return jsonify({"ok": False, "error": "Missing review_id"}), 400

    db.update_review(
        review_id,
        status="posted",
        posted_at=datetime.now(timezone.utc).isoformat()
    )
    return jsonify({"ok": True, "review_id": review_id, "status": "posted"}), 200


# ── Manual trigger for testing ────────────────────────
@app.route("/api/run-now", methods=["POST"])
@login_required
def run_now():
    try:
        worker.fetch_and_store()
        worker.process_pending()
        return jsonify({"ok": True, "msg": "Fetch + process triggered"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

