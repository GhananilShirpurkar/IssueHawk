import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from tools.profile import load_profile

logger = logging.getLogger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

def generate_markdown_report(
    issues: List[Dict[str, Any]], 
    limit: int = 15,
    profile_name: Optional[str] = None
) -> Tuple[str, str]:
    """
    Generate a formatted markdown report of the top scored issues and save it to reports/ directory.
    Returns a tuple of (saved_file_path, markdown_content).
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    top_issues = issues[:limit]
    date_str = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prof = load_profile()
    active_profile = profile_name or prof.name
    
    markdown_lines = [
        f"# IssueHawk Curation Report — {date_str}",
        f"Curated for **{active_profile}** ({len(top_issues)} Issues Selected)",
        "",
        "---",
        ""
    ]
    
    if not top_issues:
        markdown_lines.append("No new relevant issues found matching your profile today.")
    else:
        for idx, issue in enumerate(top_issues, 1):
            title = issue.get("title", "No Title")
            url = issue.get("url", "#")
            repo = issue.get("repo", "Unknown Repo")
            score = issue.get("score", 0)
            difficulty = issue.get("difficulty", "intermediate")
            explanation = issue.get("explanation", "No explanation provided.")
            hint = issue.get("implementation_hint", "")
            labels = ", ".join(issue.get("labels", [])) or "None"
            
            entry = [
                f"### {idx}. [{title}]({url}) — Score: {score}/10 [{difficulty.upper()}]",
                f"**Repository:** `{repo}`",
                f"**Labels:** {labels}",
                f"**Why this fits you:** {explanation}"
            ]
            if hint:
                entry.append(f"**Where to start:** {hint}")
            entry.extend(["", "---", ""])
            markdown_lines.extend(entry)
            
    markdown_content = "\n".join(markdown_lines)
    
    report_filename = f"report_{timestamp}.md"
    report_path = os.path.join(REPORTS_DIR, report_filename)
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        logger.info(f"Report successfully written to {report_path}")
    except Exception as e:
        logger.error(f"Failed to write report file: {e}")
        
    return report_path, markdown_content
