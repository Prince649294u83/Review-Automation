import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "reviews.db")
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def is_postgres():
    return bool(DATABASE_URL)

def get_connection():
    """
    Returns an SQLite connection by default, or PostgreSQL connection
    when DATABASE_URL is set in environment (for 100% persistent cloud storage).
    """
    if is_postgres():
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

def init_db():
    conn = get_connection()
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
    conn = get_connection()
    c = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    c.execute(f"SELECT 1 FROM reviews WHERE review_id = {placeholder}", (review_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def insert_review(review_id, reviewer_name, star_rating, comment, review_time):
    conn = get_connection()
    c = conn.cursor()
    fetched_at = datetime.now(timezone.utc).isoformat()
    if is_postgres():
        query = """
            INSERT INTO reviews
            (review_id, reviewer_name, star_rating, comment, review_time, fetched_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            ON CONFLICT (review_id) DO NOTHING
        """
    else:
        query = """
            INSERT OR IGNORE INTO reviews
            (review_id, reviewer_name, star_rating, comment, review_time, fetched_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """
    c.execute(query, (review_id, reviewer_name, star_rating, comment, review_time, fetched_at))
    conn.commit()
    conn.close()

def get_pending_reviews():
    conn = get_connection()
    if is_postgres():
        from psycopg2.extras import RealDictCursor
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT * FROM reviews WHERE status = 'pending'")
        rows = [dict(r) for r in c.fetchall()]
    else:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM reviews WHERE status = 'pending'")
        rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_awaiting_approval():
    """1-3 star reviews with AI draft, waiting for your Telegram approval."""
    conn = get_connection()
    if is_postgres():
        from psycopg2.extras import RealDictCursor
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT * FROM reviews WHERE status = 'ai_drafted'")
        rows = [dict(r) for r in c.fetchall()]
    else:
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
    conn = get_connection()
    c = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    set_clause = ", ".join(f"{k} = {placeholder}" for k in fields)
    values = list(fields.values()) + [review_id]
    c.execute(f"UPDATE reviews SET {set_clause} WHERE review_id = {placeholder}", values)
    conn.commit()
    conn.close()

def get_all_reviews(limit=100):
    conn = get_connection()
    placeholder = "%s" if is_postgres() else "?"
    if is_postgres():
        from psycopg2.extras import RealDictCursor
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute(f"SELECT * FROM reviews ORDER BY review_time DESC LIMIT {placeholder}", (limit,))
        rows = [dict(r) for r in c.fetchall()]
    else:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f"SELECT * FROM reviews ORDER BY review_time DESC LIMIT {placeholder}", (limit,))
        rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_review_by_id(review_id):
    conn = get_connection()
    placeholder = "%s" if is_postgres() else "?"
    if is_postgres():
        from psycopg2.extras import RealDictCursor
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute(f"SELECT * FROM reviews WHERE review_id = {placeholder}", (review_id,))
        row = c.fetchone()
        res = dict(row) if row else None
    else:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f"SELECT * FROM reviews WHERE review_id = {placeholder}", (review_id,))
        row = c.fetchone()
        res = dict(row) if row else None
    conn.close()
    return res
