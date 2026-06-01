import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from bot.config import BOT_TOKEN
from bot.database.db import init_db
from bot.handlers.start import start_router
from bot.handlers.user import user_router
from bot.handlers.events import events_router
from bot.handlers.admin import admin_router
from bot.handlers.scanner import scanner_router
from bot.middlewares.check_sub import CheckSubMiddleware

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global bot instance (scanner uchun kerak)
bot = None


async def main():
    global bot
    logger.info("Bot ishga tushmoqda...")

    # Database ni ishga tushirish
    await init_db()
    logger.info("Database tayyor.")

    from bot.config import BOT_USERNAME, SUPER_ADMIN_ID
    logger.info(f"Config: BOT_USERNAME='{BOT_USERNAME}', SUPER_ADMIN_ID={SUPER_ADMIN_ID}")

    # Bot va Dispatcher yaratish
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Middleware ulash
    dp.message.middleware(CheckSubMiddleware())
    dp.callback_query.middleware(CheckSubMiddleware())
    logger.info("Middleware ulandi.")

    # Router larni ulash (scanner birinchi bo'lishi kerak - deep link uchun)
    dp.include_router(scanner_router)
    dp.include_router(start_router)
    dp.include_router(user_router)
    dp.include_router(events_router)
    dp.include_router(admin_router)
    logger.info("Barcha router lar ulandi.")

    # Webhook ni o'chirish va polling ni boshlash
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Polling rejimida ishlamoqda...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot to'xtatildi.")
    except Exception as e:
        logger.error(f"Bot ishga tushishda xatolik: {e}")
