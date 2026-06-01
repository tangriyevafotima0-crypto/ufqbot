"""
Main Telegram bot for test grading using OMR.
Uses python-telegram-bot async (Application class).
"""

import json
import logging
import os
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, ADMIN_ID, DATA_DIR
from sheet_generator import generate_answer_sheet
from omr_scanner import scan_answer_sheet
from excel_export import generate_results_excel

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
(
    AWAITING_NUM_QUESTIONS,
    AWAITING_NUM_OPTIONS,
    AWAITING_ANSWERS,
    AWAITING_SCAN_PHOTO,
    AWAITING_STUDENT_NAME,
) = range(5)


def _get_session_path(user_id: int) -> Path:
    """Get path to session JSON file for a user."""
    return DATA_DIR / f"session_{user_id}.json"


def _load_session(user_id: int) -> dict:
    """Load session data from JSON file."""
    path = _get_session_path(user_id)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_session(user_id: int, data: dict) -> None:
    """Save session data to JSON file."""
    path = _get_session_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# Access control
# ============================================================

async def _check_admin(update: Update) -> bool:
    """Check if the user is the admin. If not, send a rejection message."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Sizda ruxsat yo'q.")
        return False
    return True


# ============================================================
# Command handlers
# ============================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command."""
    await update.message.reply_text(
        "Assalomu alaykum! Men test tekshiruvchi botman.\n\n"
        "Buyruqlar:\n"
        "/new_test - Yangi test yaratish\n"
        "/scan - Javob varaqasini skanerlash\n"
        "/results - Natijalarni Excel fayl sifatida olish\n"
        "/cancel - Bekor qilish\n\n"
        "Boshlash uchun /new_test buyrug'ini yuboring."
    )
    return ConversationHandler.END


async def new_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /new_test - start creating a new test."""
    if not await _check_admin(update):
        return ConversationHandler.END

    await update.message.reply_text(
        "Yangi test yaratamiz.\n\n"
        "Savollar sonini kiriting (1 dan 74 gacha):"
    )
    return AWAITING_NUM_QUESTIONS


async def receive_num_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive number of questions."""
    text = update.message.text.strip()
    try:
        num = int(text)
        if num < 1 or num > 74:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Iltimos, 1 dan 74 gacha son kiriting:"
        )
        return AWAITING_NUM_QUESTIONS

    context.user_data["num_questions"] = num
    await update.message.reply_text(
        f"Savollar soni: {num}\n\n"
        "Har bir savol uchun variantlar sonini kiriting (2, 3, 4 yoki 5):"
    )
    return AWAITING_NUM_OPTIONS


async def receive_num_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive number of options per question."""
    text = update.message.text.strip()
    try:
        num = int(text)
        if num < 2 or num > 5:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Iltimos, 2 dan 5 gacha son kiriting:"
        )
        return AWAITING_NUM_OPTIONS

    context.user_data["num_options"] = num
    option_letters = "ABCDE"[:num]
    num_q = context.user_data["num_questions"]
    await update.message.reply_text(
        f"Variantlar soni: {num} ({option_letters})\n\n"
        f"Endi to'g'ri javoblarni ketma-ket yozing ({num_q} ta harf).\n"
        f"Masalan: {''.join(option_letters[i % num] for i in range(min(num_q, 5)))}...\n\n"
        f"Yoki vergul bilan: A,B,C,D,A,B..."
    )
    return AWAITING_ANSWERS


async def receive_answers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive correct answers string."""
    text = update.message.text.strip().upper()
    num_q = context.user_data["num_questions"]
    num_opt = context.user_data["num_options"]
    option_letters = "ABCDE"[:num_opt]

    # Parse answers - support both "ABCD" and "A,B,C,D" formats
    if "," in text:
        answers_str = [a.strip() for a in text.split(",")]
    else:
        answers_str = list(text)

    # Validate
    if len(answers_str) != num_q:
        await update.message.reply_text(
            f"Xatolik: {len(answers_str)} ta javob kiritildi, "
            f"lekin {num_q} ta kerak.\n\n"
            f"Qaytadan kiriting:"
        )
        return AWAITING_ANSWERS

    # Convert to indices
    correct_indices = []
    for i, ans in enumerate(answers_str):
        if ans not in option_letters:
            await update.message.reply_text(
                f"Xatolik: {i+1}-savol javobida '{ans}' noto'g'ri. "
                f"Faqat {option_letters} harflaridan foydalaning.\n\n"
                f"Qaytadan kiriting:"
            )
            return AWAITING_ANSWERS
        correct_indices.append(option_letters.index(ans))

    # Save session
    user_id = update.effective_user.id
    session = _load_session(user_id)
    session["num_questions"] = num_q
    session["num_options"] = num_opt
    session["correct_answers"] = correct_indices
    session["correct_letters"] = answers_str
    session["students"] = []
    _save_session(user_id, session)

    # Generate answer sheet
    await update.message.reply_text("Javob varaqasi tayyorlanmoqda...")
    img = generate_answer_sheet(num_q, num_opt)

    # Save to temp file and send
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img.save(tmp.name, "PNG")
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"javob_varaqasi_{num_q}_savol.png",
                caption=(
                    f"Javob varaqasi tayyor!\n"
                    f"Savollar: {num_q}, Variantlar: {option_letters}\n\n"
                    f"Bu varaqani chop eting va o'quvchilarga tarqating.\n"
                    f"Tekshirish uchun /scan buyrug'ini yuboring."
                ),
            )
    finally:
        os.unlink(tmp_path)

    return ConversationHandler.END


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /scan - start scanning mode."""
    if not await _check_admin(update):
        return ConversationHandler.END

    user_id = update.effective_user.id
    session = _load_session(user_id)

    if not session.get("correct_answers"):
        await update.message.reply_text(
            "Avval /new_test orqali test yarating.\n"
            "To'g'ri javoblar kiritilmagan."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Skanerlash rejimi yoqildi.\n\n"
        "To'ldirilgan javob varaqasining rasmini yuboring.\n"
        "Diqqat:\n"
        "- Yaxshi yorug'likda suratga oling\n"
        "- Varaqani tekis joyga qo'ying\n"
        "- 4 ta burchak ko'rinsin\n\n"
        "Bekor qilish: /cancel"
    )
    return AWAITING_SCAN_PHOTO


async def receive_scan_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and process a photo of a filled answer sheet."""
    if not update.message.photo:
        await update.message.reply_text(
            "Iltimos, rasm yuboring. Matn emas."
        )
        return AWAITING_SCAN_PHOTO

    user_id = update.effective_user.id
    session = _load_session(user_id)

    # Download photo (get highest resolution)
    photo = update.message.photo[-1]
    file = await photo.get_file()

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    try:
        # Process with OMR
        result = scan_answer_sheet(
            tmp_path,
            session["num_questions"],
            session["num_options"],
            session["correct_answers"],
        )
    finally:
        os.unlink(tmp_path)

    if result["error"]:
        await update.message.reply_text(
            f"Xatolik: {result['error']}\n\n"
            "Qaytadan rasm yuboring yoki /cancel bilan bekor qiling."
        )
        return AWAITING_SCAN_PHOTO

    # Store temporary result
    context.user_data["last_scan_result"] = result

    # Show result summary
    total = result["total"]
    score = result["score"]
    percentage = round((score / total) * 100, 1) if total > 0 else 0
    answers_display = " ".join(result["answers"])

    await update.message.reply_text(
        f"Natija: {score}/{total} ({percentage}%)\n"
        f"Javoblar: {answers_display}\n\n"
        f"O'quvchining ism va familiyasini kiriting\n"
        f"(masalan: Ali Valiyev):"
    )
    return AWAITING_STUDENT_NAME


