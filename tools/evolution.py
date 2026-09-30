"""
tools/evolution.py

Developer Progression and Evolution Engine for IssueHawk.
Tracks developer experience (XP), milestone graduations, and GitHub contribution sync
to transition users from "good first issue" starters to LFX / GSoC mentorship-ready contributors.
"""

import os
import logging
import requests
from typing import Dict, Any, Optional, Tuple
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tools.memory import (
    get_progress_record,
    update_progress_record,
    save_completed_contribution,
    get_completed_contributions,
    record_evaluation
)
from tools.profile import load_profile, DeveloperProfile

logger = logging.getLogger(__name__)

TIER_ORDER = ["apprentice", "contributor", "core_contributor", "mentorship_ready"]

TIER_CONFIG = {
    "apprentice": {
        "title": "Level 1: Apprentice Contributor",
        "badge": "🌱 APPRENTICE",
        "description": "Building momentum with good first issues, setup docs, and small patches.",
        "min_xp": 0,
        "next_tier": "contributor",
        "next_xp": 150,
        "color": "yellow"
    },
    "contributor": {
        "title": "Level 2: Active Contributor",
        "badge": "⚡ CONTRIBUTOR",
        "description": "Shipping real bugfixes, features, and non-trivial codebase contributions.",
        "min_xp": 150,
        "next_tier": "core_contributor",
        "next_xp": 500,
        "color": "cyan"
    },
    "core_contributor": {
        "title": "Level 3: Core Subsystem Engineer",
        "badge": "🔥 CORE CONTRIBUTOR",
        "description": "Tackling core features, concurrency, performance, and multi-file architecture.",
        "min_xp": 500,
        "next_tier": "mentorship_ready",
        "next_xp": 1200,
        "color": "magenta"
    },
    "mentorship_ready": {
        "title": "Level 4: LFX / GSoC Mentorship Candidate",
        "badge": "🏆 MENTORSHIP READY",
        "description": "Proven architectural capability ready for premier programs (LFX, GSoC, CNCF, Apache).",
        "min_xp": 1200,
        "next_tier": None,
        "next_xp": 1200,
        "color": "green"
    }
}

def determine_tier_from_xp(xp: int) -> str:
    """Calculates appropriate tier based on accumulated XP points."""
    if xp >= 1200:
        return "mentorship_ready"
    elif xp >= 500:
        return "core_contributor"
    elif xp >= 150:
        return "contributor"
    return "apprentice"

def calculate_xp_award(difficulty: str = "intermediate", impact_score: int = 6) -> int:
    """Calculates XP awarded for resolving an issue."""
    diff = (difficulty or "intermediate").lower()
    base_xp = 50
    if diff == "advanced":
        base_xp = 200
    elif diff == "intermediate":
        base_xp = 120
    else:
        base_xp = 60

    multiplier = max(1, min(impact_score, 10))
    return base_xp + (multiplier * 10)

