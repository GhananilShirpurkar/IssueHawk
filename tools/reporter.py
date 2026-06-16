import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

def generate_markdown_report(issues: list[dict], limit: int = 15) -> tuple[str, str]:
    """
    Generate a formatted markdown report of the top scored issues and save it to the reports/ directory.
    Returns a tuple of (saved_file_path, markdown_content).
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    top_issues = issues[:limit]
    date_str = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    markdown_lines = [
        f"# IssueHawk Daily Report — {date_str}",
        "Curation of top open-source issues matching your profile.",
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
            explanation = issue.get("explanation", "No explanation provided.")
            labels = ", ".join(issue.get("labels", [])) or "None"
            
            markdown_lines.extend([
                f"### {idx}. [{title}]({url}) — Score: {score}/10",
                f"**Repository:** `{repo}`",
                f"**Labels:** {labels}",
                f"**Why this fits you:** {explanation}",
                "",
                "---",
                ""
            ])
            
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
