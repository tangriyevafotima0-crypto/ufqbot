"""Bot configuration - loads settings from .env file."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the same directory as this file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Directory for storing session data as JSON
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Maximum number of students per session
MAX_STUDENTS = 50
