import sys
import os
import logging
from google import genai
from pydantic import BaseModel, Field
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

class IssueScore(BaseModel):
    url: str = Field(description="The exact URL of the issue being scored")
    score: int = Field(description="Relevance score from 1 to 10 based on the user's stack and preferences")
    explanation: str = Field(description="A concise 1-line explanation of why this issue fits the user's profile and skill level")

class IssueScoreBatch(BaseModel):
    scores: List[IssueScore]

# Initialize the Gemini client if the key is provided
_client = None
def get_gemini_client():
    global _client
    if _client is None:
        api_key = config.GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY not found in configuration/environment. Gemini calls will fail.")
        _client = genai.Client(api_key=api_key)
    return _client

SYSTEM_PROMPT = """
You are a career mentor and senior software architect. Your task is to evaluate open-source GitHub issues and score how relevant they are to the User's Profile.

User Profile:
- Stack: FastAPI, LangGraph, React, RAG pipelines, Python async, agents
- Skill level: Intermediate (wants challenging but not impossible issues)
- Preference: Backend-heavy, AI/ML adjacent, Python or JS/TS repos preferred

For each issue, assign a relevance score from 1 to 10:
- 10: Perfect fit. Involves Python, FastAPI, LangGraph, agentic frameworks, or RAG/vector-database logic. Challenging but fits an intermediate dev.
- 7-9: Strong fit. Backend Python/JS/TS, asynchronous coding, React, or standard web application backend.
- 4-6: Neutral fit. General Python/JS/TS issue, or standard frontend without React/AI relevance.
- 1-3: Poor fit. Other languages (Go, C++, Rust, C#), DevOps/infra configuration only, trivial documentation tasks, or extremely complex/unreachable tasks.

Also write a concise, 1-line explanation of why this issue fits or doesn't fit the user.
"""

def score_issues(issues: List[dict]) -> List[dict]:
    """
    Score a list of issues using Gemini in batches.
    Each issue dictionary is updated with a 'score' and 'explanation'.
    """
    if not issues:
        return []
        
    client = get_gemini_client()
    if not config.GEMINI_API_KEY:
        logger.error("Skipping LLM scoring: GEMINI_API_KEY is not set.")
        # Fallback to default neutral scores
        for issue in issues:
            issue["score"] = 5
            issue["explanation"] = "Default score (no Gemini API key provided)"
        return issues

    scored_issues_map = {}
    
    # Process issues in batches of 10 to fit context windows and schema limits safely
    batch_size = 10
    for i in range(0, len(issues), batch_size):
        batch = issues[i:i+batch_size]
        logger.info(f"Scoring batch {i // batch_size + 1} ({len(batch)} issues)...")
        
        # Prepare the issues text representation
        issues_text = ""
        for idx, issue in enumerate(batch):
            issues_text += f"Issue #{idx + 1}:\n"
            issues_text += f"URL: {issue.get('url')}\n"
            issues_text += f"Repo: {issue.get('repo')}\n"
            issues_text += f"Title: {issue.get('title')}\n"
            issues_text += f"Labels: {', '.join(issue.get('labels', []))}\n"
            issues_text += f"Body Snippet: {(issue.get('body') or '')[:300]}...\n"
            issues_text += "-------------------\n"
            
        prompt = f"{SYSTEM_PROMPT}\nEvaluate the following issues:\n\n{issues_text}"
        
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": IssueScoreBatch,
                }
            )
            
            # The response.text is guaranteed to match the schema
            batch_result = IssueScoreBatch.model_validate_json(response.text)
            for item in batch_result.scores:
                scored_issues_map[item.url] = {
                    "score": item.score,
                    "explanation": item.explanation
                }
        except Exception as e:
            logger.error(f"Failed to score batch starting at index {i}: {e}")
            # Ensure fallback values for this batch in case of error
            for issue in batch:
                if issue.get("url") not in scored_issues_map:
                    scored_issues_map[issue.get("url")] = {
                        "score": 5,
                        "explanation": "Failed to score using LLM due to error"
                    }
                    
    # Map the scores back to the original issues list
    scored_list = []
    for issue in issues:
        url = issue.get("url")
        score_info = scored_issues_map.get(url, {"score": 5, "explanation": "Unscored"})
        issue["score"] = score_info["score"]
        issue["explanation"] = score_info["explanation"]
        scored_list.append(issue)
        
    # Sort by score descending
    scored_list.sort(key=lambda x: x.get("score", 0), reverse=True)
    return scored_list
