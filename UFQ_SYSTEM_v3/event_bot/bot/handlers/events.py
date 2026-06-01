from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from bot.database.crud import get_active_events, register_user_for_event, create_ticket, get_user_by_tg_id, create_user
from bot.keyboards.menus import event_registration_keyboard
import html
import logging

events_router = Router()
logger = logging.getLogger(__name__)


@events_router.message(F.text == "Faol Tadbirlar")
async def show_active_events(message: Message):
    events = await get_active_events(limit=10)

    if not events:
        return await message.answer("Hozircha ochiq (faol) tadbirlar yo'q.")

    await message.answer("Quyida faol tadbirlar ro'yxati keltirilgan (eng so'nggi 10 ta):")

    import asyncio
    for i, event in enumerate(events):
        desc = html.escape(event.description) if event.description else "Tavsif yo'q"
        text = (
            f"<b>{html.escape(event.title)}</b>\n\n"
            f"{desc}\n"
            f"<i>Ro'yxatdan o'tish: +{event.registration_points} ball</i>\n"
            f"<i>Qatnashish: +{event.attendance_points} ball</i>"
        )
        await message.answer(
            text,
            reply_markup=event_registration_keyboard(event.id, event.post_link),
            parse_mode="HTML"
        )
        if (i + 1) % 20 == 0:
            await asyncio.sleep(1)


@events_router.callback_query(F.data.startswith("reg_event_"))
async def register_to_event(call: CallbackQuery):
    parts = call.data.split("_")
    if len(parts) < 3:
        return await call.answer("Noto'g'ri ma'lumot", show_alert=True)

    try:
        event_id = int(parts[2])
    except (ValueError, IndexError):
        return await call.answer("Tadbir ID noto'g'ri", show_alert=True)

    # Auto-create user if not in DB yet
    user = await get_user_by_tg_id(call.from_user.id)
    if not user:
        await create_user(
            telegram_id=call.from_user.id,
            full_name=call.from_user.full_name or "Foydalanuvchi",
            username=call.from_user.username,
            club_id=None
        )

    success, msg = await register_user_for_event(call.from_user.id, event_id)

    if success:
        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("Ro'yxatdan o'tdingiz!", show_alert=False)

        # Generate ticket
        try:
            ticket, ticket_image = await create_ticket(call.from_user.id, event_id)

            if ticket and ticket_image:
                photo = BufferedInputFile(ticket_image.read(), filename="ticket.png")
                await call.message.answer_photo(
                    photo=photo,
                    caption=(
                        "<b>Sizning chiptangiz tayyor!</b>\n\n"
                        "Bu chiptani tadbir kirishida ko'rsating.\n"
                        "QR-kodni admin skanerlaydi va sizga ball beriladi.\n\n"
                        f"PIN-kod: <code>{ticket.ticket_pin}</code>\n\n"
                        "<i>Chiptani yo'qotmang! Agar yo'qotilsa, botga /mytickets yozib qayta yuklab olishingiz mumkin.</i>"
                    ),
                    parse_mode="HTML"
                )
            else:
                logger.error(f"Chipta yaratishda xatolik: {ticket_image}")
                await call.message.answer("Ro'yxatdan o'tdingiz, lekin chiptani generatsiya qilishda xatolik yuz berdi.")
        except Exception as e:
            logger.error(f"Chipta generatsiya xatoligi: {e}")
            await call.message.answer("Ro'yxatdan o'tdingiz!")
    else:
        await call.answer(msg, show_alert=True)
