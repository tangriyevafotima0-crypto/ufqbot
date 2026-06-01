from typing import Any, Awaitable, Callable, Dict
import logging
import re
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import CHANNELS, SUPER_ADMIN_ID

logger = logging.getLogger(__name__)


class CheckSubMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:

        bot = data['bot']
        user_id = event.from_user.id

        if user_id == SUPER_ADMIN_ID:
            return await handler(event, data)

        # BUG #9 FIX: QR skanerlash deep link (/start chk_...) uchun
        # obuna tekshiruvini o'tkazib yuborish. Skaner CP/admin bo'lib,
        # kanal a'zoligi yo'qolgan bo'lsa ham QR ishlashi kerak.
        if isinstance(event, Message) and event.text:
            if re.match(r'^/start(@\w+)?\s+chk_', event.text.strip()):
                return await handler(event, data)

        # Agar CHANNELS bo'sh bo'lsa, tekshiruv o'tkazilmaydi
        if not CHANNELS:
            return await handler(event, data)

        not_subscribed_channels = []

        for channel in CHANNELS:
            try:
                # Convert numeric channel IDs to int
                chat_id = int(channel) if channel.lstrip('-').isdigit() else channel
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                if member.status in ['left', 'kicked', 'banned']:
                    not_subscribed_channels.append(channel)
            except Exception as e:
                logger.error(f"Kanalni tekshirishda xatolik ({channel}): {e}")
                if "chat not found" in str(e).lower() or "bot was kicked" in str(e).lower():
                    not_subscribed_channels.append(channel)
                else:
                    # Fail-closed: unknown errors (rate limits, network issues)
                    # should block access rather than silently allowing through
                    not_subscribed_channels.append(channel)

        if not_subscribed_channels:
            keyboard = []
            for ch in not_subscribed_channels:
                ch_str = str(ch).strip()
                if ch_str.startswith("@"):
                    url = f"https://t.me/{ch_str.replace('@', '')}"
                    keyboard.append([InlineKeyboardButton(
                        text=f"{ch_str} kanaliga a'zo bo'lish", url=url
                    )])
                else:
                    # For numeric IDs, try to get invite link from bot
                    try:
                        chat = await bot.get_chat(chat_id=int(ch_str))
                        if chat.invite_link:
                            keyboard.append([InlineKeyboardButton(
                                text=f"{chat.title or 'Kanal'} ga a'zo bo'lish",
                                url=chat.invite_link
                            )])
                        elif chat.username:
                            keyboard.append([InlineKeyboardButton(
                                text=f"@{chat.username} kanaliga a'zo bo'lish",
                                url=f"https://t.me/{chat.username}"
                            )])
                        else:
                            keyboard.append([InlineKeyboardButton(
                                text=f"{chat.title or 'Kanal'} (admindan havola so'rang)",
                                callback_data="cant_join"
                            )])
                    except Exception as e:
                        logger.error(f"Kanal ma'lumotini olishda xatolik ({ch_str}): {e}")
                        keyboard.append([InlineKeyboardButton(
                            text=f"Majburiy kanal (admindan havola so'rang)",
                            callback_data="cant_join"
                        )])

            keyboard.append([InlineKeyboardButton(
                text="A'zo bo'ldim, qayta tekshirish", callback_data="check_sub"
            )])
            markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

            msg_text = "Tizimdan foydalanish uchun quyidagi majburiy kanallarga a'zo bo'lishingiz shart!"

            if isinstance(event, Message):
                await event.answer(msg_text, reply_markup=markup)
            elif isinstance(event, CallbackQuery) and event.data == "check_sub":
                await event.answer("Qayta tekshirilmoqda...", show_alert=False)
                return
            elif isinstance(event, CallbackQuery) and event.data == "cant_join":
                await event.answer(
                    "Iltimos, admin bilan bog'laning va kanalga kirish havolasini so'rang.",
                    show_alert=True
                )
                return
            elif isinstance(event, CallbackQuery):
                await event.message.answer(msg_text, reply_markup=markup)
                await event.answer()
            return

        # Agar foydalanuvchi "check_sub" bosganda va hamma kanalga a'zo bo'lsa
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            await event.message.delete()
            await event.answer("Tasdiqlandi! Endi /start bosing.", show_alert=True)
            return

        return await handler(event, data)
