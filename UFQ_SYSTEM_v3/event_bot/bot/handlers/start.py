from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart
import html

from bot.database.crud import get_user_by_tg_id, create_user, get_db
from bot.keyboards.menus import main_menu_keyboard
from bot.config import SUPER_ADMIN_ID

start_router = Router()


def get_user_role(user_data: dict, telegram_id: int) -> str:
    """Determine user role from shared table data."""
    if telegram_id == SUPER_ADMIN_ID:
        return 'SUPER_ADMIN'
    if user_data.get('is_cp'):
        return 'PRESIDENT'
    return 'USER'


@start_router.message(CommandStart(deep_link=False))
async def cmd_start(message: Message):
    user = await get_user_by_tg_id(message.from_user.id)

    if user:
        role = get_user_role(user, message.from_user.id)

        # Build enhanced welcome message
        club_name = None
        if user.get('club_id'):
            async with get_db() as db:
                cursor = await db.execute("SELECT name FROM clubs WHERE id=?", (user['club_id'],))
                row = await cursor.fetchone()
                if row:
                    club_name = row['name']

        if club_name:
            role_label = "Klub Prezidenti" if user.get('is_cp') else "A'zo"
            welcome_text = (
                f"Xush kelibsiz qaytib, {html.escape(user['full_name'])}!\n"
                f"Klub: {html.escape(club_name)} ({role_label})"
            )
        else:
            welcome_text = f"Xush kelibsiz qaytib, {html.escape(user['full_name'])}!"

        await message.answer(welcome_text, reply_markup=main_menu_keyboard(role))
    else:
        # SUPER_ADMIN special case
        if message.from_user.id == SUPER_ADMIN_ID:
            user = await create_user(
                telegram_id=message.from_user.id,
                full_name=message.from_user.full_name or "Super Admin",
                username=message.from_user.username
            )
            await message.answer(
                "Siz Super Admin sifatida ro'yxatdan o'tdingiz!",
                reply_markup=main_menu_keyboard('SUPER_ADMIN')
            )
            return

        # Auto-register new user with club_id=None
        user = await create_user(
            telegram_id=message.from_user.id,
            full_name=message.from_user.full_name or "Foydalanuvchi",
            username=message.from_user.username,
            club_id=None
        )
        role = get_user_role(user, message.from_user.id)
        await message.answer(
            f"Xush kelibsiz, {html.escape(user['full_name'])}!\n"
            "Siz muvaffaqiyatli ro'yxatdan o'tdingiz.",
            reply_markup=main_menu_keyboard(role)
        )
