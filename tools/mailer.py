import os
import sys
import logging
import requests
from jinja2 import Environment, FileSystemLoader
from typing import List, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from tools.profile import load_profile

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

def render_newsletter_html(
    issues: List[Dict[str, Any]], 
    title: str = "IssueHawk Curation Report",
    subtitle: str = "Curation of top open-source issues matching your profile.",
    profile_name: Optional[str] = None,
    cadence: Optional[str] = None
) -> str:
    """Renders the HTML newsletter using Jinja2 template."""
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)
    template = env.get_template("newsletter.html.j2")
    
    prof = load_profile()
    active_profile_name = profile_name or prof.name
    active_cadence = cadence or config.SCHEDULE_DAY
    
    return template.render(
        title=title,
        subtitle=subtitle,
        issues=issues,
        profile_name=active_profile_name,
        cadence=active_cadence
    )

def render_simple_html(title: str, text_content: str) -> str:
    """Fallback HTML renderer for simple text or verification emails."""
    paragraphs = [p for p in text_content.split("\n") if p.strip()]
    body_html = "".join(f"<p style='line-height: 1.5; font-size: 14px;'>{p}</p>" for p in paragraphs)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset='utf-8'></head>
<body style='font-family: -apple-system, sans-serif; background-color: #0f172a; padding: 30px 10px;'>
  <div style='max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 28px; border: 1px solid #e2e8f0;'>
    <h2 style='color: #4338ca; margin-top: 0;'>🦅 {title}</h2>
    <div style='color: #334155;'>{body_html}</div>
    <hr style='border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;'/>
    <p style='font-size: 12px; color: #64748b; margin: 0;'>Sent by IssueHawk Autonomous Agent</p>
  </div>
</body>
</html>"""

def send_email(
    subject: str, 
    body_markdown: str, 
    issues: Optional[List[Dict[str, Any]]] = None,
    profile_name: Optional[str] = None
) -> bool:
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
    
    if issues:
        prof = load_profile()
        pname = profile_name or prof.name
        html_content = render_newsletter_html(
            issues=issues,
            title=subject,
            subtitle=f"Curated for {pname} • {len(issues)} High-Relevance Opportunities",
            profile_name=pname
        )
    else:
        html_content = render_simple_html(subject, body_markdown)
        
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
