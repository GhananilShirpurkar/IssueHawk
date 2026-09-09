import os
import tempfile
import pytest
from tools.profile import load_profile, build_system_prompt, DeveloperProfile

def test_default_profile_loading():
    profile = load_profile()
    assert profile is not None
    assert "FastAPI" in profile.skills or len(profile.skills) > 0
    assert "python" in profile.languages
    assert profile.min_score >= 1
    assert profile.max_results >= 1

def test_custom_profile_yaml():
    yaml_content = """
profile:
  name: "Rust Systems Engineer"
  skill_level: "advanced"
  skills:
    - "Tokio"
    - "Axum"
    - "Async Rust"
  languages:
    - "rust"
  min_score: 7
  max_results: 5
  exclude_labels:
    - "good first issue"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name
        
    try:
        custom_profile = load_profile(temp_path)
        assert custom_profile.name == "Rust Systems Engineer"
        assert custom_profile.skill_level == "advanced"
        assert "Tokio" in custom_profile.skills
        assert custom_profile.min_score == 7
        assert custom_profile.max_results == 5
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def test_prompt_generation():
    profile = DeveloperProfile(
        name="Test Dev",
        skill_level="intermediate",
        skills=["FastAPI", "Postgres"],
        languages=["python"]
    )
    prompt = build_system_prompt(profile)
    assert "FastAPI" in prompt
    assert "Postgres" in prompt
    assert "python" in prompt
    assert "intermediate" in prompt
