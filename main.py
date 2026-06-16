import argparse
import sys
import logging
import os
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

import config
from tools.scraper import collect_all_issues
from tools.memory import is_duplicate, mark_as_processed, init_db
from tools.llm import score_issues
from tools.reporter import generate_markdown_report
from tools.mailer import send_email

# Configure Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("issuehawk")

def run_pipeline():
    """Runs the full IssueHawk agent pipeline."""
    logger.info("--- Starting IssueHawk Pipeline Run ---")
    
    # 1. Initialize memory DB
    init_db()
    
    # 2. Collect issues from all sources
    raw_issues = collect_all_issues()
    if not raw_issues:
        logger.info("No raw issues found during scrape. Pipeline finished.")
        return
        
    # 3. Deduplicate against memory
    new_issues = []
    for issue in raw_issues:
        url = issue.get("url")
        if url and not is_duplicate(url):
            new_issues.append(issue)
            
    logger.info(f"Deduplication complete. {len(new_issues)} new issues of {len(raw_issues)} raw issues.")
    if not new_issues:
        logger.info("No new issues to process. Pipeline finished.")
        return
        
    # 4. Score issues using Gemini
    logger.info("Scoring new issues with Gemini...")
    scored_issues = score_issues(new_issues)
    
    # 5. Filter and Rank issues
    # Filter out low relevance issues (score < 5) and rank descending
    relevant_issues = [issue for issue in scored_issues if issue.get("score", 0) >= 5]
    logger.info(f"Filtered {len(scored_issues)} issues to {len(relevant_issues)} with score >= 5.")
    
    if not relevant_issues:
        logger.info("No issues passed the relevance threshold (score >= 5). Pipeline finished.")
        return
        
    # Keep top 15 ranked issues
    top_issues = relevant_issues[:15]
    
    # 6. Generate report
    logger.info("Generating report...")
    report_path, markdown_content = generate_markdown_report(top_issues)
    
    # 7. Deliver report email
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"IssueHawk Report — {date_str} ({len(top_issues)} Issues)"
    
    email_success = send_email(subject, markdown_content)
    
    # 8. Update Memory DB for emailed issues
    if email_success:
        logger.info("Updating memory with mailed issues...")
        for issue in top_issues:
            mark_as_processed(issue, status="emailed")
        logger.info("Pipeline executed successfully and memory updated.")
    else:
        logger.error("Failed to send email report. Memory was not updated.")

def send_test_email():
    """Sends a quick test email to verify Resend setup."""
    logger.info("Sending test email...")
    test_md = """# IssueHawk Test Report
This is a test notification from your IssueHawk agent.

* **Status:** Success
* **Resend Configuration:** Verified
* **Time Sent:** {}
""".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    success = send_email("IssueHawk — Test Verification", test_md)
    if success:
        logger.info("Test email sent successfully!")
    else:
        logger.error("Failed to send test email. Please check your .env configuration.")

def main():
    parser = argparse.ArgumentParser(description="IssueHawk — Autonomous GitHub Issue Curation Agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-now", action="store_true", help="Run the full pipeline immediately")
    group.add_argument("--schedule", action="store_true", help="Start the scheduler to run on the configured schedule")
    group.add_argument("--test-mail", action="store_true", help="Send a test email to verify Resend credentials")
    
    args = parser.parse_args()
    
    # Verify environment
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
        run_pipeline()
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
            trigger="cron",
            **cron_kwargs
        )
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")

if __name__ == "__main__":
    main()
