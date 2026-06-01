import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from bot.config import BOT_TOKEN, SUPER_ADMIN_ID
from bot.database.db import init_db
from bot.database.crud import auto_close_events
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


async def auto_close_task(bot_instance):
    """Background task: close expired events every 5 minutes."""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            reports = await auto_close_events()
            for report in reports:
                # Build report message
                msg = (
                    f"<b>Tadbir yakunlandi!</b>\n\n"
                    f"{report['event_title']}\n"
                    f"Ro'yxatdan o'tganlar: {report['total_registered']}\n"
                    f"Qatnashganlar: {report['total_attended']}\n\n"
                    f"<b>Qatnashchilar:</b>\n"
                )
                for att in report.get('attendees', []):
                    msg += f"  - {att['name']} (+{att['points_given']} ball)\n"

                # Send to event creator
                if report.get('creator_tg_id'):
                    try:
                        await bot_instance.send_message(report['creator_tg_id'], msg, parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Report yuborishda xatolik (creator): {e}")

                # Send to SUPER_ADMIN
                try:
                    await bot_instance.send_message(SUPER_ADMIN_ID, msg, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Report yuborishda xatolik (admin): {e}")
        except Exception as e:
            logger.error(f"Auto-close task xatoligi: {e}")


async def main():
    global bot
    logger.info("Bot ishga tushmoqda...")

    # Database ni ishga tushirish
    await init_db()
    logger.info("Database tayyor.")

    from bot.config import BOT_USERNAME
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
    asyncio.create_task(auto_close_task(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot to'xtatildi.")
    except Exception as e:
        logger.error(f"Bot ishga tushishda xatolik: {e}")
