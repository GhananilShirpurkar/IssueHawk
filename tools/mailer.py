import requests
import logging
import re
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

def parse_markdown_report(markdown_content: str):
    """Parses structured IssueHawk markdown report into clean data structures."""
    lines = markdown_content.split("\n")
    title = "IssueHawk Curation Report"
    subtitle = "Curation of top open-source issues matching your profile."
    issues = []
    
    current_issue = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("# "):
            title = line[2:]
            continue
        if line.startswith("Curation of top"):
            subtitle = line
            continue
            
        # Match issue header: ### Rank. [Title](URL) — Score: X/10
        header_match = re.match(r"^###\s+(\d+)\.\s+\[(.*?)\]\((.*?)\)\s+—\s+Score:\s+(\d+)/10", line)
        if header_match:
            if current_issue:
                issues.append(current_issue)
            current_issue = {
                "rank": header_match.group(1),
                "title": header_match.group(2),
                "url": header_match.group(3),
                "score": int(header_match.group(4)),
                "repo": "",
                "labels": [],
                "why": ""
            }
            continue
            
        # Match Repository: **Repository:** `repo`
        repo_match = re.match(r"^\*\*Repository:\*\*\s+`(.*?)`", line)
        if repo_match and current_issue:
            current_issue["repo"] = repo_match.group(1)
            continue
            
        # Match Labels: **Labels:** labels
        labels_match = re.match(r"^\*\*Labels:\*\*\s+(.*)", line)
        if labels_match and current_issue:
            labels_str = labels_match.group(1)
            if labels_str.lower() != "none":
                current_issue["labels"] = [l.strip() for l in labels_str.split(",")]
            else:
                current_issue["labels"] = []
            continue
            
        # Match Why this fits you: **Why this fits you:** explanation
        fit_match = re.match(r"^\*\*Why this fits you:\*\*\s+(.*)", line)
        if fit_match and current_issue:
            current_issue["why"] = fit_match.group(1)
            continue
            
    if current_issue:
        issues.append(current_issue)
        
    return title, subtitle, issues

