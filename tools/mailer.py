import requests
import logging
import re
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

def convert_markdown_to_html(markdown_content: str) -> str:
    """Converts the specific IssueHawk markdown report to styled, clean HTML."""
    lines = markdown_content.split("\n")
    html_body = []
    
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                html_body.append("</ul>")
                in_list = False
            continue
            
        # Parse main header
        if line.startswith("# "):
            title = line[2:]
            html_body.append(f"<h1>{title}</h1>")
            continue
            
        # Parse subtitle (usually the second line of the report)
        if line.startswith("Curation of top"):
            html_body.append(f"<div class='subtitle'>{line}</div>")
            continue
            
        # Parse horizontal rule
        if line == "---":
            if in_list:
                html_body.append("</ul>")
                in_list = False
            html_body.append("<hr>")
            continue
            
        # Parse issue headers: ### Rank. [Title](URL) — Score: X/10
        issue_header_match = re.match(r"^###\s+(\d+)\.\s+\[(.*?)\]\((.*?)\)\s+—\s+Score:\s+(\d+/10)$", line)
        if issue_header_match:
            if in_list:
                html_body.append("</ul>")
                in_list = False
            rank = issue_header_match.group(1)
            title = issue_header_match.group(2)
            url = issue_header_match.group(3)
            score = issue_header_match.group(4)
            html_body.append(
                f"<div class='issue-card'>"
                f"<h3>{rank}. <a href='{url}'>{title}</a><span class='score-badge'>Score: {score}</span></h3>"
            )
            continue
            
        # End of issue card handler (when separator occurs or next issue card starts)
        # Parse metadata lines: **Repository:** `repo`
        repo_match = re.match(r"\*\*Repository:\*\*\s+`(.*?)`", line)
        if repo_match:
            repo = repo_match.group(1)
            html_body.append(f"<p><strong>Repository:</strong> <code>{repo}</code></p>")
            continue
            
        # Parse labels: **Labels:** label1, label2
        labels_match = re.match(r"\*\*Labels:\*\*\s+(.*)", line)
        if labels_match:
            labels = labels_match.group(1)
            html_body.append(f"<p><strong>Labels:</strong> {labels}</p>")
            continue
            
        # Parse why it fits: **Why this fits you:** explanation
        fits_match = re.match(r"\*\*Why this fits you:\*\*\s+(.*)", line)
        if fits_match:
            explanation = fits_match.group(1)
            html_body.append(f"<p><strong>Why this fits you:</strong> {explanation}</p></div>")
            continue
            
        # Fallback line formatting (handle bolding and code blocks inline)
        formatted_line = line
        formatted_line = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", formatted_line)
        formatted_line = re.sub(r"`(.*?)`", r"<code>\1</code>", formatted_line)
        
        html_body.append(f"<p>{formatted_line}</p>")
        
    if in_list:
        html_body.append("</ul>")
        
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          color: #333333;
          background-color: #f4f6f8;
          padding: 20px;
          margin: 0;
        }}
        .container {{
          max-width: 600px;
          margin: 0 auto;
          background: #ffffff;
          padding: 30px;
          border-radius: 10px;
          box-shadow: 0 4px 10px rgba(0,0,0,0.05);
          border: 1px solid #e1e3e6;
        }}
        h1 {{
          font-size: 22px;
          color: #1c1d1f;
          margin-top: 0;
          border-bottom: 2px solid #5c6ac4;
          padding-bottom: 10px;
        }}
        .subtitle {{
          font-size: 14px;
          color: #6d7175;
          margin-top: -6px;
          margin-bottom: 20px;
          font-style: italic;
        }}
        .issue-card {{
          margin-bottom: 20px;
          padding-bottom: 15px;
          border-bottom: 1px solid #f1f2f4;
        }}
        .issue-card:last-of-type {{
          border-bottom: none;
        }}
        h3 {{
          font-size: 16px;
          margin-top: 0;
          margin-bottom: 8px;
          color: #1c1d1f;
        }}
        h3 a {{
          color: #008060;
          text-decoration: none;
        }}
        h3 a:hover {{
          text-decoration: underline;
        }}
        .score-badge {{
          display: inline-block;
          background: #e3f1df;
          color: #008060;
          font-size: 11px;
          font-weight: 600;
          padding: 2px 6px;
          border-radius: 4px;
          margin-left: 8px;
          vertical-align: middle;
        }}
        p {{
          margin: 4px 0;
          font-size: 14px;
          line-height: 1.4;
          color: #454f5b;
        }}
        strong {{
          color: #212b36;
        }}
        code {{
          background: #f4f6f8;
          padding: 2px 4px;
          border-radius: 4px;
          font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
          font-size: 12px;
        }}
        hr {{
          border: 0;
          border-top: 1px solid #e1e3e6;
          margin: 20px 0;
        }}
      </style>
    </head>
    <body>
      <div class="container">
        {"".join(html_body)}
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
        response = requests.post(url, json=payload, headers=headers, timeout=15)
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
