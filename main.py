import argparse
import sys
import logging
import os
import glob
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from rich.console import Console
from rich.panel import Panel

import config
from tools.profile import load_profile
from tools.scraper import collect_all_issues
from tools.memory import is_duplicate, record_evaluation, init_db, get_memory_stats
from tools.triage import triage_issues
from tools.llm import score_issues
from tools.reporter import generate_markdown_report
from tools.mailer import send_email
from tools.dispatchers import dispatch_webhooks
from tools.viewer import display_latest_report, display_issue_table, parse_markdown_report_file, REPORTS_DIR
from tools.evolution import (
    get_developer_status,
    record_completed_issue,
    sync_github_activity,
    format_progress_panel
)

console = Console()

def setup_logging(verbose: bool = False):
    """Configures clean, professional logging without terminal spam."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "issuehawk.log")

    # File logger captures all detailed debug information
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(file_formatter)

    # Console logger only shows warnings/errors unless verbose mode is enabled
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console_formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    console_handler.setFormatter(console_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers = [file_handler, console_handler]

    # Suppress verbose noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger("issuehawk")

def run_pipeline(profile_path=None, force: bool = False):
    """Runs the full upgraded IssueHawk career acceleration pipeline."""
    dev_profile = load_profile(profile_path)
    dev_status = get_developer_status(dev_profile)
    
    # 1. Header Card with progression info
    skills_preview = ", ".join(dev_profile.skills[:4]) + ("..." if len(dev_profile.skills) > 4 else "")
    foundations_preview = ", ".join([f.upper() for f in dev_profile.target_foundations])
    console.print()
    console.print(Panel(
        f"[bold white]Target Stack:[/bold white] [cyan]{skills_preview}[/cyan]\n"
        f"[bold white]Progression:[/bold white] [{dev_status['color']}]{dev_status['badge']}[/{dev_status['color']}]  •  "
        f"[bold white]Career Track:[/bold white] [yellow]{dev_profile.track.replace('_', ' ').title()}[/yellow]\n"
        f"[bold white]Target Foundations:[/bold white] [magenta]{foundations_preview}[/magenta]  •  "
        f"[bold white]Min Score:[/bold white] [green]>={dev_profile.min_score}/10[/green]  •  "
        f"[bold white]Limit:[/bold white] [white]{dev_profile.max_results} issues[/white]",
        title=f"🦅 [bold]IssueHawk[/bold] — High-Impact Curation: [bold cyan]{dev_profile.name}[/bold cyan]",
        border_style=dev_status["color"],
        padding=(0, 2)
    ))
    console.print()

    # Step 1: Memory init & Scrape
    with console.status(f"[bold cyan][1/5] Collecting open issues across Foundations ({foundations_preview}) & GitHub..."):
        init_db()
        raw_issues = collect_all_issues(profile=dev_profile)

    if not raw_issues:
        console.print("  [yellow]⚠[/yellow] [1/5] No open issues found across sources today. Pipeline complete.")
        return
    console.print(f"  [green]✔[/green] [bold white][1/5] Scraped candidate issues:[/bold white] [cyan]{len(raw_issues)}[/cyan] found.")

    # Step 2: Deduplication
    with console.status("[bold cyan][2/5] Deduplicating against memory cache..."):
        unseen_issues = []
        for issue in raw_issues:
            url = issue.get("url")
            if url and (force or not is_duplicate(url)):
                unseen_issues.append(issue)

    cached_count = len(raw_issues) - len(unseen_issues)
    if not unseen_issues:
        console.print(f"  [green]✔[/green] [bold white][2/5] Deduplication:[/bold white] All [cyan]{cached_count}[/cyan] issues already cached in memory. Nothing new to process.")
        console.print("  [dim]Tip: Use --force to re-evaluate cached candidate issues and dispatch an updated report.[/dim]")
        return
    if force:
        console.print(f"  [yellow]⚡[/yellow] [bold white][2/5] Deduplication (Force Mode):[/bold white] Bypassed memory cache for all [cyan]{len(unseen_issues)}[/cyan] candidates.")
    else:
        console.print(f"  [green]✔[/green] [bold white][2/5] Deduplication complete:[/bold white] [cyan]{len(unseen_issues)}[/cyan] unseen ([dim]{cached_count} cached in memory[/dim]).")

    # Step 3: Triage
    with console.status("[bold cyan][3/5] Triaging candidates (active repos & claimed checks)..."):
        accepted_issues, rejected_issues = triage_issues(
            unseen_issues,
            filter_claimed=dev_profile.filter_claimed,
            filter_inactive=dev_profile.filter_inactive_repos
        )
        for rej in rejected_issues:
            record_evaluation(
                rej,
                status=rej.get("rejection_status", "claimed"),
                score=0,
                explanation=rej.get("rejection_reason", "Filtered during triage"),
                ttl_days=14,
                foundation=rej.get("foundation", "")
            )

    if not accepted_issues:
        console.print(f"  [yellow]⚠[/yellow] [3/5] All {len(unseen_issues)} unseen issues were filtered (claimed or inactive). Pipeline complete.")
        return
    console.print(f"  [green]✔[/green] [bold white][3/5] Triage complete:[/bold white] [cyan]{len(accepted_issues)}[/cyan] active candidates ([dim]{len(rejected_issues)} claimed/stale filtered[/dim]).")

    # Step 4: AI Scoring with High-Impact Portfolio Rubric
    with console.status(f"[bold cyan][4/5] Scoring {len(accepted_issues)} issues with High-Impact Portfolio Rubric..."):
        scored_issues = score_issues(accepted_issues, profile=dev_profile)
        min_score = dev_profile.min_score
        relevant_issues = []
        for issue in scored_issues:
            score = issue.get("score", 0)
            if score >= min_score:
                relevant_issues.append(issue)
            else:
                record_evaluation(
                    issue,
                    status="skipped_low_score",
                    score=score,
                    explanation=issue.get("explanation", "Below relevance threshold"),
                    hint=issue.get("implementation_hint", ""),
                    impact_score=issue.get("impact_score", 0),
                    portfolio_rationale=issue.get("portfolio_rationale", ""),
                    foundation=issue.get("foundation", ""),
                    ttl_days=14
                )

    if not relevant_issues:
        console.print(f"  [yellow]⚠[/yellow] [4/5] No issues scored >= {min_score}/10 today. Negative-cache updated. Pipeline complete.")
        return

    top_issues = relevant_issues[:dev_profile.max_results]
    console.print(f"  [green]✔[/green] [bold white][4/5] AI Scoring complete:[/bold white] [cyan]{len(top_issues)}[/cyan] high-impact opportunities curated.")

    # Step 5: Reports & Dispatch
    with console.status("[bold cyan][5/5] Generating reports and dispatching notifications..."):
        report_path, markdown_content = generate_markdown_report(top_issues, profile_name=dev_profile.name)
        date_str = datetime.now().strftime("%Y-%m-%d")
        tier_title = dev_status['tier'].replace('_', ' ').title()
        subject = f"IssueHawk [{tier_title}] Report — {date_str} ({len(top_issues)} High-Impact Opportunities)"
        email_success = send_email(subject, markdown_content, issues=top_issues, profile_name=dev_profile.name)
        dispatch_webhooks(top_issues, profile_name=dev_profile.name)

        if email_success:
            for issue in top_issues:
                record_evaluation(
                    issue,
                    status="emailed",
                    score=issue.get("score", 0),
                    explanation=issue.get("explanation", ""),
                    hint=issue.get("implementation_hint", ""),
                    impact_score=issue.get("impact_score", 0),
                    portfolio_rationale=issue.get("portfolio_rationale", ""),
                    foundation=issue.get("foundation", "")
                )

    console.print(f"  [green]✔[/green] [bold white][5/5] Delivery complete:[/bold white] Report saved & dispatched via email/webhooks.")
    console.print()

    # Final Summary Table
    display_issue_table(top_issues, title=f"🦅 IssueHawk Run Complete • {len(top_issues)} Opportunities for {dev_profile.name}")

def show_progress(profile_path=None):
    """Displays developer progression status panel."""
    dev_profile = load_profile(profile_path)
    status = get_developer_status(dev_profile)
    console.print()
    console.print(format_progress_panel(status))
    console.print()

def complete_contribution(url: str, title: str = "", repo: str = "", difficulty: str = "intermediate"):
    """Records a completed issue contribution and awards XP."""
    res = record_completed_issue(url, title=title, repo=repo, difficulty=difficulty)
    console.print()
    console.print(f"[bold green]✔ Issue marked as completed![/bold green] [cyan]{res['url']}[/cyan]")
    console.print(f"• Awarded [bold yellow]+{res['xp_gained']} XP[/bold yellow] (Total XP: [bold cyan]{res['total_xp']}[/bold cyan])")
    if res["graduated"]:
        console.print(f"[bold magenta]🎉 CONGRATULATIONS! You graduated from {res['old_tier']} to {res['new_tier'].upper()}![/bold magenta]")
    else:
        console.print(f"• Current Tier: [bold cyan]{res['new_tier'].replace('_', ' ').title()}[/bold cyan]")
    console.print()

def sync_profile(username: str = None):
    """Syncs merged PRs from GitHub to update progression."""
    console.print("[cyan]Syncing contributions from GitHub API...[/cyan]")
    res = sync_github_activity(username=username)
    if not res.get("success"):
        console.print(f"[bold red]✖ {res.get('message')}[/bold red]")
        return
        
    console.print(f"[bold green]✔ Successfully synced with @{res['username']}![/bold green]")
    console.print(f"• Total Merged PRs on GitHub: [bold cyan]{res['total_merged_prs']}[/bold cyan]")
    if res['new_prs'] > 0:
        console.print(f"• Detected [bold green]{res['new_prs']} new merged PR(s)[/bold green] (+{res['xp_boost']} XP awarded!)")
    else:
        console.print("• No new merged PRs since last sync.")
    console.print(f"• Total XP: [bold yellow]{res['total_xp']}[/bold yellow] • Tier: [bold cyan]{res['tier'].replace('_', ' ').title()}[/bold cyan]")
    if res.get("graduated"):
        console.print(f"[bold magenta]🎉 PROMOTION: You graduated to {res['tier'].upper()}![/bold magenta]")
    console.print()

def send_test_email():
    """Sends a rich newsletter test email containing premier foundation & high-impact curated issues."""
    console.print("[cyan]Sending high-impact curated newsletter preview email via Resend...[/cyan]")
    dev_profile = load_profile()
    
    report_files = sorted(glob.glob(os.path.join(REPORTS_DIR, "report_*.md")), reverse=True)
    sample_issues = []
    if report_files:
        sample_issues = parse_markdown_report_file(report_files[0])
        
    if not sample_issues:
        sample_issues = [
            {
                "title": "Implement adaptive rate-limiting and retry backoff for distributed streaming runner",
                "url": "https://github.com/kubernetes/kubernetes/issues/112450",
                "repo": "kubernetes/kubernetes",
                "foundation": "CNCF",
                "score": 10,
                "impact_score": 9,
                "difficulty": "advanced",
                "portfolio_rationale": "High-visibility CNCF subsystem contribution demonstrating distributed systems and concurrency expertise.",
                "explanation": "Directly targets high-impact cloud-native systems architecture. Exceptional portfolio uplift for LFX Mentorship.",
                "implementation_hint": "Inspect `pkg/controller/daemon/` and analyze how work queues handle token replenishment under network throttling.",
                "labels": ["help wanted", "enhancement", "sig/node"]
            },
            {
                "title": "Add async streaming support for LangGraph execution graphs in FastAPI worker nodes",
                "url": "https://github.com/langchain-ai/langgraph/issues/1124",
                "repo": "langchain-ai/langgraph",
                "foundation": "GSoC",
                "score": 9,
                "impact_score": 8,
                "difficulty": "intermediate",
                "portfolio_rationale": "Strong showcase of modern Python async workflows, agent architectures, and ecosystem integration.",
                "explanation": "Directly matches your FastAPI and LangGraph stack. High impact with clear scope.",
                "implementation_hint": "Check `langgraph/pregel/runner.py` and inspect how `TaskStream` yields state chunks. Implement an async generator adapter.",
                "labels": ["help wanted", "enhancement"]
            },
            {
                "title": "Optimize Arrow IPC deserialization zero-copy memory buffers for columnar queries",
                "url": "https://github.com/apache/arrow/issues/39021",
                "repo": "apache/arrow",
                "foundation": "Apache",
                "score": 9,
                "impact_score": 9,
                "difficulty": "advanced",
                "portfolio_rationale": "Benchmark Apache Software Foundation issue demonstrating deep low-level memory efficiency and data systems design.",
                "explanation": "Ideal for showcasing high-performance backend engineering on Apache infrastructure.",
                "implementation_hint": "Look into `cpp/src/arrow/ipc/reader.cc` and verify buffer alignment in SIMD vector paths.",
                "labels": ["help wanted", "performance"]
            }
        ]
        
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"IssueHawk High-Impact Preview — {date_str} ({len(sample_issues)} Opportunities)"
    report_path, markdown_content = generate_markdown_report(sample_issues, profile_name=dev_profile.name)
    success = send_email(subject, markdown_content, issues=sample_issues, profile_name=dev_profile.name)
    if success:
        console.print(f"[bold green]✔ High-impact preview newsletter with {len(sample_issues)} curated issues sent successfully to {config.RECIPIENT_EMAIL}![/bold green]")
    else:
        console.print("[bold red]✖ Failed to send preview email. Please check your .env configuration.[/bold red]")

def test_webhooks():
    """Sends a test notification to configured webhooks."""
    console.print("[cyan]Testing configured webhooks...[/cyan]")
    sample_issues = [{
        "title": "IssueHawk High-Impact Webhook Verification Test",
        "url": "https://github.com/kubernetes/kubernetes",
        "repo": "kubernetes/kubernetes",
        "foundation": "CNCF",
        "score": 10,
        "impact_score": 9,
        "difficulty": "advanced",
        "portfolio_rationale": "High-impact cloud-native contribution anchor for LFX Mentorship.",
        "explanation": "This is a test event confirming your webhook integration is operational.",
        "implementation_hint": "No action required — your IssueHawk dispatch pipeline is ready."
    }]
    results = dispatch_webhooks(sample_issues, profile_name="Webhook Test")
    if not results:
        console.print("[yellow]No webhook URLs configured. Set DISCORD_WEBHOOK_URL or SLACK_WEBHOOK_URL in .env to enable.[/yellow]")
    else:
        for channel, status in results.items():
            color = "green" if status else "red"
            console.print(f"[{color}]Webhook {channel.upper()}: {'Success' if status else 'Failed'}[/{color}]")

def show_stats():
    """Displays SQLite memory and cache statistics."""
    stats = get_memory_stats()
    content = (
        f"[bold cyan]Database Location:[/bold cyan] {stats['db_path']}\n\n"
        f"• [bold white]Total Tracked Issues:[/bold white] {stats['total_tracked']}\n"
        f"• [bold green]Emailed (Permanent Dedupe):[/bold green] {stats['emailed']}\n"
        f"• [bold yellow]Skipped (Low Score Negative-Cache):[/bold yellow] {stats['skipped_low_score']}\n"
        f"• [bold magenta]Claimed / In-Progress Filtered:[/bold magenta] {stats['claimed']}\n"
        f"• [bold red]Inactive Repos Filtered:[/bold red] {stats['inactive_repo']}\n"
    )
    console.print(Panel(content, title="🦅 IssueHawk Memory Statistics", border_style="cyan"))

def main():
    parser = argparse.ArgumentParser(description="IssueHawk — Autonomous Career Accelerator for Open-Source & Mentorships (LFX/GSoC)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-now", action="store_true", help="Run the full pipeline immediately")
    group.add_argument("--schedule", action="store_true", help="Start the scheduler to run on the configured schedule")
    group.add_argument("--test-mail", action="store_true", help="Send a test email to verify Resend credentials")
    group.add_argument("--view", action="store_true", help="View the latest curated report in the terminal")
    group.add_argument("--stats", action="store_true", help="Display memory and deduplication statistics")
    group.add_argument("--test-webhooks", action="store_true", help="Test configured Discord/Slack webhooks")
    group.add_argument("--progress", action="store_true", help="Display developer progression tier, XP, and milestones")
    group.add_argument("--complete", type=str, metavar="URL", help="Mark an issue URL as completed to gain XP and graduate tier")
    group.add_argument("--sync-profile", action="store_true", help="Sync merged PRs from GitHub to update XP and tier")
    
    parser.add_argument("--username", type=str, default=None, help="GitHub username for profile sync")
    parser.add_argument("--profile", type=str, default=None, help="Path to custom profile.yaml file")
    parser.add_argument("--force", action="store_true", help="Bypass memory cache deduplication and force evaluation of all scraped issues")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging in terminal")
    
    args = parser.parse_args()
    setup_logging(verbose=args.verbose)
    
    if args.view:
        display_latest_report()
        return
    elif args.stats:
        show_stats()
        return
    elif args.test_webhooks:
        test_webhooks()
        return
    elif args.progress:
        show_progress(profile_path=args.profile)
        return
    elif args.complete:
        complete_contribution(url=args.complete)
        return
    elif args.sync_profile:
        sync_profile(username=args.username)
        return
        
    if not config.GEMINI_API_KEY:
        console.print("[bold red]GEMINI_API_KEY environment variable is missing.[/bold red]")
        sys.exit(1)
    if not config.RESEND_API_KEY:
        console.print("[bold red]RESEND_API_KEY environment variable is missing.[/bold red]")
        sys.exit(1)
    if not config.RECIPIENT_EMAIL:
        console.print("[bold red]RECIPIENT_EMAIL environment variable is missing in config/environment.[/bold red]")
        sys.exit(1)
        
    if args.run_now:
        run_pipeline(profile_path=args.profile, force=args.force)
    elif args.test_mail:
        send_test_email()
    elif args.schedule:
        console.print(
            f"[cyan]Starting scheduler on {config.SCHEDULE_DAY} at {config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d} ({config.SCHEDULE_TIMEZONE})[/cyan]"
        )
        scheduler = BlockingScheduler(timezone=config.SCHEDULE_TIMEZONE)
        cron_kwargs = {"hour": config.SCHEDULE_HOUR, "minute": config.SCHEDULE_MINUTE}
        if config.SCHEDULE_DAY not in ("daily", "*"):
            cron_kwargs["day_of_week"] = config.SCHEDULE_DAY
            
        scheduler.add_job(run_pipeline, args=[args.profile], trigger="cron", **cron_kwargs)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            console.print("[yellow]Scheduler stopped.[/yellow]")

if __name__ == "__main__":
    main()
