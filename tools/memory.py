import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "memory.db")

_initialized_paths = set()

def init_db(target_db_path: Optional[str] = None):
    """Initialize the database and run schema migrations if necessary."""
    db_file = os.path.abspath(target_db_path or DB_PATH)
    
    if db_file in _initialized_paths:
        return
        
    os.makedirs(os.path.dirname(db_file), exist_ok=True)
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # 1. Ensure table exists
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
    
    # 2. Inspect existing columns to apply migrations safely
    cursor.execute("PRAGMA table_info(issues)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    migrations = [
        ("score", "INTEGER DEFAULT 0"),
        ("explanation", "TEXT DEFAULT ''"),
        ("implementation_hint", "TEXT DEFAULT ''"),
        ("ttl_days", "INTEGER DEFAULT 14")
    ]
    
    for col_name, col_def in migrations:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE issues ADD COLUMN {col_name} {col_def}")
                logger.debug(f"Migrated memory.db: Added column '{col_name}'")
            except sqlite3.OperationalError as e:
                logger.debug(f"Column '{col_name}' migration notice: {e}")
                
    conn.commit()
    conn.close()
    
    _initialized_paths.add(db_file)
    logger.debug("SQLite Database initialized at %s", db_file)

def is_duplicate(issue_url: str, target_db_path: Optional[str] = None) -> bool:
    """
    Check if the issue should be skipped:
    - If status == 'emailed': permanently duplicate.
    - If status in ('skipped_low_score', 'claimed', 'inactive_repo'):
      duplicate if evaluated within ttl_days (default 14 days).
    """
    db_file = target_db_path or DB_PATH
    init_db(db_file)
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, processed_at, ttl_days 
        FROM issues 
        WHERE url = ?
    """, (issue_url,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return False
        
    status, processed_at_str, ttl_days = row[0], row[1], row[2] or 14
    
    # Emailed issues are permanently deduplicated
    if status == "emailed":
        return True
        
    # Check TTL for cached rejections
    if status in ("skipped_low_score", "claimed", "inactive_repo", "processed"):
        if not processed_at_str:
            return True
            
        try:
            # Parse datetime string from SQLite (handles ISO or standard format)
            if "T" in processed_at_str:
                processed_at = datetime.fromisoformat(processed_at_str)
            else:
                # Format: YYYY-MM-DD HH:MM:SS.mmmmmm or YYYY-MM-DD HH:MM:SS
                base_fmt = "%Y-%m-%d %H:%M:%S"
                clean_str = processed_at_str.split(".")[0]
                processed_at = datetime.strptime(clean_str, base_fmt)
                
            expiry_date = processed_at + timedelta(days=ttl_days)
            if datetime.now() < expiry_date:
                return True # Still within negative cache TTL
            else:
                return False # Expired, allow re-evaluation
        except Exception as e:
            logger.debug(f"Date parsing exception for {processed_at_str}: {e}")
            return True # In doubt, don't spam
            
    return False

def record_evaluation(
    issue: dict, 
    status: str, 
    score: int = 0, 
    explanation: str = "", 
    hint: str = "",
    ttl_days: int = 14,
    target_db_path: Optional[str] = None
):
    """Save an evaluated or triaged issue to the persistent memory cache."""
    db_file = target_db_path or DB_PATH
    init_db(db_file)
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    issue_id = str(issue.get("id", ""))
    url = issue.get("url")
    title = issue.get("title", "")
    repo = issue.get("repo", "")
    
    if not url:
        conn.close()
        return
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cursor.execute("""
            INSERT INTO issues (id, url, title, repo, status, processed_at, score, explanation, implementation_hint, ttl_days)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                status = excluded.status,
                processed_at = excluded.processed_at,
                score = excluded.score,
                explanation = excluded.explanation,
                implementation_hint = excluded.implementation_hint,
                ttl_days = excluded.ttl_days
        """, (issue_id, url, title, repo, status, now_str, score, explanation, hint, ttl_days))
        conn.commit()
    except Exception as e:
        logger.error("Failed to write to database: %s", e)
    finally:
        conn.close()

def mark_as_processed(issue: dict, status: str = "processed", target_db_path: Optional[str] = None):
    """Backward-compatible helper to mark an issue as processed or emailed."""
    record_evaluation(
        issue=issue,
        status=status,
        score=issue.get("score", 0),
        explanation=issue.get("explanation", ""),
        hint=issue.get("implementation_hint", ""),
        target_db_path=target_db_path
    )

def get_memory_stats(target_db_path: Optional[str] = None) -> Dict[str, Any]:
    """Return summary statistics of tracked issues in memory."""
    db_file = target_db_path or DB_PATH
    init_db(db_file)
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM issues")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT status, COUNT(*) FROM issues GROUP BY status")
    by_status = dict(cursor.fetchall())
    
    conn.close()
    
    return {
        "total_tracked": total,
        "emailed": by_status.get("emailed", 0),
        "skipped_low_score": by_status.get("skipped_low_score", 0),
        "claimed": by_status.get("claimed", 0),
        "inactive_repo": by_status.get("inactive_repo", 0),
        "processed": by_status.get("processed", 0),
        "db_path": db_file
    }
