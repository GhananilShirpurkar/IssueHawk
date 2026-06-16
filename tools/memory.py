import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "memory.db")

_initialized = False

def init_db():
    """Initialize the database and ensure the issues table exists."""
    global _initialized
    if _initialized:
        return
        
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id TEXT,
            url TEXT PRIMARY KEY,
            title TEXT,
            repo TEXT,
            status TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    _initialized = True
    logger.info("SQLite Database initialized at %s", DB_PATH)

def is_duplicate(issue_url: str) -> bool:
    """Check if the issue has already been processed/emailed."""
    init_db()  # Ensure DB is initialized
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM issues WHERE url = ?", (issue_url,))
    row = cursor.fetchone()
    conn.close()
    
    # If the issue exists and has been 'emailed' or 'processed', treat as duplicate
    if row:
        return row[0] in ("processed", "emailed")
    return False

def mark_as_processed(issue: dict, status: str = "processed"):
    """Mark an issue as processed/emailed in the database."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    issue_id = str(issue.get("id", ""))
    url = issue.get("url")
    title = issue.get("title", "")
    repo = issue.get("repo", "")
    
    if not url:
        return
        
    try:
        cursor.execute("""
            INSERT INTO issues (id, url, title, repo, status, processed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                status = excluded.status,
                processed_at = excluded.processed_at
        """, (issue_id, url, title, repo, status, datetime.now()))
        conn.commit()
    except Exception as e:
        logger.error("Failed to write to database: %s", e)
    finally:
        conn.close()