def convert_markdown_to_html(markdown_content: str) -> str:
    """Converts parsed markdown into a premium-styled responsive HTML newsletter."""
    title, subtitle, issues = parse_markdown_report(markdown_content)
    
    content_html = ""
    if not issues:
        # Fallback for simple markdown messages (like test emails)
        body_html = []
        for line in markdown_content.split("\n"):
            line = line.strip()
            if not line or line.startswith("# ") or line.startswith("---") or "curation of top" in line.lower():
                continue
            # Basic styling substitutions
            line = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"`(.*?)`", r"<code>\1</code>", line)
            if line.startswith("* "):
                body_html.append(f'<li style="margin-bottom: 8px;">{line[2:]}</li>')
            else:
                body_html.append(f'<p style="line-height: 1.5; font-size: 14px; margin-bottom: 12px;">{line}</p>')
        
        content_html = "".join(body_html)
        if "<li>" in content_html:
            content_html = f'<ul style="padding-left: 20px; font-size: 14px; margin-bottom: 16px;">{content_html}</ul>'
    else:
        issues_html = []
        for issue in issues:
            # Determine score styling
            score = issue["score"]
            if score >= 8:
                score_class = "score-high"
            elif score >= 6:
                score_class = "score-med"
            else:
                score_class = "score-low"
                
            # Build labels HTML
            labels_html = ""
            if issue["labels"]:
                labels_html = '<div class="label-container">' + "".join(
                    f'<span class="label-tag">{label}</span>' for label in issue["labels"]
                ) + '</div>'
                
            # Build issue card template
            card = f"""
            <div class="issue-card">
              <div class="issue-title-row">
                <h3 class="issue-title">
                  <span class="rank-num">#{issue["rank"]}</span> 
                  <a href="{issue["url"]}" target="_blank">{issue["title"]}</a>
                </h3>
                <span class="score-badge {score_class}">{score}/10 Match</span>
              </div>
              <div class="meta-info">
                <span class="repo-tag">📁 {issue["repo"]}</span>
                {labels_html}
              </div>
              <div class="fit-callout">
                <span class="fit-label">Why this fits you</span>
                <p>{issue["why"]}</p>
              </div>
            </div>
            """
            issues_html.append(card)
        content_html = "".join(issues_html)
        
    # Full email template
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: #f1f5f9;
      color: #334155;
    }}
    .container {{
      max-width: 600px;
      margin: 30px auto;
      background: #ffffff;
      border-radius: 12px;
      border: 1px solid #e2e8f0;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
      overflow: hidden;
    }}
    .header {{
      background: linear-gradient(135deg, #4f46e5, #6366f1);
      padding: 35px 24px;
      color: #ffffff;
      text-align: center;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      background: rgba(255, 255, 255, 0.2);
      color: #ffffff;
      border-radius: 100px;
      margin-bottom: 12px;
    }}
    .header h1 {{
      font-size: 24px;
      margin: 0 0 8px 0;
      font-weight: 800;
      letter-spacing: -0.02em;
    }}
    .header p {{
      font-size: 14px;
      margin: 0;
      opacity: 0.9;
    }}
    .content {{
      padding: 24px;
      background-color: #ffffff;
    }}
    .issue-card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 18px;
      margin-bottom: 20px;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.02);
    }}
    .issue-title-row {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 10px;
    }}
    .issue-title {{
      font-size: 15px;
      font-weight: 700;
      margin: 0;
      line-height: 1.4;
      flex: 1;
    }}
    .rank-num {{
      color: #6366f1;
      margin-right: 4px;
    }}
    .issue-title a {{
      color: #0f172a;
      text-decoration: none;
    }}
    .issue-title a:hover {{
      color: #4f46e5;
      text-decoration: underline;
    }}
    .score-badge {{
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      white-space: nowrap;
      margin-left: 12px;
    }}
    .score-high {{
      background-color: #dcfce7;
      color: #15803d;
    }}
    .score-med {{
      background-color: #dbeafe;
      color: #1d4ed8;
    }}
    .score-low {{
      background-color: #fef3c7;
      color: #b45309;
    }}
    .meta-info {{
      margin-bottom: 12px;
      font-size: 12px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
    }}
    .repo-tag {{
      color: #475569;
      font-weight: 600;
      background-color: #f1f5f9;
      padding: 2px 6px;
      border-radius: 4px;
    }}
    .label-container {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }}
    .label-tag {{
      font-size: 10px;
      background-color: #f8fafc;
      color: #64748b;
      padding: 1px 5px;
      border: 1px solid #e2e8f0;
      border-radius: 4px;
    }}
    .fit-callout {{
      background-color: #faf5ff;
      border-left: 3px solid #8b5cf6;
      padding: 10px 12px;
      border-radius: 0 6px 6px 0;
    }}
    .fit-callout p {{
      margin: 0;
      font-size: 13px;
      line-height: 1.4;
      color: #5b21b6;
    }}
    .fit-label {{
      font-weight: 700;
      color: #7c3aed;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 4px;
      display: block;
    }}
    .footer {{
      text-align: center;
      padding: 20px;
      font-size: 12px;
      color: #64748b;
      background-color: #f8fafc;
      border-top: 1px solid #e2e8f0;
    }}
    .footer p {{
      margin: 4px 0;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <span class="badge">🤖 Automated Curation</span>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
    <div class="content">
      {content_html}
    </div>
    <div class="footer">
      <p>Sent by <strong>IssueHawk</strong> Autonomous Agent</p>
      <p>© {config.SCHEDULE_DAY.upper()} Curation Cadence</p>
    </div>
  </div>
</body>
</html>
"""
    return html_content

def send_email(subject: str, body_markdown: str) -> bool:
    """Send report email using Resend API."""
    api_key = config.RESEND_API_KEY
    recipient = config.RECIPIENT_EMAIL
    
    if not api_key:
        logger.error("Failed to send email: RESEND_API_KEY is not configured.")
        return False
        
    if not recipient:
        logger.error("Failed to send email: RECIPIENT_EMAIL is not configured.")
        return False
        
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    html_content = convert_markdown_to_html(body_markdown)
    
    payload = {
        "from": "IssueHawk <onboarding@resend.dev>",
        "to": [recipient],
        "subject": subject,
        "html": html_content,
        "text": body_markdown
    }
    
    logger.info(f"Sending email to {recipient} via Resend...")
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.ok:
            data = response.json()
            logger.info(f"Email sent successfully! Message ID: {data.get('id')}")
            return True
        else:
            logger.error(f"Failed to send email. Status: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error calling Resend API: {e}")
        return False

