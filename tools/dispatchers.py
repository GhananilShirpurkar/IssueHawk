import os
import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def send_discord_webhook(webhook_url: str, issues: List[Dict[str, Any]], profile_name: str = "Developer") -> bool:
    """Sends curated issues as rich embeds to a Discord channel via webhook."""
    if not webhook_url:
        return False
        
    top_issues = issues[:10]  # Discord allows up to 10 embeds per message
    if not top_issues:
        logger.info("No issues to send to Discord.")
        return True
        
    embeds = []
    for idx, issue in enumerate(top_issues, 1):
        score = issue.get("score", 5)
        # Choose color based on score (Green: 0x22c55e, Indigo: 0x4f46e5, Amber: 0xf59e0b)
        color = 0x22c55e if score >= 8 else (0x4f46e5 if score >= 6 else 0xf59e0b)
        
        hint = issue.get("implementation_hint", "")
        hint_text = f"\n💡 **Where to start:** {hint}" if hint else ""
        
        embed = {
            "title": f"#{idx}. {issue.get('title', 'Untitled')[:200]}",
            "url": issue.get("url", ""),
            "description": f"**Why:** {issue.get('explanation', '')}{hint_text}",
            "color": color,
            "fields": [
                {"name": "Repository", "value": f"`{issue.get('repo', 'N/A')}`", "inline": True},
                {"name": "Match Score", "value": f"**{score}/10**", "inline": True},
                {"name": "Difficulty", "value": f"`{issue.get('difficulty', 'intermediate')}`", "inline": True},
            ]
        }
        embeds.append(embed)
        
    payload = {
        "content": f"🦅 **IssueHawk Curation Report** for **{profile_name}** ({len(issues)} matching issues found):",
        "embeds": embeds
    }
    
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            logger.info("Successfully dispatched report to Discord webhook.")
            return True
        else:
            logger.error(f"Discord webhook failed with status {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Error dispatching to Discord: {e}")
        return False

def send_slack_webhook(webhook_url: str, issues: List[Dict[str, Any]], profile_name: str = "Developer") -> bool:
    """Sends curated issues as rich blocks to a Slack channel via webhook."""
    if not webhook_url:
        return False
        
    top_issues = issues[:10]
    if not top_issues:
        return True
        
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🦅 IssueHawk Curation for {profile_name}"
            }
        },
        {"type": "divider"}
    ]
    
    for idx, issue in enumerate(top_issues, 1):
        score = issue.get("score", 5)
        title = issue.get("title", "Untitled")
        url = issue.get("url", "")
        repo = issue.get("repo", "")
        why = issue.get("explanation", "")
        hint = issue.get("implementation_hint", "")
        
        issue_block = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*<{url}|#{idx}. {title}>* — *{score}/10 Match*\n"
                    f"*Repo:* `{repo}`\n"
                    f"*Why:* {why}\n"
                    + (f"*Hint:* {hint}" if hint else "")
                )
            }
        }
        blocks.append(issue_block)
        blocks.append({"type": "divider"})
        
    payload = {"blocks": blocks}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Successfully dispatched report to Slack webhook.")
            return True
        else:
            logger.error(f"Slack webhook failed with status {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Error dispatching to Slack: {e}")
        return False

def dispatch_webhooks(issues: List[Dict[str, Any]], profile_name: str = "Developer") -> Dict[str, bool]:
    """Dispatches reports to any configured webhooks (Discord / Slack)."""
    results = {}
    
    discord_url = os.getenv("DISCORD_WEBHOOK_URL")
    if discord_url:
        logger.info("Dispatching report to Discord webhook...")
        results["discord"] = send_discord_webhook(discord_url, issues, profile_name)
        
    slack_url = os.getenv("SLACK_WEBHOOK_URL")
    if slack_url:
        logger.info("Dispatching report to Slack webhook...")
        results["slack"] = send_slack_webhook(slack_url, issues, profile_name)
        
    return results
