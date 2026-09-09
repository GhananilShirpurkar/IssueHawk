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
        profile=prof,
        cadence=active_cadence
    )


def render_simple_html(title: str, text_content: str) -> str:
    """Fallback HTML renderer for simple text or verification emails."""
    paragraphs = [p for p in text_content.split("\n") if p.strip()]
    body_html = "".join(f"<p style='line-height: 1.6; font-size: 14px; color: #334155; margin: 0 0 12px 0;'>{p}</p>" for p in paragraphs)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'></head>
<body style='margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f8fafc; color: #1e293b;'>
  <table width='100%' border='0' cellpadding='0' cellspacing='0' bgcolor='#f8fafc' style='background-color: #f8fafc; padding: 40px 12px;'>
    <tr>
      <td align='center'>
        <table width='580' border='0' cellpadding='0' cellspacing='0' bgcolor='#ffffff' style='max-width: 580px; width: 100%; background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 12px -2px rgba(0,0,0,0.05);'>
          <tr>
            <td style='padding: 32px 28px 20px 28px; text-align: center; border-bottom: 1px solid #f1f5f9;'>
              <a href='https://github.com/GhananilShirpurkar/IssueHawk' target='_blank' style='text-decoration: none;'>
                <img src='https://raw.githubusercontent.com/GhananilShirpurkar/IssueHawk/main/assets/logo.png' width='180' alt='IssueHawk' style='display: block; margin: 0 auto 12px auto; border: 0;' />
              </a>
              <h2 style='color: #0f172a; margin: 0; font-size: 18px; font-weight: 700;'>{title}</h2>
            </td>
          </tr>
          <tr>
            <td style='padding: 24px 28px;'>
              {body_html}
            </td>
          </tr>
          <tr>
            <td style='padding: 16px 28px; background-color: #f8fafc; border-top: 1px solid #f1f5f9; text-align: center;'>
              <p style='font-size: 12px; color: #94a3b8; margin: 0;'>Sent by <strong style='color: #64748b;'>IssueHawk Autonomous Agent</strong></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
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
