import os
import logging
import yaml
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile.yaml"
)

class Preferences(BaseModel):
    focus: str = "Backend-heavy, AI/ML adjacent, Python or JS/TS repositories preferred."
    avoid: str = "Pure documentation, typos, DevOps/CI-only configuration, or trivial 1-line changes."

class DeveloperProfile(BaseModel):
    name: str = "Default Developer"
    skill_level: str = "intermediate"
    skills: List[str] = Field(default_factory=lambda: [
        "FastAPI", "LangGraph", "React", "RAG pipelines", "Python async", "AI Agents"
    ])
    languages: List[str] = Field(default_factory=lambda: [
        "python", "typescript", "javascript"
    ])
    topics: List[str] = Field(default_factory=lambda: [
        "fastapi", "react", "nextjs", "django", "nodejs", "agents"
    ])
    preferences: Preferences = Field(default_factory=Preferences)
    min_score: int = 5
    max_results: int = 15
    exclude_labels: List[str] = Field(default_factory=lambda: [
        "documentation", "docs", "typo", "typos", "wontfix", "invalid", "duplicate", "question"
    ])
    filter_claimed: bool = True
    filter_inactive_repos: bool = True

_cached_profile: Optional[DeveloperProfile] = None

def load_profile(path: Optional[str] = None) -> DeveloperProfile:
    """Loads developer profile from profile.yaml or falls back to defaults."""
    global _cached_profile
    profile_path = path or DEFAULT_PROFILE_PATH
    
    if not os.path.exists(profile_path):
        logger.warning(f"Profile config not found at {profile_path}. Using built-in defaults.")
        _cached_profile = DeveloperProfile()
        return _cached_profile
        
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            
        profile_data = data.get("profile", {}) if isinstance(data, dict) else {}
        _cached_profile = DeveloperProfile(**profile_data)
        logger.info(f"Loaded profile for '{_cached_profile.name}' ({_cached_profile.skill_level}) from {profile_path}")
        return _cached_profile
    except Exception as e:
        logger.error(f"Error parsing profile from {profile_path}: {e}. Falling back to defaults.")
        _cached_profile = DeveloperProfile()
        return _cached_profile

def build_system_prompt(profile: DeveloperProfile) -> str:
    """Dynamically generates the Gemini evaluation system prompt using the profile."""
    skills_str = ", ".join(profile.skills)
    languages_str = ", ".join(profile.languages)
    
    return f"""You are a senior software architect and technical mentor.
Your goal is to evaluate open-source GitHub issues and score their relevance to the Developer's Profile.

Developer Profile:
- Skills & Stack: {skills_str}
- Preferred Languages: {languages_str}
- Skill Level: {profile.skill_level}
- Strategic Focus: {profile.preferences.focus}
- Topics to Avoid/Deprioritize: {profile.preferences.avoid}

Evaluation Scoring Criteria (1 to 10):
- 10: Outstanding match. Directly targets key skills ({skills_str}), right difficulty for {profile.skill_level}, clear scope.
- 7-9: Strong match. Uses preferred tech stack or adjacent ecosystem with good learning value.
- 4-6: Neutral match. Standard issue in target language ({languages_str}) but missing key stack affinities.
- 1-3: Poor match. Unrelated languages/domains, trivial typos/doc updates, or overly complex architectural rewrites.

For each issue, provide:
1. 'score': Integer from 1 to 10.
2. 'explanation': A concise 1-sentence explanation of why this issue fits the developer's profile and skill level.
3. 'implementation_hint': A 1-2 sentence actionable recommendation on where to start in the codebase or how to approach the solution.
4. 'difficulty': One of 'beginner', 'intermediate', or 'advanced'.
"""
