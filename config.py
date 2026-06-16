import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

# Schedule settings: default to everyday at 18:30 (6:30 PM) Asia/Kolkata
try:
    SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "18"))
except ValueError:
    SCHEDULE_HOUR = 18

try:
    SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "30"))
except ValueError:
    SCHEDULE_MINUTE = 30

SCHEDULE_DAY = os.getenv("SCHEDULE_DAY", "daily")
SCHEDULE_TIMEZONE = os.getenv("SCHEDULE_TIMEZONE", "Asia/Kolkata")
