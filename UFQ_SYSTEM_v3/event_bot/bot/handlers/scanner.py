from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database.crud import scan_checkin, get_user_by_tg_id, is_user_president, is_user_admin
from bot.database.crud import checkin_by_pin
import logging

scanner_router = Router()
logger = logging.getLogger(__name__)


class ScanState(StatesGroup):
    waiting_for_pin = State()


@scanner_router.message(CommandStart(deep_link=True))
async def handle_deep_link(message: Message, command: CommandObject):
    """Deep link orqali QR skanerlash"""
    if not command.args:
        return

    args = command.args

    # Only process checkin_ prefix deep links
    if not args.startswith("checkin_"):
        return

    try:
        parts = args.split("_")
        # Format: checkin_{ticket_id}_{pin}
        if len(parts) < 3:
            return await message.answer("Noto'g'ri QR kod formati!")

        ticket_id = int(parts[1])
        pin = parts[2]

        logger.info(
            f"QR SCAN: scanner={message.from_user.id}, raw_args='{args}', "
            f"ticket_id={ticket_id}, pin='{pin[:3]}...'"
        )

        success, msg, extra = await scan_checkin(
            ticket_id=ticket_id,
            pin=pin,
            scanner_tg_id=message.from_user.id
        )

        if success:
            await message.answer(
                f"<b>CHECK-IN MUVAFFAQIYATLI!</b>\n\n{msg}",
                parse_mode="HTML"
            )

            # Send notification to ticket owner
            try:
                if extra and extra.get('user_tg_id'):
                    user_notify_msg = (
                        f"Siz check-in qilindingiz!\n\n"
                        f"Tadbir: {extra['event_title']}"
                    )
                    await message.bot.send_message(
                        extra['user_tg_id'],
                        user_notify_msg,
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
async def scan_command(message: Message, state: FSMContext):
    """Skanerlash boshlash komandasi"""
    is_admin = await is_user_admin(message.from_user.id)
    is_pres = await is_user_president(message.from_user.id)

    if not is_admin and not is_pres:
        return await message.answer("Sizda skanerlash huquqi yo'q!")

    await message.answer(
        "<b>QR-Kod Skanerlash</b>\n\n"
        "Variant 1: Foydalanuvchining QR-kodini telefon kamerangiz bilan skanerlang.\n\n"
        "Variant 2: Chiptadagi 6 xonali PIN kodni shu yerga yozing.\n\n"
        "Bekor qilish uchun /cancel bosing.",
        parse_mode="HTML"
    )
    await state.set_state(ScanState.waiting_for_pin)


@scanner_router.message(ScanState.waiting_for_pin)
async def process_pin_entry(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        return await message.answer("Bekor qilindi.")
    if not message.text or not message.text.strip().isdigit() or len(message.text.strip()) != 6:
        return await message.answer("Iltimos, 6 xonali PIN kodni kiriting yoki /cancel bosing.")

    pin = message.text.strip()
    success, msg, extra = await checkin_by_pin(pin=pin, scanner_tg_id=message.from_user.id)

    if success:
        await message.answer(f"<b>CHECK-IN MUVAFFAQIYATLI!</b>\n\n{msg}", parse_mode="HTML")
        try:
            if extra and extra.get('user_tg_id'):
                await message.bot.send_message(
                    extra['user_tg_id'],
                    f"Siz check-in qilindingiz!\n\nTadbir: {extra['event_title']}",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Foydalanuvchiga xabar yuborishda xatolik: {e}")
        await state.clear()
    else:
        # Keep state so they can retry, but show the error
        await message.answer(f"{msg}\n\nQayta urinib ko'ring yoki /cancel bosing.", parse_mode="HTML")


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
