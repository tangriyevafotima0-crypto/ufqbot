from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart, CommandObject
from bot.database.crud import verify_and_checkin, get_user_by_tg_id, is_user_president, is_user_admin
import logging

scanner_router = Router()
logger = logging.getLogger(__name__)


@scanner_router.message(CommandStart(deep_link=True))
async def handle_deep_link(message: Message, command: CommandObject):
    """Deep link orqali QR skanerlash"""
    if not command.args:
        return

    args = command.args

    # NOTE: This handler catches ALL deep links. Only chk_ prefix is processed.
    # Non-chk_ deep links will get no response (no other deep link handlers exist).
    if not args.startswith("chk_"):
        return

    try:
        parts = args.split("_")
        if len(parts) < 4:
            return await message.answer("Noto'g'ri QR kod formati!")

        # Validate format
        if not parts[1].startswith('E') or not parts[2].startswith('U') or not parts[3].startswith('S'):
            return await message.answer("Noto'g'ri QR kod formati!")

        event_id_str = parts[1][1:]  # E12 -> 12
        user_tg_id_str = parts[2][1:]  # U987654321 -> 987654321
        # Remove 'S' prefix from first hash part, then join remaining (defensive)
        security_hash = parts[3][1:] + ("_" + "_".join(parts[4:]) if len(parts) > 4 else "")

        event_id = int(event_id_str)
        user_tg_id = int(user_tg_id_str)

        logger.info(
            f"QR SCAN: scanner={message.from_user.id}, raw_args='{args}', "
            f"event_id={event_id}, user_tg_id={user_tg_id}, hash='{security_hash[:6]}...'"
        )

        success, msg, extra = await verify_and_checkin(
            security_hash=security_hash,
            event_id=event_id,
            scanner_tg_id=message.from_user.id,
            expected_user_tg_id=user_tg_id  # BUG #2 FIX
        )

        if success:
            await message.answer(
                f"<b>CHECK-IN MUVAFFAQIYATLI!</b>\n\n{msg}",
                parse_mode="HTML"
            )

            # BUG #8 FIX: Foydalanuvchiga alohida, tushunarli xabar yuborish
            try:
                if extra and extra.get('user_tg_id'):
                    await message.bot.send_message(
                        extra['user_tg_id'],
                        extra['user_notify_msg'],
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.error(f"Foydalanuvchiga xabar yuborishda xatolik: {e}")
        else:
            await message.answer(msg, parse_mode="HTML")

    except (ValueError, IndexError) as e:
        logger.error(f"Deep link parsing xatoligi: {e}")
        await message.answer("Noto'g'ri QR kod formati!")
    except Exception as e:
        logger.error(f"Check-in xatoligi: {e}")
        await message.answer(f"Xatolik yuz berdi: {str(e)}")


@scanner_router.message(Command("scan"))
async def scan_command(message: Message):
    """Skanerlash boshlash komandasi"""
    is_admin = await is_user_admin(message.from_user.id)
    is_pres = await is_user_president(message.from_user.id)

    if not is_admin and not is_pres:
        return await message.answer("Sizda skanerlash huquqi yo'q!")

    await message.answer(
        "<b>QR-Kod Skanerlash</b>\n\n"
        "Foydalanuvchining chiptasidagi QR-kodni telefon kamerangiz bilan skanerlang.\n\n"
        "<i>Telefon kamerasini QR-kodga tutganingizda, Telegram avtomatik ravishda "
        "havolani ochadi va bot skanerlashni amalga oshiradi.</i>",
        parse_mode="HTML"
    )


@scanner_router.message(Command("mytickets"))
async def my_tickets_command(message: Message):
    """Foydalanuvchining barcha chiptalarini ko'rsatish"""
    from bot.database.db import AsyncSessionLocal
    from sqlalchemy.future import select
    from bot.database.models import Ticket, Event
    from bot.database.crud import get_db

    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        return await message.answer("Foydalanuvchi topilmadi!")

    async with AsyncSessionLocal() as session:
        tickets_result = await session.execute(
            select(Ticket, Event)
            .join(Event)
            .where(Ticket.user_id == user['id'])
            .order_by(Ticket.generated_at.desc())
        )
        tickets = tickets_result.all()

        if not tickets:
            return await message.answer("Sizda hali chiptalar yo'q.")

        # Get club name
        club_name = "UFQ Community"
        if user.get('club_id'):
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT name FROM clubs WHERE id=?", (user['club_id'],)
                )
                club_row = await cursor.fetchone()
                if club_row:
                    club_name = club_row['name']

        for ticket, event in tickets:
            status_text = "Ishlatilgan" if ticket.is_used else "Faol"
            used_info = ""
            if ticket.is_used and ticket.used_at:
                used_info = f"\nSkanerlangan: {ticket.used_at.strftime('%d.%m.%Y %H:%M')}"

            caption = (
                f"<b>Chipta</b>\n\n"
                f"<b>Tadbir:</b> {event.title}\n"
                f"<b>PIN:</b> <code>{ticket.ticket_pin}</code>\n"
                f"<b>Status:</b> {status_text}{used_info}\n\n"
                f"<i>Bu chiptani tadbir kirishida ko'rsating.</i>"
            )

            try:
                from bot.utils.ticket_generator import generate_ticket_image
                event_date = event.event_date.strftime("%d-%b, %H:%M") if event.event_date else "Tez orada"

                ticket_image = await generate_ticket_image(
                    user_full_name=user['full_name'],
                    user_points=user.get('total_points', 0),
                    event_title=event.title,
                    event_date=event_date,
                    club_name=club_name,
                    pin=ticket.ticket_pin,
                    qr_data=ticket.qr_data
                )

                from aiogram.types import BufferedInputFile
                photo = BufferedInputFile(ticket_image.read(), filename="ticket.png")
                await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Chipta rasmini generatsiya qilishda xatolik: {e}")
                await message.answer(caption, parse_mode="HTML")
