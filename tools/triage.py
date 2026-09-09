import re
import os
import time
import logging
import requests
from typing import Tuple, List, Dict, Optional

logger = logging.getLogger(__name__)

CLAIMED_PHRASES = [
    r"\bi(?:'d| would)? like to work on this\b",
    r"\bcan i (?:take|work on) this\b",
    r"\bassign (?:this to me|me)\b",
    r"\bi am working on this\b",
    r"\bi'm working on this\b",
    r"\bworking on a fix\b",
    r"\bpr is up\b",
    r"\bopened a pr\b",
    r"\bcreated a pull request\b",
    r"\btaking this up\b"
]
CLAIMED_REGEX = re.compile("|".join(CLAIMED_PHRASES), re.IGNORECASE)

_repo_vitality_cache: Dict[str, Tuple[bool, str]] = {}

def is_issue_claimed(issue: dict, token: Optional[str] = None) -> Tuple[bool, str]:
    """
    Determines if an issue has already been claimed or worked on:
    1. Checks if assignees list is non-empty.
    2. Checks for in-progress or claimed labels.
    3. If comments exist, checks the latest comments for claiming phrases.
    """
    # 1. Assignee check
    assignees = issue.get("assignees", [])
    if assignees:
        return True, f"Already assigned to {len(assignees)} developer(s)"
        
    # 2. Label check
    labels = [l.lower() for l in issue.get("labels", [])]
    for label in labels:
        if any(term in label for term in ("in progress", "claimed", "assigned", "pr open", "has-pr")):
            return True, f"Label indicates active work: {label}"
            
    # 3. Comments check (if API token is available and repo/issue_number can be parsed)
    comments_count = issue.get("comments_count", 0)
    url = issue.get("url", "")
    
    # URL format: https://github.com/owner/repo/issues/123
    match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", url)
    if not match:
        return False, ""
        
    owner, repo_name, issue_num = match.groups()
    github_token = token or os.getenv("ACCESS_TOKEN_GITHUB") or os.getenv("GITHUB_TOKEN")
    
    # Only fetch comments if there are few comments or token is available
    if comments_count > 0 and github_token:
        comments_url = f"https://api.github.com/repos/{owner}/{repo_name}/issues/{issue_num}/comments"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        params = {"per_page": 5, "sort": "created", "direction": "desc"}
        
        try:
            resp = requests.get(comments_url, headers=headers, params=params, timeout=5)
            if resp.ok:
                comments = resp.json()
                for c in comments:
                    body = c.get("body", "")
                    if CLAIMED_REGEX.search(body):
                        author = c.get("user", {}).get("login", "someone")
                        return True, f"Claimed in comment by @{author}"
        except Exception as e:
            logger.debug(f"Could not inspect comments for {url}: {e}")
            
    return False, ""

def is_repo_vital(repo_name: str, token: Optional[str] = None) -> Tuple[bool, str]:
    """
    Verifies that the repository is active and not archived or abandoned.
    Results are cached in-memory per run.
    """
    if repo_name in _repo_vitality_cache:
        return _repo_vitality_cache[repo_name]
        
    github_token = token or os.getenv("ACCESS_TOKEN_GITHUB") or os.getenv("GITHUB_TOKEN")
    if not github_token or "/" not in repo_name:
        _repo_vitality_cache[repo_name] = (True, "Unverified (no token)")
        return _repo_vitality_cache[repo_name]
        
    api_url = f"https://api.github.com/repos/{repo_name}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    try:
        resp = requests.get(api_url, headers=headers, timeout=5)
        if resp.status_code == 404:
            res = (False, "Repository not found or private")
            _repo_vitality_cache[repo_name] = res
            return res
        if resp.ok:
            data = resp.json()
            if data.get("archived", False):
                res = (False, "Repository is archived")
                _repo_vitality_cache[repo_name] = res
                return res
            if data.get("disabled", False):
                res = (False, "Repository is disabled")
                _repo_vitality_cache[repo_name] = res
                return res
                
            res = (True, "Repository is active")
            _repo_vitality_cache[repo_name] = res
            return res
    except Exception as e:
        logger.debug(f"Error checking vitality for {repo_name}: {e}")
        
    res = (True, "Default active")
    _repo_vitality_cache[repo_name] = res
    return res

def triage_issues(
    issues: List[dict],
    filter_claimed: bool = True,
    filter_inactive: bool = True
) -> Tuple[List[dict], List[dict]]:
    """
    Triages issues into accepted candidates and rejected issues with reasons.
    """
    accepted = []
    rejected = []
    
    for issue in issues:
        repo_name = issue.get("repo", "")
        
        # Check repo vitality
        if filter_inactive and repo_name:
            is_vital, reason = is_repo_vital(repo_name)
            if not is_vital:
                issue["rejection_reason"] = reason
                issue["rejection_status"] = "inactive_repo"
                rejected.append(issue)
                continue
                
        # Check claimed status
        if filter_claimed:
            claimed, reason = is_issue_claimed(issue)
            if claimed:
                issue["rejection_reason"] = reason
                issue["rejection_status"] = "claimed"
                rejected.append(issue)
                continue
                
        accepted.append(issue)
        
    logger.info(f"Triage complete: {len(accepted)} accepted, {len(rejected)} rejected.")
    return accepted, rejected
