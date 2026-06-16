import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

# Schedule settings: default to Mon 8:00 AM if not set
try:
    SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "8"))
except ValueError:
    SCHEDULE_HOUR = 8

SCHEDULE_DAY = os.getenv("SCHEDULE_DAY", "mon")
