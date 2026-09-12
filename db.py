import sqlite3
from datetime import datetime

DB_PATH = "reviews.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            review_id       TEXT PRIMARY KEY,
            reviewer_name   TEXT,
            star_rating     INTEGER,
            comment         TEXT,
            review_time     TEXT,
            fetched_at      TEXT,
            status          TEXT DEFAULT 'pending',
            ai_draft        TEXT,
            approved_reply  TEXT,
            posted_at       TEXT,
            error_message   TEXT
        )
    """)
    conn.commit()
    conn.close()

def review_exists(review_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM reviews WHERE review_id = ?", (review_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def insert_review(review_id, reviewer_name, star_rating, comment, review_time):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO reviews
        (review_id, reviewer_name, star_rating, comment, review_time, fetched_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    """, (
        review_id, reviewer_name, star_rating,
        comment, review_time,
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()

def get_pending_reviews():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM reviews WHERE status = 'pending'")
    rows = c.fetchall()
    conn.close()
    return rows

def get_awaiting_approval():
    """1-3 star reviews with AI draft, waiting for your Telegram approval."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM reviews WHERE status = 'ai_drafted'")
    rows = c.fetchall()
    conn.close()
    return rows

def update_review(review_id, **fields):
    """Generic update — pass any column=value pairs."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [review_id]
    c.execute(f"UPDATE reviews SET {set_clause} WHERE review_id = ?", values)
    conn.commit()
    conn.close()

def get_all_reviews(limit=100):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM reviews
        ORDER BY review_time DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_review_by_id(review_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM reviews WHERE review_id = ?", (review_id,))
    row = c.fetchone()
    conn.close()
    return row
