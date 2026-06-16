import asyncio
import re
import urllib.parse
import logging
import requests
from bs4 import BeautifulSoup
import os

logger = logging.getLogger(__name__)

async def _crawl_url(url: str) -> str:
    """Crawl a URL using crawl4ai if possible, with a requests fallback."""
    try:
        from crawl4ai import AsyncWebCrawler
        logger.info(f"Crawling {url} using crawl4ai...")
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            if result and result.markdown:
                return result.markdown
    except Exception as e:
        logger.warning(f"crawl4ai failed or not fully configured: {e}. Falling back to requests.")
    
    # Fallback to requests
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.ok:
            return response.text
    except Exception as e:
        logger.error(f"Fallback requests crawl failed for {url}: {e}")
    return ""

def scrape_goodfirstissue() -> list[dict]:
    """Scrape goodfirstissue.dev and return a list of parsed issue dicts."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            pass
            
    content = loop.run_until_complete(_crawl_url("https://goodfirstissue.dev"))
    
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
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            pass
            
    content = loop.run_until_complete(_crawl_url("https://up-for-grabs.net/beta/index.html"))
    
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

def collect_all_issues() -> list[dict]:
    """
    Run all collection sources:
    1. Scrape goodfirstissue.dev
    2. Scrape up-for-grabs.net
    3. Run standard GitHub Search API query for languages and topics
    Deduplicate issues by url/id, normalize schema, and return.
    """
    from tools.github_api import fetch_github_issues
    
    logger.info("Starting collection of all issues...")
    all_issues = []
    
    try:
        gfi_issues = scrape_goodfirstissue()
        all_issues.extend(gfi_issues)
    except Exception as e:
        logger.error(f"Error scraping goodfirstissue.dev: {e}")
        
    try:
        ufg_issues = scrape_upforgrabs()
        all_issues.extend(ufg_issues)
    except Exception as e:
        logger.error(f"Error scraping up-for-grabs.net: {e}")
        
    try:
        # Fetch generic issues as well
        api_issues = fetch_github_issues(
            languages=["python", "javascript", "typescript"],
            topics=["fastapi", "react", "nextjs", "django", "nodejs"],
            limit=50
        )
        all_issues.extend(api_issues)
    except Exception as e:
        logger.error(f"Error fetching issues via GitHub API: {e}")
        
    # Deduplicate issues
    seen_ids = set()
    seen_urls = set()
    deduped = []
    for issue in all_issues:
        issue_id = issue.get("id")
        issue_url = issue.get("url")
        if issue_url and issue_url not in seen_urls:
            seen_urls.add(issue_url)
            if issue_id:
                seen_ids.add(issue_id)
            deduped.append(issue)
            
    logger.info(f"Collected total of {len(deduped)} unique issues.")
    return deduped
