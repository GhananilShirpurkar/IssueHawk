import argparse
import sys
import logging
import os
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
from tools.viewer import display_latest_report, display_issue_table

# Configure Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("issuehawk")
console = Console()

def run_pipeline(profile_path=None):
    """Runs the full upgraded IssueHawk agent pipeline."""
    dev_profile = load_profile(profile_path)
    logger.info(f"--- Starting IssueHawk Pipeline Run for '{dev_profile.name}' ({dev_profile.skill_level}) ---")
    
    # 1. Initialize memory DB
    init_db()
    
    # 2. Collect issues from all sources using profile filters
    raw_issues = collect_all_issues(profile=dev_profile)
    if not raw_issues:
        logger.info("No raw issues found during scrape. Pipeline finished.")
        return
        
    # 3. Deduplicate against memory cache (checks permanent emailed + 14-day negative cache)
    unseen_issues = []
    for issue in raw_issues:
        url = issue.get("url")
        if url and not is_duplicate(url):
            unseen_issues.append(issue)
            
    logger.info(f"Deduplication complete. {len(unseen_issues)} unseen issues of {len(raw_issues)} raw issues.")
    if not unseen_issues:
        logger.info("No new issues to process. All issues are already cached in memory. Pipeline finished.")
        return
        
    # 4. Triage: Filter out claimed issues and inactive repositories
    accepted_issues, rejected_issues = triage_issues(
        unseen_issues,
        filter_claimed=dev_profile.filter_claimed,
        filter_inactive=dev_profile.filter_inactive_repos
    )
    
    # Memorize rejected issues in negative-cache with 14-day TTL
    for rej in rejected_issues:
        record_evaluation(
            rej,
            status=rej.get("rejection_status", "claimed"),
            score=0,
            explanation=rej.get("rejection_reason", "Filtered during triage"),
            ttl_days=14
        )
        
    if not accepted_issues:
        logger.info("All unseen issues were filtered out during triage. Pipeline finished.")
        return
        
    # 5. Score remaining issues with Gemini using dynamic profile
    logger.info(f"Scoring {len(accepted_issues)} candidate issues with Gemini...")
    scored_issues = score_issues(accepted_issues, profile=dev_profile)
    
    # 6. Filter by relevance threshold and negative-cache low-scoring issues
    min_score = dev_profile.min_score
    relevant_issues = []
    for issue in scored_issues:
        score = issue.get("score", 0)
        if score >= min_score:
            relevant_issues.append(issue)
        else:
            # Negative cache low-scoring issue for 14 days to prevent re-scoring tomorrow
            record_evaluation(
                issue,
                status="skipped_low_score",
                score=score,
                explanation=issue.get("explanation", "Below relevance threshold"),
                hint=issue.get("implementation_hint", ""),
                ttl_days=14
            )
            
    logger.info(f"Filtered {len(scored_issues)} issues to {len(relevant_issues)} with score >= {min_score}.")
    if not relevant_issues:
        logger.info(f"No issues passed the relevance threshold (score >= {min_score}). Pipeline finished.")
        return
        
    # Keep top ranked issues up to max_results
    top_issues = relevant_issues[:dev_profile.max_results]
    
    # 7. Generate report (Markdown archive)
    logger.info("Generating report...")
    report_path, markdown_content = generate_markdown_report(top_issues, profile_name=dev_profile.name)
    
    # 8. Deliver report via Email (Resend)
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"IssueHawk Report — {date_str} ({len(top_issues)} Opportunities)"
    email_success = send_email(subject, markdown_content, issues=top_issues, profile_name=dev_profile.name)
    
    # 9. Deliver report via Webhooks (Discord / Slack if configured)
    webhook_results = dispatch_webhooks(top_issues, profile_name=dev_profile.name)
    if webhook_results:
        logger.info(f"Webhook dispatch results: {webhook_results}")
        
    # 10. Update Memory DB for emailed issues (permanent mark)
    if email_success:
        logger.info("Updating memory with mailed issues...")
        for issue in top_issues:
            record_evaluation(
                issue,
                status="emailed",
                score=issue.get("score", 0),
                explanation=issue.get("explanation", ""),
                hint=issue.get("implementation_hint", "")
            )
        logger.info("Pipeline executed successfully and memory updated.")
    else:
        logger.warning("Email report was not delivered. Check Resend configuration.")
        
    # 11. Print Rich Terminal Summary
    console.print()
    display_issue_table(top_issues, title=f"🦅 IssueHawk Run Complete • {len(top_issues)} Issues Curated for {dev_profile.name}")

def send_test_email():
    """Sends a quick test email to verify Resend setup."""
    logger.info("Sending test email...")
    test_md = f"""# IssueHawk Test Report
This is a test notification from your upgraded IssueHawk agent.

* **Status:** Success
* **Resend Configuration:** Verified
* **Time Sent:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
    success = send_email("IssueHawk — Test Verification", test_md)
    if success:
        logger.info("Test email sent successfully!")
    else:
        logger.error("Failed to send test email. Please check your .env configuration.")

def test_webhooks():
    """Sends a test notification to configured webhooks."""
    logger.info("Testing webhooks...")
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
    
    args = parser.parse_args()
    
    # Handlers that do not require full credentials
    if args.view:
        display_latest_report()
        return
    elif args.stats:
        show_stats()
        return
    elif args.test_webhooks:
        test_webhooks()
        return
        
    # Verify environment for live pipelines
    if not config.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY environment variable is missing.")
        sys.exit(1)
    if not config.RESEND_API_KEY:
        logger.error("RESEND_API_KEY environment variable is missing.")
        sys.exit(1)
    if not config.RECIPIENT_EMAIL:
        logger.error("RECIPIENT_EMAIL environment variable is missing in config/environment.")
        sys.exit(1)
        
    if args.run_now:
        run_pipeline(profile_path=args.profile)
    elif args.test_mail:
        send_test_email()
    elif args.schedule:
        logger.info(
            f"Starting scheduler: trigger cron, day_of_week={config.SCHEDULE_DAY}, "
            f"time={config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d} ({config.SCHEDULE_TIMEZONE})"
        )
        scheduler = BlockingScheduler(timezone=config.SCHEDULE_TIMEZONE)
        
        cron_kwargs = {
            "hour": config.SCHEDULE_HOUR,
            "minute": config.SCHEDULE_MINUTE
        }
        if config.SCHEDULE_DAY not in ("daily", "*"):
            cron_kwargs["day_of_week"] = config.SCHEDULE_DAY
            
        scheduler.add_job(
            run_pipeline,
            args=[args.profile],
            trigger="cron",
            **cron_kwargs
        )
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")

if __name__ == "__main__":
    main()
