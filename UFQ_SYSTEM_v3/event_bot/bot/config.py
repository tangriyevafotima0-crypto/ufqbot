import os
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("CRITICAL ERROR: BOT_TOKEN is missing!")

try:
    SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", 0))
    if SUPER_ADMIN_ID <= 0:
        raise ValueError("CRITICAL ERROR: SUPER_ADMIN_ID is invalid!")
except ValueError:
    raise ValueError("CRITICAL ERROR: SUPER_ADMIN_ID must be a valid integer!")

CHANNELS_RAW = os.getenv("CHANNELS", "")
CHANNELS = [ch.strip() for ch in CHANNELS_RAW.split(",") if ch.strip()]

if not CHANNELS:
    logger.warning("OGOHLANTIRISH: CHANNELS bo'sh! Kanal autentifikatsiyasi o'chirilgan.")

DB_PATH = os.getenv("DB_PATH", "/home/ubuntu/UFQ_SYSTEM/shared/ufq_system.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# BOT_USERNAME faqat zaxira sifatida. Haqiqiy username runtime'da bot.get_me() orqali aniqlanadi.
BOT_USERNAME = os.getenv("BOT_USERNAME", "ufq_events_bot")
