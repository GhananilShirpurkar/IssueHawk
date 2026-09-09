from unittest.mock import patch, MagicMock
import pytest
from tools.mailer import render_newsletter_html
from tools.dispatchers import send_discord_webhook, send_slack_webhook

def test_render_newsletter_html():
    sample_issues = [
        {
            "title": "Add streaming support to FastAPI agent",
            "url": "https://github.com/test/agent/issues/42",
            "repo": "test/agent",
            "score": 9,
            "difficulty": "intermediate",
            "labels": ["enhancement", "good first issue"],
            "explanation": "Perfect match for Python async and FastAPI development.",
            "implementation_hint": "Check router.py and implement StreamingResponse."
        }
    ]
    html = render_newsletter_html(
        issues=sample_issues,
        title="IssueHawk Test Report",
        profile_name="Test Developer"
    )
    
    assert "IssueHawk Test Report" in html
    assert "Add streaming support to FastAPI agent" in html
    assert "9/10 Match" in html
    assert "test/agent" in html
    assert "Check router.py and implement StreamingResponse" in html
    assert "Test Developer" in html

@patch("requests.post")
def test_send_discord_webhook(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_post.return_value = mock_resp
    
    issues = [
        {
            "title": "Fix React hook warning",
            "url": "https://github.com/react/app/issues/1",
            "repo": "react/app",
            "score": 8,
            "difficulty": "beginner",
            "explanation": "Great React task",
            "implementation_hint": "Wrap useEffect dependencies"
        }
    ]
    
    success = send_discord_webhook("https://discord.com/api/webhooks/test", issues, "Test Dev")
    assert success is True
    assert mock_post.called
    payload = mock_post.call_args[1]["json"]
    assert "embeds" in payload
    assert len(payload["embeds"]) == 1
    assert payload["embeds"][0]["title"] == "#1. Fix React hook warning"

@patch("requests.post")
def test_send_slack_webhook(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp
    
    issues = [
        {
            "title": "Implement LangGraph checkpointing",
            "url": "https://github.com/langchain/graph/issues/5",
            "repo": "langchain/graph",
            "score": 10,
            "difficulty": "advanced",
            "explanation": "Exact match for LangGraph profile",
            "implementation_hint": "Add SqliteSaver integration"
        }
    ]
    
    success = send_slack_webhook("https://hooks.slack.com/services/test", issues, "Test Dev")
    assert success is True
    assert mock_post.called
    payload = mock_post.call_args[1]["json"]
    assert "blocks" in payload
    assert len(payload["blocks"]) >= 2
