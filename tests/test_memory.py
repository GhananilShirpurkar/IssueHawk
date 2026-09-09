import os
import tempfile
import sqlite3
from datetime import datetime, timedelta
import pytest
from tools.memory import init_db, is_duplicate, record_evaluation, get_memory_stats

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)

def test_database_initialization(temp_db):
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(issues)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    
    expected_cols = {"id", "url", "title", "repo", "status", "processed_at", "score", "explanation", "implementation_hint", "ttl_days"}
    assert expected_cols.issubset(columns)

def test_emailed_issue_permanent_deduplication(temp_db):
    issue = {
        "id": "101",
        "url": "https://github.com/test/repo/issues/1",
        "title": "Emailed Test Issue",
        "repo": "test/repo"
    }
    
    assert not is_duplicate(issue["url"], target_db_path=temp_db)
    
    record_evaluation(issue, status="emailed", score=9, explanation="Great fit", target_db_path=temp_db)
    
    assert is_duplicate(issue["url"], target_db_path=temp_db)

def test_negative_cache_ttl(temp_db):
    issue = {
        "id": "102",
        "url": "https://github.com/test/repo/issues/2",
        "title": "Low Score Issue",
        "repo": "test/repo"
    }
    
    # Store with status 'skipped_low_score' and 14-day TTL
    record_evaluation(issue, status="skipped_low_score", score=3, ttl_days=14, target_db_path=temp_db)
    
    # Should be considered duplicate right now (within TTL)
    assert is_duplicate(issue["url"], target_db_path=temp_db)
    
    # Manually backdate the processed_at to 20 days ago
    conn = sqlite3.connect(temp_db)
    past_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE issues SET processed_at = ? WHERE url = ?", (past_date, issue["url"]))
    conn.commit()
    conn.close()
    
    # Now that TTL expired, is_duplicate should be False (eligible for re-evaluation)
    assert not is_duplicate(issue["url"], target_db_path=temp_db)

def test_memory_statistics(temp_db):
    record_evaluation({"url": "http://1", "title": "A"}, status="emailed", target_db_path=temp_db)
    record_evaluation({"url": "http://2", "title": "B"}, status="skipped_low_score", target_db_path=temp_db)
    record_evaluation({"url": "http://3", "title": "C"}, status="claimed", target_db_path=temp_db)
    
    stats = get_memory_stats(target_db_path=temp_db)
    assert stats["total_tracked"] == 3
    assert stats["emailed"] == 1
    assert stats["skipped_low_score"] == 1
    assert stats["claimed"] == 1