async def receive_student_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive student name and save the result."""
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    name = parts[0] if len(parts) > 0 else text
    surname = parts[1] if len(parts) > 1 else ""

    user_id = update.effective_user.id
    session = _load_session(user_id)
    result = context.user_data.get("last_scan_result", {})

    # Save student result
    student_record = {
        "name": name,
        "surname": surname,
        "score": result.get("score", 0),
        "total": result.get("total", 0),
        "answers": result.get("answers", []),
    }
    if "students" not in session:
        session["students"] = []
    session["students"].append(student_record)
    _save_session(user_id, session)

    total = result.get("total", 0)
    score = result.get("score", 0)
    pct = round((score / total) * 100, 1) if total > 0 else 0

    await update.message.reply_text(
        f"Saqlandi!\n"
        f"O'quvchi: {name} {surname}\n"
        f"Ball: {score}/{total} ({pct}%)\n\n"
        f"Jami tekshirilgan: {len(session['students'])} ta\n\n"
        f"Yana rasm yuboring yoki /results bilan natijalarni oling."
    )
    return AWAITING_SCAN_PHOTO


async def results_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /results - generate and send Excel file."""
    if not await _check_admin(update):
        return ConversationHandler.END

    user_id = update.effective_user.id
    session = _load_session(user_id)

    students = session.get("students", [])
    if not students:
        await update.message.reply_text(
            "Hali hech qanday natija yo'q.\n"
            "Avval /scan orqali javob varaqalarini skanerlang."
        )
        return ConversationHandler.END

    # Generate Excel
    buf = generate_results_excel(students)
    num_students = len(students)

    await update.message.reply_document(
        document=buf,
        filename="test_natijalari.xlsx",
        caption=f"Natijalar tayyor! Jami: {num_students} ta o'quvchi.",
    )
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel - cancel current operation."""
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


def main() -> None:
    """Run the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env faylini tekshiring.")
        return

    # Build application
    app = Application.builder().token(BOT_TOKEN).build()

    # New test conversation
    new_test_conv = ConversationHandler(
        entry_points=[CommandHandler("new_test", new_test_command)],
        states={
            AWAITING_NUM_QUESTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_num_questions)
            ],
            AWAITING_NUM_OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_num_options)
            ],
            AWAITING_ANSWERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_answers)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )

    # Scan conversation
    scan_conv = ConversationHandler(
        entry_points=[CommandHandler("scan", scan_command)],
        states={
            AWAITING_SCAN_PHOTO: [
                MessageHandler(filters.PHOTO, receive_scan_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_scan_photo),
            ],
            AWAITING_STUDENT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_student_name)
            ],
        },
        fallbacks=[
            CommandHandler("results", results_command),
            CommandHandler("cancel", cancel_command),
        ],
    )

    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(new_test_conv)
    app.add_handler(scan_conv)
    app.add_handler(CommandHandler("results", results_command))

    # Run
    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
