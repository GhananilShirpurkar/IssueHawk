import re
import urllib.parse
import logging
import requests
from bs4 import BeautifulSoup
import os

from tools.registry import get_tier_labels, detect_foundation

logger = logging.getLogger(__name__)

def _fetch_html(url: str) -> str:
    """Fetch URL contents with clean requests and standard headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.ok:
            return response.text
    except Exception as e:
        logger.debug(f"Fetch failed for {url}: {e}")
    return ""

def scrape_goodfirstissue() -> list[dict]:
    """Scrape goodfirstissue.dev and return a list of parsed issue dicts."""
    content = _fetch_html("https://goodfirstissue.dev")
    
    repos = []
    github_repo_regex = r"https://github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)"
    
    if content:
        if "<html" in content or "<div" in content:
            soup = BeautifulSoup(content, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                match = re.match(github_repo_regex, href)
                if match:
                    owner, name = match.group(1), match.group(2)
                    if owner.lower() not in ["login", "join", "features", "pricing", "explore", "trending", "topics", "sponsors", "about", "blog"]:
                        name = name.split("/")[0].split("#")[0]
                        repos.append({"repo": f"{owner}/{name}", "label": "good first issue"})
        else:
            matches = re.finditer(github_repo_regex, content)
            for m in matches:
                owner, name = m.group(1), m.group(2)
                if owner.lower() not in ["login", "join", "features", "pricing", "explore", "trending", "topics", "sponsors", "about", "blog"]:
                    name = name.split("/")[0].split("#")[0]
                    repos.append({"repo": f"{owner}/{name}", "label": "good first issue"})
                    
    # Deduplicate repos
    seen = set()
    deduped_repos = []
    for r in repos:
        if r["repo"] not in seen:
            seen.add(r["repo"])
            deduped_repos.append(r)
            
    logger.info(f"Scraped {len(deduped_repos)} repositories from goodfirstissue.dev")
    
    from tools.github_api import fetch_issues_from_repositories
    issues = fetch_issues_from_repositories(deduped_repos)
    for issue in issues:
        issue["source"] = "goodfirstissue"
    return issues

def scrape_upforgrabs() -> list[dict]:
    """Scrape up-for-grabs.net and return a list of parsed issue dicts."""
    content = _fetch_html("https://up-for-grabs.net/beta/index.html")
    
    repos = []
    label_link_regex = r"https://github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)/(labels|issues\?q=)([^)\"\s]+)"
    
    if content:
        if "<html" in content or "<div" in content:
            soup = BeautifulSoup(content, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                match = re.search(label_link_regex, href)
                if match:
                    owner, name = match.group(1), match.group(2)
                    name = name.split("/")[0].split("#")[0]
                    repo_name = f"{owner}/{name}"
                    
                    label = "up-for-grabs"
                    if "labels/" in href:
                        label_part = href.split("labels/")[-1]
                        label = urllib.parse.unquote(label_part).strip()
                    elif "label%3A" in href or "label:" in href:
                        q_part = urllib.parse.unquote(href.split("?q=")[-1])
                        label_match = re.search(r'label:(?:"([^"]+)"|([^\s+]+))', q_part)
                        if label_match:
                            label = label_match.group(1) or label_match.group(2)
                    
                    repos.append({"repo": repo_name, "label": label})
        else:
            matches = re.finditer(label_link_regex, content)
            for m in matches:
                owner, name = m.group(1), m.group(2)
                href = m.group(0)
                name = name.split("/")[0].split("#")[0]
                repo_name = f"{owner}/{name}"
                
                label = "up-for-grabs"
                if "labels/" in href:
                    label_part = href.split("labels/")[-1]
                    label = urllib.parse.unquote(label_part).strip()
                elif "label%3A" in href or "label:" in href:
                    q_part = urllib.parse.unquote(href.split("?q=")[-1])
                    label_match = re.search(r'label:(?:"([^"]+)"|([^\s+]+))', q_part)
                    if label_match:
                        label = label_match.group(1) or label_match.group(2)
                
                repos.append({"repo": repo_name, "label": label})
                
    # Deduplicate repos
    seen = set()
    deduped_repos = []
    for r in repos:
        if r["repo"] not in seen:
            seen.add(r["repo"])
            deduped_repos.append(r)
            
    logger.info(f"Scraped {len(deduped_repos)} repositories from up-for-grabs.net")
    
    from tools.github_api import fetch_issues_from_repositories
    issues = fetch_issues_from_repositories(deduped_repos)
    for issue in issues:
        issue["source"] = "upforgrabs"
    return issues

def collect_all_issues(profile=None) -> list[dict]:
    """
    Dynamically collect issues tailored to the developer's progression tier and target programs:
    1. Premier Open Source Foundations (CNCF, LFX, Apache, GSoC)
    2. Dynamic GitHub Search with tier-appropriate labels and star requirements
    3. Community sources (up-for-grabs / goodfirstissue) aligned with tier
    """
    from tools.github_api import fetch_github_issues, fetch_foundation_issues
    from tools.profile import load_profile
    
    dev_profile = profile or load_profile()
    tier = dev_profile.tier
    logger.info(f"Collecting issues for '{dev_profile.name}' [Tier: {tier}, Track: {dev_profile.track}]...")
    all_issues = []
    
    tier_labels = get_tier_labels(tier)
    
    # 1. Premier Foundation Repositories (CNCF, LFX, Apache, GSoC)
    if dev_profile.target_foundations:
        try:
            foundation_issues = fetch_foundation_issues(
                target_foundations=dev_profile.target_foundations,
                tier=tier,
                limit=35
            )
            all_issues.extend(foundation_issues)
            logger.info("Retrieved %d candidate issues from target foundations.", len(foundation_issues))
        except Exception as e:
            logger.error(f"Error fetching foundation issues: {e}")

    # 2. Dynamic GitHub Search (languages + topics + tier labels + min_stars)
    try:
        target_languages = dev_profile.languages or ["python", "javascript", "typescript"]
        target_topics = dev_profile.topics or ["fastapi", "react", "nextjs"]
        api_issues = fetch_github_issues(
            languages=target_languages,
            topics=target_topics,
            labels=tier_labels,
            min_stars=dev_profile.min_stars,
            limit=40
        )
        all_issues.extend(api_issues)
    except Exception as e:
        logger.error(f"Error fetching dynamic GitHub search issues: {e}")
        
    # 3. Community scrapers based on tier
    if tier == "apprentice":
        try:
            gfi_issues = scrape_goodfirstissue()
            all_issues.extend(gfi_issues)
        except Exception as e:
            logger.error(f"Error scraping goodfirstissue.dev: {e}")
            
    if tier in ("apprentice", "contributor"):
        try:
            ufg_issues = scrape_upforgrabs()
            all_issues.extend(ufg_issues)
        except Exception as e:
            logger.error(f"Error scraping up-for-grabs.net: {e}")
        
    # Deduplicate issues and filter out excluded labels
    excluded_labels = {l.lower() for l in dev_profile.exclude_labels}
    seen_urls = set()
    deduped = []
    
    for issue in all_issues:
        issue_url = issue.get("url")
        if not issue_url or issue_url in seen_urls:
            continue
            
        # Check excluded labels
        issue_labels = [l.lower() for l in issue.get("labels", [])]
        if any(ex in issue_labels for ex in excluded_labels):
            continue
            
        # Ensure foundation badge is detected if present
        if not issue.get("foundation"):
            issue["foundation"] = detect_foundation(issue.get("repo", ""))
            
        seen_urls.add(issue_url)
        deduped.append(issue)
        
    logger.info(f"Collected total of {len(deduped)} unique, non-excluded candidate issues.")
    return deduped
