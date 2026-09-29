import sqlite3
from datetime import datetime, timezone

DB_PATH = "reviews.db"

def get_connection():
    """
    Returns an SQLite connection configured for concurrent 24/7 operation.
    Enables WAL mode to allow concurrent readers and writers,
    and sets a 30-second busy timeout to eliminate 'database is locked' errors.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn

def init_db():
    with get_connection() as conn:
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

def review_exists(review_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM reviews WHERE review_id = ?", (review_id,))
        return c.fetchone() is not None

def insert_review(review_id, reviewer_name, star_rating, comment, review_time):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO reviews
            (review_id, reviewer_name, star_rating, comment, review_time, fetched_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (
            review_id, reviewer_name, star_rating,
            comment, review_time,
            datetime.now(timezone.utc).isoformat()
        ))

def get_pending_reviews():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM reviews WHERE status = 'pending'")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_awaiting_approval():
    """1-3 star reviews with AI draft, waiting for your Telegram approval."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM reviews WHERE status = 'ai_drafted'")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def update_review(review_id, **fields):
    """Generic update — pass any column=value pairs."""
    if not fields:
        return
    with get_connection() as conn:
        c = conn.cursor()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [review_id]
        c.execute(f"UPDATE reviews SET {set_clause} WHERE review_id = ?", values)

def get_all_reviews(limit=100):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM reviews
        ORDER BY review_time DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_review_by_id(review_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM reviews WHERE review_id = ?", (review_id,))
    row = c.fetchone()
    res = dict(row) if row else None
    conn.close()
    return res