def get_developer_status(profile: Optional[DeveloperProfile] = None, target_db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves full developer progress, XP breakdown, and graduation thresholds."""
    dev_profile = profile or load_profile()
    rec = get_progress_record(target_db_path=target_db_path)
    
    current_tier = rec["tier"]
    xp = rec["xp"]

    # If profile explicitly specifies a higher starting tier, initialize/sync to that tier
    if dev_profile.tier in TIER_ORDER and TIER_ORDER.index(dev_profile.tier) > TIER_ORDER.index(current_tier):
        current_tier = dev_profile.tier
        tier_base_xp = TIER_CONFIG[current_tier]["min_xp"]
        if xp < tier_base_xp:
            xp = tier_base_xp
            update_progress_record(
                tier=current_tier,
                xp=xp,
                completed_count=rec["completed_count"],
                github_username=rec["github_username"] or dev_profile.github_username or "",
                synced_pr_count=rec["synced_pr_count"],
                target_db_path=target_db_path
            )
        
    tier_info = TIER_CONFIG.get(current_tier, TIER_CONFIG["contributor"])
    next_tier_key = tier_info["next_tier"]
    next_xp = tier_info["next_xp"]
    
    # Calculate progress % to next tier
    if next_tier_key:
        curr_min = tier_info["min_xp"]
        span = next_xp - curr_min
        earned_in_span = max(0, xp - curr_min)
        progress_pct = min(100, int((earned_in_span / span) * 100)) if span > 0 else 100
        xp_needed = max(0, next_xp - xp)
    else:
        progress_pct = 100
        xp_needed = 0

    return {
        "tier": current_tier,
        "title": tier_info["title"],
        "badge": tier_info["badge"],
        "color": tier_info["color"],
        "description": tier_info["description"],
        "xp": xp,
        "next_tier": next_tier_key,
        "next_xp": next_xp,
        "xp_needed": xp_needed,
        "progress_pct": progress_pct,
        "completed_count": rec["completed_count"],
        "github_username": rec["github_username"] or dev_profile.github_username or "",
        "synced_pr_count": rec["synced_pr_count"],
        "track": dev_profile.track,
        "target_foundations": dev_profile.target_foundations,
    }

def record_completed_issue(
    url: str,
    title: str = "",
    repo: str = "",
    difficulty: str = "intermediate",
    impact_score: int = 7,
    profile: Optional[DeveloperProfile] = None,
    target_db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Marks an issue as completed, awards XP, logs contribution, and checks for graduation.
    """
    dev_profile = profile or load_profile()
    rec = get_progress_record(target_db_path=target_db_path)
    old_tier = rec["tier"]
    old_xp = rec["xp"]

    if dev_profile.tier in TIER_ORDER and TIER_ORDER.index(dev_profile.tier) > TIER_ORDER.index(old_tier):
        old_tier = dev_profile.tier
        if old_xp < TIER_CONFIG[old_tier]["min_xp"]:
            old_xp = TIER_CONFIG[old_tier]["min_xp"]
    
    xp_gained = calculate_xp_award(difficulty=difficulty, impact_score=impact_score)
    new_xp = old_xp + xp_gained
    new_count = rec["completed_count"] + 1
    
    # Check graduation
    new_tier = determine_tier_from_xp(new_xp) if dev_profile.auto_graduate else old_tier
    if TIER_ORDER.index(old_tier) > TIER_ORDER.index(new_tier):
        new_tier = old_tier # Never demote below current tier
        
    graduated = new_tier != old_tier
    
    # Persist
    save_completed_contribution(
        url=url,
        title=title or url,
        repo=repo or "github",
        tier=new_tier,
        xp_awarded=xp_gained,
        target_db_path=target_db_path
    )
    
    update_progress_record(
        tier=new_tier,
        xp=new_xp,
        completed_count=new_count,
        github_username=rec["github_username"] or dev_profile.github_username or "",
        synced_pr_count=rec["synced_pr_count"],
        target_db_path=target_db_path
    )
    
    # Also update issue status in memory
    record_evaluation(
        issue={"url": url, "title": title, "repo": repo, "id": ""},
        status="completed",
        score=10,
        explanation=f"Completed contribution (+{xp_gained} XP)",
        target_db_path=target_db_path
    )
    
    return {
        "url": url,
        "xp_gained": xp_gained,
        "total_xp": new_xp,
        "old_tier": old_tier,
        "new_tier": new_tier,
        "graduated": graduated,
        "completed_count": new_count
    }

def sync_github_activity(
    username: Optional[str] = None,
    token: Optional[str] = None,
    profile: Optional[DeveloperProfile] = None,
    target_db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Syncs user's merged PRs from GitHub API to award XP and update progression.
    """
    dev_profile = profile or load_profile()
    gh_user = username or dev_profile.github_username
    if not gh_user:
        return {
            "success": False,
            "message": "No GitHub username configured. Set github_username in profile.yaml or pass --username."
        }
        
    auth_token = token or os.getenv("ACCESS_TOKEN_GITHUB") or os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
        
    query = f"author:{gh_user} type:pr is:merged"
    url = f"https://api.github.com/search/issues?q={query}&per_page=100"
    
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if not resp.ok:
            return {
                "success": False,
                "message": f"GitHub API error ({resp.status_code}): {resp.text[:150]}"
            }
        data = resp.json()
        total_merged_prs = data.get("total_count", 0)
    except Exception as e:
        logger.error(f"GitHub PR sync failed: {e}")
        return {"success": False, "message": f"Failed to contact GitHub: {e}"}
        
    rec = get_progress_record(target_db_path=target_db_path)
    previous_pr_count = rec["synced_pr_count"]
    new_prs = max(0, total_merged_prs - previous_pr_count)
    
    # Award 150 XP per merged PR
    xp_boost = new_prs * 150
    updated_xp = rec["xp"] + xp_boost
    old_tier = rec["tier"]
    updated_tier = determine_tier_from_xp(updated_xp) if dev_profile.auto_graduate else old_tier
    if TIER_ORDER.index(old_tier) > TIER_ORDER.index(updated_tier):
        updated_tier = old_tier
        
    update_progress_record(
        tier=updated_tier,
        xp=updated_xp,
        completed_count=rec["completed_count"] + new_prs,
        github_username=gh_user,
        synced_pr_count=total_merged_prs,
        target_db_path=target_db_path
    )
    
    return {
        "success": True,
        "username": gh_user,
        "total_merged_prs": total_merged_prs,
        "new_prs": new_prs,
        "xp_boost": xp_boost,
        "total_xp": updated_xp,
        "tier": updated_tier,
        "graduated": updated_tier != old_tier
    }

def format_progress_panel(status: Dict[str, Any]) -> Panel:
    """Builds a polished Rich Panel displaying the developer's evolution."""
    tier_badge = status["badge"]
    xp = status["xp"]
    pct = status["progress_pct"]
    bar_width = 30
    filled = int(bar_width * (pct / 100))
    bar = "█" * filled + "░" * (bar_width - filled)
    
    foundations = ", ".join([f.upper() for f in status.get("target_foundations", [])])
    
    body = (
        f"[bold {status['color']}]{tier_badge}[/bold {status['color']}]  •  [bold white]{status['title']}[/bold white]\n"
        f"[dim]{status['description']}[/dim]\n\n"
        f"[bold white]Progress to Next Level:[/bold white]\n"
        f"[{status['color']}]{bar}[/{status['color']}] [bold white]{pct}%[/bold white] "
        f"([cyan]{xp}[/cyan] / {status['next_xp']} XP" + (f", [yellow]{status['xp_needed']} XP needed[/yellow])" if status['next_tier'] else ", Max Tier Achieved)") + "\n\n"
        f"• [bold white]Completed Issues:[/bold white] [green]{status['completed_count']}[/green]\n"
        f"• [bold white]GitHub Merged PRs:[/bold white] [cyan]{status['synced_pr_count']}[/cyan] " + (f"(@{status['github_username']})" if status['github_username'] else "([dim]Set github_username in profile.yaml to sync[/dim])") + "\n"
        f"• [bold white]Career Target Track:[/bold white] [bold yellow]{status['track'].replace('_', ' ').title()}[/bold yellow]\n"
        f"• [bold white]Target Foundations:[/bold white] [magenta]{foundations}[/magenta]\n\n"
        f"[dim italic]Tip: Complete an issue with `issuehawk --complete <issue-url>` to gain XP and graduate your tier.[/dim italic]"
    )
    return Panel(body, title="🦅 [bold]IssueHawk Developer Progression[/bold]", border_style=status["color"], padding=(1, 2))
