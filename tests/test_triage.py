import pytest
from tools.triage import is_issue_claimed, triage_issues

def test_claimed_by_assignee():
    issue = {
        "url": "https://github.com/org/repo/issues/10",
        "title": "Add caching",
        "assignees": ["octocat"],
        "labels": ["good first issue"]
    }
    claimed, reason = is_issue_claimed(issue)
    assert claimed is True
    assert "assigned" in reason.lower()

def test_claimed_by_label():
    issue = {
        "url": "https://github.com/org/repo/issues/11",
        "title": "Fix memory leak",
        "assignees": [],
        "labels": ["in progress", "bug"]
    }
    claimed, reason = is_issue_claimed(issue)
    assert claimed is True
    assert "in progress" in reason.lower()

def test_unclaimed_issue():
    issue = {
        "url": "https://github.com/org/repo/issues/12",
        "title": "Support async generator",
        "assignees": [],
        "labels": ["help wanted", "good first issue"]
    }
    claimed, reason = is_issue_claimed(issue)
    assert claimed is False

def test_triage_issues_filtering():
    issues = [
        {
            "url": "https://github.com/org/repo/issues/1",
            "title": "Clean issue",
            "repo": "org/repo",
            "assignees": [],
            "labels": []
        },
        {
            "url": "https://github.com/org/repo/issues/2",
            "title": "Assigned issue",
            "repo": "org/repo",
            "assignees": ["dev1"],
            "labels": []
        }
    ]
    accepted, rejected = triage_issues(issues, filter_claimed=True, filter_inactive=False)
    assert len(accepted) == 1
    assert accepted[0]["title"] == "Clean issue"
    assert len(rejected) == 1
    assert rejected[0]["title"] == "Assigned issue"
    assert rejected[0]["rejection_status"] == "claimed"
