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
    """Runs the full upgraded IssueHawk agent pipeline with a clean Rich stepper."""
    dev_profile = load_profile(profile_path)
    
    # 1. Header Card
    skills_preview = ", ".join(dev_profile.skills[:4]) + ("..." if len(dev_profile.skills) > 4 else "")
    console.print()
    console.print(Panel(
        f"[bold white]Target Stack:[/bold white] [cyan]{skills_preview}[/cyan]\n"
        f"[bold white]Seniority:[/bold white] [green]{dev_profile.skill_level.capitalize()}[/green]  •  "
        f"[bold white]Threshold:[/bold white] [yellow]>={dev_profile.min_score}/10[/yellow]  •  "
        f"[bold white]Limit:[/bold white] [white]{dev_profile.max_results} issues[/white]",
        title=f"🦅 [bold]IssueHawk[/bold] — Curation Run: [bold cyan]{dev_profile.name}[/bold cyan]",
        border_style="blue",
        padding=(0, 2)
    ))
    console.print()

    # Step 1: Memory init & Scrape
    with console.status("[bold cyan][1/5] Collecting open issues across GitHub, goodfirstissue.dev, up-for-grabs..."):
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
                ttl_days=14
            )

    if not accepted_issues:
        console.print(f"  [yellow]⚠[/yellow] [3/5] All {len(unseen_issues)} unseen issues were filtered (claimed or inactive). Pipeline complete.")
        return
    console.print(f"  [green]✔[/green] [bold white][3/5] Triage complete:[/bold white] [cyan]{len(accepted_issues)}[/cyan] active candidates ([dim]{len(rejected_issues)} claimed/stale filtered[/dim]).")

    # Step 4: AI Scoring
    with console.status(f"[bold cyan][4/5] Scoring {len(accepted_issues)} issues with Gemini 2.5 Flash..."):
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
                    ttl_days=14
                )

    if not relevant_issues:
        console.print(f"  [yellow]⚠[/yellow] [4/5] No issues scored >= {min_score}/10 today. Negative-cache updated. Pipeline complete.")
        return

    top_issues = relevant_issues[:dev_profile.max_results]
    console.print(f"  [green]✔[/green] [bold white][4/5] AI Scoring complete:[/bold white] [cyan]{len(top_issues)}[/cyan] high-relevance opportunities curated.")

    # Step 5: Reports & Dispatch
    with console.status("[bold cyan][5/5] Generating reports and dispatching notifications..."):
        report_path, markdown_content = generate_markdown_report(top_issues, profile_name=dev_profile.name)
        date_str = datetime.now().strftime("%Y-%m-%d")
        subject = f"IssueHawk Report — {date_str} ({len(top_issues)} Opportunities)"
        email_success = send_email(subject, markdown_content, issues=top_issues, profile_name=dev_profile.name)
        dispatch_webhooks(top_issues, profile_name=dev_profile.name)

        if email_success:
            for issue in top_issues:
                record_evaluation(
                    issue,
                    status="emailed",
                    score=issue.get("score", 0),
                    explanation=issue.get("explanation", ""),
                    hint=issue.get("implementation_hint", "")
                )

    console.print(f"  [green]✔[/green] [bold white][5/5] Delivery complete:[/bold white] Report saved & dispatched via email/webhooks.")
    console.print()

    # Final Summary Table
    display_issue_table(top_issues, title=f"🦅 IssueHawk Run Complete • {len(top_issues)} Issues Curated for {dev_profile.name}")

def send_test_email():
    """Sends a rich newsletter test email containing real/sample curated issues."""
    console.print("[cyan]Sending full curated newsletter preview email via Resend...[/cyan]")
    dev_profile = load_profile()
    
    report_files = sorted(glob.glob(os.path.join(REPORTS_DIR, "report_*.md")), reverse=True)
    sample_issues = []
    if report_files:
        sample_issues = parse_markdown_report_file(report_files[0])
        
    if not sample_issues:
        sample_issues = [
            {
                "title": "Add async streaming support for LangGraph execution graphs in FastAPI worker nodes",
                "url": "https://github.com/langchain-ai/langgraph/issues/1124",
                "repo": "langchain-ai/langgraph",
                "score": 9,
                "difficulty": "intermediate",
                "explanation": "Directly matches your FastAPI and LangGraph stack. High impact with clear scope.",
                "implementation_hint": "Check `langgraph/pregel/runner.py` and inspect how `TaskStream` yields state chunks. Implement an async generator adapter.",
                "labels": ["good first issue", "enhancement"]
            },
            {
                "title": "Fix memory leak in RAG vector similarity cache during high concurrency",
                "url": "https://github.com/chroma-core/chroma/issues/2405",
                "repo": "chroma-core/chroma",
                "score": 8,
                "difficulty": "intermediate",
                "explanation": "Great fit for Python & RAG pipeline optimization with clear reproduction steps.",
                "implementation_hint": "Inspect the LRU eviction policy in `chromadb/segment/impl/vector/cache.py` to ensure expired keys release their underlying numpy arrays.",
                "labels": ["bug", "good first issue"]
            },
            {
                "title": "Add React 19 forwardRef migration codemod for UI component library",
                "url": "https://github.com/shadcn-ui/ui/issues/3902",
                "repo": "shadcn-ui/ui",
                "score": 7,
                "difficulty": "beginner",
                "explanation": "Matches your React frontend interests and clean architecture conventions.",
                "implementation_hint": "Look at `packages/cli/src/commands/migrate.ts` and apply the standard AST transform to remove forwardRef wrappers.",
                "labels": ["frontend", "help wanted"]
            }
        ]
        
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"IssueHawk Preview — {date_str} ({len(sample_issues)} Opportunities)"
    report_path, markdown_content = generate_markdown_report(sample_issues, profile_name=dev_profile.name)
    success = send_email(subject, markdown_content, issues=sample_issues, profile_name=dev_profile.name)
    if success:
        console.print(f"[bold green]✔ Full preview newsletter with {len(sample_issues)} curated issues sent successfully to {config.RECIPIENT_EMAIL}![/bold green]")
    else:
        console.print("[bold red]✖ Failed to send preview email. Please check your .env configuration.[/bold red]")

def test_webhooks():
    """Sends a test notification to configured webhooks."""
    console.print("[cyan]Testing configured webhooks...[/cyan]")
    sample_issues = [{
        "title": "IssueHawk Webhook Verification Test",
        "url": "https://github.com",
        "repo": "issuehawk/core",
        "score": 10,
        "difficulty": "intermediate",
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
    parser = argparse.ArgumentParser(description="IssueHawk — Autonomous GitHub Issue Curation Agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-now", action="store_true", help="Run the full pipeline immediately")
    group.add_argument("--schedule", action="store_true", help="Start the scheduler to run on the configured schedule")
    group.add_argument("--test-mail", action="store_true", help="Send a test email to verify Resend credentials")
    group.add_argument("--view", action="store_true", help="View the latest curated report in the terminal")
    group.add_argument("--stats", action="store_true", help="Display memory and deduplication statistics")
    group.add_argument("--test-webhooks", action="store_true", help="Test configured Discord/Slack webhooks")
    
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
