"""
tools/github_api.py

Fetches open "good first issue" items from the GitHub Search API.
"""

import os
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/search/issues"
RESULTS_LIMIT = 30
RATE_LIMIT_PAUSE = 60  # seconds to wait when rate limit is hit


def _build_query(languages: list, topics: list) -> str:
    """
    Build a GitHub search query string from the given languages and topics.

    Example output:
        label:"good first issue" state:open language:python language:javascript
    """
    parts = ['label:"good first issue"', "state:open"]

    for lang in languages:
        parts.append(f"language:{lang}")

    for topic in topics:
        parts.append(f"topic:{topic}")

    return " ".join(parts)


def fetch_github_issues(languages: list, topics: list) -> list[dict]:
    """
    Fetch open "good first issue" items from the GitHub Search API.

    Args:
        languages: List of programming languages to filter by (e.g. ["python"]).
        topics:    List of repo topics to filter by (e.g. ["machine-learning"]).

    Returns:
        A list of dicts, each with keys:
            id, title, url, repo, labels, body
    """
    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        logger.warning("GITHUB_TOKEN not set — requests will use the unauthenticated rate limit (10 req/min).")

    query = _build_query(languages, topics)
    params = {
        "q": query,
        "per_page": RESULTS_LIMIT,
        "page": 1,
        "sort": "created",
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
        time.sleep(wait)

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
    logger.info("Retrieved %d issues from GitHub API.", len(raw_items))

    issues = []
    for item in raw_items:
        repo_url = item.get("repository_url", "")
        # repository_url is like https://api.github.com/repos/owner/name
        repo = repo_url.removeprefix("https://api.github.com/repos/") if repo_url else ""

        issues.append({
            "id": item.get("id"),
            "title": item.get("title", ""),
            "url": item.get("html_url", ""),
            "repo": repo,
            "labels": [label["name"] for label in item.get("labels", [])],
            "body": (item.get("body") or "").strip(),
        })

    return issues
