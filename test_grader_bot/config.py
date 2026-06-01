"""Bot configuration - loads settings from .env file."""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from the same directory as this file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Multi-admin support: ADMIN_IDS as comma-separated values
# Falls back to single ADMIN_ID for backward compatibility
_admin_ids_raw = os.getenv("ADMIN_IDS", "")
if not _admin_ids_raw.strip():
    # Fallback to ADMIN_ID (single value) for backward compatibility
    _admin_id_raw = os.getenv("ADMIN_ID", "0")
    try:
        _fallback = int(_admin_id_raw.strip())
        ADMIN_IDS = [_fallback] if _fallback != 0 else []
    except (ValueError, TypeError):
        ADMIN_IDS = []
else:
    # Parse comma-separated list
    ADMIN_IDS = []
    for part in _admin_ids_raw.split(","):
        part = part.strip()
        if part:
            try:
                ADMIN_IDS.append(int(part))
            except (ValueError, TypeError):
                logger.warning("Skipping invalid ADMIN_ID entry: %s", part)

# Directory for storing session data as JSON
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Directory for shared test storage
TESTS_DIR = DATA_DIR / "tests"
TESTS_DIR.mkdir(exist_ok=True)

# Maximum number of students per session
MAX_STUDENTS = 50

# Version identifier
VERSION = "V6"
