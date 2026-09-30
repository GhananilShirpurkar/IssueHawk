import os
import glob
import re
import webbrowser
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

def display_issue_table(issues: List[Dict[str, Any]], title: str = "🦅 High-Impact Curated Issues"):
    """Render a beautiful terminal dashboard of issues using Rich."""
    if not issues:
        console.print(Panel("No issues to display.", style="yellow"))
        return
        
    table = Table(
        title=title,
        show_header=True,
        header_style="bold magenta",
        border_style="dim white",
        padding=(0, 1)
    )
    
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Score", justify="center", width=8)
    table.add_column("Program / Foundation", justify="center", width=14)
    table.add_column("Level", justify="center", width=10)
    table.add_column("Repository", style="cyan", width=22)
    table.add_column("Title & Advice", style="white")
    
    for idx, issue in enumerate(issues, 1):
        score = issue.get("score", 5)
        impact = issue.get("impact_score", 0)
        
        if score >= 8:
            score_text = Text(f"{score}/10", style="bold green")
        elif score >= 6:
            score_text = Text(f"{score}/10", style="bold cyan")
        else:
            score_text = Text(f"{score}/10", style="yellow")
            
        foundation = issue.get("foundation")
        if foundation:
            f_style = "bold magenta" if foundation in ("LFX", "CNCF") else "bold blue"
            found_text = Text(f"[{foundation}]", style=f_style)
        else:
            found_text = Text("General OSS", style="dim")
            
        diff = issue.get("difficulty", "intermediate")
        diff_style = "green" if diff == "beginner" else ("blue" if diff == "intermediate" else "magenta")
        diff_text = Text(diff.capitalize(), style=diff_style)
        
        repo = issue.get("repo", "Unknown")
        issue_title = issue.get("title", "Untitled")
        url = issue.get("url", "")
        why = issue.get("explanation", "")
        hint = issue.get("implementation_hint", "")
        portfolio_rationale = issue.get("portfolio_rationale", "")
        
        details = Text()
        details.append(f"{issue_title}\n", style="bold underline")
        details.append(f"🔗 {url}\n", style="dim blue")
        if portfolio_rationale:
            details.append(f"⭐ Portfolio Uplift: {portfolio_rationale}\n", style="bold green")
        if why:
            details.append(f"• Why: {why}\n", style="italic")
        if hint:
            details.append(f"💡 Start here: {hint}", style="cyan")
            
        table.add_row(
            str(idx),
            score_text,
            found_text,
            diff_text,
            repo,
            details
        )
        
    console.print(table)

def parse_markdown_report_file(file_path: str) -> List[Dict[str, Any]]:
    """Parse a markdown report file back into structured issue objects."""
    if not os.path.exists(file_path):
        return []
        
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    issues = []
    current_issue = None
    
    for line in content.split("\n"):
        line = line.strip()
        # Supports both legacy and modern formats with Impact/Foundation
        header_match = re.match(
            r"^###\s+(\d+)\.\s+\[(.*?)\]\((.*?)\)\s+—\s+Score:\s+(\d+)/10(?:\s+\[Impact:\s+(\d+)/10\])?(?:\s+\[(.*?)\])?(?:\s+\[(.*?)\])?", 
            line
        )
        if header_match:
            if current_issue:
                issues.append(current_issue)
            
            impact = int(header_match.group(5)) if header_match.group(5) else 5
            bracket1 = header_match.group(6) or ""
            bracket2 = header_match.group(7) or ""
            
            diff = "intermediate"
            found = ""
            for b in (bracket1, bracket2):
                if b.lower() in ("beginner", "intermediate", "advanced"):
                    diff = b.lower()
                elif b in ("CNCF", "LFX", "Apache", "GSoC"):
                    found = b

            current_issue = {
                "rank": header_match.group(1),
                "title": header_match.group(2),
                "url": header_match.group(3),
                "score": int(header_match.group(4)),
                "impact_score": impact,
                "difficulty": diff,
                "foundation": found,
                "repo": "",
                "explanation": "",
                "portfolio_rationale": "",
                "implementation_hint": "",
                "labels": []
            }
            continue
            
        repo_match = re.match(r"^\*\*Repository:\*\*\s+`(.*?)`", line)
        if repo_match and current_issue:
            current_issue["repo"] = repo_match.group(1)
            continue
            
        fit_match = re.match(r"^\*\*Why this fits you:\*\*\s+(.*)", line)
        if fit_match and current_issue:
            current_issue["explanation"] = fit_match.group(1)
            continue

        port_match = re.match(r"^\*\*Portfolio Uplift:\*\*\s+(.*)", line)
        if port_match and current_issue:
            current_issue["portfolio_rationale"] = port_match.group(1)
            continue
            
        hint_match = re.match(r"^\*\*Where to start:\*\*\s+(.*)", line)
        if hint_match and current_issue:
            current_issue["implementation_hint"] = hint_match.group(1)
            continue
            
    if current_issue:
        issues.append(current_issue)
        
    return issues

def display_latest_report():
    """Finds the most recent report in reports/ directory and displays it in the terminal."""
    report_files = sorted(glob.glob(os.path.join(REPORTS_DIR, "report_*.md")), reverse=True)
    if not report_files:
        console.print(Panel("No reports found in reports/ directory. Run `issuehawk --run-now` to generate one.", style="yellow"))
        return
        
    latest_file = report_files[0]
    filename = os.path.basename(latest_file)
    issues = parse_markdown_report_file(latest_file)
    
    console.print(f"[bold cyan]Displaying latest report:[/bold cyan] {filename} ({len(issues)} issues)")
    display_issue_table(issues, title=f"🦅 IssueHawk Report: {filename}")
