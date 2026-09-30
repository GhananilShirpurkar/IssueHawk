"""
tools/github_api.py

Fetches open issues from the GitHub Search API and direct repository endpoints.
Supports dynamic tier labels, foundation-specific searches, and prestige organization filters.
"""

import os
import time
import logging
from typing import Optional, List, Dict
import requests
from dotenv import load_dotenv

from tools.registry import detect_foundation, get_tier_labels, get_foundation_repos

load_dotenv()

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/search/issues"
RESULTS_LIMIT = 30
RATE_LIMIT_PAUSE = 60  # seconds to wait when rate limit is hit


def _build_query(
    languages: list, 
    topics: list, 
    labels: Optional[list] = None, 
    min_stars: int = 0
) -> str:
    """
    Build a GitHub search query string from languages, topics, tier labels, and star filters.
    """
    parts = ["is:issue", "state:open", "no:assignee"]

    # Target tier labels (e.g. "help wanted", "enhancement", "lfx-mentorship")
    target_labels = labels or ["help wanted", "enhancement"]
    if target_labels:
        label_clauses = [f'label:"{lbl}"' for lbl in target_labels[:3]]
        parts.append(f"({' OR '.join(label_clauses)})")

    for lang in languages:
        parts.append(f"language:{lang}")

    for topic in topics[:5]:
        parts.append(f"topic:{topic}")

    if min_stars > 0:
        parts.append(f"stars:>={min_stars}")

    return " ".join(parts)


def fetch_github_issues(
    languages: list, 
    topics: list, 
    limit: int = 30,
    labels: Optional[list] = None,
    min_stars: int = 0
) -> list[dict]:
    """
    Fetch open issues from the GitHub Search API based on profile parameters.
    """
    token = os.getenv("ACCESS_TOKEN_GITHUB") or os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        logger.warning("Neither ACCESS_TOKEN_GITHUB nor GITHUB_TOKEN is set — requests will use unauthenticated rate limit.")

    query = _build_query(languages, topics, labels=labels, min_stars=min_stars)
    params = {
        "q": query,
        "per_page": min(limit, 50),
        "page": 1,
        "sort": "updated",
        "order": "desc",
    }

    logger.info("Fetching GitHub issues | query: %s", query)

    try:
        response = requests.get(GITHUB_API_URL, headers=headers, params=params, timeout=15)
    except requests.exceptions.RequestException as exc:
        logger.error("Network error fetching GitHub issues: %s", exc)
        return []

    # Rate-limit handling
    remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
    reset_at = int(response.headers.get("X-RateLimit-Reset", 0))

    if remaining == 0:
        wait = max(reset_at - int(time.time()), 0) + 1
        logger.warning("GitHub rate limit hit. Waiting %d seconds before retrying...", wait)
        time.sleep(min(wait, RATE_LIMIT_PAUSE))

        try:
            response = requests.get(GITHUB_API_URL, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as exc:
            logger.error("Network error on retry: %s", exc)
            return []

    if response.status_code == 403:
        logger.error("GitHub API returned 403. Check your token permissions or rate limit status.")
        return []

    if not response.ok:
        logger.error("GitHub API error %d: %s", response.status_code, response.text[:200])
        return []

    data = response.json()
    raw_items = data.get("items", [])
    logger.info("Retrieved %d issues from GitHub API search.", len(raw_items))

    issues = []
    for item in raw_items:
        repo_url = item.get("repository_url", "")
        repo = repo_url.removeprefix("https://api.github.com/repos/") if repo_url else ""
        foundation = detect_foundation(repo)

        issues.append({
            "id": item.get("id"),
            "title": item.get("title", ""),
            "url": item.get("html_url", ""),
            "repo": repo,
            "labels": [label["name"] for label in item.get("labels", []) if isinstance(label, dict) and "name" in label],
            "body": (item.get("body") or "").strip(),
            "assignees": [a.get("login") for a in item.get("assignees", []) if isinstance(a, dict) and "login" in a],
            "comments_count": item.get("comments", 0),
            "foundation": foundation,
            "source": "github_search",
        })

    return issues


def fetch_issues_from_repositories(
    repos: list[dict], 
    max_results: int = 30,
    labels: Optional[list] = None
) -> list[dict]:
    """
    Fetch open issues from a list of specific repositories with their custom labels.
    Uses GitHub's direct /repos/{owner}/{repo}/issues API (5,000 req/hr rate limit).
    """
    token = os.getenv("ACCESS_TOKEN_GITHUB") or os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    issues = []
    for item in repos[:20]:
        repo_name = item.get("repo")
        default_label = item.get("label", "help wanted")
        target_label = labels[0] if labels else default_label
        
        if not repo_name or "/" not in repo_name:
            continue
            
        repo_api_url = f"https://api.github.com/repos/{repo_name}/issues"
        params = {
            "labels": target_label,
            "state": "open",
            "per_page": 5,
            "sort": "updated",
            "direction": "desc"
        }
        
        logger.debug("Fetching issues for repo %s with label '%s'", repo_name, target_label)
        try:
            response = requests.get(repo_api_url, headers=headers, params=params, timeout=10)
            if response.status_code == 403:
                remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
                if remaining == 0:
                    reset_at = int(response.headers.get("X-RateLimit-Reset", 0))
                    wait = max(reset_at - int(time.time()), 0) + 1
                    logger.warning("GitHub rate limit hit. Waiting %d seconds...", wait)
                    time.sleep(min(wait, RATE_LIMIT_PAUSE))
                    response = requests.get(repo_api_url, headers=headers, params=params, timeout=10)
            
            if response.ok:
                raw_items = response.json()
                if isinstance(raw_items, list):
                    for raw_item in raw_items:
                        # Filter out pull requests which are also returned by /issues
                        if "pull_request" in raw_item:
                            continue
                        foundation = item.get("foundation") or detect_foundation(repo_name)
                        issues.append({
                            "id": raw_item.get("id"),
                            "title": raw_item.get("title", ""),
                            "url": raw_item.get("html_url", ""),
                            "repo": repo_name,
                            "labels": [l["name"] for l in raw_item.get("labels", []) if isinstance(l, dict) and "name" in l],
                            "body": (raw_item.get("body") or "").strip(),
                            "assignees": [a.get("login") for a in raw_item.get("assignees", []) if isinstance(a, dict) and "login" in a],
                            "comments_count": raw_item.get("comments", 0),
                            "foundation": foundation,
                            "source": "foundation_repo" if foundation else "repo_direct",
                        })
            else:
                logger.debug("Repo %s returned status %d", repo_name, response.status_code)
        except Exception as e:
            logger.debug("Error fetching issues for %s: %s", repo_name, e)
            
    return issues[:max_results]


def fetch_foundation_issues(
    target_foundations: list[str],
    tier: str = "contributor",
    limit: int = 30
) -> list[dict]:
    """
    Directly queries premier foundation repositories (CNCF, LFX, Apache, GSoC)
    for tier-appropriate opportunities.
    """
    foundation_repos = get_foundation_repos(target_foundations)
    tier_labels = get_tier_labels(tier)
    logger.info("Querying %d foundation repositories for tier '%s'...", len(foundation_repos), tier)
    return fetch_issues_from_repositories(foundation_repos, max_results=limit, labels=tier_labels)
