import os
import logging
import yaml
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile.yaml"
)

# Map legacy skill_level to modern progression tier
TIER_MAPPING = {
    "beginner": "apprentice",
    "intermediate": "contributor",
    "advanced": "core_contributor",
    "expert": "mentorship_ready",
}

class Preferences(BaseModel):
    focus: str = "Subsystem architecture, high-impact core features, performance optimizations, and LFX/GSoC portfolio issues."
    avoid: str = "Pure documentation, typos, DevOps/CI-only configuration, or trivial 1-line changes."

class DeveloperProfile(BaseModel):
    name: str = "Growth Developer"
    github_username: Optional[str] = None
    skill_level: str = "intermediate"
    tier: str = "contributor"  # apprentice | contributor | core_contributor | mentorship_ready
    auto_graduate: bool = True
    track: str = "lfx_gsoc_ready"  # lfx_gsoc_ready | core_contributor | general_open_source
    target_foundations: List[str] = Field(default_factory=lambda: [
        "cncf", "lfx", "apache", "gsoc"
    ])
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
    min_score: int = 6
    max_results: int = 15
    min_stars: int = 50
    exclude_labels: List[str] = Field(default_factory=lambda: [
        "documentation", "docs", "typo", "typos", "wontfix", "invalid", "duplicate", "question"
    ])
    filter_claimed: bool = True
    filter_inactive_repos: bool = True

    def model_post_init(self, __context):
        # Sync tier with skill_level if tier was not explicitly set or vice-versa
        if self.tier == "contributor" and self.skill_level in TIER_MAPPING:
            # Check if skill_level was specified differently
            if self.skill_level == "beginner":
                self.tier = "apprentice"
            elif self.skill_level == "advanced":
                self.tier = "core_contributor"
        elif self.tier in ("apprentice", "contributor", "core_contributor", "mentorship_ready"):
            # Ensure skill_level reflects tier for legacy components
            reverse_map = {
                "apprentice": "beginner",
                "contributor": "intermediate",
                "core_contributor": "advanced",
                "mentorship_ready": "advanced"
            }
            self.skill_level = reverse_map.get(self.tier, self.skill_level)

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
        logger.info(f"Loaded profile for '{_cached_profile.name}' [Tier: {_cached_profile.tier}] from {profile_path}")
        return _cached_profile
    except Exception as e:
        logger.error(f"Error parsing profile from {profile_path}: {e}. Falling back to defaults.")
        _cached_profile = DeveloperProfile()
        return _cached_profile

def build_system_prompt(profile: DeveloperProfile) -> str:
    """Dynamically generates the Gemini evaluation system prompt using the profile and High-Impact Portfolio Rubric."""
    skills_str = ", ".join(profile.skills)
    languages_str = ", ".join(profile.languages)
    foundations_str = ", ".join(profile.target_foundations)
    
    return f"""You are a distinguished open-source maintainer, Google Summer of Code (GSoC) mentor, and Linux Foundation (LFX) evaluator.
Your goal is to evaluate open-source GitHub issues and curate meaningful opportunities that will uplift the developer's engineering stature and technical portfolio.

Developer Profile:
- Skills & Stack: {skills_str}
- Preferred Languages: {languages_str}
- Progression Tier: {profile.tier} (Skill level: {profile.skill_level})
- Target Career Track: {profile.track}
- Target Foundations: {foundations_str}
- Strategic Focus: {profile.preferences.focus}
- Deprioritize/Avoid: {profile.preferences.avoid}

HIGH-IMPACT PORTFOLIO EVALUATION RUBRIC:
1. Architectural & Subsystem Depth:
   - Does this issue touch core business logic, concurrency, data structures, algorithms, or API design rather than trivial one-line fixes?
   - Favor multi-file logic, new capabilities, edge-case fixes, and core optimizations over cosmetic updates.
2. Mentorship & Portfolio Uplift (LFX / GSoC Readiness):
   - Would an LFX or GSoC mentor look at a PR resolving this issue and recognize serious engineering craftsmanship?
   - Issues with mentor/maintainer discussions and clear design boundaries score highest.
3. Developer Stack Affinity:
   - Strong alignment with developer's stack ({skills_str}) and languages ({languages_str}).

Scoring Guide (Overall Score: 1 to 10):
- 9-10: Exemplary Portfolio Opportunity. Directly touches core architecture/subsystems in target stack or premier foundation ({foundations_str}). Substantial portfolio uplift.
- 7-8: Solid Impact Contribution. Non-trivial bug fix, new feature module, or performance enhancement with clear learning value.
- 4-6: Marginal/Moderate. Routine issue or minor patch with limited portfolio uplift.
- 1-3: Poor / Reject. Trivial typos, doc-only changes, dependency bumps, or outside target tech stack.

Portfolio Impact Score (1 to 10):
- Rate the career and mentorship uplift value (1 = trivial 1-line typo/comment, 10 = headline portfolio piece / LFX-ready feature).

For each issue provide:
1. 'score': Integer 1 to 10.
2. 'impact_score': Integer 1 to 10 (Architectural depth & resume/mentorship uplift value).
3. 'portfolio_rationale': 1 concise sentence explaining the resume/portfolio uplift and mentorship readiness.
4. 'explanation': 1 concise sentence explaining why this issue matches the developer's stack and tier.
5. 'implementation_hint': 1-2 sentence actionable technical recommendation on where to start in the codebase or how to approach the solution.
6. 'difficulty': One of 'beginner', 'intermediate', or 'advanced'.
"""
