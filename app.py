import os
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, redirect, url_for,
    request, session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

import db
import worker
import ai_client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change_this_secret")

PWD_HASH = generate_password_hash(os.getenv("APP_PASSWORD", "admin"))

# ── Start DB and scheduler on launch ─────────────────
db.init_db()
scheduler = worker.start_scheduler()


# ── Auth decorator ────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


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
                # Save approved text — worker will post it within 10 min
                db.update_review(
                    review_id,
                    approved_reply = edited,
                    status         = "ai_drafted"
                )
                flash("✅ Reply approved! Will post within 10 minutes.")

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
    app.run(host="0.0.0.0", port=5000, debug=False)
