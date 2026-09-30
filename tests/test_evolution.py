import os
import tempfile
import pytest
from tools.evolution import (
    determine_tier_from_xp,
    calculate_xp_award,
    record_completed_issue,
    get_developer_status,
    TIER_CONFIG
)
from tools.profile import DeveloperProfile
from tools.memory import get_completed_contributions

def test_determine_tier_from_xp():
    assert determine_tier_from_xp(0) == "apprentice"
    assert determine_tier_from_xp(149) == "apprentice"
    assert determine_tier_from_xp(150) == "contributor"
    assert determine_tier_from_xp(499) == "contributor"
    assert determine_tier_from_xp(500) == "core_contributor"
    assert determine_tier_from_xp(1199) == "core_contributor"
    assert determine_tier_from_xp(1200) == "mentorship_ready"
    assert determine_tier_from_xp(2500) == "mentorship_ready"

def test_calculate_xp_award():
    beginner_xp = calculate_xp_award(difficulty="beginner", impact_score=5)
    assert beginner_xp == 60 + 50
    
    advanced_high_impact = calculate_xp_award(difficulty="advanced", impact_score=9)
    assert advanced_high_impact == 200 + 90

def test_record_completed_issue_and_graduation():
    with tempfile.NamedTemporaryFile("w", suffix=".db", delete=False) as f:
        temp_db = f.name
        
    try:
        profile = DeveloperProfile(
            name="Testing Dev",
            tier="contributor",
            auto_graduate=True
        )
        
        # Initial status
        status = get_developer_status(profile=profile, target_db_path=temp_db)
        assert status["tier"] == "contributor"
        assert status["completed_count"] == 0
        
        # Complete issue 1
        res1 = record_completed_issue(
            url="https://github.com/kubernetes/kubernetes/issues/100",
            title="Fix container runtime race condition",
            repo="kubernetes/kubernetes",
            difficulty="advanced",
            impact_score=9,
            profile=profile,
            target_db_path=temp_db
        )
        assert res1["xp_gained"] == 290
        assert res1["completed_count"] == 1
        
        # Complete issue 2 (should graduate to core_contributor at >= 500 XP)
        res2 = record_completed_issue(
            url="https://github.com/apache/airflow/issues/200",
            title="Refactor DAG scheduler executor",
            repo="apache/airflow",
            difficulty="advanced",
            impact_score=8,
            profile=profile,
            target_db_path=temp_db
        )
        assert res2["completed_count"] == 2
        assert res2["total_xp"] >= 500
        assert res2["new_tier"] == "core_contributor"
        assert res2["graduated"] is True
        
        # Verify completed contributions are logged
        contribs = get_completed_contributions(target_db_path=temp_db)
        assert len(contribs) == 2
        assert contribs[0]["repo"] in ("kubernetes/kubernetes", "apache/airflow")
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)
